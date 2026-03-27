"""
MCPOrchestrator — drives the full MCP lifecycle over a STDIO subprocess.

Observability: every JSON-RPC send/receive is logged at DEBUG level so
callers can replay any exchange post-mortem.

Usage::

	with MCPOrchestrator() as orc:
		tools = orc.list_tools()
		result = orc.call_tool("echo", {"message": "hello"})
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import queue
from typing import Any

logger = logging.getLogger(__name__)


class MCPOrchestrator:
	"""
	Spawns the simulation MCP server as a subprocess and drives the full
	JSON-RPC 2.0 lifecycle:

	1. ``connect()``     — initialize handshake
	2. ``list_tools()``  — tools/list request
	3. ``call_tool()``   — tools/call request
	"""

	def __init__(self, server_cmd: list[str] | None = None):
		self._cmd = server_cmd or [sys.executable, "-m", "mcp_agent_factory.server"]
		self._proc: subprocess.Popen | None = None
		self._recv_q: queue.Queue = queue.Queue()
		self._reader: threading.Thread | None = None
		self._next_id = 1

	# ------------------------------------------------------------------
	# Context manager support
	# ------------------------------------------------------------------

	def __enter__(self) -> "MCPOrchestrator":
		self.connect()
		return self

	def __exit__(self, *_: Any) -> None:
		self.close()

	# ------------------------------------------------------------------
	# Lifecycle
	# ------------------------------------------------------------------

	def connect(self) -> dict:
		"""
		Spawn the server subprocess and perform the MCP initialize handshake.

		Returns the ``result`` dict from the server's ``initialize`` response.
		"""
		logger.debug("Spawning server: %s", self._cmd)
		self._proc = subprocess.Popen(
			self._cmd,
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			bufsize=1,  # line-buffered
		)
		self._reader = threading.Thread(target=self._read_loop, daemon=True)
		self._reader.start()

		# --- initialize request ---
		init_response = self._rpc(
			"initialize",
			{
				"protocolVersion": "2024-11-05",
				"capabilities": {},
				"clientInfo": {"name": "mcp-orchestrator", "version": "0.1.0"},
			},
		)
		# Send initialized notification (no response expected)
		self._send({"jsonrpc": "2.0", "method": "initialized"})
		logger.debug("Handshake complete: %s", init_response)
		return init_response

	def close(self) -> None:
		"""Shut down the server subprocess gracefully."""
		if self._proc is None:
			return
		try:
			if self._proc.stdin:
				self._proc.stdin.close()
			self._proc.wait(timeout=5)
		except Exception:
			self._proc.kill()
		finally:
			self._proc = None

	# ------------------------------------------------------------------
	# MCP operations
	# ------------------------------------------------------------------

	def list_tools(self) -> list[dict]:
		"""
		Send ``tools/list`` and return the list of tool descriptors.
		"""
		response = self._rpc("tools/list", {})
		return response.get("tools", [])

	def call_tool(self, name: str, arguments: dict | None = None) -> dict:
		"""
		Send ``tools/call`` for *name* with *arguments* and return the
		full result dict (contains ``content`` and ``isError``).
		"""
		response = self._rpc(
			"tools/call",
			{"name": name, "arguments": arguments or {}},
		)
		return response

	# ------------------------------------------------------------------
	# JSON-RPC 2.0 transport
	# ------------------------------------------------------------------

	def _next_rpc_id(self) -> int:
		rid = self._next_id
		self._next_id += 1
		return rid

	def _send(self, msg: dict) -> None:
		assert self._proc and self._proc.stdin, "Not connected"
		line = json.dumps(msg) + "\n"
		logger.debug("send %s", line.rstrip())
		self._proc.stdin.write(line)
		self._proc.stdin.flush()

	def _recv(self, timeout: float = 5.0) -> dict:
		item = self._recv_q.get(timeout=timeout)
		if item is None:
			raise EOFError("Server closed stdout unexpectedly")
		logger.debug("recv %s", item)
		return item

	def _rpc(self, method: str, params: dict, timeout: float = 5.0) -> dict:
		"""Send a request and wait for the matching response, returning ``result``."""
		rid = self._next_rpc_id()
		self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
		response = self._recv(timeout=timeout)
		if "error" in response:
			err = response["error"]
			raise RuntimeError(f"RPC error {err.get('code')}: {err.get('message')}")
		return response.get("result", {})

	def _read_loop(self) -> None:
		assert self._proc and self._proc.stdout
		for raw in self._proc.stdout:
			try:
				self._recv_q.put(json.loads(raw))
			except json.JSONDecodeError:
				pass
		self._recv_q.put(None)  # EOF sentinel
