"""
MCP API Gateway — production launch module.

Starts the FastAPI gateway_app with uvicorn on 0.0.0.0:8000.

Usage::

    python -m mcp_agent_factory.gateway.run

Environment variables
---------------------
HOST    : bind address (default: 0.0.0.0)
PORT    : port (default: 8000)
LOG_LEVEL: uvicorn log level (default: info)
RELOAD  : set to '1' to enable auto-reload (dev only)
"""
from __future__ import annotations

import logging
import os

import uvicorn

from mcp_agent_factory.gateway.app import gateway_app

logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
RELOAD = os.getenv("RELOAD", "0") == "1"


def run() -> None:
	"""Start the gateway server."""
	logger.info("MCP Gateway running on http://%s:%d", HOST, PORT)
	uvicorn.run(
		"mcp_agent_factory.gateway.app:gateway_app",
		host=HOST,
		port=PORT,
		log_level=LOG_LEVEL,
		reload=RELOAD,
	)


if __name__ == "__main__":
	run()
