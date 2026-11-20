# Query Management — Quick Start Guide

## 30-Second Overview

Three protection layers on the `/query` endpoint:

1. **Rate Limit** — Max queries per second (default 10 QPS, allows 20-query burst)
2. **Quota** — Max queries per day/hour (default 100k/day, 10k/hour)
3. **Audit Log** — Every query recorded with latency and results

Returns `429 Too Many Requests` when limits exceeded.

## Enable Query Management

### Step 1: Set Environment Variables

```bash
# .env or docker-compose.yml

# Rate limiting: 10 queries/sec with 20-query burst
RATE_LIMIT_QPS=10.0
RATE_LIMIT_BURST=20

# Daily limit: 100k queries/day per tenant
QUOTA_DAILY=100000

# Hourly limit: 10k queries/hour per tenant  
QUOTA_HOURLY=10000

# Redis must be running (for state persistence)
REDIS_URL=redis://localhost:6379
```

### Step 2: Start Gateway

```bash
# Existing start command — now has rate limiting baked in
docker compose --profile full up

# Or without Docker:
python -m mcp_agent_factory.gateway.run
```

### Step 3: Verify It's Working

```bash
# Normal query (should succeed)
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the Q3 revenue?",
    "tenant": "demo-tenant",
    "top_k": 5
  }'

# Response: 200 OK with answer

# View stats for the tenant
curl http://localhost:8000/query/stats/demo-tenant

# Response: 
# {
#   "tenant": "demo-tenant",
#   "total_queries": 1,
#   "refusal_rate": 0.0,
#   "avg_retrieval_latency_ms": 85.3,
#   "avg_generation_latency_ms": 42.1,
#   "avg_top_score": 0.95
# }
```

## Understanding Rate Limits

### Token Bucket Algorithm

```
Burst window: 20 queries allowed immediately
Refill rate: 10 queries per second
```

**Timeline:**
```
T=0s     : Requests 1-20 succeed (use burst tokens)
T=0.1s   : Request 21 → 429 (no tokens, Retry-After: 0.9s)
T=1.0s   : 10 tokens refilled → Requests 21-30 can proceed
T=2.0s   : 10 more tokens refilled → Requests 31-40 can proceed
...
T=5m+    : Burst window expires if idle, resets to 20
```

**Key insight:** Bursts are free, sustained load hits 10 QPS limit.

### Client Backoff

```python
import time
import requests

def query_with_backoff(question, tenant):
    max_retries = 5
    retry_after = 1
    
    for attempt in range(max_retries):
        resp = requests.post(
            "http://localhost:8000/query",
            json={
                "question": question,
                "tenant": tenant,
                "top_k": 5,
            }
        )
        
        if resp.status_code == 200:
            return resp.json()
        
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", retry_after))
            print(f"Rate limited. Waiting {retry_after}s...")
            time.sleep(retry_after)
            continue
        
        resp.raise_for_status()
    
    raise Exception("Max retries exceeded")

# Usage
answer = query_with_backoff("What is 2+2?", "my-tenant")
print(answer["answer"])
```

## Understanding Quotas

### Daily Quota (100k queries/day)

Resets at **00:00 UTC every day**.

```
Day 1, 00:00 UTC: Counter at 0/100k
Day 1, 12:00 UTC: 50k queries made → counter at 50k/100k
Day 1, 23:59 UTC: Counter at 99.9k/100k (almost exhausted)
Day 2, 00:00 UTC: Counter resets to 0/100k (new day)
```

### Hourly Quota (10k queries/hour)

Resets at **top of every hour UTC**.

```
Hour 1 (00:00-00:59 UTC): 0/10k → 5/10k → 10/10k (exhausted)
Hour 2 (01:00-01:59 UTC): 0/10k (counter reset)
```

**Both quotas independent:** You can hit hourly limit without consuming daily quota in an unusual way.

### Check Quota Status

```bash
# See how many queries used so far
curl http://localhost:8000/query/stats/demo-tenant | jq .total_queries

# See refusal rate (quality metric)
curl http://localhost:8000/query/stats/demo-tenant | jq .refusal_rate
```

## Admin Operations

### View Current Limits

```bash
curl -X GET http://localhost:8000/admin/quotas \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>"

# Response:
# {
#   "daily_quota": 100000,
#   "hourly_quota": 10000,
#   "tokens_per_second": 10.0,
#   "burst_size": 20
# }
```

### Update Limits for a Tenant

```bash
curl -X POST http://localhost:8000/admin/quota/vip-customer \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "daily_limit": 500000,
    "hourly_limit": 50000,
    "tokens_per_second": 50.0
  }'

# Response:
# {
#   "tenant": "vip-customer",
#   "daily_quota": 500000,
#   "hourly_quota": 50000,
#   "tokens_per_second": 50.0
# }
```

