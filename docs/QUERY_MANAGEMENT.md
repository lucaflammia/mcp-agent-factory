# Query Management

Rate limiting, quotas, audit logging, timezone-aware windows, and cost-based limiting for the RAG `/query` endpoint.

---

## Control Layers

| Layer | Mechanism | Enforced |
|-------|-----------|----------|
| Rate limit | Token bucket per tenant (variable cost) | Before retrieval |
| Quota | Daily + hourly counters (tenant timezone) | Before retrieval |
| Audit log (real-time) | Redis 24h ring (fast stats) | After generation |
| Audit log (durable) | PostgreSQL partitioned table (async batch) | After generation |

---

## Configuration

```bash
# Rate limiting
RATE_LIMIT_QPS=10.0      # tokens/second refill rate (default 10)
RATE_LIMIT_BURST=20      # burst capacity (default 20)

# Quotas
QUOTA_DAILY=100000       # queries per day per tenant (default 100k)
QUOTA_HOURLY=10000       # queries per hour per tenant (default 10k)

# Redis
KV_TOPICS=default,audit  # "audit" topic required

# RAG-09 S1: PostgreSQL durable audit
PG_DSN=postgresql://user:pass@host/db   # unset = Redis-only
AUDIT_FLUSH_INTERVAL=10.0               # seconds between flushes
AUDIT_MAX_BUFFER=1000                   # max entries before forced flush

# RAG-09 S3: Cost weights (tune to reflect compute cost)
COST_TOP_K_PER_UNIT=0.1       # extra cost per top_k beyond 1
COST_LATENCY_MS_PER_100=0.1   # extra cost per 100ms retrieval latency
COST_REFUSAL_PENALTY=0.5      # extra cost on refused queries
COST_RETRY_PENALTY=0.25       # extra cost per retry
```

---

## API

### POST /query

```json
{ "question": "What is Q3 revenue?", "tenant": "acme-corp", "top_k": 5 }
```

| Status | Condition |
|--------|-----------|
| 200 | OK — answer + citations |
| 429 | Rate limited — `Retry-After` header set |
| 429 | Quota exceeded — resets at next window in tenant's timezone |

### GET /query/stats/{tenant}

Returns 24h aggregate from Redis (real-time):

```json
{
  "tenant": "acme-corp",
  "total_queries": 1250,
  "refusal_rate": 0.08,
  "avg_retrieval_latency_ms": 85.3,
  "avg_generation_latency_ms": 42.1,
  "avg_top_score": 0.87,
  "cost_p50": 1.2,
  "cost_p99": 3.4
}
```

### GET /query/audit/{tenant}?start=YYYY-MM-DD&end=YYYY-MM-DD&fmt=json|csv

Exports durable audit logs from PostgreSQL for a date range.

```bash
# Export Jan 2025 as CSV
curl "http://gateway:8000/query/audit/acme-corp?start=2025-01-01&end=2025-02-01&fmt=csv" \
  -H "Authorization: Bearer $TOKEN"
```

Returns all entries in the half-open range `[start, end)`. Requires `tools:orchestrate` scope.

### Admin endpoints (require `tools:orchestrate` scope)

```http
GET  /admin/quotas               → all current configs + resets_in_hours per tenant
POST /admin/quota/{tenant}       → update limits, timezone, QPS at runtime
```

POST body (all fields optional):
```json
{
  "daily_limit": 200000,
  "hourly_limit": 20000,
  "tokens_per_second": 20.0,
  "timezone": "America/New_York"
}
```

Response includes `resets_in_hours` for the tenant's local window.

Invalid timezones return `400` immediately.

---

## Audit Log Entry

Written to Redis (real-time, 24h TTL) and PostgreSQL (durable, partitioned).

```json
{
  "entry_id": "acme-corp:1700000000000",
  "tenant": "acme-corp",
  "question": "What is the Q3 revenue?",
  "top_k": 5,
  "result_count": 3,
  "top_score": 0.95,
  "refused": false,
  "refusal_reason": null,
  "retrieval_latency_ms": 85.3,
  "generation_latency_ms": 42.1,
  "cost_tokens": 1.35,
  "timestamp": "2024-11-15T10:30:00.000Z"
}
```

---

## Request Flow

