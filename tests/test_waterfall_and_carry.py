"""
Suíte de Testes para Waterfall Reconciliado (F06) e Carrego Unificado com Taxa Efetiva e Datas (F07).
"""

from datetime import date
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.domain.commodities import CommodityType
from src.domain.models import ParityCalculationInput, CarryCalculationInput
from src.engines.export_parity import ExportParityEngine
from src.engines.carry_cost import CarryCostEngine


def test_f06_waterfall_reconciliation_exactness():
    """
    Ticket F06: Todas as deduções portuárias, logísticas e tributárias devem bater
    exatamente com a paridade líquida calculada, sem resíduos ocultos.
    """
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        port_premium_cents=80.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        demurrage_usd_ton=0.50,
        funrural_pct=1.5,
        shrinkage_loss_pct=0.3,
        brokerage_margin_usd_ton=2.0,
        brokerage_payer="TRADING",
        brokerage_fee_brl_bag=0.50,
    )
    res = ExportParityEngine.calculate(inp)
    cb = res.cost_breakdown

    # 1. FAS entregue no porto
    expected_fas = (
        cb.fob_gross_brl_bag
        - cb.elevation_brl_bag
        - cb.other_port_costs_brl_bag
        - cb.demurrage_brl_bag
    )
    assert cb.fas_brl_bag == pytest.approx(expected_fas, abs=0.01)

    # 2. Reconciliação total das deduções
    total_interior_costs = (
        cb.freight_brl_bag
        + cb.trading_margin_brl_bag
        + cb.brokerage_fee_brl_bag
        + cb.state_fund_brl_bag
        + cb.shrinkage_brl_bag
        + cb.funrural_brl_bag
    )
    expected_net = cb.fas_brl_bag - total_interior_costs
    assert cb.net_parity_brl_bag == pytest.approx(expected_net, abs=0.01)
    assert res.net_parity_price_brl_bag == cb.net_parity_brl_bag


def test_f06_batch_parity_matrix_overrides():
    """
    Ticket F06: O endpoint /api/parity/batch deve aceitar parâmetros customizados de
    tributação e corretagem para reconciliar com a análise de originação.
    """
    client = TestClient(app)
    resp = client.post(
        "/api/parity/batch",
        params={
            "commodity": "SOJA",
            "port_id": "STS",
            "cbot_price_cents": 1200.0,
            "port_premium_cents": 80.0,
            "usd_brl_fx": 5.50,
            "funrural_pct": 2.0,
            "brokerage_fee_brl_bag": 0.50,
        },
    )
    assert resp.status_code == 200
    batch_results = resp.json()
    assert len(batch_results) > 0
    for item in batch_results:
        assert item["cost_breakdown"]["brokerage_fee_brl_bag"] == 0.50
        assert item["net_parity_price_brl_bag"] > 0


def test_f07_carry_cost_annual_effective_rate_conversion():
    """
    Ticket F07: Quando informada a taxa anual (ex: 12% a.a.), a taxa mensal efetiva
    deve ser calculada pela convenção matemática (1+i)^(1/12) - 1 ≈ 0.9489% a.m.
    """
    inp = CarryCalculationInput(
        spot_price_brl_bag=120.0,
        forward_price_brl_bag=135.0,
        months_to_forward=4.0,
        financial_cost_annual_pct=12.0,  # 12% ao ano
    )
    res = CarryCostEngine.calculate(inp)

    # (1 + 0.12)^(1/12) - 1 = 0.00948879... -> ~0.9489%
    assert res.effective_monthly_rate_pct == pytest.approx(0.9489, abs=1e-3)
    assert res.recommendation_code == "POSITIVE_CARRY"
    assert "CARREGAR" in res.recommendation


def test_f07_carry_cost_calendar_dates_calculation():
    """
    Ticket F07: Permite cálculo baseado em datas reais de spot e liquidação forward.
    """
    # 01/03/2026 até 01/07/2026 -> 122 dias (~4.01 meses)
    inp = CarryCalculationInput(
        spot_price_brl_bag=130.0,
        forward_price_brl_bag=131.0,
        spot_date=date(2026, 3, 1),
        forward_date=date(2026, 7, 1),
        financial_cost_pct_month=0.85,
    )
    res = CarryCostEngine.calculate(inp)

    assert res.months == pytest.approx(4.01, abs=0.05)
    assert res.recommendation_code == "NEGATIVE_CARRY"
    assert "VENDER SPOT" in res.recommendation


def test_f07_carry_cost_invalid_dates_raises_error():
    """
    Ticket F07: forward_date anterior ou igual à spot_date deve falhar com erro amigável.
    """
    inp = CarryCalculationInput(
        spot_price_brl_bag=120.0,
        forward_price_brl_bag=125.0,
        spot_date=date(2026, 7, 1),
        forward_date=date(2026, 3, 1),  # data no passado!
    )
    with pytest.raises(ValueError, match="posterior à data spot"):
        CarryCostEngine.calculate(inp)
