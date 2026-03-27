---
estimated_steps: 13
estimated_files: 1
skills_used: []
---

# T02: Security audit document (Fargin Curriculum mapping)

1. Create docs/ directory
2. Write docs/security_audit.md with sections:
   a. Executive Summary: what was built and which course chapter each control comes from
   b. Control 1 — Input Validation (Pydantic v2): module=server.py+server_http.py, function=_call_tool; Fargin Curriculum Cap. 3 schema validation
   c. Control 2 — Privacy-First / Egress Guard: module=config/privacy.py, function=assert_no_egress + PrivacyConfig defaults; Cap. 1 on-device inference
   d. Control 3 — PKCE S256 (RFC 7636): module=auth/server.py, function=_compute_s256 + /authorize + /token; Cap. 5 security patterns
   e. Control 4 — OAuth 2.1 Authorization Server: module=auth/server.py, functions=/register /authorize /token; Cap. 5
   f. Control 5 — Confused Deputy Protection: module=auth/resource.py, function=make_verify_token (aud check); Cap. 5 token passthrough policy
   g. Control 6 — Scope Enforcement: module=auth/resource.py, function=make_verify_token (scope check); Cap. 5 granular scopes
   h. Control 7 — User-Bound Non-Deterministic Session IDs: module=auth/session.py, function=generate_session_id; Cap. 5 session integrity
   i. Control 8 — One-Time Authorization Codes: module=auth/server.py, function=token (del _codes[req.code]); Cap. 5 code replay prevention
   j. Production Gap Notes: in-memory stores (replace with Redis), no key rotation (add JWKS), no HTTPS termination (add reverse proxy)
3. Each section: Requirement ID, Fargin Curriculum reference, Module/Function, What it does, Test proving it

## Inputs

- `src/mcp_agent_factory/auth/server.py`
- `src/mcp_agent_factory/auth/resource.py`
- `src/mcp_agent_factory/auth/session.py`
- `src/mcp_agent_factory/config/privacy.py`
- `src/mcp_agent_factory/server_http.py`

## Expected Output

- `docs/security_audit.md`

## Verification

test -f docs/security_audit.md && wc -l docs/security_audit.md
