"""
Entry point for the MCPGatewayClient CLI demo.

Demonstrates the full client lifecycle:
  1. Build OAuthMiddleware using client_credentials (machine-to-machine) when
     BRIDGE_CLIENT_ID + BRIDGE_CLIENT_SECRET are set, or fall back to a
     pre-issued GATEWAY_TOKEN for quick local testing.
  2. Call list_tools() to confirm connectivity.
  3. Call the 'echo' tool as a smoke test.

Usage::

    # Production / staging (auth server + gateway both running):
    BRIDGE_CLIENT_ID=my-bridge \\
    BRIDGE_CLIENT_SECRET=s3cr3t \\
    python -m mcp_agent_factory.bridge

    # Quick local dev (pre-issued token from POST /token):
    GATEWAY_TOKEN=<jwt> python -m mcp_agent_factory.bridge

Environment variables
---------------------
GATEWAY_URL          Base URL of the gateway   (default: http://localhost:8000)
AUTH_SERVER_URL      Base URL of the auth server (default: http://localhost:8001)
BRIDGE_CLIENT_ID     OAuth client_id registered with the auth server
BRIDGE_CLIENT_SECRET OAuth client_secret registered with the auth server
GATEWAY_TOKEN        Pre-issued JWT (fallback when client creds are not set)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from authlib.jose import OctKey, jwt as _jwt

from mcp_agent_factory.auth.session import generate_session_id
from mcp_agent_factory.bridge.gateway_client import MCPGatewayClient
from mcp_agent_factory.bridge.oauth_middleware import (
    OAuthMiddleware,
    make_client_credentials_factory,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
AUTH_SERVER_URL = os.getenv("AUTH_SERVER_URL", "http://localhost:8001")


def _make_self_signed_factory(jwt_secret: str, client_id: str = "bridge") -> OAuthMiddleware:
    """
    Return an OAuthMiddleware that self-signs JWTs using JWT_SECRET.

    This bypasses the auth server — the gateway validates the token using the
    same JWT_SECRET.  Use only when the auth server is not running.
    """
    key = OctKey.import_key(jwt_secret.encode())

    def _factory() -> tuple[str, int]:
        now = int(time.time())
        exp = now + 3600
        claims = {
            "sub": client_id,
            "aud": "mcp-server",
            "scope": "tools:call",
            "session_id": generate_session_id(client_id),
            "iat": now,
            "exp": exp,
        }
        token = _jwt.encode({"alg": "HS256"}, claims, key).decode("ascii")
        return token, exp

    return OAuthMiddleware(_factory)


def _build_middleware() -> OAuthMiddleware:
    client_id = os.getenv("BRIDGE_CLIENT_ID")
    client_secret = os.getenv("BRIDGE_CLIENT_SECRET")

    if client_id and client_secret:
        logger.info("Using client_credentials flow (client_id=%s)", client_id)
        factory = make_client_credentials_factory(
            AUTH_SERVER_URL, client_id, client_secret
        )
        return OAuthMiddleware(factory)

    token = os.getenv("GATEWAY_TOKEN")
    if token:
        logger.info("Using pre-issued GATEWAY_TOKEN")
        def _static() -> tuple[str, int]:
            return token, int(time.time()) + 3600
        return OAuthMiddleware(_static)

    jwt_secret = os.getenv("JWT_SECRET")
    if jwt_secret:
        logger.info(
            "Auth server not configured — self-signing JWTs with JWT_SECRET "
            "(dev mode; set BRIDGE_CLIENT_ID + BRIDGE_CLIENT_SECRET for production)"
        )
        return _make_self_signed_factory(jwt_secret)

    logger.warning(
        "No credentials found. Set JWT_SECRET (dev), GATEWAY_TOKEN (pre-issued), "
        "or BRIDGE_CLIENT_ID + BRIDGE_CLIENT_SECRET (M2M). "
        "Proceeding without auth — tools/call will be rejected by the gateway."
    )
    def _no_auth() -> tuple[str, int]:
        return "", int(time.time()) + 3600
    return OAuthMiddleware(_no_auth)


async def main() -> None:
    middleware = _build_middleware()
    client = MCPGatewayClient(GATEWAY_URL, middleware)

    logger.info("Connecting to gateway at %s", GATEWAY_URL)

    try:
        tools = await client.list_tools()
        logger.info("Available tools (%d):", len(tools))
        for t in tools:
            logger.info("  - %s: %s", t["name"], t.get("description", ""))

        result = await client.call_tool("echo", {"message": "hello from bridge"})
        logger.info("Echo result: %s", result)
    except Exception as exc:
        logger.error("Gateway call failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
