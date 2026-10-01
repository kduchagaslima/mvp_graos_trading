"""
Testes unitários e de integração para histórico de fretes rodoviários,
indicadores estatísticos e arbitragem logística entre corredores.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.connection import Base, get_db
from src.services.market_data import market_service
from src.api.main import app


@pytest.fixture
def engine():
    """Cria engine SQLite compartilhado em memória para testes isolados."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def client(engine):
    """Cria cliente TestClient FastAPI com injeção segura de sessão."""
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_get_freight_routes():
    routes = market_service.get_freight_routes()
    assert len(routes) > 0

    sorriso_bcr = next(
        (r for r in routes if r["origin_id"] == "sorriso_mt" and r["destination_id"] == "BCR"),
        None,
    )
    assert sorriso_bcr is not None
    assert sorriso_bcr["corridor"] == "Arco Norte"
    assert sorriso_bcr["distance_km"] == 1450
    assert sorriso_bcr["freight_brl_ton"] == 360.0
    assert sorriso_bcr["freight_brl_bag"] == round(360.0 * 0.06, 2)

    sorriso_sts = next(
        (r for r in routes if r["origin_id"] == "sorriso_mt" and r["destination_id"] == "STS"),
        None,
    )
    assert sorriso_sts is not None
    assert sorriso_sts["corridor"] == "Santos / Sudeste"
    assert sorriso_sts["is_default"] is True


def test_get_freight_history_periods():
    for days in [15, 30, 60]:
        history = market_service.get_freight_history("sorriso_mt", "STS", days=days)
        assert history["origin_id"] == "sorriso_mt"
        assert history["destination_id"] == "STS"
        assert history["period_days"] == days
        assert len(history["series"]) == days

        assert history["min_rate_ton"] <= history["avg_rate_ton"] <= history["max_rate_ton"]
        assert history["current_rate_bag"] == round(history["current_rate_ton"] * 0.06, 2)

        for pt in history["series"]:
            assert "date" in pt
            assert "price_ton" in pt
            assert "price_bag" in pt
            assert "source" in pt
            assert pt["price_bag"] == round(pt["price_ton"] * 0.06, 2)


def test_get_freight_arbitrage_analysis_sorriso():
    analysis = market_service.get_freight_arbitrage_analysis("sorriso_mt", commodity="SOJA", usd_brl_fx=5.50)
    assert analysis["origin_id"] == "sorriso_mt"
    assert analysis["commodity"] == "SOJA"
    assert len(analysis["ports_comparison"]) >= 3

    # Barcarena (BCR) deve ser mais barata que Santos (STS)
    bcr = next(c for c in analysis["ports_comparison"] if c["port_id"] == "BCR")
    sts = next(c for c in analysis["ports_comparison"] if c["port_id"] == "STS")

    assert bcr["total_logistics_brl_ton"] < sts["total_logistics_brl_ton"]
    assert bcr["status"] == "FAVORABLE"
    assert sts["status"] == "BENCHMARK"
    assert analysis["best_port_id"] == "BCR"
    assert analysis["max_savings_brl_ton"] > 0
    assert analysis["max_savings_brl_bag"] > 0


def test_get_freight_arbitrage_invalid_origin():
    with pytest.raises(ValueError):
        market_service.get_freight_arbitrage_analysis("cidade_inexistente")


def test_freight_api_routes(client):
    res = client.get("/api/freight/routes")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 10


def test_freight_api_history(client):
    res = client.get("/api/freight/history?origin=sorriso_mt&destination=STS&days=30")
    assert res.status_code == 200
    data = res.json()
    assert data["origin_id"] == "sorriso_mt"
    assert data["destination_id"] == "STS"
    assert len(data["series"]) == 30


def test_freight_api_arbitrage(client):
    res = client.get("/api/freight/arbitrage?origin=sorriso_mt")
    assert res.status_code == 200
    data = res.json()
    assert data["best_port_id"] == "BCR"
    assert "ports_comparison" in data

    # Rota inválida deve retornar 404
    res_invalid = client.get("/api/freight/arbitrage?origin=unknown_origin")
    assert res_invalid.status_code == 404
