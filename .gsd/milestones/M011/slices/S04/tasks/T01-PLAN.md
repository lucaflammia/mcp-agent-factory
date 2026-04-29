---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T01: Fix and verify smoke test

smoke_test.sh checked tools/list for 401 but that endpoint is intentionally public (read-only discovery). Fix to check tools/call for the auth error. Confirm exits 0 against live stack.

## Inputs

- `src/mcp_agent_factory/gateway/app.py`

## Expected Output

- `=== All checks passed ===`

## Verification

bash scripts/smoke_test.sh exits 0
