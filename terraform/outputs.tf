output "cloudfront_url" {
  description = "URL publica principal da aplicacao (CloudFront HTTPS)"
  value       = "https://${aws_cloudfront_distribution.cdn.domain_name}"
}

output "cloudfront_domain_name" {
  description = "Nome de dominio gerado pelo CloudFront"
  value       = aws_cloudfront_distribution.cdn.domain_name
}

output "cloudfront_distribution_id" {
  description = "ID da distribuicao CloudFront (usado para invalidacao de cache no deploy)"
  value       = aws_cloudfront_distribution.cdn.id
}

output "api_gateway_endpoint" {
  description = "Endpoint direto do API Gateway HTTP API v2"
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "s3_frontend_bucket" {
  description = "Nome do bucket S3 que armazena os arquivos estaticos do Frontend"
  value       = aws_s3_bucket.frontend.id
}

output "lambda_function_name" {
  description = "Nome da funcao Lambda serverless provisionada"
  value       = aws_lambda_function.api.function_name
}

output "eventbridge_schedules" {
  description = "Schedules do EventBridge configurados no fuso de Brasilia"
  value = {
    b3_settlement         = aws_scheduler_schedule.b3_settlement.name
    b3_intraday_morning   = aws_scheduler_schedule.b3_intraday_morning.name
    b3_intraday_afternoon = aws_scheduler_schedule.b3_intraday_afternoon.name
    macro_market_data     = aws_scheduler_schedule.macro_market_data.name
  }
}
