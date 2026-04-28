# M009: Model Agnosticism & Token Economy

**Vision:** Eliminate vendor lock-in and optimize operational costs by implementing a model-agnostic UnifiedRouter, a negative-permissions PII gate, a cosine-similarity context pruner, async prompt caching, token cost tracking, and Caddy TLS — so the ThinkPad operates as a self-sufficient AI workstation with cloud providers used opportunistically and sensitive data never leaving the local network.

**Success Criteria:**
- UnifiedRouter dispatches to OpenAI, Anthropic, or Ollama based on env config — no code change to switch providers
- Simulated OpenAI 429 triggers automatic Ollama fallback; both events recorded in EventLog
- Fields not in `MCP_ALLOWED_FIELDS` are scrubbed before leaving the local network
- Only semantically relevant chunks (cosine similarity above threshold) are passed to the LLM
- `token.usage` events with `model`, `input_tokens`, `output_tokens`, `cost_usd`, `sub` readable from EventLog
- Gateway reachable at `https://localhost` via Caddy reverse proxy in docker-compose stack

## Key Risks / Unknowns

- Ollama HTTP API shape may differ from assumed endpoint — wrong shape breaks the fallback chain
- AsyncIdempotencyGuard prompt hash instability — non-deterministic hashing causes cache misses on identical prompts
- Cosine similarity threshold miscalibration — needs empirical tuning during S03
- `MCP_ALLOWED_FIELDS` default too narrow or broad — calibrate during S02 integration testing

## Proof Strategy

- Ollama API compatibility → retire in S01 by proving OllamaHandler completes a real tool call against local Ollama
- AsyncIdempotencyGuard hash stability → retire in S04 by proving identical prompt yields cache hit across two sequential requests
- Cosine similarity threshold → retire in S03 by proving off-topic chunk dropped, on-topic chunk passes, threshold configurable
- MCP_ALLOWED_FIELDS defaults → retire in S02 by proving email blocked with default list; env var override passes previously blocked field

## Verification Classes

- Contract verification: unit tests for UnifiedRouter, PIIGate, ContextPruner, AsyncIdempotencyGuard with stubs/fakeredis
- Integration verification: UnifiedRouter → EventLog → Redis wired and verified; token.usage events readable per sub
- Operational verification: docker-compose up brings Caddy + gateway; live Ollama fallback confirmed with real subprocess call recorded in EventLog
- UAT / human verification: `curl https://localhost/health` returns 200; manual tool call shows fallback chain in EventLog

## Milestone Definition of Done

This milestone is complete only when all are true:

- All 5 slices complete and full test suite passes (unit + integration + live acceptance)
- `docker-compose up` brings gateway reachable at `https://localhost` via Caddy
- Live Ollama fallback confirmed: simulated OpenAI 429 → Ollama completion → `token.usage` in EventLog
- PII gate blocks sensitive fields; `MCP_ALLOWED_FIELDS` env var configurable
- Context pruner drops irrelevant chunks in integration test
- `token.usage` events readable per `sub` from EventLog
- All active M009 requirements (R032–R040) validated

## Requirement Coverage

- Covers: R032, R033, R034, R035, R036, R037, R038, R039, R040
- Leaves for later: cost dashboards (R_d1), allow-list UI (R_d2)
- Orphan risks: none

---

## Slices

- [x] **S01: Unified Router & Provider Handlers** `risk:high` `depends:[]`
  > After this: UnifiedRouter dispatches an echo-tool call to AnthropicHandler; simulated 429 triggers Ollama fallback; both token.usage events visible in EventLog (integration-verified with fakeredis + live Ollama)

- [x] **S02: PII Gate & Negative-Permissions Middleware** `risk:medium` `depends:[S01]`
  > After this: request with email in args is blocked at ValidationGate with generic message; request with only query passes through; MCP_ALLOWED_FIELDS env var override works

- [x] **S03: Context Pruner with Cosine Filtering** `risk:medium` `depends:[S01]`
  > After this: vector chunk with cosine similarity below threshold is dropped; on-topic chunk passes; empty-context fallthrough proceeds without error

- [x] **S04: Async Prompt Cache & Token Cost Tracking** `risk:low` `depends:[S01]`
  > After this: identical prompt returns cached result in under 1ms; token.usage events readable from EventLog per sub; cache write failure logged but does not fail the request

- [x] **S05: TLS + Caddy + Live Ollama Integration** `risk:medium` `depends:[S01,S02,S03,S04]`
  > After this: docker-compose up brings gateway at https://localhost; live fallback chain (simulated OpenAI 429 → Ollama completion) confirmed with token.usage events in EventLog

---

## Boundary Map

### S01 → S02, S03, S04

Produces:
- `gateway/router.py` — `UnifiedRouter`, `MCPRequest`, `ProviderError`, `OpenAIHandler`, `AnthropicHandler`, `OllamaHandler`
- `gateway/service_layer.py` — `InternalServiceLayer.handle()` calling `UnifiedRouter` (replaces `_dispatch`)
- EventLog `token.usage` event schema: `{model, input_tokens, output_tokens, cost_usd, sub}`

Consumes:
- nothing (first slice)

### S02 → S05

Produces:
- `gateway/validation.py` — `ValidationGate` extended with `PIIGate.scrub(args, allow_list)` negative-permissions check
- Regex patterns: email, API key signatures, private IPs, JWT-shaped strings

Consumes from S01:
- `MCPRequest` — args dict that PIIGate scrubs before passing to router

### S03 → S05

Produces:
- `gateway/pruner.py` — `ContextPruner.prune(query, chunks, embedder, threshold)` returning filtered chunk list

Consumes from S01:
- `MCPRequest` — query field used as embedding input
- `Embedder` protocol from `knowledge/embedder.py`

### S04 → S05

Produces:
- `streams/async_idempotency.py` — `AsyncIdempotencyGuard` with `async get(key)` / `set(key, value)` interface
- EventLog integration: `token.usage` event appended per handler call

Consumes from S01:
- `EventLog.append()` async interface from `streams/eventlog.py`
- `MCPRequest` — prompt hash derived from `(tool_name, args)` tuple

### S05 (integration closure)

Produces:
- `docker-compose.yml` — `caddy` service proxying `:443 → gateway:8000`
- `Caddyfile` — minimal reverse proxy config
- Live acceptance test: OpenAI 429 → Ollama → EventLog evidence

Consumes from S01–S04:
- Full assembled system: UnifiedRouter + PIIGate + ContextPruner + AsyncIdempotencyGuard + token.usage EventLog

---

## Horizontal Checklist

- [ ] Every active R### re-read against new code — still fully satisfied?
- [ ] Every D### from prior milestones re-evaluated — still valid at new scope?
- [ ] Graceful shutdown / cleanup on termination verified
- [ ] Auth boundary documented — what's protected vs public
- [ ] Reconnection / retry strategy verified for every external dependency (Ollama, Redis)
