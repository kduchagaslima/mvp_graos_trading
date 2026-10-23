"""
FastAPI Backend para o MVP de Market Data e Trading de Grãos.
Expõe endpoints REST para cálculo de paridade, custo de carrego, simulação de estresse,
extração e persistência de dados de mercado no banco relacional.
"""

import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from src.db.connection import init_db, get_db
from src.db.repository import MarketDataRepository
from src.db.models import (
    ExtractionLog,
    MarketQuote,
    DataKind,
    FreshnessStatus,
    User,
    Organization,
    Membership,
    MembershipRole,
    CostProfile,
    Invitation,
    SavedScenario,
    MarketQuotesLineage,
    CompanyFreightContract,
    TradeTicket,
    MarketAlert,
)
from src.domain.commodities import CommodityType, COMMODITY_SPECS
from src.domain.locations import ORIGINATION_HUBS, PORTS, DOMESTIC_INDUSTRIES
from src.domain.models import (
    ParityCalculationInput,
    ParityCalculationResult,
    CarryCalculationInput,
    CarryCalculationResult,
    ScenarioSimulationInput,
    ScenarioSimulationResult,
    CostProfileCreateInput,
    CostProfileUpdateInput,
    InvitationCreateInput,
    OrganizationCreateInput,
    SavedScenarioCreateInput,
    ProposalComparisonRequest,
    ProposalItemInput,
    CompanyFreightContractCreateInput,
    CompanyFreightContractBatchInput,
    TradeTicketCreateInput,
    MarketAlertCreateInput,
    MarketAlertUpdateInput,
    MarketAlertEvaluateInput,
)
from src.engines.export_parity import ExportParityEngine
from src.engines.carry_cost import CarryCostEngine
from src.engines.stress_tester import StressTesterEngine
from src.services.market_data import market_service
from src.services.extractor import extract_and_persist_market_data
from src.services.b3_extractor import extract_and_persist_b3_data
from src.services.bacen_extractor import extract_and_persist_macro_data, BacenMacroExtractor
from src.scheduler.runner import get_scheduler_status
from src.api.auth import (
    get_current_user,
    get_current_membership,
    require_role,
    require_platform_operator,
)
import json
import uuid


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa tabelas do banco de dados na inicialização
    init_db()
    yield


app = FastAPI(
    title="Grain Trading Market Data & Projection API",
    description="Motor de formação de preço de grãos, paridade de exportação FAS/FOB, carrego e persistência de mercado.",
    version="1.0.0",
    lifespan=lifespan,
)

# ==============================================================================
# Endurecimento de Políticas de Rede (CORS) e Cache (Ticket F15 - Atividade 4)
# ==============================================================================

