---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T03: Run full test suite — confirm no regressions

Run pytest excluding integration tests to confirm the metrics wiring didn't break anything.

## Inputs

- None specified.

## Expected Output

- `All non-integration tests pass`

## Verification

pytest -m 'not integration' exits 0
