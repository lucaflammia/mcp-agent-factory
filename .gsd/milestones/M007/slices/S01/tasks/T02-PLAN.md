# T02: conftest_integration.py + pytest marker registration

**Slice:** S01
**Milestone:** M007

## Goal

Write `tests/conftest_integration.py` exporting `real_redis`, `real_redis_cluster`, and `real_kafka_bootstrap` fixtures that skip gracefully when the Docker stack is not running. Register the `integration` pytest marker so `-m integration` is clean.

## Must-Haves

### Truths
- `pytest --co -m integration` exits 0 with no warnings about unknown markers
- `pytest` (without `-m integration`) passes all 246 existing tests — conftest_integration fixtures do not interfere
- Calling `real_redis` when Redis is not running produces `pytest.skip("Redis not available")`, not a connection error traceback
- Calling `real_redis_cluster` returns a list of exactly 3 `redis.Redis` clients (ports 6381, 6382, 6383)
- Calling `real_kafka_bootstrap` returns `"localhost:9092"` (string) when Kafka is up, skips when not

### Artifacts
- `tests/conftest_integration.py` — min 40 lines, exports 3 fixtures with `@pytest.fixture`
- `pyproject.toml` `[tool.pytest.ini_options]` — `markers = ["integration: marks tests as requiring live Docker stack"]`

### Key Links
- `real_redis` → used by `test_m007_scaling.py` (S04) and `test_m007_redlock.py` (S03)
- `real_redis_cluster` → used by `test_m007_redlock.py` (S03)
- `real_kafka_bootstrap` → used by `test_m007_kafka.py` (S02)

## Steps

1. Add `[tool.pytest.ini_options] markers` list to `pyproject.toml`
2. Write `tests/conftest_integration.py` with `real_redis` fixture: try `redis.Redis(port=6379).ping()`, skip on `ConnectionError`
3. Write `real_redis_cluster` fixture: connect to ports 6381, 6382, 6383 individually; skip if any fails
4. Write `real_kafka_bootstrap` fixture: try `aiokafka.AIOKafkaProducer(bootstrap_servers="localhost:9092")` start/stop in an async helper; skip on `aiokafka.errors.KafkaConnectionError`; return the bootstrap string
5. Verify `pytest -x --ignore=tests/conftest_integration.py` still passes (or just `pytest -x` — fixtures only run when requested)

## Context
- `conftest_integration.py` is a separate file from `conftest.py` to keep the existing fixture namespace clean
- The `real_kafka_bootstrap` fixture needs `pytest-asyncio` for the async ping — it's already a dev dep
