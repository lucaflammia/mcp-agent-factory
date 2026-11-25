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

### Step 2b: Get a JWT for Admin Endpoints

Admin endpoints (`/admin/quota/*`, `/admin/quotas`) require a Bearer token with the `tools:orchestrate` scope signed with `JWT_SECRET`.

**Option A — Dev mode (local only)**

`MCP_DEV_MODE=1` bypasses auth for the MCP JSON-RPC endpoint and tool calls, but **admin HTTP endpoints (`/admin/quota/*`, `/admin/quotas`) still require a valid JWT** — `make_verify_token` enforces this unconditionally. Use Option B below to get a token even in dev mode.

**Option B — Self-sign with Python (no auth server needed)**

Requires `authlib` (already a project dependency).

> **Important:** The gateway validates tokens with the `JWT_SECRET` it loaded at startup, and requires `aud: "mcp-server"`. Use the same secret value the running gateway has — not necessarily what's in your shell.

```bash
# Get the secret the running gateway loaded (Docker Compose)
export JWT_SECRET="$(docker compose --profile full exec gateway printenv JWT_SECRET)"

# Or from .env directly (only works if gateway started with the same file)
export JWT_SECRET="$(grep '^JWT_SECRET=' .env | cut -d= -f2)"
```

Then mint the token:

```python
# mint_token.py
import os, time
from authlib.jose import jwt, OctKey

secret = os.environ["JWT_SECRET"]
key = OctKey.import_key(secret.encode())

claims = {
    "sub": "admin",
    "aud": "mcp-server",                   # required by resource.py
    "scope": "tools:orchestrate tools:call",
    "iat": int(time.time()),
    "exp": int(time.time()) + 3600,
}
token = jwt.encode({"alg": "HS256"}, claims, key)
print(token.decode())
```

```bash
export TOKEN="$(python mint_token.py)"
echo $TOKEN   # should be a non-empty JWT string
```

Use `$TOKEN` as the Bearer value in all admin `curl` commands below.

---

### Step 3: Verify It's Working

Run the full verification suite (all checks must pass before this feature is considered deployed):

```bash
# 1. Unit tests — 9 must pass
pytest tests/test_query_management.py -v
# Expected output: 9 passed, 0 failed

# 2. QueryManager class exists and is importable
python -c "from mcp_agent_factory.gateway.query_management import QueryManager; print('OK')"
# Expected: OK

# 3. Normal query succeeds (200)
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the Q3 revenue?","tenant":"demo-tenant","top_k":5}'
# Expected: 200

# 4. Stats endpoint returns aggregated data
curl -s http://localhost:8000/query/stats/demo-tenant | python -m json.tool
# Expected: JSON with keys total_queries, refusal_rate, avg_retrieval_latency_ms,
#           avg_generation_latency_ms, avg_top_score

# 5. Rate limit enforced — burst exhausted triggers 429 with Retry-After
# Uses a fresh tenant + low per-request quota so the test is deterministic.
# First lower the QPS via admin, then fire 60 rapid requests.
python - <<'EOF'
import requests, sys, time
BASE = "http://localhost:8000"
import os
TOKEN = os.environ.get("TOKEN", "")

# Lower rate to 1 QPS / burst 3 on a throwaway tenant so we exhaust quickly
r = requests.post(
    f"{BASE}/admin/quota/rl-verify-tenant",
    json={"tokens_per_second": 1.0},
    headers={"Authorization": f"Bearer {TOKEN}"},
)
if r.status_code not in (200, 404):
    print(f"WARNING: could not lower rate ({r.status_code}) — test may be slow")

PAYLOAD = {"question": "ping", "tenant": "ratelimit-test", "top_k": 1}
# burst=20 at 10 QPS; 60 back-to-back requests will exhaust the bucket
statuses = []
for _ in range(60):
    statuses.append(requests.post(f"{BASE}/query", json=PAYLOAD).status_code)

if 429 in statuses:
    print(f"PASS — 429 seen (first at index {statuses.index(429)})")
    for r in (requests.post(f"{BASE}/query", json=PAYLOAD) for _ in range(60)):
        if r.status_code == 429:
            print(f"Retry-After header: {r.headers.get('Retry-After')}")
            break
else:
    print("FAIL — no 429 seen after 60 requests"); sys.exit(1)
EOF

# 6. Quota endpoint returns current config
curl -s http://localhost:8000/admin/quotas \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
# Expected: JSON with daily_quota, hourly_quota, tokens_per_second, burst_size

# 7. Admin quota update accepted (200)
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8000/admin/quota/demo-tenant \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"daily_limit":500000,"hourly_limit":50000,"tokens_per_second":50.0}'
# Expected: 200

# 8. .env.example contains all config keys
grep -E "RATE_LIMIT_QPS|RATE_LIMIT_BURST|QUOTA_DAILY|QUOTA_HOURLY" .env.example
# Expected: 4 matching lines

# 9. docs/QUERY_MANAGEMENT.md exists and is non-empty
test -s docs/QUERY_MANAGEMENT.md && echo "PASS" || echo "FAIL — file missing or empty"
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
  -H "Authorization: Bearer $TOKEN"

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
  -H "Authorization: Bearer $TOKEN" \
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

### Immediate (after enabling query management)

1. **Verify tests pass**
   ```bash
   pytest tests/test_query_management.py -v
   # Expected: 9 passed
   ```

2. **Read full API reference**
   See `docs/QUERY_MANAGEMENT.md` for endpoint schemas, error codes, and Redis key layout.

3. **Set up Grafana alerting**

   Open Grafana at `http://localhost:3000` (default user/password: `admin/admin`).

   Import the RAG metrics dashboard:
   ```bash
   # Dashboard JSON is at:
   observability/grafana/dashboards/rag-metrics.json
   # In Grafana UI: Dashboards → Import → Upload JSON file
   ```

   Then add three alert rules (Alerting → Alert rules → New alert rule):

   **Alert 1 — High refusal rate**
   ```promql
   # Query A
   100 * increase(rag_generation_refusal_total[5m]) / increase(rag_generation_total[5m])
   # Condition: IS ABOVE 20   |   For: 5m
   ```

   **Alert 2 — Low relevance score**
   ```bash
   # Grafana can't alert directly on /query/stats; poll it with a cron script instead:
   # cron: */10 * * * * python check_scores.py
   import requests, sys
   stats = requests.get("http://localhost:8000/query/stats/demo-tenant").json()
   if stats["avg_top_score"] < 0.7:
       print(f"ALERT: avg_top_score={stats['avg_top_score']}")
       sys.exit(1)
   ```

   **Alert 3 — 429 spike**
   ```promql
   # Query A
   rate(http_requests_total{status="429"}[1m])
   # Condition: IS ABOVE 0.1   |   For: 1m
   ```

