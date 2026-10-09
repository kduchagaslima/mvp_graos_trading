"""
Inventário Formal e Congelamento de Contratos de API (Ticket F01).
Classifica os endpoints da aplicação por camada de acesso (Público, Mercado Cliente, Motores, Operador da Plataforma)
e valida a rastreabilidade com o Git SHA e ambiente de execução.
"""

from collections import Counter
import subprocess
import platform
import sys
import pytest
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute

from src.api.main import app


# Classificação formal dos endpoints existentes
EXPECTED_ACCESS_TIERS = {
    # 1. PÚBLICAS / STATUS (Abertas ao tráfego geral e health check)
    "PUBLIC": [
        ("GET", "/health"),
        ("GET", "/api/metadata/commodities"),
        ("GET", "/api/metadata/locations"),
    ],
    # 2. MERCADO CLIENTE (Dados compartilhados consumidos pela mesa de operações)
    "CLIENT_MARKET": [
        ("GET", "/api/market-data/snapshot"),
        ("GET", "/api/market-data/quotes"),
        ("GET", "/api/market-data/history/{symbol}"),
        ("GET", "/api/market-data/candlestick/{symbol}"),
        ("GET", "/api/b3/quotes"),
        ("GET", "/api/macro/indices"),
        ("GET", "/api/ports/summary"),
        ("GET", "/api/tax-funds/summary"),
        ("GET", "/api/freight/routes"),
        ("GET", "/api/freight/history"),
        ("GET", "/api/freight/arbitrage"),
    ],
    # 3. MOTORES DE CÁLCULO (Cálculos de negócio com parâmetros do usuário)
    "CLIENT_ENGINES": [
        ("POST", "/api/parity/calculate"),
        ("POST", "/api/parity/batch"),
        ("POST", "/api/carry/calculate"),
        ("POST", "/api/stress/simulate"),
        ("POST", "/api/proposals/compare"),
    ],
    # 4. OPERADOR DA PLATAFORMA (Rotas administrativas protegidas por require_platform_operator em F12)
    "OPERATOR_ADMIN": [
        ("POST", "/api/market-data/extract"),
        ("POST", "/api/market-data/fx/refresh"),
        ("POST", "/api/b3/extract"),
        ("POST", "/api/macro/extract"),
        ("GET", "/api/market-data/logs"),
        ("GET", "/api/scheduler/status"),
        ("GET", "/api/admin/sources/health"),
    ],
    # 5. CLIENTE PRIVADO / TENANT (Identidade, organizações, convites, membros e perfis privados - F09, F10, F11)
    "CLIENT_PRIVATE": [
        ("GET", "/api/me"),
        ("POST", "/api/organizations"),
        ("GET", "/api/organizations/{org_id}/scenarios"),
        ("POST", "/api/organizations/{org_id}/scenarios"),
        ("DELETE", "/api/organizations/{org_id}/scenarios/{scenario_id}"),
        ("GET", "/api/organizations/{org_id}/cost-profiles"),
        ("POST", "/api/organizations/{org_id}/cost-profiles"),
        ("GET", "/api/organizations/{org_id}/cost-profiles/{profile_id}"),
        ("PUT", "/api/organizations/{org_id}/cost-profiles/{profile_id}"),
        ("GET", "/api/organizations/{org_id}/members"),
        ("DELETE", "/api/organizations/{org_id}/members/{user_id}"),
        ("POST", "/api/organizations/{org_id}/invitations"),
        ("GET", "/api/organizations/{org_id}/invitations"),
        ("POST", "/api/invitations/{token}/accept"),
    ],
}


def get_git_commit_sha() -> str:
    """Recupera o SHA do commit atual para auditoria."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        return sha
    except Exception:
        return "UNKNOWN_SHA"


# HEAD/OPTIONS are protocol helpers, explicitly excluded from the business inventory.
IGNORED_METHODS = {"HEAD", "OPTIONS"}


def assert_routes_inventory(routes, tiers=EXPECTED_ACCESS_TIERS):
    registered = [
        (method.upper(), route.path)
        for route in routes if isinstance(route, APIRoute)
        for method in route.methods if method.upper() not in IGNORED_METHODS
    ]
    expected = [
        (method.upper(), path) for entries in tiers.values() for method, path in entries
        if method.upper() not in IGNORED_METHODS
    ]
    registered_counts = Counter(registered)
    expected_counts = Counter(expected)
    assert all(count == 1 for count in registered_counts.values()), (
        f"Duplicate registered routes: {registered_counts}"
    )
    assert all(count == 1 for count in expected_counts.values()), (
        f"Duplicate inventory entries: {expected_counts}"
    )
    missing = set(expected) - set(registered)
    extra = set(registered) - set(expected)
    assert not missing and not extra, f"Route inventory mismatch: missing={sorted(missing)}, extra={sorted(extra)}"


def test_api_routes_inventory_completeness():
    """Compare exact method/path pairs, including duplicate detection."""
    assert_routes_inventory(app.routes)


@pytest.mark.parametrize("mutation", ["extra", "removed", "duplicate"])
def test_inventory_detects_route_mutations(mutation):
    routes = list(app.routes)
    if mutation == "extra":
        routes.append(APIRoute("/api/fictitious", lambda: None, methods=["GET"]))
    elif mutation == "removed":
        routes = [route for route in routes if getattr(route, "path", None) != "/health"]
    else:
        routes.append(next(route for route in routes if isinstance(route, APIRoute)))
    with pytest.raises(AssertionError, match="Route inventory mismatch|Duplicate registered routes"):
        assert_routes_inventory(routes)


def test_inventory_detects_duplicate_classification():
    tiers = {tier: list(routes) for tier, routes in EXPECTED_ACCESS_TIERS.items()}
    tiers["CLIENT_PRIVATE"].append(("GET", "/health"))
    with pytest.raises(AssertionError, match="Duplicate inventory entries"):
        assert_routes_inventory(app.routes, tiers)


def test_inventory_handles_head_and_options_explicitly():
    routes = list(app.routes) + [
        APIRoute("/health", lambda: None, methods=["HEAD", "OPTIONS"])
    ]
    assert_routes_inventory(routes)


def test_git_sha_and_environment_audit_traceability():
    """
    Verifica rastreabilidade com o Git SHA e ambiente técnico.
    """
    sha = get_git_commit_sha()
    assert len(sha) == 40 or sha == "UNKNOWN_SHA"
    
    # Valida metadados de execução
    py_version = sys.version_info
    assert py_version.major == 3
    assert py_version.minor in (11, 12, 13, 14)

    # Imprime relatório auditável nos logs de teste
    print(f"\n[AUDIT TRACEABILITY] Commit SHA: {sha}")
    print(f"[AUDIT TRACEABILITY] OS/Platform: {platform.system()} {platform.release()}")
    print(f"[AUDIT TRACEABILITY] Python Version: {sys.version.split()[0]}")
    print(f"[AUDIT TRACEABILITY] Total Endpoints Mapeados: {sum(len(routes) for routes in EXPECTED_ACCESS_TIERS.values())}")


def test_public_endpoints_smoke():
    """
    Verifica que os endpoints públicos respondem com status 200 e payload compatível.
    """
    with TestClient(app) as client:
        res_health = client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "healthy"

        res_comm = client.get("/api/metadata/commodities")
        assert res_comm.status_code == 200
        assert "SOJA" in res_comm.json()
        assert "MILHO" in res_comm.json()

        res_loc = client.get("/api/metadata/locations")
        assert res_loc.status_code == 200
        assert "ports" in res_loc.json()
        assert "hubs" in res_loc.json()
