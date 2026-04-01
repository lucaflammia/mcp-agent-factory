# S03: Validation Gate + Internal Service Layer

**Goal:** Insert a Pydantic ValidationGate and extract an InternalServiceLayer from gateway _mcp_dispatch, so the routing logic is a thin delegator and malformed tool arguments are caught with structured errors.
**Demo:** After this: pytest tests/test_m006_gateway.py -v passes — malformed payload blocked; valid payload dispatched; existing test_gateway.py still passes

## Tasks
- [x] **T01: Add ValidationGate + InternalServiceLayer, refactor _mcp_dispatch to delegate, all 12 tests pass** — Create two new gateway modules, refactor _mcp_dispatch to delegate to the service layer, and write tests/test_m006_gateway.py proving R006 and R007.

Detailed steps:
1. Create `src/mcp_agent_factory/gateway/validation.py` with a `ValidationGate` class that has a single method `validate(model_cls, data: dict)` which calls `model_cls(**data)` and lets Pydantic `ValidationError` propagate to the caller.
2. Create `src/mcp_agent_factory/gateway/service_layer.py` with `InternalServiceLayer`. It receives `bus`, `session`, `sampling_handler`, `_vector_store`, `_embedder` in `__init__`. It has `async def handle(tool_name: str, args: dict, claims: dict | None) -> dict` which mirrors the current `if tool_name ==` block logic. For the `add` tool, call `ValidationGate().validate(AddInput, args)` before computing the result — let `ValidationError` propagate. For all other tools, keep the existing logic unchanged. Raise `ValueError(f"Unknown tool: {tool_name}")` at the end instead of returning an error dict (the caller in app.py will convert exceptions to structured responses).
3. Edit `src/mcp_agent_factory/gateway/app.py`: import `InternalServiceLayer` and `ValidationError` (from pydantic). Add `_service_layer = InternalServiceLayer(bus, session, sampling_handler, _vector_store, _embedder)` after the existing module-level singletons. Replace the `if tool_name == "echo":` ... `# Unknown tool` block inside `_mcp_dispatch` with:
```python
try:
    result = await _service_layer.handle(tool_name, args, _claims)
    return _ok(req_id, result)
except (ValidationError, ValueError) as e:
    return _ok(req_id, {"isError": True, "content": [{"type": "text", "text": str(e)}]})
except Exception as e:
    return _err(req_id, -32603, str(e))
```
4. Write `tests/test_m006_gateway.py` using `from fastapi.testclient import TestClient` and `from mcp_agent_factory.gateway.app import gateway_app`. Set `MCP_DEV_MODE=1` via monkeypatch or module-level env (use `os.environ` before import or a `pytest.fixture` with `monkeypatch.setenv`). Write three tests:
   - `test_malformed_add_blocked`: POST /mcp with `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"add","arguments":{"a":"not-a-number","b":2}}}` → response body `result.isError == True`
   - `test_valid_add_dispatched`: POST /mcp with `{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"add","arguments":{"a":3,"b":4}}}` → response body `result.content[0].text == "7"`
   - `test_existing_gateway_tests_pass`: just import and assert len(TOOLS) > 0 (smoke), or simply let the test file exist and rely on running test_gateway.py in the same pytest invocation.

IMPORTANT constraints:
- Do NOT validate echo with the existing `EchoInput(message: str)` — it would break existing echo tests which pass `{"text": "..."}`.
- The pre-existing bugs on lines 190/194 (AgentTask/MCPContext field mismatches) must not be touched.
- The module-level singleton `_service_layer` must be instantiated AFTER `bus`, `session`, `sampling_handler`, `_vector_store`, `_embedder` are defined — check order in app.py.
- For `test_m006_gateway.py`, set `MCP_DEV_MODE=1` before importing gateway_app to bypass JWT auth, or use a module-level `os.environ["MCP_DEV_MODE"] = "1"` at top of file (before any gateway imports).
  - Estimate: 45m
  - Files: src/mcp_agent_factory/gateway/validation.py, src/mcp_agent_factory/gateway/service_layer.py, src/mcp_agent_factory/gateway/app.py, tests/test_m006_gateway.py
  - Verify: cd /home/luca/Documents/Misc/mcp-agent-factory/.gsd/worktrees/M006 && MCP_DEV_MODE=1 pytest tests/test_m006_gateway.py tests/test_gateway.py -v
