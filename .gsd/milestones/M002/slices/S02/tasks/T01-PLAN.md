---
estimated_steps: 12
estimated_files: 1
skills_used: []
---

# T01: FastAPI HTTP MCP server

1. Create src/mcp_agent_factory/server_http.py
2. Define MCPRequest Pydantic model: jsonrpc (str='2.0'), method (str), params (dict|None=None), id (int|str|None=None)
3. Define MCPResponse Pydantic model: jsonrpc (str='2.0'), id (int|str|None), result (Any|None=None), error (dict|None=None)
4. Create FastAPI app with POST /mcp endpoint:
   - Accepts MCPRequest body
   - Delegates to _dispatch(request) — same dispatch logic as STDIO server but async
   - Returns MCPResponse
   - PrivacyConfig.assert_no_egress() called at startup (lifespan event)
5. _dispatch handles: initialize, initialized (204 no-content), tools/list, tools/call (uses EchoInput/AddInput model_validate, catches ValueError+ValidationError)
6. Observability: log each request/response as JSON line to stderr via logger.debug
7. Add GET /health endpoint returning {status: ok}
8. Do NOT modify server.py (M001 baseline)

## Inputs

- `src/mcp_agent_factory/server.py`
- `src/mcp_agent_factory/models.py`
- `src/mcp_agent_factory/config/privacy.py`

## Expected Output

- `src/mcp_agent_factory/server_http.py`

## Verification

python -c "from mcp_agent_factory.server_http import app; print('import ok')"
