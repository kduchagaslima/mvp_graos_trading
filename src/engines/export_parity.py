"""
Motor de Cálculo de Paridade de Exportação de Grãos (FAS / FOB / Balcão Interior).
Implementa as fórmulas e convenções oficiais do mercado físico e de trading brasileiro.
"""

import uuid
from typing import Optional, Dict, Any
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
    Em conformidade com a Política de Transparência de Dados (ADR-004 e W3C PROV).
    """

    FORMULA_VERSION = "v1.2-GRAOS-007"
    PARAMETER_VERSION = "2026.10"

    @classmethod
    def calculate(cls, inp: ParityCalculationInput) -> ParityCalculationResult:
        # ==============================================================================
        # Validação da Política de Transparência de Dados (ADR-004 e W3C PROV)
        # ==============================================================================
        quote_origins = inp.quote_origins or {}
        quote_freshness = inp.quote_freshness or {}

        all_origins = [inp.origin_axis] + list(quote_origins.values())
        all_freshness = [inp.freshness_axis] + list(quote_freshness.values())

        # 1. Bloqueio Obrigatório de Origem: DEMO e UNVERIFIED
        for origin in all_origins:
            if origin == "DEMO":
                raise ValueError("Cálculo bloqueado pela Política de Transparência: inputs com origem DEMO não são permitidos em produção.")
            if origin == "UNVERIFIED":
                raise ValueError("Cálculo bloqueado pela Política de Transparência: inputs com origem UNVERIFIED não são permitidos em produção.")

        # 2. Bloqueio Obrigatório de Atualidade: UNKNOWN e STALE não autorizado
        for fresh in all_freshness:
            if fresh == "UNKNOWN":
                raise ValueError("Cálculo bloqueado pela Política de Transparência: inputs com atualidade UNKNOWN não são permitidos em produção.")
            if fresh == "STALE" and not inp.allow_stale:
                raise ValueError("Cálculo bloqueado pela Política de Transparência: inputs STALE detectados sem parâmetro allow_stale=True.")

        # 3. Propagação de Origem: DEMO > UNVERIFIED > ESTIMATED > MANUAL > OBSERVED
        if "ESTIMATED" in all_origins:
            resolved_origin = "ESTIMATED"
        elif "MANUAL" in all_origins:
            resolved_origin = "MANUAL"
        else:
            resolved_origin = "OBSERVED"

        # 4. Propagação de Atualidade: UNKNOWN > STALE > CURRENT
        if "STALE" in all_freshness:
            resolved_freshness = "STALE"
        else:
            resolved_freshness = "CURRENT"

        # 5. Indicador DECISION_READY
        decision_ready = (resolved_origin == "OBSERVED" and resolved_freshness == "CURRENT")

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
        # 2. Conversão cambial para Real (R$/ton e R$/saca de 60kg)
        fob_brl_ton = round(fob_usd_ton * inp.usd_brl_fx, 2)
        # 1 tonelada = 16.666667 sacas de 60kg (ou saca = ton * 0.06)
        ton_to_bag_factor = 0.06
        fob_brl_bag = round(fob_brl_ton * ton_to_bag_factor, 2)

        # 3. Deduções portuárias
        elevation_brl_bag = round((elevation_usd_ton * inp.usd_brl_fx) * ton_to_bag_factor, 2)
        other_port_costs_brl_bag = round(other_port_costs_ton * ton_to_bag_factor, 2)
        demurrage_usd_ton = round(inp.demurrage_usd_ton or 0.0, 2)
        demurrage_brl_bag = round((demurrage_usd_ton * inp.usd_brl_fx) * ton_to_bag_factor, 2)
        
        # Preço FAS (Free Alongside Ship) entregue no porto
        fas_brl_bag = round(fob_brl_bag - elevation_brl_bag - other_port_costs_brl_bag - demurrage_brl_bag, 2)
        
        # 4. Frete Rodoviário interior-porto
        freight_brl_bag = round(freight_ton * ton_to_bag_factor, 2)
        
        # 5. Margem da Trading (USD/ton convertida para R$/saca)
        trading_margin_brl_bag = round((inp.brokerage_margin_usd_ton * inp.usd_brl_fx) * ton_to_bag_factor, 2)
        
        # 5.1 Comissão do Corretor de Grãos
        brokerage_fee_bag = round(inp.brokerage_fee_brl_bag if inp.brokerage_payer == "TRADING" else 0.0, 2)

        # 6. Base preliminar antes de impostos sobre originação
        price_before_taxes = round(fas_brl_bag - freight_brl_bag - trading_margin_brl_bag - brokerage_fee_bag, 2)
        
        # 7. Dedução de Fundo Estadual (FETHAB / FUNDEINFRA / etc)
        state_tax_bag = round(state_tax_bag, 2)
        price_after_state_tax = round(price_before_taxes - state_tax_bag, 2)
        
        # 8. Quebra técnica (shrinkage loss)
        shrinkage_brl_bag = round(price_after_state_tax * (inp.shrinkage_loss_pct / 100.0), 2)
        
        # 9. Funrural incidente sobre valor negociado e paridade líquida FAS reconciliada
        funrural_factor = inp.funrural_pct / 100.0
        net_parity_brl_bag = round((price_after_state_tax - shrinkage_brl_bag) / (1.0 + funrural_factor), 2)
        funrural_brl_bag = round(price_after_state_tax - shrinkage_brl_bag - net_parity_brl_bag, 2)
        
        # Preço por tonelada no balcão
        net_parity_brl_ton = round(net_parity_brl_bag / ton_to_bag_factor, 2)

        # Comparativo com Balcão Físico Praticado
        originator_spread = None
        originator_margin_pct = None
        if inp.current_cash_price_brl_bag is not None and inp.current_cash_price_brl_bag > 0:
            originator_spread = round(net_parity_brl_bag - inp.current_cash_price_brl_bag, 2)
            originator_margin_pct = round((originator_spread / inp.current_cash_price_brl_bag) * 100.0, 2)

        cost_breakdown = CostBreakdownBag(
            fob_gross_brl_bag=fob_brl_bag,
            elevation_brl_bag=elevation_brl_bag,
            other_port_costs_brl_bag=other_port_costs_brl_bag,
            demurrage_brl_bag=demurrage_brl_bag,
            demurrage_usd_ton=demurrage_usd_ton,
            fas_brl_bag=fas_brl_bag,
            freight_brl_bag=freight_brl_bag,
            brokerage_fee_brl_bag=round(inp.brokerage_fee_brl_bag, 2),
            state_fund_brl_bag=state_tax_bag,
            funrural_brl_bag=funrural_brl_bag,
            shrinkage_brl_bag=shrinkage_brl_bag,
            trading_margin_brl_bag=trading_margin_brl_bag,
            net_parity_brl_bag=net_parity_brl_bag,
        )

        parity_run_id = f"run_{uuid.uuid4().hex[:12]}"
        lineage_w3c_prov = {
            "prov:id": parity_run_id,
            "prov:type": "prov:Activity",
            "prov:used": {
                "cbot_price": {"value": inp.cbot_price_cents, "unit": "cents/bu", "origin": quote_origins.get("CBOT", inp.origin_axis)},
                "usd_brl_fx": {"value": inp.usd_brl_fx, "unit": "BRL/USD", "origin": quote_origins.get("FX", inp.origin_axis)},
                "port_premium": {"value": inp.port_premium_cents, "unit": "cents/bu", "origin": quote_origins.get("PREMIUM", inp.origin_axis)},
                "freight": {"value": freight_ton, "unit": "BRL/ton", "origin": "ESTIMATED"},
                "elevation": {"value": elevation_usd_ton, "unit": "USD/ton", "origin": "ESTIMATED"},
            },
            "prov:generated": {
                "fob_usd_ton": round(fob_usd_ton, 2),
                "fob_brl_bag": round(fob_brl_bag, 2),
                "fas_brl_bag": fas_brl_bag,
                "net_parity_brl_bag": round(net_parity_brl_bag, 2),
                "net_parity_brl_ton": round(net_parity_brl_ton, 2),
            },
            "prov:wasAssociatedWith": "ExportParityEngine",
            "formula_version": cls.FORMULA_VERSION,
            "parameter_version": cls.PARAMETER_VERSION,
            "origin_axis": resolved_origin,
            "freshness_axis": resolved_freshness,
            "decision_ready": decision_ready,
        }

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
            origin_axis=resolved_origin,
            freshness_axis=resolved_freshness,
            decision_ready=decision_ready,
            parity_run_id=parity_run_id,
            lineage_w3c_prov=lineage_w3c_prov,
        )
