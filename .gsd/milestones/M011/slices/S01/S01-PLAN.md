# S01: Full-stack Compose profile

**Goal:** Wire all services into a docker compose --profile full stack that passes health checks: gateway, auth, Redis, Kafka, Jaeger, Prometheus, Grafana, and Caddy.
**Demo:** docker compose --profile full up; docker compose ps shows all services healthy

## Must-Haves

- docker compose --profile full up -d && docker compose --profile full ps shows all services healthy (no Exit/unhealthy); Jaeger UI reachable at localhost:16686, Grafana at localhost:3000, Prometheus at localhost:9090.

## Proof Level

- This slice proves: Not provided.

## Integration Closure

Not provided.

## Verification

- Not provided.

## Tasks

- [ ] **T01: Restructure docker-compose.yml with full profile and add auth/observability services** `est:30m`
  Add profiles:[full] to gateway, caddy, redis-node-1/2/3, zookeeper, kafka. Add auth service (port 8001). Add jaeger (all-in-one), prometheus, grafana services. Fix Kafka ADVERTISED_LISTENERS to use internal kafka:9092 hostname. Wire JWT_SECRET, AUTH_SERVER_URL, KAFKA_BOOTSTRAP_SERVERS env vars across services.
  - Files: `docker-compose.yml`
  - Verify: docker compose --profile full config validates without errors

- [ ] **T02: Create Prometheus scrape config and Grafana provisioning** `est:20m`
  Create observability/prometheus.yml with a scrape job for gateway:8000/metrics. Create observability/grafana/datasources/prometheus.yml pointing at prometheus:9090. Create observability/grafana/dashboards/dashboard.yml provisioning config. Create a minimal starter dashboard JSON.
  - Files: `observability/prometheus.yml`, `observability/grafana/datasources/prometheus.yml`, `observability/grafana/dashboards/dashboard.yml`, `observability/grafana/dashboards/mcp-overview.json`
  - Verify: All files exist and are valid YAML/JSON

- [ ] **T03: Start full stack and verify all services reach healthy state** `est:15m`
  Run docker compose --profile full up -d, wait for health checks to pass, then confirm all services show healthy in docker compose ps. Check Jaeger UI (16686), Prometheus (9090), and Grafana (3000) are reachable.
  - Verify: docker compose --profile full ps | grep -v healthy returns only header; curl localhost:16686 returns 200

## Files Likely Touched

- docker-compose.yml
- observability/prometheus.yml
- observability/grafana/datasources/prometheus.yml
- observability/grafana/dashboards/dashboard.yml
- observability/grafana/dashboards/mcp-overview.json
