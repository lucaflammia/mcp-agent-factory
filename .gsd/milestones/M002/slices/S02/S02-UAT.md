# S02: FastAPI HTTP MCP Server + LLM Adapters — UAT

**Milestone:** M002
**Written:** 2026-03-27T08:05:05.112Z

## UAT: FastAPI HTTP MCP Server\n\nStart the server:\n```\nuvicorn mcp_agent_factory.server_http:app --port 8000\n```\n\nHealth check:\n```\ncurl http://localhost:8000/health\n# Expected: {\"status\":\"ok\"}\n```\n\nMCP lifecycle:\n```bash\ncurl -X POST http://localhost:8000/mcp \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n# Expected: result.tools contains echo and add\n\ncurl -X POST http://localhost:8000/mcp \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"echo\",\"arguments\":{\"message\":\"hello\"}}}'\n# Expected: result.content[0].text == \"hello\", isError == false\n```\n\n## UAT: LLM Adapters\n\n```python\nfrom mcp_agent_factory.adapters import LLMAdapterFactory\nfrom mcp_agent_factory.server_http import TOOLS\n\nfor provider in ['claude', 'openai', 'gemini']:\n    result = LLMAdapterFactory.get(provider).adapt(TOOLS)\n    print(f\"{provider}: {len(result)} tools\")\n    print(result[0])\n```
