# 🚀 Infraestrutura como Código (Terraform) - AgriTrading Serverless

Este diretório contém os manifestos do **Terraform** para provisionar a infraestrutura 100% Serverless do **AgriTrading** na **AWS**, integrada ao banco de dados **Neon Serverless Postgres**.

---

## 🏗️ Recursos Provisionados

- **Computação & APIs:**
  - **AWS Lambda** (Python 3.11 ARM64 Graviton) rodando FastAPI via Mangum.
  - **Amazon API Gateway (HTTP API v2)** com roteamento proxy `$default` e CORS habilitado.
- **Agendamento Serverless:**
  - **Amazon EventBridge Scheduler** com 4 rotinas no fuso de Brasília (`America/Sao_Paulo`):
    - `19:15 BRT`: Fechamento oficial B3 e Indicadores CEPEA/ESALQ.
    - `09:30-12:00 BRT`: Intraday B3 (a cada 30 min).
    - `12:30-16:30 BRT`: Intraday B3 (a cada 30 min).
    - `18:30 BRT`: Market Data Macro (PTAX, CBOT, Prêmios, Físico).
- **Frontend & Borda:**
  - **Amazon S3 Bucket** privado para assets estáticos da interface web.
  - **Amazon CloudFront (CDN)** com Origin Access Control (OAC) e roteamento de `/api/*` diretamente para o API Gateway.
- **Segurança & Governança:**
  - Roles e políticas IAM de privilégio mínimo.
  - Log Groups dedicados no CloudWatch para auditoria.

---

## 📋 Pré-requisitos

1. **AWS CLI** configurado com credenciais válidas:
   ```bash
   aws configure
   ```
2. **Terraform** instalado (v1.5.0 ou superior).
3. Uma conta gratuita no **[Neon](https://neon.tech)** com um banco PostgreSQL criado na região `us-east-1`.

---

## ⚡ Passo a Passo para o Deploy

### 1. Configurar as Variáveis
Copie o arquivo de exemplo e defina a sua `DATABASE_URL` do Neon:
```bash
cp terraform.tfvars.example terraform.tfvars
```
Edite o arquivo `terraform.tfvars`:
```hcl
database_url = "postgresql://neondb_owner:SENHA@ep-xyz-pooler.us-east-1.aws.neon.tech/agri_trading?sslmode=require"
```

### 2. Inicializar o Terraform
Baixe os providers necessários (`aws`, `archive`, `random`):
```bash
terraform init
```

### 3. Validar a Configuração
Verifique a sintaxe e a integridade dos arquivos:
```bash
terraform validate
```

### 4. Visualizar o Plano de Execução
```bash
terraform plan
```

### 5. Aplicar o Provisionamento
```bash
terraform apply -auto-approve
```

Ao final da execução, o Terraform exibirá as saídas (*outputs*):
```
Outputs:
cloudfront_url = "https://d1234567abcdef.cloudfront.net"
api_gateway_endpoint = "https://abc123xyz.execute-api.us-east-1.amazonaws.com"
s3_frontend_bucket = "agri-trading-frontend-prod-1a2b3c4d"
...
```

---

## 📤 Publicando o Frontend no S3

Após gerar a build estática do frontend (ex: `dist/` do Vite/React):
```bash
# 1. Sincroniza arquivos para o bucket S3
aws s3 sync ../frontend/dist s3://$(terraform output -raw s3_frontend_bucket) --delete

# 2. Invalida o cache do CloudFront para propagação imediata
aws cloudfront create-invalidation \
  --distribution-id $(terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

---

## 🧹 Destruição de Recursos (Clean-up)

Para encerrar e remover todos os recursos da nuvem:
```bash
terraform destroy -auto-approve
```
