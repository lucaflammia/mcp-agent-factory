---
estimated_steps: 17
estimated_files: 2
skills_used: []
---

# T02: Resource Server middleware and secured HTTP MCP server

1. Create src/mcp_agent_factory/auth/resource.py:
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

## Inputs

- `src/mcp_agent_factory/auth/server.py`
- `src/mcp_agent_factory/server_http.py`

## Expected Output

- `src/mcp_agent_factory/auth/resource.py`
- `src/mcp_agent_factory/server_http_secured.py`

## Verification

python -c "from mcp_agent_factory.auth.resource import verify_token, set_jwt_key; print('resource imports ok')"
