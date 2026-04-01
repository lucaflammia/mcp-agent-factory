"""Idempotency primitives: IdempotencyGuard, DistributedLock, OutboxRelay."""
from __future__ import annotations

import uuid
from typing import Any, Callable


class IdempotencyGuard:
	"""Redis SET NX pre-check idempotency (R008) and result cache (R014)."""

	def __init__(self, redis_client: Any, ttl: int = 300) -> None:
		self._r = redis_client
		self._ttl = ttl

	def already_seen(self, task_id: str) -> bool:
		"""Return True if task_id was seen before (key already existed)."""
		result = self._r.set(task_id, "1", nx=True, ex=self._ttl)
		return result is None  # None → key existed; True → first time

	def cache_result(self, task_id: str, result: str) -> None:
		"""Store completed result against task_id."""
		self._r.set(f"{task_id}:result", result, ex=self._ttl)

	def get_cached(self, task_id: str) -> str | None:
		"""Return cached result or None if not present."""
		value = self._r.get(f"{task_id}:result")
		if value is None:
			return None
		return value.decode() if isinstance(value, bytes) else value


class DistributedLock:
	"""Single-node SET NX EX locking (R009, D010)."""

	def __init__(self, redis_client: Any, ttl: int = 10) -> None:
		self._r = redis_client
		self._ttl = ttl
		self._tokens: dict[str, str] = {}

	def acquire(self, key: str) -> bool:
		"""Try to acquire lock. Returns True if acquired."""
		token = str(uuid.uuid4())
		result = self._r.set(key, token, nx=True, ex=self._ttl)
		if result:
			self._tokens[key] = token
			return True
		return False

	def release(self, key: str) -> None:
		"""Release lock only if we still own it."""
		token = self._tokens.get(key)
		if token is None:
			return
		stored = self._r.get(key)
		if stored is None:
			self._tokens.pop(key, None)
			return
		if isinstance(stored, bytes):
			stored = stored.decode()
		if stored == token:
			self._r.delete(key)
		self._tokens.pop(key, None)


class OutboxRelay:
	"""In-process transactional outbox (R010)."""

	def __init__(self) -> None:
		self._queue: list[tuple[Callable, Callable]] = []

	def add(self, state_fn: Callable, dispatch_fn: Callable) -> None:
		self._queue.append((state_fn, dispatch_fn))

	def flush(self) -> None:
		"""Call all state_fns then dispatch_fns in order, then clear."""
		for state_fn, dispatch_fn in self._queue:
			state_fn()
			dispatch_fn()
		self._queue.clear()
