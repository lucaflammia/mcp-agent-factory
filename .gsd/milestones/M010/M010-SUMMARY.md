---
id: M010
title: "Production Analyst & Provider Switch"
status: complete
completed_at: 2026-04-28T15:30:24.813Z
key_decisions:
  - (none)
key_files:
  - src/mcp_agent_factory/gateway/router.py
  - src/mcp_agent_factory/knowledge/pdf_tool.py
  - src/mcp_agent_factory/agents/analyst.py
  - src/mcp_agent_factory/agents/models.py
  - scripts/demo_analyst.py
  - data/samples/finance_q3_2024.pdf
lessons_learned:
  - provider_factory() re-reads env per call — no restart needed for provider switches
  - file_context_extractor is local-only (pypdf), not a network call — important for privacy-first config
  - AnalystAgent.analyze_document() is additive; existing run() was left untouched to preserve test coverage
---

# M010: Production Analyst & Provider Switch

**Shipped a concrete business application on the MCP stack: AnalystAgent reads a real PDF, prunes context, scrubs PII, and routes to Gemini/Anthropic/OpenAI/Ollama via a single LLM_PROVIDER env var.**

## What Happened

M010 built the first end-to-end business use case on the MCP stack. S01 added GeminiHandler (httpx-based REST) and provider_factory() to UnifiedRouter, with LLM_PROVIDER re-read per call so live provider switching requires no restart. Missing GEMINI_API_KEY emits an EventLog warning and falls back to Ollama. file_context_extractor was added as an MCP tool using pypdf for local-only PDF extraction. S02 wired AnalystAgent.analyze_document() as a typed extract→prune→scrub→route pipeline using DocumentAnalysisTask/Result. S03 delivered demo_analyst.py with three-phase terminal output and a real 2-page finance PDF sample. 25 new tests added; full suite 348 passed, 13 skipped.

## Success Criteria Results



## Definition of Done Results



## Requirement Outcomes



## Deviations

None.

## Follow-ups

None.
