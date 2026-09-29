# Role IAM para o Amazon EventBridge Scheduler invocar a Lambda
resource "aws_iam_role" "scheduler" {
  name = "${var.project_name}-scheduler-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })
}

# Permissão para o Scheduler chamar a função Lambda
resource "aws_iam_policy" "scheduler_invoke_lambda" {
  name = "${var.project_name}-scheduler-invoke-lambda-${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "lambda:InvokeFunction"
        Effect   = "Allow"
        Resource = aws_lambda_function.api.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "scheduler_attach" {
  role       = aws_iam_role.scheduler.name
  policy_arn = aws_iam_policy.scheduler_invoke_lambda.arn
}

# 1. Agendamento B3 Fechamento & Ajuste Diário: Seg-Sex às 19:15 BRT
resource "aws_scheduler_schedule" "b3_settlement" {
  name                         = "${var.project_name}-b3-settlement-${var.environment}"
  description                  = "Coleta precos oficiais de fechamento B3 (CCM e SJC) e CEPEA/ESALQ"
  schedule_expression          = "cron(15 19 ? * MON-FRI *)"
  schedule_expression_timezone = "America/Sao_Paulo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.api.arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      job_type = "B3_SETTLEMENT"
    })
  }
}

# 2. Agendamento B3 Intraday Manhã: Seg-Sex a cada 30 min (09:30 - 12:00 BRT)
resource "aws_scheduler_schedule" "b3_intraday_morning" {
  name                         = "${var.project_name}-b3-intraday-morning-${var.environment}"
  description                  = "Monitoramento das cotacoes dos futuros B3 durante o pregao matutino"
  schedule_expression          = "cron(0/30 9-11 ? * MON-FRI *)"
  schedule_expression_timezone = "America/Sao_Paulo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.api.arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      job_type = "B3_INTRADAY"
    })
  }
}

# 3. Agendamento B3 Intraday Tarde: Seg-Sex a cada 30 min (12:30 - 16:30 BRT)
resource "aws_scheduler_schedule" "b3_intraday_afternoon" {
  name                         = "${var.project_name}-b3-intraday-afternoon-${var.environment}"
  description                  = "Monitoramento das cotacoes dos futuros B3 durante o pregao vespertino"
  schedule_expression          = "cron(0/30 12-16 ? * MON-FRI *)"
  schedule_expression_timezone = "America/Sao_Paulo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.api.arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      job_type = "B3_INTRADAY"
    })
  }
}

# 4. Agendamento Market Data Geral: Seg-Sex às 18:30 BRT (BCB, CBOT, Prêmios, Físico)
resource "aws_scheduler_schedule" "macro_market_data" {
  name                         = "${var.project_name}-macro-market-data-${var.environment}"
  description                  = "Extracao de PTAX BCB, CBOT CME, Premios nos Portos e Precos Fisicos"
  schedule_expression          = "cron(30 18 ? * MON-FRI *)"
  schedule_expression_timezone = "America/Sao_Paulo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.api.arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      job_type = "MACRO_MARKET_DATA"
    })
  }
}
