---
id: S01
parent: M001
milestone: M001
provides:
  - Working MCP simulation server (STDIO, JSON-RPC 2.0, echo+add tools)
  - MCPOrchestrator client with connect/list_tools/call_tool API
  - pytest subprocess fixture (mcp_server) for lifecycle tests
  - 12 passing lifecycle tests as regression baseline
requires:
  []
affects:
  - S02
  - S03
key_files:
  - pyproject.toml
  - src/mcp_agent_factory/__init__.py
  - src/mcp_agent_factory/server.py
  - src/mcp_agent_factory/orchestrator.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/test_mcp_lifecycle.py
key_decisions:
  - Newline-delimited JSON STDIO (no Content-Length framing) — simpler for subprocess testing
  - setuptools.build_meta as build backend (setuptools.backends.legacy not available on Python 3.11)
  - connect() performs initialize handshake internally so callers get a ready client immediately
  - _rpc() single-outstanding-request pattern for implementation simplicity
patterns_established:
  - JSON-RPC 2.0 request/response over newline-delimited STDIO subprocess
  - Daemon reader thread + queue for safe subprocess stdout consumption in pytest fixtures
  - MCPOrchestrator context manager pattern (connect/disconnect lifecycle)
observability_surfaces:
  - Server logs every request/response as a JSON line to stderr — run python -m mcp_agent_factory.server and pipe JSON lines to observe the protocol
drill_down_paths:
  - .gsd/milestones/M001/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S01/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-26T16:23:02.565Z
blocker_discovered: false
---

# S01: MCP Foundation — Server, Client, and Lifecycle

**Full MCP STDIO lifecycle (initialize → tools/list → tools/call) proven by 12/12 passing pytest tests against a live simulation server subprocess.**

## What Happened

T01 scaffolded the Python package (pyproject.toml with editable install, src/mcp_agent_factory/ package, tests/ package) and implemented a simulation MCP server that speaks JSON-RPC 2.0 over newline-delimited STDIO. The server handles initialize, initialized notification, tools/list, and tools/call with two tools (echo, add). A daemon-thread + queue fixture in tests/conftest.py provides safe subprocess communication. A build-backend mismatch (setuptools.backends.legacy → setuptools.build_meta) was caught and fixed early.

T02 implemented MCPOrchestrator: spawns the server subprocess, background-reads stdout via a daemon thread, performs the initialize handshake in connect(), and exposes list_tools()/call_tool() as clean synchronous public methods. 12 lifecycle tests were written across three test classes (TestInitialize, TestListTools, TestCallTool), all exercising real subprocess I/O. All 12 pass in ~4s.

## Verification

python -m pytest tests/test_mcp_lifecycle.py -v — 12/12 passed in 4.22s. Tests cover: protocol version negotiation, server info, capabilities, tool list shape, echo tool, add tool, unknown tool error, empty echo, negative number add.

## Requirements Advanced

- R001 — MCPOrchestrator routes tool calls between client and server — full task dispatch proven by tests
- R002 — Complete JSON-RPC 2.0 lifecycle (initialize → tools/list → tools/call) proven by 12 passing tests
- R004 — Perception→Reasoning→Action foundation laid: server represents agent capability exposure, orchestrator represents the reasoning/dispatch layer

## Requirements Validated

- R001 — 12/12 pytest tests pass — test_call_echo, test_call_add, test_call_unknown_tool_returns_is_error all prove tool routing
- R002 — 12/12 pytest tests pass over live STDIO subprocess — initialize handshake, tools/list, tools/call all verified

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

setuptools.build_meta used instead of setuptools.backends.legacy:build (not available on Python 3.11 host). Server has no argparse --help handler; not needed for the STDIO subprocess use case.

## Known Limitations

The STDIO transport uses newline-delimited JSON, not the Content-Length framing specified by the official MCP spec — server is not wire-compatible with official MCP clients. MCPOrchestrator._rpc() uses a single-outstanding-request pattern (no per-ID map); concurrent calls from multiple threads will corrupt the response stream.

## Follow-ups

Evaluate whether Content-Length framing is needed before integrating with real MCP-compliant agents (likely S03 or beyond). Consider adding concurrent-request support to _rpc() if S02's ReAct loop needs parallel tool calls.

## Files Created/Modified

- `pyproject.toml` — Python package config with editable install, pytest settings, dev deps
- `src/mcp_agent_factory/__init__.py` — Package init
- `src/mcp_agent_factory/server.py` — Simulation MCP server — JSON-RPC 2.0 over STDIO, echo+add tools
- `src/mcp_agent_factory/orchestrator.py` — MCPOrchestrator client — subprocess spawn, initialize handshake, list_tools, call_tool
- `tests/__init__.py` — Tests package init
- `tests/conftest.py` — mcp_server pytest fixture with daemon reader thread
- `tests/test_mcp_lifecycle.py` — 12 lifecycle tests: initialize, list_tools, call_tool
