"""
Testes unitários para geração de séries históricas de Candlestick OHLC.
"""

import pytest
from src.services.market_data import market_service


def test_candlestick_series_length_and_structure():
    series = market_service.get_candlestick_series("CBOT_SOJA", days=30)
    assert len(series) == 30
    
    for candle in series:
        assert "time" in candle
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        assert "volume" in candle
        
        # Invariantes de Candlestick OHLC
        assert candle["high"] >= candle["low"]
        assert candle["high"] >= candle["open"]
        assert candle["high"] >= candle["close"]
        assert candle["low"] <= candle["open"]
        assert candle["low"] <= candle["close"]
        assert candle["volume"] > 0


def test_candlestick_supported_symbols():
    symbols = ["CBOT_SOJA", "CBOT_MILHO", "USD_BRL", "B3_MILHO", "PARIDADE_FAS"]
    for sym in symbols:
        series = market_service.get_candlestick_series(sym, days=15)
        assert len(series) == 15
        assert all(c["open"] > 0 for c in series)


def test_candlestick_continuity():
    series = market_service.get_candlestick_series("USD_BRL", days=10)
    for i in range(len(series) - 1):
        # O fechamento de um candle é a abertura do candle seguinte
        assert series[i]["close"] == series[i + 1]["open"]
