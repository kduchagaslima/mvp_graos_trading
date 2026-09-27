"""
Serviço de Ingestão e Agregação de Market Data (Câmbio BCB, CBOT, Prêmios e Mercado Físico).
Possui fallback automático para garantir funcionamento mesmo em ambientes sem conectividade externa.
"""

from typing import Dict, Any, Optional
from datetime import datetime, date
import requests
import logging

logger = logging.getLogger(__name__)


# Cotações padrão de referência (Market Seeds)
DEFAULT_MARKET_SEEDS = {
    "fx_usd_brl": 5.4850,
    "cbot_prices": {
        "SOJA": {
            "symbol": "ZS=F",
            "name": "CBOT Soja (Março/Julho)",
            "last_price_cents": 1185.25,
            "unit": "cents/bushel",
        },
        "MILHO": {
            "symbol": "ZC=F",
            "name": "CBOT Milho (Março/Julho)",
            "last_price_cents": 435.50,
            "unit": "cents/bushel",
        },
    },
    "port_premiums_cents": {
        "PNG": {"SOJA": 85.0, "MILHO": 55.0},
        "STS": {"SOJA": 90.0, "MILHO": 60.0},
        "RG": {"SOJA": 75.0, "MILHO": 50.0},
        "BCR": {"SOJA": 80.0, "MILHO": 55.0},
        "ITQ": {"SOJA": 82.0, "MILHO": 58.0},
    },
    "cash_prices_brl_bag": {
        "sorriso_mt": {"SOJA": 122.50, "MILHO": 48.00},
        "rondonopolis_mt": {"SOJA": 127.00, "MILHO": 52.50},
        "rio_verde_go": {"SOJA": 128.50, "MILHO": 54.00},
        "cascavel_pr": {"SOJA": 133.00, "MILHO": 58.00},
        "passo_fundo_rs": {"SOJA": 134.50, "MILHO": 60.00},
        "lem_ba": {"SOJA": 125.00, "MILHO": 50.00},
    },
    "forward_curve_months": [
        {"code": "MAR", "name": "Março", "cbot_soja": 1185.0, "premium_soja": 75.0, "usd_brl": 5.48},
        {"code": "MAI", "name": "Maio", "cbot_soja": 1202.0, "premium_soja": 82.0, "usd_brl": 5.51},
        {"code": "JUL", "name": "Julho", "cbot_soja": 1218.0, "premium_soja": 95.0, "usd_brl": 5.55},
        {"code": "AGO", "name": "Agosto", "cbot_soja": 1225.0, "premium_soja": 105.0, "usd_brl": 5.58},
        {"code": "SET", "name": "Setembro", "cbot_soja": 1230.0, "premium_soja": 115.0, "usd_brl": 5.61},
    ]
}


class MarketDataService:
    """
    Agregador de cotações para a mesa de operações.
    Integra Banco Central do Brasil (PTAX), provedores de futuros e tabelas locais.
    """

    def __init__(self):
        self._cache: Dict[str, Any] = deepcopy_seeds()
        self._last_updated: datetime = datetime.now()

    def get_snapshot(self) -> Dict[str, Any]:
        """Retorna todas as cotações atuais consolidadas."""
        return {
            "timestamp": self._last_updated.isoformat(),
            "data": self._cache,
        }

    def fetch_live_usd_brl(self) -> float:
        """
        Tenta coletar a taxa PTAX oficial do Banco Central do Brasil via API pública Olinda.
        Caso ocorra timeout ou erro de rede, utiliza o valor em cache.
        """
        try:
            today_str = date.today().strftime("%m-%d-%Y")
            url = (
                f"https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
                f"CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)?"
                f"@moeda='USD'&@dataCotacao='{today_str}'&$top=1&$orderby=dataHoraCotacao%20desc&$format=json"
            )
            response = requests.get(url, timeout=3.0)
            if response.status_code == 200:
                json_data = response.json()
                items = json_data.get("value", [])
                if items:
                    ptax_sell = float(items[0]["cotacaoVenda"])
                    self._cache["fx_usd_brl"] = ptax_sell
                    self._last_updated = datetime.now()
                    return ptax_sell
        except Exception as e:
            logger.warning(f"Não foi possível obter PTAX online: {e}. Mantendo valor em cache.")
            
        return float(self._cache["fx_usd_brl"])

    def get_fx_usd_brl(self) -> float:
        return float(self._cache["fx_usd_brl"])

    def set_fx_usd_brl(self, value: float) -> None:
        self._cache["fx_usd_brl"] = round(value, 4)
        self._last_updated = datetime.now()

    def get_cbot_price(self, commodity: str) -> float:
        com_key = commodity.upper()
        return float(self._cache["cbot_prices"][com_key]["last_price_cents"])

    def set_cbot_price(self, commodity: str, price_cents: float) -> None:
        com_key = commodity.upper()
        self._cache["cbot_prices"][com_key]["last_price_cents"] = round(price_cents, 2)
        self._last_updated = datetime.now()

    def get_port_premium(self, port_id: str, commodity: str) -> float:
        return float(self._cache["port_premiums_cents"].get(port_id, {}).get(commodity.upper(), 80.0))

    def set_port_premium(self, port_id: str, commodity: str, premium_cents: float) -> None:
        if port_id not in self._cache["port_premiums_cents"]:
            self._cache["port_premiums_cents"][port_id] = {}
        self._cache["port_premiums_cents"][port_id][commodity.upper()] = round(premium_cents, 2)
        self._last_updated = datetime.now()

    def get_cash_price(self, hub_id: str, commodity: str) -> Optional[float]:
        return self._cache["cash_prices_brl_bag"].get(hub_id, {}).get(commodity.upper())

    def get_forward_curve(self) -> list:
        return self._cache.get("forward_curve_months", [])


def deepcopy_seeds() -> Dict[str, Any]:
    import copy
    return copy.deepcopy(DEFAULT_MARKET_SEEDS)


# Instância singleton para uso na aplicação
market_service = MarketDataService()
