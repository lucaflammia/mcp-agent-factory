---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T02: Full test suite regression check

Run the full pytest suite (excluding integration markers) to confirm no regressions from the telemetry wiring added in S01.

## Inputs

- `tests/`

## Expected Output

- `All non-integration tests pass (baseline: 348+)`

## Verification

pytest tests/ -m 'not integration' -v exits 0
