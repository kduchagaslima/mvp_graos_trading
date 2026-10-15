"""
Suíte de Testes Automatizados para Piso Mínimo ANTT (Item 1)
e Contratos Privados de Frete da Trading (Item 3).
"""

from datetime import date, datetime, timezone, timedelta
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
from src.db.models import User, Organization, Membership, MembershipRole, CompanyFreightContract
from src.api.auth import set_test_public_key
from src.services.antt_freight import ANTTFreightService, ANTT_COEFFICIENTS
from src.services.market_data import market_service


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
    payload = {
        "sub": sub,
        "email": email,
        "token_use": "access",
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "iat": int(now.timestamp()),
    }
    token = jwt.encode(payload, rsa_keypair["private_pem"], algorithm="RS256", headers={"kid": "test-key-1"})
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# TESTES DO PISO MÍNIMO ANTT (ITEM 1)
# ==============================================================================

def test_antt_calculate_floor_rate_formulas():
    """
    Valida a aplicação exata das fórmulas e coeficientes regulatórios da ANTT
    para Granel Sólido (Resolução nº 5.867/2020 e Lei nº 13.703/2018).
    """
    dist_km = 1000

    # 1. Bitrem 7 Eixos (37 toneladas úteis)
    bitrem = ANTTFreightService.calculate_floor_rate(dist_km, vehicle_type="7_EIXOS_BITREM")
    expected_trip_7 = (5.8504 * 1000) + 482.15  # 6332.55
    expected_floor_7_ton = round(expected_trip_7 / 37.0, 2)  # 171.15
    assert bitrem["vehicle_type"] == "7_EIXOS_BITREM"
    assert bitrem["axles"] == 7
    assert bitrem["payload_tons"] == 37.0
    assert bitrem["trip_total_minimum_brl"] == round(expected_trip_7, 2)
    assert bitrem["floor_rate_brl_ton"] == expected_floor_7_ton
    assert bitrem["floor_rate_brl_bag"] == round(expected_floor_7_ton * 0.06, 2)
    assert "13.703/2018" in bitrem["legal_basis"]

    # 2. Rodotrem 9 Eixos (49 toneladas úteis)
    rodotrem = ANTTFreightService.calculate_floor_rate(dist_km, vehicle_type="9_EIXOS_RODOTREM")
    expected_trip_9 = (7.1245 * 1000) + 584.30  # 7708.80
    expected_floor_9_ton = round(expected_trip_9 / 49.0, 2)  # 157.32
    assert rodotrem["vehicle_type"] == "9_EIXOS_RODOTREM"
    assert rodotrem["axles"] == 9
    assert rodotrem["payload_tons"] == 49.0
    assert rodotrem["trip_total_minimum_brl"] == round(expected_trip_9, 2)
    assert rodotrem["floor_rate_brl_ton"] == expected_floor_9_ton
    assert rodotrem["floor_rate_brl_bag"] == round(expected_floor_9_ton * 0.06, 2)

    # 3. Fallback para veículo desconhecido usa 9 eixos como padrão
    fallback = ANTTFreightService.calculate_floor_rate(dist_km, vehicle_type="VEICULO_DESCONHECIDO")
    assert fallback["axles"] == 9
    assert fallback["floor_rate_brl_ton"] == expected_floor_9_ton


def test_antt_corridors_compliance_summary(test_db_client):
    """
    Valida a matriz de conformidade regulatória para todos os corredores cadastrados.
    """
    summary = ANTTFreightService.get_corridors_compliance_summary(db=test_db_client["session"])
    assert len(summary) >= 10

    for item in summary:
        assert "origin_id" in item
        assert "destination_id" in item
        assert "distance_km" in item
        assert item["distance_km"] > 0
        assert "market_freight_brl_ton" in item
        assert "antt_floor_7_axles_brl_ton" in item
        assert "antt_floor_9_axles_brl_ton" in item
        assert "compliance_status" in item
        assert item["compliance_status"] in ["ABOVE_FLOOR", "BELOW_FLOOR"]
        assert "spread_vs_floor_brl_ton" in item
        assert round(item["market_freight_brl_ton"] - item["antt_floor_9_axles_brl_ton"], 2) == item["spread_vs_floor_brl_ton"]


