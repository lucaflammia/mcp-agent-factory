"""
EventLog abstraction: Protocol, InProcessEventLog, and topic helpers.

TopicRouter helpers produce deterministic topic/stream names:
  - session_topic(session_id)    → "session.<session_id>"
  - capability_topic(capability) → "capability.<capability>"
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topic helpers
# ---------------------------------------------------------------------------

def session_topic(session_id: str) -> str:
	"""Return the stream name for a given session."""
	return f"session.{session_id}"


def capability_topic(capability: str) -> str:
	"""Return the stream name for a given agent capability."""
	return f"capability.{capability}"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class EventLog(Protocol):
	"""Minimal append-read interface for an event log / stream backend."""

	async def append(self, topic: str, event: dict[str, Any]) -> str:
		"""Append *event* to *topic*; return opaque message ID."""
		...

	async def read(self, topic: str, offset: str = "0") -> list[tuple[str, dict[str, Any]]]:
		"""Read events from *topic* starting at *offset*.

		Returns a list of (message_id, event_dict) pairs.
		"""
		...


# ---------------------------------------------------------------------------
# In-process implementation (no external deps — good for tests & local dev)
# ---------------------------------------------------------------------------

class InProcessEventLog:
	"""Thread-safe, in-memory EventLog backed by asyncio.Lock."""

	def __init__(self) -> None:
		self._lock = asyncio.Lock()
		# topic → list of (msg_id, event)
		self._store: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
		self._counters: dict[str, int] = defaultdict(int)

	async def append(self, topic: str, event: dict[str, Any]) -> str:
		async with self._lock:
			idx = self._counters[topic]
			msg_id = f"{topic}-{idx}"
			self._store[topic].append((msg_id, dict(event)))
			self._counters[topic] += 1
			logger.debug(
				'{"event":"eventlog_append","topic":"%s","msg_id":"%s"}',
				topic, msg_id,
			)
			return msg_id

	async def read(self, topic: str, offset: str = "0") -> list[tuple[str, dict[str, Any]]]:
		async with self._lock:
			entries = self._store.get(topic, [])
			# offset is treated as a numeric index into the stored list
			try:
				start = int(offset)
			except (ValueError, TypeError):
				start = 0
			return list(entries[start:])
