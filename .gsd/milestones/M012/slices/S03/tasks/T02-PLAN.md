---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T02: Rehearsal run and hardening

Run ./scripts/demo.sh end-to-end against the full docker compose stack. Fix any timing, ordering, or config issues discovered. Common failure modes: gateway not ready when demo.sh starts (add a readiness wait loop), PDF path mismatch in the request payload, jq parse errors on unexpected response shapes. Document any env vars the presenter must set in a demo-setup comment block at the top of demo.sh.

## Inputs

- `T01 demo.sh`
- `Running docker compose stack`

## Expected Output

- `demo.sh passes two consecutive clean runs`
- `Any required env vars documented in script header`
- `No manual steps between phases`

## Verification

Two consecutive clean runs of ./scripts/demo.sh with no manual intervention and no errors in Phase 1 or Phase 2.
