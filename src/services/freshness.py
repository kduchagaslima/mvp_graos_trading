"""
Serviço de Avaliação de Frescor de Dados de Mercado (Ticket F02).
Implementa regras de tolerância temporal considerando calendário oficial e dias úteis,
garantindo que cotações legítimas de fechamento de semana não sejam marcadas erroneamente como STALE no final de semana.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from enum import Enum


class FreshnessStatus(str, Enum):
    CURRENT = "CURRENT"  # Dado atual dentro da tolerância de calendário
    STALE = "STALE"      # Dado defasado além da tolerância esperada
    UNKNOWN = "UNKNOWN"  # Sem data de observação para cálculo


def is_weekend(dt: datetime) -> bool:
    """Retorna True se a data cair em sábado (5) ou domingo (6)."""
    return dt.weekday() in (5, 6)


def get_business_day_delta_hours(start_dt: datetime, end_dt: datetime) -> float:
    """
    Calcula as horas decorridas descontando sábados e domingos inteiros.
    """
    if end_dt <= start_dt:
        return 0.0

    total_seconds = 0.0
    curr = start_dt
    step = timedelta(hours=1)

    while curr < end_dt:
        next_curr = min(curr + step, end_dt)
        # Se não for fim de semana, contabiliza o tempo
        if curr.weekday() not in (5, 6):
            total_seconds += (next_curr - curr).total_seconds()
        curr = next_curr

    return total_seconds / 3600.0


def evaluate_freshness(
    category: str,
    symbol: str,
    observed_at: Optional[datetime],
    now_dt: Optional[datetime] = None,
) -> FreshnessStatus:
    """
    Avalia se uma cotação é CURRENT ou STALE considerando a categoria do ativo,
    sua frequência de divulgação e o calendário de dias úteis.
    """
    if observed_at is None:
        return FreshnessStatus.UNKNOWN

    now = now_dt or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    cat_upper = category.upper()
    sym_upper = symbol.upper()

    # 1. Indicadores Macroeconômicos Mensais (IPCA, IGP-M)
    if "IPCA" in sym_upper or "IGPM" in sym_upper:
        # Periodicidade mensal: tolerância de 45 dias corridos
        elapsed_days = (now - observed_at).total_seconds() / 86400.0
        return FreshnessStatus.CURRENT if elapsed_days <= 45.0 else FreshnessStatus.STALE

    # 2. Indicadores Macroeconômicos Diários (CDI, Selic)
    if "CDI" in sym_upper or "SELIC" in sym_upper:
        business_hours = get_business_day_delta_hours(observed_at, now)
        # Tolerância de 36 horas úteis para publicação do BACEN
        return FreshnessStatus.CURRENT if business_hours <= 36.0 else FreshnessStatus.STALE

    # 3. Câmbio PTAX (BCB) e Futuros (CBOT, B3)
    if cat_upper in ("FX", "FUTURES", "B3_FUTURES"):
        business_hours = get_business_day_delta_hours(observed_at, now)
        # Uma PTAX de sexta-feira às 18h no sábado e domingo possui 0 horas úteis adicionais decorridas.
        # Segunda-feira até às 19h possui cerca de 19 horas úteis.
        # Tolerância: 28 horas úteis (cobre até o fechamento do dia útil seguinte).
        return FreshnessStatus.CURRENT if business_hours <= 28.0 else FreshnessStatus.STALE

    # 4. Prêmios de Exportação Portuários e Preços Físicos (CEPEA)
    if cat_upper in ("PORT_PREMIUM", "PHYSICAL_CASH", "CEPEA_INDEX"):
        business_hours = get_business_day_delta_hours(observed_at, now)
        # Tolerância de 48 horas úteis (2 dias úteis de reporte)
        return FreshnessStatus.CURRENT if business_hours <= 48.0 else FreshnessStatus.STALE

    # 5. Fretes Rodoviários (ESALQ-LOG / Balcão)
    if cat_upper == "FREIGHT":
        business_hours = get_business_day_delta_hours(observed_at, now)
        # Tabelas de frete possuem ajuste semanal ou a cada 3 dias úteis: 72 horas úteis
        return FreshnessStatus.CURRENT if business_hours <= 72.0 else FreshnessStatus.STALE

    # Padrão genérico: 48 horas úteis
    business_hours = get_business_day_delta_hours(observed_at, now)
    return FreshnessStatus.CURRENT if business_hours <= 48.0 else FreshnessStatus.STALE
