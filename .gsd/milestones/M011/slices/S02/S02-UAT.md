# S02: OpenTelemetry instrumentation — UAT

**Milestone:** M011
**Written:** 2026-04-29T04:51:28.446Z

## UAT — S02: OpenTelemetry instrumentation

### Prerequisites
- `docker compose --profile full up -d` — all 12 services healthy
- `MCP_DEV_MODE=1` set (or gateway configured with valid JWT)

### Test 1: mcp-gateway appears in Jaeger service list
```
curl http://localhost:16686/api/services | python -m json.tool
```
Expected: `"data"` array contains `"mcp-gateway"`

### Test 2: Echo tool produces mcp.tools/call span in Jaeger
```
curl -s -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"echo","arguments":{"text":"hello"}}}'
```
Then open http://localhost:16686 → Search → Service: mcp-gateway → Find Traces.
Expected: trace with `mcp.tools/call` span, tag `mcp.tool=echo`.

### Test 3: Integration test suite passes
```
pytest tests/test_m011_otel_integration.py -m integration -v
```
Expected: 3 passed.

### Test 4: Unit tests pass without Docker
```
pytest tests/test_otel_spans.py -v
```
Expected: 6 passed.

