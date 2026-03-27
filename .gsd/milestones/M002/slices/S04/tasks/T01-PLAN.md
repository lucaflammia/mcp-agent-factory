---
estimated_steps: 15
estimated_files: 1
skills_used: []
---

# T01: Integration test: TaskScheduler + HTTP MCP + Auth

1. Create tests/test_integration.py
2. Test: TaskScheduler dispatches a task that calls the HTTP MCP server (unauthenticated path) via httpx inside the handler
   - Start TestClient(app) for server_http
   - Build a handler that does httpx.post (sync TestClient call) with tools/call echo
   - Push a TaskItem into scheduler inbox
   - Drive via _dispatch directly (no asyncio.wait_for)
   - Assert task.state == COMPLETED and result text == input
3. Test: TaskScheduler dispatches through the secured server with a valid token
   - Setup: shared OctKey, register client, full PKCE flow to get token
   - Handler calls secured_app endpoint with Authorization header
   - Assert task.state == COMPLETED
4. Test: full stack — scheduler + auth + MCP in one flow
   - generate_session_id called during token issuance
   - Assert session_id in decoded JWT claims
5. Run full test suite at end: pytest tests/ and assert 0 failures

## Inputs

- `src/mcp_agent_factory/scheduler.py`
- `src/mcp_agent_factory/server_http.py`
- `src/mcp_agent_factory/server_http_secured.py`
- `src/mcp_agent_factory/auth/server.py`
- `src/mcp_agent_factory/auth/resource.py`

## Expected Output

- `tests/test_integration.py`

## Verification

python -m pytest tests/test_integration.py -v
