---
estimated_steps: 16
estimated_files: 4
skills_used: []
---

# T01: OAuthMiddleware, MCPGatewayClient, and bridge tests

1. Create src/mcp_agent_factory/bridge/__init__.py
2. Create src/mcp_agent_factory/bridge/oauth_middleware.py:
   - OAuthMiddleware: holds client_id, client_secret, token_url, scope
   - async get_token() -> str: performs client_credentials flow (POST to token_url)
   - async inject(headers: dict) -> dict: returns headers + Authorization: Bearer <token>
   - Caches token until exp - 60s buffer
3. Create src/mcp_agent_factory/bridge/gateway_client.py:
   - MCPGatewayClient: wraps httpx.AsyncClient + OAuthMiddleware
   - async list_tools() -> list[dict]: GET /mcp tools/list via authenticated POST
   - async call_tool(name, arguments) -> dict: POST /mcp tools/call
4. Create tests/test_langchain_bridge.py:
   - Use TestClient for gateway_app and auth_app with shared_key fixture
   - test_oauth_middleware_gets_token: middleware.inject() returns Authorization header
   - test_mcp_gateway_client_list_tools: client.list_tools() returns tools list
   - test_mcp_gateway_client_call_echo: client.call_tool('echo', {'text': 'hi'}) returns 'hi'
   - test_token_cached_between_calls: get_token() called once for two requests

## Inputs

- `src/mcp_agent_factory/gateway/app.py`
- `src/mcp_agent_factory/auth/server.py`
- `src/mcp_agent_factory/auth/resource.py`

## Expected Output

- `src/mcp_agent_factory/bridge/__init__.py`
- `src/mcp_agent_factory/bridge/oauth_middleware.py`
- `src/mcp_agent_factory/bridge/gateway_client.py`
- `tests/test_langchain_bridge.py`

## Verification

python -m pytest tests/test_langchain_bridge.py -v
