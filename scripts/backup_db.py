#!/usr/bin/env python3
"""
Script de Backup e Snapshot Estruturado do Banco de Dados (Ticket F15).
Suporta PostgreSQL e SQLite via SQLAlchemy, gerando dump JSON versionado
com hash SHA256 de integridade e metadados de rastreabilidade (Git commit, UTC).
"""

import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Adiciona raiz do projeto ao path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.db.connection import DATABASE_URL, Base
from src.db.models import (
    MarketQuote,
    ParitySnapshot,
    ExtractionLog,
    User,
    Organization,
    Membership,
    CostProfile,
    Invitation,
)


def get_git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except Exception:
        return "UNKNOWN_SHA"


def export_database_snapshot(engine, output_filepath: Path) -> dict:
    """Extrai todas as entidades relacionais para um payload de backup auditável."""
    Session = sessionmaker(bind=engine)
    session = Session()

    now_utc = datetime.now(timezone.utc).isoformat()
    git_sha = get_git_sha()

    tables_data = {
        "users": [u.to_dict() for u in session.query(User).all()],
        "organizations": [o.to_dict() for o in session.query(Organization).all()],
        "memberships": [m.to_dict() for m in session.query(Membership).all()],
        "cost_profiles": [c.to_dict() for c in session.query(CostProfile).all()],
        "invitations": [i.to_dict() for i in session.query(Invitation).all()],
        "market_quotes": [q.to_dict() for q in session.query(MarketQuote).all()],
        "parity_snapshots": [p.to_dict() for p in session.query(ParitySnapshot).all()],
        "extraction_logs": [l.to_dict() for l in session.query(ExtractionLog).all()],
    }

    raw_json = json.dumps(tables_data, indent=2, sort_keys=True)
    payload_sha256 = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    snapshot_envelope = {
        "metadata": {
            "created_at": now_utc,
            "git_commit_sha": git_sha,
            "schema_version": "v2_fase1",
            "sha256_checksum": payload_sha256,
            "record_counts": {k: len(v) for k, v in tables_data.items()},
        },
        "data": tables_data,
    }

    output_filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot_envelope, f, indent=2)

    session.close()
    return snapshot_envelope


def main():
    target_dir = ROOT_DIR / "backups"
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    backup_file = target_dir / f"agritrading_backup_{timestamp_str}.json"

    engine = create_engine(DATABASE_URL)
    print(f"📦 Iniciando backup do banco de dados em: {backup_file}")
    envelope = export_database_snapshot(engine, backup_file)
    print("✅ Backup concluído com sucesso!")
    print(f"  • Git SHA: {envelope['metadata']['git_commit_sha']}")
    print(f"  • Checksum SHA256: {envelope['metadata']['sha256_checksum']}")
    print(f"  • Registros: {envelope['metadata']['record_counts']}")


if __name__ == "__main__":
    main()
