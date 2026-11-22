# Storage Verification Guide

How to inspect PostgreSQL and Redis state across all implemented milestones
(RAG-07 through RAG-09).

---

## Docker Compose vs Local Service

### When to use `docker compose exec`

```bash
# PostgreSQL — service name is "pgvector", DB is "knowledge", user is "mcp"
docker compose exec pgvector psql -U mcp -d knowledge

# Redis
docker compose exec redis redis-cli
```

Use this when the full stack is running via Docker Compose (`docker compose --profile full up -d`).
The service names (`pgvector`, `redis`) refer to containers managed by Compose. This is the
standard path for integration testing and staging verification — no host-level port exposure needed.

### When to use direct `psql` / `redis-cli`

```bash
# PostgreSQL — user mcp, password mcp-dev-password (default), database knowledge
psql postgresql://mcp:mcp-dev-password@localhost:5432/knowledge
# or
psql -h localhost -U mcp -d knowledge   # enter "mcp-dev-password" when prompted

# Redis
redis-cli -h localhost -p 6379
```

Use this when you have exposed container ports to the host (the default `docker-compose.yml` does
expose `5432` and `6379`), or when running services natively outside Docker.

> **Note:** The default password is `mcp-dev-password`. If you have set `PGVECTOR_PASSWORD` in
> your `.env`, use that value instead.

**Quick rule of thumb:**

| Scenario | Command |
|----------|---------|
| Containers running, no host port needed | `docker compose exec pgvector psql ...` |
| Containers running, host port exposed | Either works |
| Services running natively on host | `psql ...` / `redis-cli ...` |
| CI pipeline (service containers) | `psql ...` with the service's host/port |

---

## RAG-07 — Vector Index Chunk Count

The `rag_index_chunk_count` gauge is exposed via Prometheus, not stored in PostgreSQL or Redis.
Verify it via the gateway metrics endpoint or Grafana.

```bash
# Gateway metrics (while gateway is running)
curl http://localhost:8000/metrics | grep rag_index_chunk_count

# Docker Compose variant (if gateway port not exposed to host)
docker compose exec gateway curl -s http://localhost:8000/metrics | grep rag_index_chunk_count
```

---

## RAG-08 — Rate Limiting, Quotas, Audit Logging (Redis)

RAG-08 stores all state in Redis: token-bucket rate limiter state and per-tenant quota counters.
Audit log entries have a 24h TTL (superseded by RAG-09 PostgreSQL persistence).

### Connect to Redis

```bash
# Docker Compose
docker compose exec redis redis-cli

# Local / host-exposed port
redis-cli -h localhost -p 6379
```

### Inspect quota counters

Inside `redis-cli` (interactive), type these Redis commands:

```
# List all keys for a tenant
KEYS *your-tenant*

# Daily quota counter (resets at UTC midnight)
GET quota:your-tenant:daily:2026-11-22

# Hourly quota counter
GET quota:your-tenant:hourly:2026-11-22-14

# Rate limiter token bucket (remaining tokens + last refill timestamp)
GET ratelimit:your-tenant:bucket
```

Or as one-liner shell commands (outside `redis-cli`):

```bash
redis-cli KEYS '*your-tenant*'
redis-cli GET "quota:your-tenant:daily:$(date -u +%Y-%m-%d)"
redis-cli GET "ratelimit:your-tenant:bucket"
```

### Inspect RAG-08 audit log entries (24h TTL)

Inside `redis-cli`:

```
# List audit log keys for a tenant (kv: prefix)
KEYS kv:audit:your-tenant:*

# Read a specific audit entry (JSON)
GET kv:audit:your-tenant:1700000000000
```

Or as one-liner shell commands:

```bash
redis-cli KEYS 'kv:audit:your-tenant:*'
redis-cli GET "$(redis-cli KEYS 'kv:audit:your-tenant:*' | head -1)"
```

> **Note:** Do not run `redis-cli` commands inside `redis-cli`. The `redis-cli` prompt (`127.0.0.1:6379>`)
> only accepts Redis commands (`GET`, `KEYS`, `TTL`, …). Shell syntax like `$(...)` or piping only works
> outside `redis-cli` in your terminal shell.

### Real-time stats via API

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/query/stats/your-tenant
```

---

## RAG-09 — PostgreSQL Audit Logs, Timezone-Aware Quotas, Cost-Based Limiting

RAG-09 adds durable audit log persistence to PostgreSQL. Redis still holds real-time quota counters;
PostgreSQL holds the permanent audit history.

> **Prerequisite — run the migration first.** The `query_audit_log` and `tenant_config` tables are
> created by migration `004_audit_log_partition.sql`. Run it once before any verification steps:
>
> ```bash
> # Docker Compose (recommended)
> docker compose exec pgvector psql -U mcp -d knowledge \
>   -f /migrations/004_audit_log_partition.sql
>
> # Or pipe from the host
> docker compose exec -T pgvector psql -U mcp -d knowledge \
>   < migrations/004_audit_log_partition.sql
>
> # Direct connection
> psql -h localhost -U mcp -d knowledge < migrations/004_audit_log_partition.sql
> ```
>
> You only need to run this once. Subsequent runs are safe (all statements are `IF NOT EXISTS`).

> **Prerequisite — set `AUDIT_DB_URL` in `.env`.** The gateway only connects to PostgreSQL when
> this variable is present. Without it the `AsyncAuditWriter` holds a `None` pool and silently
> skips all writes (audit data stays Redis-only with a 24 h TTL).
>
> Add this line to your `.env` (matches the `pgvector` service in `docker-compose.yml`):
>
> ```bash
> AUDIT_DB_URL=postgresql://mcp:mcp-dev-password@localhost:5432/knowledge
> ```
>
> Then restart the gateway so it picks up the new variable:
>
> ```bash
> docker compose restart gateway
> # or if running locally: restart uvicorn / the gateway process
> ```

### Connect to PostgreSQL

```bash
# Docker Compose (service name is "pgvector")
docker compose exec pgvector psql -U mcp -d knowledge

