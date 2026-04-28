---
milestone: M009
title: Model Agnosticism & Token Economy
status: complete
---

# M009 Summary — Model Agnosticism & Token Economy

## One-liner
Eliminated vendor lock-in with a model-agnostic UnifiedRouter, negative-permissions PII gate, cosine-similarity context pruner, async prompt caching, token cost tracking, and Caddy TLS — the gateway now dispatches to OpenAI, Anthropic, or Ollama with automatic fallback and complete observability.

## What was built

### S01 — Unified Router & Provider Handlers
- `gateway/router.py`: `UnifiedRouter`, `OpenAIHandler`, `AnthropicHandler`, `OllamaHandler`, `ProviderError`
- `gateway/service_layer.py`: `InternalServiceLayer` wired to `UnifiedRouter`
- EventLog `token.usage` schema: `{type, model, input_tokens, output_tokens, cost_usd, sub, ts}`

### S02 — PII Gate & Negative-Permissions Middleware
- `gateway/validation.py`: `PIIGate` with regex scrubbing for email, API keys, private IPs, JWT strings
- `MCP_ALLOWED_FIELDS` env var override; default deny-list; generic error messages

### S03 — Context Pruner with Cosine Filtering
- `gateway/pruner.py`: `ContextPruner.prune()` with cosine similarity threshold

### S04 — Async Prompt Cache & Token Cost Tracking
- `streams/async_idempotency.py`: `AsyncIdempotencyGuard` with stable SHA-256 hashing
- Prompt cache integrated into `sampling_demo` in service_layer

### S05 — TLS + Caddy + Live Ollama Integration
- `Caddyfile`: `https://localhost` → `gateway:8000` via Caddy internal TLS
- `docker-compose.yml`: `gateway` + `caddy` services added
- Live acceptance tests: simulated OpenAI 429 → Ollama fallback verified

## Verification
- 318 tests passed, 11 skipped across full suite
- Live Ollama acceptance: OpenAI 429 → qwen3:0.6b-q4_K_M → token.usage event confirmed
- All 5 slices complete

## Definition of Done
- [x] UnifiedRouter dispatches to OpenAI, Anthropic, or Ollama based on env config
- [x] Simulated OpenAI 429 triggers Ollama fallback; both events in EventLog
- [x] Fields not in MCP_ALLOWED_FIELDS scrubbed before leaving local network
- [x] Only semantically relevant chunks passed to LLM (cosine threshold)
- [x] token.usage events with model, input_tokens, output_tokens, cost_usd, sub readable from EventLog
- [x] Gateway reachable at https://localhost via Caddy in docker-compose stack

## Key Decisions
- Caddy `tls internal` for development self-signed certs; swap to ACME for production
- OllamaHandler uses `/api/chat` with `stream: false`; cost_usd always 0.0 for local models
- AsyncIdempotencyGuard write failures are swallowed (logged only) — cache is best-effort
- PIIGate uses deny-list pattern (block unless in allow-list) — privacy-first default

## Lessons Learned
- Ollama `prompt_eval_count`/`eval_count` maps to `input_tokens`/`output_tokens` in the unified schema
- `fakeredis.aioredis` required for async tests; streams arg must be a keyword dict (see KNOWLEDGE.md)
- Docker healthcheck for Python gateway: `urllib.request.urlopen` avoids curl/wget dependency in slim images
