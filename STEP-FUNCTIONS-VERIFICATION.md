# Step Functions Verification Guide

Operational reference for manually confirming the Step Functions fleet backend is active after deployment.

**Account:** `195613527809` · **Region:** `eu-west-1`

---

## Check the State Machine

```bash
aws stepfunctions describe-state-machine \
  --state-machine-arn arn:aws:states:eu-west-1:195613527809:stateMachine:mcp-agent-factory-fleet \
  --region eu-west-1 \
  --query '[Name,Status,Type]'
```

Expected: `["mcp-agent-factory-fleet", "ACTIVE", "STANDARD"]`

---

## Check the Lambda Worker

```bash
aws lambda get-function \
  --function-name mcp-agent-factory-pipeline-worker \
  --region eu-west-1 \
  --query 'Configuration.[FunctionName,State,Runtime,Handler]'
```

Expected: `["mcp-agent-factory-pipeline-worker", "Active", "python3.11", "sfn_worker.handler"]`

Verify environment variables are populated (pulled from SSM at deploy time):

```bash
aws lambda get-function-configuration \
  --function-name mcp-agent-factory-pipeline-worker \
  --region eu-west-1 \
  --query 'Environment.Variables | keys(@)'
```

Should include `REDIS_URL` and `FLASK_ENV`.

---

## Check the SSM Parameters

```bash
aws ssm get-parameter \
  --name /mcp-agent-factory/redis-url \
  --region eu-west-1 \
  --query 'Parameter.Value'

aws ssm get-parameter \
  --name /mcp-agent-factory/step-functions-arn \
  --region eu-west-1 \
  --query 'Parameter.Value'
```

Both should return non-empty values. The Step Functions ARN must match the state machine above.

---

## Inspect Recent Executions

```bash
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:eu-west-1:195613527809:stateMachine:mcp-agent-factory-fleet \
  --region eu-west-1 \
  --max-items 10 \
  --query 'executions[*].[name,status,startDate]'
```

Healthy state: executions are `SUCCEEDED` or `FAILED` (not stuck in `RUNNING`). An execution lingering in `RUNNING` for more than 5 minutes indicates a timeout or unhandled Lambda error.

---

## Trigger a Manual Test Execution

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:eu-west-1:195613527809:stateMachine:mcp-agent-factory-fleet \
  --name manual-test-$(date +%s) \
  --input '{"tools": ["web_search"], "query": "ping"}' \
  --region eu-west-1
```

Note the `executionArn` in the response, then poll:

```bash
aws stepfunctions describe-execution \
  --execution-arn <executionArn> \
  --region eu-west-1 \
  --query '[status,stopDate]'
```

After roughly 10–30 seconds the status should move from `RUNNING` to `SUCCEEDED` or `FAILED`.

---

## Read Execution History

For any execution ARN, the full audit trail is available:

```bash
aws stepfunctions get-execution-history \
  --execution-arn <executionArn> \
  --region eu-west-1 \
  --output table
```

This shows each state transition, retry attempts, and the final outcome with timestamps.

---

## Read Lambda Logs

```bash
aws logs tail /aws/lambda/mcp-agent-factory-pipeline-worker \
  --follow \
  --region eu-west-1
```

Each invocation emits structured JSON lines with `job_id`, `status`, and any error details.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| State machine not found | Terraform not applied; run `make demo-up` |
| Lambda state `Inactive` or `Failed` | Deployment package error; redeploy via Terraform |
| Execution stuck in `RUNNING` | Lambda hit the timeout; check CloudWatch logs |
| `REDIS_URL` missing from Lambda env | SSM parameter empty; run `make ssm-sync` |
| Execution `FAILED` immediately | IAM role missing `ssm:GetParameter` or `logs:PutLogEvents` |

---

**See also:** [`AWS-SERVICES-HEALTH-CHECK.md`](AWS-SERVICES-HEALTH-CHECK.md) · [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
