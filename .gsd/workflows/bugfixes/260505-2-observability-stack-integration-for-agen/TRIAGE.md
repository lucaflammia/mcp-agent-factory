# Triage: Observability Stack Integration for Agent Live Demo

## Root Cause Summary

Four distinct issues cause the "empty dashboard / no architecture" state:

### 1. Auth Server — OTEL env vars wired but no instrumentation code
`docker-compose.yml` lines 110-111 set `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_SERVICE_NAME: mcp-auth` on the auth container, but `src/mcp_agent_factory/auth/server.py` never calls `configure_telemetry()` or emits any spans. Jaeger therefore never sees `mcp-auth` as a service, breaking the architectural dependency graph.

### 2. OTel Collector — missing processor and incomplete pipeline
`observability/otel-collector.yml` has no `processors` block (no `batch`, no `memory_limiter`). The `spanmetrics` connector also lacks dimensions for the agent-level attributes (`agent.pdf_extract`, `agent.llm_route`, etc.) that the dashboard description requires. Without a `batch` processor the collector flushes every span individually, which can cause spans to be dropped under load.

### 3. Grafana Dashboard — no agent-pipeline panels
`observability/grafana/dashboards/mcp-overview.json` only has generic HTTP/process panels. There are no panels for:
- Agent span rate / latency (from `spanmetrics` via Prometheus)
- Token consumption and cost_usd (from span attributes via exemplars or recording rules)
- Provider distribution (Ollama vs. Gemini)
The "Public Dashboards" section is empty because none of the panels target the `traces_*` metrics that the OTel Collector emits.

### 4. Demo script — preflight does not verify monitoring backend
`scripts/demo.sh` checks gateway, Ollama, and `MCP_DEV_MODE`, but never checks that Prometheus (`:9090`) or Jaeger (`:16686`) are reachable. A presenter can start the demo on a stack where only the gateway profile is up and only discover the empty dashboard after Phase 2.

---

## Affected Files

| File | Issue |
|------|-------|
| `src/mcp_agent_factory/auth/server.py` | Missing `configure_telemetry()` call and FastAPI OTel instrumentation |
| `observability/otel-collector.yml` | Missing `batch` processor; missing agent-level spanmetrics dimensions |
| `observability/grafana/dashboards/mcp-overview.json` | Missing agent-pipeline panels (tokens, cost, provider, span rate) |
| `scripts/demo.sh` | Preflight does not check Prometheus/Jaeger availability |

---

## Reproduction Steps

1. `MCP_DEV_MODE=1 docker compose --profile full up -d`
2. Wait for all services to be healthy
3. Run `bash scripts/demo.sh`
4. Open `http://localhost:3000` → Public Dashboards → empty
5. Open `http://localhost:16686` → Services → no `mcp-auth` entry

---

## Fix Applied

1. **Auth instrumentation** — already present in `auth/server.py` lines 186–192 (pre-existing); no change needed.
2. **OTel Collector** — added `batch` processor to both pipelines; added agent span dimensions (`agent.provider`, `agent.pages_read`, `agent.chunk_count`, `agent.input_tokens`, `agent.output_tokens`, `agent.cost_usd`) to `spanmetrics` connector.
3. **Grafana Dashboard** — added 8 agent-pipeline panels (ids 9–16): span rate, P99 latency, pages read, chunk count, token consumption, cost, provider distribution pie, and error rate.
4. **Demo preflight** — added `check_monitoring()` function checking Prometheus `/-/healthy` and Jaeger `/api/services` before Phase 1; supports `PROMETHEUS_URL` and `JAEGER_URL` overrides.
