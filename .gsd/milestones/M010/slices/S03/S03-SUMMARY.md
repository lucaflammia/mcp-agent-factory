---
id: S03
parent: M010
milestone: M010
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
completed_at: 2026-04-28T15:30:15.442Z
blocker_discovered: false
---

# S03: Demo Script & Integration Proof

**demo_analyst.py runs three-phase output with live provider switching against a real PDF**

## What Happened

S03 added scripts/demo_analyst.py exercising the full M010 stack end-to-end: Phase 1 shows token reduction via ContextPruner, Phase 2 outputs KPIs and risks from the PDF, Phase 3 shows a provider footer reflecting LLM_PROVIDER. data/samples/finance_q3_2024.pdf is a real 2-page PDF with extractable financial text.

## Verification

25 new tests across S01+S02 pass; full suite 348 passed, 13 skipped.

## Requirements Advanced

None.

## Requirements Validated

None.

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

- `scripts/demo_analyst.py` — 
- `data/samples/finance_q3_2024.pdf` — 
