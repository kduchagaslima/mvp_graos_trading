"""
FastAPI Backend para o MVP de Market Data e Trading de Grãos.
Expõe endpoints REST para cálculo de paridade, custo de carrego, simulação de estresse,
extração e persistência de dados de mercado no banco relacional.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from src.db.connection import init_db, get_db
from src.db.repository import MarketDataRepository
from src.db.models import ExtractionLog, MarketQuote
from src.domain.commodities import CommodityType, COMMODITY_SPECS
from src.domain.locations import ORIGINATION_HUBS, PORTS
from src.domain.models import (
    ParityCalculationInput,
    ParityCalculationResult,
    CarryCalculationInput,
    CarryCalculationResult,
    ScenarioSimulationInput,
    ScenarioSimulationResult,
)
from src.engines.export_parity import ExportParityEngine
from src.engines.carry_cost import CarryCostEngine
from src.engines.stress_tester import StressTesterEngine
from src.services.market_data import market_service
from src.services.extractor import extract_and_persist_market_data
from src.services.b3_extractor import extract_and_persist_b3_data
from src.scheduler.runner import get_scheduler_status


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

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
def get_market_snapshot():
    return market_service.get_snapshot()


@app.post("/api/market-data/extract")
def trigger_market_data_extraction(db: Session = Depends(get_db)):
    """
    Executa a extração completa de Market Data (PTAX, CBOT, Prêmios, Físico e Frete)
    e persiste os dados de forma transacional e idempotente no banco de dados.
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
def get_extraction_logs(limit: int = 10, db: Session = Depends(get_db)):
    """Retorna os logs recentes de auditoria de extração de dados."""
    logs = db.query(ExtractionLog).order_by(ExtractionLog.id.desc()).limit(limit).all()
    return [l.to_dict() for l in logs]


@app.post("/api/market-data/fx/refresh")
def refresh_live_fx():
    rate = market_service.fetch_live_usd_brl()
    return {"status": "success", "usd_brl_fx": rate}


@app.post("/api/b3/extract")
def trigger_b3_extraction(session_type: str = "MANUAL", db: Session = Depends(get_db)):
    """
    Executa a extração dos futuros agrícolas da B3 (CCM Milho e SJC Soja)
    e indicadores CEPEA/ESALQ, persistindo de forma transacional no banco.
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
def get_scheduler_info():
    """Retorna o status atual do agendador e metadados das rotinas configuradas."""
    return get_scheduler_status()


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
):
    """
    Calcula a paridade de exportação simultaneamente para todas as praças de originação,
    permitindo comparar a atratividade regional de compra.
    """
    cbot = cbot_price_cents or market_service.get_cbot_price(commodity.value)
    premium = port_premium_cents or market_service.get_port_premium(port_id, commodity.value)
    fx = usd_brl_fx or market_service.get_fx_usd_brl()

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
            current_cash_price_brl_bag=cash_price,
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

