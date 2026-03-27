---
id: T03
parent: S03
milestone: M002
provides: []
requires: []
affects: []
key_files: ["tests/test_auth.py"]
key_decisions: ["autouse shared_key fixture injects fresh OctKey into both auth server and resource server per test, clears in-memory stores after each test — ensures test isolation without shared state", "_make_token helper allows crafting tokens with arbitrary aud/scope for confused deputy tests"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "python -m pytest tests/test_auth.py -v → 20 passed in 3.04s."
completed_at: 2026-03-27T08:09:07.279Z
blocker_discovered: false
---

# T03: 20 auth tests — PKCE flow, confused deputy protection, scope enforcement, session IDs — all passing in 3.04s.

> 20 auth tests — PKCE flow, confused deputy protection, scope enforcement, session IDs — all passing in 3.04s.

## What Happened
---
id: T03
parent: S03
milestone: M002
key_files:
  - tests/test_auth.py
key_decisions:
  - autouse shared_key fixture injects fresh OctKey into both auth server and resource server per test, clears in-memory stores after each test — ensures test isolation without shared state
  - _make_token helper allows crafting tokens with arbitrary aud/scope for confused deputy tests
duration: ""
verification_result: passed
completed_at: 2026-03-27T08:09:07.283Z
blocker_discovered: false
---

# T03: 20 auth tests — PKCE flow, confused deputy protection, scope enforcement, session IDs — all passing in 3.04s.

**20 auth tests — PKCE flow, confused deputy protection, scope enforcement, session IDs — all passing in 3.04s.**

## What Happened

Wrote 20 auth tests across 5 classes. autouse shared_key fixture provides per-test key injection and store cleanup. TestTokenExchange covers full PKCE flow, wrong verifier, one-time codes, and JWT claims. TestResourceServer proves confused deputy rejection (wrong aud), scope rejection, unauthenticated health, and malformed bearer. All 20 pass in 3.04s.

## Verification

python -m pytest tests/test_auth.py -v → 20 passed in 3.04s.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest tests/test_auth.py -v` | 0 | ✅ pass | 3040ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `tests/test_auth.py`


## Deviations
None.

## Known Issues
None.
