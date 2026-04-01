"""
StreamWorker: XREADGROUP-based task claiming with ACK and PEL crash recovery.

Uses Redis Streams consumer groups for at-least-once delivery guarantees.
Critical: pass streams as a keyword dict to xreadgroup — fakeredis 2.34.1
raises TypeError on positional 'streams' argument.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from redis.exceptions import ResponseError

from mcp_agent_factory.agents.models import AgentTask

logger = logging.getLogger(__name__)


class StreamWorker:
	"""Consumer-group worker backed by a single Redis stream."""

	def __init__(self, client: Any, stream: str, group: str, consumer: str) -> None:
		self._client = client
		self._stream = stream
		self._group = group
		self._consumer = consumer

	def ensure_group(self) -> None:
		"""Create consumer group, ignoring BUSYGROUP if it already exists."""
		try:
			self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
		except ResponseError as exc:
			if "BUSYGROUP" not in str(exc):
				raise

	def publish(self, task: AgentTask) -> str:
		"""Append an AgentTask to the stream and return the message ID."""
		fields = {
			"task_id": task.id,
			"task_name": task.name,
			"task_payload": json.dumps(task.payload),
			"task_capability": task.required_capability,
		}
		msg_id = self._client.xadd(self._stream, fields)
		logger.debug(
			'{"event":"stream_publish","stream":"%s","msg_id":"%s","task_id":"%s"}',
			self._stream, msg_id, task.id,
		)
		return msg_id if isinstance(msg_id, str) else msg_id.decode()

	def claim_one(self) -> tuple[bytes, dict] | None:
		"""
		Claim the next undelivered message from the group.

		Returns (msg_id, fields) or None if the stream is empty.
		streams is passed as a keyword argument to avoid fakeredis TypeError.
		"""
		result = self._client.xreadgroup(
			self._group,
			self._consumer,
			streams={self._stream: ">"},
			count=1,
		)
		if not result:
			return None
		# result: [(stream_name, [(msg_id, fields), ...])]
		messages = result[0][1]
		if not messages:
			return None
		msg_id, fields = messages[0]
		logger.debug(
			'{"event":"stream_claim","stream":"%s","msg_id":"%s"}',
			self._stream, msg_id,
		)
		return msg_id, fields

	def ack(self, msg_id: bytes) -> None:
		"""Acknowledge a message, removing it from the PEL."""
		self._client.xack(self._stream, self._group, msg_id)
		logger.debug(
			'{"event":"stream_ack","stream":"%s","msg_id":"%s"}',
			self._stream, msg_id,
		)

	def recover(self, min_idle_ms: int, new_consumer: str) -> list[tuple[bytes, dict]]:
		"""
		Reclaim messages idle for >= min_idle_ms milliseconds.

		Lists the PEL then xclaims each entry for new_consumer.
		Returns list of (msg_id, fields) tuples.
		"""
		pending = self._client.xpending_range(
			self._stream, self._group, min="-", max="+", count=10
		)
		recovered: list[tuple[bytes, dict]] = []
		for entry in pending:
			msg_id = entry["message_id"]
			claimed = self._client.xclaim(
				self._stream, self._group, new_consumer, min_idle_ms, [msg_id]
			)
			for claimed_id, fields in claimed:
				recovered.append((claimed_id, fields))
				logger.debug(
					'{"event":"stream_recover","stream":"%s","msg_id":"%s","new_consumer":"%s"}',
					self._stream, claimed_id, new_consumer,
				)
		return recovered