def test_api_antt_floor_endpoint(test_db_client):
    """
    Valida a resposta do endpoint GET /api/freight/antt-floor.
    """
    client = test_db_client["client"]
    res = client.get("/api/freight/antt-floor")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 10

    sorriso_sts = next((x for x in data if x["origin_id"] == "sorriso_mt" and x["destination_id"] == "STS"), None)
    assert sorriso_sts is not None
    assert sorriso_sts["distance_km"] == 2150
    assert sorriso_sts["market_freight_brl_ton"] == 420.0
    assert sorriso_sts["antt_floor_9_axles_brl_ton"] > 0


def test_api_freight_routes_includes_antt_fields(test_db_client):
    """
    Valida que o endpoint GET /api/freight/routes inclui métricas de conformidade ANTT.
    """
    client = test_db_client["client"]
    res = client.get("/api/freight/routes")
    assert res.status_code == 200
    routes = res.json()
    assert len(routes) > 0

    route = routes[0]
    assert "antt_floor_brl_ton" in route
    assert "antt_floor_brl_bag" in route
    assert "antt_compliance_status" in route
    assert "antt_spread_brl_ton" in route
    assert route["antt_compliance_status"] in ["ABOVE_FLOOR", "BELOW_FLOOR"]


# ==============================================================================
# TESTES DE CONTRATOS PRIVADOS DE FRETE DA TRADING (ITEM 3)
# ==============================================================================

def test_company_freight_contracts_crud_and_multitenancy(test_db_client):
    """
    Valida o ciclo de vida completo de Contratos Privados de Frete com segregação
    multi-tenant estrita entre organizações e verificação RBAC.
    """
    db = test_db_client["session"]
    client = test_db_client["client"]
    rsa = test_db_client["rsa"]

    # Cria Organização 1 (Trading Alfa) e Usuário 1 (Owner)
    org1 = Organization(name="Trading Alfa S/A", slug="trading-alfa", is_active=True)
    user1 = User(cognito_sub="sub-trader-1", email="trader1@alfa.com", name="Trader Alfa", is_active=True)
    db.add_all([org1, user1])
    db.commit()
    m1 = Membership(user_id=user1.id, organization_id=org1.id, role=MembershipRole.OWNER.value, is_active=True)
    db.add(m1)

    # Cria Organização 2 (Trading Beta) e Usuário 2 (Owner)
    org2 = Organization(name="Trading Beta S/A", slug="trading-beta", is_active=True)
    user2 = User(cognito_sub="sub-trader-2", email="trader2@beta.com", name="Trader Beta", is_active=True)
    db.add_all([org2, user2])
    db.commit()
    m2 = Membership(user_id=user2.id, organization_id=org2.id, role=MembershipRole.OWNER.value, is_active=True)
    db.add(m2)
    db.commit()

    auth1 = make_auth_header(rsa, sub="sub-trader-1", email="trader1@alfa.com")
    auth2 = make_auth_header(rsa, sub="sub-trader-2", email="trader2@beta.com")

    # 1. Usuário 1 cadastra contrato privado para Sorriso -> Santos na Org 1
    create_payload = {
        "origin_id": "sorriso_mt",
        "destination_id": "STS",
        "carrier_name": "TransGrãos Logística",
        "contract_code": "TG-2026-001",
        "freight_brl_ton": 385.50,
        "volume_contracted_tons": 50000.0,
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
        "is_active": True,
        "notes": "Acordo anual de volume para safra de soja",
    }
    res_create = client.post(
        f"/api/organizations/{org1.id}/freight-contracts",
        json=create_payload,
        headers=auth1,
    )
    assert res_create.status_code == 200
    contract_data = res_create.json()
    contract_id = contract_data["id"]
    assert contract_data["carrier_name"] == "TransGrãos Logística"
    assert contract_data["freight_brl_ton"] == 385.50
    assert contract_data["origin_id"] == "sorriso_mt"
    assert contract_data["destination_id"] == "STS"

    # 2. Usuário 1 lista contratos da Org 1
    res_list = client.get(f"/api/organizations/{org1.id}/freight-contracts", headers=auth1)
    assert res_list.status_code == 200
    contracts_list = res_list.json()
    assert len(contracts_list) == 1
    assert contracts_list[0]["contract_code"] == "TG-2026-001"

    # 3. Segregação de Tenant: Usuário 2 não tem permissão para visualizar contratos da Org 1
    res_cross_list = client.get(f"/api/organizations/{org1.id}/freight-contracts", headers=auth2)
    assert res_cross_list.status_code == 403

    # 4. Usuário 2 não pode deletar contratos da Org 1
    res_cross_delete = client.delete(
        f"/api/organizations/{org1.id}/freight-contracts/{contract_id}",
        headers=auth2,
    )
    assert res_cross_delete.status_code == 403

    # 5. Batch Upload na Org 1 (múltiplas rotas)
    batch_payload = {
        "contracts": [
            {
                "origin_id": "sorriso_mt",
                "destination_id": "BCR",
                "carrier_name": "Norte Transportes",
                "contract_code": "NT-2026-042",
                "freight_brl_ton": 330.00,
                "volume_contracted_tons": 25000.0,
            },
            {
                "origin_id": "rio_verde_go",
                "destination_id": "STS",
                "carrier_name": "Rodoviário Cerrado",
                "contract_code": "RC-2026-105",
                "freight_brl_ton": 210.00,
                "volume_contracted_tons": 30000.0,
            },
        ]
    }
    res_batch = client.post(
        f"/api/organizations/{org1.id}/freight-contracts/batch",
        json=batch_payload,
        headers=auth1,
    )
    assert res_batch.status_code == 200
    batch_data = res_batch.json()
    assert len(batch_data) == 2

    # Lista total após batch deve ter 3 contratos
    res_list_after = client.get(f"/api/organizations/{org1.id}/freight-contracts", headers=auth1)
    assert res_list_after.status_code == 200
    assert len(res_list_after.json()) == 3

    # 6. Deletar contrato válido
    res_delete = client.delete(
        f"/api/organizations/{org1.id}/freight-contracts/{contract_id}",
        headers=auth1,
    )
    assert res_delete.status_code == 200
    assert res_delete.json()["status"] == "deleted"
    assert res_delete.json()["id"] == contract_id
    res_del_404 = client.delete(
        f"/api/organizations/{org1.id}/freight-contracts/999999",
        headers=auth1,
    )
    assert res_del_404.status_code == 404


