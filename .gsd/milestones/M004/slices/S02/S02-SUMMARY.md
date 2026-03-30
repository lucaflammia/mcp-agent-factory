---
id: S02
parent: M004
milestone: M004
provides:
  - Proven PKCE S256 round-trip test pattern for future auth work
  - Proven 401/403 gateway enforcement
requires:
  - slice: S01
    provides: gateway_app with auth middleware
affects:
  - S03
key_files:
  - tests/test_m004_auth_pkce.py
key_decisions:
  - All auth enforcement confirmed from existing auth/server.py + auth/resource.py — no new auth code needed
patterns_established:
  - shared_key autouse fixture clears _clients and _codes between tests to prevent cross-test pollution
observability_surfaces:
  - Auth failures logged at WARNING in resource.py (existing, confirmed by tests)
drill_down_paths:
  - .gsd/milestones/M004/slices/S02/tasks/T01-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-30T06:50:00.795Z
blocker_discovered: false
---

# S02: PKCE Hardening + 401 on Missing/Invalid Token

**PKCE hardening test suite: 10 tests confirming full S256 round-trip and gateway 401/403 enforcement**

## What Happened

Closed the PKCE test coverage gap with 10 tests covering the full OAuth 2.1 code flow and gateway auth enforcement. No production code changes needed \u2014 the auth implementation was already correct.

## Verification

pytest tests/test_m004_auth_pkce.py -v: 10 passed

## Requirements Advanced

- R005 — 10 tests confirm PKCE S256 round-trip and gateway 401 enforcement

## Requirements Validated

- R005 — test_gateway_no_auth_returns_401, test_gateway_expired_token_returns_401, test_gateway_wrong_audience_returns_401 all pass

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

TokenRequest API shape differs from initial assumptions: uses client_secret, no redirect_uri. Corrected in tests.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `tests/test_m004_auth_pkce.py` — 10 tests: PKCE S256 round-trip, wrong verifier, plain method rejection, one-time code, gateway 401/403 enforcement
