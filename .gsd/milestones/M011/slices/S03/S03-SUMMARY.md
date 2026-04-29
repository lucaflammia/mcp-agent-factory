---
id: S03
parent: M011
milestone: M011
provides:
  - (none)
requires:
  []
affects:
  []
key_files:
  - (none)
key_decisions:
  - (none)
patterns_established:
  - (none)
observability_surfaces:
  - ["GET /metrics — Prometheus text format via prometheus-fastapi-instrumentator", "http_requests_total by handler/method/status", "http_request_duration_seconds_bucket for P50/P99", "mcp_auction_bids_total by agent_id", "Grafana dashboard uid=mcp-overview at localhost:3000"]
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-04-29T05:00:10.750Z
blocker_discovered: false
---

# S03: Prometheus metrics and Grafana dashboard

**Gateway now exports Prometheus metrics; Grafana dashboard has 6 live panels showing request rate, latency (P50+P99), error rate, tool call rate, and auction bids**

## What Happened

The gateway container predated the prometheus-fastapi-instrumentator dependency being added to pyproject.toml's otel extra. Rebuilt the image (EXTRAS=infra,otel), restarted, and confirmed /metrics returns Prometheus text format. Prometheus scrape target mcp-gateway came up immediately. Enriched the dashboard JSON from 4 to 6 panels by adding P50 latency and MCP tool call rate panels. Grafana provisioning auto-reloaded within seconds. Generated test traffic confirmed 16 requests recorded and queryable. 354 non-integration tests pass with no regressions.

## Verification

curl http://localhost:8000/metrics returns http_requests_total; Prometheus mcp-gateway target=up; Grafana dashboard has 6 panels; 354 pytest non-integration tests pass

## Requirements Advanced

None.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `observability/grafana/dashboards/mcp-overview.json` — Added P50 latency and MCP tool call rate panels; bumped to 6 panels total
