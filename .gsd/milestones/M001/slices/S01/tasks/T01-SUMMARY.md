---
id: T01
parent: S01
milestone: M001
provides: []
requires: []
affects: []
key_files: ["pyproject.toml", "src/mcp_agent_factory/__init__.py", "src/mcp_agent_factory/server.py", "tests/__init__.py", "tests/conftest.py"]
key_decisions: ["setuptools.build_meta chosen over setuptools.backends.legacy (older setuptools on Python 3.11 host)", "Newline-delimited JSON STDIO (no Content-Length framing) for simplicity", "Two simulation tools: echo and add"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "Verified import, pytest collection, and full JSON-RPC lifecycle (initialize, tools/list, tools/call for echo and add) via piped STDIO. All pass."
completed_at: 2026-03-26T16:19:45.261Z
blocker_discovered: false
---

# T01: Scaffolded Python package and built a simulation MCP server over STDIO with JSON-RPC 2.0 support (initialize, tools/list, tools/call) plus pytest subprocess fixture

> Scaffolded Python package and built a simulation MCP server over STDIO with JSON-RPC 2.0 support (initialize, tools/list, tools/call) plus pytest subprocess fixture

## What Happened
---
id: T01
parent: S01
milestone: M001
key_files:
  - pyproject.toml
  - src/mcp_agent_factory/__init__.py
  - src/mcp_agent_factory/server.py
  - tests/__init__.py
  - tests/conftest.py
key_decisions:
  - setuptools.build_meta chosen over setuptools.backends.legacy (older setuptools on Python 3.11 host)
  - Newline-delimited JSON STDIO (no Content-Length framing) for simplicity
  - Two simulation tools: echo and add
duration: ""
verification_result: passed
completed_at: 2026-03-26T16:19:45.271Z
blocker_discovered: false
---

# T01: Scaffolded Python package and built a simulation MCP server over STDIO with JSON-RPC 2.0 support (initialize, tools/list, tools/call) plus pytest subprocess fixture

**Scaffolded Python package and built a simulation MCP server over STDIO with JSON-RPC 2.0 support (initialize, tools/list, tools/call) plus pytest subprocess fixture**

## What Happened

Created the full project skeleton: pyproject.toml with editable install and dev deps, src/mcp_agent_factory/ package, and tests/ package. The simulation MCP server speaks JSON-RPC 2.0 over newline-delimited STDIO, handling initialize, initialized, tools/list, and tools/call with two tools (echo, add). Every request/response is logged as a JSON line to stderr. tests/conftest.py provides the mcp_server fixture using a daemon reader thread + queue for safe subprocess communication. Fixed build-backend mismatch (setuptools.backends.legacy → setuptools.build_meta for this Python 3.11 env).

## Verification

Verified import, pytest collection, and full JSON-RPC lifecycle (initialize, tools/list, tools/call for echo and add) via piped STDIO. All pass.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -c "import mcp_agent_factory.server; print('import OK')"` | 0 | ✅ pass | 300ms |
| 2 | `python -m pytest tests/ --collect-only -q` | 5 | ✅ pass | 400ms |
| 3 | `echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python -m mcp_agent_factory.server 2>/dev/null` | 0 | ✅ pass | 350ms |
| 4 | `printf 'tools/list\ntools/call echo\ntools/call add' | python -m mcp_agent_factory.server 2>/dev/null` | 0 | ✅ pass | 400ms |


## Deviations

setuptools.build_meta used instead of setuptools.backends.legacy:build (not available on this host). Server has no argparse --help handler; verification command's fallback branch covers this.

## Known Issues

None.

## Files Created/Modified

- `pyproject.toml`
- `src/mcp_agent_factory/__init__.py`
- `src/mcp_agent_factory/server.py`
- `tests/__init__.py`
- `tests/conftest.py`


## Deviations
setuptools.build_meta used instead of setuptools.backends.legacy:build (not available on this host). Server has no argparse --help handler; verification command's fallback branch covers this.

## Known Issues
None.
