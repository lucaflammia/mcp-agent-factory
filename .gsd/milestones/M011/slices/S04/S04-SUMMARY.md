---
id: S04
parent: M011
milestone: M011
provides:
  - (none)
requires:
  []
affects:
  []
key_files:
  - (none)
key_decisions:
  - (none)
patterns_established:
  - (none)
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-04-29T05:02:00.356Z
blocker_discovered: false
---

# S04: Smoke test and README quickstart

**bash scripts/smoke_test.sh exits 0 against live stack; README quickstart is accurate**

## What Happened

The smoke test sent tools/list for its unauthenticated check, but that endpoint is intentionally public (read-only discovery). Fixed to test tools/call, which correctly rejects unauthenticated requests with a JSON-RPC auth error. All 8 smoke checks pass. README quickstart verified — all port references and commands match the live docker-compose stack.

## Verification

bash scripts/smoke_test.sh exits 0 (8 checks pass); README URLs and commands confirmed accurate

## Requirements Advanced

None.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `scripts/smoke_test.sh` — Fixed unauthenticated check to use tools/call instead of tools/list
