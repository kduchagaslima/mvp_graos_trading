"""
Testes unitários e de integração para o Extrator B3, Agendador (Scheduler) e Endpoints REST.
"""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from src.db.connection import Base, get_db
from src.db.models import MarketQuote, ExtractionLog, User
from src.api.auth import require_platform_operator
from src.services.b3_extractor import B3DataExtractor, extract_and_persist_b3_data
from src.scheduler.runner import (
    SCHEDULED_JOBS_METADATA,
    get_scheduler_status,
    build_scheduler,
    APSCHEDULER_AVAILABLE,
)
from src.api.main import app


@pytest.fixture
def engine():
    """Cria um engine SQLite compartilhado em memória com StaticPool."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def memory_db(engine):
    """Cria uma sessão de banco isolada para testes diretos."""
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(engine):
    """Cria um cliente de teste da API FastAPI com injeção segura de sessão."""
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_platform_operator] = lambda: User(
        id=1, email="admin@platform.local", is_platform_operator=True
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_b3_extractor_data_structure():
    """Valida se o extrator gera as cotações esperadas de Milho (CCM), Soja (SJC) e CEPEA."""
    quotes = B3DataExtractor.extract_b3_derivatives()
    assert len(quotes) >= 9

    # Derivativos de Milho B3
    ccm_quotes = [q for q in quotes if q["commodity"] == "MILHO" and q["category"] == "B3_FUTURES"]
    assert len(ccm_quotes) == 4
    assert any("CCMH27" in q["symbol"] for q in ccm_quotes)
    assert any("CCMK27" in q["symbol"] for q in ccm_quotes)

    # Derivativos de Soja B3
    sjc_quotes = [q for q in quotes if q["commodity"] == "SOJA" and q["category"] == "B3_FUTURES"]
    assert len(sjc_quotes) == 3
    assert any("SJCH27" in q["symbol"] for q in sjc_quotes)

    # Indicadores CEPEA/ESALQ
    cepea_quotes = [q for q in quotes if q["category"] == "CEPEA_INDEX"]
    assert len(cepea_quotes) == 2
    assert any("CAMPINAS" in q["symbol"] for q in cepea_quotes)
    assert any("PARANAGUA" in q["symbol"] for q in cepea_quotes)


def test_b3_persist_and_idempotency(memory_db):
    """Valida a persistência no banco e idempotência das cotações B3."""
    summary = extract_and_persist_b3_data(db=memory_db, session_type="TEST_RUN")
    assert summary["status"] == "SUCCESS"
    assert summary["total_extracted"] == summary["total_persisted"]
    assert summary["total_persisted"] >= 9

    # Verifica no banco
    db_count = memory_db.query(MarketQuote).count()
    assert db_count == summary["total_persisted"]

    # Verifica log de auditoria
    log = memory_db.query(ExtractionLog).first()
    assert log is not None
    assert log.status == "SUCCESS"
    assert "B3_BMF_DERIVATIVOS" in log.sources_contacted

    # Executa novamente no mesmo dia: não deve duplicar registros
    summary_again = extract_and_persist_b3_data(db=memory_db, session_type="TEST_RUN_2")
    assert summary_again["status"] == "SUCCESS"
    db_count_after = memory_db.query(MarketQuote).count()
    assert db_count_after == db_count


def test_scheduler_metadata_and_status():
    """Valida a configuração e metadados das rotinas do agendador."""
    assert len(SCHEDULED_JOBS_METADATA) == 4

    job_ids = [j["id"] for j in SCHEDULED_JOBS_METADATA]
    assert "b3_settlement" in job_ids
    assert "b3_intraday_morning" in job_ids
    assert "b3_intraday_afternoon" in job_ids
    assert "general_market_data" in job_ids

    status = get_scheduler_status()
    assert "status" in status
    assert status["timezone"] == "America/Sao_Paulo"
    assert len(status["jobs"]) == 4

    if APSCHEDULER_AVAILABLE:
        scheduler = build_scheduler()
        assert scheduler is not None
        jobs = scheduler.get_jobs()
        assert len(jobs) == 4


def test_api_b3_and_scheduler_endpoints(client, memory_db):
    """Testa os endpoints REST FastAPI para B3 e Scheduler."""
    # 1. Consulta status do scheduler
    res_sched = client.get("/api/scheduler/status")
    assert res_sched.status_code == 200
    sched_data = res_sched.json()
    assert sched_data["timezone"] == "America/Sao_Paulo"
    assert len(sched_data["jobs"]) == 4

    # 2. Executa extração B3 via API
    res_extract = client.post("/api/b3/extract?session_type=API_UNIT_TEST")
    assert res_extract.status_code == 200
    extract_data = res_extract.json()
    assert extract_data["status"] == "SUCCESS"
    assert extract_data["total_persisted"] >= 9

    # 3. Consulta cotações B3 persistidas via API
    res_quotes = client.get("/api/b3/quotes")
    assert res_quotes.status_code == 200
    quotes_data = res_quotes.json()
    assert len(quotes_data) >= 9
    assert any(q["symbol"].startswith("B3_CCM") for q in quotes_data)