def test_market_service_freight_precedence(test_db_client):
    """
    Valida a regra de precedência de cotação de frete no MarketDataService:
    Se a organização possui um contrato ativo para a rota, o valor negociado
    prevalece sobre a cotação pública de mercado.
    """
    db = test_db_client["session"]

    org = Organization(name="Cooperativa Sul", slug="coop-sul", is_active=True)
    db.add(org)
    db.commit()

    # Rota Sorriso -> Santos: benchmark padrão é 420.0 R$/ton
    benchmark_rate = market_service.get_freight_rate("sorriso_mt", "STS", org_id=None, db=db)
    assert benchmark_rate == 420.0

    # Cadastra contrato privado de frete de 390.0 R$/ton
    contract = CompanyFreightContract(
        organization_id=org.id,
        origin_id="sorriso_mt",
        destination_id="STS",
        carrier_name="Transportadora Própria",
        contract_code="CONV-01",
        freight_brl_ton=390.0,
        is_active=True,
    )
    db.add(contract)
    db.commit()

    # Consulta com org_id deve retornar o valor negociado no contrato (390.0)
    org_rate = market_service.get_freight_rate("sorriso_mt", "STS", org_id=org.id, db=db)
    assert org_rate == 390.0

    # Consulta sem org_id continua retornando o benchmark público (420.0)
    public_rate = market_service.get_freight_rate("sorriso_mt", "STS", org_id=None, db=db)
    assert public_rate == 420.0

    # Se o contrato estiver inativo, deve reverter para o benchmark
    contract.is_active = False
    db.commit()
    inactive_rate = market_service.get_freight_rate("sorriso_mt", "STS", org_id=org.id, db=db)
    assert inactive_rate == 420.0
