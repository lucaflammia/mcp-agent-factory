---
estimated_steps: 22
estimated_files: 1
skills_used: []
---

# T03: Tests for Auth Server, Resource Server, and session module

1. Create tests/test_auth.py
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

## Inputs

- `src/mcp_agent_factory/auth/server.py`
- `src/mcp_agent_factory/auth/resource.py`
- `src/mcp_agent_factory/auth/session.py`
- `src/mcp_agent_factory/server_http_secured.py`

## Expected Output

- `tests/test_auth.py`

## Verification

python -m pytest tests/test_auth.py -v
