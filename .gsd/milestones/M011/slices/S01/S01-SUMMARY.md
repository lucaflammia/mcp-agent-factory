---
id: S01
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
  - ["Auth REDIS_URL wired to redis:6379 — avoids fakeredis dev dep in production image", "Dockerfile skips ML extras by default (lazy import in embedder means health checks work without torch)", "Kafka dual listeners: PLAINTEXT_INTERNAL://kafka:29092 internal, PLAINTEXT_EXTERNAL://localhost:9092 for host", "Caddy ports 8080/8443: host port 80 was already bound"]
patterns_established:
  - (none)
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-04-28T16:03:56.214Z
blocker_discovered: false
---

# S01: Full-stack Compose profile

**docker compose --profile full up -d brings all 12 services to healthy state in under 2 minutes from a clean start.**

## What Happened

Started from a docker-compose.yml that only had Redis and gateway wired up (no profiles, missing auth, no observability). Three blockers surfaced during execution: (1) auth server crashed with ModuleNotFoundError for fakeredis because REDIS_URL wasn't set — fixed by adding REDIS_URL to auth service; (2) gateway crashed with ModuleNotFoundError for numpy because the pruner imports it at module load and we skipped ml extras — fixed by adding numpy explicitly to the Dockerfile; (3) Caddy failed to bind port 80 already in use — remapped to 8080/8443. Kafka's ADVERTISED_LISTENERS were also broken (localhost:9092 unreachable inside Docker) — fixed with dual-listener config. All 12 services reach healthy state.

## Verification

docker compose --profile full ps shows all 12 services Up (healthy). curl localhost:16686 → 200. curl localhost:9090/-/healthy → Prometheus Server is Healthy. curl localhost:3000/api/health → {database:ok}. curl localhost:8000/health → {status:ok}. curl localhost:8001/.well-known/oauth-authorization-server → issuer confirmed.

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

- `docker-compose.yml` — Restructured with profiles:[full], auth/jaeger/prometheus/grafana services, fixed Kafka dual-listener, Caddy ports 8080/8443
- `Dockerfile` — Python 3.11-slim with infra extras + numpy; ML extras optional via build-arg
- `observability/prometheus.yml` — Prometheus scrape config
- `observability/grafana/datasources/prometheus.yml` — Grafana datasource provisioning
- `observability/grafana/dashboards/dashboard.yml` — Grafana dashboard provider
- `observability/grafana/dashboards/mcp-overview.json` — Starter dashboard: request rate, P99 latency, error rate, auction bid count
