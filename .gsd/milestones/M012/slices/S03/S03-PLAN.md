# S03: Demo Script and Rehearsal Hardening

**Goal:** Write demo.sh for zero-touch execution of all three demo phases (locked data RAG, Jaeger trace walkthrough, live provider switch with fail-fast error), and harden the full stack startup so docker compose up reliably reaches demo-ready state.
**Demo:** ./demo.sh runs Phase 1 (locked data), Phase 2 (Jaeger trace), Phase 3 (provider switch with -32602) without manual intervention

## Must-Haves

- ./demo.sh exits 0 for Phase 1 and Phase 2; Phase 3 produces -32602 JSON with message containing OPENAI_API_KEY; no manual steps required between phases.

## Proof Level

- This slice proves: ./demo.sh runs Phase 1, Phase 2, and Phase 3 without manual intervention; Phase 3 with LLM_PROVIDER=openai and no OPENAI_API_KEY produces a visible -32602 error naming the missing key.

## Integration Closure

Consumes agents/analyze endpoint from S01 and Jaeger spans from S02. Produces the demo artifact that is the milestone acceptance test.

## Verification

- Not provided.

## Tasks

- [x] **T01: Write demo.sh with three-phase execution** `est:30m`
  Create scripts/demo.sh that: (1) checks docker compose health (all services up, exits with clear message if not); (2) Phase 1 — POST agents/analyze with MCP_DEV_MODE=1 against the local PDF, pretty-prints the DocumentAnalysisResult summary; (3) Phase 2 — prints the Jaeger deep-link URL for the most recent trace (http://localhost:16686/search?service=mcp-gateway); (4) Phase 3 — repeats the agents/analyze call with LLM_PROVIDER=openai and no OPENAI_API_KEY set, shows the -32602 error response side-by-side with Phase 1 output. Uses only curl and jq — no Python dependencies.
  - Files: `scripts/demo.sh`
  - Verify: Run ./scripts/demo.sh against a running stack (MCP_DEV_MODE=1); Phase 1 shows analysis result; Phase 2 shows Jaeger URL; Phase 3 shows -32602 error with OPENAI_API_KEY in message.

- [x] **T02: Rehearsal run and hardening** `est:20m`
  Run ./scripts/demo.sh end-to-end against the full docker compose stack. Fix any timing, ordering, or config issues discovered. Common failure modes: gateway not ready when demo.sh starts (add a readiness wait loop), PDF path mismatch in the request payload, jq parse errors on unexpected response shapes. Document any env vars the presenter must set in a demo-setup comment block at the top of demo.sh.
  - Files: `scripts/demo.sh`
  - Verify: Two consecutive clean runs of ./scripts/demo.sh with no manual intervention and no errors in Phase 1 or Phase 2.

## Files Likely Touched

- scripts/demo.sh
