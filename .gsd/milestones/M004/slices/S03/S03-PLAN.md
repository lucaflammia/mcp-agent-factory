# S03: Client Bridge — PKCE + Token Cache + SSE Consumption

**Goal:** Extend MCPGatewayClient with SSE stream consumption method; extend OAuthMiddleware with token refresh logic; add __main__ entrypoint to bridge; write test_m004_client_bridge.py.
**Demo:** After this: pytest tests/test_m004_client_bridge.py -v shows list_tools, call_tool, token refresh, and SSE stream all passing.

## Tasks
- [x] **T01: MCPGatewayClient extended with stream_events, debug logging, and __main__ entrypoint** — Add stream_events() async method to MCPGatewayClient that opens /sse/v1/events and yields parsed AgentMessage dicts. Add debug logging around list_tools and call_tool. Add __main__ module to bridge package.
  - Estimate: 25m
  - Files: src/mcp_agent_factory/bridge/gateway_client.py, src/mcp_agent_factory/bridge/__main__.py
  - Verify: python -c "from mcp_agent_factory.bridge.gateway_client import MCPGatewayClient; assert hasattr(MCPGatewayClient, 'stream_events')"
- [x] **T02: 18 client bridge tests written and passing (asyncio + trio)** — Write tests/test_m004_client_bridge.py: list_tools via ASGITransport, call_tool echo, token cache (same token returned on second call), token refresh on near-expiry, SSE stream subscription test.
  - Estimate: 25m
  - Files: tests/test_m004_client_bridge.py
  - Verify: pytest tests/test_m004_client_bridge.py -v
