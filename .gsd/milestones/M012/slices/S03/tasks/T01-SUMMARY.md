---
id: T01
parent: S03
milestone: M012
key_files:
  - scripts/demo.sh
  - src/mcp_agent_factory/gateway/app.py
  - src/mcp_agent_factory/agents/analyst.py
  - src/mcp_agent_factory/gateway/router.py
key_decisions:
  - (none)
duration: 
verification_result: passed
completed_at: 2026-05-01T14:56:02.631Z
blocker_discovered: false
---

# T01: Wrote scripts/demo.sh with three-phase zero-touch execution

**Wrote scripts/demo.sh with three-phase zero-touch execution**

## What Happened

Created scripts/demo.sh covering Phase 1 (agents/analyze → pretty-printed DocumentAnalysisResult), Phase 2 (Jaeger trace deep-link URL with span chain diagram), Phase 3 (provider=openai param triggers -32602 without OPENAI_API_KEY). Uses only curl and jq. Gateway readiness wait loop included. Also: refactored _validate_provider() to accept an explicit provider param; added optional provider field to DocumentAnalysisTask; provider_factory() accepts provider override; _agents_dispatch validates when explicit provider given or DEV_MODE is off.

## Verification

bash -n scripts/demo.sh → syntax ok; full test suite 351 passed 17 skipped

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `bash -n scripts/demo.sh` | 0 | syntax ok | 50ms |
| 2 | `python3.11 -m pytest tests/ --ignore=tests/test_otel_integration.py -q` | 0 | 351 passed, 17 skipped | 154570ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `scripts/demo.sh`
- `src/mcp_agent_factory/gateway/app.py`
- `src/mcp_agent_factory/agents/analyst.py`
- `src/mcp_agent_factory/gateway/router.py`
