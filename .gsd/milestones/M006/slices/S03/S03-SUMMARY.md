---
id: S03
parent: M006
milestone: M006
provides:
  - ValidationGate class in gateway/validation.py
  - InternalServiceLayer class in gateway/service_layer.py
  - Refactored _mcp_dispatch that delegates to service layer
  - tests/test_m006_gateway.py with 3 tests covering malformed payload rejection and valid dispatch
requires:
  []
affects:
  - S04
  - S05
key_files:
  - src/mcp_agent_factory/gateway/validation.py
  - src/mcp_agent_factory/gateway/service_layer.py
  - src/mcp_agent_factory/gateway/app.py
  - tests/test_m006_gateway.py
  - tests/test_gateway.py
key_decisions:
  - monkeypatch DEV_MODE attribute (not os.environ) to avoid module-level bool baked at import time
  - client fixture in test_gateway.py patches DEV_MODE=False so auth tests work under MCP_DEV_MODE=1 env
  - InternalServiceLayer takes explicit deps in __init__ for testability
  - _service_layer singleton instantiated at module level after all dependency singletons
patterns_established:
  - Thin delegator pattern: _mcp_dispatch is now a 5-line try/except that calls _service_layer.handle()
  - ValidationGate: single-method wrapper around Pydantic model construction — lets ValidationError propagate
  - DEV_MODE isolation in tests: always monkeypatch the module attribute, not os.environ
observability_surfaces:
  - none
drill_down_paths:
  - .gsd/milestones/M006/slices/S03/tasks/T01-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-04-01T14:34:40.689Z
blocker_discovered: false
---

# S03: Validation Gate + Internal Service Layer

**Inserted a Pydantic ValidationGate and InternalServiceLayer into the gateway, refactored _mcp_dispatch to a thin delegator, and fixed the DEV_MODE isolation bug in test_gateway.py.**

## What Happened

S03 extracted business logic from the monolithic `_mcp_dispatch` function into two new modules. `ValidationGate` (validation.py) wraps Pydantic model construction and lets `ValidationError` propagate. `InternalServiceLayer` (service_layer.py) receives all dependency singletons in `__init__` and implements `async def handle(tool_name, args, claims)` — for the `add` tool it validates via `ValidationGate` before computing the result; for all other tools it preserves existing logic unchanged. `app.py` was updated to instantiate `_service_layer` at module level and replace the dispatch block with a try/except that catches `ValidationError` and `ValueError` as structured `isError` responses. The fix during auto-fix round was in `test_gateway.py`: running the full suite with `MCP_DEV_MODE=1` bypassed JWT auth globally, causing `test_mcp_no_auth_returns_401` to receive a `result` key instead of an `error` key. The client fixture was updated to `monkeypatch.setattr(_app, "DEV_MODE", False)` so the test correctly verifies the auth path regardless of the environment variable.

## Verification

MCP_DEV_MODE=1 pytest tests/test_m006_gateway.py tests/test_gateway.py -v — 12/12 passed in 4.07s

## Requirements Advanced

- R006 — InternalServiceLayer extracted from _mcp_dispatch; gateway is now a thin delegator
- R007 — ValidationGate blocks malformed add arguments; test_malformed_add_blocked confirms isError=True response

## Requirements Validated

- R006 — test_valid_add_dispatched passes; _mcp_dispatch delegates to InternalServiceLayer
- R007 — test_malformed_add_blocked passes; ValidationError returned as structured isError response

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

test_gateway.py client fixture required a monkeypatch to override DEV_MODE=False so test_mcp_no_auth_returns_401 works correctly when the suite is run with MCP_DEV_MODE=1 in the environment. This was not in the original plan.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/gateway/validation.py` — New: ValidationGate class with validate() method
- `src/mcp_agent_factory/gateway/service_layer.py` — New: InternalServiceLayer with handle() delegating tool dispatch
- `src/mcp_agent_factory/gateway/app.py` — Added _service_layer singleton; replaced dispatch block with try/except delegation
- `tests/test_m006_gateway.py` — New: 3 tests for malformed payload blocking, valid dispatch, and tools list smoke
- `tests/test_gateway.py` — Fixed client fixture to monkeypatch DEV_MODE=False for auth test isolation
