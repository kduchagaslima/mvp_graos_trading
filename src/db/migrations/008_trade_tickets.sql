-- ==============================================================================
-- Migração 008: Boletas Formais de Negociação / Compra de Grãos (Trade Tickets)
-- Registra confirmações de compra com produtores/cooperativas com amarração à
-- linhagem de auditoria DECISION_READY (W3C PROV), volumes, preços e condições.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS trade_tickets (
    id SERIAL PRIMARY KEY,
    ticket_number VARCHAR(64) UNIQUE NOT NULL,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    commodity VARCHAR(16) NOT NULL,
    crop_year VARCHAR(16) NOT NULL DEFAULT '2025/2026',
    seller_name VARCHAR(128) NOT NULL,
    seller_document VARCHAR(32),
    seller_farm VARCHAR(128),
    location_hub_id VARCHAR(32) NOT NULL,
    destination_port_id VARCHAR(16) NOT NULL,
    quantity_bags DOUBLE PRECISION NOT NULL,
    quantity_tons DOUBLE PRECISION NOT NULL,
    price_per_bag_brl DOUBLE PRECISION NOT NULL,
    total_amount_brl DOUBLE PRECISION NOT NULL,
    payment_terms VARCHAR(128),
    delivery_period VARCHAR(128),
    quality_specs TEXT,
    parity_run_id VARCHAR(64),
    cbot_reference DOUBLE PRECISION,
    fx_reference DOUBLE PRECISION,
    freight_reference DOUBLE PRECISION,
    antt_compliant BOOLEAN NOT NULL DEFAULT TRUE,
    decision_ready BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(32) NOT NULL DEFAULT 'CONFIRMED',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trade_tickets_org_id ON trade_tickets (organization_id);
CREATE INDEX IF NOT EXISTS idx_trade_tickets_status ON trade_tickets (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_trade_tickets_created_at ON trade_tickets (organization_id, created_at);
