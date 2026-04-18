"""
Shared pytest fixtures for mcp-agent-factory tests.
"""
from __future__ import annotations

import socket
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


# ---------------------------------------------------------------------------
# Integration fixtures (require live Docker stack — skip otherwise)
# ---------------------------------------------------------------------------

@pytest.fixture
def real_redis():
	"""Single Redis client on port 6379. Skips if not reachable."""
	import redis as redis_lib
	client = redis_lib.Redis(host="localhost", port=6379, decode_responses=False)
	try:
		client.ping()
	except Exception:
		pytest.skip("Redis not available — run: docker-compose up -d redis")
	yield client
	client.close()


@pytest.fixture
def real_redis_cluster():
	"""3 independent Redis clients on ports 6381-6383. Skips if any is unreachable."""
	import redis as redis_lib
	ports = [6381, 6382, 6383]
	clients = []
	for port in ports:
		c = redis_lib.Redis(host="localhost", port=port, decode_responses=False)
		try:
			c.ping()
		except Exception:
			pytest.skip(
				f"Redis node on port {port} not available — "
				"run: docker-compose up -d redis-node-1 redis-node-2 redis-node-3"
			)
		clients.append(c)
	yield clients
	for c in clients:
		c.close()


@pytest.fixture
def real_kafka_bootstrap():
	"""Returns 'localhost:9092' when Kafka is reachable; skips otherwise."""
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.settimeout(2)
	try:
		s.connect(("localhost", 9092))
		s.close()
	except (ConnectionRefusedError, OSError):
		pytest.skip("Kafka not available — run: docker-compose up -d kafka")
	return "localhost:9092"
