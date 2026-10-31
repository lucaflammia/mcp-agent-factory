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


def _gemini_response_payload(text: str = "hello", model: str = "gemini-2.5-flash") -> dict:
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
		assert result["model"] == "gemini-2.5-flash"
		assert result["input_tokens"] == 10
		assert result["output_tokens"] == 5

	async def test_missing_api_key_raises_provider_error(self, monkeypatch):
		monkeypatch.delenv("GEMINI_API_KEY", raising=False)
		monkeypatch.delenv("MCP_DEV_MODE", raising=False)
		handler = GeminiHandler()
		with pytest.raises(ProviderError) as exc_info:
			await handler.call(_make_request())
		assert exc_info.value.provider == "gemini"
		assert "GEMINI_API_KEY" in exc_info.value.detail

	async def test_missing_api_key_logs_warning(self, monkeypatch, caplog):
		monkeypatch.delenv("GEMINI_API_KEY", raising=False)
		monkeypatch.delenv("MCP_DEV_MODE", raising=False)
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
		# Create a minimal PDF using pypdf
		import pypdf
		from pypdf import PdfWriter

		from mcp_agent_factory.knowledge.pdf_tool import file_context_extractor
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


# ---------------------------------------------------------------------------
# Shared fake client helper
# ---------------------------------------------------------------------------

def _fake_client(response: httpx.Response):
	"""Return an async context-manager fake that returns *response* from post()."""
	class _FC:
		async def __aenter__(self): return self
		async def __aexit__(self, *a): pass
		async def post(self, *a, **kw): return response
	return _FC()


def _fake_client_raise(exc):
	"""Return a fake that raises *exc* on post()."""
	class _FC:
		async def __aenter__(self): return self
		async def __aexit__(self, *a): pass
		async def post(self, *a, **kw): raise exc
	return _FC()


# ---------------------------------------------------------------------------
# OpenAIHandler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOpenAIHandler:
	_openai_resp = {
		"choices": [{"message": {"content": "openai reply"}}],
		"model": "gpt-4o-mini",
		"usage": {"prompt_tokens": 8, "completion_tokens": 4},
	}

	async def test_successful_call(self, monkeypatch):
		import unittest.mock as _mock
		monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
		handler = OpenAIHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(200, json=self._openai_resp))):
			result = await handler.call(_make_request("hello"))
		assert result["content"] == "openai reply"
		assert result["input_tokens"] == 8
		assert result["output_tokens"] == 4

	async def test_rate_limit_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
		handler = OpenAIHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(429, text="rate limited"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.status == 429
		assert exc_info.value.provider == "openai"

	async def test_non_200_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
		handler = OpenAIHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(500, text="Internal Error"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.status == 500

	async def test_connect_error_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
		handler = OpenAIHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client_raise(httpx.ConnectError("refused"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.provider == "openai"


# ---------------------------------------------------------------------------
# AnthropicHandler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAnthropicHandler:
	_anthropic_resp = {
		"content": [{"type": "text", "text": "anthropic reply"}],
		"model": "claude-3-haiku-20240307",
		"usage": {"input_tokens": 6, "output_tokens": 3},
	}

	async def test_successful_call(self, monkeypatch):
		import unittest.mock as _mock
		monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
		handler = AnthropicHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(200, json=self._anthropic_resp))):
			result = await handler.call(_make_request("hello"))
		assert result["content"] == "anthropic reply"
		assert result["input_tokens"] == 6
		assert result["output_tokens"] == 3

	async def test_rate_limit_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
		handler = AnthropicHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(429, text="rate limited"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.status == 429
		assert exc_info.value.provider == "anthropic"

	async def test_non_200_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
		handler = AnthropicHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(401, text="Unauthorized"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.status == 401

	async def test_connect_error_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
		handler = AnthropicHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client_raise(httpx.ConnectError("refused"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.provider == "anthropic"


# ---------------------------------------------------------------------------
# OllamaHandler — error paths (success path covered in test_m009_s01.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOllamaHandlerErrors:
	async def test_rate_limit_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		handler = OllamaHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(429, text="rate limited"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.status == 429
		assert exc_info.value.provider == "ollama"

	async def test_non_200_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		handler = OllamaHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(503, text="Service Unavailable"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.status == 503

	async def test_connect_error_raises_provider_error(self, monkeypatch):
		import unittest.mock as _mock
		handler = OllamaHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client_raise(httpx.ConnectError("refused"))):
			with pytest.raises(ProviderError) as exc_info:
				await handler.call(_make_request())
		assert exc_info.value.provider == "ollama"


# ---------------------------------------------------------------------------
# GeminiHandler — dev mode fallback (MCP_DEV_MODE=1, no API key)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGeminiDevMode:
	async def test_dev_mode_delegates_to_ollama(self, monkeypatch):
		"""With MCP_DEV_MODE=1 and no GEMINI_API_KEY, GeminiHandler falls back to OllamaHandler."""
		import unittest.mock as _mock
		monkeypatch.delenv("GEMINI_API_KEY", raising=False)
		monkeypatch.setenv("MCP_DEV_MODE", "1")
		_ollama_resp = {
			"message": {"content": "dev reply"},
			"model": "qwen3:0.6b-q4_K_M",
			"prompt_eval_count": 4,
			"eval_count": 2,
		}
		handler = GeminiHandler()
		with _mock.patch("httpx.AsyncClient", return_value=_fake_client(httpx.Response(200, json=_ollama_resp))):
			result = await handler.call(_make_request("hello"))
		assert result["content"] == "dev reply"
		assert result["model"] == handler._model  # relabelled as gemini model
