"""
Camada de Acesso a Dados (Repository / DAO) com queries otimizadas para consumo de Market Data.
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from src.db.models import MarketQuote, ParitySnapshot, ExtractionLog


class MarketDataRepository:
    """
    Operações de consulta e persistência otimizadas para Market Data de Grãos.
    """

    @classmethod
    def upsert_quote(cls, db: Session, quote_dict: Dict[str, Any]) -> MarketQuote:
        """
        Insere ou atualiza uma cotação com base na chave natural.
        Garante idempotência estrita sem duplicação de dados temporais.
        """
        q_date = quote_dict.get("quote_date") or date.today()
        category = quote_dict["category"]
        symbol = quote_dict["symbol"]
        contract_code = quote_dict.get("contract_code") or "SPOT"
        location_id = quote_dict.get("location_id") or "GLOBAL"

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
            existing.price = float(quote_dict["price"])
            existing.timestamp = quote_dict.get("timestamp") or datetime.utcnow()
            existing.source = quote_dict.get("source", existing.source)
            existing.unit = quote_dict.get("unit", existing.unit)
            if "metadata_json" in quote_dict:
                existing.metadata_json = quote_dict["metadata_json"]
            db.add(existing)
            return existing
        else:
            new_record = MarketQuote(
                quote_date=q_date,
                timestamp=quote_dict.get("timestamp") or datetime.utcnow(),
                category=category,
                commodity=quote_dict.get("commodity"),
                symbol=symbol,
                contract_code=contract_code,
                location_id=location_id,
                price=float(quote_dict["price"]),
                unit=quote_dict.get("unit", "BRL"),
                source=quote_dict.get("source", "MANUAL"),
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
        """
        query = db.query(MarketQuote).filter(MarketQuote.symbol == symbol)
        if category:
            query = query.filter(MarketQuote.category == category)
        if location_id:
            query = query.filter(MarketQuote.location_id == location_id)

        return query.order_by(desc(MarketQuote.quote_date), desc(MarketQuote.timestamp)).first()

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
        return query.order_by(desc(MarketQuote.quote_date), desc(MarketQuote.timestamp)).limit(limit).all()

    @classmethod
    def get_all_latest_quotes(cls, db: Session) -> List[MarketQuote]:
        """
        Retorna o último snapshot de mercado agrupado por símbolo e praça.
        """
        # Subquery para pegar o ID máximo por chave natural
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
        log_entry = ExtractionLog(
            started_at=datetime.utcnow(),
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
            log_entry.finished_at = datetime.utcnow()
            log_entry.status = status
            log_entry.records_extracted = records_extracted
            log_entry.records_upserted = records_upserted
            log_entry.details_json = details_json
            log_entry.error_message = error_message
            db.commit()
