"""
Tests for the Analyst→Writer multi-agent pipeline.

Uses fakeredis.aioredis.FakeRedis as the Redis backend so tests
run without a real Redis instance.
"""
from __future__ import annotations

import json
import logging

import pytest
import fakeredis.aioredis

from mcp_agent_factory.agents.analyst import AnalystAgent
from mcp_agent_factory.agents.models import (
    AgentTask,
    AnalysisResult,
    MCPContext,
    ReportResult,
)
from mcp_agent_factory.agents.pipeline_orchestrator import MultiAgentOrchestrator
from mcp_agent_factory.agents.writer import WriterAgent
from mcp_agent_factory.session.manager import RedisSessionManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def session(fake_redis):
    return RedisSessionManager(fake_redis)


@pytest.fixture
def ctx():
    return MCPContext(tool_name="test")


@pytest.fixture
def sample_task():
    return AgentTask(
        name="sales_analysis",
        payload={"revenue": 150000.0, "costs": 90000.0, "units_sold": 320.0},
        complexity=0.7,
        required_capability="analysis",
    )


# ---------------------------------------------------------------------------
# AnalystAgent tests
# ---------------------------------------------------------------------------

class TestAnalystAgent:
    async def test_analyst_produces_analysis_result(self, sample_task, ctx):
        agent = AnalystAgent()
        result = await agent.run(sample_task, ctx)
        assert isinstance(result, AnalysisResult)
        assert result.session_key == sample_task.id

    async def test_analysis_result_metrics_extracted_from_payload(self, sample_task, ctx):
        agent = AnalystAgent()
        result = await agent.run(sample_task, ctx)
        assert "revenue" in result.metrics
        assert "costs" in result.metrics
        assert result.metrics["revenue"] == 150000.0

    async def test_analysis_result_has_trends(self, sample_task, ctx):
        agent = AnalystAgent()
        result = await agent.run(sample_task, ctx)
        assert len(result.trends) >= 1
        assert any("revenue" in t or "costs" in t or "units_sold" in t for t in result.trends)

    async def test_analysis_result_has_summary(self, sample_task, ctx):
        agent = AnalystAgent()
        result = await agent.run(sample_task, ctx)
        assert len(result.summary) > 10
        assert "sales_analysis" in result.summary

    async def test_analyst_logs_via_context(self, sample_task, ctx):
        agent = AnalystAgent()
        await agent.run(sample_task, ctx)
        assert len(ctx.trace) >= 2
        assert any("analyst" in t for t in ctx.trace)

    async def test_analyst_no_numeric_payload(self, ctx):
        task = AgentTask(name="text_task", payload={"note": "hello", "tag": "test"})
        agent = AnalystAgent()
        result = await agent.run(task, ctx)
        assert result.metrics == {}
        assert "No numeric metrics" in result.trends[0]


# ---------------------------------------------------------------------------
# WriterAgent tests
# ---------------------------------------------------------------------------

class TestWriterAgent:
    async def test_writer_produces_report_from_analysis(self, ctx):
        analysis = AnalysisResult(
            session_key="test-key",
            metrics={"revenue": 150000.0, "costs": 90000.0},
            trends=["'revenue' shows the highest value at 150000.00"],
            summary="Test summary.",
        )
        agent = WriterAgent()
        result = await agent.run(analysis, ctx)
        assert isinstance(result, ReportResult)
        assert result.session_key == "test-key"

    async def test_report_contains_summary(self, ctx):
        analysis = AnalysisResult(
            session_key="k1",
            metrics={"x": 1.0},
            trends=["trend A"],
            summary="Executive summary text.",
        )
        report = await WriterAgent().run(analysis, ctx)
        assert "Executive summary text." in report.report_text

    async def test_report_contains_trend_summary(self, ctx):
        analysis = AnalysisResult(
            session_key="k2",
            metrics={"a": 5.0},
            trends=["'a' shows the highest value at 5.00"],
            summary="Summary.",
        )
        report = await WriterAgent().run(analysis, ctx)
        assert "highest value" in report.report_text

    async def test_report_contains_metrics_table(self, ctx):
        analysis = AnalysisResult(
            session_key="k3",
            metrics={"revenue": 100.0},
            trends=["trend"],
            summary="s",
        )
        report = await WriterAgent().run(analysis, ctx)
        assert "revenue" in report.report_text
        assert "100.0000" in report.report_text

    async def test_writer_logs_via_context(self, ctx):
        analysis = AnalysisResult(session_key="k4", summary="s")
        await WriterAgent().run(analysis, ctx)
        assert any("writer" in t for t in ctx.trace)


# ---------------------------------------------------------------------------
# RedisSessionManager tests
# ---------------------------------------------------------------------------

class TestRedisSessionManager:
    async def test_set_and_get(self, session):
        await session.set("key1", {"result": 42, "name": "test"})
        result = await session.get("key1")
        assert result == {"result": 42, "name": "test"}

    async def test_get_missing_returns_none(self, session):
        result = await session.get("nonexistent")
        assert result is None

    async def test_delete(self, session):
        await session.set("key2", {"x": 1})
        await session.delete("key2")
        assert await session.get("key2") is None

    async def test_stores_handoff_data(self, session, sample_task, ctx):
        analysis = await AnalystAgent().run(sample_task, ctx)
        await session.set(analysis.session_key, analysis.model_dump())
        raw = await session.get(analysis.session_key)
        assert raw is not None
        restored = AnalysisResult(**raw)
        assert restored.session_key == sample_task.id
        assert restored.metrics == analysis.metrics


# ---------------------------------------------------------------------------
# MultiAgentOrchestrator tests
# ---------------------------------------------------------------------------

class TestMultiAgentOrchestrator:
    async def test_orchestrator_full_pipeline(self, session, sample_task, ctx):
        orch = MultiAgentOrchestrator(session)
        report = await orch.run_pipeline(sample_task, ctx)
        assert isinstance(report, ReportResult)
        assert len(report.report_text) > 50
        assert report.session_key == sample_task.id

    async def test_pipeline_report_contains_metrics(self, session, sample_task, ctx):
        orch = MultiAgentOrchestrator(session)
        report = await orch.run_pipeline(sample_task, ctx)
        assert "revenue" in report.report_text

    async def test_pipeline_logs_state_transitions(self, session, sample_task, ctx):
        orch = MultiAgentOrchestrator(session)
        await orch.run_pipeline(sample_task, ctx)
        trace_text = " ".join(ctx.trace)
        assert "orchestrator" in trace_text
        assert "analyst" in trace_text
        assert "writer" in trace_text

    async def test_mcp_context_logs_progress(self, session, sample_task, caplog):
        ctx = MCPContext(tool_name="pipeline")
        orch = MultiAgentOrchestrator(session)
        with caplog.at_level(logging.DEBUG, logger="mcp_agent_factory.agents.models"):
            await orch.run_pipeline(sample_task, ctx)
        log_messages = [r.message for r in caplog.records]
        parsed = [json.loads(m) for m in log_messages if m.startswith("{")]
        events = [p["event"] for p in parsed]
        assert "context_log" in events
        assert "context_progress" in events

    async def test_redis_handoff_data_persists_after_pipeline(self, session, sample_task, ctx):
        orch = MultiAgentOrchestrator(session)
        report = await orch.run_pipeline(sample_task, ctx)
        # Redis key should still exist after pipeline (not cleaned up)
        raw = await session.get(report.session_key)
        assert raw is not None
