"""
Gerenciador de Migrações Versionadas para o Banco de Dados (Ticket F02).
Suporta PostgreSQL (Neon) e SQLite (com fallback e compatibilidade de dialetos),
garantindo aplicação idempotente, controle em schema_migrations e rastreabilidade.
"""

import os
import re
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import text, Engine
from src.db.connection import engine as default_engine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def ensure_migration_table(conn, is_sqlite: bool):
    """Garante a existência da tabela de controle schema_migrations."""
    if is_sqlite:
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version VARCHAR(64) UNIQUE NOT NULL,
            description VARCHAR(255),
            applied_at TIMESTAMP NOT NULL
        );
        """
    else:
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            version VARCHAR(64) UNIQUE NOT NULL,
            description VARCHAR(255),
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    conn.execute(text(sql))


def get_applied_migrations(conn) -> List[str]:
    """Retorna a lista de versões de migração já aplicadas."""
    res = conn.execute(text("SELECT version FROM schema_migrations ORDER BY id ASC"))
    return [row[0] for row in res.fetchall()]


def record_migration(conn, version: str, description: str, is_sqlite: bool):
    """Grava o registro de aplicação de uma migração."""
    now_str = datetime.now(timezone.utc).isoformat()
    sql = text(
        "INSERT INTO schema_migrations (version, description, applied_at) VALUES (:version, :desc, :now)"
    )
    conn.execute(sql, {"version": version, "desc": description, "now": now_str})


def sanitize_sqlite_sql(sql_content: str) -> List[str]:
    """
    Converte comandos DDL PostgreSQL para compatibilidade SQLite quando necessário.
    """
    statements = []
    # Remove comentários de linha inteira (-- ...) para evitar interferência na análise do comando
    clean_lines = []
    for line in sql_content.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("--"):
            continue
        clean_lines.append(line)
    uncommented_sql = "\n".join(clean_lines)

    # Divide por ponto e vírgula
    raw_statements = [s.strip() for s in uncommented_sql.split(";") if s.strip()]

    for stmt in raw_statements:
        clean = stmt
        # Substitui tipos PostgreSQL por tipos SQLite compatíveis
        clean = re.sub(r"\bSERIAL PRIMARY KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bTIMESTAMP WITH TIME ZONE\b", "TIMESTAMP", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bTIMESTAMP WITHOUT TIME ZONE\b", "TIMESTAMP", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bDOUBLE PRECISION\b", "FLOAT", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bCURRENT_TIMESTAMP\b", "CURRENT_TIMESTAMP", clean, flags=re.IGNORECASE)

        # Trata ALTER TABLE ... ADD COLUMN ... IF NOT EXISTS para SQLite
        # SQLite não suporta "IF NOT EXISTS" na cláusula ADD COLUMN
        clean = re.sub(r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS", "ADD COLUMN", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s+", " ", clean).strip()

        if clean:
            statements.append(clean)

    return statements


def run_migrations(target_engine: Optional[Engine] = None) -> List[Dict[str, Any]]:
    """
    Executa todas as migrações SQL pendentes em ordem alfabética.
    Retorna a lista de migrações aplicadas nesta execução.
    """
    eng = target_engine or default_engine
    is_sqlite = eng.url.drivername.startswith("sqlite")
    applied_this_run = []

    if not MIGRATIONS_DIR.exists():
        logger.warning(f"Diretório de migrações não encontrado: {MIGRATIONS_DIR}")
        return []

    migration_files = sorted(list(MIGRATIONS_DIR.glob("*.sql")))

    with eng.begin() as conn:
        ensure_migration_table(conn, is_sqlite)
        applied_versions = get_applied_migrations(conn)

        for mf in migration_files:
            version = mf.stem  # ex: "001_initial_schema"
            if version in applied_versions:
                continue

            logger.info(f"Aplicando migração: {version}...")
            content = mf.read_text(encoding="utf-8")

            if is_sqlite:
                stmts = sanitize_sqlite_sql(content)
                for stmt in stmts:
                    if not stmt:
                        continue
                    try:
                        conn.execute(text(stmt))
                    except Exception as err:
                        # Se for erro de coluna duplicada no SQLite, ignora tolerante
                        err_str = str(err).lower()
                        if "duplicate column name" in err_str:
                            logger.debug(f"Coluna já existente no SQLite ignorada: {err}")
                        else:
                            raise err
            else:
                # PostgreSQL executa o bloco SQL direto
                conn.execute(text(content))

            desc = version.replace("_", " ").title()
            record_migration(conn, version, desc, is_sqlite)
            applied_this_run.append({
                "version": version,
                "description": desc,
                "file": mf.name,
            })
            logger.info(f"✅ Migração {version} aplicada com sucesso.")

    return applied_this_run


def get_migration_status(target_engine: Optional[Engine] = None) -> Dict[str, Any]:
    """Retorna o status atual de migrações do banco."""
    eng = target_engine or default_engine
    is_sqlite = eng.url.drivername.startswith("sqlite")

    with eng.begin() as conn:
        ensure_migration_table(conn, is_sqlite)
        applied = get_applied_migrations(conn)

    all_files = sorted([f.stem for f in MIGRATIONS_DIR.glob("*.sql")])
    pending = [f for f in all_files if f not in applied]

    return {
        "engine": eng.url.drivername,
        "total_migrations": len(all_files),
        "applied_count": len(applied),
        "applied": applied,
        "pending_count": len(pending),
        "pending": pending,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🚀 Executando migrações versionadas do AgriTrading...")
    res = run_migrations()
    status = get_migration_status()
    print(f"Status: {status['applied_count']} aplicadas, {status['pending_count']} pendentes.")
