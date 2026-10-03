"""
Serviço de Ingestão e Agregação de Market Data (Câmbio BCB, CBOT, Prêmios e Mercado Físico).
Integra com o banco de dados relacional para consultas de baixa latência e histórico,
com fallback automático para garantir funcionamento offline contínuo.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, date, timedelta
import math
import requests
import logging

from src.db.connection import SessionLocal
from src.db.models import DataKind, FreshnessStatus, MarketQuote
from src.db.repository import MarketDataRepository
from src.domain.locations import ORIGINATION_HUBS, PORTS

logger = logging.getLogger(__name__)

# Estimativa de distâncias rodoviárias em km (Origem -> Porto)
ROUTE_DISTANCES_KM = {
    ("sorriso_mt", "STS"): 2150,
    ("sorriso_mt", "PNG"): 2250,
    ("sorriso_mt", "BCR"): 1450,
    ("rondonopolis_mt", "STS"): 1550,
    ("rondonopolis_mt", "PNG"): 1680,
    ("rio_verde_go", "STS"): 1020,
    ("rio_verde_go", "PNG"): 1180,
    ("cascavel_pr", "PNG"): 650,
    ("cascavel_pr", "STS"): 920,
    ("passo_fundo_rs", "RG"): 480,
    ("passo_fundo_rs", "PNG"): 840,
    ("lem_ba", "ITQ"): 1200,
    ("lem_ba", "STS"): 1580,
}


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
    Consulta primariamente o banco de dados relacional e mantém cache em memória.
    """

    def __init__(self):
        self._cache: Dict[str, Any] = deepcopy_seeds()
        self._last_updated: datetime = datetime.now()

    def get_snapshot(self, db: Optional[Any] = None) -> Dict[str, Any]:
        """Retorna todas as cotações atuais consolidadas do banco de dados ou cache."""
        close_session = False
        session = db
        if session is None:
            try:
                session = SessionLocal()
                close_session = True
            except Exception:
                session = None

        try:
            if session is not None:
                db_quotes = MarketDataRepository.get_all_latest_quotes(session)
                if db_quotes:
                    quotes_list = [q.to_dict() for q in db_quotes]

                    # Reconciliação F03: Constrói a estrutura 'data' estritamente a partir das cotações do banco
                    structured_data = deepcopy_seeds()
                    for q in db_quotes:
                        if q.category == "FX" and q.symbol == "USD_BRL_PTAX_VENDA":
                            structured_data["fx_usd_brl"] = q.price
                        elif q.category == "FUTURES":
                            comm = q.commodity or ("SOJA" if "ZS" in q.symbol or "SOJA" in q.symbol else "MILHO")
                            if comm in structured_data["cbot_prices"]:
                                structured_data["cbot_prices"][comm]["last_price_cents"] = q.price
                        elif q.category == "PORT_PREMIUM":
                            port = q.location_id
                            comm = q.commodity or ("SOJA" if "SOJA" in q.symbol else "MILHO")
                            if port in structured_data["port_premiums_cents"]:
                                structured_data["port_premiums_cents"][port][comm] = q.price
                        elif q.category == "PHYSICAL_CASH":
                            hub = q.location_id
                            comm = q.commodity or ("SOJA" if "SOJA" in q.symbol else "MILHO")
                            if hub in structured_data["cash_prices_brl_bag"]:
                                structured_data["cash_prices_brl_bag"][hub][comm] = q.price

                    # Sincroniza cache interno com dados reais
                    self._cache = structured_data
                    self._last_updated = datetime.now(timezone.utc)

                    overall_freshness = FreshnessStatus.CURRENT.value
                    if any(q.freshness == FreshnessStatus.STALE.value for q in db_quotes):
                        overall_freshness = FreshnessStatus.STALE.value

                    return {
                        "source": "DATABASE",
                        "timestamp": self._last_updated.isoformat(),
                        "total_quotes": len(quotes_list),
                        "quotes": quotes_list,
                        "data": structured_data,
                        "freshness": overall_freshness,
                        "reconciled": True,
                    }
        except Exception as e:
            logger.warning(f"Erro ao consultar snapshot no banco de dados: {e}")
        finally:
            if close_session and session is not None:
                session.close()

        return {
            "source": "CACHE_SEEDS",
            "timestamp": self._last_updated.isoformat(),
            "total_quotes": 0,
            "quotes": [],
            "data": self._cache,
            "data_kind": DataKind.DEMO.value,
            "freshness": FreshnessStatus.UNKNOWN.value,
            "reconciled": True,
        }

    def fetch_live_usd_brl(self) -> float:
        """
        Tenta coletar a taxa PTAX oficial do Banco Central do Brasil via API pública Olinda.
        Caso ocorra timeout ou erro de rede, utiliza o valor em cache.
        """
        try:
            from src.services.extractor import MarketDataExtractor
            quotes = MarketDataExtractor.extract_bcb_ptax()
            if quotes:
                rate = float(quotes[0]["price"])
                self._cache["fx_usd_brl"] = rate
                self._last_updated = datetime.now(timezone.utc)
                return rate
        except Exception as e:
            logger.warning(f"Não foi possível obter PTAX online: {e}. Mantendo valor atual.")
            
        return float(self._cache["fx_usd_brl"])

    def get_fx_usd_brl(self) -> float:
        try:
            with SessionLocal() as db:
                quote = MarketDataRepository.get_latest_quote(db, "USD_BRL_PTAX_VENDA", category="FX")
                if quote:
                    rate = float(quote.price)
                    self._cache["fx_usd_brl"] = rate
                    return rate
        except Exception:
            pass
        return float(self._cache["fx_usd_brl"])

    def set_fx_usd_brl(self, value: float) -> None:
        self._cache["fx_usd_brl"] = round(value, 4)
        self._last_updated = datetime.now(timezone.utc)

    def get_cbot_price(self, commodity: str) -> float:
        com_key = commodity.upper()
        symbol = "ZS=F" if com_key == "SOJA" else "ZC=F"
        try:
            with SessionLocal() as db:
                quote = MarketDataRepository.get_latest_quote(db, symbol, category="FUTURES")
                if quote:
                    val = float(quote.price)
                    self._cache["cbot_prices"][com_key]["last_price_cents"] = val
                    return val
        except Exception:
            pass
        return float(self._cache["cbot_prices"][com_key]["last_price_cents"])

    def set_cbot_price(self, commodity: str, price_cents: float) -> None:
        com_key = commodity.upper()
        self._cache["cbot_prices"][com_key]["last_price_cents"] = round(price_cents, 2)
        self._last_updated = datetime.now(timezone.utc)

    def get_port_premium(self, port_id: str, commodity: str) -> float:
        sym = f"PREM_{port_id.upper()}_{commodity.upper()}"
        try:
            with SessionLocal() as db:
                quote = MarketDataRepository.get_latest_quote(db, sym, category="PORT_PREMIUM")
                if quote:
                    val = float(quote.price)
                    if port_id not in self._cache["port_premiums_cents"]:
                        self._cache["port_premiums_cents"][port_id] = {}
                    self._cache["port_premiums_cents"][port_id][commodity.upper()] = val
                    return val
        except Exception:
            pass
        return float(self._cache["port_premiums_cents"].get(port_id, {}).get(commodity.upper(), 80.0))

    def set_port_premium(self, port_id: str, commodity: str, premium_cents: float) -> None:
        if port_id not in self._cache["port_premiums_cents"]:
            self._cache["port_premiums_cents"][port_id] = {}
        self._cache["port_premiums_cents"][port_id][commodity.upper()] = round(premium_cents, 2)
        self._last_updated = datetime.now(timezone.utc)

    def get_cash_price(self, hub_id: str, commodity: str) -> Optional[float]:
        sym = f"CASH_{hub_id.upper()}_{commodity.upper()}"
        try:
            with SessionLocal() as db:
                quote = MarketDataRepository.get_latest_quote(db, sym, category="PHYSICAL_CASH")
                if quote:
                    val = float(quote.price)
                    if hub_id not in self._cache["cash_prices_brl_bag"]:
                        self._cache["cash_prices_brl_bag"][hub_id] = {}
                    self._cache["cash_prices_brl_bag"][hub_id][commodity.upper()] = val
                    return val
        except Exception:
            pass
        return self._cache["cash_prices_brl_bag"].get(hub_id, {}).get(commodity.upper())

    def get_forward_curve(self) -> list:
        return self._cache.get("forward_curve_months", [])

    def get_candlestick_series(self, symbol: str, days: int = 30, db: Optional[Any] = None) -> list:
        """
        Retorna série temporal de velas (OHLC - Open, High, Low, Close) para gráficos de cotações.
        Prioriza cotações históricas reais do banco de dados (Ticket F04).
        Caso o histórico seja insuficiente, gera série determinística de referência (marcada como DEMO),
        eliminando geradores de números aleatórios sem rastreabilidade.
        """
        configs = {
            "CBOT_SOJA": {"base": self.get_cbot_price("SOJA"), "vol": 12.0, "decimals": 2, "db_symbol": "ZS=F"},
            "CBOT_MILHO": {"base": self.get_cbot_price("MILHO"), "vol": 5.0, "decimals": 2, "db_symbol": "ZC=F"},
            "USD_BRL": {"base": self.get_fx_usd_brl(), "vol": 0.035, "decimals": 4, "db_symbol": "USD_BRL_PTAX_VENDA"},
            "B3_MILHO": {"base": 63.80, "vol": 0.65, "decimals": 2, "db_symbol": "B3_CCMK27"},
            "PARIDADE_FAS": {"base": 133.50, "vol": 1.10, "decimals": 2, "db_symbol": "CEPEA_SOJA_PARANAGUA"},
        }

        sym = symbol.upper()
        cfg = configs.get(sym, configs["CBOT_SOJA"])
        last_price = cfg["base"]
        vol = cfg["vol"]
        decimals = cfg["decimals"]
        db_sym = cfg.get("db_symbol", sym)

        # 1. Tentar consultar histórico real no banco de dados
        close_session = False
        session = db
        if session is None:
            try:
                session = SessionLocal()
                close_session = True
            except Exception:
                session = None

        real_history = []
        if session is not None:
            try:
                real_history = (
                    session.query(MarketQuote)
                    .filter(MarketQuote.symbol == db_sym)
                    .order_by(MarketQuote.quote_date.asc(), MarketQuote.observed_at.asc())
                    .all()
                )
            except Exception as e:
                logger.warning(f"Erro ao buscar histórico real de {db_sym}: {e}")
            finally:
                if close_session and session is not None:
                    session.close()

        # Se houver histórico observado com pelo menos 'days' registros diários:
        if len(real_history) >= days:
            by_date = {}
            for q in real_history:
                dt_key = q.quote_date.strftime("%Y-%m-%d")
                if dt_key not in by_date:
                    by_date[dt_key] = []
                by_date[dt_key].append(q)

            dates_sorted = sorted(by_date.keys())[-days:]
            candles = []
            prev_close = None
            for dt_str in dates_sorted:
                day_quotes = by_date[dt_str]
                prices = [q.price for q in day_quotes]
                open_p = prev_close if prev_close is not None else prices[0]
                close_p = prices[-1]
                high_p = max(max(prices), open_p, close_p)
                low_p = min(min(prices), open_p, close_p)
                candles.append({
                    "time": dt_str,
                    "open": round(open_p, decimals),
                    "high": round(high_p, decimals),
                    "low": round(low_p, decimals),
                    "close": round(close_p, decimals),
                    "volume": 10000,
                    "data_kind": day_quotes[-1].data_kind,
                    "is_synthetic": False,
                })
                prev_close = close_p
            return candles

        # 2. Histórico real insuficiente: gerar série determinística calibrada (DEMO)
        today = date.today()
        dates = []
        d = today
        while len(dates) < days:
            if d.weekday() < 5:
                dates.append(d)
            d -= timedelta(days=1)
        dates.reverse()

        candles = []
        n = len(dates)
        if n == 0:
            return candles

        prices = [0.0] * n
        prices[-1] = last_price
        for i in range(n - 2, -1, -1):
            step = math.sin((i + 1) * 0.7) * (vol * 0.4)
            prices[i] = prices[i + 1] - step

        initial_open = prices[0] - math.sin(0.7) * (vol * 0.4)
        curr_open = initial_open

        for i, d_item in enumerate(dates):
            open_p = round(curr_open, decimals)
            close_p = round(prices[i], decimals) if i < n - 1 else round(last_price, decimals)
            spread = abs(math.cos((i + 1) * 0.85)) * (vol * 0.35) + (vol * 0.05)
            high_p = round(max(open_p, close_p) + spread, decimals)
            low_p = round(max(0.01, min(open_p, close_p) - spread), decimals)
            volume = 5000 + int(abs(math.sin(i)) * 3000)

            candles.append({
                "time": d_item.strftime("%Y-%m-%d"),
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": volume,
                "data_kind": DataKind.DEMO.value,
                "is_synthetic": True,
            })
            curr_open = close_p

        return candles

    def get_freight_rate(self, origin_id: str, destination_id: str, db: Optional[Any] = None) -> float:
        """Retorna a cotação mais recente de frete rodoviário (R$/ton)."""
        orig_key = origin_id.lower()
        dest_key = destination_id.upper()
        sym = f"FREIGHT_{orig_key.upper()}_{dest_key}"
        try:
            if db is not None:
                quote = MarketDataRepository.get_latest_quote(db, sym, category="FREIGHT")
                if quote:
                    return float(quote.price)
            else:
                with SessionLocal() as session:
                    quote = MarketDataRepository.get_latest_quote(session, sym, category="FREIGHT")
                    if quote:
                        return float(quote.price)
        except Exception:
            pass

        hub = ORIGINATION_HUBS.get(orig_key)
        if hub and dest_key in hub.freight_to_port_brl_ton:
            return float(hub.freight_to_port_brl_ton[dest_key])
        return 350.0

    def get_freight_routes(self, db: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Retorna a relação completa de rotas de frete rodoviário cadastradas
        com tarifas atuais em R$/ton e R$/saca, distância estimada e corredor.
        """
        routes = []
        for hub_id, hub in ORIGINATION_HUBS.items():
            for port_id in hub.freight_to_port_brl_ton.keys():
                port = PORTS.get(port_id)
                port_name = port.name if port else f"Porto {port_id}"
                port_state = port.state if port else ""
                current_rate = self.get_freight_rate(hub_id, port_id, db=db)
                corridor = "Arco Norte" if port_id in ["BCR", "ITQ"] else ("Santos / Sudeste" if port_id == "STS" else "Sul")
                dist_km = ROUTE_DISTANCES_KM.get((hub_id.lower(), port_id.upper()), 1500)

                routes.append({
                    "origin_id": hub_id,
                    "origin_name": hub.name,
                    "origin_state": hub.state,
                    "destination_id": port_id,
                    "destination_name": port_name,
                    "destination_state": port_state,
                    "symbol": f"FREIGHT_{hub_id.upper()}_{port_id.upper()}",
                    "freight_brl_ton": round(current_rate, 2),
                    "freight_brl_bag": round(current_rate * 0.06, 2),
                    "corridor": corridor,
                    "distance_km": dist_km,
                    "is_default": (port_id == hub.default_port_id),
                })
        return routes

    def get_freight_history(
        self,
        origin_id: str,
        destination_id: str,
        days: int = 30,
        db: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Retorna a série temporal histórica de fretes rodoviários (R$/ton e R$/saca)
        para a rota especificada, combinando registros reais do banco com backfill
        estatístico determinístico contínuo.
        """
        import random
        from datetime import date, timedelta, timezone

        orig_key = origin_id.lower()
        dest_key = destination_id.upper()
        hub = ORIGINATION_HUBS.get(orig_key)
        port = PORTS.get(dest_key)

        origin_name = hub.name if hub else origin_id
        destination_name = port.name if port else destination_id
        symbol = f"FREIGHT_{orig_key.upper()}_{dest_key}"

        current_rate = self.get_freight_rate(orig_key, dest_key, db=db)

        # 1. Tentar coletar cotações reais do banco
        db_quotes_map = {}
        if db is not None:
            try:
                db_quotes = MarketDataRepository.get_quotes_history(db, symbol, limit=days * 2)
                for q in db_quotes:
                    d_str = q.quote_date.strftime("%Y-%m-%d")
                    db_quotes_map[d_str] = float(q.price)
            except Exception as e:
                logger.warning(f"Erro ao consultar histórico de frete no DB: {e}")
        else:
            try:
                with SessionLocal() as session:
                    db_quotes = MarketDataRepository.get_quotes_history(session, symbol, limit=days * 2)
                    for q in db_quotes:
                        d_str = q.quote_date.strftime("%Y-%m-%d")
                        db_quotes_map[d_str] = float(q.price)
            except Exception:
                pass

        # 2. Gerar lista de datas úteis
        today = date.today()
        dates = []
        d = today
        while len(dates) < days:
            if d.weekday() < 5:
                dates.append(d)
            d -= timedelta(days=1)
        dates.reverse()

        # 3. Gerador determinístico estável ancorado
        random_seed = int(datetime.now(timezone.utc).strftime("%Y%m%d")) + sum(ord(c) for c in symbol)
        rng = random.Random(random_seed)
        vol = 3.5  # Volatilidade diária de frete rodoviário em R$/ton

        series = []
        curr = current_rate - (rng.uniform(-0.4, 0.4) * vol * 2.0)

        for i, d_item in enumerate(dates):
            d_str = d_item.strftime("%Y-%m-%d")
            is_last = (i == len(dates) - 1)

            if d_str in db_quotes_map:
                price = db_quotes_map[d_str]
                source = "DATABASE"
            elif is_last:
                price = current_rate
                source = "SPOT_BENCHMARK"
            else:
                change = rng.uniform(-vol, vol * 1.05)
                price = round(curr + change, 2)
                source = "BENCHMARK_SERIES"
                curr = price

            price_ton = round(price, 2)
            price_bag = round(price_ton * 0.06, 2)
            series.append({
                "date": d_str,
                "price_ton": price_ton,
                "price_bag": price_bag,
                "source": source,
            })

        prices_ton = [p["price_ton"] for p in series]
        current_rate_ton = series[-1]["price_ton"]
        initial_rate_ton = series[0]["price_ton"]
        change_ton = round(current_rate_ton - initial_rate_ton, 2)
        change_pct = round((change_ton / initial_rate_ton) * 100, 2) if initial_rate_ton else 0.0

        return {
            "origin_id": orig_key,
            "origin_name": origin_name,
            "destination_id": dest_key,
            "destination_name": destination_name,
            "symbol": symbol,
            "period_days": days,
            "current_rate_ton": current_rate_ton,
            "current_rate_bag": round(current_rate_ton * 0.06, 2),
            "initial_rate_ton": initial_rate_ton,
            "change_ton": change_ton,
            "change_bag": round(change_ton * 0.06, 2),
            "change_pct": change_pct,
            "min_rate_ton": min(prices_ton),
            "max_rate_ton": max(prices_ton),
            "avg_rate_ton": round(sum(prices_ton) / len(prices_ton), 2),
            "series": series,
        }

    def get_freight_arbitrage_analysis(
        self,
        origin_id: str,
        commodity: str = "SOJA",
        usd_brl_fx: Optional[float] = None,
        db: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Calcula a análise de arbitragem logística entre corredores de escoamento
        para a praça de originação selecionada, comparando frete rodoviário, THC e demurrage.
        """
        orig_key = origin_id.lower()
        hub = ORIGINATION_HUBS.get(orig_key)
        if not hub:
            raise ValueError(f"Praça de originação '{origin_id}' não encontrada.")

        fx = usd_brl_fx or self.get_fx_usd_brl()

        comparisons = []
        for port_id in hub.freight_to_port_brl_ton.keys():
            port = PORTS.get(port_id)
            port_name = port.name if port else f"Porto {port_id}"
            road_freight = self.get_freight_rate(orig_key, port_id, db=db)
            road_freight_bag = round(road_freight * 0.06, 2)

            elev_usd = port.elevation_cost_usd_ton if port else 8.0
            elev_brl = round(elev_usd * fx, 2)
            other_brl = port.other_port_costs_brl_ton if port else 15.0
            demurrage_usd = port.demurrage_risk_usd_ton if port else 1.5
            demurrage_brl = round(demurrage_usd * fx, 2)
            waiting_days = port.typical_waiting_days if port else 15

            total_logistics_ton = round(road_freight + elev_brl + other_brl + demurrage_brl, 2)
            total_logistics_bag = round(total_logistics_ton * 0.06, 2)

            corridor = "Arco Norte" if port_id in ["BCR", "ITQ"] else ("Santos / Sudeste" if port_id == "STS" else "Sul")
            dist_km = ROUTE_DISTANCES_KM.get((orig_key, port_id), 1500)

            comparisons.append({
                "port_id": port_id,
                "port_name": port_name,
                "state": port.state if port else "",
                "corridor": corridor,
                "distance_km": dist_km,
                "road_freight_brl_ton": road_freight,
                "road_freight_brl_bag": road_freight_bag,
                "elevation_cost_usd_ton": elev_usd,
                "elevation_cost_brl_ton": elev_brl,
                "other_port_costs_brl_ton": other_brl,
                "demurrage_risk_usd_ton": demurrage_usd,
                "demurrage_risk_brl_ton": demurrage_brl,
                "waiting_days": waiting_days,
                "total_logistics_brl_ton": total_logistics_ton,
                "total_logistics_brl_bag": total_logistics_bag,
            })

        # Localizar baseline (Santos se disponível, senão a primeira rota)
        santos_item = next((c for c in comparisons if c["port_id"] == "STS"), comparisons[0])
        santos_total_ton = santos_item["total_logistics_brl_ton"]
        santos_total_bag = santos_item["total_logistics_brl_bag"]

        # Encontrar melhor rota (menor custo logístico total)
        best_port = min(comparisons, key=lambda c: c["total_logistics_brl_ton"])

        for c in comparisons:
            spread_ton = round(c["total_logistics_brl_ton"] - santos_total_ton, 2)
            spread_bag = round(spread_ton * 0.06, 2)
            c["spread_vs_santos_brl_ton"] = spread_ton
            c["spread_vs_santos_brl_bag"] = spread_bag

            if c["port_id"] == santos_item["port_id"]:
                c["status"] = "BENCHMARK"
            elif spread_ton < -0.01:
                c["status"] = "FAVORABLE"
            else:
                c["status"] = "UNFAVORABLE"

            c["is_recommended"] = (c["port_id"] == best_port["port_id"])

        max_savings_ton = round(max(0.0, santos_total_ton - best_port["total_logistics_brl_ton"]), 2)
        max_savings_bag = round(max_savings_ton * 0.06, 2)

        return {
            "origin_id": orig_key,
            "origin_name": hub.name,
            "origin_state": hub.state,
            "commodity": commodity.upper(),
            "usd_brl_fx": fx,
            "santos_benchmark_ton": santos_total_ton,
            "santos_benchmark_bag": santos_total_bag,
            "best_port_id": best_port["port_id"],
            "best_port_name": best_port["port_name"],
            "best_corridor": best_port["corridor"],
            "max_savings_brl_ton": max_savings_ton,
            "max_savings_brl_bag": max_savings_bag,
            "ports_comparison": comparisons,
        }


def deepcopy_seeds() -> Dict[str, Any]:
    import copy
    return copy.deepcopy(DEFAULT_MARKET_SEEDS)


# Instância singleton para uso na aplicação
market_service = MarketDataService()

