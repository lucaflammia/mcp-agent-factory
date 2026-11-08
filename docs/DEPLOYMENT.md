# Deployment Guide

> **Status:** IaC committed, CI deploy job wired. Run `make demo-up` with AWS credentials
> to provision the live environment. See §Demo Instructions.

## Architecture

The deployed slice is the smallest genuinely interesting cut: an ALB, an ECS Fargate task
running the FastAPI gateway, and the two persistence services that distinguish this system
from a simple proxy — pgvector for RAG and Redis for sessions and distributed locking.

```
┌───────────────────────────────────────────────────────────┐
│                        AWS (eu-west-1)                     │
│                                                           │
│  ECR → ALB → ECS (Fargate) → /health ← GitHub Actions CI │
│  (image)  (HTTPS)   (task)              (OIDC, no keys)   │
│                        │                                  │
│                   ┌────┴─────────────────────┐            │
│                   │   FastAPI gateway (8000)  │            │
│                   │   - PIIGate               │            │
│                   │   - Auth (OAuth 2.1)      │            │
│                   │   - MultiAgentOrchestrator│            │
│                   │   - OTel → Grafana Cloud  │            │
│                   └──┬────────────┬───────────┘            │
│                SSM ──┘            │                       │
│           (SecureString params)   │                       │
└───────────────────────────────────┼───────────────────────┘
                                    │  (external, free tier)
                   ┌────────────────┼──────────────────┐
                   │   Neon (pgvector)  Upstash (Redis) │
                   │   Anthropic API    Grafana Cloud    │
                   └───────────────────────────────────┘
```

**What is in AWS:** ECR, ECS cluster, Fargate task, ALB, IAM roles, SSM Parameter Store,
CloudWatch log group, Auto Scaling.

**What is outside AWS:** Neon (serverless Postgres + pgvector), Upstash (serverless Redis),
Anthropic API, Grafana Cloud OTLP collector. These have free tiers and scale to zero.

## Stack and Cost

> **No scale-to-zero.** Fargate keeps at least one task running at all times. This means
> there is a monthly cost floor unlike App Runner's idle-to-zero model. Run `make demo-down`
> after each session to avoid unintended charges.

| Resource | Purpose | Idle cost | Demo-day cost |
|---|---|---|---|
| ECR repository | Container image storage | ~€0.10/month | ~€0.10/month |
| ALB | TLS termination, health routing | ~€17/month | ~€17/month |
| ECS Fargate task (0.5 vCPU / 1 GB) | Gateway | ~€8/month | ~€8/month |
| IAM roles (3) | OIDC CI, task execution, task | free | free |
| SSM Parameter Store (6 SecureStrings) | Secrets | free | free |
| CloudWatch log group (7-day retention) | Container logs | ~€0 at low volume | ~€0 |
| Auto Scaling | 1–2 tasks at 70% CPU | free | free |
| **AWS total (always-on)** | | **~€25/month** | **~€25/month** |
| Neon (free tier) | pgvector RAG | free | free |
| Upstash (free tier) | Redis sessions + Redlock | free | free |
| Anthropic API | LLM calls | per-token | per-token |
| Grafana Cloud (free tier) | OTel traces | free | free |

**Teardown removes all billable AWS resources.** Run `make demo-down` to avoid ongoing charges.

## Async Jobs

Async job endpoints (`POST /mcp/jobs`, `POST /mcp/jobs/batch`) are available locally
(docker-compose) but return `503 async_jobs_unavailable` on the cloud demo because Redis
is not co-located with the ECS task. Cloud async support is tracked in issue #29.

The synchronous gateway (`POST /mcp`, `POST /mcp/tools/call`) is unaffected.

## What Changed from App Runner

AWS closed App Runner to new customers as of April 30, 2026. This deployment migrated to
ECS Express Mode (Fargate + ALB), which is AWS's recommended migration path.

Key differences:
- **IAM roles:** Two roles required (task execution + task) instead of one App Runner
  instance role. Task execution role handles ECR pull and CloudWatch logs;
  task role handles SSM reads at runtime.
- **Health check path:** ECS uses `/health` explicitly (App Runner also used `/health` —
  no change to the application).
- **Cost model:** ALB + Fargate always-on (~€25/month) vs App Runner scale-to-zero (~€0
  idle). Run `make demo-down` to stop paying.
