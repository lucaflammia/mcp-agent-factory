# Feature: Connect External CLI (Cursor) to Secured MCP Gateway

## Description

Enable Cursor (and any OAuth 2.1-compliant MCP client) to connect to the secured MCP
Gateway by bridging the gap between Cursor's auto-discovery expectations and our OAuth
2.1 / PKCE implementation.

## Key Decisions

- **RFC 8414 discovery** — add `/.well-known/oauth-authorization-server` to the auth
  server so clients can auto-discover `authorization_endpoint`, `token_endpoint`, and
  `registration_endpoint` without hardcoding URLs.
- **Gateway proxies discovery** — Cursor only knows the gateway URL (`:8000`); the
  gateway will forward `/.well-known/oauth-authorization-server` requests to the auth
  server so clients need only one base URL.
- **WWW-Authenticate on 401** — gateway 401 responses will include a
  `WWW-Authenticate: Bearer realm="mcp-server" ...` header pointing at the discovery
  URL, per RFC 6750 §3.1.
- **mcp.json** — add the `query_knowledge_base` tool (currently missing) and align the
  transport / auth fields with current Cursor MCP spec.

## Scope Boundaries

**In scope:**
- `/.well-known/oauth-authorization-server` endpoint on auth server
- Gateway `/.well-known/oauth-authorization-server` proxy route
- `WWW-Authenticate` header on all gateway 401 responses
- `mcp.json` update (missing tool + field alignment)
- Unit tests for discovery endpoint and 401 header

**Out of scope:**
- Interactive PKCE CLI helper / token bootstrap script
- RS256 / JWKS rotation
- Cursor UI / end-to-end browser testing
