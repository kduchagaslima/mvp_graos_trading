"""
Modelos de dados (Pydantic) para entradas, saídas e relatórios analíticos do MVP de Trading.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from src.domain.commodities import CommodityType


class ParityCalculationInput(BaseModel):
    commodity: CommodityType = Field(default=CommodityType.SOJA, description="Commodity (SOJA ou MILHO)")
    cbot_price_cents: float = Field(..., gt=0, description="Preço CBOT em cents de USD por bushel")
    port_premium_cents: float = Field(default=0.0, description="Prêmio F.O.B. no porto em cents de USD por bushel")
    usd_brl_fx: float = Field(..., gt=0, description="Taxa de câmbio USD/BRL")
    hub_id: str = Field(..., description="ID da praça de originação no interior")
    port_id: str = Field(..., description="ID do porto de escoamento")
    
    # Parâmetros logísticos e custos (opcionais com preenchimento padrão do hub/porto)
    freight_brl_ton: Optional[float] = Field(default=None, description="Frete rodoviário interior-porto em R$/tonelada")
    elevation_usd_ton: Optional[float] = Field(default=None, description="Custo de elevação portuária em USD/tonelada")
    other_port_costs_brl_ton: Optional[float] = Field(default=None, description="Outras despesas portuárias em R$/tonelada")
    demurrage_usd_ton: float = Field(default=0.0, ge=0.0, description="Provisão de sobreestadia/demurrage portuário em USD/tonelada")
    state_tax_fund_brl_bag: Optional[float] = Field(default=None, description="Fundo tributário estadual em R$/saca")
    
    # Margens e deduções comerciais
    funrural_pct: float = Field(default=1.5, ge=0.0, le=10.0, description="Funrural percentual (%)")
    shrinkage_loss_pct: float = Field(default=0.3, ge=0.0, le=5.0, description="Quebra técnica / umidade (%)")
    brokerage_margin_usd_ton: float = Field(default=2.0, ge=0.0, description="Margem desejada da trading em USD/ton")
    brokerage_payer: str = Field(default="NONE", description="Responsável pela corretagem: 'NONE' (direto), 'TRADING' (paga pela trading), 'SELLER' (retida do produtor)")
    brokerage_fee_brl_bag: float = Field(default=0.0, ge=0.0, description="Comissão do corretor em R$/saca (ex: 0.50)")
    
    # Preço de mercado balcão atual (para cálculo de Basis e margem da originação)
    current_cash_price_brl_bag: Optional[float] = Field(default=None, description="Preço de balcão praticado na praça (R$/saca)")


class CostBreakdownBag(BaseModel):
    fob_gross_brl_bag: float
    elevation_brl_bag: float
    other_port_costs_brl_bag: float
    demurrage_brl_bag: float = 0.0
    demurrage_usd_ton: float = 0.0
    fas_brl_bag: float
    freight_brl_bag: float
    brokerage_fee_brl_bag: float = 0.0
    state_fund_brl_bag: float
    funrural_brl_bag: float
    shrinkage_brl_bag: float
    trading_margin_brl_bag: float
    net_parity_brl_bag: float


class ParityCalculationResult(BaseModel):
    commodity: CommodityType
    hub_id: str
    hub_name: str
    port_id: str
    port_name: str
    
    # Cotações de referência
    cbot_price_cents: float
    port_premium_cents: float
    fob_cents_bu: float
    usd_brl_fx: float
    
    # Preços no Porto (FOB)
    fob_usd_ton: float
    fob_brl_ton: float
    fob_brl_bag: float
    
    # Custos e despesas por saca (60kg)
    cost_breakdown: CostBreakdownBag
    
    # Preço Paridade no Balcão Interior
    net_parity_price_brl_bag: float
    net_parity_price_brl_ton: float
    
    # Comparativo com mercado físico
    current_cash_price_brl_bag: Optional[float] = None
    originator_spread_brl_bag: Optional[float] = None  # Paridade - Balcão
    originator_margin_pct: Optional[float] = None


class CarryCalculationInput(BaseModel):
    spot_contract_name: str = Field(default="Spot (Março)", description="Nome do contrato spot/curto")
    forward_contract_name: str = Field(default="Julho", description="Nome do contrato futuro de entrega")
    spot_price_brl_bag: float = Field(..., gt=0, description="Preço spot na praça em R$/saca")
    forward_price_brl_bag: float = Field(..., gt=0, description="Preço forward na praça em R$/saca")
    months_to_forward: float = Field(default=4.0, gt=0, description="Meses até a entrega futura")
    
    storage_cost_brl_bag_month: float = Field(default=0.65, ge=0, description="Armazenagem física (R$/saca/mês)")
    financial_cost_pct_month: float = Field(default=0.85, ge=0, description="Custo de capital / CDI (% ao mês)")
    technical_loss_pct: float = Field(default=0.20, ge=0, description="Perda técnica no período (%)")


class CarryCalculationResult(BaseModel):
    spot_price_brl_bag: float
    forward_price_brl_bag: float
    gross_spread_brl_bag: float
    months: float
    
    total_storage_cost_brl_bag: float
    total_financial_cost_brl_bag: float
    total_technical_loss_brl_bag: float
    total_carry_cost_brl_bag: float
    
    net_carry_brl_bag: float
    net_return_pct: float
    annualized_return_pct: float
    recommendation: str
    detailed_rationale: str


class ScenarioSimulationInput(BaseModel):
    base_input: ParityCalculationInput
    fx_shift_pct: float = Field(default=0.0, description="Variação percentual do câmbio (%) ex: -5.0 para queda de 5%")
    cbot_shift_cents: float = Field(default=0.0, description="Variação em cents do CBOT ex: +30")
    premium_shift_cents: float = Field(default=0.0, description="Variação do prêmio em cents ex: -10")
    freight_shift_pct: float = Field(default=0.0, description="Variação percentual do frete (%) ex: +10.0")


class ScenarioSimulationResult(BaseModel):
    base_parity_brl_bag: float
    simulated_parity_brl_bag: float
    diff_brl_bag: float
    diff_pct: float
    base_margin_brl_bag: Optional[float] = None
    simulated_margin_brl_bag: Optional[float] = None
    applied_shifts: Dict[str, float]
