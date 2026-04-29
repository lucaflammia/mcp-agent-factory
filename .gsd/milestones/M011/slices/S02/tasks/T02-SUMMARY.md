---
id: T02
parent: S02
milestone: M011
key_files:
  - (none)
key_decisions:
  - (none)
duration: 
verification_result: passed
completed_at: 2026-04-29T04:50:53.135Z
blocker_discovered: false
---

# T02: 353 non-integration tests pass; 1 pre-existing httpx.ReadTimeout failure in test_m009_s05 unrelated to OTEL changes

**353 non-integration tests pass; 1 pre-existing httpx.ReadTimeout failure in test_m009_s05 unrelated to OTEL changes**

## What Happened

Ran full pytest suite with -m 'not integration'. 353 passed, 1 failed (test_live_multiple_sequential_calls_emit_separate_usage_events in test_m009_s05.py — httpx.ReadTimeout against a live Ollama endpoint, pre-existing), 2 skipped, 14 deselected. Our 6 new OTEL tests are included in the 353.

## Verification

pytest tests/ -m 'not integration' -q → 353 passed, 1 pre-existing failure

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest tests/ -m 'not integration' -q --tb=short` | 0 | 353 passed, 1 pre-existing failure (httpx.ReadTimeout in test_m009_s05, unrelated to OTEL) | 146540ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

None.
