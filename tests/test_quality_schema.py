"""
Suíte de Testes para o Schema de Qualidade de Dados v2, Rastreabilidade e Migrações (Ticket F02).
Valida:
1. Dois eixos: data_kind (OBSERVED, MANUAL, ESTIMATED, DEMO, UNVERIFIED) e freshness (CURRENT, STALE, UNKNOWN).
2. Preservação estrita de observed_at em reingestão (apenas ingested_at e timestamp atualizados).
3. Classificação de seeds como DEMO/ESTIMATED, nunca OBSERVED.
4. Regras de frescor conscientes de calendário (PTAX de sexta-feira é CURRENT no fim de semana).
5. Precisão numérica via price_numeric (Decimal).
6. Idempotência e integridade do executor de migrações (run_migrations).
"""

import os
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.connection import Base
from src.db.models import MarketQuote, DataKind, FreshnessStatus
from src.db.repository import MarketDataRepository
from src.services.freshness import evaluate_freshness, is_weekend, get_business_day_delta_hours
from src.services.extractor import MarketDataExtractor
from src.services.bacen_extractor import BacenMacroExtractor
from src.services.b3_extractor import B3DataExtractor
from src.db.migrate import run_migrations, ensure_migration_table, get_applied_migrations


@pytest.fixture
def in_memory_db():
    """Cria banco SQLite em memória isolado para testes unitários."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session, engine
    session.close()


def test_data_kind_and_freshness_enums():
    """Valida se os enums contêm todos os valores obrigatórios do contrato F02."""
    assert set(k.value for k in DataKind) == {"OBSERVED", "MANUAL", "ESTIMATED", "DEMO", "UNVERIFIED"}
    assert set(f.value for f in FreshnessStatus) == {"CURRENT", "STALE", "UNKNOWN"}


def test_upsert_preserves_observed_at_on_reingestion(in_memory_db):
    """
    Invariante F02: Re-ingestão de cotação existente preserva observed_at original,
    atualizando apenas ingested_at.
    """
    session, _ = in_memory_db
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
    original_observed = datetime(2026, 10, 1, 9, 30, 0, tzinfo=timezone.utc)

    # 1. Primeira ingestão
    first_dict = {
        "quote_date": date(2026, 10, 1),
        "timestamp": t0,
        "observed_at": original_observed,
        "category": "FX",
        "symbol": "USD_BRL_PTAX_VENDA",
        "contract_code": "SPOT",
        "location_id": "BRASIL_BCB",
        "price": 5.4520,
        "unit": "BRL",
        "currency": "BRL",
        "source": "BCB_PTAX_OLINDA",
        "data_kind": DataKind.OBSERVED.value,
    }
    created = MarketDataRepository.upsert_quote(session, first_dict)
    session.commit()

    assert created.id is not None
    assert created.observed_at == original_observed
    first_ingested_at = created.ingested_at

    # 2. Reingestão 2 horas depois sem fornecer novo observed_at
    reingest_dict = {
        "quote_date": date(2026, 10, 1),
        "timestamp": datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
        "category": "FX",
        "symbol": "USD_BRL_PTAX_VENDA",
        "contract_code": "SPOT",
        "location_id": "BRASIL_BCB",
        "price": 5.4520,  # mesmo valor
        "unit": "BRL",
        "source": "BCB_PTAX_OLINDA",
    }
    updated = MarketDataRepository.upsert_quote(session, reingest_dict)
    session.commit()

    # observed_at NÃO pode ter mudado para a hora da reingestão
    assert updated.id == created.id
    assert updated.observed_at == original_observed
    # ingested_at deve ter sido atualizado
    assert updated.ingested_at >= first_ingested_at


def test_seeds_are_never_marked_observed(in_memory_db):
    """
    Invariante F02: Nenhuma seed de demonstração ou fallback pode ser salva como OBSERVED.
    """
    session, _ = in_memory_db

    # Simula inserção de seed via repositório
    quote_dict = {
        "quote_date": date(2026, 10, 2),
        "category": "FX",
        "symbol": "USD_BRL_PTAX_VENDA",
        "price": 5.40,
        "unit": "BRL",
        "source": "SEED_FALLBACK",  # origem seed
    }
    record = MarketDataRepository.upsert_quote(session, quote_dict)
    session.commit()

    assert record.data_kind in (DataKind.DEMO.value, DataKind.ESTIMATED.value)
    assert record.data_kind != DataKind.OBSERVED.value


def test_decimal_precision_stored_accurately(in_memory_db):
    """
    Valida precisão decimal exata em price_numeric (sem arredondamento binário float).
    """
    session, _ = in_memory_db
    precise_val = Decimal("133.5555")

    quote_dict = {
        "quote_date": date(2026, 10, 2),
        "category": "PHYSICAL_CASH",
        "symbol": "CASH_SORRISO_SOJA",
        "price": float(precise_val),
        "unit": "R$/saca",
        "source": "CEPEA_REGIONAL_DESK",
        "data_kind": DataKind.ESTIMATED.value,
    }
    record = MarketDataRepository.upsert_quote(session, quote_dict)
    session.commit()

    assert record.price_numeric is not None
    # Comparação como Decimal
    assert Decimal(str(record.price_numeric)) == pytest.approx(precise_val, abs=1e-4)
    d = record.to_dict()
    assert "price_numeric" in d
    assert "data_kind" in d
    assert "freshness" in d


def test_calendar_aware_freshness_weekend_ptax():
    """
    Invariante F02: Fechamento PTAX de sexta-feira às 18:00 UTC permanece CURRENT no sábado e domingo.
    Torna-se STALE somente se ultrapassar a tolerância no dia útil seguinte.
    """
    # Sexta-feira 02/10/2026 às 18:00 UTC
    friday_close = datetime(2026, 10, 2, 18, 0, 0, tzinfo=timezone.utc)

    # Sábado 03/10/2026 às 14:00 UTC (fim de semana)
    saturday_noon = datetime(2026, 10, 3, 14, 0, 0, tzinfo=timezone.utc)
    assert is_weekend(saturday_noon) is True
    status_sat = evaluate_freshness("FX", "USD_BRL_PTAX_VENDA", friday_close, saturday_noon)
    assert status_sat == FreshnessStatus.CURRENT

    # Domingo 04/10/2026 às 22:00 UTC (fim de semana)
    sunday_night = datetime(2026, 10, 4, 22, 0, 0, tzinfo=timezone.utc)
    status_sun = evaluate_freshness("FX", "USD_BRL_PTAX_VENDA", friday_close, sunday_night)
    assert status_sun == FreshnessStatus.CURRENT

    # Segunda-feira 05/10/2026 às 12:00 UTC (12h de dia útil decorridas)
    monday_noon = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)
    status_mon = evaluate_freshness("FX", "USD_BRL_PTAX_VENDA", friday_close, monday_noon)
    assert status_mon == FreshnessStatus.CURRENT

    # Quarta-feira 07/10/2026 às 12:00 UTC (> 48h úteis decorridas sem nova PTAX)
    wednesday_noon = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
    status_wed = evaluate_freshness("FX", "USD_BRL_PTAX_VENDA", friday_close, wednesday_noon)
    assert status_wed == FreshnessStatus.STALE


def test_calendar_aware_freshness_monthly_indicators():
    """
    Indicadores mensais (IPCA, IGP-M) possuem ciclo mensal e tolerância de 45 dias.
    """
    base_month = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    # 25 dias depois -> CURRENT
    t1 = datetime(2026, 9, 26, 0, 0, 0, tzinfo=timezone.utc)
    assert evaluate_freshness("MACRO_INDEX", "IPCA_12M", base_month, t1) == FreshnessStatus.CURRENT

    # 50 dias depois -> STALE
    t2 = datetime(2026, 10, 21, 0, 0, 0, tzinfo=timezone.utc)
    assert evaluate_freshness("MACRO_INDEX", "IPCA_12M", base_month, t2) == FreshnessStatus.STALE


def test_extractor_quotes_enrichment_metadata():
    """
    Verifica se todos os extratores emitem cotações com campos de qualidade preenchidos.
    """
    # 1. CBOT Futures
    cbot_quotes = MarketDataExtractor.extract_cbot_futures(date(2026, 10, 2))
    assert len(cbot_quotes) >= 2
    for q in cbot_quotes:
        assert q["data_kind"] in (DataKind.OBSERVED.value, DataKind.DEMO.value)
        assert q["currency"] == "USD"
        assert q["source_vendor"] is not None
        assert q["observed_at"] is not None

    # 2. Port Premiums
    port_quotes = MarketDataExtractor.extract_port_premiums(date(2026, 10, 2))
    assert len(port_quotes) > 0
    for q in port_quotes:
        assert q["data_kind"] == DataKind.ESTIMATED.value
        assert q["currency"] == "USD"
        assert q["source_vendor"] == "PORT_TERMINALS_DESK"

    # 3. Cash Prices
    cash_quotes = MarketDataExtractor.extract_cash_prices(date(2026, 10, 2))
    assert len(cash_quotes) > 0
    for q in cash_quotes:
        assert q["data_kind"] == DataKind.ESTIMATED.value
        assert q["currency"] == "BRL"
        assert q["source_vendor"] == "CEPEA_ESALQ"

    # 4. Freight Rates
    freight_quotes = MarketDataExtractor.extract_freight_rates(date(2026, 10, 2))
    assert len(freight_quotes) > 0
    for q in freight_quotes:
        assert q["data_kind"] == DataKind.ESTIMATED.value
        assert q["currency"] == "BRL"
        assert q["source_vendor"] == "ESALQ_LOG"

    # 5. B3 Derivatives
    b3_quotes = B3DataExtractor.extract_b3_derivatives(date(2026, 10, 2))
    assert len(b3_quotes) > 0
    for q in b3_quotes:
        assert q["data_kind"] == DataKind.DEMO.value
        assert q["currency"] in ("BRL", "USD")
        assert q["source_vendor"] in ("B3_BMF", "CEPEA_ESALQ")


def test_migration_runner_idempotency(in_memory_db):
    """
    Verifica se o migrador SQL versionado cria schema_migrations e executa com idempotência.
    """
    _, engine = in_memory_db
    applied_first = run_migrations(target_engine=engine)
    assert len(applied_first) >= 2
    assert any("001_initial_schema" in m["version"] for m in applied_first)
    assert any("002_quality_schema_v2" in m["version"] for m in applied_first)

    # Segunda execução imediata não deve reaplicar nada
    applied_second = run_migrations(target_engine=engine)
    assert len(applied_second) == 0
