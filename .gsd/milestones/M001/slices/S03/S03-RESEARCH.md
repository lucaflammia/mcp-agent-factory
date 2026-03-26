# S03: Schema Validation and Privacy-First Config — Research

**Date:** 2026-03-26
**Status:** Complete

## Summary

S03 is structural hardening on top of working S01/S02 code. The codebase uses bare `dict` everywhere for tool arguments and results — this slice adds Pydantic v2 models as the canonical I/O layer, wires validation into the server's `_call_tool` path, and adds a privacy config module with a local-only inference flag and a no-egress assertion. No new technology — Pydantic 2.12.5 is already installed and Pydantic v2 patterns are already used by the `mcp` SDK.

The slice adds two new source files (`src/mcp_agent_factory/models.py`, `src/mcp_agent_factory/config/privacy.py`) and a new test file (`tests/test_schema_validation.py`). Existing files (`server.py`) get light edits to validate arguments before tool dispatch. No changes to `orchestrator.py` or `react_loop.py` are required for the base validation pass.

## Recommendation

Create Pydantic models for all tool input/output, wire them into `server.py`'s `_call_tool`, and add a `PrivacyConfig` dataclass/Pydantic model with `local_only: bool = True` and a `assert_no_egress()` helper. Write tests that send bad arguments and confirm the server returns `isError=True` with a validation error message (not a protocol-level error). This matches the curriculum's Cap 3 guidance that tool execution errors must set `isError=True`, not raise JSON-RPC faults.

## Implementation Landscape

### Key Files

- `src/mcp_agent_factory/server.py` — `_call_tool()` currently takes bare `dict`; wrap argument parsing with Pydantic model `.model_validate(arguments)` and catch `ValidationError` → return `isError=True` content block
- `src/mcp_agent_factory/models.py` — **new file**; define `EchoInput`, `EchoOutput`, `AddInput`, `AddOutput`, `ToolCallResult` as Pydantic v2 `BaseModel` subclasses. These satisfy R005.
- `src/mcp_agent_factory/config/__init__.py` — **new file** (empty package init)
- `src/mcp_agent_factory/config/privacy.py` — **new file**; `PrivacyConfig(BaseModel)` with `local_only: bool = True`, `allow_egress: bool = False`, and `assert_no_egress()` raising `RuntimeError` if `allow_egress=True`. Satisfies R006.
- `tests/test_schema_validation.py` — **new file**; tests: missing required field → `isError=True`, wrong type → `isError=True`, valid input → correct result, `PrivacyConfig` defaults, `assert_no_egress()` on default config passes, `assert_no_egress()` on `allow_egress=True` raises.

### Build Order

1. `models.py` first — pure Pydantic, no dependencies; proves schema layer exists
2. `config/privacy.py` second — pure Pydantic, no dependencies
3. `server.py` edit — import `EchoInput`/`AddInput`, wrap `_call_tool` with `model_validate` + `ValidationError` catch
4. `tests/test_schema_validation.py` — drives all validation paths

### Verification Approach

```bash
python -m pytest tests/ -v
# All prior tests (12 lifecycle + react_loop + e2e) must still pass.
# New tests: schema rejection for missing fields, wrong types, privacy config defaults.
```

## Constraints

- Pydantic v2 only — use `@field_validator` not `@validator`; use `model_validate()` not `parse_obj()`
- `ValidationError` is `pydantic.ValidationError` — catch it, format with `str(exc)`, return as `isError=True` content block (Cap 3 pattern)
- `server.py` must NOT import `react_loop.py` or `orchestrator.py` — keep the dependency graph clean
- Privacy config is a pure data model — no network calls, no subprocess, no async; just a config value + assertion helper

## Common Pitfalls

- **`model_validate` vs `model_validate` dict** — pass raw dict from `arguments` directly: `EchoInput.model_validate(arguments)`. Do not use `EchoInput(**arguments)` — it bypasses Pydantic coercion.
- **`isError` must be on the outer result, not in the content text** — `{"content": [{"type": "text", "text": "..."}], "isError": True}` is the correct shape.
- **Don't add `config/` to `.gitignore` or skip `__init__.py`** — the package won't import without it.
