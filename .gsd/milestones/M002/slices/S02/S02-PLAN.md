# S02: FastAPI HTTP MCP Server + LLM Adapters

**Goal:** Implement the FastAPI HTTP MCP server (POST /mcp endpoint, full JSON-RPC 2.0 lifecycle) and LLM adapter layer translating MCP tool descriptors into Claude/GPT/Gemini function-calling schemas.
**Demo:** After this: pytest tests/test_server_http.py tests/test_adapters.py -v passes — HTTP MCP lifecycle and Claude/GPT/Gemini adapter payloads verified.

## Tasks
- [x] **T01: FastAPI HTTP MCP server with POST /mcp endpoint (full JSON-RPC 2.0 lifecycle) and GET /health — PrivacyConfig wired at startup.** — 1. Create src/mcp_agent_factory/server_http.py
2. Define MCPRequest Pydantic model: jsonrpc (str='2.0'), method (str), params (dict|None=None), id (int|str|None=None)
3. Define MCPResponse Pydantic model: jsonrpc (str='2.0'), id (int|str|None), result (Any|None=None), error (dict|None=None)
4. Create FastAPI app with POST /mcp endpoint:
   - Accepts MCPRequest body
   - Delegates to _dispatch(request) — same dispatch logic as STDIO server but async
   - Returns MCPResponse
   - PrivacyConfig.assert_no_egress() called at startup (lifespan event)
5. _dispatch handles: initialize, initialized (204 no-content), tools/list, tools/call (uses EchoInput/AddInput model_validate, catches ValueError+ValidationError)
6. Observability: log each request/response as JSON line to stderr via logger.debug
7. Add GET /health endpoint returning {status: ok}
8. Do NOT modify server.py (M001 baseline)
  - Estimate: 25min
  - Files: src/mcp_agent_factory/server_http.py
  - Verify: python -c "from mcp_agent_factory.server_http import app; print('import ok')"
- [x] **T02: LLMAdapterFactory with Claude/OpenAI/Gemini adapters — schema translation only, tested with cross-adapter invariants.** — 1. Create src/mcp_agent_factory/adapters.py
2. Define base class LLMAdapter with method adapt(tools: list[dict]) -> Any
3. Implement ClaudeAdapter(LLMAdapter):
   - adapt() returns list of Anthropic tool dicts:
     {name, description, input_schema: {type, properties, required}}
   - Maps MCP tool inputSchema directly to input_schema
4. Implement OpenAIAdapter(LLMAdapter):
   - adapt() returns list of OpenAI tool dicts:
     {type: 'function', function: {name, description, parameters: {type, properties, required}}}
5. Implement GeminiAdapter(LLMAdapter):
   - adapt() returns list of Google function declarations:
     {name, description, parameters: {type: 'OBJECT', properties: {...}, required: [...]}}
   - Note: Gemini uses 'OBJECT' (uppercase) not 'object'
6. Implement LLMAdapterFactory with get(provider: str) -> LLMAdapter:
   - provider in {'claude', 'openai', 'gemini'}
   - raises ValueError on unknown provider
7. Log adapter output at DEBUG level
  - Estimate: 20min
  - Files: src/mcp_agent_factory/adapters.py
  - Verify: python -c "from mcp_agent_factory.adapters import LLMAdapterFactory; print('import ok')"
- [x] **T03: 34 tests for HTTP MCP server and all three LLM adapters — all passing in 2.33s.** — 1. Create tests/test_server_http.py using FastAPI TestClient (sync) or httpx.AsyncClient with ASGI transport
2. Test cases:
   - test_health: GET /health returns 200 {status: ok}
   - test_initialize: POST /mcp with initialize request returns protocolVersion, capabilities, serverInfo
   - test_tools_list: POST /mcp with tools/list returns list with echo and add
   - test_call_echo: POST /mcp with tools/call echo returns message text
   - test_call_add: POST /mcp with tools/call add returns sum as string
   - test_call_unknown_tool: POST /mcp with tools/call unknown returns isError=True
   - test_echo_missing_message: POST /mcp with tools/call echo missing message returns isError=True
   - test_add_wrong_type: POST /mcp with tools/call add wrong type returns isError=True
3. Create tests/test_adapters.py:
   - test_claude_adapter_shape: ClaudeAdapter.adapt(TOOLS) returns list with input_schema key
   - test_openai_adapter_shape: OpenAIAdapter.adapt(TOOLS) returns list with type='function' and function.parameters
   - test_gemini_adapter_shape: GeminiAdapter.adapt(TOOLS) returns list with parameters.type='OBJECT'
   - test_factory_claude/openai/gemini: LLMAdapterFactory.get(provider) returns correct adapter type
   - test_factory_unknown: LLMAdapterFactory.get('unknown') raises ValueError
   - test_adapter_preserves_tool_names: all adapters preserve tool name and description
   - test_adapter_required_fields: all adapters preserve required field list
  - Estimate: 25min
  - Files: tests/test_server_http.py, tests/test_adapters.py
  - Verify: python -m pytest tests/test_server_http.py tests/test_adapters.py -v
