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
)
from src.domain.commodities import CommodityType, COMMODITY_SPECS
from src.domain.locations import ORIGINATION_HUBS, PORTS
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
def calculate_export_parity(payload: ParityCalculationInput):
    try:
        result = ExportParityEngine.calculate(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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


@app.post("/api/organizations")
def create_organization(
    payload: OrganizationCreateInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cria uma nova organização (empresa) e associa o usuário atual como OWNER.
    Gera automaticamente o perfil de custos padrão para a organização.
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

    return {
        "status": "created",
        "organization": org.to_dict(),
        "membership": membership.to_dict(),
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

