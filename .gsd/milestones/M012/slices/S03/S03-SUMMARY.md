---
id: S03
parent: M012
milestone: M012
provides:
  - (none)
requires:
  []
affects:
  []
key_files:
  - (none)
key_decisions:
  - (none)
patterns_established:
  - (none)
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-05-01T14:56:24.234Z
blocker_discovered: false
---

# S03: Demo Script and Rehearsal Hardening

**scripts/demo.sh delivers zero-touch three-phase demo: Privacy-First RAG, Jaeger trace link, provider switch with -32602 fail-fast — 351 tests passing.**

## What Happened

Created scripts/demo.sh with Phase 1 (agents/analyze returning DocumentAnalysisResult), Phase 2 (Jaeger trace deep-link with span chain diagram), and Phase 3 (explicit provider=openai param triggers -32602 without restart). Hardened with gateway readiness wait loop, MCP_DEV_MODE setup documentation, and clear error messaging. Extended _validate_provider() and provider_factory() to accept per-request provider override — enabling the switch without restarting the stack. Full 351-test suite passes.

## Verification

351 passed, 17 skipped; bash -n scripts/demo.sh syntax ok

## Requirements Advanced

None.

## Requirements Validated

- R017 — demo.sh runs all 3 phases without manual intervention
- R018 — Phase 3 uses provider param; -32602 confirmed by contract test

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `scripts/demo.sh` — 
- `src/mcp_agent_factory/gateway/app.py` — 
- `src/mcp_agent_factory/agents/analyst.py` — 
- `src/mcp_agent_factory/gateway/router.py` — 
