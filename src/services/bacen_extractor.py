"""
Módulo de Extração de Índices Macroeconômicos Oficiais do Banco Central do Brasil (BACEN SGS).
Coleta e persiste taxas de juros (CDI, Selic Meta) e índices de inflação (IPCA, IGP-M).
"""

from datetime import datetime, date, timezone
from typing import Dict, Any, List, Optional
import json
import logging
import urllib.request
from sqlalchemy.orm import Session

from src.db.connection import SessionLocal
from src.db.repository import MarketDataRepository
from src.db.models import DataKind

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


def _parse_sgs_date(date_str: str) -> Optional[datetime]:
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


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
        now_utc = datetime.now(timezone.utc)

        for key, conf in BACEN_SGS_SERIES.items():
            raw = cls.fetch_serie_value(conf["serie"])
            if raw and "valor" in raw:
                try:
                    val = float(raw["valor"])
                    ref_date = raw.get("data", date.today().strftime("%d/%m/%Y"))
                    observed_at = _parse_sgs_date(ref_date) or now_utc
                    data_kind = DataKind.OBSERVED.value
                    source = "BCB_SGS"
                    source_vendor = "BANCO_CENTRAL_DO_BRASIL"
                    source_ref = f"BACEN_SGS_{conf['serie']}"
                except (ValueError, TypeError):
                    val = conf["fallback"]
                    ref_date = date.today().strftime("%d/%m/%Y")
                    observed_at = now_utc
                    data_kind = DataKind.DEMO.value
                    source = "SEED_FALLBACK"
                    source_vendor = "SEED_BENCHMARK"
                    source_ref = f"FALLBACK_SGS_{conf['serie']}"
            else:
                val = conf["fallback"]
                ref_date = date.today().strftime("%d/%m/%Y")
                observed_at = now_utc
                data_kind = DataKind.DEMO.value
                source = "SEED_FALLBACK"
                source_vendor = "SEED_BENCHMARK"
                source_ref = f"FALLBACK_SGS_{conf['serie']}"

            results[key] = {
                "symbol": key,
                "name": conf["name"],
                "value": val,
                "unit": conf["unit"],
                "ref_date": ref_date,
                "observed_at": observed_at,
                "source": source,
                "source_vendor": source_vendor,
                "source_reference": source_ref,
                "data_kind": data_kind,
            }
        return results

    @classmethod
    def persist_macro_data(
        cls, db: Session, indicators: Dict[str, Any], session_type: str = "SCHEDULED"
    ) -> Dict[str, Any]:
        """
        Persiste os índices extraídos na tabela market_quotes de forma transacional e idempotente.
        """
        sources_str = f"api.bcb.gov.br (SGS) - BACEN_MACRO_{session_type}"
        log_entry = MarketDataRepository.log_extraction_start(db, sources_str)

        upserted_count = 0
        persisted_items = []
        today = date.today()
        now_utc = datetime.now(timezone.utc)

        try:
            for key, item in indicators.items():
                obs_dt = item.get("observed_at") or now_utc
                quote_dict = {
                    "quote_date": today,
                    "timestamp": now_utc,
                    "observed_at": obs_dt,
                    "category": "MACRO_INDEX",
                    "commodity": None,
                    "symbol": item["symbol"],
                    "contract_code": "INDEX",
                    "location_id": "BRASIL",
                    "price": float(item["value"]),
                    "unit": item["unit"],
                    "currency": "BRL",
                    "source": item["source"],
                    "source_vendor": item.get("source_vendor", "BANCO_CENTRAL_DO_BRASIL"),
                    "source_reference": item.get("source_reference"),
                    "data_kind": item.get("data_kind", DataKind.OBSERVED.value),
                    "metadata_json": json.dumps(
                        {"name": item["name"], "ref_date": item["ref_date"]}
                    ),
                }

                q = MarketDataRepository.upsert_quote(db=db, quote_dict=quote_dict)
                persisted_items.append(q.to_dict())
                upserted_count += 1

            db.commit()

            summary = {
                "status": "success",
                "total_indicators": len(indicators),
                "total_persisted": upserted_count,
                "timestamp": now_utc.isoformat(),
                "indicators": {
                    k: {sub_k: v for sub_k, v in val.items() if sub_k != "observed_at"}
                    for k, val in indicators.items()
                },
            }

            MarketDataRepository.log_extraction_end(
                db=db,
                log_id=log_entry.id,
                status="SUCCESS",
                records_extracted=len(indicators),
                records_upserted=upserted_count,
                details_json=json.dumps(summary),
            )

            return summary

        except Exception as e:
            db.rollback()
            MarketDataRepository.log_extraction_end(
                db=db,
                log_id=log_entry.id,
                status="FAILED",
                records_extracted=len(indicators),
                records_upserted=0,
                error_message=str(e),
            )
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
