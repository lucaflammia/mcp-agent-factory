# S04: Security Audit & Integration Wiring

**Goal:** Write docs/security_audit.md mapping every implemented security control to Fargin Curriculum benchmarks, wire TaskScheduler → HTTP MCP server end-to-end, and run the full test suite to confirm M001 + M002 tests all pass together.
**Demo:** After this: pytest tests/ -v passes in full — M001 + M002 tests all green; docs/security_audit.md written and cross-referenced to Fargin Curriculum.

## Tasks
- [x] **T01: 3 integration tests proving TaskScheduler → HTTP MCP server → auth layer end-to-end — all passing.** — 1. Create tests/test_integration.py
2. Test: TaskScheduler dispatches a task that calls the HTTP MCP server (unauthenticated path) via httpx inside the handler
   - Start TestClient(app) for server_http
   - Build a handler that does httpx.post (sync TestClient call) with tools/call echo
   - Push a TaskItem into scheduler inbox
   - Drive via _dispatch directly (no asyncio.wait_for)
   - Assert task.state == COMPLETED and result text == input
3. Test: TaskScheduler dispatches through the secured server with a valid token
   - Setup: shared OctKey, register client, full PKCE flow to get token
   - Handler calls secured_app endpoint with Authorization header
   - Assert task.state == COMPLETED
4. Test: full stack — scheduler + auth + MCP in one flow
   - generate_session_id called during token issuance
   - Assert session_id in decoded JWT claims
5. Run full test suite at end: pytest tests/ and assert 0 failures
  - Estimate: 20min
  - Files: tests/test_integration.py
  - Verify: python -m pytest tests/test_integration.py -v
- [x] **T02: docs/security_audit.md: 8 security controls mapped to Fargin Curriculum chapters with module/function references and test citations.** — 1. Create docs/ directory
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
  - Estimate: 15min
  - Files: docs/security_audit.md
  - Verify: test -f docs/security_audit.md && wc -l docs/security_audit.md
- [x] **T03: 100/100 tests pass — M001 31 + M002 69 — zero regressions.** — 1. Run python -m pytest tests/ -v and capture output
2. Confirm all tests pass (target: M001 31 + M002 scheduler 12 + HTTP server 11 + adapters 23 + auth 20 + integration 3 = ~100 tests)
3. If any failures: fix them
4. Update pyproject.toml if any new dev dependencies were needed (none expected for M002)
  - Estimate: 10min
  - Verify: python -m pytest tests/ -v
