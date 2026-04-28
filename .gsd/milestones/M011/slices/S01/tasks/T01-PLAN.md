---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T01: Restructure docker-compose.yml with full profile and add auth/observability services

Add profiles:[full] to gateway, caddy, redis-node-1/2/3, zookeeper, kafka. Add auth service (port 8001). Add jaeger (all-in-one), prometheus, grafana services. Fix Kafka ADVERTISED_LISTENERS to use internal kafka:9092 hostname. Wire JWT_SECRET, AUTH_SERVER_URL, KAFKA_BOOTSTRAP_SERVERS env vars across services.

## Inputs

- `docker-compose.yml`
- `src/mcp_agent_factory/auth/__main__.py`

## Expected Output

- `docker compose --profile full config exits 0`

## Verification

docker compose --profile full config validates without errors
