"""
Shared pytest fixtures for mcp-agent-factory tests.
"""
from __future__ import annotations

import subprocess
import sys
import json
import threading
import queue
from typing import Generator

import pytest


class MCPServerProcess:
	"""
	Thin wrapper around the simulation MCP server subprocess.

	Exposes ``send(msg)`` / ``recv()`` helpers so tests can interact
	with the server over JSON-RPC 2.0 via STDIO without worrying about
	pipe buffering.
	"""

	def __init__(self, proc: subprocess.Popen):
		self.proc = proc
		self._q: queue.Queue = queue.Queue()
		self._reader = threading.Thread(target=self._read_loop, daemon=True)
		self._reader.start()

	def _read_loop(self) -> None:
		assert self.proc.stdout is not None
		for raw in self.proc.stdout:
			try:
				self._q.put(json.loads(raw))
			except json.JSONDecodeError:
				pass
		self._q.put(None)  # EOF sentinel

	def send(self, msg: dict) -> None:
		assert self.proc.stdin is not None
		self.proc.stdin.write(json.dumps(msg) + "\n")
		self.proc.stdin.flush()

	def recv(self, timeout: float = 5.0) -> dict:
		item = self._q.get(timeout=timeout)
		if item is None:
			raise EOFError("Server process closed stdout")
		return item

	def close(self) -> None:
		try:
			if self.proc.stdin:
				self.proc.stdin.close()
			self.proc.wait(timeout=5)
		except Exception:
			self.proc.kill()


@pytest.fixture
def mcp_server() -> Generator[MCPServerProcess, None, None]:
	"""
	Spawn the simulation MCP server as a subprocess and yield a
	``MCPServerProcess`` wrapper.  The process is terminated after the test.
	"""
	proc = subprocess.Popen(
		[sys.executable, "-m", "mcp_agent_factory.server"],
		stdin=subprocess.PIPE,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		text=True,
		bufsize=1,  # line-buffered
	)
	wrapper = MCPServerProcess(proc)
	yield wrapper
	wrapper.close()
