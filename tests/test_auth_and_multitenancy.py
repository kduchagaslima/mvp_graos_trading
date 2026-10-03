"""
Suíte de Testes para Autenticação Cognito, Multi-tenancy e RBAC (Tickets F08, F09, F10).
Valida:
1. Validação estrita de JWT RS256 e rejeição de ID Token (apenas Access Token permitido).
2. Provisionamento Just-In-Time (JIT) e bloqueio de usuários inativos no banco.
3. Segregação de tenants: usuário de uma organização não enxerga dados de outra.
4. Hierarquia de papéis RBAC (OWNER > ANALYST > READER) em perfis de custos privados.
5. Permissões de operador de plataforma (is_platform_operator).
6. Aplicação da migração 003_auth_and_multitenancy.sql.
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
from src.db.models import User, Organization, Membership, MembershipRole, CostProfile
from src.api.auth import set_test_public_key, require_platform_operator
from src.db.migrate import run_migrations, get_applied_migrations


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
def auth_test_db(rsa_keypair):
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
    headers: dict = None,
    exp_seconds: int = 3600,
    algorithm: str = "RS256",
) -> str:
    """Helper para gerar tokens JWT assinados com expiração controlada."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user-sub-default",
        "token_use": "access",
        "exp": int((now + timedelta(seconds=exp_seconds)).timestamp()),
        "iat": int(now.timestamp()),
        **claims,
    }
    hdrs = {"alg": algorithm, "kid": "test-key-1"}
    if headers:
        hdrs.update(headers)
    return jwt.encode(payload, private_pem, algorithm=algorithm, headers=hdrs)


