# M009: Model Agnosticism & Token Economy

**Vision:** Eliminate vendor lock-in and optimize operational costs by implementing a model-agnostic UnifiedRouter, a negative-permissions PII gate, a cosine-similarity context pruner, async prompt caching, token cost tracking, and Caddy TLS — so the ThinkPad operates as a self-sufficient AI workstation with cloud providers used opportunistically and sensitive data never leaving the local network.

## Success Criteria

- UnifiedRouter dispatches to OpenAI, Anthropic, or Ollama based on env config
- Simulated OpenAI 429 triggers automatic Ollama fallback; both events recorded in EventLog
- Fields not in MCP_ALLOWED_FIELDS are scrubbed before leaving the local network
- Only semantically relevant chunks (cosine similarity above threshold) are passed to the LLM
- token.usage events with model, input_tokens, output_tokens, cost_usd, sub readable from EventLog
- Gateway reachable at https://localhost via Caddy reverse proxy

## Slices

- [x] **S01: Unified Router & Provider Handlers** `risk:high` `depends:[]`
  > After this: UnifiedRouter dispatches an echo-tool call to AnthropicHandler; simulated 429 triggers Ollama fallback; both token.usage events visible in EventLog

- [x] **S02: PII Gate & Negative-Permissions Middleware** `risk:medium` `depends:[S01]`
  > After this: Request with email in args is blocked at ValidationGate with generic message; request with only query passes through; MCP_ALLOWED_FIELDS env var override works

- [x] **S03: Context Pruner with Cosine Filtering** `risk:medium` `depends:[S01]`
  > After this: Vector chunk with cosine similarity below threshold is dropped; on-topic chunk passes; empty-context fallthrough proceeds without error

- [x] **S04: Async Prompt Cache & Token Cost Tracking** `risk:low` `depends:[S01]`
  > After this: Identical prompt returns cached result in under 1ms; token.usage events readable from EventLog per sub; cache write failure logged but does not fail the request

- [x] **S05: TLS + Caddy + Live Ollama Integration** `risk:medium` `depends:[S01,S02,S03,S04]`
  > After this: docker-compose up brings gateway at https://localhost; live fallback chain (simulated OpenAI 429 to Ollama completion) confirmed with token.usage events in EventLog

## Boundary Map

Not provided.
