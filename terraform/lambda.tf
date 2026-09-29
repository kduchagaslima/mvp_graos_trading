# Empacotamento do código-fonte preservando a estrutura de pastas src/
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/build/lambda_function.zip"
  source_dir  = "${path.module}/../"
  excludes = [
    ".git",
    ".github",
    ".pytest_cache",
    ".streamlit",
    "tests",
    "terraform",
    "docker-compose.yml",
    "Dockerfile",
    "sql",
    ".env",
    "README.md",
    "ARCHITECTURE.md"
  ]
}

# Role de Execução IAM para o AWS Lambda
resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-lambda-exec-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Anexação da política padrão de logging do CloudWatch
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Função Lambda Serverless Principal (FastAPI + Ingestão B3)
resource "aws_lambda_function" "api" {
  function_name = "${var.project_name}-backend-${var.environment}"
  description   = "FastAPI Backend & Ingestor de Market Data Serverless para AgriTrading"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "src.api.lambda_handler.handler"
  runtime       = "python3.11"
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 30

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      DATABASE_URL = var.database_url
      STAGE        = var.environment
      PYTHONPATH   = "/var/task"
      TZ           = "America/Sao_Paulo"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_logs,
    aws_cloudwatch_log_group.lambda_logs
  ]
}

# Log Group gerenciado no CloudWatch com retenção de 14 dias
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.project_name}-backend-${var.environment}"
  retention_in_days = 14
}
