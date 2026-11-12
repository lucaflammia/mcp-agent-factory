output "ecr_repository_url" {
  description = "ECR repository URL — used in CI to tag and push images"
  value       = aws_ecr_repository.gateway.repository_url
}

output "gateway_url" {
  description = "Public HTTP URL of the ECS gateway service (ALB DNS)"
  value       = "http://${aws_lb.gateway.dns_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster name — used in CI deploy"
  value       = aws_ecs_cluster.gateway.name
}

output "ecs_service_name" {
  description = "ECS service name — used in CI deploy"
  value       = aws_ecs_service.gateway.name
}

output "ecs_task_definition_family" {
  description = "ECS task definition family — used in CI deploy"
  value       = aws_ecs_task_definition.gateway.family
}

output "ci_role_arn" {
  description = "IAM role ARN assumed by GitHub Actions via OIDC"
  value       = aws_iam_role.ci.arn
}

output "task_execution_role_arn" {
  description = "ECS task execution role ARN"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "task_role_arn" {
  description = "ECS task role ARN (runtime permissions)"
  value       = aws_iam_role.ecs_task.arn
}
