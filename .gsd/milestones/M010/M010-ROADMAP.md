# M010: Production Analyst & Provider Switch

**Vision:** Demonstrate a concrete business application on the MCP stack: an AnalystAgent that reads a real PDF locally via an MCP tool, prunes context, scrubs PII, and routes to an LLM via UnifiedRouter — with live provider switching between Claude, Gemini, and Ollama driven by a single env var.

## Success Criteria

- file_context_extractor MCP tool extracts text from a real PDF locally via pypdf
- GeminiHandler calls Gemini REST API via httpx, falls back to Ollama on missing key with EventLog warning
- LLM_PROVIDER env var re-read per request — handler order changes without restart
- AnalystAgent exercises the full extract → prune → scrub → route pipeline
- Existing test suite stays green; new unit tests for GeminiHandler and factory logic pass
- demo_analyst.py runs end-to-end: three-phase output with live provider switch

## Slices

- [ ] **S01: LLM Provider Infrastructure** `risk:high` `depends:[]`
  > After this: LLM_PROVIDER=gemini returns a Gemini response; switch to anthropic → Anthropic responds; GEMINI_API_KEY unset → EventLog warning + Ollama fallback; unit tests for GeminiHandler mapping and factory routing pass

- [ ] **S02: AnalystAgent Document Pipeline** `risk:medium` `depends:[S01]`
  > After this: AnalystAgent.run() with a PDF task calls the local tool, prunes context, scrubs PII, routes to UnifiedRouter — verified by tests with the sample PDF fixture

- [ ] **S03: Demo Script & Integration Proof** `risk:low` `depends:[S01,S02]`
  > After this: python scripts/demo_analyst.py runs end-to-end: Phase 1 token reduction, Phase 2 KPIs and risks, Phase 3 provider footer; switches LLM_PROVIDER and re-runs showing new provider

## Boundary Map

### S01 → S02\n\nProduces:\n- `GeminiHandler` class in `router.py` — `call(request) -> LLMResponse`\n- `provider_factory(env_var) -> list[LLMHandler]` function in `router.py`\n- `file_context_extractor` MCP tool — `extract(path, query) -> list[str]` (page snippets)\n- `pypdf` and `httpx` added to `pyproject.toml`\n\nConsumes:\n- nothing (first slice)\n\n### S02 → S03\n\nProduces:\n- `AnalystAgent.run(task: AnalysisTask) -> AnalysisResult` — upgraded pipeline interface\n- `data/samples/finance_q3_2024.pdf` — real sample PDF on disk\n\nConsumes from S01:\n- `provider_factory()` — called inside AnalystAgent to get the handler list\n- `file_context_extractor` — invoked as the local MCP tool step
