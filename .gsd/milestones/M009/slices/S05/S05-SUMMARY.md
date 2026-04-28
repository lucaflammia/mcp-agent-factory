---
slice: S05
milestone: M009
title: TLS + Caddy + Live Ollama Integration
status: complete
---

# S05 Summary — TLS + Caddy + Live Ollama Integration

## One-liner
Caddy TLS termination added to docker-compose; live Ollama fallback chain (simulated OpenAI 429 → Ollama) confirmed with token.usage events in EventLog.

## What was built
- `Caddyfile` — minimal Caddy reverse proxy: `https://localhost` → `gateway:8000`, using Caddy's internal self-signed cert for development
- `docker-compose.yml` — added `gateway` service (uvicorn on port 8000, Redis-backed, Ollama via host.docker.internal) and `caddy` service (ports 443/80, caddy_data/caddy_config volumes)
- `tests/test_m009_s05.py` — 7 tests: health endpoint, router 429→stub fallback (unit), all-fail raises, live Ollama 429→fallback+EventLog (skipped if Ollama absent), sequential calls emit separate usage events, docker-compose Caddy smoke tests (skipped unless DOCKER_STACK_UP=1)

## Verification
`pytest tests/test_m009_s05.py` — 5 passed, 2 skipped (docker-compose skips expected).

Live Ollama tests ran against local qwen3:0.6b-q4_K_M:
- Simulated OpenAI 429 → OllamaHandler completes successfully
- token.usage event: type=token.usage, sub=s05-acceptance, output_tokens>0, cost_usd=0.0
- Sequential calls produce distinct per-sub usage events

Full suite: 318 passed, 11 skipped.

## Requirements advanced
- R039: docker-compose brings Caddy + gateway (Caddyfile + compose service delivered)
- R040: Live Ollama fallback confirmed with token.usage in EventLog (validated)
