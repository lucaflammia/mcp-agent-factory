# S04: Idempotency + Circuit Breakers — UAT

**Milestone:** M006
**Written:** 2026-04-01T20:03:28.694Z

## UAT: S04 — Idempotency + Circuit Breakers\n\n### Test command\n```bash\nPYTHONPATH=src pytest tests/test_m006_reliability.py -v\n```\n\n### Expected result\n7 passed, 0 failed.\n\n### Test coverage\n| Test | Requirement |\n|------|-------------|\n| test_r008_idempotency_precheck | R008 |\n| test_r009_distributed_lock_acquire | R009 |\n| test_r014_result_cache_hit | R014 |\n| test_r010_outbox_relay | R010 |\n| test_r011_circuit_opens_after_n_failures | R011 |\n| test_r013_fallback_on_open_circuit | R013 |\n| test_r012_half_open_recovery | R012 |