```
POST /query
  → calculate_query_cost(top_k)      → estimated cost (pre-retrieval)
  → check_rate_limit(cost)           → 429 + Retry-After if bucket empty
  → check_quota(tenant_timezone)     → 429 if daily/hourly limit reached
  → retrieve + generate              → measure latencies
  → calculate_query_cost(actual)     → final cost with real latency
  → rag_query_cost_tokens.observe()  → Prometheus histogram
  → log_query(cost_tokens=cost)      → Redis (24h) + PostgreSQL async batch
  → 200 QueryResponse
```

---

## Token Bucket (Variable Cost)

- Capacity: `RATE_LIMIT_BURST` tokens
- Refill: `RATE_LIMIT_QPS` tokens/second (lazy, on each request)
- Each query deducts variable tokens (see Cost Function below)
- Bucket state persisted in Redis; TTL 1h

## Cost Function (RAG-09 S3)

```
cost = 1.0
     + max(0, top_k - 1) × COST_TOP_K_PER_UNIT
     + (retrieval_ms / 100) × COST_LATENCY_MS_PER_100
     + COST_REFUSAL_PENALTY  (if refused)
     + retries × COST_RETRY_PENALTY
```

**Example:** `top_k=10, latency=200ms, refused=false` → `1.0 + 0.9 + 0.2 = 2.1`

A query whose cost exceeds remaining tokens returns 429 with `Retry-After = cost / QPS`.

## Timezone-Aware Quota Windows (RAG-09 S2)

Quota windows are calculated in each tenant's configured timezone:

```bash
# Set timezone for a tenant
POST /admin/quota/acme-corp
{ "timezone": "America/New_York" }
```

- Quota resets at **00:00 local time** (daily) or **:00 local time** (hourly)
- DST transitions are handled correctly — no double-resets or gaps
- Default: UTC (backward-compatible with RAG-08 deployments)
- Invalid timezone string → `400 Bad Request`

## Durable Audit Log (RAG-09 S1)

PostgreSQL table `query_audit_log` is partitioned by month. The async batch writer:

- Buffers entries in memory
- Flushes every `AUDIT_FLUSH_INTERVAL` seconds (default 10s)
- Also flushes when buffer reaches `AUDIT_MAX_BUFFER` entries (default 1000)
- Falls back gracefully to Redis-only if PostgreSQL is unavailable
- Remaining buffer is flushed on graceful shutdown

Migration: `migrations/004_audit_log_partition.sql`

---

## Monitoring

```promql
# Query cost distribution
histogram_quantile(0.99, rate(rag_query_cost_tokens_bucket[5m]))

# Query volume per tenant
rate(rag_query_total{tenant="acme-corp"}[1m])

# Refusal rate
100 * increase(rag_generation_refusal_total[5m]) / increase(rag_generation_total[5m])

# 429 pressure
rate(http_requests_total{status="429"}[5m])
```

---

## Testing

```bash
# RAG-08 original tests (9 tests)
python -m pytest tests/test_query_management.py -v

# RAG-09 enhancement tests (367 tests across 4 files)
python -m pytest tests/test_rag09*.py -v

# All query management tests
python -m pytest tests/test_query_management.py tests/test_rag09*.py -v
```

---

## Troubleshooting

**Every request returns 429 immediately**
- `RATE_LIMIT_BURST` too small — increase to ≥10
- Expensive `top_k` consuming all tokens — reduce `COST_TOP_K_PER_UNIT`
- Redis unreachable — `redis-cli ping` should return `PONG`
- Clock skew — verify NTP: `timedatectl`

**Quota not resetting at expected time**
- Check tenant timezone: `GET /admin/quotas` → `tenants.<tenant>.timezone`
- Ensure the timezone is set via `POST /admin/quota/{tenant}` with `timezone` field

**Audit export empty**
- Confirm `PG_DSN` is set and PostgreSQL is reachable
- Check `AUDIT_FLUSH_INTERVAL` — data may still be in the buffer
- Run `GET /query/audit/{tenant}?start=...&end=...` with the correct date range

**Cost too aggressive (tenants hitting limits too quickly)**
- Reduce `COST_TOP_K_PER_UNIT`, `COST_LATENCY_MS_PER_100`
- Increase `RATE_LIMIT_BURST` and `RATE_LIMIT_QPS`
