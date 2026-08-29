output "ecr_repository_url" {
  description = "ECR repository URL — used in CI to tag and push images"
  value       = aws_ecr_repository.gateway.repository_url
}

output "app_runner_service_url" {
  description = "Public HTTPS URL of the App Runner gateway service"
  value       = "https://${aws_apprunner_service.gateway.service_url}"
}

output "app_runner_service_arn" {
  description = "App Runner service ARN — used in CI to trigger redeploy"
  value       = aws_apprunner_service.gateway.arn
}

output "ci_role_arn" {
  description = "IAM role ARN assumed by GitHub Actions via OIDC"
  value       = aws_iam_role.ci.arn
}
