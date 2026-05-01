# S01: agents/analyze Dispatch

**Goal:** Add agents/analyze JSON-RPC method to the gateway with _agents_dispatch() sub-router, provider-not-configured validation, and a contract test covering response shape and both error codes.
**Demo:** curl to :8000/mcp with agents/analyze returns a real DocumentAnalysisResult; contract test green validating -32602 on missing provider key and -32603 on pipeline failure

## Must-Haves

- curl POST /mcp with agents/analyze and MCP_DEV_MODE=1 returns DocumentAnalysisResult fields; -32602 returned when explicitly requested provider lacks an API key; -32603 returned on pipeline failure; contract test green.

## Proof Level

- This slice proves: Not provided.

## Integration Closure

Not provided.

## Verification

- Not provided.

## Tasks

- [x] **T01: Add ProviderNotConfiguredError and provider key validation** `est:15m`
  Add a ProviderNotConfiguredError exception class and a _validate_provider() function in gateway/app.py that checks the API key env var for explicitly requested providers (openai→OPENAI_API_KEY, anthropic→ANTHROPIC_API_KEY, gemini→GEMINI_API_KEY) and raises the error if missing. ollama needs no key — never raises.
  - Files: `src/mcp_agent_factory/gateway/app.py`
  - Verify: Unit test: _validate_provider('openai') with no OPENAI_API_KEY set raises ProviderNotConfiguredError; _validate_provider('ollama') never raises.

- [x] **T02: Implement _agents_dispatch() and wire into _mcp_dispatch_inner()** `est:30m`
  Add _agents_dispatch() function in gateway/app.py that handles agents/analyze: validates provider config, builds DocumentAnalysisTask from params, calls AnalystAgent().analyze_document(), and returns a JSON-serializable result dict. Wire it via elif method.startswith('agents/') in _mcp_dispatch_inner(). agents/analyze requires auth (same as tools/call). Unknown agents/* methods return -32601.
  - Files: `src/mcp_agent_factory/gateway/app.py`
  - Verify: Sending agents/analyze via TestClient with MCP_DEV_MODE=1 returns a result with summary, provider, input_tokens, output_tokens fields.

- [x] **T03: Write contract test for agents/analyze dispatch** `est:30m`
  Create tests/test_agents_dispatch.py with three test cases: (1) happy path — monkeypatch AnalystAgent.analyze_document to return a stub DocumentAnalysisResult, verify response has result dict with correct fields; (2) -32602 — set LLM_PROVIDER=openai with no OPENAI_API_KEY, verify error code -32602 and message names the key; (3) -32603 — monkeypatch analyze_document to raise RuntimeError, verify error code -32603. All tests use MCP_DEV_MODE=1.
  - Files: `tests/test_agents_dispatch.py`
  - Verify: pytest tests/test_agents_dispatch.py -v → 3 tests green

## Files Likely Touched

- src/mcp_agent_factory/gateway/app.py
- tests/test_agents_dispatch.py
