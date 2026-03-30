# M004: 

## Vision
Transition the MCP ecosystem from local STDIO to a secured HTTP/SSE Gateway, enabling external clients (Cursor, Claude Desktop, or custom Apps) to interact with the Agent Factory via OAuth 2.1. By the end of this milestone, a curl request streams live SSE events, unauthorized requests return 401, the Python client bridge handles full PKCE lifecycle with token caching, and an mcp.json config points external IDEs at the gateway.

## Slice Overview
| ID | Slice | Risk | Depends | Done | After this |
|----|-------|------|---------|------|------------|
| S01 | SSE /v1 Endpoints + Connected Event | high | — | ✅ | curl -N http://localhost:8000/sse/v1/events?topic=agent.events stays open and receives event: connected followed by tool call events when /mcp is invoked. |
| S02 | PKCE Hardening + 401 on Missing/Invalid Token | medium | S01 | ✅ | pytest tests/test_m004_auth_pkce.py -v shows PKCE round-trip issuing a token; 401 tests all pass. |
| S03 | Client Bridge — PKCE + Token Cache + SSE Consumption | medium | S02 | ✅ | pytest tests/test_m004_client_bridge.py -v shows list_tools, call_tool, token refresh, and SSE stream all passing. |
| S04 | Launch Script + mcp.json External Config | low | S03 | ✅ | python -m mcp_agent_factory.gateway.run starts; curl http://localhost:8000/health returns 200; mcp.json is checked in and valid. |
