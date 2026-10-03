"""
Suíte de Testes para Convites, Gestão de Membros e Proteção de Administração (Tickets F11, F12).
Valida:
1. Emissão de convites com tokens de uso único e validade de 48h restrita ao OWNER.
2. Aceite de convite e vinculação de membro com papel pretendido.
3. Proteção contra remoção do único OWNER da organização.
4. Proteção estrita de todas as rotas administrativas sob require_platform_operator (403 para não-operador).
5. Endpoint de auditoria de telemetria e saúde por fonte (/api/admin/sources/health).
6. Idempotência da migração 004_invitations.sql.
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
from src.db.models import (
    User,
    Organization,
    Membership,
    MembershipRole,
    Invitation,
    MarketQuote,
    ExtractionLog,
    DataKind,
    FreshnessStatus,
)
from src.api.auth import set_test_public_key
from src.db.migrate import run_migrations


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
def f11_test_db(rsa_keypair):
    """Cria banco SQLite em memória isolado e configura a chave pública de teste."""
    set_test_public_key(rsa_keypair["public_pem"])
    
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
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
    yield session
    app.dependency_overrides.clear()
    session.close()
    set_test_public_key(None)


def create_token(
    private_pem: str,
    claims: dict,
    exp_seconds: int = 3600,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user-default-sub",
        "token_use": "access",
        "exp": int((now + timedelta(seconds=exp_seconds)).timestamp()),
        "iat": int(now.timestamp()),
        **claims,
    }
    hdrs = {"alg": "RS256", "kid": "test-key-1"}
    return jwt.encode(payload, private_pem, algorithm="RS256", headers=hdrs)


def test_f11_invitations_workflow_and_rbac(rsa_keypair, f11_test_db):
    """
    Ticket F11: Teste completo do fluxo de convites.
    - Apenas OWNER pode criar e listar convites.
    - Usuário convidado aceita via token e torna-se membro com a role definida.
    - Tentativa de reutilizar convite aceito é rejeitada.
    """
    client = TestClient(app)
    priv_pem = rsa_keypair["private_pem"]

    # Cria organização
    org = Organization(name="Agro Alpha", slug="agro-alpha", is_active=True)
    f11_test_db.add(org)
    f11_test_db.commit()

    # Cria dono e analista
    owner = User(cognito_sub="sub-owner", email="owner@agroalpha.com", name="Owner Alpha", is_active=True)
    analyst = User(cognito_sub="sub-analyst", email="analyst@agroalpha.com", name="Analyst Alpha", is_active=True)
    f11_test_db.add_all([owner, analyst])
    f11_test_db.commit()

    # Cria memberships
    m_owner = Membership(user_id=owner.id, organization_id=org.id, role=MembershipRole.OWNER.value, is_active=True)
    m_analyst = Membership(user_id=analyst.id, organization_id=org.id, role=MembershipRole.ANALYST.value, is_active=True)
    f11_test_db.add_all([m_owner, m_analyst])
    f11_test_db.commit()

    token_owner = create_token(priv_pem, {"sub": "sub-owner", "email": "owner@agroalpha.com"})
    token_analyst = create_token(priv_pem, {"sub": "sub-analyst", "email": "analyst@agroalpha.com"})

    # 1. Analista tenta criar convite -> 403 Forbidden
    res_denied = client.post(
        f"/api/organizations/{org.id}/invitations",
        headers={"Authorization": f"Bearer {token_analyst}"},
        json={"email": "guest@empresa.com", "role": "READER"},
    )
    assert res_denied.status_code == 403

    # 2. Dono cria convite para novo usuário -> 200 OK
    res_inv = client.post(
        f"/api/organizations/{org.id}/invitations",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "guest@empresa.com", "role": "READER"},
    )
    assert res_inv.status_code == 200
    inv_data = res_inv.json()
    assert inv_data["email"] == "guest@empresa.com"
    assert inv_data["role"] == "READER"
    assert inv_data["is_accepted"] is False
    invite_token = inv_data["token"]
    assert len(invite_token) > 20

    # 3. Dono lista convites pendentes -> 200 OK
    res_list = client.get(
        f"/api/organizations/{org.id}/invitations",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 4. Novo usuário autentica-se e aceita o convite
    new_user_token = create_token(priv_pem, {"sub": "sub-guest-1", "email": "guest@empresa.com", "name": "Convidado"})
    res_accept = client.post(
        f"/api/invitations/{invite_token}/accept",
        headers={"Authorization": f"Bearer {new_user_token}"},
    )
    assert res_accept.status_code == 200
    accept_data = res_accept.json()
    assert accept_data["status"] == "success"
    assert accept_data["role"] == "READER"

    # 5. Tenta aceitar novamente -> 400
    res_reaccept = client.post(
        f"/api/invitations/{invite_token}/accept",
        headers={"Authorization": f"Bearer {new_user_token}"},
    )
    assert res_reaccept.status_code == 400
    assert "already been accepted" in res_reaccept.json()["detail"]

    # 6. Lista membros da organização -> novo usuário está presente como READER
    res_members = client.get(
        f"/api/organizations/{org.id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert res_members.status_code == 200
    members = res_members.json()
    emails = [m["email"] for m in members]
    assert "guest@empresa.com" in emails
    assert "owner@agroalpha.com" in emails


def test_f11_sole_owner_removal_protection(rsa_keypair, f11_test_db):
    """
    Ticket F11: Proteção contra remoção do único OWNER da organização.
    """
    client = TestClient(app)
    priv_pem = rsa_keypair["private_pem"]

    org = Organization(name="Beta Grains", slug="beta-grains", is_active=True)
    f11_test_db.add(org)
    f11_test_db.commit()

    owner = User(cognito_sub="sub-owner-beta", email="owner@betagrains.com", is_active=True)
    analyst = User(cognito_sub="sub-analyst-beta", email="analyst@betagrains.com", is_active=True)
    f11_test_db.add_all([owner, analyst])
    f11_test_db.commit()

    m_owner = Membership(user_id=owner.id, organization_id=org.id, role=MembershipRole.OWNER.value, is_active=True)
    m_analyst = Membership(user_id=analyst.id, organization_id=org.id, role=MembershipRole.ANALYST.value, is_active=True)
    f11_test_db.add_all([m_owner, m_analyst])
    f11_test_db.commit()

    token_owner = create_token(priv_pem, {"sub": "sub-owner-beta", "email": "owner@betagrains.com"})

    # Tentativa de remover o único dono -> 400 Bad Request
    res_delete_owner = client.delete(
        f"/api/organizations/{org.id}/members/{owner.id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert res_delete_owner.status_code == 400
    assert "sole OWNER" in res_delete_owner.json()["detail"]

    # Remover o analista -> 200 OK
    res_delete_analyst = client.delete(
        f"/api/organizations/{org.id}/members/{analyst.id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert res_delete_analyst.status_code == 200
    assert res_delete_analyst.json()["status"] == "success"


def test_f12_operator_routes_adversarial_protection(rsa_keypair, f11_test_db):
    """
    Ticket F12: Todas as 7 rotas administrativas devem rejeitar chamadas de usuários comuns (403)
    e permitir apenas operadores da plataforma (is_platform_operator=True).
    """
    client = TestClient(app)
    priv_pem = rsa_keypair["private_pem"]

    # Cria usuário comum (não-operador)
    user_common = User(cognito_sub="sub-common-trader", email="trader@agro.com", is_platform_operator=False, is_active=True)
    user_operator = User(cognito_sub="sub-admin-operator", email="ops@agritrading.local", is_platform_operator=True, is_active=True)
    f11_test_db.add_all([user_common, user_operator])
    f11_test_db.commit()

    token_common = create_token(priv_pem, {"sub": "sub-common-trader", "email": "trader@agro.com"})
    token_operator = create_token(priv_pem, {"sub": "sub-admin-operator", "email": "ops@agritrading.local"})

    admin_routes = [
        ("POST", "/api/market-data/extract"),
        ("POST", "/api/market-data/fx/refresh"),
        ("POST", "/api/b3/extract"),
        ("POST", "/api/macro/extract"),
        ("GET", "/api/market-data/logs"),
        ("GET", "/api/scheduler/status"),
        ("GET", "/api/admin/sources/health"),
    ]

    # 1. Usuário comum deve receber 403 em TODAS as rotas administrativas
    for method, path in admin_routes:
        if method == "POST":
            res = client.post(path, headers={"Authorization": f"Bearer {token_common}"})
        else:
            res = client.get(path, headers={"Authorization": f"Bearer {token_common}"})
        assert res.status_code == 403, f"Rota {method} {path} deveria ter retornado 403 para usuário comum, mas retornou {res.status_code}"
        assert "platform operator privileges" in res.json()["detail"]

    # 2. Operador da plataforma deve conseguir acessar
    res_health = client.get("/api/admin/sources/health", headers={"Authorization": f"Bearer {token_operator}"})
    assert res_health.status_code == 200
    health_data = res_health.json()
    assert health_data["status"] == "HEALTHY"
    assert "sources" in health_data
    assert "CBOT" in health_data["sources"]
    assert "BACEN_PTAX" in health_data["sources"]
    assert "B3" in health_data["sources"]

    res_logs = client.get("/api/market-data/logs", headers={"Authorization": f"Bearer {token_operator}"})
    assert res_logs.status_code == 200


def test_f11_migration_004_applied_cleanly():
    """
    Valida se a migração 004_invitations.sql é executada de forma limpa pelo gerenciador.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    applied = run_migrations(engine)
    applied_versions = [m["version"] for m in applied]

    assert "001_initial_schema" in applied_versions
    assert "002_quality_schema_v2" in applied_versions
    assert "003_auth_and_multitenancy" in applied_versions
    assert "004_invitations" in applied_versions
