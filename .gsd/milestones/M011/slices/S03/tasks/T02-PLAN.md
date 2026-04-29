---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T02: Enrich Grafana dashboard and verify live panels

Add P50 latency panel and an MCP tool call rate panel to the existing dashboard JSON. Send a test request to generate metrics, then verify Grafana shows non-zero values.

## Inputs

- `observability/prometheus.yml`
- `observability/grafana/dashboards/mcp-overview.json`

## Expected Output

- `Dashboard has 6 panels including P50 latency and tool call rate`
- `All panels show data after test request`

## Verification

Grafana at localhost:3000 dashboard shows non-zero request rate and latency after test request
