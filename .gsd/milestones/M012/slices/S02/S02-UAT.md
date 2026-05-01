# S02: Full OTel Pipeline Instrumentation — UAT

**Milestone:** M012
**Written:** 2026-05-01T14:48:15.171Z

# S02 UAT: Full OTel Pipeline Instrumentation\n\n## Trace Chain Expected in Jaeger\n```\nmcp.agents/analyze\n  └─ agent.pdf_extract   [pages_read, total_pages, chunk_count]\n  └─ agent.prune         [input_chunks, output_chunks, input_tokens, output_tokens]\n  └─ agent.pii_scrub     [input_tokens, output_tokens]\n  └─ agent.llm_route     [provider, input_tokens, output_tokens, cost_usd]\nagent.vector_store.search [owner_id, top_k, result_count]\n```\n\n## Verification\n- OTEL_TRACES_EXPORTER configured → spans visible in Jaeger at :16686\n- Tests pass with no-op tracer (no OTEL env vars needed)\n- Status: PASS (9/9 tests)
