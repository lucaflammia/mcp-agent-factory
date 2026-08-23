terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  # Uncomment after creating the S3 bucket + DynamoDB table (one-time bootstrap):
  # backend "s3" {
  #   bucket         = "mcp-agent-factory-tfstate"
  #   key            = "prod/terraform.tfstate"
  #   region         = var.aws_region
  #   dynamodb_table = "mcp-agent-factory-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      project     = "mcp-agent-factory"
      environment = var.environment
      managed_by  = "terraform"
    }
  }
}

# ---------------------------------------------------------------------------
# ECR — container image repository
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "gateway" {
  name                 = "mcp-agent-factory/gateway"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "gateway" {
  repository = aws_ecr_repository.gateway.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# CloudWatch — log group for App Runner (7-day retention → ~€0 at low volume)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/aws/apprunner/mcp-agent-factory"
  retention_in_days = 7
}

# ---------------------------------------------------------------------------
# App Runner — gateway service
# ---------------------------------------------------------------------------

resource "aws_apprunner_service" "gateway" {
  service_name = "mcp-agent-factory"

  source_configuration {
    image_repository {
      image_configuration {
        port = "8000"
        runtime_environment_secrets = {
          # Secrets pulled from SSM at runtime — never in the image or env vars at deploy time.
          ANTHROPIC_API_KEY = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/anthropic-api-key"
          DATABASE_URL      = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/database-url"
          REDIS_URL         = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/redis-url"
          JWT_SECRET        = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/jwt-secret"
          OTEL_EXPORTER_OTLP_ENDPOINT = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/otel-endpoint"
          OTEL_EXPORTER_OTLP_HEADERS  = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/otel-headers"
        }
        runtime_environment_variables = {
          ENVIRONMENT = var.environment
          # Gateway reads DATABASE_URL and uses pgvector if set; falls back to InMemoryVectorStore
          VECTOR_STORE_BACKEND = "pgvector"
        }
      }
      image_identifier      = "${aws_ecr_repository.gateway.repository_url}:latest"
      image_repository_type = "ECR"
    }
    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr.arn
    }
    auto_deployments_enabled = false
  }

  instance_configuration {
    cpu    = "0.25 vCPU"
    memory = "0.5 GB"
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }

  # Scale to 0 when idle — no charge at rest except ECR storage
  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.gateway.arn

  observability_configuration {
    observability_enabled           = true
    observability_configuration_arn = aws_apprunner_observability_configuration.gateway.arn
  }

  depends_on = [
    aws_cloudwatch_log_group.gateway,
    aws_iam_role_policy_attachment.apprunner_ecr,
  ]
}

resource "aws_apprunner_auto_scaling_configuration_version" "gateway" {
  auto_scaling_configuration_name = "mcp-agent-factory"
  min_size = 1
  max_size = 2
}

resource "aws_apprunner_observability_configuration" "gateway" {
  observability_configuration_name = "mcp-agent-factory"
  trace_configuration {
    vendor = "AWSXRAY"
  }
}

# ---------------------------------------------------------------------------
# ECS Fargate module — written and tested once to prove the pattern.
# Kept here for reference; not running to avoid ALB + NAT costs.
# See docs/DEPLOYMENT.md §Known Gaps.
# ---------------------------------------------------------------------------
# module "fargate_gateway" {
#   source  = "./modules/fargate"
#   cluster_name   = "mcp-agent-factory"
#   image_uri      = "${aws_ecr_repository.gateway.repository_url}:latest"
#   container_port = 8000
# }

data "aws_caller_identity" "current" {}
