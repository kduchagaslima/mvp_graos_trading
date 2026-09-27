"""
Definições de commodities agrícolas, unidades de medida e fatores de conversão física/financeira.
"""

from enum import Enum
from dataclasses import dataclass


class CommodityType(str, Enum):
    SOJA = "SOJA"
    MILHO = "MILHO"


@dataclass(frozen=True)
class CommoditySpecs:
    name: str
    ticker_cbot: str
    bushel_weight_lbs: float
    bushel_weight_kg: float
    bushels_per_ton: float
    bags_60kg_per_ton: float = 1000.0 / 60.0  # 16.666667 sacas por tonelada

    @property
    def cents_per_bu_to_usd_per_ton(self) -> float:
        """
        Fator para converter cents/bushel diretamente para USD/tonelada métrica.
        (cents / 100) * bushels_per_ton = cents * (bushels_per_ton / 100)
        """
        return self.bushels_per_ton / 100.0

    @property
    def bags_per_bushel(self) -> float:
        """Quantidade de sacas de 60kg contidas em 1 bushel."""
        return self.bushel_weight_kg / 60.0


COMMODITY_SPECS = {
    CommodityType.SOJA: CommoditySpecs(
        name="Soja em Grão",
        ticker_cbot="ZS=F",
        bushel_weight_lbs=60.0,
        bushel_weight_kg=27.2155,
        bushels_per_ton=36.7437,
    ),
    CommodityType.MILHO: CommoditySpecs(
        name="Milho em Grão",
        ticker_cbot="ZC=F",
        bushel_weight_lbs=56.0,
        bushel_weight_kg=25.4012,
        bushels_per_ton=39.3683,
    ),
}


def get_commodity_specs(commodity: CommodityType | str) -> CommoditySpecs:
    if isinstance(commodity, str):
        commodity = CommodityType(commodity.upper())
    return COMMODITY_SPECS[commodity]
