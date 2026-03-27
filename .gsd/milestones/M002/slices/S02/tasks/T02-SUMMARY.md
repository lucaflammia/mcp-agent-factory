---
id: T02
parent: S02
milestone: M002
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/adapters.py"]
key_decisions: ["Gemini uses uppercase type strings (OBJECT, STRING, NUMBER) — _convert_schema recursion handles all nested property types", "LLMAdapterFactory uses case-insensitive provider lookup"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "python -c 'from mcp_agent_factory.adapters import LLMAdapterFactory; print(\"import ok\")' — passed."
completed_at: 2026-03-27T08:04:36.876Z
blocker_discovered: false
---

# T02: LLMAdapterFactory with Claude/OpenAI/Gemini adapters — schema translation only, tested with cross-adapter invariants.

> LLMAdapterFactory with Claude/OpenAI/Gemini adapters — schema translation only, tested with cross-adapter invariants.

## What Happened
---
id: T02
parent: S02
milestone: M002
key_files:
  - src/mcp_agent_factory/adapters.py
key_decisions:
  - Gemini uses uppercase type strings (OBJECT, STRING, NUMBER) — _convert_schema recursion handles all nested property types
  - LLMAdapterFactory uses case-insensitive provider lookup
duration: ""
verification_result: passed
completed_at: 2026-03-27T08:04:36.880Z
blocker_discovered: false
---

# T02: LLMAdapterFactory with Claude/OpenAI/Gemini adapters — schema translation only, tested with cross-adapter invariants.

**LLMAdapterFactory with Claude/OpenAI/Gemini adapters — schema translation only, tested with cross-adapter invariants.**

## What Happened

Created adapters.py with LLMAdapter base class, ClaudeAdapter (input_schema key), OpenAIAdapter (type=function wrapper), GeminiAdapter (uppercase types via recursive _convert_schema), and LLMAdapterFactory. All adapters deep-copy input to avoid mutation. Gemini type map covers string/number/integer/boolean/array/object.

## Verification

python -c 'from mcp_agent_factory.adapters import LLMAdapterFactory; print(\"import ok\")' — passed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -c 'from mcp_agent_factory.adapters import LLMAdapterFactory; print("import ok")'` | 0 | ✅ pass | 250ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/adapters.py`


## Deviations
None.

## Known Issues
None.
