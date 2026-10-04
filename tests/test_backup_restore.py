"""
Suíte de Testes Automatizados de Backup, Restore e Integridade Criptográfica (Ticket F15).
Valida:
1. Extração de snapshot com envelope de metadados, commit SHA e hash SHA256.
2. Detecção e recusa de restore caso o arquivo tenha sido adulterado (checksum mismatch).
3. Restauração 100% íntegra de entidades (Users, Organizations, Memberships, CostProfiles, MarketQuotes) em novo banco.
"""

import json
from pathlib import Path
from datetime import date, datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.connection import Base
from src.db.models import (
    User,
    Organization,
    Membership,
    MembershipRole,
    CostProfile,
    MarketQuote,
    DataKind,
    FreshnessStatus,
)
from scripts.backup_db import export_database_snapshot
from scripts.restore_db import restore_database_snapshot


def test_backup_and_restore_cycle_integrity(tmp_path):
    """
    Ticket F15: Executa ciclo completo de exportação e importação verificando integridade.
    """
    backup_file = tmp_path / "test_snapshot.json"

    # 1. Configura banco de origem
    origin_engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=origin_engine)
    OriginSession = sessionmaker(bind=origin_engine)
    origin_db = OriginSession()

    # Popula dados de referência
    org = Organization(name="Agro Teste S/A", slug="agro-teste", is_active=True)
    user = User(cognito_sub="sub-test-backup", email="backup@teste.com", name="Operador Teste", is_active=True)
    origin_db.add_all([org, user])
    origin_db.commit()

    m = Membership(user_id=user.id, organization_id=org.id, role=MembershipRole.OWNER.value, is_active=True)
    cp = CostProfile(organization_id=org.id, name="Perfil Backup", brokerage_margin_usd_ton=3.5, brokerage_payer="TRADING")
    now_utc = datetime.now(timezone.utc)
    quote = MarketQuote(
        quote_date=date(2026, 10, 3),
        timestamp=now_utc,
        observed_at=now_utc,
        category="FX",
        symbol="USD/BRL",
        price=5.6540,
        unit="BRL",
        source="BACEN_PTAX",
        data_kind=DataKind.OBSERVED.value,
        freshness=FreshnessStatus.CURRENT.value,
    )
    origin_db.add_all([m, cp, quote])
    origin_db.commit()
    origin_db.close()

    # 2. Executa exportação de backup
    envelope = export_database_snapshot(origin_engine, backup_file)
    assert backup_file.exists()
    assert envelope["metadata"]["schema_version"] == "v2_fase1"
    assert envelope["metadata"]["sha256_checksum"] is not None
    assert envelope["metadata"]["record_counts"]["users"] == 1
    assert envelope["metadata"]["record_counts"]["organizations"] == 1
    assert envelope["metadata"]["record_counts"]["cost_profiles"] == 1
    assert envelope["metadata"]["record_counts"]["market_quotes"] == 1

    # 3. Teste de adulteração (Tampering Detection)
    corrupted_file = tmp_path / "corrupted_snapshot.json"
    with open(backup_file, "r") as f:
        data = json.load(f)
    # Adultera o preço no arquivo
    data["data"]["market_quotes"][0]["price"] = 99.99
    with open(corrupted_file, "w") as f:
        json.dump(data, f)

    dest_engine_corrupted = create_engine("sqlite:///:memory:", echo=False)
    with pytest.raises(ValueError) as exc_info:
        restore_database_snapshot(dest_engine_corrupted, corrupted_file, verify_checksum=True)
    assert "Falha de integridade: Checksum do arquivo" in str(exc_info.value)

    # 4. Restauração válida em novo banco de destino
    dest_engine = create_engine("sqlite:///:memory:", echo=False)
    meta_restored = restore_database_snapshot(dest_engine, backup_file, verify_checksum=True)
    assert meta_restored["schema_version"] == "v2_fase1"

    # 5. Validação de integridade pós-restauração
    DestSession = sessionmaker(bind=dest_engine)
    dest_db = DestSession()

    restored_user = dest_db.query(User).filter(User.cognito_sub == "sub-test-backup").first()
    assert restored_user is not None
    assert restored_user.email == "backup@teste.com"

    restored_org = dest_db.query(Organization).filter(Organization.slug == "agro-teste").first()
    assert restored_org is not None
    assert restored_org.name == "Agro Teste S/A"

    restored_cp = dest_db.query(CostProfile).filter(CostProfile.organization_id == restored_org.id).first()
    assert restored_cp is not None
    assert restored_cp.brokerage_margin_usd_ton == 3.5

    restored_quote = dest_db.query(MarketQuote).filter(MarketQuote.symbol == "USD/BRL").first()
    assert restored_quote is not None
    assert restored_quote.price == 5.6540
    assert restored_quote.source == "BACEN_PTAX"

    dest_db.close()
