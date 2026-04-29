---
id: T01
parent: S01
milestone: M011
key_files:
  - docker-compose.yml
  - Dockerfile
key_decisions:
  - (none)
duration: 
verification_result: passed
completed_at: 2026-04-28T16:03:25.901Z
blocker_discovered: false
---

# T01: Restructured docker-compose.yml with full profile, auth service, fixed Kafka listeners, added Jaeger/Prometheus/Grafana

**Restructured docker-compose.yml with full profile, auth service, fixed Kafka listeners, added Jaeger/Prometheus/Grafana**

## What Happened

Added profiles:[full] to all non-Redis services. Added auth service with REDIS_URL and JWT_SECRET. Fixed Kafka ADVERTISED_LISTENERS to use dual-listener pattern (internal kafka:29092, external localhost:9092). Added jaeger all-in-one, prometheus, and grafana services. Remapped Caddy ports to 8080/8443 to avoid host port 80 conflict. Created Dockerfile for gateway/auth images.

## Verification

docker compose --profile full config exits 0 with no errors

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `docker compose --profile full config` | 0 | pass | 500ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `docker-compose.yml`
- `Dockerfile`
