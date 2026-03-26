---
estimated_steps: 19
estimated_files: 2
skills_used: []
---

# T02: Wire validation into server.py and write schema tests

Import the new models into server.py, validate arguments before dispatch, and write tests proving rejection and acceptance behaviour.

Steps:
1. Edit `src/mcp_agent_factory/server.py` — add imports at the top: `from pydantic import ValidationError` and `from mcp_agent_factory.models import EchoInput, AddInput`.
2. In `_call_tool()`, replace bare dict access with model_validate:
   - For echo: `validated = EchoInput.model_validate(arguments)` then use `validated.message`.
   - For add: `validated = AddInput.model_validate(arguments)` then use `validated.a + validated.b`.
   - Wrap each validate call in try/except ValidationError and re-raise as ValueError with `str(exc)` so the existing ValueError handler in `_dispatch` returns isError=True.
   - Actually: since _dispatch already catches ValueError → isError=True, just let ValidationError propagate as-is OR catch it separately. Cleanest: catch `ValidationError` in `_dispatch`'s tools/call block alongside the existing `except ValueError`, same handling.
3. Create `tests/test_schema_validation.py` with these test cases:
   - `test_echo_missing_message` — call echo with `{}` → response has `isError: True`
   - `test_echo_valid` — call echo with `{"message": "hi"}` → isError False, text == "hi"
   - `test_add_missing_field` — call add with `{"a": 1}` (missing b) → isError True
   - `test_add_wrong_type` — call add with `{"a": "notanumber", "b": 2}` → isError True (Pydantic will coerce string digits but reject pure non-numeric)
   - `test_add_valid` — call add with `{"a": 3, "b": 4}` → isError False, text == "7"
   - `test_privacy_config_defaults` — `PrivacyConfig()` has `local_only=True`, `allow_egress=False`
   - `test_assert_no_egress_passes_on_default` — `PrivacyConfig().assert_no_egress()` does not raise
   - `test_assert_no_egress_raises_when_enabled` — `PrivacyConfig(allow_egress=True).assert_no_egress()` raises RuntimeError
4. Tests calling the server should use the existing `mcp_server` fixture from conftest.py and `MCPOrchestrator` to call tools (same pattern as test_mcp_lifecycle.py).
5. Run `python -m pytest tests/ -v` — all tests must pass.

## Inputs

- ``src/mcp_agent_factory/models.py``
- ``src/mcp_agent_factory/config/privacy.py``
- ``src/mcp_agent_factory/server.py``
- ``tests/conftest.py``
- ``tests/test_mcp_lifecycle.py``

## Expected Output

- ``src/mcp_agent_factory/server.py``
- ``tests/test_schema_validation.py``

## Verification

python -m pytest tests/ -v 2>&1 | tail -5
