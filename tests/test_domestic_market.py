"""
Suíte de Testes Automatizados para o Módulo de Mercado Interno e ICMS (Atividade 2).
Valida paridade de consumo industrial doméstico, isenção/diferimento de taxas portuárias,
alíquotas de ICMS e contratos privados de frete para indústrias.
"""

from datetime import datetime, timezone, timedelta, date
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
from src.domain.locations import DOMESTIC_INDUSTRIES
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


def test_domestic_industries_catalog_endpoint(test_db_client):
    """Valida o endpoint de catálogo de indústrias processadoras e usinas domésticas."""
    client = test_db_client["client"]
    res = client.get("/api/industries/summary")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 5
    ids = [item["id"] for item in data]
    assert "IND_LRV_FS" in ids
    assert "IND_ROO_BUNGE" in ids
    assert "IND_RV_COMIGO" in ids
    assert "IND_CHAP_BRF" in ids
    assert "IND_CASCAVEL_LAR" in ids

    # Valida estrutura detalhada da usina FS de Lucas do Rio Verde
    fs = next(item for item in data if item["id"] == "IND_LRV_FS")
    assert fs["city"] == "Lucas do Rio Verde"
    assert fs["state"] == "MT"
    assert fs["industry_type"] == "USINA_ETANOL"
    assert fs["commodity_handled"] == "MILHO"
    assert fs["icms_internal_rate"] == 0.0


def test_domestic_parity_zero_port_fees_and_icms(test_db_client):
    """
    Valida cálculo de paridade para indústria interna:
    - Despesas portuárias (elevação, demurrage, outras) devem ser R$ 0,00.
    - ICMS diferido (0%) em MT resulta em icms_brl_bag == 0.0.
    - ICMS interestadual (12%) resulta em dedução no waterfall.
    """
    client = test_db_client["client"]

    # 1. Cálculo Mercado Interno MT com ICMS 0% (Diferido)
    payload_internal = {
        "commodity": "SOJA",
        "cbot_price_cents": 1050.0,
        "port_premium_cents": 0.0,
        "usd_brl_fx": 5.60,
        "hub_id": "rondonopolis_mt",
        "destination_type": "DOMESTIC_INDUSTRY",
        "industry_id": "IND_ROO_BUNGE",
        "icms_rate_pct": 0.0,
        "freight_brl_ton": 35.0,
    }
    res_int = client.post("/api/parity/calculate", json=payload_internal)
    assert res_int.status_code == 200
    res_data = res_int.json()

    assert res_data["destination_type"] == "DOMESTIC_INDUSTRY"
    assert res_data["industry_name"] == "Complexo Esmagadora Bunge/ADM"
    breakdown = res_data["cost_breakdown"]

    # Deduções portuárias estritamente zeradas
    assert breakdown["elevation_brl_bag"] == 0.0
    assert breakdown["demurrage_brl_bag"] == 0.0
    assert breakdown["other_port_costs_brl_bag"] == 0.0
    assert breakdown["icms_brl_bag"] == 0.0

    # Frete interno de 35 R$/ton = 2.10 R$/saca
    assert breakdown["freight_brl_bag"] == 2.10
    assert res_data["net_parity_price_brl_bag"] > 120.0

    # 2. Cálculo Mercado Interno Interestadual com ICMS 12%
    payload_interstate = {
        "commodity": "MILHO",
        "cbot_price_cents": 450.0,
        "port_premium_cents": 0.0,
        "usd_brl_fx": 5.60,
        "hub_id": "rio_verde_go",
        "destination_type": "DOMESTIC_INDUSTRY",
        "industry_id": "IND_CHAP_BRF",
        "icms_rate_pct": 12.0,
        "freight_brl_ton": 220.0,
    }
    res_inter = client.post("/api/parity/calculate", json=payload_interstate)
    assert res_inter.status_code == 200
    inter_data = res_inter.json()

    assert inter_data["destination_type"] == "DOMESTIC_INDUSTRY"
    inter_breakdown = inter_data["cost_breakdown"]
    assert inter_breakdown["elevation_brl_bag"] == 0.0
    assert inter_breakdown["demurrage_brl_bag"] == 0.0
    assert inter_breakdown["icms_brl_bag"] > 0.0  # Alíquota de 12% aplicada


def test_domestic_parity_with_private_freight_contract(test_db_client):
    """Valida se contrato privado cadastrado para rota hub -> indústria é aplicado no cálculo."""
    client = test_db_client["client"]
    db = test_db_client["session"]
    rsa = test_db_client["rsa"]

    owner = User(cognito_sub="domestic-owner", email="owner@dom.local", name="Domestic Owner")
    org = Organization(name="Trading Doméstica SA", slug="trading-dom", is_active=True)
    db.add_all([owner, org])
    db.commit()

    db.add(Membership(user_id=owner.id, organization_id=org.id, role=MembershipRole.OWNER.value, is_active=True))
    db.commit()

    headers = make_auth_header(rsa, sub="domestic-owner", email="owner@dom.local")

    # Cadastra contrato privado de frete para usina FS de Lucas do Rio Verde
    contract_payload = {
        "origin_id": "sorriso_mt",
        "destination_id": "IND_LRV_FS",
        "carrier_name": "TransNorte Frota Dedicada",
        "contract_code": "CTR-FS-2026",
        "freight_brl_ton": 38.0,
    }
    res_ctr = client.post(f"/api/organizations/{org.id}/freight-contracts", json=contract_payload, headers=headers)
    assert res_ctr.status_code == 200

    # Consulta contratos da organização
    res_list = client.get(f"/api/organizations/{org.id}/freight-contracts", headers=headers)
    assert res_list.status_code == 200
    saved_contract = res_list.json()[0]
    assert saved_contract["destination_id"] == "IND_LRV_FS"
    assert saved_contract["freight_brl_ton"] == 38.0

    # Executa cálculo de paridade aplicando a tarifa do contrato privado para a rota
    calc_payload = {
        "commodity": "MILHO",
        "cbot_price_cents": 440.0,
        "port_premium_cents": 0.0,
        "usd_brl_fx": 5.60,
        "hub_id": "sorriso_mt",
        "destination_type": "DOMESTIC_INDUSTRY",
        "industry_id": "IND_LRV_FS",
        "freight_brl_ton": saved_contract["freight_brl_ton"],
    }
    res_calc = client.post("/api/parity/calculate", json=calc_payload, headers=headers)
    assert res_calc.status_code == 200
    res_data = res_calc.json()

    # Frete deve ser 38.0 R$/ton * 0.06 = 2.28 R$/saca
    assert res_data["cost_breakdown"]["freight_brl_bag"] == 2.28
    assert res_data["cost_breakdown"]["elevation_brl_bag"] == 0.0
