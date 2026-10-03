-- ==============================================================================
-- Migração 003: Autenticação, Organizações, RBAC e Custos Privados (Tickets F09, F10)
-- Suporte a isolamento multi-tenant, controle de permissões e perfis de custo
-- ==============================================================================

-- 1. Tabela de usuários vinculados ao sub do Cognito
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    cognito_sub VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(128) UNIQUE NOT NULL,
    name VARCHAR(128),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_platform_operator BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_cognito_sub ON users (cognito_sub);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- 2. Tabela de organizações (empresas / tenants)
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    slug VARCHAR(64) UNIQUE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_slug ON organizations (slug);

-- 3. Vínculo de membros e papéis (RBAC: OWNER, ANALYST, READER)
CREATE TABLE IF NOT EXISTS memberships (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL DEFAULT 'ANALYST',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_membership_user_org UNIQUE (user_id, organization_id)
);

CREATE INDEX IF NOT EXISTS idx_memberships_user_id ON memberships (user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_org_id ON memberships (organization_id);

-- 4. Perfis privados de custos e margens de originação por empresa
CREATE TABLE IF NOT EXISTS cost_profiles (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL DEFAULT 'Padrão',
    brokerage_margin_usd_ton DOUBLE PRECISION NOT NULL DEFAULT 2.0,
    brokerage_fee_brl_bag DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    brokerage_payer VARCHAR(16) NOT NULL DEFAULT 'NONE',
    default_funrural_pct DOUBLE PRECISION NOT NULL DEFAULT 1.5,
    default_shrinkage_loss_pct DOUBLE PRECISION NOT NULL DEFAULT 0.3,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cost_profiles_org_id ON cost_profiles (organization_id);
