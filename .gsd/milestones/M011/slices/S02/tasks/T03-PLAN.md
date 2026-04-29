---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T03: Live stack verification — Jaeger trace confirmation

With docker compose --profile full up running (MCP_DEV_MODE=1), run the integration tests and manually confirm: mcp-gateway appears in Jaeger services list, a mcp.tools/call span exists with mcp.tool=echo, and a tool.echo child span exists under it.

## Inputs

- `tests/test_m011_otel_integration.py`
- `docker-compose.yml`

## Expected Output

- `mcp-gateway visible in Jaeger UI`
- `mcp.tools/call span with mcp.tool attribute present`
- `Integration tests pass`

## Verification

pytest tests/test_m011_otel_integration.py -m integration -v exits 0
