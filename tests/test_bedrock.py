"""
Tests for the Bedrock LLM handler (Component 3).

All tests mock boto3.client — no live AWS calls are made.
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

boto3 = pytest.importorskip("boto3", reason="boto3 not installed")

from mcp_agent_factory.gateway.router import (
    BedrockHandler,
    LLMRequest,
    ProviderError,
    UnifiedRouter,
    OllamaHandler,
    provider_factory,
)


def _make_bedrock_response(text: str = "ok", input_tokens: int = 5, output_tokens: int = 10):
    body = {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    return {"body": io.BytesIO(json.dumps(body).encode())}


class TestBedrockHandler:
    def test_bedrock_call_returns_content(self):
        with patch("boto3.client") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            mock_client.invoke_model.return_value = _make_bedrock_response("hello bedrock")

            import asyncio
            handler = BedrockHandler()
            result = asyncio.get_event_loop().run_until_complete(
                handler.call(LLMRequest(tool_name="echo", args={"text": "ping"}))
            )

        assert result["content"] == "hello bedrock"
        assert result["input_tokens"] == 5
        assert result["output_tokens"] == 10

    def test_bedrock_raises_provider_error_on_exception(self):
        with patch("boto3.client") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            mock_client.invoke_model.side_effect = Exception("connection refused")

            import asyncio
            handler = BedrockHandler()
            with pytest.raises(ProviderError) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    handler.call(LLMRequest(tool_name="echo", args={"text": "ping"}))
                )
            assert exc_info.value.provider == "bedrock"

    def test_bedrock_missing_boto3_raises_provider_error(self):
        import sys
        import asyncio

        # Temporarily hide boto3
        original = sys.modules.get("boto3")
        sys.modules["boto3"] = None  # type: ignore[assignment]
        try:
            handler = BedrockHandler()
            with pytest.raises((ProviderError, ImportError)):
                asyncio.get_event_loop().run_until_complete(
                    handler.call(LLMRequest(tool_name="echo", args={"text": "ping"}))
                )
        finally:
            if original is None:
                sys.modules.pop("boto3", None)
            else:
                sys.modules["boto3"] = original

    def test_bedrock_provider_name(self):
        assert BedrockHandler().provider_name == "bedrock"

    def test_bedrock_uses_iam_role_not_api_key(self):
        """Verify BedrockHandler does not read any *_API_KEY env vars."""
        import inspect
        src = inspect.getsource(BedrockHandler)
        assert "API_KEY" not in src

    def test_provider_name_is_bedrock(self):
        assert BedrockHandler.provider_name == "bedrock"


class TestBedrockFallback:
    def test_bedrock_fails_falls_back_to_ollama(self):
        """UnifiedRouter falls back to Ollama when Bedrock raises ProviderError."""
        import asyncio

        bedrock = BedrockHandler()
        ollama = OllamaHandler()

        async def _fail(req):
            raise ProviderError("bedrock", detail="unreachable")

        async def _ok(req):
            return {"content": "ollama fallback", "model": "qwen3", "input_tokens": 1, "output_tokens": 1}

        bedrock.call = _fail  # type: ignore[assignment]
        ollama.call = _ok    # type: ignore[assignment]

        router = UnifiedRouter(handlers=[bedrock, ollama])
        result = asyncio.get_event_loop().run_until_complete(
            router.route(LLMRequest(tool_name="echo", args={"text": "hi"}))
        )
        assert result["content"] == "ollama fallback"


class TestProviderFactory:
    def test_factory_bedrock_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "bedrock")
        router = provider_factory()
        assert any(h.provider_name == "bedrock" for h in router._handlers)
        # Last handler is Ollama fallback
        assert router._handlers[-1].provider_name == "ollama"

    def test_factory_gemini_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        router = provider_factory()
        assert router._handlers[0].provider_name == "gemini"
        assert router._handlers[-1].provider_name == "ollama"

    def test_factory_openai_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        router = provider_factory()
        assert router._handlers[0].provider_name == "openai"

    def test_factory_ollama_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        router = provider_factory()
        assert len(router._handlers) == 1
        assert router._handlers[0].provider_name == "ollama"

    def test_factory_default_is_anthropic(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        router = provider_factory()
        assert router._handlers[0].provider_name == "anthropic"


# ---------------------------------------------------------------------------
# _emit_token_usage with a real EventLog
# ---------------------------------------------------------------------------

class TestEmitTokenUsage:
    def test_emit_called_when_event_log_present(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from mcp_agent_factory.gateway.router import UnifiedRouter, LLMHandler, LLMRequest

        class _FakeHandler(LLMHandler):
            provider_name = "fake"

            async def call(self, request):
                return {"content": "hi", "model": "fake-model", "input_tokens": 10, "output_tokens": 5}

        event_log = MagicMock()
        event_log.append = AsyncMock()
        router = UnifiedRouter(handlers=[_FakeHandler()], event_log=event_log)
        asyncio.get_event_loop().run_until_complete(
            router.route(LLMRequest(tool_name="t", args={"text": "x"}))
        )
        event_log.append.assert_called_once()
        args = event_log.append.call_args[0]
        assert args[0] == "token.usage"

    def test_emit_log_failure_does_not_propagate(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from mcp_agent_factory.gateway.router import UnifiedRouter, LLMHandler, LLMRequest

        class _FakeHandler(LLMHandler):
            provider_name = "fake"

            async def call(self, request):
                return {"content": "hi", "model": "fake-model", "input_tokens": 1, "output_tokens": 1}

        event_log = MagicMock()
        event_log.append = AsyncMock(side_effect=Exception("log failure"))
        router = UnifiedRouter(handlers=[_FakeHandler()], event_log=event_log)
        # Must not raise
        result = asyncio.get_event_loop().run_until_complete(
            router.route(LLMRequest(tool_name="t", args={"text": "x"}))
        )
        assert result["content"] == "hi"
