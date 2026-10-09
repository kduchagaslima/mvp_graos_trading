"""Offline gate loaded by pytest.ini before test collection.

Blocks Python DNS and IP sockets, substitutes yfinance with a synthetic unavailable-price provider,
and uses a disposable SQLite database. Dependencies must be installed first.
"""

import socket
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


def pytest_configure(config):
    patch = pytest.MonkeyPatch()
    directory = TemporaryDirectory(prefix="graos-offline-")
    patch.setenv("DATABASE_URL", f"sqlite:///{directory.name}/market_data.db")

    def reject_network(*args, **kwargs):
        pytest.fail("Offline gate: DNS/IP socket access attempted", pytrace=False)

    patch.setattr(socket, "getaddrinfo", reject_network)
    patch.setattr(socket, "gethostbyname", reject_network)
    patch.setattr(socket, "gethostbyname_ex", reject_network)
    patch.setattr(socket, "gethostbyaddr", reject_network)
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            reject_network()
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            reject_network()
        return original_connect_ex(sock, address)

    patch.setattr(socket.socket, "connect", connect)
    patch.setattr(socket.socket, "connect_ex", connect_ex)
    patch.setattr(socket.socket, "sendto", reject_network)
    yf = ModuleType("yfinance")
    yf.Ticker = Mock(side_effect=lambda symbol: SimpleNamespace(fast_info=None))
    patch.setitem(sys.modules, "yfinance", yf)
    config._graos_offline_resources = (patch, directory)


def pytest_unconfigure(config):
    resources = getattr(config, "_graos_offline_resources", None)
    if resources:
        patch, directory = resources
        patch.undo()
        directory.cleanup()
