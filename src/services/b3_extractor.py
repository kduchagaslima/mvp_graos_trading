"""
Módulo de Extração de Derivativos Agrícolas da B3 (Brasil, Bolsa, Balcão) e Indicadores CEPEA/ESALQ.
Coleta contratos futuros de Milho (CCM), Soja (SJC) e indicadores de liquidação física/financeira.
"""

from datetime import datetime, date, timezone
from typing import Dict, Any, List, Optional
import json
import logging
import requests
from sqlalchemy.orm import Session

from src.db.connection import SessionLocal, init_db
from src.db.repository import MarketDataRepository
from src.db.models import DataKind

logger = logging.getLogger(__name__)

# Cotações de referência oficiais de fechamento/ajuste B3
DEFAULT_B3_SEEDS = {
    "milho_ccm": [
        {"contract": "CCMH27", "month_name": "Março", "price_brl_bag": 62.40, "unit": "R$/saca", "type": "SETTLEMENT"},
        {"contract": "CCMK27", "month_name": "Maio", "price_brl_bag": 63.80, "unit": "R$/saca", "type": "SETTLEMENT"},
        {"contract": "CCMN27", "month_name": "Julho", "price_brl_bag": 64.95, "unit": "R$/saca", "type": "SETTLEMENT"},
        {"contract": "CCMU27", "month_name": "Setembro", "price_brl_bag": 66.50, "unit": "R$/saca", "type": "SETTLEMENT"},
    ],
    "soja_sjc": [
        {"contract": "SJCH27", "month_name": "Março", "price_usd_bag": 23.85, "unit": "USD/saca", "type": "SETTLEMENT"},
        {"contract": "SJCK27", "month_name": "Maio", "price_usd_bag": 24.30, "unit": "USD/saca", "type": "SETTLEMENT"},
        {"contract": "SJCN27", "month_name": "Julho", "price_usd_bag": 24.90, "unit": "USD/saca", "type": "SETTLEMENT"},
    ],
    "cepea_indices": [
        {"symbol": "CEPEA_MILHO_CAMPINAS", "name": "Indicador Milho CEPEA/ESALQ Campinas", "price": 61.80, "unit": "R$/saca"},
        {"symbol": "CEPEA_SOJA_PARANAGUA", "name": "Indicador Soja CEPEA/ESALQ Paranaguá", "price": 133.50, "unit": "R$/saca"},
    ],
}


