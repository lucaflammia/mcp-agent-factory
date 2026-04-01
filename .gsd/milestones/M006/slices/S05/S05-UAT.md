# S05: Integration &amp; Regression — UAT

**Milestone:** M006
**Written:** 2026-04-01T20:16:40.502Z

## UAT: S05 — Integration &amp; Regression\n\n### Test command\n```bash\nPYTHONPATH=src pytest tests/ -v\n```\n\n### Expected result\n231 passed, 0 failed.\n\n### Integration test\n`tests/test_m006_integration.py::test_m006_full_pipeline` — exercises StreamWorker → IdempotencyGuard → DistributedLock → CircuitBreaker → OutboxRelay → InProcessEventLog in one scenario.
