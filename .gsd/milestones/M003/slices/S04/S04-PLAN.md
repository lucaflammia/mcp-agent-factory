# S04: MCP API Gateway + Sampling

**Goal:** Implement the MCP API Gateway FastAPI app with tool routing to internal agents, sampling/createMessage handler, auth protection, and SSE router mounted. Integrates all S01-S03 components.
**Demo:** After this: pytest tests/test_gateway.py -v passes — external tools/call routed to correct handler; sampling/createMessage returns stub LLM completion.

## Tasks
- [x] **T01: Created MCP API Gateway FastAPI app with tool routing, stub sampling handler, and SSE router mounted** — 1. Create src/mcp_agent_factory/gateway/__init__.py
2. Create src/mcp_agent_factory/gateway/sampling.py:
   - SamplingResult(BaseModel): prompt, completion (str), model (str='stub')
   - SamplingClient protocol: async def request_completion(prompt: str) -> SamplingResult
   - StubSamplingClient: implements SamplingClient, returns SamplingResult with completion='[stub] ' + prompt[:50]
   - SamplingHandler(client: SamplingClient): async handle(prompt: str) -> SamplingResult
3. Create src/mcp_agent_factory/gateway/app.py:
   - Imports: MessageBus, create_sse_router, MultiAgentOrchestrator, RedisSessionManager, Auction, MCPRequest, MCPResponse, make_verify_token, PrivacyConfig, lifespan from server_http
   - gateway_app = FastAPI(lifespan=lifespan)
   - Mount SSE router (create_sse_router(bus)) on gateway_app
   - POST /mcp with Depends(make_verify_token('tools:call')):
     - Routes tools/list → returns TOOLS list from server_http
     - Routes tools/call 'echo' → direct echo handler
     - Routes tools/call 'analyse_and_report' → runs MultiAgentOrchestrator.run_pipeline()
     - Routes tools/call 'sampling_demo' → SamplingHandler.handle()
     - Unknown tool → isError=True
   - POST /sampling (unauthenticated): body {prompt: str} -> SamplingResult
   - GET /health (unauthenticated)
   - Publish AgentMessage to bus on every tools/call
   - Module-level singletons: bus, sampling_handler, session
   - set_sampling_client(client) function for test injection
  - Estimate: 30min
  - Files: src/mcp_agent_factory/gateway/
  - Verify: python -c "from mcp_agent_factory.gateway.app import gateway_app; from mcp_agent_factory.gateway.sampling import SamplingHandler, StubSamplingClient; print('imports ok')"
- [x] **T02: Created 9 gateway tests covering auth, routing, sampling, SSE, and bus publish — all passing after fixing AgentMessage topic field in app.py** — 1. Create tests/test_gateway.py
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
  - Estimate: 25min
  - Files: tests/test_gateway.py
  - Verify: python -m pytest tests/test_gateway.py -v