raw_allowed = os.getenv(
    "ALLOWED_ORIGINS",
    "https://d1qfxp2g7u6ypc.cloudfront.net,http://localhost:8501,http://localhost:3000,http://127.0.0.1:8501",
)
allowed_origins = [o.strip() for o in raw_allowed.split(",") if o.strip()]
allow_creds = "*" not in allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=allow_creds,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_and_cache_headers(request, call_next):
    """
    Garante que respostas da API nunca sejam armazenadas em caches públicos/compartilhados
    e adiciona cabeçalhos defensivos de proteção contra clickjacking e MIME-sniffing.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "mvp-graos-trading"}


@app.get("/api/metadata/commodities")
def get_commodities():
    return {
        key: {
            "name": spec.name,
            "ticker_cbot": spec.ticker_cbot,
            "bushel_weight_kg": spec.bushel_weight_kg,
            "bushels_per_ton": spec.bushels_per_ton,
            "cents_to_usd_ton": spec.cents_per_bu_to_usd_per_ton,
        }
        for key, spec in COMMODITY_SPECS.items()
    }


@app.get("/api/metadata/locations")
def get_locations():
    return {
        "ports": PORTS,
        "hubs": ORIGINATION_HUBS,
    }


# ==============================================================================
# ENDPOINTS DE MARKET DATA E BANCO DE DADOS
# ==============================================================================

@app.get("/api/market-data/snapshot")
def get_market_snapshot(db: Session = Depends(get_db)):
    return market_service.get_snapshot(db=db)


@app.post("/api/market-data/extract")
def trigger_market_data_extraction(
    operator: User = Depends(require_platform_operator),
    db: Session = Depends(get_db),
):
    """
    Executa a extração completa de Market Data (PTAX, CBOT, Prêmios, Físico e Frete)
    e persiste os dados de forma transacional e idempotente no banco de dados.
    Acesso restrito a operadores da plataforma (Ticket F12).
    """
    try:
        summary = extract_and_persist_market_data(db=db)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market-data/quotes")
def get_latest_quotes_from_db(db: Session = Depends(get_db)):
    """Retorna todas as cotações ativas mais recentes persistidas no banco."""
    quotes = MarketDataRepository.get_all_latest_quotes(db)
    return [q.to_dict() for q in quotes]


@app.get("/api/market-data/history/{symbol}")
def get_quote_history(symbol: str, limit: int = 50, db: Session = Depends(get_db)):
    """Retorna o histórico temporal de cotações para um símbolo específico."""
    history = MarketDataRepository.get_quotes_history(db=db, symbol=symbol, limit=limit)
    return [q.to_dict() for q in history]


@app.get("/api/market-data/logs")
def get_extraction_logs(
    limit: int = 10,
    operator: User = Depends(require_platform_operator),
    db: Session = Depends(get_db),
):
    """
    Retorna os logs recentes de auditoria de extração de dados.
    Acesso restrito a operadores da plataforma (Ticket F12).
    """
    logs = db.query(ExtractionLog).order_by(ExtractionLog.id.desc()).limit(limit).all()
    return [l.to_dict() for l in logs]


@app.post("/api/market-data/fx/refresh")
def refresh_live_fx(operator: User = Depends(require_platform_operator)):
    """
    Atualiza taxa spot ao vivo. Acesso restrito a operadores da plataforma (Ticket F12).
    """
    rate = market_service.fetch_live_usd_brl()
    return {"status": "success", "usd_brl_fx": rate}


@app.post("/api/b3/extract")
def trigger_b3_extraction(
    session_type: str = "MANUAL",
    operator: User = Depends(require_platform_operator),
    db: Session = Depends(get_db),
):
    """
    Executa a extração dos futuros agrícolas da B3 (CCM Milho e SJC Soja)
    e indicadores CEPEA/ESALQ, persistindo de forma transacional no banco.
    Acesso restrito a operadores da plataforma (Ticket F12).
    """
    try:
        summary = extract_and_persist_b3_data(db=db, session_type=session_type)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/b3/quotes")
def get_latest_b3_quotes(db: Session = Depends(get_db)):
    """Retorna as cotações ativas mais recentes de derivativos B3 e índices CEPEA."""
    quotes = (
        db.query(MarketQuote)
        .filter(MarketQuote.category.in_(["B3_FUTURES", "CEPEA_INDEX"]))
        .order_by(MarketQuote.commodity, MarketQuote.symbol)
        .all()
    )
    return [q.to_dict() for q in quotes]


@app.get("/api/scheduler/status")
def get_scheduler_info(operator: User = Depends(require_platform_operator)):
    """
    Retorna o status atual do agendador e metadados das rotinas configuradas.
    Acesso restrito a operadores da plataforma (Ticket F12).
    """
    return get_scheduler_status()


@app.get("/api/macro/indices")
def get_macro_indices(db: Session = Depends(get_db)):
    """
    Retorna os índices macroeconômicos mais recentes (CDI, Selic, IPCA, IGPM).
    Operação estritamente de leitura (Ticket F05) sem efeitos colaterais ou mutações no banco.
    """
    quotes = (
        db.query(MarketQuote)
        .filter(MarketQuote.category == "MACRO_INDEX")
        .order_by(MarketQuote.symbol, MarketQuote.id.desc())
        .all()
    )
    if not quotes:
        from src.services.bacen_extractor import BACEN_SGS_SERIES
        today_str = date.today().strftime("%d/%m/%Y")
        return {
            key: {
                "symbol": key,
                "name": conf["name"],
                "value": conf["fallback"],
                "unit": conf["unit"],
                "ref_date": today_str,
                "source": "SEED_FALLBACK",
                "data_kind": DataKind.DEMO.value,
                "freshness": FreshnessStatus.UNKNOWN.value,
            }
            for key, conf in BACEN_SGS_SERIES.items()
        }

    result = {}
    for q in quotes:
        if q.symbol not in result:
            meta = json.loads(q.metadata_json) if q.metadata_json else {}
            result[q.symbol] = {
                "symbol": q.symbol,
                "name": meta.get("name", q.symbol),
                "value": q.price,
                "unit": q.unit,
                "ref_date": meta.get("ref_date", q.quote_date.strftime("%d/%m/%Y")),
                "source": q.source,
                "data_kind": q.data_kind,
                "freshness": q.freshness,
            }
    return result


@app.post("/api/macro/extract")
def trigger_macro_extraction(
    session_type: str = "MANUAL",
    operator: User = Depends(require_platform_operator),
    db: Session = Depends(get_db),
):
    """
    Dispara a extração e persistência dos índices oficiais do BACEN SGS.
    Acesso restrito a operadores da plataforma (Ticket F12).
    """
    try:
        summary = extract_and_persist_macro_data(db=db, session_type=session_type)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ports/summary")
def get_ports_summary(usd_brl_fx: Optional[float] = None):
    """
    Retorna o comparativo detalhado de tarifas e riscos de sobreestadia
    para todos os portos brasileiros de escoamento.
    """
    fx = usd_brl_fx or market_service.get_fx_usd_brl()
    summary = []
    for port_id, p in PORTS.items():
        elev_brl_ton = p.elevation_cost_usd_ton * fx
        demurrage_brl_ton = p.demurrage_risk_usd_ton * fx
        total_port_brl_ton = elev_brl_ton + p.other_port_costs_brl_ton + demurrage_brl_ton
        total_port_usd_ton = total_port_brl_ton / fx
        total_port_brl_bag = total_port_brl_ton * 0.06

        summary.append({
            "id": p.id,
            "name": p.name,
            "state": p.state,
            "elevation_usd_ton": p.elevation_cost_usd_ton,
            "other_port_costs_brl_ton": p.other_port_costs_brl_ton,
            "typical_waiting_days": p.typical_waiting_days,
            "demurrage_risk_usd_ton": p.demurrage_risk_usd_ton,
            "main_terminals": p.main_terminals,
            "total_port_cost_usd_ton": round(total_port_usd_ton, 2),
            "total_port_cost_brl_ton": round(total_port_brl_ton, 2),
            "total_port_cost_brl_bag": round(total_port_brl_bag, 2),
        })
    return summary


@app.get("/api/tax-funds/summary")
def get_tax_funds_summary():
    """
    Retorna a tabela consolidada de fundos tributários estaduais incidentes
    (FETHAB MT, FUNDEINFRA GO, PRODEAGRO BA, Isenções PR/RS Lei Kandir).
    """
    from src.domain.locations import STATE_TAX_FUNDS
    return STATE_TAX_FUNDS


@app.get("/api/industries/summary")
def get_industries_summary():
    """
    Retorna o catálogo de indústrias domésticas consumidoras (esmagadoras de soja,
    usinas de etanol de milho e fábricas de ração animal).
    """
    return [
        {
            "id": ind.id,
            "name": ind.name,
            "state": ind.state,
            "city": ind.city,
            "industry_type": ind.industry_type,
            "commodity_handled": ind.commodity_handled,
            "typical_freight_from_hub": ind.typical_freight_from_hub,
            "icms_internal_rate": ind.icms_internal_rate,
            "icms_interstate_rate": ind.icms_interstate_rate,
        }
        for ind in DOMESTIC_INDUSTRIES.values()
    ]


# ==============================================================================
# ENDPOINTS DE LOGÍSTICA E FRETE RODOVIÁRIO
# ==============================================================================

@app.get("/api/freight/routes")
def get_freight_routes(db: Session = Depends(get_db)):
    """
    Retorna a lista de rotas rodoviárias cadastradas com tarifas spot,
    distâncias estimadas e corredores logísticos.
    """
    return market_service.get_freight_routes(db=db)


@app.get("/api/freight/history")
def get_freight_history(
    origin: str = "sorriso_mt",
    destination: str = "STS",
    days: int = 30,
    db: Session = Depends(get_db),
):
    """
    Retorna a série temporal e indicadores estatísticos de frete rodoviário
    para o trecho e período (30D, 60D, 90D) selecionados.
    """
    return market_service.get_freight_history(
        origin_id=origin,
        destination_id=destination,
        days=days,
        db=db,
    )


@app.get("/api/freight/arbitrage")
def get_freight_arbitrage(
    origin: str = "sorriso_mt",
    commodity: str = "SOJA",
    usd_brl_fx: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """
    Analisa a arbitragem logística entre corredores (Santos vs. Arco Norte vs. Sul)
    para uma praça de originação, computando frete rodoviário, elevação portuária e demurrage.
    """
    try:
        return market_service.get_freight_arbitrage_analysis(
            origin_id=origin,
            commodity=commodity,
            usd_brl_fx=usd_brl_fx,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/freight/antt-floor")
def get_freight_antt_floor(db: Session = Depends(get_db)):
    """
    Retorna os pisos mínimos regulatórios de frete rodoviário da ANTT (Resolução nº 5.867/2020)
    e matriz de conformidade legal para cada corredor logístico de grãos.
    """
    from src.services.antt_freight import ANTTFreightService
    return ANTTFreightService.get_corridors_compliance_summary(db=db)





@app.get("/api/market-data/candlestick/{symbol}")
def get_candlestick_data(symbol: str, days: int = 30, db: Session = Depends(get_db)):
    """
    Gera histórico em formato OHLC (Open, High, Low, Close) para gráficos Candlestick.
    Suporta: CBOT_SOJA, CBOT_MILHO, USD_BRL, B3_MILHO, PARIDADE_FAS.
    """
    candles = market_service.get_candlestick_series(symbol=symbol, days=days, db=db)
    return candles


# ==============================================================================
# ENDPOINTS DE CÁLCULO E MOTORES DE PROJEÇÃO
# ==============================================================================

@app.post("/api/parity/calculate", response_model=ParityCalculationResult)
def calculate_export_parity(payload: ParityCalculationInput, db: Session = Depends(get_db)):
    try:
        result = ExportParityEngine.calculate(payload)
        if db is not None and result.parity_run_id:
            try:
                lineage_record = MarketQuotesLineage(
                    parity_run_id=result.parity_run_id,
                    formula_version=ExportParityEngine.FORMULA_VERSION,
                    parameter_version=ExportParityEngine.PARAMETER_VERSION,
                    origin_axis=result.origin_axis,
                    freshness_axis=result.freshness_axis,
                    decision_ready=result.decision_ready,
                    inputs_json=json.dumps(result.lineage_w3c_prov or {}),
                )
                db.add(lineage_record)
                db.commit()
            except Exception:
                db.rollback()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/parity/lineage/{parity_run_id}")
def get_parity_lineage(parity_run_id: str, db: Session = Depends(get_db)):
    """
    Retorna a linhagem e evidências de proveniência W3C PROV de um cálculo de paridade (Ticket F02 / ADR-004).
    """
    lineage = db.query(MarketQuotesLineage).filter(MarketQuotesLineage.parity_run_id == parity_run_id).first()
    if not lineage:
        raise HTTPException(status_code=404, detail=f"Linhagem não encontrada para o identificador '{parity_run_id}'.")
    return lineage.to_dict()


@app.post("/api/parity/batch")
def calculate_batch_parity(
    commodity: CommodityType = CommodityType.SOJA,
    port_id: str = "STS",
    cbot_price_cents: Optional[float] = None,
    port_premium_cents: Optional[float] = None,
    usd_brl_fx: Optional[float] = None,
    demurrage_usd_ton: Optional[float] = 0.0,
    funrural_pct: Optional[float] = None,
    shrinkage_loss_pct: Optional[float] = None,
    brokerage_margin_usd_ton: Optional[float] = None,
    brokerage_payer: Optional[str] = "NONE",
    brokerage_fee_brl_bag: Optional[float] = 0.0,
):
    """
    Calcula a paridade de exportação simultaneamente para todas as praças de originação,
    permitindo comparar a atratividade regional de compra com parâmetros consistentes (Ticket F06).
    """
    cbot = cbot_price_cents or market_service.get_cbot_price(commodity.value)
    premium = port_premium_cents or market_service.get_port_premium(port_id, commodity.value)
    fx = usd_brl_fx or market_service.get_fx_usd_brl()

    kwargs = {}
    if funrural_pct is not None:
        kwargs["funrural_pct"] = funrural_pct
    if shrinkage_loss_pct is not None:
        kwargs["shrinkage_loss_pct"] = shrinkage_loss_pct
    if brokerage_margin_usd_ton is not None:
        kwargs["brokerage_margin_usd_ton"] = brokerage_margin_usd_ton
    if brokerage_payer is not None:
        kwargs["brokerage_payer"] = brokerage_payer
    if brokerage_fee_brl_bag is not None:
        kwargs["brokerage_fee_brl_bag"] = brokerage_fee_brl_bag

    results = []
    for hub_id, hub in ORIGINATION_HUBS.items():
        cash_price = market_service.get_cash_price(hub_id, commodity.value)
        inp = ParityCalculationInput(
            commodity=commodity,
            cbot_price_cents=cbot,
            port_premium_cents=premium,
            usd_brl_fx=fx,
            hub_id=hub_id,
            port_id=port_id,
            demurrage_usd_ton=demurrage_usd_ton or 0.0,
            current_cash_price_brl_bag=cash_price,
            **kwargs,
        )
        res = ExportParityEngine.calculate(inp)
        results.append(res)
        
    return results


@app.post("/api/carry/calculate", response_model=CarryCalculationResult)
def calculate_carry(payload: CarryCalculationInput):
    try:
        result = CarryCostEngine.calculate(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stress/simulate", response_model=ScenarioSimulationResult)
def simulate_stress_scenario(payload: ScenarioSimulationInput):
    try:
        result = StressTesterEngine.simulate_scenario(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================================================
# Endpoints de Identidade, Organizações e Custos Privados (Tickets F09, F10)
# ==============================================================================

@app.get("/api/me")
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retorna o perfil do usuário autenticado e suas filiações ativas a organizações (Ticket F09).
    """
    memberships = (
        db.query(Membership)
        .filter(Membership.user_id == current_user.id, Membership.is_active == True)
        .all()
    )
    return {
        "id": current_user.id,
        "cognito_sub": current_user.cognito_sub,
        "email": current_user.email,
        "name": current_user.name,
        "is_active": current_user.is_active,
        "is_platform_operator": current_user.is_platform_operator,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "memberships": [m.to_dict() for m in memberships],
    }


