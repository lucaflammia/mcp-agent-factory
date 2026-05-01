---
id: S01
parent: M012
milestone: M012
provides:
  - (none)
requires:
  []
affects:
  []
key_files:
  - (none)
key_decisions:
  - (none)
patterns_established:
  - ["_agents_dispatch() sub-router pattern — all agents/* methods delegate here from _mcp_dispatch_inner()"]
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-05-01T14:46:22.126Z
blocker_discovered: false
---

# S01: agents/analyze Dispatch

**New agents/analyze JSON-RPC method on the gateway with _agents_dispatch() sub-router, provider validation, and 3-case contract test green.**

## What Happened

Added ProviderNotConfiguredError, _PROVIDER_KEY_MAP, _validate_provider(), and _agents_dispatch() to gateway/app.py. The dispatch wires into _mcp_dispatch_inner() via a new elif method.startswith('agents/') branch. agents/analyze builds a DocumentAnalysisTask from request params, calls AnalystAgent().analyze_document(), and returns the serialized result. Missing provider key returns -32602; pipeline failure returns -32603; unknown agents/* method returns -32601. Contract test covers all three cases with MCP_DEV_MODE=1.

## Verification

python3.11 -m pytest tests/test_agents_dispatch.py -v → 3 passed

## Requirements Advanced

None.

## Requirements Validated

- R013 — agents/analyze method returns DocumentAnalysisResult via gateway
- R014 — _agents_dispatch() implemented and wired
- R016 — -32602 and -32603 verified by contract test
- R019 — 3 contract tests passing

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/gateway/app.py` — 
- `tests/test_agents_dispatch.py` — 
