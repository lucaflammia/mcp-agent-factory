"""
MCPGatewayClient — wraps the MCP API Gateway with OAuth token injection.

Uses httpx.AsyncClient for real HTTP; in tests a TestClient-backed transport
is injected via the ``transport`` parameter.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .oauth_middleware import OAuthMiddleware

logger = logging.getLogger(__name__)


class MCPGatewayClient:
	"""
	Async client for the MCP API Gateway.

	Parameters
	----------
	base_url:
		Base URL of the gateway (e.g. ``http://localhost:8000``).
	middleware:
		OAuthMiddleware instance that injects Bearer tokens.
	transport:
		Optional httpx transport — useful for test injection
		(e.g. ``httpx.ASGITransport(app=gateway_app)``).
	"""

	def __init__(
		self,
		base_url: str,
		middleware: OAuthMiddleware,
		transport: httpx.AsyncBaseTransport | None = None,
	) -> None:
		self._base_url = base_url.rstrip("/")
		self._middleware = middleware
		self._transport = transport

	async def _post_mcp(self, payload: dict[str, Any]) -> dict[str, Any]:
		headers = await self._middleware.inject({"Content-Type": "application/json"})
		async with httpx.AsyncClient(
			base_url=self._base_url,
			transport=self._transport,
		) as client:
			resp = await client.post("/mcp", json=payload, headers=headers)
			resp.raise_for_status()
			return resp.json()

	async def list_tools(self) -> list[dict]:
		"""Return the list of tools exposed by the gateway."""
		logger.debug("bridge.list_tools base_url=%s", self._base_url)
		body = await self._post_mcp({
			"jsonrpc": "2.0",
			"method": "tools/list",
			"id": 1,
		})
		return body["result"]["tools"]

	async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
		"""Call a named tool and return the result dict."""
		logger.debug("bridge.call_tool name=%s base_url=%s", name, self._base_url)
		body = await self._post_mcp({
			"jsonrpc": "2.0",
			"method": "tools/call",
			"params": {"name": name, "arguments": arguments},
			"id": 2,
		})
		print(f"DEBUG GATEWAY RESPONSE: {body}")
		return body["result"]

	async def stream_events(
		self,
		topic: str = "agent.events",
		*,
		max_events: int | None = None,
	) -> AsyncIterator[dict[str, Any]]:
		"""
		Async generator that streams SSE events from /sse/v1/events.

		Yields parsed event data dicts (JSON-decoded ``data:`` lines).
		Stops after *max_events* events when specified, otherwise runs until
		the caller breaks or the server closes the connection.

		Parameters
		----------
		topic:
			Bus topic to subscribe to (passed as query param).
		max_events:
			Maximum number of data events to yield before stopping.
		"""
		headers = await self._middleware.inject({})
		count = 0
		async with httpx.AsyncClient(
			base_url=self._base_url,
			transport=self._transport,
		) as client:
			async with client.stream(
				"GET",
				f"/sse/v1/events?topic={topic}",
				headers=headers,
			) as resp:
				resp.raise_for_status()
				async for line in resp.aiter_lines():
					line = line.strip()
					if line.startswith("data:"):
						raw = line[len("data:"):].strip()
						if raw:
							try:
								yield json.loads(raw)
								count += 1
								if max_events is not None and count >= max_events:
									return
							except json.JSONDecodeError:
								logger.warning("bridge.stream_events: bad JSON: %r", raw)
