# S01: Specialized Agent Pipeline (Analyst→Writer)

**Goal:** Implement AnalystAgent, WriterAgent, MultiAgentOrchestrator, and RedisSessionManager. Establish the structured handoff: Analyst produces AnalysisResult stored in Redis; Orchestrator reads it and passes to Writer. MCP Context logs progress at each step.
**Demo:** After this: pytest tests/test_pipeline.py -v passes — MultiAgentOrchestrator coordinates Analyst→Writer handoff via Redis session; MCP Context logs progress at each step.

## Tasks
- [x] **T01: AgentTask/AnalysisResult/ReportResult models, MCPContext observability primitive, AnalystAgent, WriterAgent, and RedisSessionManager implemented.** — 1. Create src/mcp_agent_factory/agents/__init__.py
2. Create src/mcp_agent_factory/session/__init__.py
3. Define shared models in src/mcp_agent_factory/agents/models.py:
   - AgentTask(BaseModel): id (uuid4), name, payload (dict), complexity (float 0-1), required_capability (str)
   - AnalysisResult(BaseModel): session_key, metrics (dict[str,float]), trends (list[str]), summary (str)
   - ReportResult(BaseModel): session_key, report_text, agent_trace (list[str])
   - MCPContext: plain dataclass with log(msg), report_progress(pct, msg) methods that emit JSON log lines via logging.DEBUG
4. Create src/mcp_agent_factory/session/manager.py:
   - RedisSessionManager(redis_client): async set(key, value: dict), get(key) -> dict|None, delete(key)
   - Serializes values as JSON strings
   - Accepts any redis client (real or fakeredis)
5. Create src/mcp_agent_factory/agents/analyst.py:
   - AnalystAgent.run(task: AgentTask, ctx: MCPContext) -> AnalysisResult
   - ctx.log('analyst: starting') at start
   - ctx.report_progress(0.5, 'extracting metrics')
   - Extracts numeric values from task.payload as metrics, generates 2 trend strings
   - ctx.report_progress(1.0, 'complete')
   - Returns AnalysisResult with session_key=task.id
6. Create src/mcp_agent_factory/agents/writer.py:
   - WriterAgent.run(analysis: AnalysisResult, ctx: MCPContext) -> ReportResult
   - ctx.log('writer: generating report')
   - Produces a formatted report_text from analysis.metrics + analysis.trends
   - Returns ReportResult with agent_trace logging
  - Estimate: 30min
  - Files: src/mcp_agent_factory/agents/, src/mcp_agent_factory/session/
  - Verify: python -c "from mcp_agent_factory.agents.analyst import AnalystAgent; from mcp_agent_factory.agents.writer import WriterAgent; from mcp_agent_factory.session.manager import RedisSessionManager; print('imports ok')"
- [x] **T02: MultiAgentOrchestrator with Redis handoff proven by 20 passing pipeline tests.** — 1. Create src/mcp_agent_factory/agents/pipeline_orchestrator.py:
   - MultiAgentOrchestrator(session: RedisSessionManager):
     - async run_pipeline(task: AgentTask, ctx: MCPContext) -> ReportResult
     - Step 1: ctx.log('orchestrator: starting pipeline')
     - Step 2: analyst = AnalystAgent(); result = await analyst.run(task, ctx) [make run async]
     - Step 3: await session.set(result.session_key, result.model_dump())
     - Step 4: ctx.log('orchestrator: handoff to writer')
     - Step 5: raw = await session.get(result.session_key); analysis = AnalysisResult(**raw)
     - Step 6: writer = WriterAgent(); report = await writer.run(analysis, ctx)
     - Step 7: ctx.log('orchestrator: pipeline complete')
     - Returns report
2. Make AnalystAgent.run and WriterAgent.run async (async def)
3. Create tests/test_pipeline.py with fakeredis:
   - Fixture: fakeredis.aioredis.FakeRedis() injected into RedisSessionManager
   - test_analyst_produces_analysis_result
   - test_writer_produces_report_from_analysis
   - test_redis_stores_handoff_data
   - test_orchestrator_full_pipeline
   - test_mcp_context_logs_progress (caplog verifies JSON log lines)
   - test_analysis_result_metrics_extracted_from_payload
   - test_report_contains_trend_summary
  - Estimate: 25min
  - Files: src/mcp_agent_factory/agents/pipeline_orchestrator.py, tests/test_pipeline.py
  - Verify: python -m pytest tests/test_pipeline.py -v