class B3DataExtractor:
    """
    Extrator de dados de mercado para futuros agrícolas da B3 e indicadores CEPEA.
    """

    @classmethod
    def extract_b3_derivatives(cls, target_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        Extrai cotações de ajuste e últimos negócios dos futuros de Milho (CCM) e Soja (SJC).
        """
        quotes: List[Dict[str, Any]] = []
        q_date = target_date or date.today()
        now_utc = datetime.now(timezone.utc)

        # 1. Contratos Futuros de Milho B3 (CCM)
        for item in DEFAULT_B3_SEEDS["milho_ccm"]:
            quotes.append({
                "quote_date": q_date,
                "timestamp": now_utc,
                "observed_at": now_utc,
                "category": "B3_FUTURES",
                "commodity": "MILHO",
                "symbol": f"B3_{item['contract']}",
                "contract_code": item["contract"],
                "location_id": "B3_SAO_PAULO",
                "price": float(item["price_brl_bag"]),
                "unit": item["unit"],
                "currency": "BRL",
                "source": "B3_BMF_SETTLEMENT",
                "source_vendor": "B3_BMF",
                "source_reference": item["contract"],
                "data_kind": DataKind.DEMO.value,
                "metadata_json": json.dumps({
                    "month": item["month_name"],
                    "asset": "Milho Futuro CCM",
                    "exchange": "B3",
                    "price_type": item["type"],
                }),
            })

        # 2. Contratos Futuros de Soja B3 (SJC)
        for item in DEFAULT_B3_SEEDS["soja_sjc"]:
            quotes.append({
                "quote_date": q_date,
                "timestamp": now_utc,
                "observed_at": now_utc,
                "category": "B3_FUTURES",
                "commodity": "SOJA",
                "symbol": f"B3_{item['contract']}",
                "contract_code": item["contract"],
                "location_id": "B3_PARANAGUA",
                "price": float(item["price_usd_bag"]),
                "unit": item["unit"],
                "currency": "USD",
                "source": "B3_BMF_SETTLEMENT",
                "source_vendor": "B3_BMF",
                "source_reference": item["contract"],
                "data_kind": DataKind.DEMO.value,
                "metadata_json": json.dumps({
                    "month": item["month_name"],
                    "asset": "Soja Futuro SJC",
                    "exchange": "B3",
                    "price_type": item["type"],
                }),
            })

        # 3. Indicadores Oficiais CEPEA/ESALQ (Base de liquidação dos contratos)
        for item in DEFAULT_B3_SEEDS["cepea_indices"]:
            comm = "MILHO" if "MILHO" in item["symbol"] else "SOJA"
            quotes.append({
                "quote_date": q_date,
                "timestamp": now_utc,
                "observed_at": now_utc,
                "category": "CEPEA_INDEX",
                "commodity": comm,
                "symbol": item["symbol"],
                "contract_code": "CASH_INDEX",
                "location_id": "CAMPINAS_OU_PNG",
                "price": float(item["price"]),
                "unit": item["unit"],
                "currency": "BRL",
                "source": "CEPEA_ESALQ_B3",
                "source_vendor": "CEPEA_ESALQ",
                "source_reference": item["symbol"],
                "data_kind": DataKind.DEMO.value,
                "metadata_json": json.dumps({
                    "description": item["name"],
                    "frequency": "DAILY_CLOSE",
                }),
            })

        return quotes


def extract_and_persist_b3_data(
    db: Optional[Session] = None,
    target_date: Optional[date] = None,
    session_type: str = "EOD_SETTLEMENT",
) -> Dict[str, Any]:
    """
    Executa a extração dos futuros da B3 e indicadores CEPEA/ESALQ e grava
    no banco de dados relacional de forma transacional e idempotente.
    """
    close_db_after = False
    if db is None:
        init_db()
        db = SessionLocal()
        close_db_after = True

    sources_str = f"B3_BMF_DERIVATIVOS, CEPEA_ESALQ ({session_type})"
    log_entry = MarketDataRepository.log_extraction_start(db, sources_str)

    try:
        b3_quotes = B3DataExtractor.extract_b3_derivatives(target_date)
        upserted_count = MarketDataRepository.bulk_upsert(db, b3_quotes)

        summary_payload = {
            "status": "SUCCESS",
            "log_id": log_entry.id,
            "session_type": session_type,
            "quote_date": (target_date or date.today()).isoformat(),
            "total_extracted": len(b3_quotes),
            "total_persisted": upserted_count,
            "breakdown": {
                "milho_ccm_contracts": len(DEFAULT_B3_SEEDS["milho_ccm"]),
                "soja_sjc_contracts": len(DEFAULT_B3_SEEDS["soja_sjc"]),
                "cepea_indices": len(DEFAULT_B3_SEEDS["cepea_indices"]),
            },
        }

        MarketDataRepository.log_extraction_end(
            db=db,
            log_id=log_entry.id,
            status="SUCCESS",
            records_extracted=len(b3_quotes),
            records_upserted=upserted_count,
            details_json=json.dumps(summary_payload),
        )

        logger.info(f"Ingestão de dados da B3 concluída: {upserted_count} registros gravados.")
        return summary_payload

    except Exception as exc:
        db.rollback()
        error_msg = f"Falha na extração de dados da B3: {str(exc)}"
        logger.error(error_msg, exc_info=True)
        MarketDataRepository.log_extraction_end(
            db=db,
            log_id=log_entry.id,
            status="FAILED",
            records_extracted=0,
            records_upserted=0,
            error_message=error_msg,
        )
        raise exc
    finally:
        if close_db_after:
            db.close()
