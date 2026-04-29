# S01: Full-stack Compose profile — UAT

**Milestone:** M011
**Written:** 2026-04-28T16:03:56.215Z

# S01 UAT — Full-stack Compose Profile

## Prerequisites
- Docker + Docker Compose v2
- Ports 8000, 8001, 3000, 9090, 16686, 6379 free on host

## Steps

1. `docker compose --profile full build`
2. `docker compose --profile full up -d`
3. Wait ~90s for Kafka and gateway health checks

## Assertions

- [ ] `docker compose --profile full ps` — all 12 services `(healthy)`
- [ ] `curl http://localhost:8000/health` → `{"status":"ok","service":"mcp-gateway"}`
- [ ] `curl http://localhost:8001/.well-known/oauth-authorization-server` → JSON with `issuer`
- [ ] `curl -sf http://localhost:16686/` → exit 0 (Jaeger UI)
- [ ] `curl http://localhost:9090/-/healthy` → `Prometheus Server is Healthy.`
- [ ] `curl http://localhost:3000/api/health` → `{"database":"ok"}`

## Teardown
`docker compose --profile full down`
