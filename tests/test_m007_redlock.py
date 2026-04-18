"""
M007/S03 — RedlockClient integration tests.

Require 3 live Redis nodes on ports 6381, 6382, 6383. Skip automatically
when not available. Start with: docker-compose up -d redis-node-1 redis-node-2 redis-node-3
"""
import uuid

import pytest

from mcp_agent_factory.streams.redlock import RedlockClient


def _unique_key(base: str) -> str:
	return f"{base}:{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _cleanup(real_redis_cluster):
	"""DEL all test keys from all nodes after each test."""
	yield
	# best-effort cleanup — ignore errors
	for node in real_redis_cluster:
		try:
			keys = node.keys("test:lock:*")
			if keys:
				node.delete(*keys)
		except Exception:
			pass


@pytest.mark.integration
def test_redlock_acquires_quorum(real_redis_cluster):
	"""Acquire on fresh key returns True; after release, re-acquire also returns True."""
	client = RedlockClient(real_redis_cluster, ttl_ms=5000)
	key = _unique_key("test:lock:quorum")

	assert client.acquire(key) is True
	client.release(key)

	# Second acquire on released key should succeed
	assert client.acquire(key) is True
	client.release(key)


@pytest.mark.integration
def test_redlock_contention_serialises(real_redis_cluster):
	"""Two clients racing for the same key: exactly one wins, the other loses."""
	key = _unique_key("test:lock:contention")
	client_a = RedlockClient(real_redis_cluster, ttl_ms=5000, retry_count=1)
	client_b = RedlockClient(real_redis_cluster, ttl_ms=5000, retry_count=1)

	result_a = client_a.acquire(key)
	# While A holds it, B should fail
	result_b = client_b.acquire(key)

	assert result_a is True
	assert result_b is False

	# Cleanup
	client_a.release(key)


@pytest.mark.integration
def test_redlock_releases_on_all_nodes(real_redis_cluster):
	"""After release(), the key is gone from all 3 Redis nodes."""
	client = RedlockClient(real_redis_cluster, ttl_ms=5000)
	key = _unique_key("test:lock:release")

	assert client.acquire(key) is True
	client.release(key)

	for node in real_redis_cluster:
		assert node.get(key) is None
