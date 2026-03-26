---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T02: Implement orchestrator client and test full MCP lifecycle over STDIO

Implement the MCPOrchestrator client class that spawns the simulation server as a subprocess, drives the full JSON-RPC lifecycle (initialize, tools/list, tools/call), and write tests/test_mcp_lifecycle.py with at least 3 passing tests covering capability negotiation, tool discovery, and tool invocation.

## Inputs

- ``src/mcp_agent_factory/server.py` — simulation server to spawn as subprocess`
- ``tests/conftest.py` — shared fixtures`
- ``pyproject.toml` — package entry point for subprocess spawning`

## Expected Output

- ``src/mcp_agent_factory/orchestrator.py` — MCPOrchestrator class with connect(), list_tools(), call_tool() methods`
- ``tests/test_mcp_lifecycle.py` — 3+ tests: test_initialize, test_list_tools, test_call_tool`

## Verification

python -m pytest tests/test_mcp_lifecycle.py -v

## Observability Impact

MCPOrchestrator logs each JSON-RPC send/receive at DEBUG level; tests assert on response structure so failures show the exact malformed message.