# Local / host-exposed port (default password: mcp-dev-password)
psql postgresql://mcp:mcp-dev-password@localhost:5432/knowledge
# or
psql -h localhost -U mcp -d knowledge   # enter "mcp-dev-password" when prompted
```

### Verify the partitioned audit table (migration 004)

```sql
-- Confirm the table and its partitions exist
\d query_audit_log

-- List partitions
SELECT
  inhrelid::regclass AS partition,
  pg_get_expr(c.relpartbound, c.oid) AS bound
FROM pg_inherits
JOIN pg_class c ON c.oid = inhrelid
WHERE inhparent = 'query_audit_log'::regclass;
```

### Inspect audit log entries

```sql
-- Most recent 20 entries across all tenants
SELECT tenant, question, cost_tokens, "timestamp"
FROM query_audit_log
ORDER BY "timestamp" DESC
LIMIT 20;

-- Filter by tenant
SELECT tenant, question, cost_tokens, "timestamp"
FROM query_audit_log
WHERE tenant = 'your-tenant'
ORDER BY "timestamp" DESC;

-- Date-range filter (matches the API export endpoint)
SELECT *
FROM query_audit_log
WHERE tenant = 'your-tenant'
  AND "timestamp" >= '2026-11-01'
  AND "timestamp" <  '2026-11-23';

-- Cost distribution
SELECT
  tenant,
  COUNT(*) AS queries,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cost_tokens) AS p50,
  PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY cost_tokens) AS p99
FROM query_audit_log
GROUP BY tenant;
```

### Verify timezone-aware quota state (Redis)

Quota counters use UTC-date keys; there is no separate `tenant_config` key. Verify the
active quota window and rate limiter state:

```bash
# Shell one-liners (outside redis-cli)
redis-cli KEYS 'quota:your-tenant:*'
redis-cli GET "quota:your-tenant:daily:$(date -u +%Y-%m-%d)"
redis-cli GET "ratelimit:your-tenant:bucket"

# TTL remaining on today's daily quota counter
redis-cli TTL "quota:your-tenant:daily:$(date -u +%Y-%m-%d)"
```

Inside `redis-cli` (interactive):

```
KEYS quota:your-tenant:*
GET quota:your-tenant:daily:2026-11-22
GET ratelimit:your-tenant:bucket
```

### Export audit logs via API (JSON or CSV)

```bash
# JSON (default)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/query/audit/your-tenant?start=2026-11-01&end=2026-11-22"

# CSV
curl -H "Authorization: Bearer $TOKEN" \
     -H "Accept: text/csv" \
  "http://localhost:8000/query/audit/your-tenant?start=2026-11-01&end=2026-11-22"
```

### Verify cost-based metrics via Prometheus

```bash
# Cost histogram
curl http://localhost:8000/metrics | grep rag_query_cost_tokens

# Docker Compose variant
docker compose exec gateway curl -s http://localhost:8000/metrics | grep rag_query_cost_tokens
```

Expected output:
```
rag_query_cost_tokens_bucket{le="1.0"} 45.0
rag_query_cost_tokens_bucket{le="2.0"} 72.0
...
rag_query_cost_tokens_sum 310.5
rag_query_cost_tokens_count 89.0
```

---

## Full Stack Startup Reference

```bash
# Start the complete observability stack (gateway + Prometheus + Grafana + PostgreSQL + Redis)
docker compose --profile full up -d

# Tail gateway logs
docker compose logs -f gateway

# Check all container health
docker compose ps

# Stop everything
docker compose --profile full down
```

---

## Quick Troubleshooting

| Symptom | Check |
|---------|-------|
| `psql: could not connect` | Is the `pgvector` container running? `docker compose ps` |
| `password authentication failed for user "postgres"` | Wrong user — use `-U mcp` with password `mcp-dev-password` (or `$PGVECTOR_PASSWORD`) |
| `NOAUTH` from redis-cli | Redis has auth enabled; check `REDIS_PASSWORD` in `.env` |
| `query_audit_log` table missing | Run migration: `docker compose exec pgvector psql -U mcp -d knowledge -f /docker-entrypoint-initdb.d/004_audit_log_partition.sql` |
| Audit logs not appearing in PG | Check `AUDIT_DB_URL` in `.env`; gateway logs for `AsyncAuditWriter` flush errors |
| `rag_index_chunk_count` missing | Gateway not running or not scraped yet; wait one Prometheus scrape interval (15s) |
