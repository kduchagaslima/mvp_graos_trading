"""
Suíte de Testes Automatizados para Emissão e Gestão de Boletas Formais
de Negociação de Compra de Grãos (Trade Tickets) com Amarração W3C PROV.
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
from src.db.models import User, Organization, Membership, MembershipRole, TradeTicket
from src.api.auth import set_test_public_key


@pytest.fixture(scope="session")
def rsa_keypair():
    """Gera par de chaves RSA em memória para assinar e validar tokens RS256 nos testes."""
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
    """Cria banco SQLite isolado com injeção segura de dependência no FastAPI."""
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


def test_create_and_list_trade_tickets(test_db_client):
    """Testa criação e listagem de boletas formais de negociação."""
    session = test_db_client["session"]
    client = test_db_client["client"]
    rsa = test_db_client["rsa"]

    # Criar Usuário e Organização
    user = User(cognito_sub="sub-trader-01", email="trader@agrocorp.com", name="Carlos Trader")
    session.add(user)
    session.flush()

    org = Organization(name="AgroCorp Trading", slug="agrocorp")
    session.add(org)
    session.flush()

    m = Membership(user_id=user.id, organization_id=org.id, role=MembershipRole.ANALYST.value)
    session.add(m)
    session.commit()

    headers = make_auth_header(rsa, sub="sub-trader-01", email="trader@agrocorp.com")

    payload = {
        "commodity": "SOJA",
        "crop_year": "2025/2026",
        "seller_name": "Fazenda Rio Grande (João Silveira)",
        "seller_document": "12.345.678/0001-90",
        "seller_farm": "Fazenda Rio Grande",
        "location_hub_id": "sorriso_mt",
        "destination_port_id": "STS",
        "quantity_bags": 5000.0,
        "price_per_bag_brl": 132.50,
        "payment_terms": "À vista contra entrega e classificação de grãos",
        "delivery_period": "Março/2026 - Imediato",
        "quality_specs": "Padrão Exportação ANEC: Umidade máx 14%, Impureza máx 1%, Avariados máx 8%",
        "parity_run_id": "run-test-w3c-prov-1234",
        "cbot_reference": 1185.25,
        "fx_reference": 5.4850,
        "freight_reference": 420.00,
        "antt_compliant": True,
        "notes": "Compra fechada direto com produtor.",
    }

    # 1. Criação da boleta
    res = client.post(f"/api/organizations/{org.id}/trade-tickets", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["ticket_number"].startswith("BOL-")
    assert data["commodity"] == "SOJA"
    assert data["seller_name"] == "Fazenda Rio Grande (João Silveira)"
    assert data["quantity_bags"] == 5000.0
    assert data["quantity_tons"] == 300.0  # 5000 * 0.06
    assert data["price_per_bag_brl"] == 132.50
    assert data["total_amount_brl"] == 662500.0  # 5000 * 132.50
    assert data["status"] == "CONFIRMED"
    assert data["decision_ready"] is True
    assert data["parity_run_id"] == "run-test-w3c-prov-1234"
    assert data["antt_compliant"] is True

    ticket_id = data["id"]

    # 2. Listagem de boletas da organização
    res_list = client.get(f"/api/organizations/{org.id}/trade-tickets", headers=headers)
    assert res_list.status_code == 200
    tickets = res_list.json()
    assert len(tickets) == 1
    assert tickets[0]["id"] == ticket_id

    # 3. Consulta individual da boleta
    res_get = client.get(f"/api/organizations/{org.id}/trade-tickets/{ticket_id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["ticket_number"] == data["ticket_number"]


def test_trade_ticket_rbac_and_multitenancy(test_db_client):
    """Garante controle RBAC (READER não cria boleta) e isolamento multi-tenant entre empresas."""
    session = test_db_client["session"]
    client = test_db_client["client"]
    rsa = test_db_client["rsa"]

    # Org 1: AgroCorp com 1 ANALYST e 1 READER
    org1 = Organization(name="AgroCorp", slug="agrocorp")
    session.add(org1)
    session.flush()

    user_analyst = User(cognito_sub="sub-analyst", email="analyst@agrocorp.com", name="Analyst")
    user_reader = User(cognito_sub="sub-reader", email="reader@agrocorp.com", name="Reader")
    session.add_all([user_analyst, user_reader])
    session.flush()

    session.add(Membership(user_id=user_analyst.id, organization_id=org1.id, role=MembershipRole.ANALYST.value))
    session.add(Membership(user_id=user_reader.id, organization_id=org1.id, role=MembershipRole.READER.value))

    # Org 2: Cooperativa Sul
    org2 = Organization(name="CoopSul", slug="coopsul")
    session.add(org2)
    session.flush()

    user_other = User(cognito_sub="sub-other", email="trader@coopsul.com", name="Other")
    session.add(user_other)
    session.flush()
    session.add(Membership(user_id=user_other.id, organization_id=org2.id, role=MembershipRole.ANALYST.value))
    session.commit()

    headers_reader = make_auth_header(rsa, sub="sub-reader", email="reader@agrocorp.com")
    headers_analyst = make_auth_header(rsa, sub="sub-analyst", email="analyst@agrocorp.com")
    headers_other = make_auth_header(rsa, sub="sub-other", email="trader@coopsul.com")

    payload = {
        "commodity": "MILHO",
        "crop_year": "2025/2026",
        "seller_name": "Produtor Teste",
        "location_hub_id": "rio_verde_go",
        "destination_port_id": "STS",
        "quantity_bags": 2000.0,
        "price_per_bag_brl": 62.00,
    }

    # Tentativa de criação por READER -> 403 Forbidden
    res_forbidden = client.post(f"/api/organizations/{org1.id}/trade-tickets", json=payload, headers=headers_reader)
    assert res_forbidden.status_code == 403

    # Criação por ANALYST -> 201 Created
    res_create = client.post(f"/api/organizations/{org1.id}/trade-tickets", json=payload, headers=headers_analyst)
    assert res_create.status_code == 201
    ticket_id = res_create.json()["id"]

    # Usuário de Org 2 tentando acessar boleta da Org 1 -> 403 ou 404 (não pertence à organização)
    res_leak = client.get(f"/api/organizations/{org1.id}/trade-tickets/{ticket_id}", headers=headers_other)
    assert res_leak.status_code == 403

    # Exclusão por ANALYST
    res_del = client.delete(f"/api/organizations/{org1.id}/trade-tickets/{ticket_id}", headers=headers_analyst)
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # Verificação de exclusão
    res_check = client.get(f"/api/organizations/{org1.id}/trade-tickets/{ticket_id}", headers=headers_analyst)
    assert res_check.status_code == 404
