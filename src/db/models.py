"""
Modelagem Relacional de Dados de Mercado e Trading de Grãos.
Estruturado para alta performance em consultas analíticas e séries temporais.
"""

from datetime import datetime, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    Text,
    Index,
    UniqueConstraint,
)
from src.db.connection import Base


class MarketQuote(Base):
    """
    Tabela central de cotações de mercado temporalmente indexada.
    Consolida FX, CBOT, Prêmios nos Portos, Preços Físicos no Interior e Fretes.
    """
    __tablename__ = "market_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    quote_date = Column(Date, nullable=False, default=date.today)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    category = Column(String(32), nullable=False)  # FX, FUTURES, PORT_PREMIUM, PHYSICAL_CASH, FREIGHT
    commodity = Column(String(16), nullable=True)  # SOJA, MILHO, etc.
    symbol = Column(String(64), nullable=False)    # USD_BRL_PTAX, ZS=F, PREM_STS_SOJA, etc.
    contract_code = Column(String(32), nullable=True, default="SPOT")  # SPOT, MAR25, MAY25, JUL25
    location_id = Column(String(32), nullable=True, default="GLOBAL")  # sorriso_mt, STS, PNG, etc.
    price = Column(Float, nullable=False)
    unit = Column(String(32), nullable=False)      # BRL, cents/bu, USD/ton, R$/saca, R$/ton
    source = Column(String(64), nullable=False)    # BCB_PTAX, YAHOO_FINANCE, CEPEA_ESALQ, MANUAL
    metadata_json = Column(Text, nullable=True)    # Detalhes adicionais em formato JSON

    __table_args__ = (
        # Garante idempotência: apenas 1 cotação por combinação de chave natural no mesmo dia
        UniqueConstraint(
            "quote_date",
            "category",
            "symbol",
            "contract_code",
            "location_id",
            name="uq_quote_natural_key",
        ),
        # Índices compostos de alta performance para consumo otimizado
        Index("idx_quotes_latest", "category", "symbol", "quote_date"),
        Index("idx_quotes_commodity_date", "commodity", "category", "quote_date"),
        Index("idx_quotes_lookup", "symbol", "contract_code", "quote_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "quote_date": self.quote_date.isoformat() if self.quote_date else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "category": self.category,
            "commodity": self.commodity,
            "symbol": self.symbol,
            "contract_code": self.contract_code,
            "location_id": self.location_id,
            "price": self.price,
            "unit": self.unit,
            "source": self.source,
        }


class ParitySnapshot(Base):
    """
    Histórico de preços de paridade calculados e spreads de originação para analytics/BI.
    """
    __tablename__ = "parity_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    calculation_date = Column(Date, nullable=False, default=date.today)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    commodity = Column(String(16), nullable=False)
    hub_id = Column(String(32), nullable=False)
    port_id = Column(String(16), nullable=False)
    
    # Variáveis base no momento do cálculo
    cbot_cents = Column(Float, nullable=False)
    premium_cents = Column(Float, nullable=False)
    fx_rate = Column(Float, nullable=False)
    fob_usd_ton = Column(Float, nullable=False)
    fob_brl_bag = Column(Float, nullable=False)
    freight_brl_bag = Column(Float, nullable=False)
    
    # Resultados calculados
    net_parity_brl_bag = Column(Float, nullable=False)
    cash_price_brl_bag = Column(Float, nullable=True)
    originator_spread_brl_bag = Column(Float, nullable=True)
    originator_margin_pct = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_parity_hub_date", "hub_id", "commodity", "calculation_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "calculation_date": self.calculation_date.isoformat(),
            "commodity": self.commodity,
            "hub_id": self.hub_id,
            "port_id": self.port_id,
            "net_parity_brl_bag": self.net_parity_brl_bag,
            "cash_price_brl_bag": self.cash_price_brl_bag,
            "originator_spread_brl_bag": self.originator_spread_brl_bag,
            "originator_margin_pct": self.originator_margin_pct,
        }


class ExtractionLog(Base):
    """
    Tabela de auditoria, governança e observabilidade de extrações de Market Data.
    """
    __tablename__ = "extraction_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False)  # RUNNING, SUCCESS, PARTIAL, FAILED
    records_extracted = Column(Integer, default=0)
    records_upserted = Column(Integer, default=0)
    sources_contacted = Column(String(255), nullable=True)
    details_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "records_extracted": self.records_extracted,
            "records_upserted": self.records_upserted,
            "sources_contacted": self.sources_contacted,
            "error_message": self.error_message,
        }
