variable "aws_region" {
  type        = string
  description = "Região da AWS para provisionamento dos recursos serverless"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Identificador do ambiente (ex: dev, staging, prod)"
  default     = "prod"
}

variable "project_name" {
  type        = string
  description = "Prefixo aplicado no nome dos recursos da infraestrutura"
  default     = "agri-trading"
}

variable "database_url" {
  type        = string
  description = "String de conexão para o banco Neon Serverless Postgres (com ?sslmode=require)"
  sensitive   = true
}

variable "custom_domain_name" {
  type        = string
  description = "Domínio personalizado opcional para o CloudFront (ex: agritrading.empresa.com)"
  default     = ""
}

variable "acm_certificate_arn" {
  type        = string
  description = "ARN do certificado ACM em us-east-1 (obrigatório se custom_domain_name for preenchido)"
  default     = ""
}

variable "cognito_domain_prefix" {
  type        = string
  description = "Prefixo único para o domínio do Cognito Managed Login"
  default     = ""
}

variable "cognito_callback_urls" {
  type        = list(string)
  description = "URLs permitidas de callback para redirecionamento após autenticação"
  default     = [
    "https://d1qfxp2g7u6ypc.cloudfront.net",
    "https://d1qfxp2g7u6ypc.cloudfront.net/",
    "http://localhost:8000/callback",
    "http://localhost:3000/callback",
    "https://localhost/callback"
  ]
}

variable "cognito_logout_urls" {
  type        = list(string)
  description = "URLs permitidas para redirecionamento após logout"
  default     = [
    "https://d1qfxp2g7u6ypc.cloudfront.net",
    "https://d1qfxp2g7u6ypc.cloudfront.net/",
    "http://localhost:8000/login",
    "http://localhost:3000/login",
    "https://localhost/login"
  ]
}
