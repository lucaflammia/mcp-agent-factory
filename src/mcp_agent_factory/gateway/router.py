"""
UnifiedRouter — model-agnostic LLM dispatch with automatic fallback.

Handlers are tried in the order provided. On ProviderError the next handler
is attempted. After a successful call a ``token.usage`` event is appended to
the EventLog (fire-and-forget — log write failures never propagate).
"""
from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from mcp_agent_factory.streams.eventlog import EventLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass
class LLMRequest:
	"""Normalised request passed to every LLMHandler."""
	tool_name: str
	args: dict[str, Any]
	claims: dict[str, Any] | None = None
	prompt: str = ""


class ProviderError(Exception):
	"""Raised by a handler when the provider is unavailable or rate-limited."""

	def __init__(self, provider: str, status: int | None = None, detail: str = "") -> None:
		self.provider = provider
		self.status = status
		self.detail = detail
		super().__init__(f"{provider} failed (status={status}): {detail}")


# ---------------------------------------------------------------------------
# Abstract handler
# ---------------------------------------------------------------------------

class LLMHandler(ABC):
	"""Contract all provider handlers must satisfy."""

	@abstractmethod
	async def call(self, request: LLMRequest) -> dict[str, Any]:
		"""
		Call the provider and return a normalised response dict::

			{content: str, model: str, input_tokens: int, output_tokens: int}

		Raises ProviderError on 429, connection error, or non-2xx response.
		"""

	@property
	@abstractmethod
	def provider_name(self) -> str:
		"""Human-readable provider label used in log events."""


# ---------------------------------------------------------------------------
# Cost table — USD per 1 M tokens (in, out). Configurable in future via env.
# ---------------------------------------------------------------------------

_COST_PER_M: dict[str, tuple[float, float]] = {
	"gpt-4o": (5.0, 15.0),
	"gpt-4o-mini": (0.15, 0.60),
	"claude-3-5-sonnet-20241022": (3.0, 15.0),
	"claude-3-haiku-20240307": (0.25, 1.25),
}


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
	in_rate, out_rate = _COST_PER_M.get(model, (0.0, 0.0))
	return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def _prompt_from(request: LLMRequest) -> str:
	return request.prompt or request.args.get("text", str(request.args))


# ---------------------------------------------------------------------------
# OpenAI handler
# ---------------------------------------------------------------------------

class OpenAIHandler(LLMHandler):
	provider_name = "openai"

	def __init__(self) -> None:
		self._api_key = os.getenv("OPENAI_API_KEY", "")
		self._base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
		self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

	async def call(self, request: LLMRequest) -> dict[str, Any]:
		payload = {
			"model": self._model,
			"messages": [{"role": "user", "content": _prompt_from(request)}],
			"max_tokens": 256,
		}
		headers = {
			"Authorization": f"Bearer {self._api_key}",
			"Content-Type": "application/json",
		}
		async with httpx.AsyncClient(timeout=30.0) as client:
			try:
				resp = await client.post(
					f"{self._base_url}/chat/completions", json=payload, headers=headers
				)
			except httpx.ConnectError as exc:
				raise ProviderError("openai", detail=str(exc)) from exc

		if resp.status_code == 429:
			raise ProviderError("openai", status=429, detail="rate limited")
		if resp.status_code >= 400:
			raise ProviderError("openai", status=resp.status_code, detail=resp.text[:200])

		data = resp.json()
		usage = data.get("usage", {})
		return {
			"content": data["choices"][0]["message"]["content"],
			"model": data.get("model", self._model),
			"input_tokens": usage.get("prompt_tokens", 0),
			"output_tokens": usage.get("completion_tokens", 0),
		}


# ---------------------------------------------------------------------------
# Anthropic handler
# ---------------------------------------------------------------------------

class AnthropicHandler(LLMHandler):
	provider_name = "anthropic"

	def __init__(self) -> None:
		self._api_key = os.getenv("ANTHROPIC_API_KEY", "")
		self._base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
		self._model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

	async def call(self, request: LLMRequest) -> dict[str, Any]:
		payload = {
			"model": self._model,
			"messages": [{"role": "user", "content": _prompt_from(request)}],
			"max_tokens": 256,
		}
		headers = {
			"x-api-key": self._api_key,
			"anthropic-version": "2023-06-01",
			"Content-Type": "application/json",
		}
		async with httpx.AsyncClient(timeout=30.0) as client:
			try:
				resp = await client.post(
					f"{self._base_url}/messages", json=payload, headers=headers
				)
			except httpx.ConnectError as exc:
				raise ProviderError("anthropic", detail=str(exc)) from exc

		if resp.status_code == 429:
			raise ProviderError("anthropic", status=429, detail="rate limited")
		if resp.status_code >= 400:
			raise ProviderError("anthropic", status=resp.status_code, detail=resp.text[:200])

		data = resp.json()
		usage = data.get("usage", {})
		content_blocks = data.get("content", [])
		content_text = " ".join(
			b.get("text", "") for b in content_blocks if b.get("type") == "text"
		)
		return {
			"content": content_text,
			"model": data.get("model", self._model),
			"input_tokens": usage.get("input_tokens", 0),
			"output_tokens": usage.get("output_tokens", 0),
		}


# ---------------------------------------------------------------------------
# Ollama handler
# ---------------------------------------------------------------------------

