---
id: S02
parent: M001
milestone: M001
provides:
  - ReActAgent.run(task) → ReActResult executing full Perception→Reasoning→Action→Observation→Synthesis cycle
  - ReActStep and ReActResult Pydantic v2 models as trace record
  - StubOrchestrator pattern for unit testing agent logic without subprocess overhead
requires:
  - slice: S01
    provides: MCPOrchestrator with connect/disconnect/list_tools/call_tool API and conftest mcp_server fixture
affects:
  - S03
key_files:
  - src/mcp_agent_factory/react_loop.py
  - tests/test_react_loop.py
  - tests/test_e2e_routing.py
key_decisions:
  - Rule-based tool selection avoids LLM dependency for deterministic unit tests
  - E2e tests use MCPOrchestrator() directly (no-arg) rather than wrapping the mcp_server fixture's MCPServerProcess, because MCPOrchestrator manages its own subprocess lifecycle
patterns_established:
  - StubOrchestrator pattern: plain class (not Mock) implementing list_tools/call_tool for fast, readable unit tests
  - ReActStep/ReActResult Pydantic v2 models as the canonical trace record for a ReAct cycle
  - Rule-based _select_tool + _extract_args as the deterministic routing layer before any LLM integration
observability_surfaces:
  - DEBUG logging on every ReAct step (thought, action, observation) via Python logging
drill_down_paths:
  - .gsd/milestones/M001/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S02/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-26T16:29:07.191Z
blocker_discovered: false
---

# S02: ReAct Loop — Perception, Reasoning, and Action

**ReActAgent implementing the full Perception→Reasoning→Action→Observation→Synthesis cycle over MCPOrchestrator, proven by 7 unit tests and 4 e2e integration tests (23 total suite tests passing).**

## What Happened

T01 delivered `src/mcp_agent_factory/react_loop.py` with three classes: `ReActStep` and `ReActResult` (Pydantic v2 BaseModels) and `ReActAgent` wrapping an MCPOrchestrator. `ReActAgent.run()` executes the full ReAct cycle: Perception (list_tools), Reasoning (_select_tool — rule-based, no LLM dependency), Action (_extract_args + call_tool), Observation (extract text from result), and Synthesis (populate ReActResult). Rule-based tool selection deterministically routes echo/add tasks without requiring an LLM, making tests fast and reproducible.

T02 wrote two test files. `tests/test_react_loop.py` uses a plain StubOrchestrator (no Mock) covering 7 cases: echo routing, add routing, no-tool fallback, steps structure, model types, message extraction, and large numbers. `tests/test_e2e_routing.py` uses MCPOrchestrator() directly (no-arg constructor) rather than the conftest mcp_server fixture — the fixture yields an MCPServerProcess wrapper incompatible with MCPOrchestrator's constructor, so e2e tests bypass it and let the orchestrator spawn its own subprocess. This was a deliberate deviation from the plan but produces the same behaviour with a cleaner API. All 11 new tests pass; full suite is 23 passed.

## Verification

pytest tests/test_react_loop.py tests/test_e2e_routing.py -v → 11 passed in 1.22s. pytest tests/ -v → 23 passed in 5.14s.

## Requirements Advanced

- R003 — ReActAgent implements Perception→Reasoning→Action loop with tool discovery (list_tools) and execution (call_tool), proven by passing unit and e2e tests

## Requirements Validated

- R003 — pytest tests/test_react_loop.py tests/test_e2e_routing.py -v → 11 passed; pytest tests/ -v → 23 passed; full ReAct cycle (thought+action+observation steps) verified in test_e2e_react_steps_present and test_steps_structure

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

E2e tests use MCPOrchestrator() (no-arg) directly instead of wrapping the mcp_server fixture, because the fixture yields MCPServerProcess which is incompatible with MCPOrchestrator's constructor. Functionally equivalent — orchestrator spawns its own subprocess.

## Known Limitations

Rule-based tool selection only handles echo and add — adding new tools requires extending _select_tool and _extract_args. MCPOrchestrator single-request assumption means concurrent ReActAgent calls would corrupt the response stream (documented in KNOWLEDGE.md from S01).

## Follow-ups

S03 should add schema validation on tool args before the Action step. Consider whether ReActAgent should accept an orchestrator factory or context manager to avoid connect/disconnect boilerplate in tests.

## Files Created/Modified

- `src/mcp_agent_factory/react_loop.py` — ReActStep, ReActResult Pydantic v2 models and ReActAgent implementing the full ReAct cycle
- `tests/test_react_loop.py` — 7 unit tests using StubOrchestrator
- `tests/test_e2e_routing.py` — 4 e2e integration tests using live MCPOrchestrator subprocess
