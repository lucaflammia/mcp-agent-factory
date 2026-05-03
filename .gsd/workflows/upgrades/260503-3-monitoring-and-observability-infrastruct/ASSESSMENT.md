# Assessment: Monitoring and Observability Infrastructure Enhancement

**Date:** 2026-05-03  
**Branch:** gsd/dep-upgrade/monitoring-and-observability-infrastruct

---

## Current Stack Versions

| Component | Image | Version |
|-----------|-------|---------|
| Prometheus | prom/prometheus | v2.51.2 |
| Grafana | grafana/grafana | 10.4.2 |
| Jaeger | jaegertracing/all-in-one | 1.57 |
| OTel Collector | otel/opentelemetry-collector-contrib | 0.100.0 |
| prometheus_client (Python) | prometheus_client | ≥0.20 |
| prometheus-fastapi-instrumentator | prometheus-fastapi-instrumentator | ≥6.1 |

No version upgrades are required — all components are recent. The issues are **configuration gaps**.

---

## Gap Analysis

### Gap 1: Jaeger Monitor Tab — Service Metrics Not Showing

**Root cause:** The OTel Collector exports spanmetrics with `namespace: traces`, producing metric names like `traces_calls_total` and `traces_duration_milliseconds_bucket`. Jaeger's SPM (Service Performance Monitoring) queries assume a default namespace (empty) unless told otherwise. Missing: `PROMETHEUS_QUERY_NAMESPACE: traces` in Jaeger's environment.

**Fix:** Add `PROMETHEUS_QUERY_NAMESPACE: traces` to `jaeger` service env in `docker-compose.yml`.

**Risk:** Low — additive config change.

### Gap 2: Jaeger System Architecture Graph — Empty

**Root cause:** The System Architecture (dependency) graph in Jaeger is derived from span references between services. It requires traces to have actually flowed AND the `dependencies` endpoint to be populated. With `all-in-one` and in-memory storage, dependencies are built automatically from trace data. The graph should populate once the stack is running with traffic.

**Additional concern:** The `all-in-one` image doesn't expose a dedicated dependency storage API but builds it from spans at query time. No config change needed — this is a "run traffic" requirement.

**Fix:** No config change required. Document that it populates after traffic flows.

### Gap 3: Grafana — Missing CPU and Memory Panels

**Root cause:** The current `mcp-overview.json` dashboard has 6 panels covering HTTP metrics and auction bids, but no panels for process CPU or memory usage. The gateway's `/metrics` endpoint already exposes `process_cpu_seconds_total` and `process_resident_memory_bytes` (from Python `prometheus_client` default collectors), and Prometheus already scrapes `gateway:8000/metrics`.

**Fix:** Add panels to `mcp-overview.json`:
- Process CPU Usage (rate of `process_cpu_seconds_total`)
- Process Memory (RSS) from `process_resident_memory_bytes`

**Risk:** Low — dashboard JSON edit, no service restart needed (Grafana hot-reloads provisioned dashboards).

### Gap 4: No Worker/Agent Scrape Targets

**Root cause:** There are no worker/agent services with exposed `/metrics` endpoints in the current `docker-compose.yml`. The description mentions "agent process metrics" but no agent containers exist with Prometheus instrumentation.

**Fix:** Deferred — no agent containers currently exist to scrape. No action needed.

---

## Upgrade Order

1. `docker-compose.yml` — add `PROMETHEUS_QUERY_NAMESPACE: traces` to Jaeger env (**Gap 1**)
2. `observability/grafana/dashboards/mcp-overview.json` — add CPU and Memory panels (**Gap 3**)
3. *(Deferred)* Agent /metrics scraping — requires agent service instrumentation first

---

## Risk Assessment

| Change | Risk | Rollback |
|--------|------|---------|
| Jaeger PROMETHEUS_QUERY_NAMESPACE env var | Low | Remove the env var |
| Grafana dashboard CPU/Memory panels | Low | Revert JSON file |

No breaking changes. No service restarts required except Jaeger (for env var pickup).
