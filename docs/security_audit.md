# Security Audit — MCP Agent Factory (M002)

**Date:** 2026-03-27  
**Milestone:** M002 — Autonomous Orchestrator & Production Security  
**Author:** GSD auto-mode  
**Reference:** Fargin Curriculum — Corso Agenti AI & Protocollo MCP

---

## Executive Summary

M002 implements 8 security controls across the MCP orchestration stack, directly derived from the Fargin Curriculum's security and architecture chapters. Every control has a corresponding test that mechanically proves it works. This document maps each control to its implementation module, function, course reference, and test evidence.

**Stack overview:**

```
[Client]
    │
    ├─ GET /authorize?code_challenge=... → auth/server.py:authorize()
    │         [PKCE S256, R010, R011]
    │
    ├─ POST /token {code, code_verifier} → auth/server.py:token()
    │         [JWT issuance, one-time code, R010, R012]
    │
    └─ POST /mcp {jsonrpc payload}  Authorization: Bearer <JWT>
              │
              ├─ auth/resource.py:make_verify_token()  [aud check, scope check, R011, R014]
              │
              └─ server_http_secured.py:mcp_endpoint()
                        │
                        └─ server_http.py:_dispatch()
                                  │
                                  └─ models.py EchoInput/AddInput.model_validate()  [R005]
```

---

## Control 1 — Input Validation (Pydantic v2)

| Field | Value |
|-------|-------|
| Requirement | R005 — Schema Validation for Security |
| Fargin Curriculum | Capitolo 3 — Implementazione del Protocollo MCP in Python (schema validation at dispatch boundary) |
| Module | `src/mcp_agent_factory/server.py`, `src/mcp_agent_factory/server_http.py` |
| Function | `_call_tool()` — calls `EchoInput.model_validate(arguments)` / `AddInput.model_validate(arguments)` |
| What it does | All tool arguments are validated against Pydantic v2 models before execution. Invalid inputs (missing required fields, wrong types) raise `ValidationError`, caught by `_dispatch()`, returned as `isError=True` MCP response. |
| Test evidence | `test_echo_missing_message`, `test_add_missing_field`, `test_add_wrong_type` in `tests/test_schema_validation.py` and `tests/test_server_http.py` |

---

## Control 2 — Privacy-First Egress Guard

| Field | Value |
|-------|-------|
| Requirement | R006 — Privacy-First Design |
| Fargin Curriculum | Capitolo 1 — Architettura Asincrona, on-device inference and data minimization |
| Module | `src/mcp_agent_factory/config/privacy.py` |
| Function | `PrivacyConfig.assert_no_egress()` — raises `RuntimeError` if `allow_egress=True` |
| What it does | `PrivacyConfig` defaults to `local_only=True, allow_egress=False`. Both HTTP servers call `assert_no_egress()` in their FastAPI lifespan startup event, preventing accidental misconfiguration from silently opening outbound connections. |
| Test evidence | `test_assert_no_egress_passes_on_default`, `test_assert_no_egress_raises_when_enabled` in `tests/test_schema_validation.py` |

---

## Control 3 — PKCE S256 (RFC 7636)

| Field | Value |
|-------|-------|
| Requirement | R010 — OAuth 2.1 Authorization Server with PKCE |
| Fargin Curriculum | Capitolo 5 — Integrazioni con Strumenti Esterni, OAuth 2.1 security patterns |
| Module | `src/mcp_agent_factory/auth/server.py` |
| Function | `_compute_s256(verifier)` — `base64url(SHA256(code_verifier))`; enforced in `/authorize` (method must be `S256`) and `/token` (challenge comparison) |
| What it does | Only `code_challenge_method=S256` is accepted. `plain` is explicitly rejected with HTTP 400. During token exchange, `SHA256(code_verifier)` is recomputed and compared to the stored `code_challenge`. Any mismatch → HTTP 400. |
| Test evidence | `test_authorize_rejects_plain_method` (HTTP 400 on plain), `test_token_exchange_wrong_verifier_rejected` (PKCE mismatch → 400) in `tests/test_auth.py` |

---

## Control 4 — OAuth 2.1 Authorization Server

| Field | Value |
|-------|-------|
| Requirement | R010 — OAuth 2.1 Authorization Server with PKCE |
| Fargin Curriculum | Capitolo 5 — token issuance, authorization code flow |
| Module | `src/mcp_agent_factory/auth/server.py` |
| Functions | `register_client()` (POST /register), `authorize()` (GET /authorize), `token()` (POST /token) |
| What it does | Full authorization code + PKCE flow: client registration with scope, code issuance with challenge storage, token exchange with PKCE verification and JWT issuance. Tokens carry `sub`, `aud`, `scope`, `session_id`, `iat`, `exp` claims. |
| Test evidence | `test_register_client`, `test_authorize_returns_code`, `test_token_exchange_returns_access_token`, `test_jwt_contains_correct_claims` in `tests/test_auth.py` |

**Production gaps (document, not defects):**
- In-memory `_clients` and `_codes` dicts → replace with Redis or a database in production
- No JWKS endpoint — static symmetric key → add RS256 + JWKS for multi-service deployments
- No HTTPS termination → add reverse proxy (nginx/caddy) in production

