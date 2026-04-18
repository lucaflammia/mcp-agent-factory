# S01 UAT: Docker Compose Stack

## Test When Ready

1. `docker-compose up -d` — all 6 services start without errors
2. `docker-compose ps` — all services show `healthy` or `running`
3. `redis-cli ping` → `PONG`
4. `redis-cli -p 6381 ping` → `PONG`
5. `redis-cli -p 6382 ping` → `PONG`
6. `redis-cli -p 6383 ping` → `PONG`
7. `pytest -m integration --co` → lists tests with no marker warnings
8. `pytest` → 246 passed, no failures
