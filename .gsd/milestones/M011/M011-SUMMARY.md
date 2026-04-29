---
id: M011
title: "Dockerized Observable Reference Architecture"
status: complete
completed_at: 2026-04-29T05:02:45.899Z
key_decisions:
  - OTEL tracing configured in FastAPI lifespan (not per-request) for idempotent startup
  - prometheus-fastapi-instrumentator added to otel extras and exposed at /metrics before route registration
  - tools/list is intentionally public (read-only discovery); auth only required for tools/call
  - Grafana dashboard provisioned via filesystem mount — auto-reloads without container restart
key_files:
  - docker-compose.yml
  - Dockerfile
  - src/mcp_agent_factory/gateway/telemetry.py
  - src/mcp_agent_factory/gateway/app.py
  - src/mcp_agent_factory/gateway/service_layer.py
  - src/mcp_agent_factory/economics/auction.py
  - observability/grafana/dashboards/mcp-overview.json
  - observability/prometheus.yml
  - scripts/smoke_test.sh
  - tests/test_otel_spans.py
  - tests/test_m011_otel_integration.py
lessons_learned:
  - Container images must be rebuilt after adding new pip extras — docker compose up -d alone reuses stale layers
  - prometheus-fastapi-instrumentator must be wired before FastAPI route registration to instrument all endpoints
  - Smoke tests for auth should test mutating endpoints (tools/call), not read-only discovery endpoints (tools/list)
---

# M011: Dockerized Observable Reference Architecture

**docker compose --profile full up brings 12 services healthy with end-to-end OTEL tracing, Prometheus metrics, and a live Grafana dashboard**

## What Happened

Four slices delivered a fully observable, containerized reference architecture. S01 wired a 12-service Compose stack (gateway, auth, Redis×4, Kafka, Zookeeper, Jaeger, Prometheus, Grafana, Caddy) with health checks and an otel build profile. S02 added OpenTelemetry tracing: configure_telemetry() in the gateway lifespan, FastAPIInstrumentor auto-instrumentation, manual mcp.tools/call and tool.{name} spans in service_layer, and auction.py OTEL integration — confirmed in Jaeger via 6 unit tests and 3 live integration tests. S03 rebuilt the gateway image to include prometheus-fastapi-instrumentator, confirmed /metrics live, and enriched the Grafana dashboard from 4 to 6 panels (P50 latency + MCP tool call rate added). S04 fixed the smoke test (tools/list is public; tools/call is the correct auth check) and verified README accuracy. 354 non-integration tests pass throughout.

## Success Criteria Results

All 5 criteria met: 12-service stack healthy, Jaeger traces confirmed, Grafana dashboard live with 6 panels, smoke test exits 0, 354 tests pass

## Definition of Done Results



## Requirement Outcomes



## Deviations

None.

## Follow-ups

None.
