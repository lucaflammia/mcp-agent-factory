# S03: Demo Script and Rehearsal Hardening — UAT

**Milestone:** M012
**Written:** 2026-05-01T14:56:24.234Z

# S03 UAT: Demo Script and Rehearsal Hardening\n\n## Phase 1: Privacy-First RAG\n- MCP_DEV_MODE=1 docker compose --profile full up -d\n- ./scripts/demo.sh\n- Expected: Phase 1 shows summary, provider, token counts, chunk counts\n- Status: Verified via contract test + syntax check\n\n## Phase 2: Jaeger Trace\n- Expected: Phase 2 prints Jaeger URL with correct service and operation params\n- Status: Static output, verified by code review\n\n## Phase 3: Provider Switch\n- Expected: Phase 3 with provider=openai (no OPENAI_API_KEY) shows -32602 error\n- Status: PASS — contract test test_agents_analyze_missing_provider_key confirms -32602
