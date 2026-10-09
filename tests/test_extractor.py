"""ETL unit tests: synthetic providers only; no external integration is retained."""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.connection import Base
from src.db.models import DataKind, MarketQuote
from src.services import extractor
from src.services.extractor import extract_and_persist_market_data, MarketDataExtractor
from src.services.market_data import DEFAULT_MARKET_SEEDS

TARGET_DATE = date(2026, 10, 2)
NOW = datetime(2026, 10, 2, 15, tzinfo=timezone.utc)


@pytest.fixture
def payloads():
    return json.loads((Path(__file__).parent / "fixtures/extractor_payloads.json").read_text())


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch, payloads):
    """Replace providers before execution, freeze time and reject accidental DNS/socket use."""
    def reject_network(*args, **kwargs):
        pytest.fail("Unit test attempted DNS/socket access")

    monkeypatch.setattr(socket, "getaddrinfo", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    monkeypatch.setattr(socket.socket, "connect_ex", reject_network)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz else NOW.replace(tzinfo=None)

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return TARGET_DATE

    monkeypatch.setattr(extractor, "datetime", FrozenDatetime)
    monkeypatch.setattr(extractor, "date", FrozenDate)
    response = Mock(status_code=200)
    response.json.return_value = payloads["ptax_valid"]
    get = Mock(return_value=response)
    monkeypatch.setattr(extractor.requests, "get", get)
    # Do not import real yfinance: the production import resolves to this fake module.
    yf = ModuleType("yfinance")
    yf.Ticker = Mock(side_effect=lambda symbol: SimpleNamespace(
        fast_info=SimpleNamespace(last_price=payloads["cbot_valid"][symbol])))
    monkeypatch.setitem(sys.modules, "yfinance", yf)
    return SimpleNamespace(get=get, response=response, ticker=yf.Ticker)


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def assert_origin(quotes, kind, source, vendor, reference=None):
    for quote in quotes:
        assert quote["data_kind"] == kind.value
        assert quote["source"] == source
        assert quote["source_vendor"] == vendor
        if reference is not None:
            assert quote["source_reference"] == reference
        assert quote["quote_date"] == TARGET_DATE
        assert quote["timestamp"] == NOW


def test_ptax_observed_payload(offline_providers, payloads):
    quotes = MarketDataExtractor.extract_bcb_ptax(TARGET_DATE)
    assert [(q["symbol"], q["price"]) for q in quotes] == [
        ("USD_BRL_PTAX_VENDA", 5.2238), ("USD_BRL_PTAX_COMPRA", 5.2232)]
    assert_origin(quotes, DataKind.OBSERVED, "BCB_PTAX_OLINDA",
                  "BANCO_CENTRAL_DO_BRASIL", "BCB_PTAX_OLINDA")
    for quote in quotes:
        assert quote["observed_at"] == datetime(2026, 10, 2, 13, tzinfo=timezone.utc)
        assert json.loads(quote["metadata_json"]) == payloads["ptax_valid"]["value"][0]
    offline_providers.get.assert_called_once()
    assert "10-02-2026" in offline_providers.get.call_args.args[0]
    assert offline_providers.get.call_args.kwargs == {"timeout": 4.0}


def test_ptax_searches_previous_day(offline_providers, payloads):
    empty = Mock(status_code=200)
    empty.json.return_value = payloads["ptax_empty"]
    offline_providers.get.side_effect = [empty, offline_providers.response]
    quotes = MarketDataExtractor.extract_bcb_ptax(TARGET_DATE)
    assert len(quotes) == 2
    assert all(q["quote_date"] == TARGET_DATE - timedelta(days=1) for q in quotes)
    assert all(q["data_kind"] == DataKind.OBSERVED.value for q in quotes)
    assert offline_providers.get.call_count == 2
    assert "10-01-2026" in offline_providers.get.call_args.args[0]


@pytest.mark.parametrize("failure", ["timeout", "connection", "http", "bad_json",
    "ptax_empty", "ptax_missing_rate", "ptax_invalid_rate", "ptax_invalid_shape"])
def test_ptax_fallback_is_demo(failure, offline_providers, payloads):
    if failure == "timeout":
        offline_providers.get.side_effect = requests.Timeout("synthetic timeout")
    elif failure == "connection":
        offline_providers.get.side_effect = requests.ConnectionError("synthetic error")
    elif failure == "http":
        offline_providers.response.status_code = 503
    elif failure == "bad_json":
        offline_providers.response.json.side_effect = ValueError("invalid JSON")
    else:
        offline_providers.response.json.return_value = payloads[failure]
    quotes = MarketDataExtractor.extract_bcb_ptax(TARGET_DATE)
    assert len(quotes) == 1
    assert quotes[0]["price"] == DEFAULT_MARKET_SEEDS["fx_usd_brl"]
    assert quotes[0]["symbol"] == "USD_BRL_PTAX_VENDA"
    assert_origin(quotes, DataKind.DEMO, "SEED_FALLBACK", "SEED_BENCHMARK", "DEFAULT_MARKET_SEEDS")
    assert offline_providers.get.call_count == 5
    for offset, request_call in enumerate(offline_providers.get.call_args_list):
        assert (TARGET_DATE - timedelta(days=offset)).strftime("%m-%d-%Y") in request_call.args[0]
        assert request_call.kwargs == {"timeout": 4.0}


def test_cbot_observed_payload(offline_providers):
    quotes = MarketDataExtractor.extract_cbot_futures(TARGET_DATE)
    assert [(q["symbol"], q["price"]) for q in quotes] == [("ZS=F", 1185.25), ("ZC=F", 435.5)]
    assert_origin(quotes, DataKind.OBSERVED, "CME_YFINANCE", "CME_GROUP")
    assert all(q["source_reference"] == q["symbol"] for q in quotes)
    assert offline_providers.ticker.call_args_list == [call("ZS=F"), call("ZC=F")]


@pytest.mark.parametrize("failure", ["timeout", "connection", "cbot_missing", "cbot_invalid"])
def test_cbot_fallback_is_demo(failure, offline_providers, payloads):
    if failure in ("timeout", "connection"):
        error = requests.Timeout if failure == "timeout" else requests.ConnectionError
        offline_providers.ticker.side_effect = error("synthetic failure")
    else:
        offline_providers.ticker.side_effect = lambda symbol: SimpleNamespace(
            fast_info=SimpleNamespace(last_price=payloads[failure][symbol]))
    quotes = MarketDataExtractor.extract_cbot_futures(TARGET_DATE)
    assert len(quotes) == 2
    assert_origin(quotes, DataKind.DEMO, "SEED_BENCHMARK", "SEED_BENCHMARK", "DEFAULT_MARKET_SEEDS")
    for quote in quotes:
        assert quote["price"] == DEFAULT_MARKET_SEEDS["cbot_prices"][quote["commodity"]]["last_price_cents"]
    assert offline_providers.ticker.call_args_list == [call("ZS=F"), call("ZC=F")]


def test_cbot_mixed_sources(offline_providers):
    offline_providers.ticker.side_effect = [
        SimpleNamespace(fast_info=SimpleNamespace(last_price=1185.25)), requests.Timeout("synthetic")]
    observed, demo = MarketDataExtractor.extract_cbot_futures(TARGET_DATE)
    assert_origin([observed], DataKind.OBSERVED, "CME_YFINANCE", "CME_GROUP", "ZS=F")
    assert_origin([demo], DataKind.DEMO, "SEED_BENCHMARK", "SEED_BENCHMARK", "DEFAULT_MARKET_SEEDS")


def test_extractor_extracts_all_pillars():
    assert len(MarketDataExtractor.extract_bcb_ptax()) == 2
    assert len(MarketDataExtractor.extract_cbot_futures()) == 2
    for method, category, source, vendor, minimum in [
        (MarketDataExtractor.extract_port_premiums, "PORT_PREMIUM", "PORT_DESK_INDICATION", "PORT_TERMINALS_DESK", 5),
        (MarketDataExtractor.extract_cash_prices, "PHYSICAL_CASH", "CEPEA_REGIONAL_DESK", "CEPEA_ESALQ", 6),
        (MarketDataExtractor.extract_freight_rates, "FREIGHT", "ESALQ_LOG_BENCHMARK", "ESALQ_LOG", 6),
    ]:
        quotes = method()
        assert len(quotes) >= minimum
        assert all(q["category"] == category for q in quotes)
        assert_origin(quotes, DataKind.ESTIMATED, source, vendor, source)


@pytest.mark.parametrize("fallback", [False, True], ids=["observed", "offline-fallback"])
def test_extract_and_persist_pipeline(memory_db, offline_providers, fallback):
    if fallback:
        offline_providers.get.side_effect = requests.Timeout("synthetic")
        offline_providers.ticker.side_effect = requests.ConnectionError("synthetic")
    summary = extract_and_persist_market_data(db=memory_db, target_date=TARGET_DATE)
    assert summary["status"] == "SUCCESS"
    assert summary["quote_date"] == TARGET_DATE.isoformat()
    assert summary["total_extracted"] > 20
    assert summary["total_persisted"] == summary["total_extracted"]
    rows = memory_db.query(MarketQuote).all()
    assert len(rows) == summary["total_persisted"]
    financial = [q for q in rows if q.category in ("FX", "FUTURES")]
    assert len(financial) == (3 if fallback else 4)
    assert all(q.data_kind == (DataKind.DEMO.value if fallback else DataKind.OBSERVED.value) for q in financial)
    fx = next(q for q in financial if q.symbol == "USD_BRL_PTAX_VENDA")
    assert fx.price == (DEFAULT_MARKET_SEEDS["fx_usd_brl"] if fallback else 5.2238)
    assert fx.source == ("SEED_FALLBACK" if fallback else "BCB_PTAX_OLINDA")
    second = extract_and_persist_market_data(db=memory_db, target_date=TARGET_DATE)
    assert second["status"] == "SUCCESS"
    assert second["total_persisted"] == len(rows)
    assert memory_db.query(MarketQuote).count() == len(rows)
