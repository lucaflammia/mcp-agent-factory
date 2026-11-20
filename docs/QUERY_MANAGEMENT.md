# Query Management — Rate Limiting, Quotas, and Audit Logging

This document describes the query management system for monitoring and controlling tenant usage of the RAG `/query` endpoint.

## Overview

The gateway enforces three layers of control:

1. **Rate Limiting** — Token bucket algorithm, per-tenant QPS limit with burst allowance
2. **Quotas** — Daily and hourly usage limits per tenant
3. **Audit Logging** — Complete query audit trail with latency and results metadata

All three are enforced **before retrieval** (rate limit and quota) or **after generation** (audit log).

## Configuration

Set via environment variables or Pydantic config:

```bash
# Rate limiting: tokens per second (default 10 QPS)
RATE_LIMIT_QPS=10.0

# Burst allowance: requests that can exceed QPS briefly (default 20)
RATE_LIMIT_BURST=20

# Daily quota: queries per 24h UTC window per tenant (default 100k)
QUOTA_DAILY=100000

# Hourly quota: queries per 1h UTC window per tenant (default 10k)
QUOTA_HOURLY=10000

# KV topics for Redis (audit logs stored under "audit" topic)
KV_TOPICS=default,audit
```

All defaults support 100 tenants × 24h = 2.4M queries/day before hitting limits. Adjust based on your capacity.

## HTTP API

### Query Endpoint (Existing)

```http
POST /query
Content-Type: application/json

{
  "question": "What is the Q3 revenue?",
  "tenant": "acme-corp",
  "top_k": 5
}
```

**Success (200):**
```json
{
  "answer": "Q3 2024 revenue was $42M...",
  "refused": false,
  "citations": ["chunk-1", "chunk-2"],
  "refusal_reason": null
}
```

**Rate Limited (429):**
```json
{
  "detail": "Rate limit exceeded. Retry after 0.1s",
  "headers": {"Retry-After": "1"}
}
```

**Quota Exceeded (429):**
```json
{
  "detail": "Daily quota exceeded (98000/100000). Resets in 3600s"
}
```

### Query Stats Endpoint

```http
GET /query/stats/{tenant}
```

Returns aggregated statistics for a tenant (last 24h of audit logs):

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

### Admin: Quota Configuration

Requires `tools:orchestrate` scope (authenticated request with bearer token).

**Get current quotas:**
```http
GET /admin/quotas
Authorization: Bearer <token>
```

**Update quotas for a tenant:**
```http
POST /admin/quota/{tenant}
Authorization: Bearer <token>
Content-Type: application/json

{
  "daily_limit": 200000,
  "hourly_limit": 20000,
  "tokens_per_second": 20.0
}
```

Response:
```json
{
  "tenant": "acme-corp",
  "daily_quota": 200000,
  "hourly_quota": 20000,
  "tokens_per_second": 20.0
}
```

## Audit Log Format

Each query is logged with complete metadata for post-hoc analysis. Logs are stored in Redis under the `audit` KV topic with TTL of 24 hours.

**Entry ID:** `{tenant}:{epoch_milliseconds}`

**Entry Structure:**
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

Questions are truncated to 500 characters for storage efficiency.

## Token Bucket Algorithm

The rate limiter uses a **token bucket** per tenant:

- **Capacity**: `burst_size` tokens (default 20)
- **Refill rate**: `tokens_per_second` per second (default 10 QPS)
- **Cost per request**: 1 token

**Example:** With `burst_size=20, tokens_per_second=10`:
- Requests 1-20: Allowed immediately (burst)
- Requests 21+: Allowed at ~10/second (token refill rate)
- If idle 1 second: Bucket refills to 10 tokens

Buckets are stored in Redis with 1-hour TTL and reset if not accessed within that window.

## Quota Windows

Quotas use **UTC calendar windows**:

- **Daily**: Resets at 00:00 UTC every day (key: `YYYY-MM-DD`)
- **Hourly**: Resets at top of hour UTC (key: `YYYY-MM-DD-HH`)

If a tenant hits a quota at 23:55 UTC with daily_limit=100k:
- Last 5 minutes: Can make 0 queries
- At 00:00 UTC: Quota resets, can make up to 100k queries again

Both quotas are **independent**. A tenant can hit the hourly limit without consuming daily quota in an unusual way.

## Flow Diagram

```
POST /query {question, tenant, top_k}
  ↓
[Check Rate Limit] — tokens available?
  ├─ Yes: Proceed
  └─ No: 429 Retry-After
  ↓
[Check Daily Quota] — used < limit?
  ├─ Yes: Proceed
  └─ No: 429 Daily Quota Exceeded
  ↓
[Retrieve + Generate]
  ├─ Measure retrieval_latency_ms
  ├─ Measure generation_latency_ms
  └─ Track result_count, top_score, refused
  ↓
[Log to Audit Trail]
  ├─ Store in KV: audit/{tenant}:{epoch_ms}
  ├─ Emit to logger: event=query_logged
  └─ Set TTL: 24 hours
  ↓
Return 200 + QueryResponse
```

## Monitoring

### Prometheus Metrics

The existing `/metrics` endpoint exposes:
- `rag_query_total` — Total queries by tenant
- `rag_query_empty_results_total` — Queries with no results
- `rag_generation_refusal_total` — Generation refusals by reason

### Grafana Queries

**Query volume per tenant:**
```promql
rate(rag_query_total{tenant="acme-corp"}[1m])
```

**Rate limit pressure (burst exhaustion):**
```promql
histogram_quantile(0.95, rate(rag_retrieval_score[5m]))
```

