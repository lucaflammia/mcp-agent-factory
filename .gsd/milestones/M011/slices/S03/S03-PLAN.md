# S03: Prometheus metrics and Grafana dashboard

**Goal:** Expose Prometheus metrics from the gateway and verify Grafana dashboard shows live data
**Demo:** Open Grafana at localhost:3000; dashboard shows live request rate, latency percentiles, and auction bid count

## Must-Haves

- curl http://localhost:8000/metrics returns prometheus text; Prometheus target mcp-gateway is UP; Grafana dashboard panels show non-zero data after sending a request

## Proof Level

- This slice proves: Not provided.

## Integration Closure

Not provided.

## Verification

- Not provided.

## Tasks

- [x] **T01: Rebuild gateway image and verify /metrics endpoint** `est:10m`
  The gateway container predates the prometheus-fastapi-instrumentator dep. Rebuild the image, restart the gateway service, and confirm /metrics returns Prometheus text format with http_requests_total and mcp_auction_bids_total metrics.
  - Files: `Dockerfile`, `src/mcp_agent_factory/gateway/app.py`
  - Verify: curl http://localhost:8000/metrics | grep http_requests_total exits 0; Prometheus target mcp-gateway shows state=up

- [x] **T02: Enrich Grafana dashboard and verify live panels** `est:15m`
  Add P50 latency panel and an MCP tool call rate panel to the existing dashboard JSON. Send a test request to generate metrics, then verify Grafana shows non-zero values.
  - Files: `observability/grafana/dashboards/mcp-overview.json`
  - Verify: Grafana at localhost:3000 dashboard shows non-zero request rate and latency after test request

- [x] **T03: Run full test suite — confirm no regressions** `est:5m`
  Run pytest excluding integration tests to confirm the metrics wiring didn't break anything.
  - Verify: pytest -m 'not integration' exits 0

## Files Likely Touched

- Dockerfile
- src/mcp_agent_factory/gateway/app.py
- observability/grafana/dashboards/mcp-overview.json
