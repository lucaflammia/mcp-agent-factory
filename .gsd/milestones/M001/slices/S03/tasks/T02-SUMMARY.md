---
id: T02
parent: S03
milestone: M001
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/server.py", "tests/test_schema_validation.py"]
key_decisions: ["Catch both ValueError and ValidationError in _dispatch's tools/call block", "AddInput uses float; output formatted as int string when result is whole number"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "python -m pytest tests/ -v — 31 passed in 31.02s"
completed_at: 2026-03-26T16:33:56.980Z
blocker_discovered: false
---

# T02: Wired Pydantic v2 model_validate into server.py and wrote 8 schema/privacy tests; all 31 tests pass.

> Wired Pydantic v2 model_validate into server.py and wrote 8 schema/privacy tests; all 31 tests pass.

## What Happened
---
id: T02
parent: S03
milestone: M001
key_files:
  - src/mcp_agent_factory/server.py
  - tests/test_schema_validation.py
key_decisions:
  - Catch both ValueError and ValidationError in _dispatch's tools/call block
  - AddInput uses float; output formatted as int string when result is whole number
duration: ""
verification_result: passed
completed_at: 2026-03-26T16:33:56.983Z
blocker_discovered: false
---

# T02: Wired Pydantic v2 model_validate into server.py and wrote 8 schema/privacy tests; all 31 tests pass.

**Wired Pydantic v2 model_validate into server.py and wrote 8 schema/privacy tests; all 31 tests pass.**

## What Happened

Added Pydantic ValidationError import and model imports to server.py. Replaced bare dict access in _call_tool with EchoInput/AddInput model_validate calls. Updated _dispatch's tools/call except clause to catch (ValueError, ValidationError). Fixed add output to emit integer strings. Wrote tests/test_schema_validation.py with 8 tests covering missing fields, wrong types, valid paths, and PrivacyConfig assertions.

## Verification

python -m pytest tests/ -v — 31 passed in 31.02s

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest tests/ -v` | 0 | ✅ pass | 31020ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/server.py`
- `tests/test_schema_validation.py`


## Deviations
None.

## Known Issues
None.
