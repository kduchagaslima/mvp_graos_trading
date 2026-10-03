"""
Modelagem Relacional de Dados de Mercado e Trading de Grãos.
Estruturado para alta performance em consultas analíticas e séries temporais,
com suporte a rastreabilidade em dois eixos (data_kind e freshness) e precisão Decimal.
"""

from datetime import datetime, date, timezone
from enum import Enum
from decimal import Decimal
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Numeric,
    Date,
    DateTime,
    Text,
    Index,
    UniqueConstraint,
    TypeDecorator,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from src.db.connection import Base


class UTCDateTime(TypeDecorator):
    """Garante que datetimes retornados do banco sejam sempre timezone-aware em UTC."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class DataKind(str, Enum):
    """Eixo 1 da Auditoria: Origem e Providência do Dado."""
    OBSERVED = "OBSERVED"       # Coletado diretamente de fonte oficial verificada
    MANUAL = "MANUAL"           # Inserido manualmente pelo operador
    ESTIMATED = "ESTIMATED"     # Calculado ou projetado matematicamente
    DEMO = "DEMO"               # Cotação de seed/demonstração
    UNVERIFIED = "UNVERIFIED"   # Dado legado cuja procedência não pode ser auditada


class FreshnessStatus(str, Enum):
    """Eixo 2 da Auditoria: Atualidade e Tolerância Temporal."""
    CURRENT = "CURRENT"  # Atual dentro da tolerância de calendário
    STALE = "STALE"      # Defasado além da tolerância esperada
    UNKNOWN = "UNKNOWN"  # Sem data de observação para cálculo


class MarketQuote(Base):
    """
    Tabela central de cotações de mercado temporalmente indexada.
    Consolida FX, CBOT, Prêmios nos Portos, Preços Físicos no Interior e Fretes,
    com eixos explícitos de providência (data_kind), frescor (freshness) e precisão numérica.
    """
    __tablename__ = "market_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    quote_date = Column(Date, nullable=False, default=date.today)
    timestamp = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    category = Column(String(32), nullable=False)  # FX, FUTURES, PORT_PREMIUM, PHYSICAL_CASH, FREIGHT, B3_FUTURES, MACRO_INDEX
    commodity = Column(String(16), nullable=True)  # SOJA, MILHO, etc.
    symbol = Column(String(64), nullable=False)    # USD_BRL_PTAX, ZS=F, PREM_STS_SOJA, etc.
    contract_code = Column(String(32), nullable=True, default="SPOT")  # SPOT, MAR25, MAY25, JUL25
    location_id = Column(String(32), nullable=True, default="GLOBAL")  # sorriso_mt, STS, PNG, etc.
    price = Column(Float, nullable=False)
    price_numeric = Column(Numeric(14, 4), nullable=True)
    unit = Column(String(32), nullable=False)      # BRL, cents/bu, USD/ton, R$/saca, R$/ton
    currency = Column(String(8), nullable=False, default="BRL")
    source = Column(String(64), nullable=False)    # BCB_PTAX, YAHOO_FINANCE, CEPEA_ESALQ, MANUAL, SEED_FALLBACK
    source_vendor = Column(String(64), nullable=True)
    source_reference = Column(String(128), nullable=True)
    contract_expiry = Column(Date, nullable=True)
    payload_hash = Column(String(64), nullable=True)
    metadata_json = Column(Text, nullable=True)    # Detalhes adicionais em formato JSON

    # Eixos de Rastreabilidade e Auditoria (Ticket F02)
    data_kind = Column(String(16), nullable=False, default=DataKind.OBSERVED.value)
    freshness = Column(String(16), nullable=False, default=FreshnessStatus.CURRENT.value)
    observed_at = Column(UTCDateTime, nullable=True)
    ingested_at = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

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
        Index("idx_quotes_observed_at", "symbol", "observed_at"),
    )

    def to_dict(self):
        obs_iso = self.observed_at.isoformat() if self.observed_at else (self.timestamp.isoformat() if self.timestamp else None)
        return {
            "id": self.id,
            "quote_date": self.quote_date.isoformat() if self.quote_date else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "observed_at": obs_iso,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "category": self.category,
            "commodity": self.commodity,
            "symbol": self.symbol,
            "contract_code": self.contract_code,
            "location_id": self.location_id,
            "price": self.price,
            "price_numeric": float(self.price_numeric) if self.price_numeric is not None else self.price,
            "unit": self.unit,
            "currency": self.currency,
            "source": self.source,
            "source_vendor": self.source_vendor,
            "source_reference": self.source_reference,
            "data_kind": self.data_kind,
            "freshness": self.freshness,
        }


class ParitySnapshot(Base):
    """
    Histórico de preços de paridade calculados e spreads de originação para analytics/BI.
    """
    __tablename__ = "parity_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    calculation_date = Column(Date, nullable=False, default=date.today)
    timestamp = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
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
    started_at = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(UTCDateTime, nullable=True)
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


# ==============================================================================
# Modelos de Identidade, Organizações, RBAC e Custos Privados (Tickets F09, F10)
# ==============================================================================

class MembershipRole(str, Enum):
    """Papéis permitidos dentro de uma organização."""
    OWNER = "OWNER"
    ANALYST = "ANALYST"
    READER = "READER"


class User(Base):
    """
    Identidade do usuário autenticado vinculada ao sub do Amazon Cognito.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cognito_sub = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_platform_operator = Column(Boolean, nullable=False, default=False)
    created_at = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "cognito_sub": self.cognito_sub,
            "email": self.email,
            "name": self.name,
            "is_active": self.is_active,
            "is_platform_operator": self.is_platform_operator,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Organization(Base):
    """
    Empresa / Tenant da plataforma (segregação de dados e custos privados).
    """
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    cost_profiles = relationship("CostProfile", back_populates="organization", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Membership(Base):
    """
    Vínculo de um usuário a uma organização com papel (RBAC: OWNER, ANALYST, READER).
    """
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False, default=MembershipRole.ANALYST.value)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "organization_name": self.organization.name if self.organization else None,
            "organization_slug": self.organization.slug if self.organization else None,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CostProfile(Base):
    """
    Perfil privado de custos e margens de originação específico de cada empresa (Tenant).
    Garante que parâmetros privados de corretagem e margens não vazem entre empresas.
    """
    __tablename__ = "cost_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False, default="Padrão")
    brokerage_margin_usd_ton = Column(Float, nullable=False, default=2.0)
    brokerage_fee_brl_bag = Column(Float, nullable=False, default=0.0)
    brokerage_payer = Column(String(16), nullable=False, default="NONE")  # NONE, TRADING, SELLER
    default_funrural_pct = Column(Float, nullable=False, default=1.5)
    default_shrinkage_loss_pct = Column(Float, nullable=False, default=0.3)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="cost_profiles")

    def to_dict(self):
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "brokerage_margin_usd_ton": self.brokerage_margin_usd_ton,
            "brokerage_fee_brl_bag": self.brokerage_fee_brl_bag,
            "brokerage_payer": self.brokerage_payer,
            "default_funrural_pct": self.default_funrural_pct,
            "default_shrinkage_loss_pct": self.default_shrinkage_loss_pct,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
