---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Add SSE v1 router to gateway

Create messaging/sse_v1_router.py with GET /events and POST /messages endpoints. /events emits a 'connected' SSE event immediately on connect then streams bus messages. /messages accepts a JSON body and publishes to the bus. Mount at /sse/v1 on gateway_app.

## Inputs

- `src/mcp_agent_factory/messaging/sse_router.py`
- `src/mcp_agent_factory/gateway/app.py`

## Expected Output

- `src/mcp_agent_factory/messaging/sse_v1_router.py`

## Verification

python -c "from mcp_agent_factory.gateway.app import gateway_app; routes = [str(getattr(r,'path','')) for r in gateway_app.routes]; assert any('/sse/v1' in r for r in routes), routes"
