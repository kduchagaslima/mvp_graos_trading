-- ==============================================================================
-- Migração 009: Alertas de Mercado e Metas de Preço (Watchlist da Mesa)
-- Permite que operadores e analistas cadastrem regras e metas de preço
-- (paridade FAS, spread balcão, CBOT e variação cambial PTAX).
-- ==============================================================================

CREATE TABLE IF NOT EXISTS market_alerts (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(128) NOT NULL,
    alert_type VARCHAR(32) NOT NULL,
    commodity VARCHAR(16) NOT NULL DEFAULT 'SOJA',
    hub_id VARCHAR(32),
    port_id VARCHAR(16),
    target_value DOUBLE PRECISION NOT NULL,
    current_value DOUBLE PRECISION,
    is_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    triggered_at TIMESTAMP WITH TIME ZONE,
    trigger_count INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notification_channel VARCHAR(32) NOT NULL DEFAULT 'IN_APP',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_market_alerts_org ON market_alerts (organization_id);
CREATE INDEX IF NOT EXISTS idx_market_alerts_active ON market_alerts (organization_id, is_active);
CREATE INDEX IF NOT EXISTS idx_market_alerts_triggered ON market_alerts (organization_id, is_triggered);
