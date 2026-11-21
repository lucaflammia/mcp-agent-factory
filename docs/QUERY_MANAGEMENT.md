# Query Management

Rate limiting, quotas, and audit logging for the RAG `/query` endpoint.

## Three Layers of Control

| Layer | Mechanism | Enforced |
|-------|-----------|----------|
| Rate limit | Token bucket per tenant | Before retrieval |
| Quota | Daily + hourly counters (UTC) | Before retrieval |
| Audit log | Full query metadata → Redis (24h TTL) | After generation |

## Configuration

```bash
RATE_LIMIT_QPS=10.0      # tokens/second refill rate (default 10)
RATE_LIMIT_BURST=20      # burst capacity (default 20)
QUOTA_DAILY=100000       # queries per UTC day per tenant
QUOTA_HOURLY=10000       # queries per UTC hour per tenant
KV_TOPICS=default,audit  # Redis topics; "audit" is required
```

## API

### POST /query

```json
{ "question": "What is Q3 revenue?", "tenant": "acme-corp", "top_k": 5 }
```

| Status | Condition |
|--------|-----------|
| 200 | OK — answer + citations |
| 429 | Rate limited — `Retry-After` header set |
| 429 | Quota exceeded — resets at next UTC window |

### GET /query/stats/{tenant}

Returns 24h aggregate (from audit logs):

```json
{
  "tenant": "acme-corp",
  "total_queries": 1250,
  "refusal_rate": 0.08,
  "avg_retrieval_latency_ms": 85.3,
  "avg_generation_latency_ms": 42.1,
  "avg_top_score": 0.87
}
```

### Admin endpoints (require `tools:orchestrate` scope)

```http
GET  /admin/quotas               → all current configs
POST /admin/quota/{tenant}       → update limits at runtime
```

POST body:
```json
{ "daily_limit": 200000, "hourly_limit": 20000, "tokens_per_second": 20.0 }
```

## Audit Log Entry

Stored in Redis under key `audit/{tenant}:{epoch_ms}`, TTL 24h. Questions truncated to 500 chars.

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
  "timestamp": "2024-11-15T10:30:00.000Z"
}
```

## Request Flow

```
POST /query
  → check_rate_limit()     → 429 if bucket empty
  → check_quota()          → 429 if daily/hourly limit reached
  → retrieve + generate    → measure latencies
  → log_query()            → write to KV audit topic + structured log
  → 200 QueryResponse
```

## Token Bucket

- Capacity: `RATE_LIMIT_BURST` tokens
- Refill: `RATE_LIMIT_QPS` tokens/second (lazy, on each request)
- Bucket state persisted in Redis; TTL 1h (resets if idle)

## Quota Windows

Both windows use **UTC calendar keys** — they auto-expire from Redis with no cleanup needed.

- Daily: resets 00:00 UTC
- Hourly: resets top of hour UTC

## Monitoring

```promql
# Query volume per tenant
rate(rag_query_total{tenant="acme-corp"}[1m])

# Refusal rate
100 * increase(rag_generation_refusal_total[5m]) / increase(rag_generation_total[5m])

# 429 pressure
rate(http_requests_total{status="429"}[5m])
```

## Testing

```bash
python -m pytest tests/test_query_management.py -v
```

Covers: rate limit burst + refill, daily/hourly quota, audit log storage + truncation, stats aggregation.

## Troubleshooting

**Every request returns 429 immediately**
- `RATE_LIMIT_BURST` too small — increase to ≥10
- Redis unreachable — `redis-cli ping` should return `PONG`
- Clock skew — verify NTP: `timedatectl`

**Quota not resetting**
- Resets at 00:00 UTC, not local time. For UTC-8 tenants this is 16:00 PST.
- Per-tenant timezone support is planned in RAG-09.

**Audit logs empty after 24h**
- TTL is 24h by design. Export stats before expiry if you need history.
- Durable PostgreSQL persistence is planned in RAG-09.

## Known Limitations (addressed in RAG-09)

| Limitation | RAG-09 fix |
|------------|------------|
| Audit logs expire after 24h | PostgreSQL async batch writer |
| UTC-only quota windows | Per-tenant timezone support |
| All queries cost 1 token | Cost function (top_k / latency / retries) |
