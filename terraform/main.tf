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
  force_delete         = true

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
# CloudWatch — log group for the gateway container (7-day retention)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/ecs/mcp-agent-factory"
  retention_in_days = 7
}

# ---------------------------------------------------------------------------
# Networking — use the default VPC; subnets and SGs are configurable
# ---------------------------------------------------------------------------

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "gateway" {
  name        = "mcp-agent-factory-gateway"
  description = "ECS gateway task — allow inbound HTTP from ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP from ALB"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------------------------------------------------------------------------
# ECS cluster
# ---------------------------------------------------------------------------

resource "aws_ecs_cluster" "gateway" {
  name = "mcp-agent-factory"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "gateway" {
  cluster_name       = aws_ecs_cluster.gateway.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# ---------------------------------------------------------------------------
# ECS task definition
# CPU: 512 (0.5 vCPU)  Memory: 1024 MB
# These are the smallest Fargate sizes that comfortably run the gateway.
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "gateway" {
  family                   = "mcp-agent-factory-gateway"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "gateway"
      image     = "${aws_ecr_repository.gateway.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "ENVIRONMENT", value = var.environment },
        { name = "VECTOR_STORE_BACKEND", value = "pgvector" },
        # Async job endpoints are disabled in the cloud demo (no Redis worker).
        # They return 503 immediately instead of accepting jobs that would hang.
        # Async jobs in the cloud will be enabled by #29 (Step Functions Worker).
        { name = "ASYNC_JOBS_ENABLED", value = "false" },
      ]

      secrets = [
        {
          name      = "GEMINI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/gemini-api-key"
        },
        {
          name      = "DATABASE_URL"
          valueFrom = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/database-url"
        },
        {
          name      = "REDIS_URL"
          valueFrom = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/redis-url"
        },
        {
          name      = "JWT_SECRET"
          valueFrom = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/jwt-secret"
        },
        {
          name      = "OTEL_EXPORTER_OTLP_ENDPOINT"
          valueFrom = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/otel-endpoint"
        },
        {
          name      = "OTEL_EXPORTER_OTLP_HEADERS"
          valueFrom = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/mcp-agent-factory/otel-headers"
        },
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.gateway.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "gateway"
        }
      }
    }
  ])

  depends_on = [aws_cloudwatch_log_group.gateway]

  # CI rolls out new image tags via aws-actions/amazon-ecs-deploy-task-definition.
  # Ignoring container_definitions prevents a subsequent `terraform apply` from
  # reverting the running service to the `:latest` tag declared here.
  lifecycle {
    ignore_changes = [container_definitions]
  }
}

# ---------------------------------------------------------------------------
# Application Load Balancer
# ---------------------------------------------------------------------------

resource "aws_lb" "gateway" {
  name               = "mcp-agent-factory"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_security_group" "alb" {
  name        = "mcp-agent-factory-alb"
  description = "ALB — allow inbound HTTPS/HTTP"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb_target_group" "gateway" {
  name        = "mcp-agent-factory"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip"

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }
}

resource "aws_lb_listener" "gateway_http" {
  load_balancer_arn = aws_lb.gateway.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.gateway.arn
  }
}

# ---------------------------------------------------------------------------
# ECS service (Express Mode: Fargate + ALB, min 1 task, max 2)
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "gateway" {
  name            = "mcp-agent-factory-gateway"
  cluster         = aws_ecs_cluster.gateway.id
  task_definition = aws_ecs_task_definition.gateway.arn
  desired_count   = var.min_tasks
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.gateway.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.gateway.arn
    container_name   = "gateway"
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  depends_on = [
    aws_lb_listener.gateway_http,
    aws_iam_role_policy_attachment.ecs_task_execution,
  ]
}

# ---------------------------------------------------------------------------
# Auto Scaling (min 1 / max 2 tasks)
# ---------------------------------------------------------------------------

resource "aws_appautoscaling_target" "gateway" {
  max_capacity       = var.max_tasks
  min_capacity       = var.min_tasks
  resource_id        = "service/${aws_ecs_cluster.gateway.name}/${aws_ecs_service.gateway.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "gateway_cpu" {
  name               = "mcp-agent-factory-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.gateway.resource_id
  scalable_dimension = aws_appautoscaling_target.gateway.scalable_dimension
  service_namespace  = aws_appautoscaling_target.gateway.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Budget alert — notify when demo cost exceeds €40/month (~1.5× the floor)
# Removed by `make demo-down` (terraform destroy) along with all other resources
# ---------------------------------------------------------------------------

resource "aws_budgets_budget" "demo" {
  name         = "mcp-agent-factory-demo"
  budget_type  = "COST"
  limit_amount = "40"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = var.budget_alert_email != "" ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 100
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.budget_alert_email]
    }
  }
}
