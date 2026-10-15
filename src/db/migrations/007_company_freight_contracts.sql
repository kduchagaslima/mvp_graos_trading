-- ==============================================================================
-- Migração 007: Contratos Privados de Frete Rodoviário por Empresa (Tenant)
-- Permite que tradings e cooperativas cadastrem suas tabelas de fretes contratados
-- com transportadoras, substituindo benchmarks públicos para cálculos da organização.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS company_freight_contracts (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    origin_id VARCHAR(32) NOT NULL,
    destination_id VARCHAR(16) NOT NULL,
    carrier_name VARCHAR(128) NOT NULL,
    contract_code VARCHAR(64) NOT NULL,
    freight_brl_ton DOUBLE PRECISION NOT NULL,
    volume_contracted_tons DOUBLE PRECISION,
    valid_from DATE,
    valid_until DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_company_freight_org_id ON company_freight_contracts (organization_id);
CREATE INDEX IF NOT EXISTS idx_company_freight_route ON company_freight_contracts (organization_id, origin_id, destination_id);
