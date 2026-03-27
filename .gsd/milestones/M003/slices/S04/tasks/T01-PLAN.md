---
estimated_steps: 21
estimated_files: 1
skills_used: []
---

# T01: Gateway app, sampling handler, tool routing

1. Create src/mcp_agent_factory/gateway/__init__.py
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

## Inputs

- `src/mcp_agent_factory/agents/pipeline_orchestrator.py`
- `src/mcp_agent_factory/economics/auction.py`
- `src/mcp_agent_factory/messaging/bus.py`
- `src/mcp_agent_factory/messaging/sse_router.py`
- `src/mcp_agent_factory/server_http.py`
- `src/mcp_agent_factory/auth/resource.py`

## Expected Output

- `src/mcp_agent_factory/gateway/__init__.py`
- `src/mcp_agent_factory/gateway/sampling.py`
- `src/mcp_agent_factory/gateway/app.py`

## Verification

python -c "from mcp_agent_factory.gateway.app import gateway_app; from mcp_agent_factory.gateway.sampling import SamplingHandler, StubSamplingClient; print('imports ok')"
