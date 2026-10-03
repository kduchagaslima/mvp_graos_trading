"""
Testes de Regressão Financeira de Referência (Ticket F01).
Congela os resultados dos motores de cálculo (Paridade, Carrego, Arbitragem de Frete e Tributos)
com base nos parâmetros auditados em 02/10/2026, garantindo isolamento total da internet.
"""

import pytest
from src.domain.commodities import CommodityType, COMMODITY_SPECS
from src.domain.models import ParityCalculationInput, CarryCalculationInput
from src.engines.export_parity import ExportParityEngine
from src.engines.carry_cost import CarryCostEngine
from src.services.market_data import market_service
from tests.fixtures.deterministic_market_data import (
    AUDIT_FX_REFERENCE,
    AUDIT_FX_AUDIT_SCENARIO,
    AUDIT_CBOT_SOJA_CENTS,
    AUDIT_CBOT_MILHO_CENTS,
    AUDIT_PORT_PREMIUMS_CENTS,
    AUDIT_PORT_COSTS,
    AUDIT_STATE_TAX_FUNDS,
    AUDIT_FREIGHT_RATES_TON,
    AUDIT_CASH_PRICES_BRL_BAG,
)


def test_parity_sensitivity_fx_audit_comparison():
    """
    Compara o cálculo de paridade de exportação com PTAX 5.4850 vs PTAX 5.2238 (cenário de auditoria).
    Comprova que a variação cambial é absorvida proporcionalmente no FOB e FAS sem distorções.
    """
    input_base = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=AUDIT_CBOT_SOJA_CENTS,
        port_premium_cents=AUDIT_PORT_PREMIUMS_CENTS["STS"]["SOJA"],
        usd_brl_fx=AUDIT_FX_REFERENCE,
        hub_id="sorriso_mt",
        port_id="STS",
        elevation_usd_ton=AUDIT_PORT_COSTS["STS"]["elevation_usd_ton"],
        other_port_costs_brl_ton=AUDIT_PORT_COSTS["STS"]["other_port_costs_brl_ton"],
        demurrage_usd_ton=AUDIT_PORT_COSTS["STS"]["demurrage_risk_usd_ton"],
        state_tax_fund_brl_bag=AUDIT_STATE_TAX_FUNDS["MT"]["SOJA"],
        current_cash_price_brl_bag=AUDIT_CASH_PRICES_BRL_BAG["sorriso_mt"]["SOJA"],
    )
    res_base = ExportParityEngine.calculate(input_base)

    input_audit = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=AUDIT_CBOT_SOJA_CENTS,
        port_premium_cents=AUDIT_PORT_PREMIUMS_CENTS["STS"]["SOJA"],
        usd_brl_fx=AUDIT_FX_AUDIT_SCENARIO,
        hub_id="sorriso_mt",
        port_id="STS",
        elevation_usd_ton=AUDIT_PORT_COSTS["STS"]["elevation_usd_ton"],
        other_port_costs_brl_ton=AUDIT_PORT_COSTS["STS"]["other_port_costs_brl_ton"],
        demurrage_usd_ton=AUDIT_PORT_COSTS["STS"]["demurrage_risk_usd_ton"],
        state_tax_fund_brl_bag=AUDIT_STATE_TAX_FUNDS["MT"]["SOJA"],
        current_cash_price_brl_bag=AUDIT_CASH_PRICES_BRL_BAG["sorriso_mt"]["SOJA"],
    )
    res_audit = ExportParityEngine.calculate(input_audit)

    # Invariante 1: O preço FOB em USD é idêntico em ambos os cenários (depende apenas de CBOT + Prêmio)
    assert res_base.fob_usd_ton == res_audit.fob_usd_ton
    assert res_base.fob_usd_ton == pytest.approx((1185.25 + 90.0) * 0.367437, rel=1e-3)

    # Invariante 2: O preço FOB em BRL diminui com o câmbio mais baixo (5.2238 vs 5.4850)
    assert res_audit.fob_brl_ton < res_base.fob_brl_ton
    assert res_audit.fob_brl_bag < res_base.fob_brl_bag

    # Invariante 3: A Paridade Líquida FAS Interior reflete a queda cambial
    assert res_audit.net_parity_price_brl_bag < res_base.net_parity_price_brl_bag

    # Invariante 4: FETHAB de MT incide exatamente com R$ 2.85/sc em ambos
    assert res_base.cost_breakdown.state_fund_brl_bag == 2.85
    assert res_audit.cost_breakdown.state_fund_brl_bag == 2.85


