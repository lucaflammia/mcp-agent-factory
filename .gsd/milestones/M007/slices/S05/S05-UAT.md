# S05 UAT: Integration & Regression

## Without Docker

1. `pytest` → 246 passed, 8 skipped (no failures)

## With Docker Stack

1. `docker-compose up -d`
2. `pytest -m integration` → 8 passed
3. `pytest` → 254 passed (all tests including integration)
