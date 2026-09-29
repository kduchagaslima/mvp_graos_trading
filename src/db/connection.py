"""
Configuração da conexão com o Banco de Dados e Gerenciamento de Sessões SQLAlchemy.
Suporta PostgreSQL (com psycopg ou psycopg2 e pooling) e SQLite (com WAL mode).
Possui fallback resiliente e tentativas de reconexão automática no boot.
"""

import os
import time
import logging
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator

logger = logging.getLogger(__name__)

# Detecção de ambiente Serverless AWS Lambda (onde /var/task é somente leitura e /tmp é gravável)
IS_LAMBDA = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("LAMBDA_TASK_ROOT"))

if IS_LAMBDA:
    DEFAULT_DATA_DIR = Path("/tmp/data")
elif Path("/app").exists():
    DEFAULT_DATA_DIR = Path("/app/data")
else:
    DEFAULT_DATA_DIR = Path("./data")

DEFAULT_DB_FILE = DEFAULT_DATA_DIR / "market_data.db"
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_FILE}"

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

# Cria o diretório de dados apenas se estiver usando banco SQLite local
if DATABASE_URL.startswith("sqlite"):
    try:
        DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        logger.warning(f"Aviso ao criar diretório local SQLite {DEFAULT_DATA_DIR}: {err}")

# Normalização e detecção inteligente de driver para PostgreSQL
if DATABASE_URL.startswith("postgres://") or (
    DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+")
):
    prefix = "postgres://" if DATABASE_URL.startswith("postgres://") else "postgresql://"
    # 1. Verificar se psycopg (psycopg 3) está instalado
    has_psycopg3 = False
    try:
        import psycopg  # noqa: F401
        has_psycopg3 = True
    except ImportError:
        pass

    # 2. Verificar se psycopg2 está instalado
    has_psycopg2 = False
    try:
        import psycopg2  # noqa: F401
        has_psycopg2 = True
    except ImportError:
        pass

    if has_psycopg3:
        # Mantém postgresql:// ou usa postgresql+psycopg://
        DATABASE_URL = DATABASE_URL.replace(prefix, "postgresql+psycopg://", 1)
    elif has_psycopg2:
        # Usa psycopg2
        DATABASE_URL = DATABASE_URL.replace(prefix, "postgresql+psycopg2://", 1)
    else:
        logger.warning(
            "Drivers PostgreSQL (psycopg/psycopg2) não encontrados no ambiente. "
            "Recorrendo temporariamente a SQLite local."
        )
        DATABASE_URL = DEFAULT_DB_URL

# Configuração do Engine
connect_args = {}
engine_kwargs = {"pool_pre_ping": True, "echo": False}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # Pool otimizado para PostgreSQL
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
    })

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)

# Otimização específica para SQLite
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


def init_db(max_retries: int = 5, retry_delay: float = 2.0) -> None:
    """
    Cria as tabelas no banco de dados se não existirem, com tentativas
    de espera para o caso do container do banco estar terminando de subir.
    """
    from src.db import models  # noqa: F401
    
    for attempt in range(1, max_retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Tabelas do banco de dados inicializadas com sucesso.")
            return
        except Exception as exc:
            if attempt == max_retries:
                logger.error(f"Falha definitiva ao inicializar banco após {max_retries} tentativas: {exc}")
                raise exc
            logger.warning(
                f"Banco de dados ainda indisponível (tentativa {attempt}/{max_retries}). "
                f"Aguardando {retry_delay}s... Erro: {exc}"
            )
            time.sleep(retry_delay)
