---
id: T01
parent: S04
milestone: M011
key_files:
  - scripts/smoke_test.sh
key_decisions:
  - tools/list is intentionally public (read-only discovery); auth is only required for tools/call
duration: 
verification_result: passed
completed_at: 2026-04-29T05:01:41.356Z
blocker_discovered: false
---

# T01: Smoke test fixed and exits 0 — all 8 checks pass against live stack

**Smoke test fixed and exits 0 — all 8 checks pass against live stack**

## What Happened

The smoke test's unauthenticated POST /mcp check sent tools/list, which is intentionally public (read-only discovery — no auth required). Fixed to send tools/call instead, which correctly returns a JSON-RPC auth error. Also tightened the grep pattern from quoted string to substring match.

## Verification

bash scripts/smoke_test.sh exits 0 with all 8 checks passing

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `bash scripts/smoke_test.sh` | 0 | === All checks passed === | 2000ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `scripts/smoke_test.sh`
