---
id: M001
title: "Core Orchestrator and MCP Foundation"
status: complete
completed_at: 2026-03-26T16:38:30.597Z
key_decisions:
  - Newline-delimited JSON STDIO transport (not Content-Length framing) — simpler for subprocess testing but not wire-compatible with official MCP clients.
  - setuptools.build_meta as build backend — setuptools.backends.legacy not available on Python 3.11.
  - connect() performs initialize handshake internally — callers get a ready client with no extra ceremony.
  - _rpc() single-outstanding-request pattern — acceptable for sequential test harness, documented limitation for concurrent use.
  - Rule-based _select_tool (regex heuristics) — deterministic, no LLM dependency; must remain stable as new tools are added behind an interface.
  - StubOrchestrator pattern (plain class, not Mock) — readable unit tests without setup verbosity.
  - Catch both ValueError and ValidationError in _dispatch — Pydantic v2 ValidationError is not a subclass of ValueError.
  - AddInput uses float; emit int string for whole results — required to match existing lifecycle test assertions.
key_files:
  - pyproject.toml
  - src/mcp_agent_factory/__init__.py
  - src/mcp_agent_factory/server.py
  - src/mcp_agent_factory/orchestrator.py
  - src/mcp_agent_factory/react_loop.py
  - src/mcp_agent_factory/models.py
  - src/mcp_agent_factory/config/__init__.py
  - src/mcp_agent_factory/config/privacy.py
  - tests/conftest.py
  - tests/test_mcp_lifecycle.py
  - tests/test_react_loop.py
  - tests/test_e2e_routing.py
  - tests/test_schema_validation.py
lessons_learned:
  - The mcp_server conftest fixture yields MCPServerProcess (a wrapper), not a raw Popen or MCPOrchestrator — e2e tests must instantiate MCPOrchestrator() directly to avoid constructor mismatch.
  - Pydantic v2 ValidationError is not a subclass of ValueError — always catch both in dispatch handlers.
  - StubOrchestrator as a plain class (not Mock) produces much more readable test failures and avoids mock setup overhead.
  - Rule-based routing must be isolated behind a clear interface boundary so LLM-based routing can be swapped in later without breaking deterministic tests.
  - setuptools.build_meta is the correct backend for Python 3.11+ — setuptools.backends.legacy is not available.
  - STDIO newline-delimited JSON works for subprocess testing but is not MCP-spec-compatible — evaluate Content-Length framing before connecting to real MCP clients.
---

# M001: Core Orchestrator and MCP Foundation

**Established a working multi-agent orchestration engine over MCP with full JSON-RPC 2.0 lifecycle, ReAct loop, Pydantic v2 schema validation, and privacy-first config — proven by 31 passing pytest tests.**

## What Happened

M001 was executed across three slices spanning three sessions.

S01 (MCP Foundation) built the entire STDIO transport layer from scratch: a simulation MCP server handling JSON-RPC 2.0 (initialize, tools/list, tools/call) over newline-delimited STDIO, and MCPOrchestrator as the client that spawns a subprocess, performs the initialize handshake in connect(), and exposes list_tools()/call_tool() as clean synchronous methods. A daemon-thread + queue fixture in conftest.py enables safe subprocess I/O in pytest. 12 lifecycle tests prove the full protocol lifecycle. One notable deviation: setuptools.build_meta was required instead of setuptools.backends.legacy (not available on Python 3.11).

S02 (ReAct Loop) implemented ReActAgent.run(task) executing the full Perception→Reasoning→Action→Observation→Synthesis cycle. ReActStep and ReActResult are Pydantic v2 BaseModel trace records. Tool selection is rule-based (regex heuristics), making tests fully deterministic without LLM dependency. A StubOrchestrator pattern was established for fast unit tests. E2e tests use MCPOrchestrator() directly rather than the conftest fixture (which yields MCPServerProcess, incompatible with the constructor). 11 new tests; 23 total passing.

S03 (Schema Validation and Privacy) added Pydantic v2 I/O models (EchoInput, EchoOutput, AddInput, AddOutput) and PrivacyConfig with local_only=True/allow_egress=False defaults and an assert_no_egress() guard. model_validate was wired into server.py's _call_tool handler; _dispatch was updated to catch both ValueError and ValidationError so schema errors return isError=True MCP responses. A key fix: AddInput uses float but emits integer strings for whole results to satisfy existing lifecycle test assertions. 8 new tests; 31 total passing.

