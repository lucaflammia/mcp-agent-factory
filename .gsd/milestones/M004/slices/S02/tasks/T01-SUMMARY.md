---
id: T01
parent: S02
milestone: M004
provides: []
requires: []
affects: []
key_files: ["tests/test_m004_auth_pkce.py"]
key_decisions: ["TokenRequest shape confirmed from source: requires client_secret, no redirect_uri field"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "pytest tests/test_m004_auth_pkce.py -v: 10 passed"
completed_at: 2026-03-30T06:49:42.103Z
blocker_discovered: false
---

# T01: 10 PKCE hardening tests written and passing

> 10 PKCE hardening tests written and passing

## What Happened
---
id: T01
parent: S02
milestone: M004
key_files:
  - tests/test_m004_auth_pkce.py
key_decisions:
  - TokenRequest shape confirmed from source: requires client_secret, no redirect_uri field
duration: ""
verification_result: passed
completed_at: 2026-03-30T06:49:42.103Z
blocker_discovered: false
---

# T01: 10 PKCE hardening tests written and passing

**10 PKCE hardening tests written and passing**

## What Happened

Wrote 10 tests: PKCE S256 full round-trip, wrong verifier rejection, plain method rejection, one-time code use, and 5 gateway auth enforcement cases (no token, expired, wrong aud, malformed, valid, insufficient scope).

## Verification

pytest tests/test_m004_auth_pkce.py -v: 10 passed

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pytest tests/test_m004_auth_pkce.py -v` | 0 | ✅ pass — 10 passed | 720ms |


## Deviations

TokenRequest model uses client_secret not redirect_uri; /register returns 200 not 201. Tests adjusted to match actual API shape.

## Known Issues

None.

## Files Created/Modified

- `tests/test_m004_auth_pkce.py`


## Deviations
TokenRequest model uses client_secret not redirect_uri; /register returns 200 not 201. Tests adjusted to match actual API shape.

## Known Issues
None.
