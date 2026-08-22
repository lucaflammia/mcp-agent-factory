# ---------------------------------------------------------------------------
# SSM Parameter Store — placeholder parameters.
# Values are SecureStrings set outside Terraform (never committed to the repo).
#
# One-time setup after `terraform apply`:
#   aws ssm put-parameter --name /mcp-agent-factory/anthropic-api-key \
#     --value "sk-ant-..." --type SecureString --overwrite
#   aws ssm put-parameter --name /mcp-agent-factory/database-url \
#     --value "postgresql://..." --type SecureString --overwrite
#   aws ssm put-parameter --name /mcp-agent-factory/redis-url \
#     --value "rediss://..." --type SecureString --overwrite
#   aws ssm put-parameter --name /mcp-agent-factory/jwt-secret \
#     --value "$(openssl rand -hex 32)" --type SecureString --overwrite
#   aws ssm put-parameter --name /mcp-agent-factory/otel-endpoint \
#     --value "https://otlp-gateway-prod-eu-west-0.grafana.net/otlp" --type SecureString --overwrite
#   aws ssm put-parameter --name /mcp-agent-factory/otel-headers \
#     --value "Authorization=Basic <base64(instanceId:token)>" --type SecureString --overwrite
# ---------------------------------------------------------------------------

# Declare the parameters so Terraform tracks their existence without managing values.
# `ignore_changes = [value]` means `terraform apply` won't overwrite values set manually.

resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "/mcp-agent-factory/anthropic-api-key"
  type  = "SecureString"
  value = "PLACEHOLDER"  # set manually — see comment above

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "database_url" {
  name  = "/mcp-agent-factory/database-url"
  type  = "SecureString"
  value = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "redis_url" {
  name  = "/mcp-agent-factory/redis-url"
  type  = "SecureString"
  value = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "jwt_secret" {
  name  = "/mcp-agent-factory/jwt-secret"
  type  = "SecureString"
  value = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "otel_endpoint" {
  name  = "/mcp-agent-factory/otel-endpoint"
  type  = "SecureString"
  value = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "otel_headers" {
  name  = "/mcp-agent-factory/otel-headers"
  type  = "SecureString"
  value = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [value]
  }
}
