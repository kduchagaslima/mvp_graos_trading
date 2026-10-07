-- ==============================================================================
-- Migração 005: Cenários Salvos de Paridade por Organização (Ticket U03)
-- Suporte ao salvamento e recuperação de simulações personalizadas por empresa
-- ==============================================================================

CREATE TABLE IF NOT EXISTS saved_scenarios (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    commodity VARCHAR(16) NOT NULL,
    hub_id VARCHAR(32) NOT NULL,
    port_id VARCHAR(16) NOT NULL,
    cbot_price_cents DOUBLE PRECISION NOT NULL,
    port_premium_cents DOUBLE PRECISION NOT NULL,
    usd_brl_fx DOUBLE PRECISION NOT NULL,
    freight_cost_brl_ton DOUBLE PRECISION NOT NULL,
    elevation_cost_usd_ton DOUBLE PRECISION NOT NULL,
    demurrage_risk_usd_ton DOUBLE PRECISION NOT NULL,
    other_port_costs_usd_ton DOUBLE PRECISION NOT NULL DEFAULT 15.0,
    tax_fund_brl_bag DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    net_parity_brl_bag DOUBLE PRECISION NOT NULL,
    net_parity_brl_ton DOUBLE PRECISION NOT NULL,
    fob_usd_ton DOUBLE PRECISION NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_saved_scenarios_org_id ON saved_scenarios (organization_id);
CREATE INDEX IF NOT EXISTS idx_saved_scenarios_created_at ON saved_scenarios (created_at DESC);
