---
estimated_steps: 23
estimated_files: 2
skills_used: []
---

# T01: Agent models, MCPContext, AnalystAgent, WriterAgent, RedisSessionManager

1. Create src/mcp_agent_factory/agents/__init__.py
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

## Inputs

- `src/mcp_agent_factory/react_loop.py`
- `src/mcp_agent_factory/scheduler.py`

## Expected Output

- `src/mcp_agent_factory/agents/__init__.py`
- `src/mcp_agent_factory/agents/models.py`
- `src/mcp_agent_factory/agents/analyst.py`
- `src/mcp_agent_factory/agents/writer.py`
- `src/mcp_agent_factory/session/__init__.py`
- `src/mcp_agent_factory/session/manager.py`

## Verification

python -c "from mcp_agent_factory.agents.analyst import AnalystAgent; from mcp_agent_factory.agents.writer import WriterAgent; from mcp_agent_factory.session.manager import RedisSessionManager; print('imports ok')"
