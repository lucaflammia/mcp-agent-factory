# S01: MCP Foundation — Server, Client, and Lifecycle

**Goal:** Build the MCP transport foundation: a simulation server runnable as a STDIO subprocess and an orchestrator client that performs full lifecycle (initialize → tools/list → tools/call), proving R001 (orchestration routing) and R002 (JSON-RPC 2.0 communication).
**Demo:** After this: pytest tests/test_mcp_lifecycle.py -v passes, showing the orchestrator listing and calling tools on a live simulation server subprocess over STDIO.

## Tasks
- [x] **T01: Scaffolded Python package and built a simulation MCP server over STDIO with JSON-RPC 2.0 support (initialize, tools/list, tools/call) plus pytest subprocess fixture** — Create the Python package layout, install pytest, and implement a minimal but complete simulation MCP server that speaks JSON-RPC 2.0 over STDIO. The server must handle initialize, tools/list, and tools/call (with at least one dummy tool). This server becomes the live subprocess target for T02's tests.
  - Estimate: 1h
  - Files: pyproject.toml, src/mcp_agent_factory/__init__.py, src/mcp_agent_factory/server.py, tests/__init__.py, tests/conftest.py
  - Verify: python -m mcp_agent_factory.server --help 2>&1 || python -c "import mcp_agent_factory.server" && python -m pytest tests/ --collect-only -q 2>&1 | grep -v 'no tests'
- [x] **T02: Built MCPOrchestrator client and 12 lifecycle tests — all pass in 3.84s proving full MCP STDIO round-trip** — Implement the MCPOrchestrator client class that spawns the simulation server as a subprocess, drives the full JSON-RPC lifecycle (initialize, tools/list, tools/call), and write tests/test_mcp_lifecycle.py with at least 3 passing tests covering capability negotiation, tool discovery, and tool invocation.
  - Estimate: 1.5h
  - Files: src/mcp_agent_factory/orchestrator.py, tests/test_mcp_lifecycle.py
  - Verify: python -m pytest tests/test_mcp_lifecycle.py -v
