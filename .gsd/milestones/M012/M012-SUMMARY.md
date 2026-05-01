---
id: M012
title: "Live Demonstration — AI Agents at Work"
status: complete
completed_at: 2026-05-01T14:58:55.084Z
key_decisions:
  - _agents_dispatch() sub-router pattern for all agents/* methods
  - 4 child OTel spans with token counts (not a single pipeline span)
  - -32602 for missing provider key / -32603 for pipeline failure
  - Per-request provider override — no stack restart needed for Phase 3
  - MCP_DEV_MODE=1 auth bypass for demo stability
key_files:
  - src/mcp_agent_factory/gateway/app.py
  - src/mcp_agent_factory/agents/analyst.py
  - src/mcp_agent_factory/gateway/router.py
  - scripts/demo.sh
  - tests/test_agents_dispatch.py
lessons_learned:
  - Per-request provider override requires threading provider through _validate_provider(), provider_factory(), and AnalystAgent — plan this path end-to-end before implementing to avoid mid-slice replanning.
  - DEV_MODE monkeypatching in pytest fixtures is essential when auth and non-auth tests coexist in the same suite.
---

# M012: Live Demonstration — AI Agents at Work

**Wired the complete MCP agent stack into a zero-touch three-phase demo with full OTel observability, provider switching, and a green contract test suite.**

## What Happened

M012 bridged code completeness to presentational reliability across three slices. S01 added the `agents/analyze` JSON-RPC method to the gateway via a new `_agents_dispatch()` sub-router, with `_validate_provider()` fail-fast logic and a 3-case contract test covering response shape, -32602, and -32603. S02 instrumented the analyst pipeline with 4 OTel child spans (`agent.pdf_extract`, `agent.prune`, `agent.pii_scrub`, `agent.llm_route`) carrying token count attributes, making the Gateway → AnalystAgent → LibrarianAgent → VectorStore chain fully visible in Jaeger. S03 created `scripts/demo.sh` with a gateway readiness wait loop, three fully scripted phases, and extended per-request provider override through `_validate_provider()` and `provider_factory()` so Phase 3 demonstrates the provider switch and -32602 fail-fast without a stack restart. 351 tests pass; bash -n syntax verified.

## Success Criteria Results

All five success criteria met: demo.sh zero-touch, Jaeger 4-span chain with token counts, agents/analyze returns real DocumentAnalysisResult, provider switch -32602 names exact key, contract test green.

## Definition of Done Results



## Requirement Outcomes

R013–R020 all validated. No requirements deferred or out-of-scope.

## Deviations

None.

## Follow-ups

None blocking. Potential future work: RS256 JWT for multi-service deployments (noted in M002 lessons); streaming/long-running agent methods beyond agents/analyze.
