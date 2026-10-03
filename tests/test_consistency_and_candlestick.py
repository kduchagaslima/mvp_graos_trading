"""
Suíte de Testes para Snapshot Único (F03), Candlestick Rastreável (F04) e Rota BACEN Read-Only (F05).
"""

from datetime import date, datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.db.connection import Base, get_db
from src.db.models import MarketQuote, ExtractionLog, DataKind, FreshnessStatus
from src.db.repository import MarketDataRepository
from src.services.market_data import market_service


@pytest.fixture
def test_db_session():
    """Cria banco de dados SQLite isolado em memória com suporte a múltiplas threads."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.clear()
    session.close()


def test_f03_snapshot_coherence_with_database(test_db_session):
    """
    Ticket F03: O snapshot consolidado (endpoint e serviço) deve reconciliar 'data'
    com as cotações persistidas no banco, eliminando divergências com seeds em memória.
    """
    now_utc = datetime.now(timezone.utc)
    today = date.today()

    # Injeta cotações customizadas no banco
    custom_fx = 5.7230
    custom_cbot_soja = 1290.50
    test_db_session.add(
        MarketQuote(
            quote_date=today,
            timestamp=now_utc,
            observed_at=now_utc,
            category="FX",
            symbol="USD_BRL_PTAX_VENDA",
            price=custom_fx,
            unit="BRL",
            source="BCB_PTAX_OLINDA",
            data_kind=DataKind.OBSERVED.value,
            freshness=FreshnessStatus.CURRENT.value,
        )
    )
    test_db_session.add(
        MarketQuote(
            quote_date=today,
            timestamp=now_utc,
            observed_at=now_utc,
            category="FUTURES",
            commodity="SOJA",
            symbol="ZS=F",
            price=custom_cbot_soja,
            unit="cents/bu",
            source="CME_GROUP",
            data_kind=DataKind.OBSERVED.value,
            freshness=FreshnessStatus.CURRENT.value,
        )
    )
    test_db_session.commit()

    client = TestClient(app)
    resp = client.get("/api/market-data/snapshot")
    assert resp.status_code == 200
    data = resp.json()

    assert data["source"] == "DATABASE"
    assert data["reconciled"] is True
    # O valor em 'data' DEVE refletir o valor real do banco de dados (não a seed antiga)
    assert data["data"]["fx_usd_brl"] == custom_fx
    assert data["data"]["cbot_prices"]["SOJA"]["last_price_cents"] == custom_cbot_soja


def test_f04_candlestick_synthetic_fallback_is_demarcated():
    """
    Ticket F04: Quando o histórico no banco é insuficiente, a série de velas é gerada
    com determinismo e demarcada com data_kind='DEMO' e is_synthetic=True, sem random solto.
    """
    candles = market_service.get_candlestick_series("CBOT_SOJA", days=20)
    assert len(candles) == 20

    for c in candles:
        assert c["is_synthetic"] is True
        assert c["data_kind"] == DataKind.DEMO.value
        # Invariantes estritas de candle
        assert c["high"] >= c["open"]
        assert c["high"] >= c["close"]
        assert c["low"] <= c["open"]
        assert c["low"] <= c["close"]
        assert c["volume"] > 0

    # Continuidade: close[i] == open[i+1]
    for i in range(len(candles) - 1):
        assert candles[i]["close"] == candles[i + 1]["open"]


def test_f04_candlestick_uses_real_database_history(test_db_session):
    """
    Ticket F04: Quando há cotações reais no banco para o ativo, o candlestick
    deve utilizar as cotações observadas reais (is_synthetic=False).
    """
    now_utc = datetime.now(timezone.utc)
    base_date = date.today() - timedelta(days=5)

    # Injeta 5 dias de cotações para ZS=F
    prices = [1180.0, 1185.0, 1192.0, 1188.0, 1195.0]
    for i, p in enumerate(prices):
        d = base_date + timedelta(days=i)
        test_db_session.add(
            MarketQuote(
                quote_date=d,
                timestamp=now_utc,
                observed_at=now_utc,
                category="FUTURES",
                commodity="SOJA",
                symbol="ZS=F",
                price=p,
                unit="cents/bu",
                source="CME_GROUP",
                data_kind=DataKind.OBSERVED.value,
                freshness=FreshnessStatus.CURRENT.value,
            )
        )
    test_db_session.commit()

    candles = market_service.get_candlestick_series("CBOT_SOJA", days=5, db=test_db_session)
    assert len(candles) == 5
    for c in candles:
        assert c["is_synthetic"] is False
        assert c["data_kind"] == DataKind.OBSERVED.value


def test_f05_macro_indices_get_is_strictly_read_only(test_db_session):
    """
    Ticket F05: GET /api/macro/indices deve ser estritamente de leitura.
    Mesmo com o banco vazio, NÃO deve criar ExtractionLog nem gravar registros em market_quotes.
    """
    client = TestClient(app)

    # Verifica estado inicial do banco
    quotes_count_before = test_db_session.query(MarketQuote).count()
    logs_count_before = test_db_session.query(ExtractionLog).count()
    assert quotes_count_before == 0
    assert logs_count_before == 0

    # Executa GET
    resp = client.get("/api/macro/indices")
    assert resp.status_code == 200
    indices = resp.json()
    assert "CDI_ANNUAL" in indices
    assert indices["CDI_ANNUAL"]["source"] == "SEED_FALLBACK"
    assert indices["CDI_ANNUAL"]["data_kind"] == DataKind.DEMO.value

    # Confirma que NENHUMA mutação ocorreu no banco de dados
    quotes_count_after = test_db_session.query(MarketQuote).count()
    logs_count_after = test_db_session.query(ExtractionLog).count()
    assert quotes_count_after == 0
    assert logs_count_after == 0
