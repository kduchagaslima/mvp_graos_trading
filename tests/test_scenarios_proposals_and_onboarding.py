"""
Testes automatizados para Cenários Salvos (U03), Comparador de Propostas (U04)
e Onboarding de Organizações (Etapas 1 e 2).
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from src.api.main import app
from src.db.connection import Base, get_db
from src.db.models import User, Organization, Membership, MembershipRole
from src.api.auth import set_test_public_key


@pytest.fixture(scope="session")
def rsa_keypair():
    private_key = rsa.generate_key(public_exponent=65537, key_size=2048) if hasattr(rsa, "generate_key") else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return {"private_pem": private_pem, "public_pem": public_pem}


@pytest.fixture
def test_db_client(rsa_keypair):
    set_test_public_key(rsa_keypair["public_pem"])
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    
    yield {"session": session, "client": client, "rsa": rsa_keypair}

    app.dependency_overrides.clear()
    session.close()
    set_test_public_key(None)


def make_auth_header(rsa_keypair, sub: str = "test-user-sub", email: str = "trader@agritrading.local"):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "email": email,
        "token_use": "access",
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "iat": int(now.timestamp()),
    }
    token = jwt.encode(payload, rsa_keypair["private_pem"], algorithm="RS256", headers={"kid": "test-key-1"})
    return {"Authorization": f"Bearer {token}"}


def test_create_organization_onboarding(test_db_client):
    """Valida o fluxo de onboarding self-serve criando empresa e perfil padrão."""
    client = test_db_client["client"]
    auth_header = make_auth_header(test_db_client["rsa"], sub="onboarding-sub", email="onboard@agritrading.local")

    res = client.post(
        "/api/organizations",
        json={"name": "Agro Grãos do Cerrado", "slug": "agro-cerrado"},
        headers=auth_header,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "created"
    assert data["organization"]["name"] == "Agro Grãos do Cerrado"
    assert data["organization"]["slug"] == "agro-cerrado"
    assert data["membership"]["role"] == "OWNER"

    # Verificar que perfil padrão foi criado e pode ser lido
    org_id = data["organization"]["id"]
    prof_res = client.get(f"/api/organizations/{org_id}/cost-profiles", headers=auth_header)
    assert prof_res.status_code == 200
    profiles = prof_res.json()
    assert len(profiles) >= 1
    assert profiles[0]["name"] == "Perfil Padrão Trading"


def test_saved_scenarios_workflow(test_db_client):
    """Valida gravação, listagem e exclusão de cenários salvos (Ticket U03)."""
    client = test_db_client["client"]
    auth_header = make_auth_header(test_db_client["rsa"], sub="scenario-user", email="scenarios@agritrading.local")

    # 1. Cria organização
    res_org = client.post(
        "/api/organizations",
        json={"name": "Trading Sul", "slug": "trading-sul"},
        headers=auth_header,
    )
    assert res_org.status_code == 200
    org_id = res_org.json()["organization"]["id"]

    # 2. Salva cenário
    scenario_payload = {
        "name": "Soja Sorriso Santos Safra 2026",
        "commodity": "SOJA",
        "hub_id": "sorriso_mt",
        "port_id": "STS",
        "cbot_price_cents": 1180.0,
        "port_premium_cents": 65.0,
        "usd_brl_fx": 5.4850,
        "freight_cost_brl_ton": 340.0,
        "elevation_cost_usd_ton": 8.0,
        "demurrage_risk_usd_ton": 2.5,
        "other_port_costs_usd_ton": 15.0,
        "tax_fund_brl_bag": 2.85,
        "net_parity_brl_bag": 123.85,
        "net_parity_brl_ton": 2064.17,
        "fob_usd_ton": 457.43,
        "notes": "Simulação negociada com frete carretão",
    }
    res_save = client.post(f"/api/organizations/{org_id}/scenarios", json=scenario_payload, headers=auth_header)
    assert res_save.status_code == 200
    scen_data = res_save.json()
    assert scen_data["name"] == "Soja Sorriso Santos Safra 2026"
    scen_id = scen_data["id"]

    # 3. Lista cenários
    res_list = client.get(f"/api/organizations/{org_id}/scenarios", headers=auth_header)
    assert res_list.status_code == 200
    scenarios = res_list.json()
    assert len(scenarios) == 1
    assert scenarios[0]["id"] == scen_id

    # 4. Deleta cenário
    res_del = client.delete(f"/api/organizations/{org_id}/scenarios/{scen_id}", headers=auth_header)
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # 5. Lista novamente (vazio)
    res_empty = client.get(f"/api/organizations/{org_id}/scenarios", headers=auth_header)
    assert len(res_empty.json()) == 0


def test_proposals_comparison_best_bid():
    """Valida o comparador de propostas lado a lado (Ticket U04)."""
    client = TestClient(app)
    payload = {
        "proposals": [
            {
                "name": "Comprador A - Porto Santos (STS)",
                "commodity": "SOJA",
                "hub_id": "sorriso_mt",
                "port_id": "STS",
                "cbot_cents": 1180.0,
                "premium_cents": 60.0,
                "fx_rate": 5.4850,
                "freight_brl_ton": 340.0,
                "volume_bags": 20000.0,
            },
            {
                "name": "Comprador B - Porto Barcarena (BCR)",
                "commodity": "SOJA",
                "hub_id": "sorriso_mt",
                "port_id": "BCR",
                "cbot_cents": 1180.0,
                "premium_cents": 50.0,
                "fx_rate": 5.4850,
                "freight_brl_ton": 275.0,  # Frete menor arco norte
                "volume_bags": 20000.0,
            },
        ]
    }
    res = client.post("/api/proposals/compare", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert "best_proposal" in data
    assert "proposals" in data
    assert len(data["proposals"]) == 2

    best = next(p for p in data["proposals"] if p["is_best"])
    worst = next(p for p in data["proposals"] if not p["is_best"])
    assert best["name"] == data["best_proposal"]
    assert best["spread_vs_best_brl_bag"] == 0.0
    assert worst["spread_vs_best_brl_bag"] < 0.0
    assert data["max_advantage_lot_brl"] > 0.0
