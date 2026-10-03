"""
Camada de Acesso a Dados (Repository / DAO) com queries otimizadas para consumo de Market Data,
suporte aos dois eixos de qualidade (data_kind e freshness) e precisão Decimal.
"""

from datetime import date, datetime, timezone
from typing import List, Dict, Any, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from src.db.models import MarketQuote, ParitySnapshot, ExtractionLog, DataKind, FreshnessStatus
from src.services.freshness import evaluate_freshness


class MarketDataRepository:
    """
    Operações de consulta e persistência otimizadas para Market Data de Grãos.
    """

    @classmethod
    def upsert_quote(cls, db: Session, quote_dict: Dict[str, Any]) -> MarketQuote:
        """
        Insere ou atualiza uma cotação com base na chave natural.
        Garante idempotência estrita sem duplicação e preserva observed_at em reingestões.
        """
        q_date = quote_dict.get("quote_date") or date.today()
        category = quote_dict["category"]
        symbol = quote_dict["symbol"]
        contract_code = quote_dict.get("contract_code") or "SPOT"
        location_id = quote_dict.get("location_id") or "GLOBAL"

        now_utc = datetime.now(timezone.utc)
        price_val = float(quote_dict["price"])
        price_dec = Decimal(str(quote_dict["price"]))

        # Classificação do Eixo 1: Origem / Proveniência (data_kind)
        src = quote_dict.get("source", "MANUAL")
        if "data_kind" in quote_dict and quote_dict["data_kind"]:
            kind = quote_dict["data_kind"]
        elif src in ("SEED_FALLBACK", "SEED_BENCHMARK", "SEED"):
            kind = DataKind.DEMO.value
        elif src in ("MANUAL", "UI_OVERRIDE"):
            kind = DataKind.MANUAL.value
        elif src in ("ESTIMATED", "PROJECTION"):
            kind = DataKind.ESTIMATED.value
        elif "LEGACY" in src or src == "UNVERIFIED":
            kind = DataKind.UNVERIFIED.value
        else:
            kind = DataKind.OBSERVED.value

        # Normaliza observed_at de entrada se fornecido
        input_observed = quote_dict.get("observed_at")
        if input_observed is not None and isinstance(input_observed, datetime):
            if input_observed.tzinfo is None:
                input_observed = input_observed.replace(tzinfo=timezone.utc)

        existing = (
            db.query(MarketQuote)
            .filter(
                and_(
                    MarketQuote.quote_date == q_date,
                    MarketQuote.category == category,
                    MarketQuote.symbol == symbol,
                    MarketQuote.contract_code == contract_code,
                    MarketQuote.location_id == location_id,
                )
            )
            .first()
        )

        if existing:
            existing.price = price_val
            existing.price_numeric = price_dec
            existing.timestamp = quote_dict.get("timestamp") or existing.timestamp or now_utc
            existing.ingested_at = now_utc
            existing.source = src
            existing.unit = quote_dict.get("unit", existing.unit)
            existing.currency = quote_dict.get("currency", existing.currency or "BRL")
            existing.data_kind = kind

            # Invariante F02: Reingestão não altera observed_at existente a menos que explicitamente fornecido novo
            if input_observed is not None:
                existing.observed_at = input_observed
            elif existing.observed_at is None:
                existing.observed_at = existing.timestamp or now_utc

            # Avaliação do Eixo 2: Atualidade (freshness)
            existing.freshness = evaluate_freshness(category, symbol, existing.observed_at, now_utc).value

            if "source_vendor" in quote_dict:
                existing.source_vendor = quote_dict["source_vendor"]
            if "source_reference" in quote_dict:
                existing.source_reference = quote_dict["source_reference"]
            if "contract_expiry" in quote_dict:
                existing.contract_expiry = quote_dict["contract_expiry"]
            if "payload_hash" in quote_dict:
                existing.payload_hash = quote_dict["payload_hash"]
            if "metadata_json" in quote_dict:
                existing.metadata_json = quote_dict["metadata_json"]

            db.add(existing)
            return existing
        else:
            obs_at = input_observed or quote_dict.get("timestamp") or now_utc
            if isinstance(obs_at, datetime) and obs_at.tzinfo is None:
                obs_at = obs_at.replace(tzinfo=timezone.utc)

            fresh = evaluate_freshness(category, symbol, obs_at, now_utc).value

            new_record = MarketQuote(
                quote_date=q_date,
                timestamp=quote_dict.get("timestamp") or now_utc,
                observed_at=obs_at,
                ingested_at=now_utc,
                category=category,
                commodity=quote_dict.get("commodity"),
                symbol=symbol,
                contract_code=contract_code,
                location_id=location_id,
                price=price_val,
                price_numeric=price_dec,
                unit=quote_dict.get("unit", "BRL"),
                currency=quote_dict.get("currency", "BRL"),
                source=src,
                source_vendor=quote_dict.get("source_vendor"),
                source_reference=quote_dict.get("source_reference"),
                contract_expiry=quote_dict.get("contract_expiry"),
                payload_hash=quote_dict.get("payload_hash"),
                data_kind=kind,
                freshness=fresh,
                metadata_json=quote_dict.get("metadata_json"),
            )
            db.add(new_record)
            return new_record

    @classmethod
    def bulk_upsert(cls, db: Session, quotes_list: List[Dict[str, Any]]) -> int:
        """Executa upsert em lote dentro de uma única transação atômica."""
        count = 0
        for item in quotes_list:
            cls.upsert_quote(db, item)
            count += 1
        db.commit()
        return count

    @classmethod
    def get_latest_quote(
        cls,
        db: Session,
        symbol: str,
        category: Optional[str] = None,
        location_id: Optional[str] = None,
    ) -> Optional[MarketQuote]:
        """
        Recupera a cotação mais recente de um ativo utilizando os índices compostos otimizados.
        Ordena prioritariamente por data da cotação, momento da observação e timestamp.
        """
        query = db.query(MarketQuote).filter(MarketQuote.symbol == symbol)
        if category:
            query = query.filter(MarketQuote.category == category)
        if location_id:
            query = query.filter(MarketQuote.location_id == location_id)

        return (
            query.order_by(
                desc(MarketQuote.quote_date),
                desc(MarketQuote.observed_at),
                desc(MarketQuote.timestamp),
            )
            .first()
        )

    @classmethod
    def get_quotes_history(
        cls,
        db: Session,
        symbol: str,
        limit: int = 100,
        start_date: Optional[date] = None,
    ) -> List[MarketQuote]:
        """Recupera a série temporal histórica de cotações para análise e gráficos."""
        query = db.query(MarketQuote).filter(MarketQuote.symbol == symbol)
        if start_date:
            query = query.filter(MarketQuote.quote_date >= start_date)
        return (
            query.order_by(
                desc(MarketQuote.quote_date),
                desc(MarketQuote.observed_at),
                desc(MarketQuote.timestamp),
            )
            .limit(limit)
            .all()
        )

    @classmethod
    def get_all_latest_quotes(cls, db: Session) -> List[MarketQuote]:
        """
        Retorna o último snapshot de mercado agrupado por símbolo e praça.
        """
        from sqlalchemy import func
        subq = (
            db.query(
                MarketQuote.symbol,
                MarketQuote.location_id,
                func.max(MarketQuote.id).label("max_id"),
            )
            .group_by(MarketQuote.symbol, MarketQuote.location_id)
            .subquery()
        )

        return (
            db.query(MarketQuote)
            .join(subq, MarketQuote.id == subq.c.max_id)
            .order_by(MarketQuote.category, MarketQuote.symbol)
            .all()
        )

    @classmethod
    def log_extraction_start(cls, db: Session, sources: str) -> ExtractionLog:
        now_utc = datetime.now(timezone.utc)
        log_entry = ExtractionLog(
            started_at=now_utc,
            status="RUNNING",
            sources_contacted=sources,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry

    @classmethod
    def log_extraction_end(
        cls,
        db: Session,
        log_id: int,
        status: str,
        records_extracted: int,
        records_upserted: int,
        details_json: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        log_entry = db.query(ExtractionLog).filter(ExtractionLog.id == log_id).first()
        if log_entry:
            log_entry.finished_at = datetime.now(timezone.utc)
            log_entry.status = status
            log_entry.records_extracted = records_extracted
            log_entry.records_upserted = records_upserted
            log_entry.details_json = details_json
            log_entry.error_message = error_message
            db.commit()
