# S04: Smoke test and README quickstart

**Goal:** Smoke test exits 0 against live stack; README quickstart is accurate
**Demo:** bash scripts/smoke_test.sh exits 0 against a running stack; README quickstart accurate

## Must-Haves

- bash scripts/smoke_test.sh exits 0; README quickstart matches actual commands

## Proof Level

- This slice proves: Not provided.

## Integration Closure

Not provided.

## Verification

- Not provided.

## Tasks

- [x] **T01: Fix and verify smoke test** `est:10m`
  smoke_test.sh checked tools/list for 401 but that endpoint is intentionally public (read-only discovery). Fix to check tools/call for the auth error. Confirm exits 0 against live stack.
  - Files: `scripts/smoke_test.sh`
  - Verify: bash scripts/smoke_test.sh exits 0

- [x] **T02: Verify README quickstart accuracy** `est:5m`
  Read the Docker quickstart section and confirm all commands and URLs match reality: docker compose --profile full up, smoke_test.sh, service URLs.
  - Files: `README.md`
  - Verify: All commands and URLs in quickstart section are accurate

## Files Likely Touched

- scripts/smoke_test.sh
- README.md
