---
id: S03
parent: M001
milestone: M001
provides:
  - Pydantic v2 I/O models for echo and add tools
  - PrivacyConfig with local-only defaults and egress guard
  - Schema validation wired into server dispatch returning isError=True on bad input
  - 8-test schema/privacy test suite
requires:
  - slice: S01
    provides: MCP server/client lifecycle and _dispatch handler that this slice extended with validation
affects:
  []
key_files:
  - src/mcp_agent_factory/models.py
  - src/mcp_agent_factory/config/__init__.py
  - src/mcp_agent_factory/config/privacy.py
  - src/mcp_agent_factory/server.py
  - tests/test_schema_validation.py
key_decisions:
  - Catch both ValueError and ValidationError in _dispatch's tools/call block — ValidationError is not a subclass of ValueError in Pydantic v2
  - AddInput uses float; format output as int string when result is whole number to match existing lifecycle test assertions
  - PrivacyConfig assert_no_egress raises RuntimeError only when allow_egress=True — default (False) passes silently
patterns_established:
  - Pydantic v2 model_validate at tool dispatch boundary — validate before use, surface errors as isError=True MCP responses
  - PrivacyConfig as a standalone module with explicit egress guard — import and call assert_no_egress() before any outbound operation
observability_surfaces:
  - none
drill_down_paths:
  - .gsd/milestones/M001/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S03/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-26T16:35:40.081Z
blocker_discovered: false
---

# S03: Schema Validation and Privacy-First Config

**Pydantic v2 schema validation wired into server dispatch and PrivacyConfig with local-only defaults; all 31 tests pass including 8 new schema/privacy tests.**

## What Happened

T01 created three pure-Python modules: `src/mcp_agent_factory/models.py` (EchoInput, EchoOutput, AddInput, AddOutput as Pydantic v2 BaseModel subclasses), `src/mcp_agent_factory/config/__init__.py` (package marker), and `src/mcp_agent_factory/config/privacy.py` (PrivacyConfig with local_only=True, allow_egress=False defaults and assert_no_egress() guard). T02 wired model_validate into server.py's _call_tool handler — replacing bare dict access — and updated _dispatch to catch both ValueError and ValidationError so schema errors return isError=True responses. Output formatting for add was fixed to emit integer strings for whole results. 8 new tests in test_schema_validation.py cover missing fields, wrong types, valid paths, and both PrivacyConfig branches. Full suite: 31 passed.

## Verification

python -m pytest tests/ -v — 31 passed in 21.23s. Covers all prior lifecycle, e2e routing, ReAct loop tests plus the 8 new schema/privacy tests.

## Requirements Advanced

- R005 — Schema validation via Pydantic v2 model_validate in server dispatch; invalid inputs return isError=True, proven by 5 test cases
- R006 — PrivacyConfig defaults to local_only=True/allow_egress=False; assert_no_egress() raises RuntimeError when egress enabled, proven by 3 test cases

## Requirements Validated

- R005 — test_echo_missing_message, test_add_missing_field, test_add_wrong_type return isError=True; test_echo_valid and test_add_valid confirm valid paths pass through correctly
- R006 — test_privacy_config_defaults confirms defaults, test_assert_no_egress_passes_on_default and test_assert_no_egress_raises_when_enabled prove both branches

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None.

## Known Limitations

The simulation server uses newline-delimited JSON, not the Content-Length framing required by the official MCP spec. Schema validation is scoped to the two implemented tools (echo, add); any new tool requires corresponding Pydantic models and wiring.

## Follow-ups

Evaluate Content-Length framing for MCP spec wire-compatibility. Add Pydantic models for any new tools introduced in future slices.

## Files Created/Modified

- `src/mcp_agent_factory/models.py` — New — EchoInput, EchoOutput, AddInput, AddOutput Pydantic v2 BaseModel subclasses
- `src/mcp_agent_factory/config/__init__.py` — New — empty package marker
- `src/mcp_agent_factory/config/privacy.py` — New — PrivacyConfig with local_only/allow_egress defaults and assert_no_egress guard
- `src/mcp_agent_factory/server.py` — Modified — model_validate wired into _call_tool; _dispatch catches ValidationError alongside ValueError
- `tests/test_schema_validation.py` — New — 8 tests covering schema rejection, valid paths, and PrivacyConfig assertions
