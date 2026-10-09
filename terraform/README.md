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

## 🤖 Pipeline CI/CD Automatizado (GitHub Actions)

A infraestrutura e o frontend possuem esteira de automação contínua configurada em `.github/workflows/`:
* **`ci.yml`**: Executado em Pull Requests e pushes de desenvolvimento. Realiza testes automatizados (`pytest`), compilação de sintaxe (`compileall`), validação de código Terraform (`fmt`, `init`, `validate`) e empacotamento da Lambda gerando checksum SHA-256 e artefato.
* **`deploy.yml`**: Executado automaticamente no push para a branch `main` (ou acionamento manual via `workflow_dispatch`). Conecta-se à AWS de forma segura via OIDC, constrói e provisiona a infraestrutura via `terraform apply -auto-approve`, sincroniza o frontend estático no bucket S3, invalida o cache do CloudFront e executa smoke test no endpoint público.

### 🔐 GitHub Secrets Obrigatórias

Configure os seguintes segredos no repositório do GitHub (**Settings** > **Secrets and variables** > **Actions**):

| Secret | Descrição | Exemplo |
| :--- | :--- | :--- |
| `AWS_ROLE_ARN` | ARN da IAM Role configurada com OIDC para o GitHub Actions | `arn:aws:iam::123456789012:role/AgriTradingGitHubActionsDeploy` |
| `DATABASE_URL` | String de conexão para o Neon Postgres (com SSL) | `postgresql://user:pass@ep-pooler.us-east-1.aws.neon.tech/agri_trading?sslmode=require` |
| `AWS_ACCESS_KEY_ID` *(opcional)* | Chave de acesso AWS para autenticação estática de fallback | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` *(opcional)* | Chave secreta AWS para autenticação de fallback | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |

---

### 🛡️ Configuração da IAM Role para GitHub Actions (OIDC)

Para máxima segurança sem armazenamento de chaves permanentes, utilize autenticação federada OpenID Connect (OIDC).

#### 1. Trust Relationship (Assume Role Policy)

Configure a confiança OIDC da Role limitando ao repositório:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<ORGANIZACAO_OU_USUARIO>/mvp_graos_trading:*"
        }
      }
    }
  ]
}
```

#### 2. Permissões Mínimas Recomendadas para a Role

A Role de deploy necessita de permissões para gerenciar a stack serverless:
* **AWS Lambda**: `lambda:CreateFunction`, `lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration`, `lambda:GetFunction`, `lambda:DeleteFunction`, `lambda:AddPermission`, `lambda:RemovePermission`.
* **Amazon API Gateway (v2)**: `apigateway:GET`, `apigateway:POST`, `apigateway:PUT`, `apigateway:PATCH`, `apigateway:DELETE`.
* **Amazon S3**: `s3:*` restrito aos buckets de frontend (`agri-trading-frontend-*`).
* **Amazon CloudFront**: `cloudfront:CreateDistribution`, `cloudfront:UpdateDistribution`, `cloudfront:GetDistribution`, `cloudfront:CreateInvalidation`, `cloudfront:GetInvalidation`.
* **Amazon EventBridge Scheduler**: `scheduler:CreateSchedule`, `scheduler:UpdateSchedule`, `scheduler:GetSchedule`, `scheduler:DeleteSchedule`.
* **Amazon Cognito**: `cognito-idp:*` para gerenciamento do User Pool e App Client da aplicação.
* **IAM**: `iam:PassRole`, `iam:GetRole`, `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy` para a role de execução da Lambda (`agri-trading-lambda-exec-*`).
* **Amazon CloudWatch Logs**: `logs:CreateLogGroup`, `logs:PutRetentionPolicy`, `logs:DescribeLogGroups`.

---

## 🧹 Destruição de Recursos (Clean-up)

Para encerrar e remover todos os recursos da nuvem:
```bash
terraform destroy -auto-approve
```

