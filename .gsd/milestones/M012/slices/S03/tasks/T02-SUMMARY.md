---
id: T02
parent: S03
milestone: M012
key_files:
  - scripts/demo.sh
key_decisions:
  - (none)
duration: 
verification_result: passed
completed_at: 2026-05-01T14:56:10.970Z
blocker_discovered: false
---

# T02: Full suite passes; demo.sh hardened with readiness loop and env var documentation

**Full suite passes; demo.sh hardened with readiness loop and env var documentation**

## What Happened

Verified demo.sh syntax clean. Test suite 351 passed. Key hardening: gateway readiness wait with 30s timeout, clear error message if stack not up, MCP_DEV_MODE=1 documented as must-be-set-before-compose-up, Phase 3 uses per-request provider param instead of env var override so no gateway restart needed for the switch.

## Verification

351 passed, 17 skipped on full suite including the new agents_dispatch contract test

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python3.11 -m pytest tests/ --ignore=tests/test_otel_integration.py -q` | 0 | 351 passed, 17 skipped | 154570ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `scripts/demo.sh`
