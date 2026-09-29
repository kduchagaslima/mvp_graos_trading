"""
Módulo de Execução do Agendador de Ingestão de Dados de Mercado (B3 & Agro).
Executa rotinas periódicas de coleta e atualização no banco de dados relacional
de acordo com o horário de funcionamento dos mercados (Horário de Brasília).
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

# Garante timezone padrão do Brasil
TIMEZONE_STR = "America/Sao_Paulo"

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SCHEDULER] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agri_scheduler")

# Importações dos extratores e serviços
from src.services.b3_extractor import extract_and_persist_b3_data
from src.services.extractor import extract_and_persist_market_data

# Tenta carregar APScheduler; caso não disponível, disponibiliza modo fallback
try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler ou pytz não encontrados. O agendador operará em modo de espera/fallback.")


# Definição das Rotinas Agendadas
SCHEDULED_JOBS_METADATA = [
    {
        "id": "b3_settlement",
        "name": "B3 Fechamento & Ajuste Diário (CCM & SJC)",
        "frequency": "Seg-Sex às 19:15 (Brasília)",
        "cron_day_of_week": "mon-fri",
        "cron_hour": 19,
        "cron_minute": 15,
        "description": "Coleta preços oficiais de liquidação e ajuste de contratos futuros de Milho (CCM), Soja (SJC) e Indicadores CEPEA/ESALQ.",
        "category": "B3_DERIVATIVES",
    },
    {
        "id": "b3_intraday_morning",
        "name": "B3 Intraday Manhã (09:30 - 12:00)",
        "frequency": "Seg-Sex a cada 30min entre 09:30 e 12:00",
        "cron_day_of_week": "mon-fri",
        "cron_hour": "9-12",
        "cron_minute": "0,30",
        "description": "Monitoramento e atualização das cotações em tempo de pregão aberto dos futuros agrícolas B3.",
        "category": "B3_DERIVATIVES",
    },
    {
        "id": "b3_intraday_afternoon",
        "name": "B3 Intraday Tarde (12:30 - 16:30)",
        "frequency": "Seg-Sex a cada 30min entre 12:30 e 16:30",
        "cron_day_of_week": "mon-fri",
        "cron_hour": "12-16",
        "cron_minute": "0,30",
        "description": "Monitoramento vespertino das cotações em tempo de pregão aberto dos futuros agrícolas B3.",
        "category": "B3_DERIVATIVES",
    },
    {
        "id": "general_market_data",
        "name": "Market Data Global Fechamento (BCB, CBOT, Prêmios, Físico)",
        "frequency": "Seg-Sex às 18:30 (Brasília)",
        "cron_day_of_week": "mon-fri",
        "cron_hour": 18,
        "cron_minute": 30,
        "description": "Atualização dos pilares macro: PTAX BCB, Chicago CBOT, Prêmios nos Portos, Mercado Físico e Fretes.",
        "category": "MACRO_GRAOS",
    },
]


def job_b3_settlement():
    """Rotina executada após o fechamento da B3 para capturar os ajustes finais."""
    logger.info(">>> Iniciando rotina oficial de Fechamento B3 / Indicadores CEPEA...")
    try:
        res = extract_and_persist_b3_data(session_type="EOD_SETTLEMENT")
        logger.info(f"Fechamento B3 concluído com sucesso: {res.get('total_persisted', 0)} cotações atualizadas.")
    except Exception as exc:
        logger.error(f"Erro na execução da rotina de Fechamento B3: {exc}", exc_info=True)


def job_b3_intraday():
    """Rotina executada durante o pregão da B3 a cada 30 minutos."""
    logger.info(">>> Iniciando rotina Intraday B3...")
    try:
        res = extract_and_persist_b3_data(session_type="INTRADAY")
        logger.info(f"Intraday B3 concluído: {res.get('total_persisted', 0)} cotações atualizadas.")
    except Exception as exc:
        logger.error(f"Erro na execução da rotina Intraday B3: {exc}", exc_info=True)


def job_general_market_data():
    """Rotina diária para dados macro de grãos (PTAX, CBOT, Prêmios, Físico)."""
    logger.info(">>> Iniciando rotina diária de Market Data Geral (BCB, CBOT, Prêmios, Físico)...")
    try:
        res = extract_and_persist_market_data()
        logger.info(f"Market Data Geral concluído com sucesso: {res.get('total_persisted', 0)} registros gravados.")
    except Exception as exc:
        logger.error(f"Erro na rotina de Market Data Geral: {exc}", exc_info=True)


def trigger_b3_job_now(session_type: str = "MANUAL") -> Dict[str, Any]:
    """Dispara a extração da B3 manualmente a pedido da API ou da UI."""
    logger.info(f"Disparo manual de extração B3 solicitado (session_type={session_type})...")
    return extract_and_persist_b3_data(session_type=session_type)


def build_scheduler() -> Optional[Any]:
    """Configura o agendador com os jobs cadastrados no fuso de Brasília."""
    if not APSCHEDULER_AVAILABLE:
        logger.warning("APScheduler indisponível. Não foi possível instanciar o agendador completo.")
        return None

    tz = pytz.timezone(TIMEZONE_STR)
    scheduler = BlockingScheduler(timezone=tz)

    # 1. Fechamento B3 às 19:15 Seg-Sex
    scheduler.add_job(
        job_b3_settlement,
        CronTrigger(day_of_week="mon-fri", hour=19, minute=15, timezone=tz),
        id="b3_settlement",
        name="B3 Fechamento & Ajuste Diário",
        replace_existing=True,
    )

    # 2. Intraday B3: 09:30 às 12:00 Seg-Sex a cada 30m
    scheduler.add_job(
        job_b3_intraday,
        CronTrigger(day_of_week="mon-fri", hour="9-11", minute="0,30", timezone=tz),
        id="b3_intraday_morning",
        name="B3 Intraday Manhã",
        replace_existing=True,
    )

    # 3. Intraday B3: 12:00 às 16:30 Seg-Sex a cada 30m
    scheduler.add_job(
        job_b3_intraday,
        CronTrigger(day_of_week="mon-fri", hour="12-16", minute="0,30", timezone=tz),
        id="b3_intraday_afternoon",
        name="B3 Intraday Tarde",
        replace_existing=True,
    )

    # 4. Market Data Geral às 18:30 Seg-Sex
    scheduler.add_job(
        job_general_market_data,
        CronTrigger(day_of_week="mon-fri", hour=18, minute=30, timezone=tz),
        id="general_market_data",
        name="Market Data Global Fechamento",
        replace_existing=True,
    )

    return scheduler


def get_scheduler_status() -> Dict[str, Any]:
    """Retorna o status atual e metadados das tarefas agendadas."""
    return {
        "status": "ONLINE" if APSCHEDULER_AVAILABLE else "FALLBACK",
        "timezone": TIMEZONE_STR,
        "apscheduler_installed": APSCHEDULER_AVAILABLE,
        "jobs": SCHEDULED_JOBS_METADATA,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def run_scheduler_daemon():
    """Inicia o processo contínuo do agendador."""
    logger.info("=" * 60)
    logger.info(f"Iniciando AgriTrading Market Data Scheduler ({TIMEZONE_STR})")
    logger.info("Tarefas configuradas:")
    for job in SCHEDULED_JOBS_METADATA:
        logger.info(f" - [{job['id']}] {job['name']} -> {job['frequency']}")
    logger.info("=" * 60)

    # Executa uma rodada inicial de verificação/ingestão para garantir dados frescos no boot
    logger.info("Executando ingestão inicial de dados B3 no arranque do serviço...")
    try:
        init_res = trigger_b3_job_now(session_type="STARTUP_SYNC")
        logger.info(f"Ingestão inicial B3 concluída: {init_res.get('total_persisted', 0)} cotações salvas.")
    except Exception as e:
        logger.warning(f"Aviso durante ingestão inicial: {e}")

    scheduler = build_scheduler()

    if scheduler:
        def shutdown_handler(signum, frame):
            logger.info("Sinal de encerramento recebido. Parando o scheduler...")
            scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        logger.info("Scheduler ativo e aguardando horários agendados...")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler finalizado.")
    else:
        logger.warning("Iniciando loop de espera contínuo (modo fallback sem APScheduler)...")
        while True:
            time.sleep(60)


if __name__ == "__main__":
    run_scheduler_daemon()