Final state: 631 lines of production code across 10 files, 31 passing tests covering all protocol layers, agent logic, schema validation, and privacy config.

## Success Criteria Results

## Success Criteria Results

- **A basic orchestrator successfully routes a simple task from a simulated agent to another simulated agent via MCP** ✅ — MCPOrchestrator.call_tool() routes echo and add tasks to the simulation server subprocess over STDIO. ReActAgent.run() wraps this in the full ReAct cycle. Proven by test_e2e_routing.py (4 tests) and test_mcp_lifecycle.py (12 tests).

- **Full JSON-RPC 2.0 lifecycle (initialize → tools/list → tools/call)** ✅ — All 12 lifecycle tests pass, covering protocol version negotiation, capabilities, tool list shape, echo tool, add tool, unknown tool error responses.

- **ReAct loop (Perception→Reasoning→Action) demonstrated** ✅ — ReActAgent.run() executes all 5 phases; test_e2e_react_steps_present and test_steps_structure verify the step trace contains thought/action/observation entries.

- **Schema validation (Pydantic v2) rejecting bad inputs** ✅ — test_echo_missing_message, test_add_missing_field, test_add_wrong_type all confirm isError=True responses on invalid inputs.

- **Privacy-first config with egress guard** ✅ — PrivacyConfig defaults to local_only=True/allow_egress=False; assert_no_egress() raises RuntimeError only when allow_egress=True, proven by 3 tests.

## Definition of Done Results

## Definition of Done

- **All slices ✅** — S01, S02, S03 all completed and verified.
- **All slice summaries exist** ✅ — S01-SUMMARY.md, S02-SUMMARY.md, S03-SUMMARY.md written.
- **31/31 tests pass** ✅ — `pytest tests/ -v` → 31 passed in 33.77s.
- **Code changes exist** ✅ — 10 non-.gsd/ files, 631 insertions from root commit to HEAD.
- **Cross-slice integration** ✅ — S03's validation is wired into S01's server.py handler; S02's ReActAgent uses S01's MCPOrchestrator; all three layers exercise together in test_e2e_routing.py.

## Requirement Outcomes

## Requirement Outcomes

- **R001 (Core Orchestration Engine)** — Active → Validated. MCPOrchestrator routes tool calls between client and server; 12 lifecycle tests + 4 e2e routing tests prove dispatch.
- **R002 (MCP Communication Protocol)** — Active → Validated. Full JSON-RPC 2.0 lifecycle (initialize → tools/list → tools/call) proven by 12 passing tests over live STDIO subprocess.
- **R003 (ReAct Pattern Implementation)** — Active → Validated. ReActAgent implements Perception→Reasoning→Action loop with list_tools + call_tool; 11 tests prove the cycle including step trace structure.
- **R004 (Fargin Curriculum Integration)** — Active → Validated. Server represents agent capability exposure; orchestrator represents the reasoning/dispatch layer; ReActAgent maps directly to the Perception→Reasoning→Action theory.
- **R005 (Schema Validation for Security)** — Active → Validated. Pydantic v2 model_validate in server dispatch; invalid inputs return isError=True, proven by 5 test cases.
- **R006 (Privacy-First Design)** — Active → Validated. PrivacyConfig defaults to local_only=True/allow_egress=False; assert_no_egress() raises RuntimeError when egress enabled, proven by 3 test cases.

## Deviations

setuptools.build_meta used instead of setuptools.backends.legacy (not available on Python 3.11). E2e tests use MCPOrchestrator() directly instead of wrapping conftest mcp_server fixture — functionally equivalent. STDIO transport uses newline-delimited JSON not Content-Length framing (documented as known limitation).

## Follow-ups

Evaluate Content-Length framing for MCP spec wire-compatibility before integrating with real MCP clients. Add concurrent-request support to _rpc() if parallel tool calls are needed. Extend _select_tool and _extract_args (behind an interface) when new tools are added. Consider whether ReActAgent should accept an orchestrator factory to reduce connect/disconnect boilerplate in tests.
