"""
M007/S02 — KafkaEventLog integration tests.

Require a live Kafka broker (port 9092). Skip automatically when not available.
Start the stack with: docker-compose up -d kafka

Topic names include a UUID suffix to prevent inter-test pollution across runs.
"""
import uuid

import pytest

from mcp_agent_factory.streams.kafka_adapter import KafkaEventLog


def _unique_topic(base: str) -> str:
	return f"{base}.{uuid.uuid4().hex[:8]}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kafka_append_read(real_kafka_bootstrap):
	"""Append one event; read it back; event dict matches."""
	topic = _unique_topic("m007.test.events")
	log = KafkaEventLog(bootstrap_servers=real_kafka_bootstrap)
	await log.start()
	try:
		event = {"task_id": "t1", "action": "start"}
		msg_id = await log.append(topic, event)
		assert isinstance(msg_id, str)

		results = await log.read(topic)
		assert len(results) == 1
		returned_id, returned_event = results[0]
		assert returned_event["task_id"] == "t1"
		assert returned_event["action"] == "start"
		assert returned_id == msg_id
	finally:
		await log.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kafka_ordering(real_kafka_bootstrap):
	"""Append 3 events; read all; they come back in append order."""
	topic = _unique_topic("m007.test.ordering")
	log = KafkaEventLog(bootstrap_servers=real_kafka_bootstrap)
	await log.start()
	try:
		events = [{"seq": i, "task_id": f"t{i}"} for i in range(3)]
		ids = []
		for evt in events:
			ids.append(await log.append(topic, evt))

		results = await log.read(topic)
		assert len(results) == 3
		for i, (_, returned_event) in enumerate(results):
			assert returned_event["seq"] == i
	finally:
		await log.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kafka_topic_isolation(real_kafka_bootstrap):
	"""Events on different topics do not cross-contaminate."""
	topic_search = _unique_topic("m007.tasks.search")
	topic_write = _unique_topic("m007.tasks.write")
	log = KafkaEventLog(bootstrap_servers=real_kafka_bootstrap)
	await log.start()
	try:
		await log.append(topic_search, {"task_id": "search-1", "type": "search"})
		await log.append(topic_write, {"task_id": "write-1", "type": "write"})

		search_results = await log.read(topic_search)
		write_results = await log.read(topic_write)

		assert len(search_results) == 1
		assert search_results[0][1]["type"] == "search"

		assert len(write_results) == 1
		assert write_results[0][1]["type"] == "write"
	finally:
		await log.stop()
