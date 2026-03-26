# S02: ReAct Loop — Perception, Reasoning, and Action — Research

**Date:** 2026-03-26
**Status:** Complete

## Summary

S01 delivered a clean, tested MCPOrchestrator that can spawn a server subprocess and perform initialize/tools/list/tools/call over STDIO. S02 builds the ReAct loop directly on top of this — no new transport or protocol work needed.

The Fargin Curriculum (Cap 1, Cap 4) defines the loop precisely: Perception (receive task + available tools) → Reasoning (Thought: select tool and parameters, CoT log) → Action (tools/call via MCPOrchestrator) → Observation (result returned to reasoning step) → repeat or Synthesize. Cap 4's `LangChainAgent.reason_and_act()` is the direct template: `thought1` → `_select_tools` → `tool.execute()` → `observation` → `thought3` (synthesis). The M001 simulation keeps reasoning rule-based (no LLM) per R006 — the loop structure is identical, reasoning is heuristic.

The slice needs two new source files and two new test files. Everything else (server, orchestrator, conftest) is reused unchanged.

## Recommendation

Implement a `ReActAgent` class in `src/mcp_agent_factory/react_loop.py` that wraps MCPOrchestrator. The agent's `run(task: str)` method executes the full Perception→Reasoning→Action→Observation→Synthesis cycle and returns a `ReActResult` (Pydantic model). Tool selection is rule-based for M001 (keyword matching on task string). The reasoning log (list of Thought/Action/Observation dicts) is captured and exposed for test assertion.

A second file `tests/test_react_loop.py` tests the agent in isolation using a mock/stub MCPOrchestrator. A third file `tests/test_e2e_routing.py` tests the full path: ReActAgent → real MCPOrchestrator → live subprocess server.

## Implementation Landscape

### Key Files

- `src/mcp_agent_factory/react_loop.py` — **new** — `ReActAgent` class; `ReActStep` and `ReActResult` Pydantic models
- `src/mcp_agent_factory/orchestrator.py` — **unchanged** — consumed by `ReActAgent.__init__`
- `src/mcp_agent_factory/server.py` — **unchanged** — echo + add tools sufficient for ReAct demo
- `tests/test_react_loop.py` — **new** — unit tests with stub orchestrator
- `tests/test_e2e_routing.py` — **new** — integration tests against live subprocess
- `tests/conftest.py` — **unchanged** — `mcp_server` fixture reused by e2e tests

### ReActAgent Design

```python
# src/mcp_agent_factory/react_loop.py

from pydantic import BaseModel
from typing import Any

class ReActStep(BaseModel):
    type: str          # "thought" | "action" | "observation"
    content: str
    tool_name: str | None = None
    tool_args: dict | None = None

class ReActResult(BaseModel):
    task: str
    steps: list[ReActStep]
    answer: str
    success: bool

class ReActAgent:
    def __init__(self, orchestrator):  # accepts MCPOrchestrator instance
        self.orc = orchestrator

    def run(self, task: str) -> ReActResult:
        steps = []
        # 1. Perception: list available tools
        tools = self.orc.list_tools()
        tool_names = [t["name"] for t in tools]

        # 2. Reasoning: select tool (rule-based for M001)
        selected = self._select_tool(task, tool_names)
        steps.append(ReActStep(type="thought", content=f"Task: {task!r}. Available tools: {tool_names}. Selected: {selected}"))

        # 3. Action + Observation
        if selected:
            args = self._extract_args(task, selected)
            steps.append(ReActStep(type="action", content=f"call {selected}", tool_name=selected, tool_args=args))
            result = self.orc.call_tool(selected, args)
            obs = result.get("content", [{}])[0].get("text", "")
            steps.append(ReActStep(type="observation", content=obs))
            answer = f"Result of {selected}: {obs}"
            success = not result.get("isError", False)
        else:
            answer = "No suitable tool found"
            success = False

        return ReActResult(task=task, steps=steps, answer=answer, success=success)
```

### Tool Selection (rule-based, M001 only)

- Task contains "echo" or quoted string → select `echo`, extract first quoted or last word as `message`
- Task contains digits and math operators ("+", "add", "sum", "plus") → select `add`, extract two numbers
- No match → no tool (answer = "No suitable tool found")

### Build Order

1. `src/mcp_agent_factory/react_loop.py` — Pydantic models + ReActAgent class (no deps beyond orchestrator)
2. `tests/test_react_loop.py` — unit tests with a stub orchestrator (no subprocess); proves the loop logic
3. `tests/test_e2e_routing.py` — integration tests reusing `mcp_server` fixture; proves full chain

### Verification Approach

```bash
# Unit tests (stub orchestrator, no subprocess)
python -m pytest tests/test_react_loop.py -v

# E2E routing (live subprocess)
python -m pytest tests/test_e2e_routing.py -v

# Full suite regression
python -m pytest tests/ -v
```

Expected: all 12 S01 tests still pass, plus new tests for S02.

## Constraints

- Python 3.11.0 — no 3.12+ syntax (`str | None` in type hints is fine with `from __future__ import annotations`)
- MCPOrchestrator `_rpc()` is single-outstanding-request, synchronous — ReActAgent must call tools sequentially, not concurrently
- No external LLM calls in M01 simulation (R006) — reasoning must be rule-based or stub
- Pydantic v2 only — use `@field_validator`, not `@validator`

## Common Pitfalls

- **`from __future__ import annotations`** — required at the top of `react_loop.py` for `str | None` union syntax on Python 3.11 without `__future__`, actually `str | None` works natively on 3.10+ so this is fine — but `list[ReActStep]` in Pydantic v2 requires no extra import
- **Stub orchestrator in unit tests** — create a simple class with `list_tools()` / `call_tool()` methods; don't use `unittest.mock.MagicMock` unless careful about attribute access patterns (`.get()` on mock returns another mock)
- **`isError` field** — `call_tool()` result may have `isError: True`; the ReActAgent must check this to set `success=False` in result

## Sources

- Fargin Curriculum Cap 1: `note_intro_agenti.md` — "Percezione → Reasoning → Azione" cycle definition
- Fargin Curriculum Cap 4: `note_agenti_collaborativi_e_catene_di_ragionamento.md` — `reason_and_act()` implementation, Thought/Action/Observation/Answer pattern
- S01 Summary: `.gsd/milestones/M001/slices/S01/S01-SUMMARY.md` — MCPOrchestrator API, patterns established