**Refusal rate trending:**
```promql
100 * increase(rag_generation_refusal_total[5m]) / increase(rag_generation_total[5m])
```

## Best Practices

### For Operators

1. **Start conservative**: Set quotas 20-30% above baseline, then relax after stable week
   ```
   Daily baseline: 50k queries/day
   Set daily quota: 65k
   After 1 week stable: Increase to 80k if no complaints
   ```

2. **Monitor refusal rate**: Sustained >20% refusal means index quality or query patterns may have shifted
   ```
   GET /query/stats/acme-corp → refusal_rate trending up?
   → Check retrieval scores, re-evaluate index
   ```

3. **Tune rate limits for latency profile**:
   ```
   If avg_retrieval_latency_ms=100ms + avg_generation_latency_ms=50ms = 150ms per query
   → 10 QPS = ~1.5s sustained load
   → Burst=20 allows 20 quick queries before backing off
   ```

4. **Alert on quota exhaustion**: Set up monitoring on 429 responses
   ```
   rate(http_requests_total{status="429"}[5m]) > 0.1
   ```

### For Developers

1. **Handle 429 gracefully**: Client should respect Retry-After header
   ```python
   import backoff
   
   @backoff.on_exception(
       backoff.expo,
       requests.HTTPError,
       giveup=lambda e: e.response.status_code != 429,
       max_tries=5,
   )
   def query_with_backoff(question, tenant):
       resp = requests.post("/query", json={"question": question, "tenant": tenant})
       resp.raise_for_status()
       return resp.json()
   ```

2. **Batch queries during load**: Instead of 10k individual requests, batch into 100-request chunks
   ```python
   # Slow (hits rate limit)
   for q in queries:
       await gateway.query(q, tenant)
   
   # Fast (burst through 100, then backoff)
   for batch in chunked(queries, 100):
       results = await asyncio.gather(*[gateway.query(q, tenant) for q in batch])
   ```

3. **Monitor audit stats before releasing**: Check refusal rate is <10% on staging
   ```
   GET /query/stats/staging-tenant
   → Expect refusal_rate < 0.1, avg_top_score > 0.8
   ```

## Implementation Details

### Rate Limiting

Implemented in `src/mcp_agent_factory/gateway/query_management.py:QueryManager.check_rate_limit()`.

- Uses Redis `get/setex` to persist bucket state
- Bucket is JSON: `{tokens: float, last_refill: timestamp}`
- Refill happens on every request (lazy evaluation)
- Buckets TTL: 1 hour (reset if idle)

### Quota Tracking

Implemented in `src/mcp_agent_factory/gateway/query_management.py:QueryManager.check_quota()`.

- Uses Redis `incr/expire` to track count
- Keys include UTC window (day or hour) so they auto-reset
- No complex cleanup — old window keys auto-expire from Redis

### Audit Logging

Implemented in `src/mcp_agent_factory/gateway/query_management.py:QueryManager.log_query()`.

- Stores in KV store under `audit` topic (requires `KV_TOPICS=audit` or auto-added)
- Also emits structured log line for immediate visibility: `event=query_logged`
- TTL: 24 hours (configurable via `audit_log_ttl_seconds` parameter)

### Integration Points

1. **Gateway initialization** (`app.py:lifespan`):
   - Adds "audit" to KV topics
   - Initializes QueryManager with config from env vars

2. **Query endpoint** (`app.py:query_endpoint`):
   - Calls `check_rate_limit()` before retrieval
   - Calls `check_quota()` before retrieval
   - Measures latencies during retrieval and generation
   - Calls `log_query()` with full metadata after generation

3. **Admin endpoints** (`app.py`):
   - `GET /query/stats/{tenant}` — Fetches and aggregates audit logs
   - `POST /admin/quota/{tenant}` — Updates config in-memory
   - `GET /admin/quotas` — Returns current config

## Testing

Run tests:
```bash
python -m pytest tests/test_query_management.py -v
```

Tests cover:
- Rate limit burst and refill
- Quota daily/hourly tracking
- Audit log storage and truncation
- Stats aggregation

For integration testing, start the full stack:
```bash
docker compose --profile full up
# Then: POST http://localhost:8000/query
```

## Troubleshooting

### "Rate limit exceeded" immediately

**Symptom:** Every request returns 429.

**Causes:**
1. `RATE_LIMIT_BURST` is too small (default 20)
2. Redis is unreachable (checks will fail silently and allow requests, but rate state is lost)
3. Clock skew (bucket refill calculation assumes server clocks are synchronized)

**Fix:**
1. Check `RATE_LIMIT_BURST` >= 10
2. Verify Redis: `redis-cli ping` → `PONG`
3. Verify NTP: `timedatectl` → `System clock synchronized: yes`

### Quotas not resetting

**Symptom:** Daily quota stays at 0 even after 24h.

**Cause:** Quota key is tracked per UTC calendar day, but tenant's local timezone may differ.

**Fix:** Quotas always reset at 00:00 UTC. If tenant is in UTC-8:
- Resets at 16:00 previous day (PST)
- Document this explicitly to tenant

**Alternative:** Contact maintainer to implement per-tenant timezone offsets (not yet implemented).

### Audit logs disappearing

**Symptom:** `GET /query/stats/{tenant}` returns 0 queries after 24h.

**Cause:** TTL is set to 24h by default.

**Fix:** Increase `audit_log_ttl_seconds` on QueryManager init, or export logs before TTL expires:
```python
# Before logs expire, fetch and persist
stats = await gateway.get_query_stats("tenant")
# → Send to data warehouse, Kafka, etc.
```

