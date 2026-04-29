---
id: T01
parent: S03
milestone: M010
key_files:
  - scripts/demo_analyst.py
  - data/samples/finance_q3_2024.pdf
key_decisions:
  - (none)
duration: 
verification_result: passed
completed_at: 2026-04-28T15:29:56.132Z
blocker_discovered: false
---

# T01: Demo script and sample PDF shipped

**Demo script and sample PDF shipped**

## What Happened

Added scripts/demo_analyst.py with three-phase terminal output. Added data/samples/finance_q3_2024.pdf as a real 2-page PDF with extractable financial text. Script demonstrates live provider switching via LLM_PROVIDER env var.

## Verification

25 new tests pass across S01+S02; full suite 348 passed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pytest tests/ -q --tb=no` | 0 | 348 passed, 13 skipped | 237000ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `scripts/demo_analyst.py`
- `data/samples/finance_q3_2024.pdf`
