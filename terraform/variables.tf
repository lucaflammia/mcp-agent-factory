variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Environment name — used in tags and resource names"
  type        = string
  default     = "demo"
}

variable "github_org" {
  description = "GitHub org or username — used to scope the OIDC trust policy"
  type        = string
  default     = "lucaflammia"
}

variable "github_repo" {
  description = "GitHub repository name (without org prefix)"
  type        = string
  default     = "mcp-agent-factory"
}

variable "min_tasks" {
  description = "Minimum number of running ECS tasks (no scale-to-zero — there is a cost floor)"
  type        = number
  default     = 1
}

variable "max_tasks" {
  description = "Maximum number of ECS tasks under auto scaling"
  type        = number
  default     = 2
}

variable "budget_alert_email" {
  description = "Email address to receive budget alert notifications"
  type        = string
  default     = ""
}
