"""
Entry point for the MCPGatewayClient CLI demo.

Demonstrates the full client lifecycle:
  1. Build an OAuthMiddleware with a static token factory (replace with
     a real PKCE flow token factory for production use).
  2. Call list_tools() to confirm connectivity.
  3. Call the 'echo' tool as a smoke test.

Usage::

    python -m mcp_agent_factory.bridge

Set GATEWAY_URL to override the default localhost endpoint.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

from mcp_agent_factory.bridge.gateway_client import MCPGatewayClient
from mcp_agent_factory.bridge.oauth_middleware import OAuthMiddleware

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")


def _demo_token_factory() -> tuple[str, int]:
	"""
	Placeholder token factory for local development.

	In production, replace with a proper PKCE flow:
	  1. Generate code_verifier + code_challenge (S256)
	  2. GET /authorize → receive code
	  3. POST /token with code + code_verifier → receive access_token
	"""
	logger.warning(
		"Using demo token factory — replace with real PKCE flow for production. "
		"Set GATEWAY_TOKEN env var to inject a pre-issued token."
	)
	token = os.getenv("GATEWAY_TOKEN", "demo-token-replace-me")
	expires_at = int(time.time()) + 3600
	return token, expires_at


async def main() -> None:
	middleware = OAuthMiddleware(_demo_token_factory)
	client = MCPGatewayClient(GATEWAY_URL, middleware)

	logger.info("Connecting to gateway at %s", GATEWAY_URL)

	try:
		tools = await client.list_tools()
		logger.info("Available tools (%d):", len(tools))
		for t in tools:
			logger.info("  - %s: %s", t["name"], t.get("description", ""))

		result = await client.call_tool("echo", {"text": "hello from bridge"})
		logger.info("Echo result: %s", result)
	except Exception as exc:
		logger.error("Gateway call failed: %s", exc)
		sys.exit(1)


if __name__ == "__main__":
	asyncio.run(main())
