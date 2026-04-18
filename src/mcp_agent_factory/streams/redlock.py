"""
RedlockClient: Redlock quorum locking across N independent Redis nodes (R018).

Supersedes DistributedLock (single-node SET NX) from M006 when 3+ nodes are
available. Implements the same acquire/release interface so callers can swap
implementations behind the DistributedLock protocol.

Algorithm (per antirez/redlock-rb):
  1. Record start time.
  2. For each node, attempt SET key token NX PX ttl_ms.
  3. Count successes. If >= quorum AND elapsed < ttl_ms, lock is held.
  4. On failure, release all partial locks (DEL key where token matches).
"""
from __future__ import annotations

import time
import uuid
from typing import Any


class RedlockClient:
	"""Quorum-based distributed lock across multiple independent Redis nodes."""

	def __init__(
		self,
		nodes: list[Any],
		ttl_ms: int = 5000,
		retry_count: int = 3,
		retry_delay_ms: int = 50,
	) -> None:
		self._nodes = nodes
		self._ttl_ms = ttl_ms
		self._retry_count = retry_count
		self._retry_delay_ms = retry_delay_ms
		self._quorum = len(nodes) // 2 + 1
		self._tokens: dict[str, str] = {}

	def acquire(self, key: str) -> bool:
		"""
		Try to acquire the lock across all nodes.

		Returns True if quorum reached within TTL; releases partial locks and
		returns False otherwise.
		"""
		token = uuid.uuid4().hex
		for _ in range(self._retry_count):
			start_ms = int(time.monotonic() * 1000)
			acquired_nodes: list[Any] = []

			for node in self._nodes:
				try:
					result = node.set(key, token, nx=True, px=self._ttl_ms)
					if result:
						acquired_nodes.append(node)
				except Exception:
					pass

			elapsed_ms = int(time.monotonic() * 1000) - start_ms
			validity_ms = self._ttl_ms - elapsed_ms

			if len(acquired_nodes) >= self._quorum and validity_ms > 0:
				self._tokens[key] = token
				return True

			# Not enough nodes — release whatever we got
			self._release_partial(key, token, acquired_nodes)

			if self._retry_delay_ms > 0:
				time.sleep(self._retry_delay_ms / 1000)

		return False

	def release(self, key: str) -> None:
		"""
		Release the lock on all nodes.

		Only deletes the key when the stored value matches our token (safe
		release). Swallows errors from individual nodes.
		"""
		token = self._tokens.pop(key, None)
		if token is None:
			return
		self._release_partial(key, token, self._nodes)

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	def _release_partial(self, key: str, token: str, nodes: list[Any]) -> None:
		"""DEL key on each node only if it still holds our token."""
		for node in nodes:
			try:
				stored = node.get(key)
				if stored is None:
					continue
				if isinstance(stored, bytes):
					stored = stored.decode()
				if stored == token:
					node.delete(key)
			except Exception:
				pass
