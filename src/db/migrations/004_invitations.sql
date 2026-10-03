-- ==============================================================================
-- Migração 004: Convites e Gestão de Membros (Ticket F11)
-- Tokens criptográficos de uso único e validade de 48 horas para onboarding
-- ==============================================================================

CREATE TABLE IF NOT EXISTS invitations (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(128) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'ANALYST',
    token VARCHAR(64) UNIQUE NOT NULL,
    invited_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    accepted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_invitations_token ON invitations (token);
CREATE INDEX IF NOT EXISTS idx_invitations_org_email ON invitations (organization_id, email);
