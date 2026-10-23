"""
Suíte de Testes Automatizados para Alertas de Mercado e Metas de Preço (Atividade 1).
Valida CRUD, RBAC, isolamento multi-tenant e motor de avaliação de gatilhos em tempo real.
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
from src.db.models import User, Organization, Membership, MembershipRole, MarketAlert
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


def test_market_alert_crud_lifecycle(test_db_client):
    """Valida o ciclo de vida completo de cadastro, listagem, atualização e deleção de alertas."""
    client = test_db_client["client"]
    db = test_db_client["session"]
    rsa = test_db_client["rsa"]

    owner = User(cognito_sub="user-owner-alerts", email="owner@alerts.local", name="Alerts Owner")
    org = Organization(name="Trading Alerts SA", slug="trading-alerts", is_active=True)
    db.add_all([owner, org])
    db.commit()

    m_owner = Membership(user_id=owner.id, organization_id=org.id, role=MembershipRole.OWNER.value, is_active=True)
    db.add(m_owner)
    db.commit()

    headers = make_auth_header(rsa, sub="user-owner-alerts", email="owner@alerts.local")

    # 1. Cria alerta
    payload = {
        "name": "Meta Soja Sorriso > R$ 130/sc",
        "alert_type": "PARITY_ABOVE",
        "commodity": "SOJA",
        "hub_id": "sorriso_mt",
        "port_id": "STS",
        "target_value": 130.0,
        "notification_channel": "IN_APP",
        "notes": "Disparar ordens de compra quando atingir 130",
    }
    res_create = client.post(f"/api/organizations/{org.id}/alerts", json=payload, headers=headers)
    assert res_create.status_code == 201
    alert_data = res_create.json()
    assert alert_data["id"] is not None
    assert alert_data["name"] == "Meta Soja Sorriso > R$ 130/sc"
    assert alert_data["target_value"] == 130.0
    assert alert_data["is_triggered"] is False
    assert alert_data["trigger_count"] == 0

    alert_id = alert_data["id"]

    # 2. Lista alertas
    res_list = client.get(f"/api/organizations/{org.id}/alerts", headers=headers)
    assert res_list.status_code == 200
    alerts = res_list.json()
    assert len(alerts) == 1
    assert alerts[0]["id"] == alert_id

    # 3. Atualiza alerta
    update_payload = {
        "name": "Meta Soja Sorriso > R$ 132/sc",
        "target_value": 132.0,
        "is_active": True,
        "notes": "Atualizado para R$ 132",
    }
    res_upd = client.put(f"/api/organizations/{org.id}/alerts/{alert_id}", json=update_payload, headers=headers)
    assert res_upd.status_code == 200
    assert res_upd.json()["target_value"] == 132.0
    assert res_upd.json()["name"] == "Meta Soja Sorriso > R$ 132/sc"

    # 4. Reset do status do alerta
    res_reset = client.post(f"/api/organizations/{org.id}/alerts/{alert_id}/reset", headers=headers)
    assert res_reset.status_code == 200
    assert res_reset.json()["is_triggered"] is False

    # 5. Remove alerta
    res_del = client.delete(f"/api/organizations/{org.id}/alerts/{alert_id}", headers=headers)
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # 6. Verifica remoção
    res_empty = client.get(f"/api/organizations/{org.id}/alerts", headers=headers)
    assert len(res_empty.json()) == 0


def test_market_alert_evaluation_triggers(test_db_client):
    """Valida a avaliação do motor de alertas contra valores simulados e o disparo correto dos gatilhos."""
    client = test_db_client["client"]
    db = test_db_client["session"]
    rsa = test_db_client["rsa"]

    user = User(cognito_sub="eval-trader", email="eval@trading.local", name="Trader Evaluator")
    org = Organization(name="Trading Evaluator", slug="trading-eval", is_active=True)
    db.add_all([user, org])
    db.commit()

    db.add(Membership(user_id=user.id, organization_id=org.id, role=MembershipRole.ANALYST.value, is_active=True))
    db.commit()

    headers = make_auth_header(rsa, sub="eval-trader", email="eval@trading.local")

    # Cadastra 3 regras de monitoramento
    client.post(
        f"/api/organizations/{org.id}/alerts",
        json={
            "name": "Paridade Alta",
            "alert_type": "PARITY_ABOVE",
            "commodity": "SOJA",
            "hub_id": "sorriso_mt",
            "port_id": "STS",
            "target_value": 125.0,
        },
        headers=headers,
    )
    client.post(
        f"/api/organizations/{org.id}/alerts",
        json={
            "name": "Paridade Baixa Stop",
            "alert_type": "PARITY_BELOW",
            "commodity": "SOJA",
            "hub_id": "sorriso_mt",
            "port_id": "STS",
            "target_value": 115.0,
        },
        headers=headers,
    )
    client.post(
        f"/api/organizations/{org.id}/alerts",
        json={
            "name": "CBOT Rompimento",
            "alert_type": "CBOT_ABOVE",
            "commodity": "SOJA",
            "target_value": 1100.0,
        },
        headers=headers,
    )

    # 1. Avalia com paridade = 126.0 (deve disparar apenas Paridade Alta)
    eval_res = client.post(
        f"/api/organizations/{org.id}/alerts/evaluate",
        json={
            "commodity": "SOJA",
            "hub_id": "sorriso_mt",
            "port_id": "STS",
            "parity_brl_bag": 126.0,
            "cbot_cents": 1050.0,
        },
        headers=headers,
    )
    assert eval_res.status_code == 200
    data = eval_res.json()
    assert data["total_active_alerts"] == 3
    assert data["total_triggered"] == 1
    assert len(data["newly_triggered"]) == 1
    assert data["newly_triggered"][0]["name"] == "Paridade Alta"
    assert data["newly_triggered"][0]["is_triggered"] is True
    assert data["newly_triggered"][0]["trigger_count"] == 1

    # 2. Avalia com paridade = 110.0 (deve disparar Paridade Baixa Stop)
    eval_res_2 = client.post(
        f"/api/organizations/{org.id}/alerts/evaluate",
        json={
            "commodity": "SOJA",
            "hub_id": "sorriso_mt",
            "port_id": "STS",
            "parity_brl_bag": 110.0,
            "cbot_cents": 1050.0,
        },
        headers=headers,
    )
    assert eval_res_2.status_code == 200
    data_2 = eval_res_2.json()
    assert data_2["total_triggered"] == 2
    assert len(data_2["newly_triggered"]) == 1
    assert data_2["newly_triggered"][0]["name"] == "Paridade Baixa Stop"


def test_market_alert_rbac_and_tenant_isolation(test_db_client):
    """Valida permissões por papel (READER, ANALYST, OWNER) e isolamento estrito entre tenants."""
    client = test_db_client["client"]
    db = test_db_client["session"]
    rsa = test_db_client["rsa"]

    u_reader = User(cognito_sub="sub-reader-alerts", email="reader@tenant1.local", name="Tenant1 Reader")
    u_analyst = User(cognito_sub="sub-analyst-alerts", email="analyst@tenant1.local", name="Tenant1 Analyst")
    u_other = User(cognito_sub="sub-other-tenant", email="other@tenant2.local", name="Tenant2 Trader")

    org1 = Organization(name="Tenant 1 Trading", slug="tenant-1", is_active=True)
    org2 = Organization(name="Tenant 2 Trading", slug="tenant-2", is_active=True)
    db.add_all([u_reader, u_analyst, u_other, org1, org2])
    db.commit()

    db.add_all([
        Membership(user_id=u_reader.id, organization_id=org1.id, role=MembershipRole.READER.value, is_active=True),
        Membership(user_id=u_analyst.id, organization_id=org1.id, role=MembershipRole.ANALYST.value, is_active=True),
        Membership(user_id=u_other.id, organization_id=org2.id, role=MembershipRole.OWNER.value, is_active=True),
    ])
    db.commit()

    headers_reader = make_auth_header(rsa, sub="sub-reader-alerts", email="reader@tenant1.local")
    headers_analyst = make_auth_header(rsa, sub="sub-analyst-alerts", email="analyst@tenant1.local")
    headers_other = make_auth_header(rsa, sub="sub-other-tenant", email="other@tenant2.local")

    alert_payload = {
        "name": "Alerta Confidencial Org1",
        "alert_type": "PARITY_ABOVE",
        "commodity": "SOJA",
        "target_value": 135.0,
    }

    # 1. READER tentando criar alerta -> 403 Forbidden
    res_forbidden = client.post(f"/api/organizations/{org1.id}/alerts", json=alert_payload, headers=headers_reader)
    assert res_forbidden.status_code == 403

    # 2. ANALYST cria alerta -> 201 Created
    res_create = client.post(f"/api/organizations/{org1.id}/alerts", json=alert_payload, headers=headers_analyst)
    assert res_create.status_code == 201
    alert_id = res_create.json()["id"]

    # 3. Usuário de outra organização (Tenant 2) tentando ler alertas do Org1 -> 403 Forbidden
    res_leak = client.get(f"/api/organizations/{org1.id}/alerts", headers=headers_other)
    assert res_leak.status_code == 403

    # 4. Usuário de outra organização tentando deletar alerta do Org1 -> 403 Forbidden
    res_del_cross = client.delete(f"/api/organizations/{org1.id}/alerts/{alert_id}", headers=headers_other)
    assert res_del_cross.status_code == 403
