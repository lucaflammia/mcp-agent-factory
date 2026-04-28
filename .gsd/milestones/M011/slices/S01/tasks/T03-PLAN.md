---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T03: Start full stack and verify all services reach healthy state

Run docker compose --profile full up -d, wait for health checks to pass, then confirm all services show healthy in docker compose ps. Check Jaeger UI (16686), Prometheus (9090), and Grafana (3000) are reachable.

## Inputs

- `docker-compose.yml`
- `observability/`

## Expected Output

- `All services Up (healthy)`
- `HTTP 200 from Jaeger, Prometheus, Grafana`

## Verification

docker compose --profile full ps | grep -v healthy returns only header; curl localhost:16686 returns 200