def seed_organization_demo_data(db: Session, org_id: int, user_id: int) -> Dict[str, Any]:
    """
    Pré-popula a organização com um portfólio completo de dados de demonstração (Trial de 14 dias):
    - 4 Contratos de Frete Rodoviário negociados (rotas exportação e consumo interno)
    - 3 Cenários de Paridade salvos (Soja Exportação, Milho Safrinha, Soja Indústria Doméstica)
    - 2 Boletas Formais de Negociação (Trade Tickets) auditadas
    - 4 Alertas de Mercado e Metas de Preço (Watchlist do trader)
    """
    now = datetime.now(timezone.utc)
    today = date.today()

    # 1. Contratos de Frete Privados
    contracts = [
        CompanyFreightContract(
            organization_id=org_id,
            origin_id="sorriso_mt",
            destination_id="STS",
            carrier_name="Expresso Rondonópolis Grãos",
            contract_code=f"CTR-DEMO-{org_id}-01",
            freight_brl_ton=385.0,
            volume_contracted_tons=25000.0,
            valid_from=today,
            valid_until=today + timedelta(days=180),
            is_active=True,
            notes="Tarifa contratada com desconto de frota dedicada Sorriso -> Santos",
        ),
        CompanyFreightContract(
            organization_id=org_id,
            origin_id="rio_verde_go",
            destination_id="STS",
            carrier_name="TransCerrado Logística Integrada",
            contract_code=f"CTR-DEMO-{org_id}-02",
            freight_brl_ton=260.0,
            volume_contracted_tons=15000.0,
            valid_from=today,
            valid_until=today + timedelta(days=180),
            is_active=True,
            notes="Frete contratado para escoamento safrinha Rio Verde -> Santos",
        ),
        CompanyFreightContract(
            organization_id=org_id,
            origin_id="sorriso_mt",
            destination_id="IND_LRV_FS",
            carrier_name="TransNorte MT",
            contract_code=f"CTR-DEMO-{org_id}-03",
            freight_brl_ton=42.0,
            volume_contracted_tons=30000.0,
            valid_from=today,
            valid_until=today + timedelta(days=180),
            is_active=True,
            notes="Rota curta de transferência para Usina de Etanol FS em Lucas do Rio Verde",
        ),
        CompanyFreightContract(
            organization_id=org_id,
            origin_id="rondonopolis_mt",
            destination_id="IND_ROO_BUNGE",
            carrier_name="RodoGrãos MT",
            contract_code=f"CTR-DEMO-{org_id}-04",
            freight_brl_ton=35.0,
            volume_contracted_tons=20000.0,
            valid_from=today,
            valid_until=today + timedelta(days=180),
            is_active=True,
            notes="Entrega local para polo industrial esmagador em Rondonópolis",
        ),
    ]
    for c in contracts:
        db.add(c)

    # 2. Cenários Salvos
    scenarios = [
        SavedScenario(
            organization_id=org_id,
            user_id=user_id,
            name="Soja Safra 2026 Sorriso x Santos (Exportação Base)",
            commodity="SOJA",
            hub_id="sorriso_mt",
            port_id="STS",
            cbot_price_cents=1045.5,
            port_premium_cents=65.0,
            usd_brl_fx=5.65,
            freight_cost_brl_ton=385.0,
            elevation_cost_usd_ton=10.5,
            demurrage_risk_usd_ton=2.5,
            other_port_costs_usd_ton=15.0,
            tax_fund_brl_bag=0.0,
            net_parity_brl_bag=124.80,
            net_parity_brl_ton=2080.00,
            fob_usd_ton=408.03,
            notes="Cenário base da mesa para travar compras na fazenda em Sorriso/MT.",
        ),
        SavedScenario(
            organization_id=org_id,
            user_id=user_id,
            name="Milho Safrinha Rio Verde x Santos (Exportação)",
            commodity="MILHO",
            hub_id="rio_verde_go",
            port_id="STS",
            cbot_price_cents=435.0,
            port_premium_cents=45.0,
            usd_brl_fx=5.65,
            freight_cost_brl_ton=260.0,
            elevation_cost_usd_ton=9.5,
            demurrage_risk_usd_ton=2.0,
            other_port_costs_usd_ton=12.0,
            tax_fund_brl_bag=0.0,
            net_parity_brl_bag=54.20,
            net_parity_brl_ton=903.33,
            fob_usd_ton=188.97,
            notes="Simulação comercial de originação milho safrinha sudoeste goiano.",
        ),
        SavedScenario(
            organization_id=org_id,
            user_id=user_id,
            name="Soja Mercado Interno - Esmagamento Bunge Rondonópolis",
            commodity="SOJA",
            hub_id="rondonopolis_mt",
            port_id="IND_ROO_BUNGE",
            cbot_price_cents=1045.5,
            port_premium_cents=0.0,
            usd_brl_fx=5.65,
            freight_cost_brl_ton=35.0,
            elevation_cost_usd_ton=0.0,
            demurrage_risk_usd_ton=0.0,
            other_port_costs_usd_ton=0.0,
            tax_fund_brl_bag=0.0,
            net_parity_brl_bag=128.50,
            net_parity_brl_ton=2141.67,
            fob_usd_ton=408.03,
            notes="Entrega mercado doméstico MT com isenção/diferimento de ICMS e sem taxas portuárias.",
        ),
    ]
    for s in scenarios:
        db.add(s)

    # 3. Boletas Formais (Trade Tickets)
    tickets = [
        TradeTicket(
            ticket_number=f"BOL-{org_id}-DEMO-001",
            organization_id=org_id,
            user_id=user_id,
            commodity="SOJA",
            crop_year="2025/2026",
            seller_name="Agropecuária Terra Santa Ltda",
            seller_document="12.345.678/0001-90",
            seller_farm="Fazenda Boa Esperança - Sorriso/MT",
            location_hub_id="sorriso_mt",
            destination_port_id="STS",
            quantity_bags=50000.0,
            quantity_tons=3000.0,
            price_per_bag_brl=126.50,
            total_amount_brl=6325000.0,
            payment_terms="30 dias após emissão da NF de entrega e classificação",
            delivery_period="Março/2026",
            quality_specs="Padrão Exportação ANEC 41 (Umidade máx 14%, Impureza máx 1%, Avariados máx 8%)",
            parity_run_id=f"RUN-DEMO-{org_id}-SOJA",
            cbot_reference=1045.5,
            fx_reference=5.65,
            freight_reference=385.0,
            antt_compliant=True,
            decision_ready=True,
            status="CONFIRMED",
            notes="Boleta fechada com margem travada no porto de Santos via contrato dedilhado.",
        ),
        TradeTicket(
            ticket_number=f"BOL-{org_id}-DEMO-002",
            organization_id=org_id,
            user_id=user_id,
            commodity="MILHO",
            crop_year="2025/2026",
            seller_name="Cooperativa Agrícola Regional de Rio Verde",
            seller_document="98.765.432/0001-10",
            seller_farm="Silos Armazém Central - Rio Verde/GO",
            location_hub_id="rio_verde_go",
            destination_port_id="STS",
            quantity_bags=30000.0,
            quantity_tons=1800.0,
            price_per_bag_brl=53.50,
            total_amount_brl=1605000.0,
            payment_terms="À vista contra apresentação do ticket de balança do armazém",
            delivery_period="Julho/2026",
            quality_specs="Padrão ANEC 43 (Umidade máx 14.5%, Impureza máx 1.5%, Quebrados máx 5%)",
            parity_run_id=f"RUN-DEMO-{org_id}-MILHO",
            cbot_reference=435.0,
            fx_reference=5.65,
            freight_reference=260.0,
            antt_compliant=True,
            decision_ready=True,
            status="CONFIRMED",
            notes="Lote de milho safrinha destinado a programa exportador de julho.",
        ),
    ]
    for t in tickets:
        db.add(t)

    # 4. Alertas de Mercado (Watchlist)
    alerts = [
        MarketAlert(
            organization_id=org_id,
            user_id=user_id,
            name="Meta Paridade Soja Sorriso > R$ 130,00/sc",
            alert_type="PARITY_ABOVE",
            commodity="SOJA",
            hub_id="sorriso_mt",
            port_id="STS",
            target_value=130.0,
            current_value=124.8,
            is_triggered=False,
            notification_channel="IN_APP",
            notes="Gatilho de originação para disparar ofertas de compra aos cooperados.",
        ),
        MarketAlert(
            organization_id=org_id,
            user_id=user_id,
            name="Dólar Comercial PTAX Acima de R$ 5,80",
            alert_type="FX_CHANGE_PCT",
            commodity="SOJA",
            target_value=5.80,
            current_value=5.65,
            is_triggered=False,
            notification_channel="IN_APP",
            notes="Alerta para travamento cambial via NDF / trava de balcão.",
        ),
        MarketAlert(
            organization_id=org_id,
            user_id=user_id,
            name="CBOT Soja Acima de 1.080 ¢/bu",
            alert_type="CBOT_ABOVE",
            commodity="SOJA",
            target_value=1080.0,
            current_value=1045.5,
            is_triggered=False,
            notification_channel="IN_APP",
            notes="Rompimento técnico de média móvel na Bolsa de Chicago.",
        ),
        MarketAlert(
            organization_id=org_id,
            user_id=user_id,
            name="Oportunidade Esmagadora MT > R$ 127,00/sc",
            alert_type="PARITY_ABOVE",
            commodity="SOJA",
            hub_id="rondonopolis_mt",
            port_id="IND_ROO_BUNGE",
            target_value=127.0,
            current_value=128.5,
            is_triggered=True,
            triggered_at=now,
            trigger_count=1,
            notification_channel="IN_APP",
            notes="Indústria em Rondonópolis pagando acima da paridade de exportação líquida!",
        ),
    ]
    for a in alerts:
        db.add(a)

    db.commit()
    return {
        "freight_contracts_count": len(contracts),
        "scenarios_count": len(scenarios),
        "trade_tickets_count": len(tickets),
        "market_alerts_count": len(alerts),
    }