class OllamaHandler(LLMHandler):
	provider_name = "ollama"

	def __init__(self) -> None:
		self._base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
		self._model = os.getenv("OLLAMA_MODEL", "llama3.2")

	async def call(self, request: LLMRequest) -> dict[str, Any]:
		payload = {
			"model": self._model,
			"messages": [{"role": "user", "content": _prompt_from(request)}],
			"stream": False,
		}
		async with httpx.AsyncClient(timeout=60.0) as client:
			try:
				resp = await client.post(f"{self._base_url}/api/chat", json=payload)
			except httpx.ConnectError as exc:
				raise ProviderError("ollama", detail=str(exc)) from exc

		if resp.status_code == 429:
			raise ProviderError("ollama", status=429, detail="rate limited")
		if resp.status_code >= 400:
			raise ProviderError("ollama", status=resp.status_code, detail=resp.text[:200])

		data = resp.json()
		message = data.get("message", {})
		return {
			"content": message.get("content", ""),
			"model": data.get("model", self._model),
			# Ollama uses prompt_eval_count / eval_count for token counts
			"input_tokens": data.get("prompt_eval_count", 0),
			"output_tokens": data.get("eval_count", 0),
		}


# ---------------------------------------------------------------------------
# Gemini handler
# ---------------------------------------------------------------------------

class GeminiHandler(LLMHandler):
	provider_name = "gemini"

	def __init__(self) -> None:
		self._api_key = os.getenv("GEMINI_API_KEY", "")
		self._model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
		self._base_url = "https://generativelanguage.googleapis.com/v1beta"

	async def call(self, request: LLMRequest) -> dict[str, Any]:
		if not self._api_key:
			logger.warning('{"event":"gemini_key_missing","detail":"GEMINI_API_KEY not set — falling back"}')
			raise ProviderError("gemini", detail="GEMINI_API_KEY not set")

		url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"
		payload = {
			"contents": [{"parts": [{"text": _prompt_from(request)}]}],
		}
		async with httpx.AsyncClient(timeout=30.0) as client:
			try:
				resp = await client.post(url, json=payload)
			except httpx.ConnectError as exc:
				raise ProviderError("gemini", detail=str(exc)) from exc

		if resp.status_code == 429:
			raise ProviderError("gemini", status=429, detail="rate limited")
		if resp.status_code >= 400:
			raise ProviderError("gemini", status=resp.status_code, detail=resp.text[:200])

		data = resp.json()
		candidates = data.get("candidates", [])
		content_text = ""
		if candidates:
			parts = candidates[0].get("content", {}).get("parts", [])
			content_text = " ".join(p.get("text", "") for p in parts)

		usage = data.get("usageMetadata", {})
		return {
			"content": content_text,
			"model": self._model,
			"input_tokens": usage.get("promptTokenCount", 0),
			"output_tokens": usage.get("candidatesTokenCount", 0),
		}


# ---------------------------------------------------------------------------
# Provider factory — re-read LLM_PROVIDER on every call for live switching
# ---------------------------------------------------------------------------

def provider_factory(event_log: EventLog | None = None) -> "UnifiedRouter":
	"""Build a UnifiedRouter with handler order driven by LLM_PROVIDER env var.

	LLM_PROVIDER=anthropic → [AnthropicHandler, OllamaHandler]
	LLM_PROVIDER=gemini    → [GeminiHandler, OllamaHandler]
	LLM_PROVIDER=ollama    → [OllamaHandler]
	LLM_PROVIDER=openai    → [OpenAIHandler, OllamaHandler]
	default (unset)        → [AnthropicHandler, OllamaHandler]
	"""
	provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
	ollama = OllamaHandler()

	if provider == "gemini":
		handlers: list[LLMHandler] = [GeminiHandler(), ollama]
	elif provider == "openai":
		handlers = [OpenAIHandler(), ollama]
	elif provider == "ollama":
		handlers = [ollama]
	else:
		handlers = [AnthropicHandler(), ollama]

	return UnifiedRouter(handlers=handlers, event_log=event_log)


# ---------------------------------------------------------------------------
# UnifiedRouter
# ---------------------------------------------------------------------------

class UnifiedRouter:
	"""Dispatches an LLMRequest to the first handler that succeeds.

	If a handler raises ProviderError, the next handler in the list is tried.
	After a successful call a ``token.usage`` event is appended to the EventLog.
	If all handlers fail, the last ProviderError is re-raised.
	"""

	def __init__(
		self,
		handlers: list[LLMHandler],
		event_log: EventLog | None = None,
	) -> None:
		if not handlers:
			raise ValueError("UnifiedRouter requires at least one handler")
		self._handlers = handlers
		self._event_log = event_log

	async def route(self, request: LLMRequest) -> dict[str, Any]:
		"""Try each handler in order; return first success."""
		last_error: ProviderError | None = None
		for handler in self._handlers:
			try:
				result = await handler.call(request)
				await self._emit_token_usage(result, request)
				return result
			except ProviderError as exc:
				logger.warning(
					'{"event":"provider_error","provider":"%s","status":%s,"detail":"%s"}',
					exc.provider,
					exc.status,
					exc.detail,
				)
				last_error = exc
		raise last_error  # type: ignore[misc]

	async def _emit_token_usage(
		self, result: dict[str, Any], request: LLMRequest
	) -> None:
		if self._event_log is None:
			return
		sub = (request.claims or {}).get("sub", "anonymous")
		event = {
			"type": "token.usage",
			"model": result.get("model", "unknown"),
			"input_tokens": result.get("input_tokens", 0),
			"output_tokens": result.get("output_tokens", 0),
			"cost_usd": _cost_usd(
				result.get("model", ""),
				result.get("input_tokens", 0),
				result.get("output_tokens", 0),
			),
			"sub": sub,
			"ts": int(time.time()),
		}
		try:
			await self._event_log.append("token.usage", event)
		except Exception as exc:  # noqa: BLE001
			logger.warning('{"event":"token_usage_log_failure","detail":"%s"}', exc)
