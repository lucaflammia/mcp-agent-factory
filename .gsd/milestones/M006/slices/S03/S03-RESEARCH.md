# S03 Research: Validation Gate + Internal Service Layer

## Summary

S03 is straightforward. The insertion points are well-defined, the existing patterns are clear, and the work is additive — no existing code is deleted. The two deliverables are:

1. **`ValidationGate`** — a thin Pydantic v2 wrapper that validates tool-call argument dicts before they reach business logic
2. **`InternalServiceLayer`** — extracts the tool-dispatch `if` blocks from `_mcp_dispatch` into a discrete class, leaving `_mcp_dispatch` as a thin router

Tests in `tests/test_m006_gateway.py` must prove: malformed payload blocked → structured error; valid payload dispatched; existing `test_gateway.py` still passes.

## Target Requirements

- **R006** — InternalServiceLayer extracted from gateway `_mcp_dispatch`; new tools can be added without touching routing logic
- **R007** — ValidationGate blocks malformed agent output with a structured error; passes valid payloads through

## Implementation Landscape

### Existing gateway: `src/mcp_agent_factory/gateway/app.py`

`_mcp_dispatch` contains the full tool-dispatch logic inline as a chain of `if tool_name ==` blocks. The target function signature is `async def _mcp_dispatch(req: MCPRequest, _claims: dict | None) -> MCPResponse`.

**Current tool handlers in `_mcp_dispatch`:**
- `echo` — trivial passthrough
- `add` — uses `AddInput(**args)` from `src/mcp_agent_factory/models.py`; result formatted as int if whole number
- `analyse_and_report` — spins up `MultiAgentOrchestrator`, runs pipeline
- `sampling_demo` — calls `sampling_handler.handle(prompt)`
- `query_knowledge_base` — calls `query_knowledge_base()` from knowledge module

**Existing Pydantic models** (`src/mcp_agent_factory/models.py`):
- `AddInput(a: float, b: float)`, `EchoInput(message: str)`, `EchoOutput(text: str)`, `AddOutput(result: float)`
- Note: gateway currently uses `AddInput` but NOT `EchoInput` — echo just reads `args.get("text", "")` with no validation

**Bug in current gateway code** (don't break, just note):
- Line 190: `AgentTask(task_id=..., description=...)` — `AgentTask` has no `task_id` or `description` fields; it has `id` and `name`. This is a pre-existing bug; don't fix or worsen it during S03.
- Line 194: `MCPContext(session_id=...)` — `MCPContext` is a dataclass with `tool_name` field, not `session_id`. Same pre-existing bug.

### New modules to create

**`src/mcp_agent_factory/gateway/validation.py`**

```python
# ValidationGate wraps Pydantic model validation
# validate(model_class, data: dict) -> model_instance  (raises ValidationError on bad input)
```

The gate is simple: take a Pydantic model class and a raw dict, call `model_class(**data)`, and let `ValidationError` propagate. The caller (`_mcp_dispatch` or `InternalServiceLayer`) catches it and converts to a structured MCP error response.

**`src/mcp_agent_factory/gateway/service_layer.py`**

```python
# InternalServiceLayer holds tool handler methods
# async def handle(tool_name, args, claims) -> dict  (returns result dict or raises)
```

Extract the `if tool_name ==` blocks from `_mcp_dispatch` into methods on `InternalServiceLayer`. The service layer is injected as a module-level singleton in `app.py` (same pattern as `bus`, `session`, `sampling_handler`).

### Insertion point in `_mcp_dispatch`

Replace the `if tool_name == "echo":` ... `# Unknown tool` block with:

```python
try:
    result = await _service_layer.handle(tool_name, args, _claims)
    return _ok(req_id, result)
except ValidationError as e:
    return _ok(req_id, {"isError": True, "content": [{"type": "text", "text": str(e)}]})
except Exception as e:
    return _err(req_id, -32603, str(e))
```

### Test file: `tests/test_m006_gateway.py`

Three scenarios:
1. **Malformed payload blocked** — call `add` with `{"a": "not-a-number", "b": 2}` → response has `isError: True`
2. **Valid payload dispatched** — call `add` with `{"a": 3, "b": 4}` → response has text `"7"`
3. **Existing gateway test passes** — just run `test_gateway.py`; the new test file imports `gateway_app` and uses `TestClient`

### Important: existing `test_gateway.py` compatibility

`test_gateway.py` uses `TestClient(gateway_app)` with `MCP_DEV_MODE=1` (or jwt tokens). The `_mcp_dispatch` refactor must not change external behavior for any existing test. The only behavioral change is that previously-unvalidated tool args now get Pydantic-validated before dispatch.

**Echo special case**: current echo uses `args.get("text", "")` with no `EchoInput` validation. To avoid breaking existing gateway tests that call `echo` with `{"text": "hi"}`, either:
- Keep echo validation-free (acceptable — R007 only requires the gate exists and is used for *some* tool)
- Or use `EchoInput` but note that `EchoInput` has field `message`, not `text` — so it would break existing tests

**Safe choice**: validate `add` (which already uses `AddInput`), validate `analyse_and_report` with a new `AnalyseAndReportInput`, leave `echo` unvalidated or create `EchoInput` with field `text` (not `message`).

### Note on `EchoInput` field name mismatch

`models.py` defines `EchoInput(message: str)` but the echo handler reads `args.get("text", "")`. These are inconsistent. If ValidationGate is applied to echo using existing `EchoInput`, it will break existing echo calls. **Do not validate echo with existing `EchoInput`.** Either skip echo validation or create a new `EchoCallInput(text: str)` model. The simplest correct approach: only validate `add` in the gate for the test requirement.

## Recommendation

Single task T01:

1. Create `src/mcp_agent_factory/gateway/validation.py` — `ValidationGate` class with `validate(model_cls, data)` method
2. Create `src/mcp_agent_factory/gateway/service_layer.py` — `InternalServiceLayer` with `async handle(tool_name, args, claims) -> dict`; move all tool handler blocks here; call `ValidationGate.validate` for `add` (and optionally other tools)
3. Edit `src/mcp_agent_factory/gateway/app.py` — replace inline tool-dispatch block with `await _service_layer.handle(...)`, catch `ValidationError`
4. Write `tests/test_m006_gateway.py` — malformed `add` args → `isError: True`; valid `add` args → `"7"`; any existing gateway tests not broken

## File Map

| File | Action | Notes |
|------|--------|-------|
| `src/mcp_agent_factory/gateway/validation.py` | **CREATE** | `ValidationGate` |
| `src/mcp_agent_factory/gateway/service_layer.py` | **CREATE** | `InternalServiceLayer` |
| `src/mcp_agent_factory/gateway/app.py` | **EDIT** | Wire service layer + gate into `_mcp_dispatch` |
| `tests/test_m006_gateway.py` | **CREATE** | 3 tests for R006/R007 |
| `src/mcp_agent_factory/gateway/__init__.py` | **EDIT** (maybe) | Export new classes if needed |

## Verification Command

```
pytest tests/test_m006_gateway.py tests/test_gateway.py -v
```

Expected: all pass (test_m006_gateway: 2–3 new tests; test_gateway: existing suite unchanged).