@app.post("/api/organizations")
def create_organization(
    payload: OrganizationCreateInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cria uma nova organização (empresa) e associa o usuário atual como OWNER.
    Gera automaticamente o perfil de custos padrão para a organização.
    Opcionalmente pré-popula dados demonstrativos (fretes, cenários, boletas e alertas).
    """
    slug = payload.slug
    if not slug:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-")
        if not slug:
            slug = f"org-{current_user.id}"

    # Evita duplicação de slug
    existing = db.query(Organization).filter(Organization.slug == slug).first()
    if existing:
        slug = f"{slug}-{int(datetime.now(timezone.utc).timestamp())}"

    org = Organization(name=payload.name, slug=slug, is_active=True)
    db.add(org)
    db.commit()
    db.refresh(org)

    membership = Membership(
        user_id=current_user.id,
        organization_id=org.id,
        role=MembershipRole.OWNER.value,
        is_active=True,
    )
    db.add(membership)

    default_profile = CostProfile(
        organization_id=org.id,
        name="Perfil Padrão Trading",
        brokerage_margin_usd_ton=2.0,
        brokerage_fee_brl_bag=0.0,
        brokerage_payer="NONE",
        default_funrural_pct=1.5,
        default_shrinkage_loss_pct=0.3,
        is_active=True,
    )
    db.add(default_profile)
    db.commit()
    db.refresh(membership)

    demo_summary = None
    if payload.seed_demo_data:
        demo_summary = seed_organization_demo_data(db=db, org_id=org.id, user_id=current_user.id)

    return {
        "status": "created",
        "organization": org.to_dict(),
        "membership": membership.to_dict(),
        "demo_seeded": bool(payload.seed_demo_data),
        "demo_summary": demo_summary,
    }


@app.get("/api/organizations/{org_id}/cost-profiles")
def list_organization_cost_profiles(
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Lista todos os perfis privados de custo da organização do usuário (Ticket F10).
    Acesso restrito a membros ativos com papel READER, ANALYST ou OWNER na organização.
    """
    profiles = (
        db.query(CostProfile)
        .filter(CostProfile.organization_id == org_id, CostProfile.is_active == True)
        .all()
    )
    return [p.to_dict() for p in profiles]


@app.post("/api/organizations/{org_id}/cost-profiles")
def create_organization_cost_profile(
    org_id: int,
    payload: CostProfileCreateInput,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Cria um perfil privado de custos e margens para a organização (Ticket F10).
    Acesso restrito a membros com papel ANALYST ou OWNER.
    """
    profile = CostProfile(
        organization_id=org_id,
        name=payload.name,
        brokerage_margin_usd_ton=payload.brokerage_margin_usd_ton,
        brokerage_fee_brl_bag=payload.brokerage_fee_brl_bag,
        brokerage_payer=payload.brokerage_payer,
        default_funrural_pct=payload.default_funrural_pct,
        default_shrinkage_loss_pct=payload.default_shrinkage_loss_pct,
        is_active=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile.to_dict()


@app.get("/api/organizations/{org_id}/cost-profiles/{profile_id}")
def get_organization_cost_profile(
    org_id: int,
    profile_id: int,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Retorna os detalhes de um perfil de custo privado da organização (Ticket F10).
    """
    profile = (
        db.query(CostProfile)
        .filter(CostProfile.id == profile_id, CostProfile.organization_id == org_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Cost profile not found in this organization")
    return profile.to_dict()


@app.put("/api/organizations/{org_id}/cost-profiles/{profile_id}")
def update_organization_cost_profile(
    org_id: int,
    profile_id: int,
    payload: CostProfileUpdateInput,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Atualiza parâmetros de um perfil privado de custos da organização (Ticket F10).
    """
    profile = (
        db.query(CostProfile)
        .filter(CostProfile.id == profile_id, CostProfile.organization_id == org_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Cost profile not found in this organization")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if val is not None:
            setattr(profile, field, val)

    db.commit()
    db.refresh(profile)
    return profile.to_dict()


# ==============================================================================
# Contratos Privados de Frete da Empresa / Trading (Item 3)
# ==============================================================================

@app.get("/api/organizations/{org_id}/freight-contracts")
def list_organization_freight_contracts(
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Lista todos os contratos privados de frete da organização.
    """
    contracts = (
        db.query(CompanyFreightContract)
        .filter(CompanyFreightContract.organization_id == org_id)
        .order_by(CompanyFreightContract.updated_at.desc())
        .all()
    )
    return [c.to_dict() for c in contracts]


@app.post("/api/organizations/{org_id}/freight-contracts")
def create_organization_freight_contract(
    org_id: int,
    payload: CompanyFreightContractCreateInput,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Cadastra ou atualiza um contrato privado de frete para uma rota na organização.
    """
    orig_key = payload.origin_id.lower()
    dest_key = payload.destination_id.upper()

    contract = CompanyFreightContract(
        organization_id=org_id,
        origin_id=orig_key,
        destination_id=dest_key,
        carrier_name=payload.carrier_name,
        contract_code=payload.contract_code,
        freight_brl_ton=payload.freight_brl_ton,
        volume_contracted_tons=payload.volume_contracted_tons,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        is_active=payload.is_active,
        notes=payload.notes,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract.to_dict()


@app.post("/api/organizations/{org_id}/freight-contracts/batch")
def batch_upload_organization_freight_contracts(
    org_id: int,
    payload: CompanyFreightContractBatchInput,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Importação em lote de contratos privados de frete para a organização.
    """
    created = []
    for item in payload.contracts:
        c = CompanyFreightContract(
            organization_id=org_id,
            origin_id=item.origin_id.lower(),
            destination_id=item.destination_id.upper(),
            carrier_name=item.carrier_name,
            contract_code=item.contract_code,
            freight_brl_ton=item.freight_brl_ton,
            volume_contracted_tons=item.volume_contracted_tons,
            valid_from=item.valid_from,
            valid_until=item.valid_until,
            is_active=item.is_active,
            notes=item.notes,
        )
        db.add(c)
        created.append(c)

    db.commit()
    for c in created:
        db.refresh(c)
    return [c.to_dict() for c in created]


@app.delete("/api/organizations/{org_id}/freight-contracts/{contract_id}")
def delete_organization_freight_contract(
    org_id: int,
    contract_id: int,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Remove um contrato privado de frete da organização.
    """
    contract = (
        db.query(CompanyFreightContract)
        .filter(CompanyFreightContract.id == contract_id, CompanyFreightContract.organization_id == org_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Freight contract not found in this organization")

    db.delete(contract)
    db.commit()
    return {"status": "deleted", "message": "Freight contract deleted successfully", "id": contract_id}


# ==============================================================================
# Boletas Formais de Negociação / Compra de Grãos (Trade Tickets)
# ==============================================================================

@app.get("/api/organizations/{org_id}/trade-tickets")
def list_organization_trade_tickets(
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Lista todas as boletas formais de compra e negociação emitidas pela organização.
    Permitido para READER, ANALYST e OWNER.
    """
    tickets = (
        db.query(TradeTicket)
        .filter(TradeTicket.organization_id == org_id)
        .order_by(TradeTicket.created_at.desc())
        .all()
    )
    return [t.to_dict() for t in tickets]


@app.post("/api/organizations/{org_id}/trade-tickets", status_code=201)
def create_organization_trade_ticket(
    org_id: int,
    payload: TradeTicketCreateInput,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Emite e registra uma nova boleta formal de compra de grãos (Trade Ticket)
    com amarração a cálculo auditado DECISION_READY e ID de linhagem W3C PROV.
    """
    now = datetime.now(timezone.utc)
    ticket_seq = uuid.uuid4().hex[:6].upper()
    ticket_num = f"BOL-{now.strftime('%Y%m%d')}-{ticket_seq}"
    
    qty_tons = round(payload.quantity_bags * 0.06, 2)
    total_brl = round(payload.quantity_bags * payload.price_per_bag_brl, 2)

    ticket = TradeTicket(
        ticket_number=ticket_num,
        organization_id=org_id,
        user_id=membership.user_id,
        commodity=payload.commodity.upper(),
        crop_year=payload.crop_year,
        seller_name=payload.seller_name.strip(),
        seller_document=payload.seller_document.strip() if payload.seller_document else None,
        seller_farm=payload.seller_farm.strip() if payload.seller_farm else None,
        location_hub_id=payload.location_hub_id,
        destination_port_id=payload.destination_port_id,
        quantity_bags=payload.quantity_bags,
        quantity_tons=qty_tons,
        price_per_bag_brl=payload.price_per_bag_brl,
        total_amount_brl=total_brl,
        payment_terms=payload.payment_terms,
        delivery_period=payload.delivery_period,
        quality_specs=payload.quality_specs,
        parity_run_id=payload.parity_run_id,
        cbot_reference=payload.cbot_reference,
        fx_reference=payload.fx_reference,
        freight_reference=payload.freight_reference,
        antt_compliant=payload.antt_compliant,
        decision_ready=True,
        status="CONFIRMED",
        notes=payload.notes,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket.to_dict()


@app.get("/api/organizations/{org_id}/trade-tickets/{ticket_id}")
def get_organization_trade_ticket(
    org_id: int,
    ticket_id: int,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Obtém os detalhes de uma boleta formal específica.
    """
    ticket = (
        db.query(TradeTicket)
        .filter(TradeTicket.id == ticket_id, TradeTicket.organization_id == org_id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Trade ticket not found in this organization")
    return ticket.to_dict()


@app.delete("/api/organizations/{org_id}/trade-tickets/{ticket_id}")
def delete_organization_trade_ticket(
    org_id: int,
    ticket_id: int,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Cancela/exclui uma boleta de negociação da organização.
    """
    ticket = (
        db.query(TradeTicket)
        .filter(TradeTicket.id == ticket_id, TradeTicket.organization_id == org_id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Trade ticket not found in this organization")
    
    db.delete(ticket)
    db.commit()
    return {"status": "deleted", "message": "Trade ticket deleted successfully", "id": ticket_id}


# ==============================================================================
# Gestão de Membros e Convites Organizacionais (Ticket F11)
# ==============================================================================

@app.get("/api/organizations/{org_id}/members")
def list_organization_members(
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Lista todos os membros ativos da organização com seus papéis RBAC (Ticket F11).
    Acesso permitido a READER, ANALYST e OWNER.
    """
    members = (
        db.query(Membership)
        .filter(Membership.organization_id == org_id, Membership.is_active == True)
        .all()
    )
    result = []
    for m in members:
        u = m.user
        result.append({
            "membership_id": m.id,
            "user_id": u.id,
            "email": u.email,
            "name": u.name,
            "role": m.role,
            "joined_at": m.created_at.isoformat() if m.created_at else None,
        })
    return result


@app.delete("/api/organizations/{org_id}/members/{user_id}")
def remove_organization_member(
    org_id: int,
    user_id: int,
    membership: Membership = Depends(require_role(MembershipRole.OWNER)),
    db: Session = Depends(get_db),
):
    """
    Remove ou desativa um membro da organização (Ticket F11).
    Apenas OWNER pode remover membros. Impede remover o único OWNER da organização.
    """
    target_membership = (
        db.query(Membership)
        .filter(
            Membership.organization_id == org_id,
            Membership.user_id == user_id,
            Membership.is_active == True,
        )
        .first()
    )
    if not target_membership:
        raise HTTPException(status_code=404, detail="Member not found in this organization")

    if target_membership.role == MembershipRole.OWNER.value:
        active_owners = (
            db.query(Membership)
            .filter(
                Membership.organization_id == org_id,
                Membership.role == MembershipRole.OWNER.value,
                Membership.is_active == True,
            )
            .count()
        )
        if active_owners <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the sole OWNER of the organization"
            )

    target_membership.is_active = False
    db.commit()
    return {"status": "success", "message": f"User {user_id} removed from organization {org_id}"}


@app.post("/api/organizations/{org_id}/invitations")
def create_invitation(
    org_id: int,
    payload: InvitationCreateInput,
    membership: Membership = Depends(require_role(MembershipRole.OWNER)),
    db: Session = Depends(get_db),
):
    """
    Gera um convite criptográfico de uso único com validade de 48 horas (Ticket F11).
    Apenas OWNER pode emitir convites.
    """
    import secrets
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    role_val = payload.role.upper()
    if role_val not in [r.value for r in MembershipRole]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{payload.role}'. Must be one of {[r.value for r in MembershipRole]}"
        )

    invitation = Invitation(
        organization_id=org_id,
        email=payload.email,
        role=role_val,
        token=token,
        invited_by_user_id=membership.user_id,
        expires_at=expires_at,
        is_accepted=False,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation.to_dict()


@app.get("/api/organizations/{org_id}/invitations")
def list_pending_invitations(
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.OWNER)),
    db: Session = Depends(get_db),
):
    """
    Lista convites pendentes e não expirados da organização (Ticket F11).
    Apenas OWNER pode visualizar convites.
    """
    now = datetime.now(timezone.utc)
    invitations = (
        db.query(Invitation)
        .filter(
            Invitation.organization_id == org_id,
            Invitation.is_accepted == False,
            Invitation.expires_at > now,
        )
        .all()
    )
    return [inv.to_dict() for inv in invitations]


@app.post("/api/invitations/{token}/accept")
def accept_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Aceita um convite ativo e vincula o usuário autenticado à organização (Ticket F11).
    """
    invitation = db.query(Invitation).filter(Invitation.token == token).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.is_accepted:
        raise HTTPException(status_code=400, detail="Invitation has already been accepted")

    now = datetime.now(timezone.utc)
    exp = invitation.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if exp < now:
        raise HTTPException(status_code=400, detail="Invitation has expired (48-hour limit exceeded)")

    existing = (
        db.query(Membership)
        .filter(
            Membership.user_id == current_user.id,
            Membership.organization_id == invitation.organization_id,
        )
        .first()
    )
    if existing:
        existing.role = invitation.role
        existing.is_active = True
    else:
        new_membership = Membership(
            user_id=current_user.id,
            organization_id=invitation.organization_id,
            role=invitation.role,
            is_active=True,
        )
        db.add(new_membership)

    invitation.is_accepted = True
    invitation.accepted_at = now
    db.commit()

    org_name = invitation.organization.name if invitation.organization else "Organization"
    return {
        "status": "success",
        "message": f"Successfully joined {org_name} as {invitation.role}",
        "organization_id": invitation.organization_id,
        "role": invitation.role,
    }


# ==============================================================================
# Cenários Salvos por Organização (Ticket U03)
# ==============================================================================

@app.post("/api/organizations/{org_id}/scenarios")
def save_organization_scenario(
    org_id: int,
    payload: SavedScenarioCreateInput,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Salva uma simulação de paridade de exportação personalizada na organização (Ticket U03).
    Acesso restrito a membros com papel ANALYST ou OWNER.
    """
    scenario = SavedScenario(
        organization_id=org_id,
        user_id=current_user.id,
        name=payload.name,
        commodity=payload.commodity.upper(),
        hub_id=payload.hub_id,
        port_id=payload.port_id,
        cbot_price_cents=payload.cbot_price_cents,
        port_premium_cents=payload.port_premium_cents,
        usd_brl_fx=payload.usd_brl_fx,
        freight_cost_brl_ton=payload.freight_cost_brl_ton,
        elevation_cost_usd_ton=payload.elevation_cost_usd_ton,
        demurrage_risk_usd_ton=payload.demurrage_risk_usd_ton,
        other_port_costs_usd_ton=payload.other_port_costs_usd_ton,
        tax_fund_brl_bag=payload.tax_fund_brl_bag,
        net_parity_brl_bag=payload.net_parity_brl_bag,
        net_parity_brl_ton=payload.net_parity_brl_ton,
        fob_usd_ton=payload.fob_usd_ton,
        notes=payload.notes,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario.to_dict()


@app.get("/api/organizations/{org_id}/scenarios")
def list_organization_scenarios(
    org_id: int,
    limit: int = 20,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Lista todos os cenários salvos de paridade da organização (Ticket U03).
    """
    scenarios = (
        db.query(SavedScenario)
        .filter(SavedScenario.organization_id == org_id)
        .order_by(SavedScenario.id.desc())
        .limit(limit)
        .all()
    )
    return [s.to_dict() for s in scenarios]


@app.delete("/api/organizations/{org_id}/scenarios/{scenario_id}")
def delete_organization_scenario(
    org_id: int,
    scenario_id: int,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Remove um cenário salvo da organização.
    """
    scen = (
        db.query(SavedScenario)
        .filter(SavedScenario.id == scenario_id, SavedScenario.organization_id == org_id)
        .first()
    )
    if not scen:
        raise HTTPException(status_code=404, detail="Cenário não encontrado")
    db.delete(scen)
    db.commit()
    return {"status": "deleted", "scenario_id": scenario_id}


# ==============================================================================
# Alertas de Mercado e Metas de Preço - Watchlist do Trader (Atividade 1)
# ==============================================================================

@app.get("/api/organizations/{org_id}/alerts")
def list_organization_alerts(
    org_id: int,
    active_only: bool = False,
    triggered_only: bool = False,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Lista todos os alertas de mercado e metas de preço cadastrados na watchlist da organização.
    """
    query = db.query(MarketAlert).filter(MarketAlert.organization_id == org_id)
    if active_only:
        query = query.filter(MarketAlert.is_active == True)
    if triggered_only:
        query = query.filter(MarketAlert.is_triggered == True)
    
    alerts = query.order_by(MarketAlert.is_triggered.desc(), MarketAlert.id.desc()).all()
    return [a.to_dict() for a in alerts]


@app.post("/api/organizations/{org_id}/alerts", status_code=201)
def create_organization_alert(
    org_id: int,
    payload: MarketAlertCreateInput,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Cria uma nova regra ou meta de preço na watchlist de monitoramento de mercado.
    """
    alert = MarketAlert(
        organization_id=org_id,
        user_id=membership.user_id,
        name=payload.name.strip(),
        alert_type=payload.alert_type.strip().upper(),
        commodity=payload.commodity.strip().upper(),
        hub_id=payload.hub_id,
        port_id=payload.port_id,
        target_value=payload.target_value,
        notification_channel=payload.notification_channel,
        notes=payload.notes,
        is_active=True,
        is_triggered=False,
        trigger_count=0,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert.to_dict()


@app.put("/api/organizations/{org_id}/alerts/{alert_id}")
def update_organization_alert(
    alert_id: int,
    payload: MarketAlertUpdateInput,
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Atualiza meta de preço, status ativo/inativo ou notas de um alerta da watchlist.
    """
    alert = (
        db.query(MarketAlert)
        .filter(MarketAlert.id == alert_id, MarketAlert.organization_id == org_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta de mercado não encontrado")

    if payload.name is not None:
        alert.name = payload.name.strip()
    if payload.target_value is not None:
        alert.target_value = payload.target_value
    if payload.is_active is not None:
        alert.is_active = payload.is_active
    if payload.notes is not None:
        alert.notes = payload.notes

    alert.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert.to_dict()


@app.delete("/api/organizations/{org_id}/alerts/{alert_id}")
def delete_organization_alert(
    alert_id: int,
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Remove uma regra de alerta da organização.
    """
    alert = (
        db.query(MarketAlert)
        .filter(MarketAlert.id == alert_id, MarketAlert.organization_id == org_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta de mercado não encontrado")

    db.delete(alert)
    db.commit()
    return {"status": "deleted", "id": alert_id}


@app.post("/api/organizations/{org_id}/alerts/{alert_id}/reset")
def reset_organization_alert(
    alert_id: int,
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.ANALYST)),
    db: Session = Depends(get_db),
):
    """
    Reseta o status disparado (is_triggered) do alerta para permitir novo disparo.
    """
    alert = (
        db.query(MarketAlert)
        .filter(MarketAlert.id == alert_id, MarketAlert.organization_id == org_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta de mercado não encontrado")

    alert.is_triggered = False
    alert.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert.to_dict()


@app.post("/api/organizations/{org_id}/alerts/evaluate")
def evaluate_organization_alerts(
    org_id: int,
    payload: MarketAlertEvaluateInput,
    membership: Membership = Depends(require_role(MembershipRole.READER)),
    db: Session = Depends(get_db),
):
    """
    Avalia em tempo real as metas e regras da watchlist contra parâmetros simulados ou cotações ativas.
    Dispara os alertas cujas condições foram atingidas e atualiza o histórico de auditoria.
    """
    alerts = (
        db.query(MarketAlert)
        .filter(MarketAlert.organization_id == org_id, MarketAlert.is_active == True)
        .all()
    )

    now = datetime.now(timezone.utc)
    triggered_now = []

    for alert in alerts:
        # Verifica se o alerta é aplicável à commodity
        if payload.commodity and alert.commodity and alert.commodity.upper() != payload.commodity.upper():
            continue

        # Verifica praça / destino se especificados no alerta
        if alert.hub_id and payload.hub_id and alert.hub_id != payload.hub_id:
            continue
        if alert.port_id and payload.port_id and alert.port_id != payload.port_id:
            continue

        candidate_value: Optional[float] = None
        should_trigger = False

        if alert.alert_type == "PARITY_ABOVE":
            if payload.parity_brl_bag is not None:
                candidate_value = payload.parity_brl_bag
                should_trigger = candidate_value >= alert.target_value
        elif alert.alert_type == "PARITY_BELOW":
            if payload.parity_brl_bag is not None:
                candidate_value = payload.parity_brl_bag
                should_trigger = candidate_value <= alert.target_value
        elif alert.alert_type == "CBOT_ABOVE":
            if payload.cbot_cents is not None:
                candidate_value = payload.cbot_cents
                should_trigger = candidate_value >= alert.target_value
        elif alert.alert_type == "CBOT_BELOW":
            if payload.cbot_cents is not None:
                candidate_value = payload.cbot_cents
                should_trigger = candidate_value <= alert.target_value
        elif alert.alert_type in ("FX_CHANGE_PCT", "FX_ABOVE"):
            if payload.fx_rate is not None:
                candidate_value = payload.fx_rate
                should_trigger = candidate_value >= alert.target_value
        elif alert.alert_type == "FX_BELOW":
            if payload.fx_rate is not None:
                candidate_value = payload.fx_rate
                should_trigger = candidate_value <= alert.target_value
        elif alert.alert_type == "SPREAD_ABOVE":
            if payload.spread_brl_bag is not None:
                candidate_value = payload.spread_brl_bag
                should_trigger = candidate_value >= alert.target_value

        if candidate_value is not None:
            alert.current_value = candidate_value

        if should_trigger:
            if not alert.is_triggered:
                alert.is_triggered = True
                alert.triggered_at = now
                alert.trigger_count += 1
                triggered_now.append(alert.to_dict())

    db.commit()
    all_active = [a.to_dict() for a in alerts]
    total_triggered = sum(1 for a in alerts if a.is_triggered)

    return {
        "status": "evaluated",
        "total_active_alerts": len(alerts),
        "total_triggered": total_triggered,
        "newly_triggered": triggered_now,
        "alerts": all_active,
    }


# ==============================================================================
# Onboarding Demo Seed (Atividade 3)
# ==============================================================================

@app.post("/api/organizations/{org_id}/seed-demo")
def seed_organization_demo_endpoint(
    org_id: int,
    membership: Membership = Depends(require_role(MembershipRole.OWNER)),
    db: Session = Depends(get_db),
):
    """
    Popula sob demanda o portfólio completo de dados de demonstração (Trial 14 dias):
    contratos de frete, cenários, boletas de compra e watchlist de alertas.
    """
    summary = seed_organization_demo_data(db=db, org_id=org_id, user_id=membership.user_id)
    return {"status": "seeded", "summary": summary}


# ==============================================================================
# Comparador de Propostas / Bids (Ticket U04)
# ==============================================================================

@app.post("/api/proposals/compare")
def compare_proposals(payload: ProposalComparisonRequest):
    """
    Compara de 2 a 5 propostas/bids de compradores ou rotas portuárias lado a lado (Ticket U04).
    Calcula a paridade líquida na fazenda para cada proposta e elege a proposta mais rentável.
    """
    results = []

    for p in payload.proposals:
        comm_type = CommodityType.SOJA if p.commodity.upper() == "SOJA" else CommodityType.MILHO
        inp = ParityCalculationInput(
            commodity=comm_type,
            cbot_price_cents=p.cbot_cents,
            port_premium_cents=p.premium_cents,
            usd_brl_fx=p.fx_rate,
            hub_id=p.hub_id,
            port_id=p.port_id,
            freight_brl_ton=p.freight_brl_ton,
            elevation_usd_ton=p.elevation_usd_ton,
            demurrage_usd_ton=p.demurrage_usd_ton or 0.0,
            other_port_costs_brl_ton=(p.other_port_usd_ton * p.fx_rate) if p.other_port_usd_ton is not None else None,
            state_tax_fund_brl_bag=p.tax_fund_brl_bag,
        )
        calc = ExportParityEngine.calculate(inp)
        total_revenue_brl = calc.net_parity_price_brl_bag * p.volume_bags
        results.append({
            "name": p.name,
            "commodity": p.commodity.upper(),
            "hub_id": p.hub_id,
            "port_id": p.port_id,
            "volume_bags": p.volume_bags,
            "volume_tons": round(p.volume_bags / 16.6667, 1),
            "fob_usd_ton": calc.fob_usd_ton,
            "fob_brl_ton": calc.fob_brl_ton,
            "fob_brl_bag": calc.fob_brl_bag,
            "road_freight_brl_ton": p.freight_brl_ton,
            "road_freight_brl_bag": calc.cost_breakdown.freight_brl_bag,
            "tax_fund_brl_bag": calc.cost_breakdown.state_fund_brl_bag,
            "net_price_brl_bag": calc.net_parity_price_brl_bag,
            "net_price_brl_ton": calc.net_parity_price_brl_ton,
            "total_lot_revenue_brl": round(total_revenue_brl, 2),
        })

    results.sort(key=lambda x: x["net_price_brl_bag"], reverse=True)
    best_bid = results[0]

    for r in results:
        spread_bag = round(r["net_price_brl_bag"] - best_bid["net_price_brl_bag"], 2)
        spread_lot = round(r["total_lot_revenue_brl"] - best_bid["total_lot_revenue_brl"], 2)
        r["spread_vs_best_brl_bag"] = spread_bag
        r["spread_vs_best_lot_brl"] = spread_lot
        r["is_best"] = (r["name"] == best_bid["name"])

    return {
        "best_proposal": best_bid["name"],
        "best_price_brl_bag": best_bid["net_price_brl_bag"],
        "max_advantage_lot_brl": round(best_bid["total_lot_revenue_brl"] - results[-1]["total_lot_revenue_brl"], 2),
        "proposals": results,
    }


# ==============================================================================
# Telemetria e Saúde de Fontes de Dados (Ticket F12)
# ==============================================================================

@app.get("/api/admin/sources/health")
def get_sources_health(
    operator: User = Depends(require_platform_operator),
    db: Session = Depends(get_db),
):
    """
    Retorna o status operacional, integridade e telemetria de cada fonte de dados (Ticket F12).
    Acesso restrito ao operador da plataforma.
    """
    sources_to_check = ["CBOT", "BACEN_PTAX", "B3", "BACEN_MACRO", "CEPEA"]
    health_report = {}

    for src in sources_to_check:
        latest_quote = (
            db.query(MarketQuote)
            .filter(MarketQuote.source.like(f"%{src}%"))
            .order_by(MarketQuote.observed_at.desc(), MarketQuote.id.desc())
            .first()
        )
        latest_log = (
            db.query(ExtractionLog)
            .filter(ExtractionLog.sources_contacted.like(f"%{src}%"))
            .order_by(ExtractionLog.id.desc())
            .first()
        )
        health_report[src] = {
            "source": src,
            "status": "OPERATIONAL" if (latest_quote or (latest_log and latest_log.status == "SUCCESS")) else "UNVERIFIED",
            "last_observed_at": latest_quote.observed_at.isoformat() if latest_quote and latest_quote.observed_at else None,
            "last_ingested_at": latest_quote.ingested_at.isoformat() if latest_quote and latest_quote.ingested_at else None,
            "last_log_status": latest_log.status if latest_log else None,
            "last_log_finished_at": latest_log.finished_at.isoformat() if latest_log and latest_log.finished_at else None,
            "data_kind": latest_quote.data_kind if latest_quote else "UNKNOWN",
            "freshness": latest_quote.freshness if latest_quote else "UNKNOWN",
        }

    return {
        "status": "HEALTHY",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "sources": health_report,
    }

