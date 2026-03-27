---
id: T01
parent: S05
milestone: M003
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/bridge/__init__.py", "src/mcp_agent_factory/bridge/oauth_middleware.py", "src/mcp_agent_factory/bridge/gateway_client.py", "tests/test_langchain_bridge.py"]
key_decisions: ["OAuthMiddleware accepts a token_factory callable rather than a token_url, because auth server has no client_credentials endpoint", "httpx.ASGITransport used for async ASGI testing without a live server"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "pytest tests/test_langchain_bridge.py -v → 4 passed; pytest tests/ -v → 157 passed"
completed_at: 2026-03-27T11:28:34.187Z
blocker_discovered: false
---

# T01: LangChain bridge: OAuthMiddleware with token caching and MCPGatewayClient — 4 bridge tests pass, full suite 157/157

> LangChain bridge: OAuthMiddleware with token caching and MCPGatewayClient — 4 bridge tests pass, full suite 157/157

## What Happened
---
id: T01
parent: S05
milestone: M003
key_files:
  - src/mcp_agent_factory/bridge/__init__.py
  - src/mcp_agent_factory/bridge/oauth_middleware.py
  - src/mcp_agent_factory/bridge/gateway_client.py
  - tests/test_langchain_bridge.py
key_decisions:
  - OAuthMiddleware accepts a token_factory callable rather than a token_url, because auth server has no client_credentials endpoint
  - httpx.ASGITransport used for async ASGI testing without a live server
duration: ""
verification_result: passed
completed_at: 2026-03-27T11:28:34.252Z
blocker_discovered: false
---

# T01: LangChain bridge: OAuthMiddleware with token caching and MCPGatewayClient — 4 bridge tests pass, full suite 157/157

**LangChain bridge: OAuthMiddleware with token caching and MCPGatewayClient — 4 bridge tests pass, full suite 157/157**

## What Happened

Implemented OAuthMiddleware (token caching, factory pattern), MCPGatewayClient (httpx.AsyncClient + ASGI transport injection), and 4 bridge tests. Full 157-test suite passes.

## Verification

pytest tests/test_langchain_bridge.py -v → 4 passed; pytest tests/ -v → 157 passed

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest tests/test_langchain_bridge.py -v` | 0 | ✅ pass | 2760ms |
| 2 | `python -m pytest tests/ -v` | 0 | ✅ pass | 38670ms |


## Deviations

OAuthMiddleware uses token_factory callable instead of client_credentials token endpoint — M002 auth server only supports authorization_code grant.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/bridge/__init__.py`
- `src/mcp_agent_factory/bridge/oauth_middleware.py`
- `src/mcp_agent_factory/bridge/gateway_client.py`
- `tests/test_langchain_bridge.py`


## Deviations
OAuthMiddleware uses token_factory callable instead of client_credentials token endpoint — M002 auth server only supports authorization_code grant.

## Known Issues
None.
