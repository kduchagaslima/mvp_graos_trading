"""
FastAPI Backend para o MVP de Market Data e Trading de Grãos.
Expõe endpoints REST para cálculo de paridade, custo de carrego, simulação de estresse e cotações.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional

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

app = FastAPI(
    title="Grain Trading Market Data & Projection API",
    description="Motor de formação de preço de grãos, paridade de exportação FAS/FOB, carrego e simulação de risco.",
    version="1.0.0",
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


@app.get("/api/market-data/snapshot")
def get_market_snapshot():
    return market_service.get_snapshot()


@app.post("/api/market-data/fx/refresh")
def refresh_live_fx():
    rate = market_service.fetch_live_usd_brl()
    return {"status": "success", "usd_brl_fx": rate}


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