**Note:** This updates limits **in-memory** for the current gateway instance. For persistent config changes, update `.env` and restart the gateway.

## Audit Trail

### Query Metadata

Every query is logged with:
- Retrieval latency (embedding search + vector operations)
- Generation latency (LLM call)
- Number of results returned
- Top result similarity score
- Whether the answer was refused
- Exact timestamp

### Access Audit Data

```bash
# Get stats for a tenant (aggregates audit logs from last 24h)
curl http://localhost:8000/query/stats/demo-tenant

# Example response:
{
  "tenant": "demo-tenant",
  "total_queries": 1250,
  "refusal_rate": 0.08,                    # 8% of queries refused
  "avg_retrieval_latency_ms": 85.3,        # 85ms to find chunks
  "avg_generation_latency_ms": 42.1,       # 42ms to generate answer
  "avg_top_score": 0.87                    # Average relevance score
}
```

### Audit Log Details

Logs are stored in Redis with 24-hour TTL. Each entry:

```json
{
  "entry_id": "tenant-1:1700000000000",
  "tenant": "tenant-1",
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

**Before logs expire (24h):**
- Use `/query/stats/{tenant}` to get aggregated metrics
- Export to your data warehouse for long-term analysis
- Set up alerts on high refusal rates

## Troubleshooting

### "Rate limit exceeded" immediately on first request

**Problem:** Every request returns 429.

**Check:**
1. Redis running? `redis-cli ping` → should return `PONG`
2. `RATE_LIMIT_BURST` >= 10? (default 20 is fine)
3. Clock skew? `timedatectl` → should show `System clock synchronized: yes`

**Solution:**
- Start Redis: `redis-server`
- Check env vars: `echo $RATE_LIMIT_BURST` → should be 20
- Sync clock: `sudo timedatectl set-ntp true`

### Quota never resets

**Problem:** Tenant stuck at quota even after 24h.

**Root cause:** Quotas use UTC calendar days. If tenant is in UTC-8:
- Daily quota resets at 16:00 (8am PST previous day)

**Solution:** Document to tenant. If you need timezone support, file an issue.

### Can't see audit logs after 24h

**Problem:** `/query/stats/{tenant}` returns 0 queries after 24h.

**Root cause:** Audit logs expire after 24h (TTL). This is by design.

**Solution:** Export stats before logs expire:
```python
# Every 23h, fetch and store stats
stats = requests.get(f"http://localhost:8000/query/stats/{tenant}").json()
# → Send to data warehouse, Kafka, etc.
```

## Configuration Recipes

### Free Tier (Shared Resource)

```bash
RATE_LIMIT_QPS=1.0           # 1 query/sec
RATE_LIMIT_BURST=5           # Allow 5 burst queries
QUOTA_DAILY=1000             # 1k queries/day
QUOTA_HOURLY=100             # 100 queries/hour
```

### Professional Tier (Dedicated)

```bash
RATE_LIMIT_QPS=50.0          # 50 queries/sec
RATE_LIMIT_BURST=100         # Allow 100 burst queries
QUOTA_DAILY=1000000          # 1M queries/day
QUOTA_HOURLY=100000          # 100k queries/hour
```

### Enterprise Tier (Custom)

```bash
RATE_LIMIT_QPS=200.0         # 200 queries/sec
RATE_LIMIT_BURST=500         # Allow 500 burst queries
QUOTA_DAILY=10000000         # 10M queries/day (unlimited effectively)
QUOTA_HOURLY=1000000         # 1M queries/hour
```

Then use `/admin/quota/{tenant}` to override per-tenant.

## Monitoring

### Key Metrics to Watch

```promql
# Refusal rate trending (quality signal)
100 * increase(rag_generation_refusal_total[5m]) / increase(rag_generation_total[5m])

# Query throughput (load signal)
rate(rag_query_total{tenant="demo"}[1m])

# Rate limit pressure (use /query/stats instead)
GET /query/stats/demo → avg_top_score trending down = quality degradation
```

### Alerting Rules

```
Alert if refusal_rate > 0.2 for 5m
Alert if avg_top_score < 0.7 for 10m
Alert if rate(http_errors{status="429"}[1m]) > 0.1
```

## Next Steps

- [ ] Read full API docs: `docs/QUERY_MANAGEMENT.md`
- [ ] Run tests: `pytest tests/test_query_management.py -v`
- [ ] Set up monitoring: Configure Grafana queries above
- [ ] Scale: Tune RATE_LIMIT_QPS based on cluster capacity
- [ ] Export: Set up daily exports of query stats to data warehouse

---

**Questions?** See `docs/QUERY_MANAGEMENT.md` for detailed API, troubleshooting, and implementation notes.
