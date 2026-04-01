"""Circuit breaker for LLM and vector store calls (R011, R012, R013)."""
from __future__ import annotations

import time
from enum import Enum, auto
from typing import Any, Callable


class State(Enum):
	CLOSED = auto()
	OPEN = auto()
	HALF_OPEN = auto()


class CircuitBreaker:
	"""CLOSED→OPEN→HALF_OPEN state machine wrapping arbitrary callables."""

	def __init__(self, threshold: int = 3, recovery_timeout: float = 1.0) -> None:
		self._threshold = threshold
		self._recovery_timeout = recovery_timeout
		self._state = State.CLOSED
		self._failures = 0
		self._opened_at: float = 0.0

	@property
	def state(self) -> State:
		return self._state

	def call(self, fn: Callable, *args: Any, fallback: Any = None, **kwargs: Any) -> Any:
		if self._state == State.OPEN:
			if time.monotonic() - self._opened_at >= self._recovery_timeout:
				self._state = State.HALF_OPEN
			else:
				return fallback

		try:
			result = fn(*args, **kwargs)
		except Exception:
			self._failures += 1
			if self._state == State.HALF_OPEN or self._failures >= self._threshold:
				self._state = State.OPEN
				self._opened_at = time.monotonic()
			raise

		# success
		self._failures = 0
		self._state = State.CLOSED
		return result
