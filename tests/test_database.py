"""
Testes unitários para o Banco de Dados, Modelos ORM e Métodos do Repository.
"""

import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.connection import Base
from src.db.models import MarketQuote, ParitySnapshot, ExtractionLog
from src.db.repository import MarketDataRepository


@pytest.fixture
def test_db():
    """Cria um banco SQLite em memória isolado para os testes."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_upsert_single_quote(test_db):
    quote_data = {
        "quote_date": date(2026, 9, 27),
        "category": "FX",
        "symbol": "USD_BRL_PTAX_VENDA",
        "price": 5.4850,
        "unit": "BRL",
        "source": "BCB_PTAX",
    }
    
    # 1. Primeira inserção
    q1 = MarketDataRepository.upsert_quote(test_db, quote_data)
    test_db.commit()
    assert q1.id is not None
    assert q1.price == 5.4850
    
    # 2. Segunda inserção com mesma chave natural (deve atualizar sem duplicar)
    quote_data_updated = dict(quote_data)
    quote_data_updated["price"] = 5.5200
    q2 = MarketDataRepository.upsert_quote(test_db, quote_data_updated)
    test_db.commit()
    
    assert q2.id == q1.id
    assert q2.price == 5.5200
    assert test_db.query(MarketQuote).count() == 1


def test_bulk_upsert_and_latest(test_db):
    quotes = [
        {
            "quote_date": date(2026, 9, 26),
            "category": "FUTURES",
            "symbol": "ZS=F",
            "commodity": "SOJA",
            "price": 1180.0,
            "unit": "cents/bu",
            "source": "CME",
        },
        {
            "quote_date": date(2026, 9, 27),
            "category": "FUTURES",
            "symbol": "ZS=F",
            "commodity": "SOJA",
            "price": 1195.5,
            "unit": "cents/bu",
            "source": "CME",
        },
    ]
    
    count = MarketDataRepository.bulk_upsert(test_db, quotes)
    assert count == 2
    
    latest = MarketDataRepository.get_latest_quote(test_db, "ZS=F", category="FUTURES")
    assert latest is not None
    assert latest.quote_date == date(2026, 9, 27)
    assert latest.price == 1195.5


def test_extraction_logging(test_db):
    log = MarketDataRepository.log_extraction_start(test_db, "TEST_SOURCE")
    assert log.status == "RUNNING"
    
    MarketDataRepository.log_extraction_end(
        test_db,
        log_id=log.id,
        status="SUCCESS",
        records_extracted=10,
        records_upserted=10,
    )
    
    updated_log = test_db.query(ExtractionLog).filter(ExtractionLog.id == log.id).first()
    assert updated_log.status == "SUCCESS"
    assert updated_log.records_extracted == 10
