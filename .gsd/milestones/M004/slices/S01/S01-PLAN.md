# S01: SSE /v1 Endpoints + Connected Event

**Goal:** Add /sse/v1/messages (POST) and /sse/v1/events (GET) to the gateway, with a 'connected' SSE event on subscription and tool-call log events.
**Demo:** After this: curl -N http://localhost:8000/sse/v1/events?topic=agent.events stays open and receives event: connected followed by tool call events when /mcp is invoked.

## Tasks
- [x] **T01: Added /sse/v1/events and /sse/v1/messages endpoints with connected event and bus integration** — Create messaging/sse_v1_router.py with GET /events and POST /messages endpoints. /events emits a 'connected' SSE event immediately on connect then streams bus messages. /messages accepts a JSON body and publishes to the bus. Mount at /sse/v1 on gateway_app.
  - Estimate: 30m
  - Files: src/mcp_agent_factory/messaging/sse_v1_router.py, src/mcp_agent_factory/gateway/app.py
  - Verify: python -c "from mcp_agent_factory.gateway.app import gateway_app; routes = [str(getattr(r,'path','')) for r in gateway_app.routes]; assert any('/sse/v1' in r for r in routes), routes"
- [x] **T02: 9 SSE tests written and passing** — Test: connected event received on GET /sse/v1/events; POST /sse/v1/messages publishes to bus; tool call via /mcp with auth emits gateway.tool_calls event visible on /sse/v1/events. Use httpx AsyncClient with ASGITransport and anyio for async.
  - Estimate: 30m
  - Files: tests/test_m004_sse.py
  - Verify: pytest tests/test_m004_sse.py -v
