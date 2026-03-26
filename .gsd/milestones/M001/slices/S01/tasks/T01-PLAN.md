---
estimated_steps: 1
estimated_files: 5
skills_used: []
---

# T01: Scaffold Python project and build simulation MCP server over STDIO

Create the Python package layout, install pytest, and implement a minimal but complete simulation MCP server that speaks JSON-RPC 2.0 over STDIO. The server must handle initialize, tools/list, and tools/call (with at least one dummy tool). This server becomes the live subprocess target for T02's tests.

## Inputs

- ``.gsd/milestones/M001/M001-CONTEXT.md` — project description and constraints`

## Expected Output

- ``pyproject.toml` — package manifest with pytest dev dependency and mcp-sim-server entry point`
- ``src/mcp_agent_factory/__init__.py` — package init`
- ``src/mcp_agent_factory/server.py` — STDIO JSON-RPC 2.0 MCP server handling initialize/tools/list/tools/call`
- ``tests/__init__.py` — empty tests package marker`
- ``tests/conftest.py` — pytest fixtures (e.g. server subprocess fixture)`

## Verification

python -m mcp_agent_factory.server --help 2>&1 || python -c "import mcp_agent_factory.server" && python -m pytest tests/ --collect-only -q 2>&1 | grep -v 'no tests'

## Observability Impact

Server writes one JSON line to stderr per request received and per response sent, enabling post-mortem replay of any failing message exchange.
