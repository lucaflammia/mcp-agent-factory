# Summary: Connect External CLI (Cursor) to Secured MCP Gateway

## What was built

Four changes that bridge the gap between Cursor's OAuth auto-discovery expectations and
the existing OAuth 2.1 / PKCE implementation.

### 1. RFC 8414 Discovery on Auth Server
`src/mcp_agent_factory/auth/server.py`

`GET /.well-known/oauth-authorization-server` returns the full metadata document:
`issuer`, `authorization_endpoint`, `token_endpoint`, `registration_endpoint`,
`response_types_supported`, `code_challenge_methods_supported`, `scopes_supported`.
Issuer URL is controlled via the `AUTH_ISSUER` env var (default `http://localhost:8001`).

### 2. Gateway Discovery Proxy + WWW-Authenticate
`src/mcp_agent_factory/gateway/app.py`

- `GET /.well-known/oauth-authorization-server` on the gateway (`:8000`) proxies the auth
  server's discovery document via `httpx`. Falls back to a hardcoded static response when
  the auth server is unreachable (safe for unit tests / dev mode).
- All HTTP 401 responses now include
  `WWW-Authenticate: Bearer realm="mcp-server", resource_metadata="..."` per RFC 6750 §3.1,
  pointing clients at the gateway's own discovery URL.

### 3. mcp.json update
`mcp.json`

- Added missing `query_knowledge_base` tool schema.
- Added `discoveryUrl` pointing to `http://localhost:8000/.well-known/oauth-authorization-server`.
- Changed `transport` from `"http"` to `"sse"` (Cursor's preferred transport for HTTP+SSE servers).

### 4. Tests
`tests/test_cursor_connect.py` — 4 new tests, all green.

## Files changed

| File | Change |
|------|--------|
| `src/mcp_agent_factory/auth/server.py` | `GET /.well-known/oauth-authorization-server` endpoint |
| `src/mcp_agent_factory/gateway/app.py` | Discovery proxy + `WWW-Authenticate` exception handler |
| `mcp.json` | `query_knowledge_base` tool, `discoveryUrl`, `transport: sse` |
| `tests/test_cursor_connect.py` | 4 new tests |

## How to test / use

```bash
# 1. Start auth server
AUTH_ISSUER=http://localhost:8001 uvicorn mcp_agent_factory.auth.server:auth_app --port 8001

# 2. Start gateway
JWT_SECRET=<shared-secret> python -m mcp_agent_factory.gateway.run

# 3. Test discovery from gateway (single URL — no need to know port 8001)
curl http://localhost:8000/.well-known/oauth-authorization-server | jq .

# 4. Test WWW-Authenticate on 401
curl -si -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer bad.token.here" \
  -d '{}' | grep -i www-authenticate

# 5. Point Cursor at mcp.json — it will auto-discover auth endpoints
```

## Test results

```
240 passed, 11 skipped (Docker-only)
```
