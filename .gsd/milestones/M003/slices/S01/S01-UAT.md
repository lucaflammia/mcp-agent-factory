# S01: Specialized Agent Pipeline (Analyst→Writer) — UAT

**Milestone:** M003
**Written:** 2026-03-27T10:47:21.864Z

## UAT: Agent Pipeline\n\n```python\nimport asyncio, fakeredis.aioredis\nfrom mcp_agent_factory.agents.models import AgentTask, MCPContext\nfrom mcp_agent_factory.agents.pipeline_orchestrator import MultiAgentOrchestrator\nfrom mcp_agent_factory.session.manager import RedisSessionManager\n\nasync def main():\n    redis = fakeredis.aioredis.FakeRedis()\n    session = RedisSessionManager(redis)\n    orch = MultiAgentOrchestrator(session)\n    ctx = MCPContext(tool_name=\"demo\")\n    task = AgentTask(\n        name=\"quarterly_report\",\n        payload={\"revenue\": 500000, \"costs\": 320000, \"profit\": 180000},\n    )\n    report = await orch.run_pipeline(task, ctx)\n    print(report.report_text)\n    print(\"\\nTrace:\", ctx.trace)\n\nasyncio.run(main())\n```\n\nExpected: markdown report with metrics table and trend observations.
