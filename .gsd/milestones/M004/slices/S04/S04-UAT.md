# S04: Launch Script + mcp.json External Config — UAT

**Milestone:** M004
**Written:** 2026-03-30T06:55:52.426Z

## UAT: Launch Script + mcp.json\n\n```bash\n# Start gateway\npython -m mcp_agent_factory.gateway.run\n# Expected output: MCP Gateway running on http://0.0.0.0:8000\n\n# Health check\ncurl http://localhost:8000/health\n# Expected: {\"status\": \"ok\", \"service\": \"mcp-gateway\"}\n\n# SSE stream\ncurl -N http://localhost:8000/sse/v1/events?topic=agent.events\n# Expected: event: connected\\ndata: {\"topic\": \"agent.events\"}\n```\n\n`mcp.json` is valid JSON with serverUrl, authUrl, endpoints, and tool schemas."
