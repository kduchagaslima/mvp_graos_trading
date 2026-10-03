# ==============================================================================
# Amazon Cognito User Pool & OIDC App Client (Ticket F08)
# Implementa autenticação moderna com PKCE (S256), sem client secret no frontend.
# ==============================================================================

resource "aws_cognito_user_pool" "pool" {
  name = "${var.project_name}-${var.environment}-user-pool"

  # Autenticação por e-mail como username primário
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Política de senhas forte
  password_policy {
    minimum_length    = 10
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
    temporary_password_validity_days = 7
  }

  # Configuração de verificação de e-mail
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Seu código de acesso - AgriTrading"
    email_message        = "Seu código de verificação para acesso ao AgriTrading é: {####}. Válido por 24 horas."
  }

  # Esquema de atributos padrão
  schema {
    name                = "email"
    attribute_data_type = "String"
    mutable             = true
    required            = true
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    mutable             = true
    required            = false
  }

  # Proteção contra enumeração de contas
  user_pool_add_ons {
    advanced_security_mode = "AUDIT"
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }
}

resource "random_string" "cognito_suffix" {
  length  = 6
  special = false
  upper   = false
}

# Domínio do Cognito para Managed Login
resource "aws_cognito_user_pool_domain" "domain" {
  domain       = var.cognito_domain_prefix != "" ? var.cognito_domain_prefix : "${var.project_name}-${var.environment}-${random_string.cognito_suffix.result}"
  user_pool_id = aws_cognito_user_pool.pool.id
}

# Cliente Público para Frontend (Single Page App / PWA)
# Sem client_secret, fluxo Authorization Code com PKCE obrigatório
resource "aws_cognito_user_pool_client" "public_client" {
  name         = "${var.project_name}-${var.environment}-spa-client"
  user_pool_id = aws_cognito_user_pool.pool.id

  # Cliente público: não gera segredo (inseguro em JavaScript cliente)
  generate_secret = false

  # Fluxo OAuth 2.0 PKCE
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  # Validade dos tokens
  access_token_validity  = 15
  id_token_validity      = 15
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  # Revogação e prevenção de token theft
  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"

  # URLs de redirecionamento autorizadas
  callback_urls = var.cognito_callback_urls
  logout_urls   = var.cognito_logout_urls
}
