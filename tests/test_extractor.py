"""
Testes unitários para o módulo de extração e persistência (ETL).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.connection import Base
from src.db.models import MarketQuote
from src.services.extractor import extract_and_persist_market_data, MarketDataExtractor


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_extractor_extracts_all_pillars():
    fx_quotes = MarketDataExtractor.extract_bcb_ptax()
    assert len(fx_quotes) >= 1
    assert any(q["category"] == "FX" for q in fx_quotes)

    cbot_quotes = MarketDataExtractor.extract_cbot_futures()
    assert len(cbot_quotes) >= 2
    assert any(q["symbol"] == "ZS=F" for q in cbot_quotes)
    assert any(q["symbol"] == "ZC=F" for q in cbot_quotes)

    port_quotes = MarketDataExtractor.extract_port_premiums()
    assert len(port_quotes) >= 5

    cash_quotes = MarketDataExtractor.extract_cash_prices()
    assert len(cash_quotes) >= 6

    freight_quotes = MarketDataExtractor.extract_freight_rates()
    assert len(freight_quotes) >= 6


def test_extract_and_persist_pipeline(memory_db):
    summary = extract_and_persist_market_data(db=memory_db)
    
    assert summary["status"] == "SUCCESS"
    assert summary["total_extracted"] > 20
    assert summary["total_persisted"] == summary["total_extracted"]
    
    # Conferir se as cotações foram salvas no banco
    db_count = memory_db.query(MarketQuote).count()
    assert db_count == summary["total_persisted"]
    
    # Executar uma segunda vez para garantir idempotência (não duplica linhas no mesmo dia)
    summary_second = extract_and_persist_market_data(db=memory_db)
    assert summary_second["status"] == "SUCCESS"
    db_count_second = memory_db.query(MarketQuote).count()
    assert db_count_second == db_count  # Contagem não deve duplicar!
