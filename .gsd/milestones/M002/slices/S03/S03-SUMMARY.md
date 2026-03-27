---
id: S03
parent: M002
milestone: M002
provides:
  - auth/server.py: OAuth 2.1 Auth Server — /register, /authorize (PKCE S256), /token (code exchange)
  - auth/resource.py: make_verify_token dependency, set_jwt_key for test injection
  - auth/session.py: generate_session_id, parse_session_id, validate_session_id
  - server_http_secured.py: auth-protected MCP server variant
requires:
  - slice: S02
    provides: FastAPI TestClient pattern, MCPRequest/MCPResponse models, _dispatch and lifespan for reuse in secured server
affects:
  - S04
key_files:
  - src/mcp_agent_factory/auth/server.py
  - src/mcp_agent_factory/auth/resource.py
  - src/mcp_agent_factory/auth/session.py
  - src/mcp_agent_factory/server_http_secured.py
  - tests/test_auth.py
key_decisions:
  - make_verify_token factory for per-endpoint scope requirements
  - Confused deputy: aud mismatch → HTTP 401 (not 403)
  - autouse shared_key fixture for per-test key injection and store cleanup
  - One-time codes deleted before token issuance to prevent TOCTOU
patterns_established:
  - autouse shared_key fixture with per-test store cleanup for auth integration tests
  - make_verify_token factory pattern for FastAPI dependency injection with per-endpoint scopes
  - _make_token helper for crafting test tokens with arbitrary claims
observability_surfaces:
  - Token issuance logged at INFO: event=token_issued, client_id, scope, aud, session_id (never token value)
  - Token validation logged at INFO: event=token_accepted, sub, scope, session_id
  - Rejection events logged at WARNING: confused_deputy_rejected (expected/got aud), scope_rejected (required/granted)
drill_down_paths:
  - .gsd/milestones/M002/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S03/tasks/T02-SUMMARY.md
  - .gsd/milestones/M002/slices/S03/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-27T08:09:42.295Z
blocker_discovered: false
---

# S03: OAuth 2.1 Auth Server + Resource Server

**Full OAuth 2.1 Auth Server (PKCE S256, one-time codes, JWT) + Resource Server middleware (confused deputy, scope enforcement) — proven by 20 passing tests.**

## What Happened

S03 delivered the full OAuth 2.1 security stack in three tasks. T01 built the Auth Server (PKCE S256, one-time codes, JWT issuance with aud+session_id) and session module. T02 built the Resource Server middleware (confused deputy protection, scope enforcement) and the secured MCP server variant. T03 wrote 20 tests with a clean per-test key injection pattern. All 20 pass in 3.04s with full test isolation via the autouse shared_key fixture.

## Verification

python -m pytest tests/test_auth.py -v → 20 passed in 3.04s.

## Requirements Advanced

- R010 — Full OAuth 2.1 Auth Server implemented with PKCE, scopes, client registration
- R011 — Audience binding enforced in Resource Server: wrong aud → HTTP 401
- R012 — generate_session_id produces user_id:token_urlsafe(32) format, validated in all token claims
- R014 — Resource Server validates bearer tokens, enforces scopes, audience binding

## Requirements Validated

- R010 — test_token_exchange_returns_access_token, test_jwt_contains_correct_claims, test_authorize_rejects_plain_method — full PKCE flow proven
- R011 — test_confused_deputy_wrong_aud_rejected: aud='other-service' → HTTP 401
- R012 — test_session_id_format, test_session_ids_are_unique: user_id:token format, 10/10 unique
- R014 — test_protected_endpoint_no_token_returns_401, test_protected_endpoint_valid_token_accepted, test_wrong_scope_rejected

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

make_verify_token factory pattern used instead of a single verify_token — cleaner for per-endpoint scope requirements.

## Known Limitations

In-memory stores (clients, codes) — replace with Redis in production. JWT key generated fresh per process; no key rotation or JWKS endpoint.

## Follow-ups

In-memory _clients and _codes stores should be replaced with Redis in production — flagged in security_audit.md.

## Files Created/Modified

- `src/mcp_agent_factory/auth/server.py` — OAuth 2.1 Auth Server: PKCE S256, client registration, one-time codes, JWT issuance
- `src/mcp_agent_factory/auth/resource.py` — Resource Server middleware: audience binding, scope enforcement, set_jwt_key for tests
- `src/mcp_agent_factory/auth/session.py` — Session ID generation: user_id:token format, validation helpers
- `src/mcp_agent_factory/auth/__init__.py` — Empty package marker
- `src/mcp_agent_factory/server_http_secured.py` — Secured FastAPI MCP server: /mcp requires tools:call scope, /health unauthenticated
- `tests/test_auth.py` — 20 auth tests: PKCE flow, confused deputy, scope enforcement, session IDs
