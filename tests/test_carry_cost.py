"""
Testes unitários para o Motor de Curva Forward e Análise de Carrego.
"""

import pytest
from src.domain.models import CarryCalculationInput
from src.engines.carry_cost import CarryCostEngine


def test_positive_carry_decision():
    # Preço spot = 120, Preço Forward (4 meses) = 135 (Spread = 15.00)
    # Custos: 4 * 0.60 = 2.40 armazém, juros ~ 4.15, quebra ~ 0.24 = Total ~6.79
    # Net carry = ~8.21 -> Recomendação "CARREGAR"
    inp = CarryCalculationInput(
        spot_price_brl_bag=120.0,
        forward_price_brl_bag=135.0,
        months_to_forward=4.0,
        storage_cost_brl_bag_month=0.60,
        financial_cost_pct_month=0.85,
        technical_loss_pct=0.20,
    )
    res = CarryCostEngine.calculate(inp)
    
    assert res.gross_spread_brl_bag == 15.0
    assert res.total_storage_cost_brl_bag == 2.40
    assert res.net_carry_brl_bag > 5.0
    assert "CARREGAR" in res.recommendation


def test_negative_carry_inversion():
    # Preço spot = 130, Preço Forward = 131 (Spread apenas de 1.00 para 4 meses)
    # Custos superam em muito o spread -> Recomendação "VENDER SPOT"
    inp = CarryCalculationInput(
        spot_price_brl_bag=130.0,
        forward_price_brl_bag=131.0,
        months_to_forward=4.0,
        storage_cost_brl_bag_month=0.65,
        financial_cost_pct_month=0.90,
        technical_loss_pct=0.25,
    )
    res = CarryCostEngine.calculate(inp)
    
    assert res.gross_spread_brl_bag == 1.0
    assert res.net_carry_brl_bag < 0.0
    assert "VENDER SPOT" in res.recommendation
