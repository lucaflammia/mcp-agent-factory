# Deployment Guide

> **Status:** IaC committed, CI deploy job wired. Run `make demo-up` with AWS credentials
> to provision the live environment. See §Demo Instructions.

## Architecture

The deployed slice is the smallest genuinely interesting cut: TLS termination, the
FastAPI gateway, and the two persistence services that distinguish this system from a
simple proxy — pgvector for RAG and Redis for sessions and distributed locking.

```
┌───────────────────────────────────────────────────────────┐
│                        AWS (eu-west-1)                     │
│                                                           │
│   ECR ──► App Runner ──► /health  ◄── GitHub Actions CI  │
│   (image)   (TLS, HTTPS)    │         (OIDC, no keys)    │
│             scale-to-0      │                             │
│                        ┌────┴─────────────────────┐      │
│                        │   FastAPI gateway (8000)  │      │
│                        │   - PIIGate               │      │
│                        │   - Auth (OAuth 2.1)      │      │
│                        │   - MultiAgentOrchestrator│      │
│                        │   - OTel → Grafana Cloud  │      │
│                        └──┬────────────┬───────────┘      │
│                     SSM ──┘            │                  │
│                (SecureString params)   │                  │
└────────────────────────────────────────┼──────────────────┘
                                         │  (external, free tier)
                        ┌────────────────┼──────────────────┐
                        │   Neon (pgvector)  Upstash (Redis) │
                        │   Anthropic API    Grafana Cloud    │
                        └───────────────────────────────────┘
```

**What is in AWS:** ECR, App Runner, IAM roles, SSM Parameter Store, CloudWatch log group.

**What is outside AWS:** Neon (serverless Postgres + pgvector), Upstash (serverless Redis),
Anthropic API, Grafana Cloud OTLP collector. These have free tiers and scale to zero,
which keeps idle AWS cost near zero.

## Stack and Cost

| Resource | Purpose | Idle cost | Demo-day cost |
|---|---|---|---|
| ECR repository | Container image storage | ~€0.10/month | ~€0.10/month |
| App Runner service | Gateway, TLS, scale-to-zero | €0 (paused) | ~€0.50–1.00 |
| IAM roles (3) | OIDC CI, App Runner ECR pull, App Runner instance | free | free |
| SSM Parameter Store (6 SecureStrings) | Secrets | free | free |
| CloudWatch log group (7-day retention) | App Runner logs | ~€0 at low volume | ~€0 |
| **AWS total** | | **~€0.10/month** | **~€1/day** |
| Neon (free tier) | pgvector RAG | free | free |
| Upstash (free tier) | Redis sessions + Redlock | free | free |
| Anthropic API | LLM calls | per-token | per-token |
| Grafana Cloud (free tier) | OTel traces | free | free |

**Total idle cost: <€0.10/month** (ECR storage only — nothing runs at rest).
**Total demo-day cost: ~€1** (App Runner instance time only).

> No NAT Gateway (€32/month), ALB (€17/month), RDS, or ElastiCache were created.
> These resources do not scale to zero. Neon and Upstash replace them at zero idle cost.

## What Broke Moving from Compose to Cloud

This section documents what was invisible locally and only appeared under the constraints
of a real cloud deployment. It is the most operationally useful part of this document.

### 1. Hostname assumptions (`localhost` → service DNS)

In `docker-compose`, services reference each other by container name (`redis`, `kafka`,
`gateway`). In App Runner, the gateway is the only container AWS manages; external
services are reached by their provider hostnames.

- `REDIS_URL` changed from `redis://redis:6379` to `rediss://default:...@....upstash.io:6379`
- `DATABASE_URL` changed from `postgresql://localhost:5432/...` to a Neon connection string
- The gateway reads both from SSM at startup — no code change needed, only the values changed.

### 2. Secret injection (env vars in compose → SSM + IAM)

In compose, secrets live in a `.env` file bind-mounted into the container. In App Runner,
`runtime_environment_secrets` maps SSM parameter ARNs to environment variable names; the
App Runner instance role provides `ssm:GetParameters` access. The container sees the same
environment variable names; the difference is where the values originate.

The `load_dotenv()` call in `gateway/app.py` is a no-op when `.env` does not exist —
SSM-injected variables are already in the environment before Python starts.

### 3. App Runner cold start latency

App Runner's `min_size = 0` means the service scales to zero when idle. The first request
after a cold period takes 10–30 seconds while App Runner provisions a new instance and
runs the health check. Subsequent requests are fast.

For a demo: run `curl https://<app_url>/health` once before the call to warm the instance.

The health check configuration (`healthy_threshold = 1`, `interval = 10s`) means traffic
routes to the container after a single successful `/health` — App Runner waits for this
before considering the deployment complete.

### 4. Image size with Python ML dependencies

The full `.[ml]` extras (sentence-transformers, torch) push the image to ~2 GB, which
meaningfully increases cold start time and ECR storage cost.

