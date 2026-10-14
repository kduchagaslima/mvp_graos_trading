-- ==============================================================================
-- Migração 006: Tabela Satélite de Lineage W3C PROV (ADR-004 e Política de Transparência)
-- Registra a linhagem, fórmula, parâmetros, eixos e decisão dos cálculos de paridade
-- ==============================================================================

CREATE TABLE IF NOT EXISTS market_quotes_lineage (
    id SERIAL PRIMARY KEY,
    quote_id INTEGER REFERENCES market_quotes(id) ON DELETE SET NULL,
    parity_snapshot_id INTEGER REFERENCES parity_snapshots(id) ON DELETE SET NULL,
    parity_run_id VARCHAR(64) NOT NULL,
    formula_version VARCHAR(32) NOT NULL,
    parameter_version VARCHAR(32) NOT NULL,
    origin_axis VARCHAR(32) NOT NULL,
    freshness_axis VARCHAR(32) NOT NULL,
    decision_ready BOOLEAN NOT NULL DEFAULT false,
    inputs_json TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lineage_run_id ON market_quotes_lineage (parity_run_id);
CREATE INDEX IF NOT EXISTS idx_lineage_quote_id ON market_quotes_lineage (quote_id);
CREATE INDEX IF NOT EXISTS idx_lineage_parity_id ON market_quotes_lineage (parity_snapshot_id);
