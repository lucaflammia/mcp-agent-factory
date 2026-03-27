---
id: T02
parent: S03
milestone: M002
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/auth/resource.py", "src/mcp_agent_factory/server_http_secured.py"]
key_decisions: ["make_verify_token factory pattern allows per-endpoint scope requirements without hardcoding", "Confused deputy check: aud != 'mcp-server' → HTTP 401 (not 403 — it's an identity/audience problem, not an authorization problem)", "Scope check: required_scope not in token_scopes → HTTP 403"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "python -c imports ok. Tests pass in T03."
completed_at: 2026-03-27T08:09:07.267Z
blocker_discovered: false
---

# T02: Resource Server middleware with audience binding (confused deputy protection) and scope enforcement, plus secured FastAPI MCP server variant.

> Resource Server middleware with audience binding (confused deputy protection) and scope enforcement, plus secured FastAPI MCP server variant.

## What Happened
---
id: T02
parent: S03
milestone: M002
key_files:
  - src/mcp_agent_factory/auth/resource.py
  - src/mcp_agent_factory/server_http_secured.py
key_decisions:
  - make_verify_token factory pattern allows per-endpoint scope requirements without hardcoding
  - Confused deputy check: aud != 'mcp-server' → HTTP 401 (not 403 — it's an identity/audience problem, not an authorization problem)
  - Scope check: required_scope not in token_scopes → HTTP 403
duration: ""
verification_result: passed
completed_at: 2026-03-27T08:09:07.275Z
blocker_discovered: false
---

# T02: Resource Server middleware with audience binding (confused deputy protection) and scope enforcement, plus secured FastAPI MCP server variant.

**Resource Server middleware with audience binding (confused deputy protection) and scope enforcement, plus secured FastAPI MCP server variant.**

## What Happened

Created resource.py with make_verify_token factory and set_jwt_key/get_jwt_key for test key injection. Confused deputy protection rejects tokens with wrong aud claim with HTTP 401. Scope enforcement returns HTTP 403. Created server_http_secured.py that wraps the existing MCP endpoint with Depends(make_verify_token('tools:call')) while keeping /health unauthenticated.

## Verification

python -c imports ok. Tests pass in T03.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -c "from mcp_agent_factory.auth.resource import make_verify_token, set_jwt_key; print('ok')"` | 0 | ✅ pass | 250ms |


## Deviations

Implemented make_verify_token(required_scope) factory pattern instead of a single verify_token — cleaner for per-endpoint scope requirements. server_http_secured.py imports and reuses _dispatch and lifespan from server_http.py to avoid duplication.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/auth/resource.py`
- `src/mcp_agent_factory/server_http_secured.py`


## Deviations
Implemented make_verify_token(required_scope) factory pattern instead of a single verify_token — cleaner for per-endpoint scope requirements. server_http_secured.py imports and reuses _dispatch and lifespan from server_http.py to avoid duplication.

## Known Issues
None.
