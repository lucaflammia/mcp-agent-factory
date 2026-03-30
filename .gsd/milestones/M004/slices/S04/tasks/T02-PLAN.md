---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T02: Final suite run + docs update

Run the full test suite and update KNOWLEDGE.md and PROJECT.md with M004 lessons and new capabilities.

## Inputs

- None specified.

## Expected Output

- `Updated .gsd/KNOWLEDGE.md`
- `Updated .gsd/PROJECT.md`

## Verification

pytest tests/ -q --tb=no
