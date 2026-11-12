# ---------------------------------------------------------------------------
# Step Functions fleet worker — async job execution backend for issue #29
#
# Architecture
# ------------
#   Gateway → sfn.start_execution → state machine → Lambda worker → pipeline
#
# The state machine enforces:
#   - Per-job timeout  (FLEET_JOB_TIMEOUT_SECS, default 300 s)
#   - Retry with exponential back-off (3 attempts, 2× multiplier)
#   - Durable execution history in CloudWatch (audit trail)
#
# The Lambda function runs sfn_worker.py and calls the gateway's /mcp endpoint.
# ---------------------------------------------------------------------------

locals {
  sfn_timeout_seconds = tonumber(coalesce(var.fleet_job_timeout_seconds, "300"))
}

# ---------------------------------------------------------------------------
# Lambda function — pipeline worker
# ---------------------------------------------------------------------------

data "archive_file" "sfn_worker" {
  type        = "zip"
  source_dir  = "${path.module}/../src/mcp_agent_factory/streams"
  output_path = "${path.module}/.terraform/sfn_worker.zip"
}

resource "aws_lambda_function" "pipeline_worker" {
  function_name    = "mcp-agent-factory-pipeline-worker"
  filename         = data.archive_file.sfn_worker.output_path
  source_code_hash = data.archive_file.sfn_worker.output_base64sha256
  handler          = "sfn_worker.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_worker.arn
  timeout          = local.sfn_timeout_seconds
  memory_size      = 512

  environment {
    variables = {
      GATEWAY_URL  = "https://${aws_lb.gateway.dns_name}"
      MCP_DEV_MODE = "0"
    }
  }

  tags = {
    project = "mcp-agent-factory"
  }

  depends_on = [aws_cloudwatch_log_group.lambda_worker]
}

resource "aws_cloudwatch_log_group" "lambda_worker" {
  name              = "/aws/lambda/mcp-agent-factory-pipeline-worker"
  retention_in_days = 7
  tags              = { project = "mcp-agent-factory" }
}

# ---------------------------------------------------------------------------
# Step Functions state machine
# ---------------------------------------------------------------------------

resource "aws_sfn_state_machine" "fleet" {
  name     = "mcp-agent-factory-fleet"
  role_arn = aws_iam_role.sfn_execution.arn

  definition = jsonencode({
    Comment = "MCP Agent Factory — async fleet job execution"
    StartAt = "RunPipeline"
    States = {
      RunPipeline = {
        Type     = "Task"
        Resource = aws_lambda_function.pipeline_worker.arn
        TimeoutSeconds = local.sfn_timeout_seconds
        Retry = [
          {
            ErrorEquals   = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "States.TaskFailed"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "MarkFailed"
          }
        ]
        Next = "MarkDone"
      }
      MarkDone = {
        Type = "Succeed"
      }
      MarkFailed = {
        Type  = "Fail"
        Error = "PipelineError"
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_fleet.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  tags = {
    project = "mcp-agent-factory"
  }
}

resource "aws_cloudwatch_log_group" "sfn_fleet" {
  name              = "/aws/states/mcp-agent-factory-fleet"
  retention_in_days = 7
  tags              = { project = "mcp-agent-factory" }
}

# ---------------------------------------------------------------------------
# SSM — store state machine ARN for the gateway to consume
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "state_machine_arn" {
  name  = "/mcp-agent-factory/STATE_MACHINE_ARN"
  type  = "String"
  value = aws_sfn_state_machine.fleet.arn
  tags  = { project = "mcp-agent-factory" }
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "state_machine_arn" {
  description = "ARN of the Step Functions fleet state machine"
  value       = aws_sfn_state_machine.fleet.arn
}

output "lambda_worker_arn" {
  description = "ARN of the pipeline worker Lambda"
  value       = aws_lambda_function.pipeline_worker.arn
}
