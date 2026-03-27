---
estimated_steps: 12
estimated_files: 1
skills_used: []
---

# T02: Gateway tests

1. Create tests/test_gateway.py
2. Use autouse shared_key fixture pattern from test_auth.py
3. Test cases:
   - test_health_unauthenticated: GET /health → 200
   - test_mcp_no_auth_returns_401: POST /mcp without token → 401
   - test_tools_list_authenticated: tools/list with valid token → 200 + tools list
   - test_call_echo_authenticated: tools/call echo with valid token → correct response
   - test_call_unknown_tool_returns_is_error: unknown tool → isError=True
   - test_sampling_endpoint: POST /sampling {prompt} → SamplingResult with completion
   - test_sampling_stub_returns_prompt_prefix: completion starts with '[stub]'
   - test_sse_route_registered: /events route exists on gateway_app
   - test_gateway_publishes_message_on_tool_call: after tools/call, bus has message in queue

## Inputs

- `src/mcp_agent_factory/gateway/app.py`
- `src/mcp_agent_factory/gateway/sampling.py`

## Expected Output

- `tests/test_gateway.py`

## Verification

python -m pytest tests/test_gateway.py -v