**Mitigation:** the Dockerfile defaults to `EXTRAS=infra,otel`, which installs the OTel
instrumentation and infra dependencies but skips sentence-transformers. The gateway uses
`StubEmbedder` unless `VECTOR_STORE_BACKEND=pgvector` is set, in which case it uses Neon
with a server-side embedding function (pgvector's `pg_trgm` or an RPC to an external
embedder). The image builds to ~400 MB.

If real ML embeddings are required, lazy-import sentence-transformers on first use rather
than at module import time — cold start completes before the model loads.

### 5. Neon connection limits under serverless Postgres

Neon's free tier caps concurrent connections at 10. Under compose, a long-lived connection
pool with `pool_size=10` is fine. Under App Runner with `max_size=2` instances, each
instance can hold up to 5 connections — that is fine at demo scale.

For production scale, use `pgbouncer` in front of Neon, or use Neon's connection pooling
endpoint (`:5432` vs `:5433`).

### 6. Platform-level TLS (Caddy removed)

The repo ships a `Caddyfile` for local TLS termination. App Runner provides TLS
termination natively — the Caddy container is not deployed. The gateway listens on HTTP
port 8000; App Runner handles HTTPS externally.

### 7. OTel endpoint changed

In compose, the OTel collector runs as a sidecar container (`otel-collector`). In App Runner,
the gateway exports traces directly to Grafana Cloud's OTLP endpoint over HTTPS. The
`OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS` environment variables
control this; both are stored as SSM SecureStrings.

## Secrets

All secrets are `SecureString` parameters in SSM under `/mcp-agent-factory/*`.

| SSM path | Contains |
|---|---|
| `/mcp-agent-factory/anthropic-api-key` | `sk-ant-...` |
| `/mcp-agent-factory/database-url` | Neon connection string |
| `/mcp-agent-factory/redis-url` | Upstash connection string |
| `/mcp-agent-factory/jwt-secret` | 32-byte hex JWT signing key |
| `/mcp-agent-factory/otel-endpoint` | Grafana Cloud OTLP URL |
| `/mcp-agent-factory/otel-headers` | Grafana Cloud auth header |

No secrets are in the image, in environment variables set at deploy time, in `.env` files
in the repository, or in GitHub Secrets (except `AWS_CI_ROLE_ARN` and
`APP_RUNNER_SERVICE_ARN`, which are resource identifiers, not credentials).

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
4. Call `aws apprunner start-deployment` to pull the new image.

The OIDC trust policy is scoped to `repo:lucaflammia/mcp-agent-factory:*` — a token from
any other repository cannot assume this role.

## Teardown and Cost Verification

```bash
make demo-down    # terraform destroy + teardown verification
```

`make demo-verify` checks:
- No App Runner services named `mcp-agent-factory` remain
- No unassociated Elastic IPs
- No available (unattached) EBS volumes
- CloudWatch log group is gone

**Check Cost Explorer the day after teardown** (billing data has a 12–24h lag):
- Filter: `Tag: project = mcp-agent-factory`
- Verify the curve is flat after the teardown date

Screenshot of flat Cost Explorer curve: `docs/cost-explorer-post-teardown.png`
*(Committed after first demo-down cycle.)*

## Demo Instructions

For a scheduled interview or demo day:

```bash
# 1. Bring the environment up (~8 minutes, ~€1 total for the session)
make demo-up

# 2. Warm the instance (avoids cold-start on the first demo request)
curl https://<app_url>/health

# 3. Run the demo
# ... (see docs/demo-walkthrough.md for the full flow)

# 4. Tear down after the call
make demo-down
```

The `<app_url>` is printed by `make demo-up` and is available via:

```bash
cd terraform && terraform output -raw app_runner_service_url
```

## Known Gaps

These are intentional omissions, not missing work.

| Gap | Why omitted | Path forward |
|---|---|---|
| Full 18-service compose stack | Does not add depth to the cloud story | Not planned |
| ALB + NAT Gateway | ~€49/month idle; App Runner covers the use case | Not planned |
| Full OTel pipeline (Prometheus, Grafana, Jaeger) | Grafana Cloud OTLP covers traces; local compose handles metrics | Add metrics export to Grafana Cloud when needed |
| ECS Fargate module | Proved in Terraform (commented out in `main.tf`); not running to avoid ALB cost | Uncomment `module.fargate_gateway` to redeploy |
| Multi-region | Single region is correct for a portfolio project | Add Route 53 + failover when SLA requires it |
| Load testing | No sustained load scenario defined | Add k6 test when performance baseline is needed |
| Chaos engineering | No fault injection tooling | Uncomment circuit breaker chaos tests |
| pgvector real embeddings | Image skips sentence-transformers for size | Set `EXTRAS=infra,otel,ml` in Dockerfile when needed |

## Security Baseline (one-time account setup)

These are personal AWS account settings, not project resources. Do once:

- **AWS Budgets:** €1/month, notify at 100% actual and 100% forecasted
- **Free Tier alert:** enable in Billing Preferences
- **Cost Anomaly Detection:** all services, threshold €5
- **IAM hygiene:** MFA on root, no root access keys, dedicated IAM role for Terraform
- **Tagging:** `project = mcp-agent-factory` via `default_tags` on the Terraform provider
  (every resource is tagged automatically — Cost Explorer can filter by project)