def test_carry_cost_neutral_tolerance_baseline():
    """
    Testa o motor de custo de carrego para o cenário base congelado e a zona neutra.
    """
    carry_input = CarryCalculationInput(
        spot_price_brl_bag=125.00,
        forward_price_brl_bag=133.80,
        months_to_forward=4.0,
        storage_cost_brl_bag_month=0.50,
        financial_cost_pct_month=0.85,
        technical_loss_pct=0.25,
    )
    res = CarryCostEngine.calculate(carry_input)

    # Spread bruto: 133.80 - 125.00 = 8.80
    assert res.gross_spread_brl_bag == pytest.approx(8.80, abs=0.01)

    # Armazenagem total para 4 meses: 4 * 0.50 = 2.00
    assert res.total_storage_cost_brl_bag == pytest.approx(2.00, abs=0.01)

    # Custo de carrego total positivo e coerente
    assert res.total_carry_cost_brl_bag > 0
    assert res.net_carry_brl_bag == pytest.approx(res.gross_spread_brl_bag - res.total_carry_cost_brl_bag, abs=0.01)


def test_freight_arbitrage_sorriso_barcarena_baseline():
    """
    Verifica a arbitragem logística congelada de Sorriso (Barcarena vs Santos).
    Barcarena deve apresentar custo logístico inferior e economia > R$ 60/ton.
    """
    analysis = market_service.get_freight_arbitrage_analysis(
        origin_id="sorriso_mt",
        commodity="SOJA",
        usd_brl_fx=AUDIT_FX_REFERENCE,
    )
    assert analysis["origin_id"] == "sorriso_mt"
    assert analysis["best_port_id"] == "BCR"
    assert analysis["best_corridor"] == "Arco Norte"
    assert analysis["max_savings_brl_ton"] > 60.00
    assert analysis["max_savings_brl_bag"] > 3.60

    sts_item = next(c for c in analysis["ports_comparison"] if c["port_id"] == "STS")
    bcr_item = next(c for c in analysis["ports_comparison"] if c["port_id"] == "BCR")

    assert bcr_item["total_logistics_brl_ton"] < sts_item["total_logistics_brl_ton"]
    assert bcr_item["status"] == "FAVORABLE"
    assert sts_item["status"] == "BENCHMARK"


def test_conversion_metric_invariants():
    """
    Verifica que os fatores de conversão de commodities permanecem matematicamente exatos.
    """
    soy = COMMODITY_SPECS[CommodityType.SOJA]
    corn = COMMODITY_SPECS[CommodityType.MILHO]

    # Soja: 60 lbs = 27.2155 kg -> 36.7437 bu/ton -> fator 0.367437
    assert soy.bushel_weight_kg == pytest.approx(27.2155, abs=1e-3)
    assert soy.bushels_per_ton == pytest.approx(36.7437, abs=1e-3)
    assert soy.cents_per_bu_to_usd_per_ton == pytest.approx(0.367437, abs=1e-4)

    # Milho: 56 lbs = 25.4012 kg -> 39.3683 bu/ton -> fator 0.393683
    assert corn.bushel_weight_kg == pytest.approx(25.4012, abs=1e-3)
    assert corn.bushels_per_ton == pytest.approx(39.3683, abs=1e-3)
    assert corn.cents_per_bu_to_usd_per_ton == pytest.approx(0.393683, abs=1e-4)
