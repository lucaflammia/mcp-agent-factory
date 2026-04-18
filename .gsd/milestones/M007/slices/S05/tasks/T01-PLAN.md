# T01: Full regression + integration smoke

**Slice:** S05
**Milestone:** M007

## Goal

Run `pytest` and `pytest -m integration` against the complete codebase. Fix any import errors, fixture issues, or regressions found. Write M007-SUMMARY.md on success.

## Must-Haves

### Truths
- `pytest` exits 0 with ≥ 246 tests passing, 0 failures
- `pytest -m integration` exits 0 with all integration tests passing (requires live Docker stack)
- `pip install -e ".[infra]"` succeeds — no missing package errors

### Artifacts
- `.gsd/milestones/M007/M007-SUMMARY.md` — milestone completion summary

### Key Links
- All M007 source and test files must be importable without errors

## Steps

1. `pip install -e ".[infra]"` — verify aiokafka and redis install cleanly
2. `pytest --tb=short -q` — confirm all unit tests pass; fix any regressions
3. `docker-compose up -d` — start the live stack
4. `pytest -m integration --tb=short -v` — run all integration tests; fix any connectivity or fixture issues
5. Write `M007-SUMMARY.md` with completion details
6. Update `STATE.md` to phase=complete

## Context
- If `docker-compose up -d` is not available in the test environment, document the skip behaviour and confirm unit tests alone pass
- Regressions from aiokafka being importable: the `try/except ImportError` guard in `kafka_adapter.py` ensures no breakage even when aiokafka IS installed
