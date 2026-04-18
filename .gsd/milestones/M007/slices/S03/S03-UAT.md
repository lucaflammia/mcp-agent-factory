# S03 UAT: Redlock 3-Node Quorum

## Test When Ready (requires docker-compose up -d redis-node-1 redis-node-2 redis-node-3)

1. `pytest -m integration tests/test_m007_redlock.py -v` → 3 passed
2. Confirm tests: `test_redlock_acquires_quorum`, `test_redlock_contention_serialises`, `test_redlock_releases_on_all_nodes`
