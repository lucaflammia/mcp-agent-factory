# Fix: Live Demo Does Not Work Using README

## Changes Made

### 1. `README.md` — Live Demo and Quick Start sections
- Prefixed all `docker compose --profile full up -d` invocations with `MCP_DEV_MODE=1`
- Added Docker Compose v2 prerequisite note
- Documented Linux Ollama requirement: `OLLAMA_HOST=0.0.0.0` must be set so containers can reach the host daemon
- Restructured Quick Start for correct sequencing (gateway must be running before `echo` tool call)
- Fixed `echo` tool example — was returning empty string due to missing argument forwarding
- De-duplicated Topic Affinity section (was explained twice); consolidated into one section at the bottom with both the gateway variant and direct-Python variant
- Added `MCP_DEV_MODE=1` to the gateway variant startup command, and a `redis-cli` caveat (only applies when `REDIS_URL` is set, not with fakeredis)

### 2. `scripts/demo.sh` — error message
- Fixed gateway-not-ready error message to include `MCP_DEV_MODE=1 docker compose --profile full up -d`

### 3. `src/mcp_agent_factory/gateway/service_layer.py` — echo tool
- Fixed `echo` returning empty string: argument was not being forwarded to the response

### 4. `observability/` — spanmetrics
- Removed duplicate `status.code` dimension that caused Prometheus scrape errors

### 5. `tests/test_m008_integration.py` and `src/mcp_agent_factory/streams/kafka_adapter.py` — Kafka integration test
- Fixed indefinite hang: replaced `async for msg in consumer` with bounded `getmany(timeout_ms=2000)`
- Fixed event-loop mismatch: producer now starts lazily on the anyio loop used by `TestClient`
- Fixed auth bypass for the test: `monkeypatch.setattr(_app, "DEV_MODE", True)`

## Commits on Branch
- `0603da0` fix(docs): add MCP_DEV_MODE=1 to live demo commands and document Docker Compose v2 requirement
- `720635a` fix(observability): remove duplicate status.code dimension from spanmetrics
- `169c8f9` fix(docs): document Linux Ollama OLLAMA_HOST requirement for live demo
- `6a581a9` fix(quickstart): echo returns empty string + restructure Quick Start for correct sequencing
- `932d8e4` fix Kafka Integration
- `3c4e635` chore(gsd): update codebase map and snapshot
