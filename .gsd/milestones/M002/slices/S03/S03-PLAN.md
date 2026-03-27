# S03: OAuth 2.1 Auth Server + Resource Server

**Goal:** Implement the full OAuth 2.1 Authorization Server (PKCE, scopes, client registration) and Resource Server middleware (audience-bound token validation, scope enforcement, session IDs). Two separate FastAPI apps with clean boundary.
**Demo:** After this: pytest tests/test_auth.py -v passes — full PKCE flow, scope gating, and confused deputy protection proven.

## Tasks
- [x] **T01: OAuth 2.1 Auth Server with PKCE S256, client registration, one-time codes, and JWT issuance with audience binding and user-bound session IDs.** — 1. Create src/mcp_agent_factory/auth/__init__.py (empty)
2. Create src/mcp_agent_factory/auth/session.py:
   - generate_session_id(user_id: str) -> str: returns f'{user_id}:{secrets.token_urlsafe(32)}'
   - parse_session_id(session_id: str) -> tuple[str, str]: splits on first ':' returns (user_id, token_part)
   - validate_session_id(session_id: str) -> bool: checks format user_id:token (both non-empty)
3. Create src/mcp_agent_factory/auth/server.py:
   - Use authlib.jose OctKey + jwt for token signing (generate shared key at startup, store in app.state)
   - In-memory stores: clients dict, codes dict (code_challenge + user_id + scope + client_id)
   - POST /register: accepts {client_id, client_secret, redirect_uri, scope} returns {client_id, registered: true}
   - GET /authorize: params code_challenge, code_challenge_method (must be 'S256'), client_id, scope, user_id (simulated, no real login); generates auth code, stores {code_challenge, user_id, scope, client_id}; returns {code: <auth_code>}
   - POST /token: form body {code, code_verifier, client_id, client_secret, grant_type='authorization_code'}; verifies S256(code_verifier)==code_challenge; issues JWT {sub: user_id, aud: 'mcp-server', scope: granted_scope, iat, exp: now+3600, session_id: generate_session_id(user_id)}; returns {access_token, token_type: 'bearer', expires_in: 3600}
   - Reject plain method: if code_challenge_method != 'S256' return 400
   - One-time codes: delete code after successful exchange
4. Scope definitions: 'tools:list', 'tools:call', 'tools:all' (shorthand for both)
5. Observability: log issuance events at INFO (client_id, scope, aud — never token value)
  - Estimate: 35min
  - Files: src/mcp_agent_factory/auth/__init__.py, src/mcp_agent_factory/auth/session.py, src/mcp_agent_factory/auth/server.py
  - Verify: python -c "from mcp_agent_factory.auth.server import app as auth_app; from mcp_agent_factory.auth.session import generate_session_id; print('auth imports ok')"
- [x] **T02: Resource Server middleware with audience binding (confused deputy protection) and scope enforcement, plus secured FastAPI MCP server variant.** — 1. Create src/mcp_agent_factory/auth/resource.py:
   - JWT_KEY: OctKey — must be the same key used by auth server. For tests, use a shared fixture key. For module-level default, generate once.
   - get_jwt_key() -> OctKey: returns the shared key (settable for tests)
   - set_jwt_key(key: OctKey) -> None: allows tests to inject the auth server's key
   - async verify_token(required_scope: str, authorization: str = Header(None)) -> dict:
     - extracts Bearer token from Authorization header
     - decodes JWT with authlib.jose jwt.decode(token, key)
     - checks aud claim == 'mcp-server' — if wrong: raise HTTPException(401, 'invalid audience')
     - checks required_scope in scope claim — if missing: raise HTTPException(403, 'insufficient scope')
     - returns decoded claims dict
   - Confused deputy: if token was issued for a different audience, reject it
2. Create src/mcp_agent_factory/server_http_secured.py:
   - Same as server_http.py but POST /mcp requires Authorization header
   - Add FastAPI Depends(verify_token('tools:call')) to the /mcp endpoint
   - Import verify_token from auth.resource
   - /health endpoint remains unauthenticated
3. Keep server_http.py unchanged (unauthenticated server stays for M001 regression)
  - Estimate: 20min
  - Files: src/mcp_agent_factory/auth/resource.py, src/mcp_agent_factory/server_http_secured.py
  - Verify: python -c "from mcp_agent_factory.auth.resource import verify_token, set_jwt_key; print('resource imports ok')"
- [x] **T03: 20 auth tests — PKCE flow, confused deputy protection, scope enforcement, session IDs — all passing in 3.04s.** — 1. Create tests/test_auth.py
2. Fixtures:
   - auth_client: TestClient(auth_app) — register a test client in setup
   - secured_mcp_client: TestClient(secured_app) with jwt key injected
   - pkce_pair(): helper returning (code_verifier, code_challenge) using S256
3. Test cases — Auth Server:
   - test_register_client: POST /register returns {registered: true}
   - test_authorize_returns_code: GET /authorize with valid params returns {code: ...}
   - test_authorize_rejects_plain_method: code_challenge_method=plain returns 400
   - test_token_exchange_returns_access_token: full PKCE flow returns {access_token, token_type='bearer'}
   - test_token_exchange_wrong_verifier_rejected: bad code_verifier returns 400
   - test_token_code_one_time_use: second exchange with same code returns 400
   - test_jwt_contains_correct_claims: decoded token has sub, aud='mcp-server', scope, session_id
4. Test cases — Resource Server:
   - test_protected_endpoint_no_token_returns_401: POST /mcp without auth returns 401
   - test_protected_endpoint_valid_token_accepted: valid token returns 200
   - test_confused_deputy_wrong_aud_rejected: token with aud='other-service' returns 401
   - test_wrong_scope_rejected: token with scope='tools:list' (not tools:call) on /mcp returns 403
5. Test cases — Session:
   - test_session_id_format: generate_session_id('user1') returns 'user1:<token>'
   - test_session_id_validates: validate_session_id passes for valid, fails for malformed
   - test_session_ids_are_unique: two calls produce different session_ids
  - Estimate: 30min
  - Files: tests/test_auth.py
  - Verify: python -m pytest tests/test_auth.py -v
