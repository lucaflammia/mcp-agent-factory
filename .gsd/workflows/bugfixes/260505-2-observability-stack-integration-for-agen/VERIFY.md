# Verification: Observability Stack Integration

## Test Results

### Unit / Integration Tests
```
PYTHONPATH=src pytest tests/test_adapters.py tests/test_economics.py tests/test_knowledge_auction.py tests/test_vector_store.py -q
50 passed, 0 failed
```
Pre-existing async test failures in `test_ingest.py` (missing `pytest-asyncio`) are unrelated to this fix.

### Prometheus Scrape Targets
```
job=mcp-gateway  health=up
```

### HTTP Metrics (http_requests_total)
Labels use `status="2xx"` grouping — dashboard query `status="5xx"` will correctly select 5xx responses when they occur.
```
http_requests_total{handler="/health",method="GET",status="2xx"} 1308
http_requests_total{handler="/mcp",method="POST",status="2xx"} 6
```

### Span Metrics (agent pipeline)
`traces_calls_total` with `span_name=~"agent\..*"` returns **6 series** with correct span names:
- `agent.pdf_extract` (9 calls)
- `agent.pii_scrub` (9 calls)
- `agent.prune` (9 calls)
- `agent.llm_route` (8 calls)
- `agent.vector_store.search` (8 calls)

### Auction Bids
`mcp_auction_bids_total` is registered and exposed at `/metrics` on the gateway. It shows 0 until `demo.sh` triggers an auction — correct behavior.

### OTel Collector Dimensions
All agent-pipeline dimensions confirmed present in `otel-collector.yml`:
`agent.provider`, `agent.pages_read`, `agent.chunk_count`, `agent.input_tokens`, `agent.output_tokens`, `agent.cost_usd`, `status.code`

## Dashboard Panels Status
| Panel | Before | After |
|---|---|---|
| HTTP Error Rate (%) | Wrong regex `5..` | Fixed `status="5xx"` |
| Agent Pipeline — Span Rate | Wrong metric prefix | Fixed `traces_calls_total` |
| Agent Pipeline — Span Latency P99 | Wrong metric prefix | Fixed `traces_duration_milliseconds_bucket` |
| Pages Read per Analyze Call | Empty (no attr prefix) | `agent.pages_read` label populated |
| Chunk Count | Empty (no attr prefix) | `agent.chunk_count` label populated |
| Token Consumption | Empty (no attr prefix) | `agent.input_tokens` / `agent.output_tokens` populated |
| Cost per Request (USD) | Empty (no attr prefix) | `agent.cost_usd` label populated |
| Provider Distribution | Empty (no attr prefix) | `agent.provider` label populated |
| Agent Pipeline — Error Rate (%) | No status.code dim | `status.code` dimension added |
| Auction Bids (total) | No data (0) | Metric registered; populates on auction run |
