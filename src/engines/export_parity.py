"""
Motor de Cálculo de Paridade de Exportação de Grãos (FAS / FOB / Balcão Interior).
Implementa as fórmulas e convenções oficiais do mercado físico e de trading brasileiro.
"""

from typing import Optional
from src.domain.commodities import get_commodity_specs, CommodityType
from src.domain.locations import ORIGINATION_HUBS, PORTS
from src.domain.models import (
    ParityCalculationInput,
    ParityCalculationResult,
    CostBreakdownBag,
)


class ExportParityEngine:
    """
    Executa a formação do preço de paridade de exportação partindo da cotação internacional
    até a fazenda/armazém no interior do Brasil.
    """

    @classmethod
    def calculate(cls, inp: ParityCalculationInput) -> ParityCalculationResult:
        specs = get_commodity_specs(inp.commodity)
        
        # Validar ou carregar praça e porto
        hub = ORIGINATION_HUBS.get(inp.hub_id)
        if not hub:
            raise ValueError(f"Praça de originação '{inp.hub_id}' não encontrada.")
            
        port = PORTS.get(inp.port_id)
        if not port:
            raise ValueError(f"Porto '{inp.port_id}' não encontrado.")
            
        # Obter custos logísticos (usar os fornecidos ou padrões da tabela de frete/porto)
        freight_ton = (
            inp.freight_brl_ton
            if inp.freight_brl_ton is not None
            else hub.freight_to_port_brl_ton.get(inp.port_id, 300.0)
        )
        
        elevation_usd_ton = (
            inp.elevation_usd_ton
            if inp.elevation_usd_ton is not None
            else port.elevation_cost_usd_ton
        )
        
        other_port_costs_ton = (
            inp.other_port_costs_brl_ton
            if inp.other_port_costs_brl_ton is not None
            else port.other_port_costs_brl_ton
        )
        
        state_tax_bag = (
            inp.state_tax_fund_brl_bag
            if inp.state_tax_fund_brl_bag is not None
            else hub.state_tax_fund_brl_bag.get(inp.commodity.value, 0.0)
        )

        # 1. Preço FOB no Porto (USD/ton)
        fob_cents_bu = inp.cbot_price_cents + inp.port_premium_cents
        fob_usd_ton = fob_cents_bu * specs.cents_per_bu_to_usd_per_ton
        
        # 2. Conversão cambial para Real (R$/ton e R$/saca de 60kg)
        fob_brl_ton = fob_usd_ton * inp.usd_brl_fx
        # 1 tonelada = 16.666667 sacas de 60kg (ou saca = ton * 0.06)
        ton_to_bag_factor = 0.06
        fob_brl_bag = fob_brl_ton * ton_to_bag_factor

        # 3. Deduções portuárias
        elevation_brl_bag = (elevation_usd_ton * inp.usd_brl_fx) * ton_to_bag_factor
        other_port_costs_brl_bag = other_port_costs_ton * ton_to_bag_factor
        
        # Preço FAS (Free Alongside Ship) entregue no porto
        fas_brl_bag = fob_brl_bag - elevation_brl_bag - other_port_costs_brl_bag
        
        # 4. Frete Rodoviário interior-porto
        freight_brl_bag = freight_ton * ton_to_bag_factor
        
        # 5. Margem da Trading (USD/ton convertida para R$/saca)
        trading_margin_brl_bag = (inp.brokerage_margin_usd_ton * inp.usd_brl_fx) * ton_to_bag_factor
        
        # 5.1 Comissão do Corretor de Grãos
        # Se a corretagem for assumida pela trading (TRADING), ela deduz da paridade máxima ofertada
        brokerage_fee_bag = inp.brokerage_fee_brl_bag if inp.brokerage_payer == "TRADING" else 0.0

        # 6. Base preliminar antes de impostos sobre originação
        price_before_taxes = fas_brl_bag - freight_brl_bag - trading_margin_brl_bag - brokerage_fee_bag
        
        # 7. Dedução de Fundo Estadual (FETHAB / FUNDEINFRA / etc)
        # O FETHAB é em R$/saca fixa
        price_after_state_tax = price_before_taxes - state_tax_bag
        
        # 8. Quebra técnica (shrinkage loss)
        shrinkage_brl_bag = price_after_state_tax * (inp.shrinkage_loss_pct / 100.0)
        
        # 9. Funrural (produtor pessoa física) incidente sobre o valor bruto negociado
        # Paridade líquida = (Preço - Fundo - Quebra) / (1 + Funrural_pct)
        funrural_factor = inp.funrural_pct / 100.0
        net_parity_brl_bag = (price_after_state_tax - shrinkage_brl_bag) / (1.0 + funrural_factor)
        funrural_brl_bag = net_parity_brl_bag * funrural_factor
        
        # Preço por tonelada no balcão
        net_parity_brl_ton = net_parity_brl_bag / ton_to_bag_factor

        # Comparativo com Balcão Físico Praticado
        originator_spread = None
        originator_margin_pct = None
        if inp.current_cash_price_brl_bag is not None and inp.current_cash_price_brl_bag > 0:
            originator_spread = net_parity_brl_bag - inp.current_cash_price_brl_bag
            originator_margin_pct = (originator_spread / inp.current_cash_price_brl_bag) * 100.0

        cost_breakdown = CostBreakdownBag(
            fob_gross_brl_bag=round(fob_brl_bag, 2),
            elevation_brl_bag=round(elevation_brl_bag, 2),
            other_port_costs_brl_bag=round(other_port_costs_brl_bag, 2),
            fas_brl_bag=round(fas_brl_bag, 2),
            freight_brl_bag=round(freight_brl_bag, 2),
            brokerage_fee_brl_bag=round(inp.brokerage_fee_brl_bag, 2),
            state_fund_brl_bag=round(state_tax_bag, 2),
            funrural_brl_bag=round(funrural_brl_bag, 2),
            shrinkage_brl_bag=round(shrinkage_brl_bag, 2),
            trading_margin_brl_bag=round(trading_margin_brl_bag, 2),
            net_parity_brl_bag=round(net_parity_brl_bag, 2),
        )

        return ParityCalculationResult(
            commodity=inp.commodity,
            hub_id=inp.hub_id,
            hub_name=hub.name,
            port_id=inp.port_id,
            port_name=port.name,
            cbot_price_cents=inp.cbot_price_cents,
            port_premium_cents=inp.port_premium_cents,
            fob_cents_bu=fob_cents_bu,
            usd_brl_fx=inp.usd_brl_fx,
            fob_usd_ton=round(fob_usd_ton, 2),
            fob_brl_ton=round(fob_brl_ton, 2),
            fob_brl_bag=round(fob_brl_bag, 2),
            cost_breakdown=cost_breakdown,
            net_parity_price_brl_bag=round(net_parity_brl_bag, 2),
            net_parity_price_brl_ton=round(net_parity_brl_ton, 2),
            current_cash_price_brl_bag=inp.current_cash_price_brl_bag,
            originator_spread_brl_bag=round(originator_spread, 2) if originator_spread is not None else None,
            originator_margin_pct=round(originator_margin_pct, 2) if originator_margin_pct is not None else None,
        )
