# S04 UAT: Multi-Instance StreamWorker

## Test When Ready (requires docker-compose up -d redis)

1. `pytest -m integration tests/test_m007_scaling.py -v` → 2 passed
2. Confirm tests: `test_two_workers_no_double_execution`, `test_pel_recovery_across_processes`
