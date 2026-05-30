# Ship: Live Demo Does Not Work Using README

## PR Details

**Branch:** `gsd/bugfix/the-live-demo-does-not-work-using-readme`
**Base:** `main`

### Title
fix(demo): live demo setup and Kafka integration test fixes

### Body

## Root Cause

The live demo failed for three independent reasons:

1. **Missing `MCP_DEV_MODE=1`** — the gateway requires this env var to bypass OAuth for unauthenticated `tools/call` requests. All README demo commands omitted it, causing every tool call to return a 401-equivalent JSON-RPC error.

2. **Docker Compose v1 incompatibility** — the legacy `docker-compose` v1.29.2 binary crashes with `KeyError: 'ContainerConfig'` against modern Docker Engine, and treats `docker compose` (space-separated) as an unknown flag. Docker Compose v2 (plugin) is required.

3. **Linux Ollama not reachable from containers** — on Linux, Ollama binds to `127.0.0.1` by default, making it unreachable from Docker containers. `OLLAMA_HOST=0.0.0.0` is required.

Two secondary issues were also fixed: the `echo` tool returned an empty string (argument not forwarded), and the Kafka integration test hung indefinitely.

## Changes

- **`README.md`**: Added `MCP_DEV_MODE=1` to all demo commands; documented Docker Compose v2 and Linux Ollama requirements; restructured Quick Start sequencing; de-duplicated Topic Affinity section.
- **`scripts/demo.sh`**: Fixed error message to include the correct startup command.
- **`src/mcp_agent_factory/gateway/service_layer.py`**: Fixed `echo` tool returning empty string.
- **`observability/otel-collector.yml`**: Removed duplicate `status.code` dimension causing Prometheus scrape errors.
- **`src/mcp_agent_factory/streams/kafka_adapter.py`**: Lazy producer start on the caller's event loop (fixes `Future attached to a different loop`).
- **`tests/test_m008_integration.py`**: Replaced indefinite `async for` consumer with bounded `getmany(timeout_ms=2000)`; fixed auth bypass via monkeypatch; fixed event-loop lifecycle.

## Test Coverage

- 14 integration tests pass (Kafka, Redlock, scaling, integration, OTel)
- 391 unit tests pass; 5 pre-existing failures in `test_otel_spans.py` (unrelated to this branch)

## Status
Pending `gh pr create` — awaiting user approval.
