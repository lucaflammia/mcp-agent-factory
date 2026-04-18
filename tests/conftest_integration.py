"""
Integration fixtures requiring a live Docker stack.

All fixtures skip automatically when the target service is not reachable,
so `pytest` (no -m flag) continues to pass without Docker running.

Start the stack with: docker-compose up -d
"""
import pytest
import redis as redis_lib


# ---------------------------------------------------------------------------
# Standalone Redis (port 6379) — StreamWorker, IdempotencyGuard
# ---------------------------------------------------------------------------

@pytest.fixture
def real_redis():
	"""Single Redis client on port 6379. Skips if not reachable."""
	client = redis_lib.Redis(host="localhost", port=6379, decode_responses=False)
	try:
		client.ping()
	except (redis_lib.exceptions.ConnectionError, ConnectionRefusedError):
		pytest.skip("Redis not available — run: docker-compose up -d redis")
	yield client
	client.close()


# ---------------------------------------------------------------------------
# Three-node Redis cluster (ports 6381-6383) — Redlock quorum
# ---------------------------------------------------------------------------

@pytest.fixture
def real_redis_cluster():
	"""
	List of 3 independent Redis clients on ports 6381, 6382, 6383.
	Skips if any node is not reachable.
	"""
	ports = [6381, 6382, 6383]
	clients = []
	for port in ports:
		c = redis_lib.Redis(host="localhost", port=port, decode_responses=False)
		try:
			c.ping()
		except (redis_lib.exceptions.ConnectionError, ConnectionRefusedError):
			pytest.skip(
				f"Redis node on port {port} not available — "
				"run: docker-compose up -d redis-node-1 redis-node-2 redis-node-3"
			)
		clients.append(c)
	yield clients
	for c in clients:
		c.close()


# ---------------------------------------------------------------------------
# Kafka bootstrap address — KafkaEventLog
# ---------------------------------------------------------------------------

@pytest.fixture
def real_kafka_bootstrap():
	"""
	Returns 'localhost:9092' when Kafka is reachable; skips otherwise.

	Uses a raw TCP connection check to avoid importing aiokafka at collection
	time (aiokafka may not be installed in the base dev environment).
	"""
	import socket
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.settimeout(2)
	try:
		s.connect(("localhost", 9092))
		s.close()
	except (ConnectionRefusedError, OSError):
		pytest.skip("Kafka not available — run: docker-compose up -d kafka")
	return "localhost:9092"
