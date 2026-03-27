---
estimated_steps: 18
estimated_files: 2
skills_used: []
---

# T03: Tests for HTTP server and adapters

1. Create tests/test_server_http.py using FastAPI TestClient (sync) or httpx.AsyncClient with ASGI transport
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

## Inputs

- `src/mcp_agent_factory/server_http.py`
- `src/mcp_agent_factory/adapters.py`

## Expected Output

- `tests/test_server_http.py`
- `tests/test_adapters.py`

## Verification

python -m pytest tests/test_server_http.py tests/test_adapters.py -v
