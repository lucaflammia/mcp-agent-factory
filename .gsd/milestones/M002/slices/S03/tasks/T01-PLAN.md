---
estimated_steps: 15
estimated_files: 3
skills_used: []
---

# T01: OAuth 2.1 Auth Server with PKCE and session module

1. Create src/mcp_agent_factory/auth/__init__.py (empty)
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

## Inputs

- `src/mcp_agent_factory/server_http.py`

## Expected Output

- `src/mcp_agent_factory/auth/__init__.py`
- `src/mcp_agent_factory/auth/session.py`
- `src/mcp_agent_factory/auth/server.py`

## Verification

python -c "from mcp_agent_factory.auth.server import app as auth_app; from mcp_agent_factory.auth.session import generate_session_id; print('auth imports ok')"
