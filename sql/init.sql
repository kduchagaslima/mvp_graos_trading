-- ==============================================================================
-- Schema DDL Oficial para PostgreSQL: Grain Trading Market Data
-- Otimizado com Índices Compostos e Constraints Únicas de Baixa Latência
-- ==============================================================================

-- 1. Tabela Principal de Cotações de Mercado (Time-Series Indexada)
CREATE TABLE IF NOT EXISTS market_quotes (
    id SERIAL PRIMARY KEY,
    quote_date DATE NOT NULL,
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    category VARCHAR(32) NOT NULL,        -- FX, FUTURES, PORT_PREMIUM, PHYSICAL_CASH, FREIGHT
    commodity VARCHAR(16),                 -- SOJA, MILHO
    symbol VARCHAR(64) NOT NULL,           -- USD_BRL_PTAX_VENDA, ZS=F, PREM_STS_SOJA, etc.
    contract_code VARCHAR(32) DEFAULT 'SPOT', -- SPOT, PROMPT, MAR25, JUL25
    location_id VARCHAR(32) DEFAULT 'GLOBAL', -- sorriso_mt, STS, PNG, etc.
    price DOUBLE PRECISION NOT NULL,
    unit VARCHAR(32) NOT NULL,             -- BRL, cents/bu, R$/saca, R$/ton
    source VARCHAR(64) NOT NULL,           -- BCB_PTAX_OLINDA, CME, CEPEA
    metadata_json TEXT,
    CONSTRAINT uq_quote_natural_key UNIQUE (quote_date, category, symbol, contract_code, location_id)
);

-- Índices Compostos para Consultas em Tempo Real
CREATE INDEX IF NOT EXISTS idx_quotes_latest ON market_quotes (category, symbol, quote_date DESC);
CREATE INDEX IF NOT EXISTS idx_quotes_commodity_date ON market_quotes (commodity, category, quote_date);
CREATE INDEX IF NOT EXISTS idx_quotes_lookup ON market_quotes (symbol, contract_code, quote_date);

-- 2. Tabela de Histórico de Paridade Calculada
CREATE TABLE IF NOT EXISTS parity_snapshots (
    id SERIAL PRIMARY KEY,
    calculation_date DATE NOT NULL,
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    commodity VARCHAR(16) NOT NULL,
    hub_id VARCHAR(32) NOT NULL,
    port_id VARCHAR(16) NOT NULL,
    cbot_cents DOUBLE PRECISION NOT NULL,
    premium_cents DOUBLE PRECISION NOT NULL,
    fx_rate DOUBLE PRECISION NOT NULL,
    fob_usd_ton DOUBLE PRECISION NOT NULL,
    fob_brl_bag DOUBLE PRECISION NOT NULL,
    freight_brl_bag DOUBLE PRECISION NOT NULL,
    net_parity_brl_bag DOUBLE PRECISION NOT NULL,
    cash_price_brl_bag DOUBLE PRECISION,
    originator_spread_brl_bag DOUBLE PRECISION,
    originator_margin_pct DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_parity_hub_date ON parity_snapshots (hub_id, commodity, calculation_date);

-- 3. Tabela de Governança e Auditoria ETL
CREATE TABLE IF NOT EXISTS extraction_logs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(16) NOT NULL,           -- RUNNING, SUCCESS, FAILED
    records_extracted INTEGER DEFAULT 0,
    records_upserted INTEGER DEFAULT 0,
    sources_contacted VARCHAR(255),
    details_json TEXT,
    error_message TEXT
);
