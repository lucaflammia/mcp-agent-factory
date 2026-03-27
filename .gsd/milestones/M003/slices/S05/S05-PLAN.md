# S05: LangChain Bridge + OAuth Middleware

**Goal:** Implement OAuthMiddleware that fetches tokens from the M002 auth server and MCPGatewayClient wrapping the gateway app with the middleware applied, so external clients can authenticate and list/call tools.
**Demo:** After this: pytest tests/test_langchain_bridge.py -v passes — MCPGatewayClient loads gateway tools; OAuth middleware injects valid Bearer token.

## Tasks
- [x] **T01: LangChain bridge: OAuthMiddleware with token caching and MCPGatewayClient — 4 bridge tests pass, full suite 157/157** — 1. Create src/mcp_agent_factory/bridge/__init__.py
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
  - Estimate: 45min
  - Files: src/mcp_agent_factory/bridge/__init__.py, src/mcp_agent_factory/bridge/oauth_middleware.py, src/mcp_agent_factory/bridge/gateway_client.py, tests/test_langchain_bridge.py
  - Verify: python -m pytest tests/test_langchain_bridge.py -v
