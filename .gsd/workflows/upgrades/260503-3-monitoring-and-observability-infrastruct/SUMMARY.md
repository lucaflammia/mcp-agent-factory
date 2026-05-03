# Summary: Monitoring and Observability Infrastructure Enhancement

**Date:** 2026-05-03  
**Branch:** gsd/dep-upgrade/monitoring-and-observability-infrastruct  
**Commit:** b1b9565

---

## Changes Made

### 1. Jaeger Monitor Tab — SPM Namespace Fix
**File:** `docker-compose.yml`  
**Change:** Added `PROMETHEUS_QUERY_NAMESPACE: traces` to the `jaeger` service environment.  
**Why:** The OTel Collector spanmetrics connector exports metrics with `namespace: traces`, producing names like `traces_calls_total`. Jaeger SPM was querying without a namespace prefix, so the Monitor tab showed no data. This env var tells Jaeger's query layer to prepend `traces_` when building PromQL queries.

### 2. Grafana CPU and Memory Panels
**File:** `observability/grafana/dashboards/mcp-overview.json`  
**Change:** Added two panels (IDs 7 and 8) at row y=24:
- **Panel 7 — Gateway CPU Usage (%):** `rate(process_cpu_seconds_total{job="mcp-gateway"}[1m]) * 100`
- **Panel 8 — Gateway Memory RSS (MB):** `process_resident_memory_bytes{job="mcp-gateway"} / 1024 / 1024`

Both metrics are emitted by default by Python's `prometheus_client` and are already being scraped by Prometheus from `gateway:8000/metrics`.

---

## Deferred Items

- **System Architecture graph (Jaeger):** No config change needed. The dependency graph is automatically computed from trace spans at query time. It will populate after traffic flows through the stack.
- **Agent/worker /metrics scraping:** No agent containers with Prometheus instrumentation exist currently. Deferred until agents are instrumented.

---

## No Version Upgrades

All component versions (Jaeger 1.57, Prometheus v2.51.2, Grafana 10.4.2, OTel Collector 0.100.0) are current and were not changed. All issues were configuration gaps, not version incompatibilities.
