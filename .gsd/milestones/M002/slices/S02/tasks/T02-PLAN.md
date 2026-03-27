---
estimated_steps: 17
estimated_files: 1
skills_used: []
---

# T02: LLM function-calling adapters (Claude, OpenAI, Gemini)

1. Create src/mcp_agent_factory/adapters.py
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

## Inputs

- `src/mcp_agent_factory/server_http.py`

## Expected Output

- `src/mcp_agent_factory/adapters.py`

## Verification

python -c "from mcp_agent_factory.adapters import LLMAdapterFactory; print('import ok')"
