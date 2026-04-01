"""
KafkaEventLog: aiokafka-backed EventLog stub.

The aiokafka import is guarded so the package remains importable when
aiokafka is not installed (e.g. in lightweight test environments).

Usage::

    from mcp_agent_factory.streams.kafka_adapter import KafkaEventLog
    log = KafkaEventLog(bootstrap_servers="localhost:9092")
    await log.start()
    msg_id = await log.append("capability.general", {"task_id": "x"})
    await log.stop()

If aiokafka is absent, instantiating KafkaEventLog raises RuntimeError.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
	from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import]
	_AIOKAFKA_AVAILABLE = True
except ImportError:  # pragma: no cover
	_AIOKAFKA_AVAILABLE = False


class KafkaEventLog:
	"""EventLog backed by Apache Kafka via aiokafka (optional dependency)."""

	def __init__(self, bootstrap_servers: str = "localhost:9092") -> None:
		if not _AIOKAFKA_AVAILABLE:
			raise RuntimeError(
				"aiokafka is not installed. "
				"Install it with: pip install aiokafka"
			)
		self._bootstrap_servers = bootstrap_servers
		self._producer: Any = None

	async def start(self) -> None:
		"""Start the underlying Kafka producer."""
		self._producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
		await self._producer.start()
		logger.info(
			'{"event":"kafka_producer_started","bootstrap_servers":"%s"}',
			self._bootstrap_servers,
		)

	async def stop(self) -> None:
		"""Flush and stop the Kafka producer."""
		if self._producer is not None:
			await self._producer.stop()
			logger.info('{"event":"kafka_producer_stopped"}')

	async def append(self, topic: str, event: dict[str, Any]) -> str:
		"""Publish *event* as JSON to *topic*; return the Kafka offset as str."""
		if self._producer is None:
			raise RuntimeError("KafkaEventLog.start() must be called before append()")
		value = json.dumps(event).encode()
		record_metadata = await self._producer.send_and_wait(topic, value)
		msg_id = str(record_metadata.offset)
		logger.debug(
			'{"event":"kafka_append","topic":"%s","offset":"%s"}',
			topic, msg_id,
		)
		return msg_id

	async def read(self, topic: str, offset: str = "0") -> list[tuple[str, dict[str, Any]]]:
		"""Read events from *topic* from *offset* (simple single-poll fetch)."""
		if not _AIOKAFKA_AVAILABLE:
			raise RuntimeError("aiokafka is not installed")
		start_offset = int(offset)
		consumer = AIOKafkaConsumer(
			topic,
			bootstrap_servers=self._bootstrap_servers,
		)
		await consumer.start()
		results: list[tuple[str, dict[str, Any]]] = []
		try:
			async for msg in consumer:
				if msg.offset < start_offset:
					continue
				results.append((str(msg.offset), json.loads(msg.value)))
		finally:
			await consumer.stop()
		return results
