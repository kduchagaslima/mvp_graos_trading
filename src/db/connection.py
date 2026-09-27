"""
Configuração da conexão com o Banco de Dados e Gerenciamento de Sessões SQLAlchemy.
Suporta SQLite otimizado com Write-Ahead Logging (WAL) e PostgreSQL via DATABASE_URL.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator

# Diretório padrão para dados persistentes
DEFAULT_DATA_DIR = Path("/app/data") if Path("/app").exists() else Path("./data")
DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_FILE = DEFAULT_DATA_DIR / "market_data.db"
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_FILE}"

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

# Configuração do Engine
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

# Otimização específica para SQLite: Habilitar modo WAL (Write-Ahead Logging) e foreign keys
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency para injeção de sessão no FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Cria todas as tabelas no banco de dados se não existirem."""
    from src.db import models  # noqa
    Base.metadata.create_all(bind=engine)
