"""
Testes unitários para o Motor de Formação de Preço e Paridade de Exportação.
"""

import pytest
from src.domain.commodities import CommodityType
from src.domain.models import ParityCalculationInput
from src.engines.export_parity import ExportParityEngine


def test_export_parity_calculation_soja():
    # Cenário: CBOT Soja 1200 c/bu, Prêmio +80 c/bu, Dólar 5.50
    # Rota: Sorriso-MT -> Porto de Santos
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        port_premium_cents=80.0,
        usd_brl_fx=5.50,
        hub_id="sorriso_mt",
        port_id="STS",
        freight_brl_ton=420.0,
        elevation_usd_ton=8.0,
        other_port_costs_brl_ton=15.0,
        state_tax_fund_brl_bag=2.85,
        funrural_pct=1.5,
        shrinkage_loss_pct=0.3,
        brokerage_margin_usd_ton=2.0,
        current_cash_price_brl_bag=120.0,
    )
    
    res = ExportParityEngine.calculate(inp)
    
    # 1. FOB cents = 1200 + 80 = 1280
    assert res.fob_cents_bu == 1280.0
    
    # 2. FOB USD/ton = 1280 * 0.3674371 = ~470.32
    assert pytest.approx(res.fob_usd_ton, abs=0.5) == 470.32
    
    # 3. FOB BRL/ton = 470.32 * 5.50 = ~2586.76
    assert pytest.approx(res.fob_brl_ton, abs=2.0) == 2586.76
    
    # 4. FOB BRL/saca = 2586.76 * 0.06 = ~155.20
    assert pytest.approx(res.fob_brl_bag, abs=0.2) == 155.20
    
    # 5. Frete R$/saca = 420.0 * 0.06 = 25.20
    assert res.cost_breakdown.freight_brl_bag == 25.20
    
    # 6. Preço Paridade Líquido deve ser menor que o FOB
    assert res.net_parity_price_brl_bag < res.fob_brl_bag
    assert res.net_parity_price_brl_bag > 100.0
    
    # 7. Spread de originação (Paridade - Balcão atual)
    assert res.originator_spread_brl_bag == pytest.approx(
        res.net_parity_price_brl_bag - 120.0, abs=0.01
    )


def test_export_parity_missing_hub_raises_error():
    inp = ParityCalculationInput(
        commodity=CommodityType.SOJA,
        cbot_price_cents=1200.0,
        usd_brl_fx=5.50,
        hub_id="hub_inexistente",
        port_id="STS",
    )
    with pytest.raises(ValueError, match="não encontrada"):
        ExportParityEngine.calculate(inp)
