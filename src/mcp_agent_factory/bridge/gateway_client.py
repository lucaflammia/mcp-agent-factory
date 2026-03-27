"""
MCPGatewayClient — wraps the MCP API Gateway with OAuth token injection.

Uses httpx.AsyncClient for real HTTP; in tests a TestClient-backed transport
is injected via the ``transport`` parameter.
"""
from __future__ import annotations

import logging
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
        body = await self._post_mcp({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1,
        })
        return body["result"]["tools"]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a named tool and return the result dict."""
        body = await self._post_mcp({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
            "id": 2,
        })
        return body["result"]
