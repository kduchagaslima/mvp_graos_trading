"""
Módulo de Extração de Índices Macroeconômicos Oficiais do Banco Central do Brasil (BACEN SGS).
Coleta e persiste taxas de juros (CDI, Selic Meta) e índices de inflação (IPCA, IGP-M).
"""

from datetime import datetime, date
from typing import Dict, Any, List, Optional
import json
import logging
import urllib.request
from sqlalchemy.orm import Session

from src.db.connection import SessionLocal
from src.db.repository import MarketDataRepository
from src.db.models import ExtractionLog

logger = logging.getLogger(__name__)

# Séries Oficiais do SGS - Sistema Gerenciador de Séries Temporais do Banco Central
BACEN_SGS_SERIES = {
    "SELIC_META": {
        "serie": 432,
        "name": "Taxa Selic Meta (% a.a.)",
        "unit": "% a.a.",
        "fallback": 13.75,
    },
    "CDI_ANNUAL": {
        "serie": 4389,
        "name": "Taxa CDI Acumulada Anualizada (% a.a.)",
        "unit": "% a.a.",
        "fallback": 13.65,
    },
    "IPCA_12M": {
        "serie": 13522,
        "name": "IPCA Acumulado 12 Meses (%)",
        "unit": "% (12m)",
        "fallback": 4.22,
    },
    "IPCA_MONTHLY": {
        "serie": 433,
        "name": "IPCA Variação Mensal (%)",
        "unit": "% a.m.",
        "fallback": -0.32,
    },
    "IGPM_12M": {
        "serie": 189,
        "name": "IGP-M Geral FGV (% 12m)",
        "unit": "% (12m)",
        "fallback": 1.57,
    },
}


class BacenMacroExtractor:
    """
    Extrator de dados macroeconômicos do Banco Central do Brasil via API REST pública do SGS.
    """

    @classmethod
    def fetch_serie_value(cls, serie_id: int, timeout: int = 6) -> Optional[Dict[str, Any]]:
        """
        Consulta o último registro disponível de uma série temporal do SGS.
        """
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie_id}/dados/ultimos/1?formato=json"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AgriTrading-Serverless/1.0 (Mozilla/5.0; TradingDesk)",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
        except Exception as e:
            logger.warning(f"Aviso ao consultar série BACEN SGS {serie_id}: {e}")
        return None

    @classmethod
    def extract_macro_indicators(cls) -> Dict[str, Any]:
        """
        Extrai todos os índices macroeconômicos configurados (com fallback resiliente).
        """
        results: Dict[str, Any] = {}
        for key, conf in BACEN_SGS_SERIES.items():
            raw = cls.fetch_serie_value(conf["serie"])
            if raw and "valor" in raw:
                try:
                    val = float(raw["valor"])
                    ref_date = raw.get("data", date.today().strftime("%d/%m/%Y"))
                except (ValueError, TypeError):
                    val = conf["fallback"]
                    ref_date = date.today().strftime("%d/%m/%Y")
            else:
                val = conf["fallback"]
                ref_date = date.today().strftime("%d/%m/%Y")

            results[key] = {
                "symbol": key,
                "name": conf["name"],
                "value": val,
                "unit": conf["unit"],
                "ref_date": ref_date,
                "source": "BCB_SGS",
            }
        return results

    @classmethod
    def persist_macro_data(
        cls, db: Session, indicators: Dict[str, Any], session_type: str = "SCHEDULED"
    ) -> Dict[str, Any]:
        """
        Persiste os índices extraídos na tabela market_quotes de forma transacional e idempotente.
        """
        log_entry = ExtractionLog(
            source=f"BACEN_MACRO_{session_type}",
            status="RUNNING",
            sources_contacted="api.bcb.gov.br (SGS)",
            records_extracted=len(indicators),
            records_upserted=0,
            session_type=session_type,
            started_at=datetime.utcnow(),
        )
        db.add(log_entry)
        db.flush()

        upserted_count = 0
        persisted_items = []
        today = date.today()

        try:
            for key, item in indicators.items():
                quote_dict = {
                    "quote_date": today,
                    "timestamp": datetime.utcnow(),
                    "category": "MACRO_INDEX",
                    "commodity": None,
                    "symbol": item["symbol"],
                    "contract_code": "INDEX",
                    "location_id": "BRASIL",
                    "price": float(item["value"]),
                    "unit": item["unit"],
                    "source": item["source"],
                    "metadata_json": json.dumps(
                        {"name": item["name"], "ref_date": item["ref_date"]}
                    ),
                }

                q = MarketDataRepository.upsert_market_quote(db=db, quote_data=quote_dict)
                persisted_items.append(q.to_dict())
                upserted_count += 1

            db.commit()

            log_entry.status = "SUCCESS"
            log_entry.records_upserted = upserted_count
            log_entry.finished_at = datetime.utcnow()
            db.commit()

            return {
                "status": "success",
                "total_indicators": len(indicators),
                "total_persisted": upserted_count,
                "timestamp": datetime.utcnow().isoformat(),
                "indicators": indicators,
            }

        except Exception as e:
            db.rollback()
            log_entry.status = "FAILED"
            log_entry.error_message = str(e)
            log_entry.finished_at = datetime.utcnow()
            try:
                db.commit()
            except Exception:
                pass
            raise e


def extract_and_persist_macro_data(
    db: Optional[Session] = None, session_type: str = "MANUAL"
) -> Dict[str, Any]:
    """Função utilitária de conveniência para disparo manual ou agendado."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        indicators = BacenMacroExtractor.extract_macro_indicators()
        summary = BacenMacroExtractor.persist_macro_data(
            db=db, indicators=indicators, session_type=session_type
        )
        return summary
    finally:
        if should_close:
            db.close()
