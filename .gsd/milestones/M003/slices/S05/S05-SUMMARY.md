---
id: S05
parent: M003
milestone: M003
provides:
  - src/mcp_agent_factory/bridge/ package with OAuthMiddleware and MCPGatewayClient
  - tests/test_langchain_bridge.py
requires:
  - slice: S04
    provides: gateway_app with auth-protected /mcp endpoint
affects:
  []
key_files:
  - src/mcp_agent_factory/bridge/__init__.py
  - src/mcp_agent_factory/bridge/oauth_middleware.py
  - src/mcp_agent_factory/bridge/gateway_client.py
  - tests/test_langchain_bridge.py
key_decisions:
  - token_factory callable pattern decouples token acquisition from HTTP — clean for tests, extensible for production
  - httpx.ASGITransport enables async ASGI tests without a live server process
patterns_established:
  - token_factory callable for OAuthMiddleware — decouples token source from injection logic
  - httpx.ASGITransport for async ASGI testing without a live server
observability_surfaces:
  - OAuthMiddleware logs token fetch vs cache-hit at DEBUG level
drill_down_paths:
  - milestones/M003/slices/S05/tasks/T01-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-27T11:28:56.254Z
blocker_discovered: false
---

# S05: LangChain Bridge + OAuth Middleware

**LangChain bridge with OAuthMiddleware token caching and MCPGatewayClient — 4 tests pass, full suite 157/157**

## What Happened

Built the LangChain bridge layer: OAuthMiddleware with token caching (60s buffer) and factory-based token acquisition, and MCPGatewayClient wrapping the gateway with httpx.AsyncClient. 4 tests cover token injection, tool listing, echo routing, and cache hit verification. Full 157-test suite confirms no regressions across all M001/M002/M003 components.

## Verification

pytest tests/test_langchain_bridge.py -v → 4 passed; pytest tests/ -v → 157 passed

## Requirements Advanced

- R001 — External clients can authenticate and call gateway tools via MCPGatewayClient

## Requirements Validated

- R001 — pytest tests/test_langchain_bridge.py -v → 4 passed; pytest tests/ → 157 passed

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

OAuthMiddleware uses token_factory callable instead of hitting a client_credentials endpoint — M002 auth server only supports authorization_code grant.

## Known Limitations

OAuthMiddleware does not perform a real OAuth token endpoint call — it requires a token factory. Suitable for testing and single-process deployments; a real client_credentials flow would be needed for multi-service production.

## Follow-ups

If a client_credentials grant is added to the auth server in a future milestone, OAuthMiddleware can be extended with a real token_url flow — the factory pattern keeps the interface backward-compatible.

## Files Created/Modified

- `src/mcp_agent_factory/bridge/__init__.py` — Package marker
- `src/mcp_agent_factory/bridge/oauth_middleware.py` — OAuthMiddleware: token factory, caching, header injection
- `src/mcp_agent_factory/bridge/gateway_client.py` — MCPGatewayClient: list_tools and call_tool over authenticated HTTP
- `tests/test_langchain_bridge.py` — 4 bridge tests covering middleware, tool listing, echo call, and token caching
