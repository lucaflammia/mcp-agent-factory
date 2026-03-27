---
estimated_steps: 21
estimated_files: 2
skills_used: []
---

# T02: MultiAgentOrchestrator and pipeline tests

1. Create src/mcp_agent_factory/agents/pipeline_orchestrator.py:
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

## Inputs

- `src/mcp_agent_factory/agents/analyst.py`
- `src/mcp_agent_factory/agents/writer.py`
- `src/mcp_agent_factory/session/manager.py`

## Expected Output

- `src/mcp_agent_factory/agents/pipeline_orchestrator.py`
- `tests/test_pipeline.py`

## Verification

python -m pytest tests/test_pipeline.py -v
