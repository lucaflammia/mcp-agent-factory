"""
M010 S01 — GeminiHandler and provider_factory unit tests.

Tests are fully offline — no real HTTP calls made.
GeminiHandler.call() is exercised via httpx.MockTransport.
provider_factory() is verified by checking handler ordering from LLM_PROVIDER env var.
"""
from __future__ import annotations

import os

import httpx
import pytest

from mcp_agent_factory.gateway.router import (
	AnthropicHandler,
	GeminiHandler,
	LLMRequest,
	OllamaHandler,
	OpenAIHandler,
	ProviderError,
	UnifiedRouter,
	provider_factory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(prompt: str = "test prompt") -> LLMRequest:
	return LLMRequest(tool_name="test", args={}, prompt=prompt)


def _gemini_response_payload(text: str = "hello", model: str = "gemini-1.5-flash") -> dict:
	return {
		"candidates": [
			{"content": {"parts": [{"text": text}]}}
		],
		"usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
		"modelVersion": model,
	}


class _MockTransport(httpx.MockTransport):
	"""Thin wrapper that stores the last request for assertion."""
	def __init__(self, response: httpx.Response) -> None:
		self._response = response
		self.last_request: httpx.Request | None = None

	def handle_request(self, request: httpx.Request) -> httpx.Response:
		self.last_request = request
		return self._response


# ---------------------------------------------------------------------------
# GeminiHandler — request mapping
# ---------------------------------------------------------------------------

class TestGeminiHandlerMapping:
	"""Verify GeminiHandler maps LLMRequest → Gemini REST payload correctly."""

	async def test_successful_call_returns_content(self, monkeypatch):
		monkeypatch.setenv("GEMINI_API_KEY", "test-key")
		transport = _MockTransport(
			httpx.Response(200, json=_gemini_response_payload("Analysis complete."))
		)
		monkeypatch.setattr(
			"httpx.AsyncClient",
			lambda **kw: httpx.AsyncClient(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
		)
		handler = GeminiHandler()
		# Patch AsyncClient to use mock transport
		import httpx as _httpx
		original_init = _httpx.AsyncClient.__init__

		async def _patched_call():
			import json as _json
			import httpx as _httpx2
			req = _make_request("Analyze Q3 report")
			payload = {
				"contents": [{"parts": [{"text": req.prompt}]}],
			}
			url = f"{handler._base_url}/models/{handler._model}:generateContent?key={handler._api_key}"
			mock_resp = httpx.Response(200, json=_gemini_response_payload("Analysis complete."))

			class _FakeClient:
				async def __aenter__(self): return self
				async def __aexit__(self, *a): pass
				async def post(self, u, json=None):
					assert "generateContent" in u
					assert json["contents"][0]["parts"][0]["text"] == "Analyze Q3 report"
					return mock_resp

			import unittest.mock as _mock
			with _mock.patch("httpx.AsyncClient", return_value=_FakeClient()):
				result = await handler.call(req)
			return result

		result = await _patched_call()
		assert result["content"] == "Analysis complete."
		assert result["model"] == "gemini-1.5-flash"
		assert result["input_tokens"] == 10
		assert result["output_tokens"] == 5

	async def test_missing_api_key_raises_provider_error(self, monkeypatch):
		monkeypatch.delenv("GEMINI_API_KEY", raising=False)
		handler = GeminiHandler()
		with pytest.raises(ProviderError) as exc_info:
			await handler.call(_make_request())
		assert exc_info.value.provider == "gemini"
		assert "GEMINI_API_KEY" in exc_info.value.detail

	async def test_missing_api_key_logs_warning(self, monkeypatch, caplog):
		monkeypatch.delenv("GEMINI_API_KEY", raising=False)
		import logging
		handler = GeminiHandler()
		with caplog.at_level(logging.WARNING, logger="mcp_agent_factory.gateway.router"):
			with pytest.raises(ProviderError):
				await handler.call(_make_request())
		assert any("gemini_key_missing" in r.message or "GEMINI_API_KEY" in r.message for r in caplog.records)

	async def test_rate_limit_raises_provider_error(self, monkeypatch):
		monkeypatch.setenv("GEMINI_API_KEY", "test-key")
		handler = GeminiHandler()

		async def _patched_call():
			import unittest.mock as _mock

			class _FakeClient:
				async def __aenter__(self): return self
				async def __aexit__(self, *a): pass
				async def post(self, u, json=None):
					return httpx.Response(429, text="quota exceeded")

			with _mock.patch("httpx.AsyncClient", return_value=_FakeClient()):
				return await handler.call(_make_request())

		with pytest.raises(ProviderError) as exc_info:
			await _patched_call()
		assert exc_info.value.status == 429
		assert exc_info.value.provider == "gemini"

	async def test_non_200_raises_provider_error(self, monkeypatch):
		monkeypatch.setenv("GEMINI_API_KEY", "test-key")
		handler = GeminiHandler()

		async def _patched_call():
			import unittest.mock as _mock

			class _FakeClient:
				async def __aenter__(self): return self
				async def __aexit__(self, *a): pass
				async def post(self, u, json=None):
					return httpx.Response(403, text="Forbidden")

			with _mock.patch("httpx.AsyncClient", return_value=_FakeClient()):
				return await handler.call(_make_request())

		with pytest.raises(ProviderError) as exc_info:
			await _patched_call()
		assert exc_info.value.status == 403

	async def test_connect_error_raises_provider_error(self, monkeypatch):
		monkeypatch.setenv("GEMINI_API_KEY", "test-key")
		handler = GeminiHandler()

		async def _patched_call():
			import unittest.mock as _mock

			class _FakeClient:
				async def __aenter__(self): return self
				async def __aexit__(self, *a): pass
				async def post(self, u, json=None):
					raise httpx.ConnectError("connection refused")

			with _mock.patch("httpx.AsyncClient", return_value=_FakeClient()):
				return await handler.call(_make_request())

		with pytest.raises(ProviderError) as exc_info:
			await _patched_call()
		assert exc_info.value.provider == "gemini"

	def test_provider_name(self):
		assert GeminiHandler().provider_name == "gemini"


# ---------------------------------------------------------------------------
# provider_factory — env-var routing
# ---------------------------------------------------------------------------

class TestProviderFactory:
	"""Verify provider_factory builds the right handler order for each LLM_PROVIDER."""

	def test_default_is_anthropic_first(self, monkeypatch):
		monkeypatch.delenv("LLM_PROVIDER", raising=False)
		router = provider_factory()
		assert isinstance(router._handlers[0], AnthropicHandler)
		assert isinstance(router._handlers[1], OllamaHandler)

	def test_anthropic_explicit(self, monkeypatch):
		monkeypatch.setenv("LLM_PROVIDER", "anthropic")
		router = provider_factory()
		assert isinstance(router._handlers[0], AnthropicHandler)
		assert isinstance(router._handlers[1], OllamaHandler)

	def test_gemini_first(self, monkeypatch):
		monkeypatch.setenv("LLM_PROVIDER", "gemini")
		router = provider_factory()
		assert isinstance(router._handlers[0], GeminiHandler)
		assert isinstance(router._handlers[1], OllamaHandler)

	def test_openai_first(self, monkeypatch):
		monkeypatch.setenv("LLM_PROVIDER", "openai")
		router = provider_factory()
		assert isinstance(router._handlers[0], OpenAIHandler)
		assert isinstance(router._handlers[1], OllamaHandler)

	def test_ollama_only(self, monkeypatch):
		monkeypatch.setenv("LLM_PROVIDER", "ollama")
		router = provider_factory()
		assert len(router._handlers) == 1
		assert isinstance(router._handlers[0], OllamaHandler)

	def test_case_insensitive(self, monkeypatch):
		monkeypatch.setenv("LLM_PROVIDER", "GEMINI")
		router = provider_factory()
		assert isinstance(router._handlers[0], GeminiHandler)

	def test_returns_unified_router(self, monkeypatch):
		monkeypatch.delenv("LLM_PROVIDER", raising=False)
		router = provider_factory()
		assert isinstance(router, UnifiedRouter)

	def test_factory_re_reads_env_on_each_call(self, monkeypatch):
		"""Each call to provider_factory re-reads LLM_PROVIDER — confirms live switching."""
		monkeypatch.setenv("LLM_PROVIDER", "anthropic")
		r1 = provider_factory()
		assert isinstance(r1._handlers[0], AnthropicHandler)

		monkeypatch.setenv("LLM_PROVIDER", "gemini")
		r2 = provider_factory()
		assert isinstance(r2._handlers[0], GeminiHandler)

		# r1 is unaffected — it was built with the old env
		assert isinstance(r1._handlers[0], AnthropicHandler)


# ---------------------------------------------------------------------------
# file_context_extractor — basic validation (no real PDF needed)
# ---------------------------------------------------------------------------

class TestFileContextExtractor:
	def test_raises_file_not_found(self, tmp_path):
		from mcp_agent_factory.knowledge.pdf_tool import file_context_extractor
		with pytest.raises(FileNotFoundError):
			file_context_extractor(str(tmp_path / "nonexistent.pdf"))

	def test_returns_expected_keys(self, tmp_path):
		"""Create a minimal valid PDF and verify the return shape."""
		pytest.importorskip("pypdf")
		from mcp_agent_factory.knowledge.pdf_tool import file_context_extractor

		# Create a minimal PDF using pypdf
		import pypdf
		from pypdf import PdfWriter
		writer = PdfWriter()
		writer.add_blank_page(width=200, height=200)
		pdf_path = tmp_path / "test.pdf"
		with open(pdf_path, "wb") as f:
			writer.write(f)

		result = file_context_extractor(str(pdf_path), query="test")
		assert "snippets" in result
		assert "total_pages" in result
		assert "pages_read" in result
		assert "source" in result
		assert result["total_pages"] == 1
		assert result["pages_read"] == 1
