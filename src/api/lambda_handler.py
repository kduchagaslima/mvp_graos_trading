"""
Handler de Execução Serverless para AWS Lambda.
Permite executar a API FastAPI via Amazon API Gateway e rotinas de ingestão
agendadas via Amazon EventBridge Scheduler utilizando o mesmo runtime.
"""

import json
import logging
from typing import Dict, Any

logger = logging.getLogger("agri_lambda")
logger.setLevel(logging.INFO)

from src.api.main import app

# Inicializa o adaptador Mangum para transformar requisições API Gateway em ASGI
try:
    from mangum import Mangum
    mangum_handler = Mangum(app, lifespan="off")
    MANGUM_AVAILABLE = True
except ImportError:
    MANGUM_AVAILABLE = False
    logger.warning("Mangum não instalado no ambiente local. Necessário para deploy no AWS Lambda.")


_db_initialized = False

def ensure_db_initialized():
    """Garante que as tabelas no Neon Postgres sejam criadas na primeira execução da Lambda."""
    global _db_initialized
    if not _db_initialized:
        try:
            from src.db.connection import init_db
            init_db()
            _db_initialized = True
            logger.info("Tabelas do banco de dados verificadas/criadas com sucesso na inicializacao da Lambda.")
        except Exception as err:
            logger.error(f"Erro ao inicializar tabelas no banco durante execucao da Lambda: {err}")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Entrypoint principal do AWS Lambda.
    Identifica dinamicamente a origem do evento:
    1. EventBridge Scheduler (disparos cron de B3 / Macro)
    2. API Gateway HTTP API v2 (requisições REST / Swagger)
    """
    ensure_db_initialized()
    logger.info(f"Lambda acionada. Origem/Tipo do evento: {list(event.keys())}")

    # 1. Trata disparos agendados via Amazon EventBridge Scheduler
    is_eventbridge = (
        event.get("source") == "aws.events"
        or "detail-type" in event
        or "job_type" in event
        or event.get("trigger") == "eventbridge"
    )

    if is_eventbridge:
        job_type = event.get("job_type", "B3_SETTLEMENT")
        logger.info(f"[EVENTBRIDGE] Executando rotina agendada: {job_type}")

        from src.services.b3_extractor import extract_and_persist_b3_data
        from src.services.extractor import extract_and_persist_market_data

        if job_type == "B3_SETTLEMENT":
            res = extract_and_persist_b3_data(session_type="EOD_SETTLEMENT")
        elif job_type == "B3_INTRADAY":
            res = extract_and_persist_b3_data(session_type="INTRADAY")
        elif job_type == "MACRO_MARKET_DATA":
            res = extract_and_persist_market_data()
        else:
            res = extract_and_persist_b3_data(session_type=f"JOB_{job_type}")

        return {
            "statusCode": 200,
            "body": json.dumps({"status": "SUCCESS", "job_type": job_type, "result": res}),
        }

    # 2. Trata requisições HTTP REST vindas do Amazon API Gateway
    if MANGUM_AVAILABLE:
        return mangum_handler(event, context)
    else:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Mangum não configurado no runtime"}),
        }
