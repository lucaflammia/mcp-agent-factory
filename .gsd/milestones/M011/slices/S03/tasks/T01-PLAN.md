---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Rebuild gateway image and verify /metrics endpoint

The gateway container predates the prometheus-fastapi-instrumentator dep. Rebuild the image, restart the gateway service, and confirm /metrics returns Prometheus text format with http_requests_total and mcp_auction_bids_total metrics.

## Inputs

- `docker-compose.yml`
- `pyproject.toml`

## Expected Output

- `Gateway /metrics returns prometheus text`
- `Prometheus scrape target mcp-gateway is UP`

## Verification

curl http://localhost:8000/metrics | grep http_requests_total exits 0; Prometheus target mcp-gateway shows state=up
