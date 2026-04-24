# Plan: Connect External CLI (Cursor) to Secured MCP Gateway

## Task 1 — OAuth discovery endpoint on auth server

**File:** `src/mcp_agent_factory/auth/server.py`

Add `GET /.well-known/oauth-authorization-server` that returns an RFC 8414 metadata
document. Fields: `issuer`, `authorization_endpoint`, `token_endpoint`,
`registration_endpoint`, `response_types_supported`, `code_challenge_methods_supported`,
`scopes_supported`.

The `issuer` URL is derived from a new `AUTH_ISSUER` env var (default `http://localhost:8001`).

**Verify:** `GET http://localhost:8001/.well-known/oauth-authorization-server` returns JSON
with all required fields.

---

## Task 2 — Gateway proxies discovery + adds WWW-Authenticate on 401

**File:** `src/mcp_agent_factory/gateway/app.py`

1. Add `GET /.well-known/oauth-authorization-server` — fetches the auth server's discovery
   doc (URL from `AUTH_SERVER_URL` env var, default `http://localhost:8001`) using
   `httpx.AsyncClient` and re-serves it. Falls back to a static inline response when auth
   server is unreachable (dev mode).
2. Override the 401 exception handler to inject
   `WWW-Authenticate: Bearer realm="mcp-server", resource_metadata="http://localhost:8000/.well-known/oauth-authorization-server"`

**Verify:** `curl -I http://localhost:8000/mcp` returns 401 with `WWW-Authenticate` header.

---

## Task 3 — Update mcp.json

**File:** `mcp.json`

- Add `query_knowledge_base` tool entry (already exposed by gateway, just missing from config).
- Align `transport` field: use `"sse"` alongside existing `serverUrl` (Cursor's current
  preferred transport for HTTP+SSE servers).
- Add `discoveryUrl` field pointing to
  `http://localhost:8000/.well-known/oauth-authorization-server`.

**Verify:** JSON is valid; tool list matches gateway's `TOOLS` registry.

---

## Task 4 — Tests

**File:** `tests/test_cursor_connect.py` (new)

- Test auth server discovery endpoint returns correct RFC 8414 fields.
- Test gateway 401 response includes `WWW-Authenticate` header.
- Test gateway discovery proxy returns at least `authorization_endpoint`.

**Verify:** `pytest tests/test_cursor_connect.py -v` all green.
