---
id: S05
parent: M007
provides:
  - Full regression: 246 unit tests pass, 8 integration tests skip cleanly without Docker
  - Integration fixture discovery fixed: integration fixtures folded into conftest.py
  - M007 complete — all 5 slices shipped
key_files:
  - tests/conftest.py
key_decisions:
  - Integration fixtures merged into conftest.py rather than using pytest_plugins — pytest_plugins doesn't resolve sibling modules from within tests/ conftest files
verification_result: pass
completed_at: 2026-04-18T00:00:00Z
---

# S05: Integration & Regression

**246 unit tests green, 8 integration tests skip cleanly — M007 fully shipped.**

## What Happened

Integration test discovery was broken: `conftest_integration.py` is not auto-discovered by pytest (only `conftest.py` files are). Fixed by merging the integration fixtures (`real_redis`, `real_redis_cluster`, `real_kafka_bootstrap`) directly into `tests/conftest.py`. The `pytest_plugins` approach failed because pytest can't resolve sibling module names from within a `tests/` conftest.

Final result: `pytest` passes with 246 passed + 8 skipped (integration tests skip on missing Docker). All M001–M007 unit coverage intact.

## Deviations

`conftest_integration.py` remains as a documentation reference but is no longer the active fixture source — fixtures were merged into `conftest.py`.

## Files Created/Modified

- `tests/conftest.py` — integration fixtures appended