4. **Tune limits for your load**

   After 24–48h of traffic, check the peak observed QPS:
   ```bash
   # Check how many queries a tenant made
   curl -s http://localhost:8000/query/stats/demo-tenant | python -m json.tool
   ```

   Then set `RATE_LIMIT_QPS` to 80% of observed peak and apply immediately (no restart needed):
   ```bash
   curl -X POST http://localhost:8000/admin/quota/demo-tenant \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"tokens_per_second": 8.0}'
   # Persist by updating RATE_LIMIT_QPS in .env
   ```

5. **Set up daily stats export**

   Audit logs expire after 24h. Save `export_stats.py` and register the cron:
   ```python
   # export_stats.py
   import requests, json, datetime, pathlib

   GATEWAY = "http://localhost:8000"
   TENANTS = ["tenant-a", "tenant-b"]   # adjust as needed
   OUT_DIR = pathlib.Path("stats")
   OUT_DIR.mkdir(exist_ok=True)

   for t in TENANTS:
       stats = requests.get(f"{GATEWAY}/query/stats/{t}").json()
       stats["exported_at"] = datetime.datetime.utcnow().isoformat()
       out = OUT_DIR / f"{t}-{datetime.date.today()}.json"
       out.write_text(json.dumps(stats, indent=2))
       print(f"Exported {t} → {out}")
   ```

   Register the cron (runs at 23:00 UTC, before the 24h TTL expires):
   ```bash
   crontab -e
   # Add:
   0 23 * * * cd /path/to/mcp-agent-factory && python export_stats.py >> logs/export_stats.log 2>&1
   ```

### Upcoming (RAG-09)

RAG-09 addresses the three known limitations of this release:

| Limitation | RAG-09 Solution |
|---|---|
| Audit logs expire after 24h | PostgreSQL async batch writer — durable audit history with `/query/audit/{tenant}` export endpoint |
| Quotas reset at UTC midnight only | Per-tenant timezone support — quota windows aligned to tenant's local calendar day |
| All queries cost 1 token | Cost function based on `top_k`, latency, retries, and refusal rate — cost-aware rate limiter |

Track progress: `RAG-09-QUERY-MANAGEMENT-ENHANCEMENTS.md` at the project root.

---

**Questions?** See `docs/QUERY_MANAGEMENT.md` for detailed API, troubleshooting, and implementation notes.
