"""
Suíte de Testes Automatizados para Onboarding Guiado com Dados Demo Pré-populados (Atividade 3).
Valida criação de conta com portfólio completo pré-carregado (Trial 14 dias),
endpoint sob demanda /seed-demo e segregação de tenant.
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
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
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


def make_auth_header(rsa_keypair, sub: str, email: str = "trader@agritrading.local"):
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": sub,
            "email": email,
            "token_use": "access",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
        },
        rsa_keypair["private_pem"],
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    return {"Authorization": f"Bearer {token}"}


def test_organization_creation_with_demo_seed(test_db_client):
    """Valida cadastro com seed_demo_data=True gerando portfólio completo de demonstração."""
    client = test_db_client["client"]
    rsa = test_db_client["rsa"]
    headers = make_auth_header(rsa, sub="trial-user-1", email="trial@novatrading.com")

    # 1. Cria organização com dados demo ativados
    res = client.post(
        "/api/organizations",
        json={"name": "Nova Grãos Trial SA", "seed_demo_data": True},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "created"
    assert data["demo_seeded"] is True
    summary = data["demo_summary"]
    assert summary["freight_contracts_count"] == 4
    assert summary["scenarios_count"] == 3
    assert summary["trade_tickets_count"] == 2
    assert summary["market_alerts_count"] == 4

    org_id = data["organization"]["id"]

    # 2. Confirma existência dos 4 contratos privados de frete
    res_contracts = client.get(f"/api/organizations/{org_id}/freight-contracts", headers=headers)
    assert res_contracts.status_code == 200
    contracts = res_contracts.json()
    assert len(contracts) == 4
    dest_ids = [c["destination_id"] for c in contracts]
    assert "STS" in dest_ids
    assert "IND_LRV_FS" in dest_ids
    assert "IND_ROO_BUNGE" in dest_ids

    # 3. Confirma existência dos 3 cenários de paridade salvos
    res_scenarios = client.get(f"/api/organizations/{org_id}/scenarios", headers=headers)
    assert res_scenarios.status_code == 200
    scenarios = res_scenarios.json()
    assert len(scenarios) == 3

    # 4. Confirma existência das 2 boletas formais de compra (Trade Tickets)
    res_tickets = client.get(f"/api/organizations/{org_id}/trade-tickets", headers=headers)
    assert res_tickets.status_code == 200
    tickets = res_tickets.json()
    assert len(tickets) == 2
    assert tickets[0]["status"] == "CONFIRMED"
    assert tickets[0]["decision_ready"] is True

    # 5. Confirma existência dos 4 alertas de mercado
    res_alerts = client.get(f"/api/organizations/{org_id}/alerts", headers=headers)
    assert res_alerts.status_code == 200
    alerts = res_alerts.json()
    assert len(alerts) == 4
    assert any(a["is_triggered"] for a in alerts)


def test_organization_creation_without_demo_and_manual_seed(test_db_client):
    """Valida cadastro limpo (seed_demo_data=False) e posterior ativação via POST /seed-demo."""
    client = test_db_client["client"]
    rsa = test_db_client["rsa"]
    headers = make_auth_header(rsa, sub="trial-user-2", email="limpo@trading.com")

    # 1. Cria organização sem seed demo
    res = client.post(
        "/api/organizations",
        json={"name": "Empresa Limpa", "seed_demo_data": False},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["demo_seeded"] is False
    org_id = data["organization"]["id"]

    # Verifica que não há cenários nem alertas
    res_scen = client.get(f"/api/organizations/{org_id}/scenarios", headers=headers)
    assert len(res_scen.json()) == 0
    res_al = client.get(f"/api/organizations/{org_id}/alerts", headers=headers)
    assert len(res_al.json()) == 0

    # 2. Trader decide carregar os dados demo posteriormente pelo botão /seed-demo
    res_seed = client.post(f"/api/organizations/{org_id}/seed-demo", headers=headers)
    assert res_seed.status_code == 200
    assert res_seed.json()["status"] == "seeded"

    # Agora deve ter os dados populados
    res_scen_after = client.get(f"/api/organizations/{org_id}/scenarios", headers=headers)
    assert len(res_scen_after.json()) == 3
    res_al_after = client.get(f"/api/organizations/{org_id}/alerts", headers=headers)
    assert len(res_al_after.json()) == 4


def test_seed_demo_endpoint_rbac(test_db_client):
    """Garante que apenas OWNER possa disparar o seed de dados demo na organização."""
    client = test_db_client["client"]
    db = test_db_client["session"]
    rsa = test_db_client["rsa"]

    u_reader = User(cognito_sub="sub-reader-seed", email="reader@seed.local", name="Seed Reader")
    org = Organization(name="Seed Test Org", slug="seed-test", is_active=True)
    db.add_all([u_reader, org])
    db.commit()

    db.add(Membership(user_id=u_reader.id, organization_id=org.id, role=MembershipRole.READER.value, is_active=True))
    db.commit()

    headers_reader = make_auth_header(rsa, sub="sub-reader-seed", email="reader@seed.local")

    # READER não pode popular seed
    res = client.post(f"/api/organizations/{org.id}/seed-demo", headers=headers_reader)
    assert res.status_code == 403
