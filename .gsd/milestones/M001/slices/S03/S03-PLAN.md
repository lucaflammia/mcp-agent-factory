# S03: Schema Validation and Privacy-First Config

**Goal:** Add Pydantic v2 schema validation for all tool arguments and a PrivacyConfig module with local-only defaults, wiring both into the existing server so invalid inputs return isError=True without breaking the 12 passing lifecycle tests.
**Demo:** After this: pytest tests/ -v passes in full, including schema rejection and privacy flag tests.

## Tasks
- [x] **T01: Created Pydantic v2 I/O models and PrivacyConfig with local-only defaults and egress guard** — Create two pure Pydantic v2 modules with no external dependencies beyond pydantic.

Steps:
1. Create `src/mcp_agent_factory/models.py` — define `EchoInput(BaseModel)` with `message: str`, `EchoOutput(BaseModel)` with `text: str`, `AddInput(BaseModel)` with `a: float` and `b: float`, `AddOutput(BaseModel)` with `result: float`. Use standard Pydantic v2 `BaseModel` subclasses.
2. Create `src/mcp_agent_factory/config/__init__.py` — empty file to make config a Python package.
3. Create `src/mcp_agent_factory/config/privacy.py` — define `PrivacyConfig(BaseModel)` with `local_only: bool = True` and `allow_egress: bool = False`. Add `assert_no_egress(self) -> None` method that raises `RuntimeError('Egress is disabled by PrivacyConfig')` if `self.allow_egress is True`.
4. Verify imports work: `python -c "from mcp_agent_factory.models import EchoInput, AddInput; from mcp_agent_factory.config.privacy import PrivacyConfig; print('ok')"`
  - Estimate: 20m
  - Files: src/mcp_agent_factory/models.py, src/mcp_agent_factory/config/__init__.py, src/mcp_agent_factory/config/privacy.py
  - Verify: python -c "from mcp_agent_factory.models import EchoInput, AddInput, EchoOutput, AddOutput; from mcp_agent_factory.config.privacy import PrivacyConfig; print('ok')"
- [x] **T02: Wired Pydantic v2 model_validate into server.py and wrote 8 schema/privacy tests; all 31 tests pass.** — Import the new models into server.py, validate arguments before dispatch, and write tests proving rejection and acceptance behaviour.

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
  - Estimate: 40m
  - Files: src/mcp_agent_factory/server.py, tests/test_schema_validation.py
  - Verify: python -m pytest tests/ -v 2>&1 | tail -5
