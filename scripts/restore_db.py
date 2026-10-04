#!/usr/bin/env python3
"""
Script de Restauração Segura do Banco de Dados com Validação de Integridade (Ticket F15).
Verifica hash SHA256 antes da restauração e repovoa as tabelas relacionais.
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, date, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.db.connection import DATABASE_URL, Base
from src.db.models import (
    User,
    Organization,
    Membership,
    CostProfile,
    Invitation,
    MarketQuote,
    ParitySnapshot,
    ExtractionLog,
    DataKind,
    FreshnessStatus,
)


def parse_iso_dt(val):
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


def parse_iso_date(val):
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except Exception:
        return None


def restore_database_snapshot(engine, input_filepath: Path, verify_checksum: bool = True) -> dict:
    """Restaura o estado do banco a partir de um arquivo de backup verificado."""
    with open(input_filepath, "r", encoding="utf-8") as f:
        envelope = json.load(f)

    meta = envelope.get("metadata", {})
    tables_data = envelope.get("data", {})

    if verify_checksum:
        raw_json = json.dumps(tables_data, indent=2, sort_keys=True)
        computed_sha256 = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
        expected_sha256 = meta.get("sha256_checksum")
        if expected_sha256 and computed_sha256 != expected_sha256:
            raise ValueError(
                f"Falha de integridade: Checksum do arquivo ({computed_sha256}) difere do esperado ({expected_sha256})"
            )

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 1. Usuários
        id_map_user = {}
        for row in tables_data.get("users", []):
            existing = session.query(User).filter(User.cognito_sub == row["cognito_sub"]).first()
            if not existing:
                u = User(
                    cognito_sub=row["cognito_sub"],
                    email=row["email"],
                    name=row.get("name"),
                    is_active=row.get("is_active", True),
                    is_platform_operator=row.get("is_platform_operator", False),
                    created_at=parse_iso_dt(row.get("created_at")) or datetime.now(timezone.utc),
                )
                session.add(u)
                session.flush()
                id_map_user[row["id"]] = u.id
            else:
                id_map_user[row["id"]] = existing.id

        # 2. Organizações
        id_map_org = {}
        for row in tables_data.get("organizations", []):
            existing = session.query(Organization).filter(Organization.slug == row["slug"]).first()
            if not existing:
                o = Organization(
                    name=row["name"],
                    slug=row["slug"],
                    is_active=row.get("is_active", True),
                    created_at=parse_iso_dt(row.get("created_at")) or datetime.now(timezone.utc),
                )
                session.add(o)
                session.flush()
                id_map_org[row["id"]] = o.id
            else:
                id_map_org[row["id"]] = existing.id

        # 3. Memberships
        for row in tables_data.get("memberships", []):
            mapped_user_id = id_map_user.get(row["user_id"])
            mapped_org_id = id_map_org.get(row["organization_id"])
            if mapped_user_id and mapped_org_id:
                existing = session.query(Membership).filter(
                    Membership.user_id == mapped_user_id,
                    Membership.organization_id == mapped_org_id,
                ).first()
                if not existing:
                    m = Membership(
                        user_id=mapped_user_id,
                        organization_id=mapped_org_id,
                        role=row.get("role", "ANALYST"),
                        is_active=row.get("is_active", True),
                        created_at=parse_iso_dt(row.get("created_at")) or datetime.now(timezone.utc),
                    )
                    session.add(m)

        # 4. Cost Profiles
        for row in tables_data.get("cost_profiles", []):
            mapped_org_id = id_map_org.get(row["organization_id"])
            if mapped_org_id:
                cp = CostProfile(
                    organization_id=mapped_org_id,
                    name=row.get("name", "Padrão"),
                    brokerage_margin_usd_ton=row.get("brokerage_margin_usd_ton", 2.0),
                    brokerage_fee_brl_bag=row.get("brokerage_fee_brl_bag", 0.0),
                    brokerage_payer=row.get("brokerage_payer", "NONE"),
                    default_funrural_pct=row.get("default_funrural_pct", 1.5),
                    default_shrinkage_loss_pct=row.get("default_shrinkage_loss_pct", 0.3),
                    is_active=row.get("is_active", True),
                    created_at=parse_iso_dt(row.get("created_at")) or datetime.now(timezone.utc),
                    updated_at=parse_iso_dt(row.get("updated_at")) or datetime.now(timezone.utc),
                )
                session.add(cp)

        # 5. Cotações de Mercado
        for row in tables_data.get("market_quotes", []):
            q_date = parse_iso_date(row.get("quote_date"))
            if q_date:
                existing_q = session.query(MarketQuote).filter(
                    MarketQuote.quote_date == q_date,
                    MarketQuote.category == row["category"],
                    MarketQuote.symbol == row["symbol"],
                    MarketQuote.contract_code == row.get("contract_code", "SPOT"),
                    MarketQuote.location_id == row.get("location_id", "GLOBAL"),
                ).first()
                if not existing_q:
                    mq = MarketQuote(
                        quote_date=q_date,
                        timestamp=parse_iso_dt(row.get("timestamp")) or datetime.now(timezone.utc),
                        observed_at=parse_iso_dt(row.get("observed_at")),
                        ingested_at=parse_iso_dt(row.get("ingested_at")) or datetime.now(timezone.utc),
                        category=row["category"],
                        commodity=row.get("commodity"),
                        symbol=row["symbol"],
                        contract_code=row.get("contract_code", "SPOT"),
                        location_id=row.get("location_id", "GLOBAL"),
                        price=row["price"],
                        price_numeric=row.get("price_numeric"),
                        unit=row.get("unit", ""),
                        currency=row.get("currency", "BRL"),
                        source=row.get("source", ""),
                        source_vendor=row.get("source_vendor"),
                        source_reference=row.get("source_reference"),
                        data_kind=row.get("data_kind", "OBSERVED"),
                        freshness=row.get("freshness", "CURRENT"),
                    )
                    session.add(mq)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return meta


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 scripts/restore_db.py <caminho_do_arquivo_backup.json>")
        sys.exit(1)

    backup_path = Path(sys.argv[1])
    if not backup_path.exists():
        print(f"Erro: Arquivo {backup_path} não encontrado.")
        sys.exit(1)

    engine = create_engine(DATABASE_URL)
    print(f"🔄 Restaurando banco de dados a partir de: {backup_path}")
    meta = restore_database_snapshot(engine, backup_path, verify_checksum=True)
    print("🎉 Restauração concluída com sucesso e integridade validada!")
    print(f"  • Snapshot de origem criado em: {meta.get('created_at')}")
    print(f"  • Git SHA do snapshot: {meta.get('git_commit_sha')}")


if __name__ == "__main__":
    main()
