# S05: Integration & Regression

**Goal:** Confirm the full test suite is green (unit + integration) and that M007 components interact correctly end-to-end. No new source code — this slice is verification only.

**Demo:** `pytest` passes (all M001–M007 unit tests, ~246+); `pytest -m integration` passes against live Docker stack.

## Must-Haves

- `pytest` (no marker) passes — all existing 246+ tests green, no regressions
- `pytest -m integration` passes — all 4 integration test files pass against live stack
- No import errors when all optional deps installed (`pip install -e ".[infra]"`)

## Tasks

- [ ] **T01: Full regression + integration smoke**
  Run both suites, fix any wiring issues found.

## Files Likely Touched

- Any file needing a minor fix found during regression
