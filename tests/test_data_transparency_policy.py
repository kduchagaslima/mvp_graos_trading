"""
Testes automatizados para a Política de Transparência de Dados e Rastreabilidade W3C PROV.
Valida:
1. Bloqueio obrigatório de inputs DEMO e UNVERIFIED na produção.
2. Bloqueio de inputs UNKNOWN e STALE (quando allow_stale=False).
3. Propagação de origem e atualidade.
4. Geração e conformidade de metadados de Lineage W3C PROV e parity_run_id.
5. Políticas dinâmicas de frescor (CBOT 20min, PTAX, CEPEA 24h).
"""

import pytest
from datetime import datetime, timezone, timedelta
from src.domain.commodities import CommodityType
from src.domain.models import ParityCalculationInput
from src.engines.export_parity import ExportParityEngine
from src.services.freshness import (
    evaluate_freshness,
    get_freshness_policy_id,
    FreshnessStatus,
    POLICY_CBOT_DYNAMIC_20M,
    POLICY_PTAX_BULLETIN,
    POLICY_CEPEA_PHYSICAL_24H,
)
from src.db.models import MarketQuotesLineage


def test_block_demo_data_in_calculation():
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        origin_axis="DEMO",
    )
    with pytest.raises(ValueError, match="DEMO"):
        ExportParityEngine.calculate(inp)


def test_block_unverified_data_in_calculation():
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        quote_origins={"CBOT": "UNVERIFIED"},
    )
    with pytest.raises(ValueError, match="UNVERIFIED"):
        ExportParityEngine.calculate(inp)


def test_block_unknown_freshness():
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        freshness_axis="UNKNOWN",
    )
    with pytest.raises(ValueError, match="UNKNOWN"):
        ExportParityEngine.calculate(inp)


def test_block_stale_without_allow_stale():
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        freshness_axis="STALE",
        allow_stale=False,
    )
    with pytest.raises(ValueError, match="STALE"):
        ExportParityEngine.calculate(inp)


def test_allow_stale_with_flag():
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        freshness_axis="STALE",
        allow_stale=True,
    )
    res = ExportParityEngine.calculate(inp)
    assert res.freshness_axis == "STALE"
    assert res.decision_ready is False


def test_origin_and_freshness_propagation():
    # Input com origem MANUAL -> resultado herda MANUAL, decision_ready é False
    inp_manual = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        origin_axis="MANUAL",
        freshness_axis="CURRENT",
    )
    res_manual = ExportParityEngine.calculate(inp_manual)
    assert res_manual.origin_axis == "MANUAL"
    assert res_manual.decision_ready is False

    # Input 100% OBSERVED + CURRENT -> decision_ready é True
    inp_observed = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        origin_axis="OBSERVED",
        freshness_axis="CURRENT",
    )
    res_observed = ExportParityEngine.calculate(inp_observed)
    assert res_observed.origin_axis == "OBSERVED"
    assert res_observed.decision_ready is True


def test_w3c_prov_lineage_generation():
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        port_premium_cents=80.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
    )
    res = ExportParityEngine.calculate(inp)
    assert res.parity_run_id is not None
    assert res.parity_run_id.startswith("run_")
    assert res.lineage_w3c_prov is not None
    assert res.lineage_w3c_prov["prov:type"] == "prov:Activity"
    assert "cbot_price" in res.lineage_w3c_prov["prov:used"]
    assert "net_parity_brl_bag" in res.lineage_w3c_prov["prov:generated"]


def test_dynamic_freshness_policies():
    assert get_freshness_policy_id("FUTURES", "ZS=F") == POLICY_CBOT_DYNAMIC_20M
    assert get_freshness_policy_id("FX", "USD_BRL_PTAX_VENDA") == POLICY_PTAX_BULLETIN
    assert get_freshness_policy_id("PHYSICAL_CASH", "CASH_SORRISO_SOJA") == POLICY_CEPEA_PHYSICAL_24H

    # Teste CBOT estrito: 25 minutos durante dia útil deve ser STALE em modo estrito
    now = datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc)  # Segunda-feira
    obs_recent = now - timedelta(minutes=15)
    obs_old = now - timedelta(minutes=25)

    assert evaluate_freshness("FUTURES", "CBOT_SOJA", obs_recent, now_dt=now, strict_cbot_minutes=True) == FreshnessStatus.CURRENT
    assert evaluate_freshness("FUTURES", "CBOT_SOJA", obs_old, now_dt=now, strict_cbot_minutes=True) == FreshnessStatus.STALE


def test_market_quotes_lineage_model():
    lineage = MarketQuotesLineage(
        quote_id=1,
        parity_snapshot_id=10,
        parity_run_id="run_test123",
        formula_version="v1.2",
        parameter_version="2026.10",
        origin_axis="OBSERVED",
        freshness_axis="CURRENT",
        decision_ready=True,
        inputs_json='{"test": true}',
    )
    d = lineage.to_dict()
    assert d["parity_run_id"] == "run_test123"
    assert d["origin_axis"] == "OBSERVED"
    assert d["decision_ready"] is True


def test_api_parity_calculate_persists_lineage_and_get_endpoint():
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.db.connection import Base, get_db
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    payload = {
        "commodity": "SOJA",
        "cbot_price_cents": 1250.0,
        "port_premium_cents": 85.0,
        "usd_brl_fx": 5.55,
        "hub_id": "sorriso_mt",
        "port_id": "STS",
    }

    res = client.post("/api/parity/calculate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["decision_ready"] is True
    assert "parity_run_id" in data
    run_id = data["parity_run_id"]

    # Consulta endpoint de linhagem
    res_lineage = client.get(f"/api/parity/lineage/{run_id}")
    assert res_lineage.status_code == 200
    lineage_data = res_lineage.json()
    assert lineage_data["parity_run_id"] == run_id
    assert lineage_data["origin_axis"] == "OBSERVED"
    assert lineage_data["freshness_axis"] == "CURRENT"
    assert lineage_data["decision_ready"] is True

    # Consulta run inexistente -> 404
    res_404 = client.get("/api/parity/lineage/run_inexistente_999")
    assert res_404.status_code == 404

    app.dependency_overrides.clear()


def test_frontend_transparency_and_privacy_elements():
    """Valida a presença de componentes de transparência e privacidade no frontend HTML."""
    from pathlib import Path
    html_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")

    # Item 1.1: Selo e linhagem interativa
    assert 'id="badge-decision-ready"' in content
    assert 'id="btn-view-lineage"' in content
    assert 'id="lineage-modal"' in content
    assert 'openLineageModal' in content
    assert 'closeLineageModal' in content
    assert 'lineage-used-tbody' in content
    assert 'lineage-generated-container' in content

    # Item 1.2: Modal de termos/privacidade e link de rodapé
    assert 'id="privacy-modal"' in content
    assert 'openPrivacyModal' in content
    assert 'closePrivacyModal' in content
    assert '5 (cinco) anos' in content or '5 anos' in content
    assert 'Ag Data Transparent' in content
    assert 'Inteligência Artificial' in content
    assert 'LGPD' in content