---

## Control 5 — Confused Deputy Protection

| Field | Value |
|-------|-------|
| Requirement | R011 — Confused Deputy Protection |
| Fargin Curriculum | Capitolo 5 — "Strict Token Passthrough policy: Servers must only accept tokens explicitly issued for their scope" |
| Module | `src/mcp_agent_factory/auth/resource.py` |
| Function | `make_verify_token()` — checks `claims['aud'] != 'mcp-server'` → `HTTPException(401)` |
| What it does | Every JWT is validated for audience binding. A token issued for `aud='other-service'` is rejected with HTTP 401 before any resource access occurs, even if the signature is valid. This prevents an attacker from replaying a token stolen from one service against another. |
| Test evidence | `test_confused_deputy_wrong_aud_rejected`: token with `aud='other-service'` → HTTP 401, detail contains "audience" |

---

## Control 6 — Scope Enforcement

| Field | Value |
|-------|-------|
| Requirement | R014 — Resource Server Token Validation |
| Fargin Curriculum | Capitolo 5 — granular OAuth 2.1 scopes |
| Module | `src/mcp_agent_factory/auth/resource.py` |
| Function | `make_verify_token(required_scope)` — checks `required_scope in token_scopes` → `HTTPException(403)` |
| What it does | Each endpoint declares a minimum required scope. A token with `scope='tools:list'` cannot call the `/mcp` endpoint which requires `scope='tools:call'`. Scope shorthand `tools:all` is expanded at issuance to `{tools:call, tools:list}`. |
| Scope definitions | `tools:list` — may call tools/list; `tools:call` — may call tools/call; `tools:all` — expands to both |
| Test evidence | `test_wrong_scope_rejected`: token with `scope='tools:list'` on `/mcp` → HTTP 403 |

---

## Control 7 — User-Bound Non-Deterministic Session IDs

| Field | Value |
|-------|-------|
| Requirement | R012 — User-Bound Non-Deterministic Session IDs |
| Fargin Curriculum | Capitolo 5 — session integrity, non-predictable session identifiers |
| Module | `src/mcp_agent_factory/auth/session.py` |
| Function | `generate_session_id(user_id)` → `f'{user_id}:{secrets.token_urlsafe(32)}'` |
| What it does | Session IDs are user-bound (the user_id is embedded as a prefix, enabling audit trail) and non-deterministic (the token_part is 32 bytes of cryptographic randomness from `secrets.token_urlsafe`). The session_id is embedded in every issued JWT as a claim. |
| Test evidence | `test_session_id_format` (starts with `user1:`), `test_session_ids_are_unique` (10/10 unique), `test_full_stack_pkce_session_id_in_claims` (session_id in JWT, passes `validate_session_id`) |

---

## Control 8 — One-Time Authorization Codes

| Field | Value |
|-------|-------|
| Requirement | R010 — OAuth 2.1 Authorization Server with PKCE |
| Fargin Curriculum | Capitolo 5 — authorization code replay prevention |
| Module | `src/mcp_agent_factory/auth/server.py` |
| Function | `token()` — `del _codes[req.code]` immediately after PKCE verification, before token issuance |
| What it does | Authorization codes are deleted from the in-memory store immediately upon successful PKCE verification. A second exchange attempt with the same code returns HTTP 400 "Invalid or expired authorization code". The deletion occurs before token issuance to prevent TOCTOU races. |
| Test evidence | `test_token_code_one_time_use`: second exchange with same code → HTTP 400 |

---

## Threat Model Coverage Summary

| Threat | Mitigated By | Control |
|--------|-------------|---------|
| Injection / malformed tool args | Pydantic v2 model_validate at dispatch | Control 1 |
| Accidental data egress | PrivacyConfig.assert_no_egress() at startup | Control 2 |
| Authorization code interception | PKCE S256 — verifier never transmitted with code | Control 3 |
| Token theft from another service | Audience binding (aud claim enforcement) | Control 5 |
| Over-privileged token reuse | Scope enforcement per endpoint | Control 6 |
| Session prediction / fixation | Non-deterministic user-bound session IDs | Control 7 |
| Authorization code replay | One-time code deletion before token issuance | Control 8 |

---

## Production Hardening Checklist

Items not implemented in M002 (development milestone) but required for production deployment:

| Item | Priority | Notes |
|------|----------|-------|
| Replace in-memory `_clients`/`_codes` with Redis | P0 | Multi-process and restart safety |
| Add HTTPS termination (nginx/caddy reverse proxy) | P0 | Required for OAuth 2.1 compliance |
| Switch to RS256 + JWKS endpoint | P1 | Enables multi-service token validation without shared secrets |
| Add token revocation endpoint | P1 | Needed for logout / credential rotation |
| Add refresh token flow | P2 | Access token TTL of 3600s acceptable for demo; production needs refresh |
| Rate-limit `/authorize` and `/token` | P1 | Prevent brute-force PKCE verifier guessing |
| Add `kid` (key ID) to JWT header | P1 | Required for JWKS-based key rotation |

---

*This audit document maps to the Fargin Curriculum chapters referenced above. Each control is proven by automated tests in the `tests/` directory — the test names are cited in each section.*
