"""
M010 S02 — AnalystAgent.analyze_document() pipeline tests.

All LLM and PDF calls are mocked — tests are fully offline.
"""
from __future__ import annotations

import os
import unittest.mock as mock

import pytest

from mcp_agent_factory.agents.analyst import (
	AnalystAgent,
	DocumentAnalysisResult,
	DocumentAnalysisTask,
)
from mcp_agent_factory.agents.models import MCPContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx():
	return MCPContext(tool_name="test_analyze_document")


@pytest.fixture
def sample_pdf(tmp_path):
	"""Create a minimal real PDF using pypdf."""
	pytest.importorskip("pypdf")
	from pypdf import PdfWriter
	writer = PdfWriter()
	writer.add_blank_page(width=612, height=792)
	pdf_path = tmp_path / "test_report.pdf"
	with open(pdf_path, "wb") as f:
		writer.write(f)
	return str(pdf_path)


@pytest.fixture
def sample_pdf_with_text(tmp_path):
	"""Create a PDF with real extractable text using pypdf."""
	pytest.importorskip("pypdf")
	from pypdf import PdfWriter
	writer = PdfWriter()
	writer.add_blank_page(width=612, height=792)
	pdf_path = tmp_path / "report.pdf"
	with open(pdf_path, "wb") as f:
		writer.write(f)
	return str(pdf_path)


@pytest.fixture
def mock_llm_response():
	return {
		"content": "KPIs: Revenue $5.2M (+12% YoY), EBITDA 18%\nRisks: Supply chain disruptions\nSummary: Solid Q3 performance.",
		"model": "claude-3-5-sonnet-20241022",
		"input_tokens": 120,
		"output_tokens": 45,
		"cost_usd": 0.002,
	}


# ---------------------------------------------------------------------------
# Core pipeline tests
# ---------------------------------------------------------------------------

class TestAnalyzeDocument:
	async def test_returns_document_analysis_result(self, sample_pdf, mock_llm_response, monkeypatch):
		monkeypatch.setenv("LLM_PROVIDER", "anthropic")
		router_mock = mock.AsyncMock()
		router_mock.route = mock.AsyncMock(return_value=mock_llm_response)
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			agent = AnalystAgent()
			task = DocumentAnalysisTask(pdf_path=sample_pdf, query="Find KPIs and risks")
			result = await agent.analyze_document(task)
		assert isinstance(result, DocumentAnalysisResult)

	async def test_summary_comes_from_llm(self, sample_pdf, mock_llm_response, monkeypatch):
		monkeypatch.setenv("LLM_PROVIDER", "anthropic")
		router_mock = mock.AsyncMock()
		router_mock.route = mock.AsyncMock(return_value=mock_llm_response)
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			agent = AnalystAgent()
			task = DocumentAnalysisTask(pdf_path=sample_pdf)
			result = await agent.analyze_document(task)
		assert result.summary == mock_llm_response["content"]

	async def test_token_counts_surfaced(self, sample_pdf, mock_llm_response, monkeypatch):
		router_mock = mock.AsyncMock()
		router_mock.route = mock.AsyncMock(return_value=mock_llm_response)
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			agent = AnalystAgent()
			result = await agent.analyze_document(DocumentAnalysisTask(pdf_path=sample_pdf))
		assert result.input_tokens == 120
		assert result.output_tokens == 45

	async def test_pages_read_reported(self, sample_pdf, mock_llm_response, monkeypatch):
		router_mock = mock.AsyncMock()
		router_mock.route = mock.AsyncMock(return_value=mock_llm_response)
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			agent = AnalystAgent()
			result = await agent.analyze_document(DocumentAnalysisTask(pdf_path=sample_pdf))
		assert result.total_pages >= 1
		assert result.pages_read >= 1

	async def test_raises_file_not_found(self, monkeypatch):
		router_mock = mock.AsyncMock()
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			agent = AnalystAgent()
			task = DocumentAnalysisTask(pdf_path="/nonexistent/path/report.pdf")
			with pytest.raises(FileNotFoundError):
				await agent.analyze_document(task)

	async def test_ctx_logs_progress(self, sample_pdf, mock_llm_response, ctx, monkeypatch):
		router_mock = mock.AsyncMock()
		router_mock.route = mock.AsyncMock(return_value=mock_llm_response)
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			agent = AnalystAgent()
			await agent.analyze_document(DocumentAnalysisTask(pdf_path=sample_pdf), ctx=ctx)
		assert any("analyst" in t for t in ctx.trace)
		assert any("PDF" in t or "pdf" in t for t in ctx.trace)

	async def test_provider_changes_with_env_var(self, sample_pdf, monkeypatch):
		"""Verifies provider_factory is called each time (live switching)."""
		calls = []

		async def _mock_route(req):
			calls.append(os.environ.get("LLM_PROVIDER", "anthropic"))
			return {
				"content": "ok",
				"model": "test",
				"input_tokens": 5,
				"output_tokens": 5,
				"cost_usd": 0.0,
			}

		monkeypatch.setenv("LLM_PROVIDER", "anthropic")
		router_mock = mock.AsyncMock()
		router_mock.route = mock.AsyncMock(side_effect=_mock_route)
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			agent = AnalystAgent()
			await agent.analyze_document(DocumentAnalysisTask(pdf_path=sample_pdf))

		monkeypatch.setenv("LLM_PROVIDER", "gemini")
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			await agent.analyze_document(DocumentAnalysisTask(pdf_path=sample_pdf))

		assert calls[0] == "anthropic"
		assert calls[1] == "gemini"

	async def test_prune_stats_in_result(self, sample_pdf_with_text, mock_llm_response, monkeypatch):
		router_mock = mock.AsyncMock()
		router_mock.route = mock.AsyncMock(return_value=mock_llm_response)
		with mock.patch(
			"mcp_agent_factory.agents.analyst.provider_factory",
			return_value=router_mock,
		):
			agent = AnalystAgent()
			result = await agent.analyze_document(
				DocumentAnalysisTask(pdf_path=sample_pdf_with_text)
			)
		assert result.chunks_before_pruning >= 0
		assert result.chunks_after_pruning >= 0