def test_jwt_validation_strict_rs256_and_access_token(rsa_keypair, auth_test_db):
    """
    Ticket F08/F09: Validação estrita de token RS256.
    Rejeita ID token, algoritmos não-RS256, tokens expirados e assinaturas inválidas.
    """
    client = TestClient(app)
    priv_pem = rsa_keypair["private_pem"]

    # 1. Sem cabeçalho Authorization -> 401
    res = client.get("/api/me")
    assert res.status_code == 401
    assert "Missing Authorization header" in res.json()["detail"]

    # 2. Formato inválido do cabeçalho -> 401
    res = client.get("/api/me", headers={"Authorization": "InvalidTokenNoBearer"})
    assert res.status_code == 401
    assert "Expected 'Bearer <token>'" in res.json()["detail"]

    # 3. ID Token rejeitado explicitamente (token_use == 'id') -> 401
    id_token = create_token(priv_pem, {"sub": "user-id-test", "token_use": "id"})
    res = client.get("/api/me", headers={"Authorization": f"Bearer {id_token}"})
    assert res.status_code == 401
    assert "ID token is not allowed for API authentication" in res.json()["detail"]

    # 4. Token com algoritmo não permitido (HS256) -> 401
    hs256_token = jwt.encode(
        {"sub": "hs-user", "token_use": "access"},
        "super-secret-symmetric-key-at-least-32-bytes-long",
        algorithm="HS256",
    )
    res = client.get("/api/me", headers={"Authorization": f"Bearer {hs256_token}"})
    assert res.status_code == 401
    assert "Only RS256 is permitted" in res.json()["detail"]

    # 5. Token expirado -> 401
    expired_token = create_token(priv_pem, {"sub": "user-expired"}, exp_seconds=-60)
    res = client.get("/api/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "Token has expired" in res.json()["detail"]

    # 6. Access Token RS256 válido -> 200
    valid_token = create_token(
        priv_pem,
        {"sub": "user-valid-1", "email": "valid1@trading.com", "name": "Operador Valido"},
    )
    res = client.get("/api/me", headers={"Authorization": f"Bearer {valid_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["cognito_sub"] == "user-valid-1"
    assert data["email"] == "valid1@trading.com"
    assert data["is_active"] is True


def test_user_jit_provisioning_and_immediate_deactivation(rsa_keypair, auth_test_db):
    """
    Ticket F09: Provisionamento Just-in-Time (JIT) na primeira autenticação e
    bloqueio imediato na requisição seguinte se usuário desativado no banco.
    """
    client = TestClient(app)
    priv_pem = rsa_keypair["private_pem"]
    sub = "cognito-jit-user-999"
    token = create_token(priv_pem, {"sub": sub, "email": "jit@empresa.com", "name": "JIT User"})

    # Primeira requisição: provisiona usuário JIT
    res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    user_data = res.json()
    assert user_data["email"] == "jit@empresa.com"
    user_id = user_data["id"]

    # Verifica se usuário existe no banco
    user_in_db = auth_test_db.query(User).filter(User.id == user_id).first()
    assert user_in_db is not None
    assert user_in_db.is_active is True

    # Desativa o usuário no banco (desligamento imediato)
    user_in_db.is_active = False
    auth_test_db.commit()

    # Próxima requisição com o MESMO token ainda válido criptograficamente DEVE ser barrada
    res_blocked = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res_blocked.status_code == 403
    assert "deactivated" in res_blocked.json()["detail"]


def test_multitenant_cost_profile_isolation_and_rbac(rsa_keypair, auth_test_db):
    """
    Ticket F10: Segregação completa entre empresas e RBAC estrito (OWNER, ANALYST, READER).
    - Usuário de Org 1 não pode acessar Org 2.
    - READER pode visualizar mas não pode criar/alterar.
    - ANALYST / OWNER podem criar e alterar.
    """
    client = TestClient(app)
    priv_pem = rsa_keypair["private_pem"]

    # Cria Organizações
    org1 = Organization(name="Cerrado Grãos Ltda", slug="cerrado-graos", is_active=True)
    org2 = Organization(name="Sul Trading S/A", slug="sul-trading", is_active=True)
    auth_test_db.add_all([org1, org2])
    auth_test_db.commit()
    auth_test_db.refresh(org1)
    auth_test_db.refresh(org2)

    # Cria Usuários
    user_owner_org1 = User(cognito_sub="sub-owner-org1", email="owner1@cerrado.com", name="Owner 1", is_active=True)
    user_reader_org1 = User(cognito_sub="sub-reader-org1", email="reader1@cerrado.com", name="Reader 1", is_active=True)
    user_org2 = User(cognito_sub="sub-user-org2", email="user2@sultrading.com", name="User Org 2", is_active=True)
    auth_test_db.add_all([user_owner_org1, user_reader_org1, user_org2])
    auth_test_db.commit()

    # Cria Memberships
    m_owner = Membership(user_id=user_owner_org1.id, organization_id=org1.id, role=MembershipRole.OWNER.value, is_active=True)
    m_reader = Membership(user_id=user_reader_org1.id, organization_id=org1.id, role=MembershipRole.READER.value, is_active=True)
    m_org2 = Membership(user_id=user_org2.id, organization_id=org2.id, role=MembershipRole.OWNER.value, is_active=True)
    auth_test_db.add_all([m_owner, m_reader, m_org2])
    auth_test_db.commit()

    # Gera Tokens
    token_owner1 = create_token(priv_pem, {"sub": "sub-owner-org1", "email": "owner1@cerrado.com"})
    token_reader1 = create_token(priv_pem, {"sub": "sub-reader-org1", "email": "reader1@cerrado.com"})
    token_org2 = create_token(priv_pem, {"sub": "sub-user-org2", "email": "user2@sultrading.com"})

    # 1. TESTE DE ISOLAMENTO CROSS-TENANT:
    # Usuário de Org 2 tenta acessar perfil de Org 1 -> 403 Forbidden
    res_cross = client.get(
        f"/api/organizations/{org1.id}/cost-profiles",
        headers={"Authorization": f"Bearer {token_org2}"},
    )
    assert res_cross.status_code == 403
    assert "Access denied: user does not have active membership" in res_cross.json()["detail"]

    # 2. TESTE RBAC - READER (Org 1):
    # Reader pode ler a lista (vazia inicialmente) -> 200
    res_list = client.get(
        f"/api/organizations/{org1.id}/cost-profiles",
        headers={"Authorization": f"Bearer {token_reader1}"},
    )
    assert res_list.status_code == 200
    assert res_list.json() == []

    # Reader tenta criar perfil de custo -> 403 (exige ANALYST ou superior)
    res_create_denied = client.post(
        f"/api/organizations/{org1.id}/cost-profiles",
        headers={"Authorization": f"Bearer {token_reader1}"},
        json={
            "name": "Perfil Exportação",
            "brokerage_margin_usd_ton": 3.5,
            "brokerage_fee_brl_bag": 0.5,
            "brokerage_payer": "TRADING",
            "default_funrural_pct": 1.5,
            "default_shrinkage_loss_pct": 0.3,
        },
    )
    assert res_create_denied.status_code == 403
    assert "does not meet required 'ANALYST'" in res_create_denied.json()["detail"]

    # 3. TESTE RBAC - OWNER (Org 1):
    # Owner cria perfil de custo -> 200
    res_create_ok = client.post(
        f"/api/organizations/{org1.id}/cost-profiles",
        headers={"Authorization": f"Bearer {token_owner1}"},
        json={
            "name": "Perfil Exportação",
            "brokerage_margin_usd_ton": 3.5,
            "brokerage_fee_brl_bag": 0.5,
            "brokerage_payer": "TRADING",
            "default_funrural_pct": 1.5,
            "default_shrinkage_loss_pct": 0.3,
        },
    )
    assert res_create_ok.status_code == 200
    profile_data = res_create_ok.json()
    profile_id = profile_data["id"]
    assert profile_data["organization_id"] == org1.id
    assert profile_data["brokerage_margin_usd_ton"] == 3.5

    # 4. Reader agora consegue visualizar o perfil criado -> 200
    res_get_profile = client.get(
        f"/api/organizations/{org1.id}/cost-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token_reader1}"},
    )
    assert res_get_profile.status_code == 200
    assert res_get_profile.json()["name"] == "Perfil Exportação"

    # Reader tenta atualizar o perfil -> 403
    res_update_denied = client.put(
        f"/api/organizations/{org1.id}/cost-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token_reader1}"},
        json={"brokerage_margin_usd_ton": 4.0},
    )
    assert res_update_denied.status_code == 403

    # Owner atualiza o perfil -> 200
    res_update_ok = client.put(
        f"/api/organizations/{org1.id}/cost-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token_owner1}"},
        json={"brokerage_margin_usd_ton": 4.0},
    )
    assert res_update_ok.status_code == 200
    assert res_update_ok.json()["brokerage_margin_usd_ton"] == 4.0

    # 5. Usuário de Org 2 NÃO consegue ler o perfil de Org 1 pelo ID -> 403
    res_cross_get = client.get(
        f"/api/organizations/{org1.id}/cost-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token_org2}"},
    )
    assert res_cross_get.status_code == 403


def test_platform_operator_privileges(auth_test_db):
    """
    Ticket F09: Distinção estrita entre membro de organização e operador da plataforma.
    """
    user_regular = User(cognito_sub="sub-regular", email="reg@test.com", is_platform_operator=False)
    user_op = User(cognito_sub="sub-op", email="op@platform.com", is_platform_operator=True)
    auth_test_db.add_all([user_regular, user_op])
    auth_test_db.commit()

    # Valida exceção com require_platform_operator
    with pytest.raises(Exception) as exc_info:
        require_platform_operator(user_regular)
    assert "platform operator privileges" in str(exc_info.value.detail)

    # Operador da plataforma deve passar
    res_op = require_platform_operator(user_op)
    assert res_op.is_platform_operator is True


def test_migration_003_applied_cleanly():
    """
    Valida se a migração 003_auth_and_multitenancy.sql é executada de forma limpa e idempotente.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    applied = run_migrations(engine)
    applied_versions = [m["version"] for m in applied]

    assert "001_initial_schema" in applied_versions
    assert "002_quality_schema_v2" in applied_versions
    assert "003_auth_and_multitenancy" in applied_versions

    # Segunda execução não deve re-aplicar
    applied_again = run_migrations(engine)
    assert len(applied_again) == 0