- **No `APP_RUNNER_SERVICE_ARN` secret.** Deploy uses `ECS_CLUSTER_NAME`,
  `ECS_SERVICE_NAME`, and `ECS_TASK_DEFINITION_FAMILY` repository variables.

## Secrets

All secrets are `SecureString` parameters in SSM under `/mcp-agent-factory/*`.

| SSM path | Contains |
|---|---|
| `/mcp-agent-factory/gemini-api-key` | Gemini API key |
| `/mcp-agent-factory/database-url` | Neon connection string |
| `/mcp-agent-factory/redis-url` | Upstash connection string |
| `/mcp-agent-factory/jwt-secret` | 32-byte hex JWT signing key |
| `/mcp-agent-factory/otel-endpoint` | Grafana Cloud OTLP URL |
| `/mcp-agent-factory/otel-headers` | Grafana Cloud auth header |

No secrets appear in the image, in environment variables at deploy time, in repository files,
or in GitHub Secrets (except `AWS_CI_ROLE_ARN`, which is a resource identifier).

To populate after `terraform apply`:

```bash
make ssm-populate
```

## CI/CD

Push to `main` triggers `.github/workflows/ci.yml` → `deploy` job:

1. GitHub Actions assumes `mcp-agent-factory-ci` IAM role via OIDC (`id-token: write`).
   No static `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in GitHub Secrets.
2. Login to ECR, build the gateway image for `linux/amd64`, tag with the commit SHA and `latest`.
3. Push both tags to ECR.
4. Download the current ECS task definition, patch the image to the commit SHA, register
   the new revision, and update the ECS service (waits for stability).

GitHub repository variables required: `ECS_CLUSTER_NAME`, `ECS_SERVICE_NAME`,
`ECS_TASK_DEFINITION_FAMILY`.

The OIDC trust policy is scoped to `repo:lucaflammia/mcp-agent-factory:*`.

## Post-Deploy Trace Verification

After deployment, verify that traces reach Grafana Cloud Tempo:

1. Call `/health` a few times to generate spans:
   ```bash
   for i in 1 2 3; do curl -s http://$(cd terraform && terraform output -raw gateway_url)/health; done
   ```
2. Open Grafana Cloud → Explore → Tempo data source.
3. Search for service name `mcp-gateway` in the last 15 minutes.
4. Confirm at least one trace appears with spans for the `/health` route.

## Teardown and Cost Verification

```bash
make demo-down    # terraform destroy + teardown verification
```

`make demo-verify` checks:
- No ECS services named `mcp-agent-factory-gateway` remain
- No unassociated Elastic IPs
- No available (unattached) EBS volumes
- CloudWatch log group is gone

**Check Cost Explorer the day after teardown** (billing data has a 12–24h lag):
- Filter: `Tag: project = mcp-agent-factory`
- Verify the curve is flat after the teardown date

## Demo Instructions

For a scheduled interview or demo day:

```bash
# 1. Bring the environment up (~5 minutes)
make demo-up

# 2. Verify the endpoint
curl http://$(cd terraform && terraform output -raw gateway_url)/health

# 3. Run the demo
# ... (see docs/demo-walkthrough.md for the full flow)

# 4. Tear down after the call (stops ALB + Fargate charges)
make demo-down
```

The gateway URL is printed by `make demo-up` and is available via:

```bash
cd terraform && terraform output -raw gateway_url
```

## Known Gaps

| Gap | Why omitted | Path forward |
|---|---|---|
| Scale-to-zero | Fargate keeps at least 1 task running | Use Lambda container image for infrequent workloads |
| Async jobs in cloud | Redis not co-located with ECS task | Issue #29 (Step Functions Worker) |
| Full OTel pipeline (Prometheus, Grafana, Jaeger) | Grafana Cloud OTLP covers traces | Add metrics export to Grafana Cloud when needed |
| Multi-region | Single region is correct for a portfolio project | Add Route 53 + failover when SLA requires it |
| pgvector real embeddings | Image skips sentence-transformers for size | Set `EXTRAS=infra,otel,ml` in Dockerfile when needed |

## Security Baseline (one-time account setup)

- **AWS Budgets:** €1/month, notify at 100% actual and 100% forecasted
- **Free Tier alert:** enable in Billing Preferences
- **Cost Anomaly Detection:** all services, threshold €5
- **IAM hygiene:** MFA on root, no root access keys, dedicated IAM role for Terraform
- **Tagging:** `project = mcp-agent-factory` via `default_tags` on the Terraform provider
