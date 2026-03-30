---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T02: Write tests/test_m004_sse.py

Test: connected event received on GET /sse/v1/events; POST /sse/v1/messages publishes to bus; tool call via /mcp with auth emits gateway.tool_calls event visible on /sse/v1/events. Use httpx AsyncClient with ASGITransport and anyio for async.

## Inputs

- `src/mcp_agent_factory/messaging/sse_v1_router.py`
- `src/mcp_agent_factory/gateway/app.py`

## Expected Output

- `tests/test_m004_sse.py`

## Verification

pytest tests/test_m004_sse.py -v
