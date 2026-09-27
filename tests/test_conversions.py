"""
Testes unitários para conferência matemática das conversões de unidades de commodities agrícolas.
"""

import pytest
from src.domain.commodities import CommodityType, get_commodity_specs


def test_soja_conversion_factors():
    specs = get_commodity_specs(CommodityType.SOJA)
    
    # 1 bushel de soja = 60 lbs = 27.2155 kg
    assert pytest.approx(specs.bushel_weight_kg, rel=1e-3) == 27.2155
    
    # 1 tonelada métrica = 1000 kg = ~36.7437 bushels
    assert pytest.approx(specs.bushels_per_ton, rel=1e-3) == 36.7437
    
    # Fator de conversão cents/bu para USD/ton:
    # 1000 cents/bu = $10.00/bu * 36.7437 bu/ton = $367.437 / ton
    usd_ton = 1000.0 * specs.cents_per_bu_to_usd_per_ton
    assert pytest.approx(usd_ton, rel=1e-3) == 367.437


def test_milho_conversion_factors():
    specs = get_commodity_specs(CommodityType.MILHO)
    
    # 1 bushel de milho = 56 lbs = 25.4012 kg
    assert pytest.approx(specs.bushel_weight_kg, rel=1e-3) == 25.4012
    
    # 1 tonelada métrica = 1000 kg = ~39.3683 bushels
    assert pytest.approx(specs.bushels_per_ton, rel=1e-3) == 39.3683
    
    # Fator de conversão cents/bu para USD/ton:
    usd_ton = 500.0 * specs.cents_per_bu_to_usd_per_ton
    assert pytest.approx(usd_ton, rel=1e-3) == 196.841


def test_bags_per_ton():
    specs_soja = get_commodity_specs(CommodityType.SOJA)
    specs_milho = get_commodity_specs(CommodityType.MILHO)
    
    # No Brasil, 1 saca = 60 kg, logo 1 ton = 16.6667 sacas
    assert pytest.approx(specs_soja.bags_60kg_per_ton, rel=1e-3) == 16.6667
    assert pytest.approx(specs_milho.bags_60kg_per_ton, rel=1e-3) == 16.6667
