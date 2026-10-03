-- ==============================================================================
-- Migração 001: Schema Inicial do MVP AgriTrading
-- Baseline: Commit 693a541897c78c6e7d60638e1bbae1b5068079f8
-- ==============================================================================

CREATE TABLE IF NOT EXISTS market_quotes (
    id SERIAL PRIMARY KEY,
    quote_date DATE NOT NULL,
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    category VARCHAR(32) NOT NULL,
    commodity VARCHAR(16),
    symbol VARCHAR(64) NOT NULL,
    contract_code VARCHAR(32) DEFAULT 'SPOT',
    location_id VARCHAR(32) DEFAULT 'GLOBAL',
    price DOUBLE PRECISION NOT NULL,
    unit VARCHAR(32) NOT NULL,
    source VARCHAR(64) NOT NULL,
    metadata_json TEXT,
    CONSTRAINT uq_quote_natural_key UNIQUE (quote_date, category, symbol, contract_code, location_id)
);

CREATE INDEX IF NOT EXISTS idx_quotes_latest ON market_quotes (category, symbol, quote_date);
CREATE INDEX IF NOT EXISTS idx_quotes_commodity_date ON market_quotes (commodity, category, quote_date);
CREATE INDEX IF NOT EXISTS idx_quotes_lookup ON market_quotes (symbol, contract_code, quote_date);

CREATE TABLE IF NOT EXISTS parity_snapshots (
    id SERIAL PRIMARY KEY,
    calculation_date DATE NOT NULL,
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
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

CREATE TABLE IF NOT EXISTS extraction_logs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(16) NOT NULL,
    records_extracted INTEGER DEFAULT 0,
    records_upserted INTEGER DEFAULT 0,
    sources_contacted VARCHAR(255),
    details_json TEXT,
    error_message TEXT
);
