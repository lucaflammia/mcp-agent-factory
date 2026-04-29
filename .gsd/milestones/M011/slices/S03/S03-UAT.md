# S03: Prometheus metrics and Grafana dashboard — UAT

**Milestone:** M011
**Written:** 2026-04-29T05:00:10.751Z

## UAT: S03 — Prometheus metrics and Grafana dashboard

### Setup
Stack running: `docker compose --profile full up -d`

### Check 1: /metrics endpoint
```
curl http://localhost:8000/metrics | grep http_requests_total
```
Expected: lines with `http_requests_total{handler=...}` values

### Check 2: Prometheus target UP
Open http://localhost:9090/targets — mcp-gateway row shows State=UP

### Check 3: Grafana dashboard
Open http://localhost:3000 (admin/admin) → Dashboards → MCP Agent Factory — Overview
Expected: 6 panels visible — Request Rate, Latency P99, Latency P50, Error Rate, Tool Call Rate, Auction Bids

### Check 4: Live data
Send a request: `curl http://localhost:8000/health`
Wait 15s for scrape. All timeseries panels show data points.

### Result: PASS
