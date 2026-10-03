-- ==============================================================================
-- Migração 002: Schema de Qualidade de Dados v2 (Ticket F02)
-- Adiciona dois eixos de rastreabilidade (data_kind, freshness), Decimal e UTC
-- ==============================================================================

-- 1. Novos campos de rastreabilidade e qualidade na tabela market_quotes
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS data_kind VARCHAR(16) DEFAULT 'OBSERVED';
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS freshness VARCHAR(16) DEFAULT 'CURRENT';
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS observed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS currency VARCHAR(8) DEFAULT 'BRL';
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS contract_expiry DATE;
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS source_vendor VARCHAR(64);
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS source_reference VARCHAR(128);
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(64);
ALTER TABLE market_quotes ADD COLUMN IF NOT EXISTS price_numeric NUMERIC(14, 4);

-- 2. Índice para consultas de séries temporais por momento de observação
CREATE INDEX IF NOT EXISTS idx_quotes_observed_at ON market_quotes (symbol, observed_at);

-- 3. Backfill preservativo dos dados legados existentes (sem apagar registros)
UPDATE market_quotes 
SET price_numeric = CAST(price AS NUMERIC(14, 4))
WHERE price_numeric IS NULL;

UPDATE market_quotes 
SET observed_at = timestamp,
    ingested_at = timestamp
WHERE observed_at IS NULL;

-- Segrega seeds prévias como DEMO (não OBSERVED) conforme critério de aceite
UPDATE market_quotes 
SET data_kind = 'DEMO'
WHERE source LIKE 'SEED%' AND data_kind = 'OBSERVED';
