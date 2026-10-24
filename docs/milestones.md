# Milestone History

Development history of MCP Agent Factory, preserved from the original README.

| Milestone | Focus | Tests |
|-----------|-------|-------|
| M001 | STDIO MCP lifecycle, ReAct loop, schema validation, privacy config | 31 |
| M002 | Async TaskScheduler, FastAPI HTTP server, LLM adapters, OAuth 2.1 + PKCE | +69 (100) |
| M003 | Multi-agent pipeline, economic allocation, async message bus, API gateway, LangChain bridge | +61 (161) |
| M004 | SSE /v1 streaming, PKCE hardening, client bridge with token cache, mcp.json IDE config | +37 (198) |
| M005 | Vector RAG layer, multi-tenant isolation, async ingestion, knowledge-augmented auction, LibrarianAgent, SSE events | +7 (205) |
| M006 | Redis Streams consumer groups, EventLog + KafkaEventLog, ValidationGate, IdempotencyGuard, DistributedLock, OutboxRelay, CircuitBreaker | +26 (231) |
| M007 | docker-compose stack, real KafkaEventLog integration tests, RedlockClient 3-node quorum, multi-process StreamWorker scaling | +15 unit / +8 integration (246 unit) |
| M008 | Production wiring: env-driven Redis/Kafka factories, Redis-backed OAuth state, EventLog on every tool call; `redis>=5` promoted to core dep | +5 (241 unit) |
| Hotfix | Bridge `client_credentials` grant — headless machine-to-machine auth without browser redirect | +6 (246 unit) |
| Hotfix | Auth server falls back to FakeRedis when configured Redis is unreachable at startup | +2 (248 unit) |
| Hotfix | Auth server now reads `JWT_SECRET` env var to share the signing key with the gateway — fixes `bad_signature` when both run as separate processes | +0 (248 unit) |
| Hotfix | Resource server reads `JWT_SECRET` from env as fallback; bridge warns on stale `GATEWAY_TOKEN` + `JWT_SECRET` combination that would cause `bad_signature` | +0 (248 unit) |
| Hotfix | Bridge no longer injects `Authorization: Bearer ` when no credentials are configured; resource server guards against empty token before parsing — fixes `Invalid input segments length` 500 error | +0 (248 unit) |
| Hotfix | Bridge self-signs a valid HS256 JWT with `JWT_SECRET` when no auth server is running — no extra process needed for local dev; `python -m mcp_agent_factory.auth token` generates a static `GATEWAY_TOKEN` | +0 (248 unit) |
| Hotfix | README: `client_credentials` flow now documents that auth server, gateway, and bridge all require the **same** `JWT_SECRET`; missing this causes `Not Authorized` even with correct credentials | +0 (248 unit) |
| Hotfix | `docker compose up` starts Redis + Kafka infrastructure only — gateway and auth are Python processes started separately; README corrected to remove misleading "already wired" claim | +0 (248 unit) |
| KV Store | Topic-namespaced `RedisKVStore` (`kv/`) — async `set/get/delete/keys` with registered-topic enforcement; `add_phrase` / `has_affinity` / `phrases` topic-affinity API via Redis sets; tested with `fakeredis` | +13 (273 unit) |
| KV Tools | `kv/add_phrase` and `kv/check_affinity` exposed as MCP tools on the gateway; dispatch tested end-to-end in dev mode | +8 (281 unit) |
| M009 | Model agnosticism: `UnifiedRouter` (OpenAI / Anthropic / Ollama + auto-fallback), `PIIGate` scrubbing, `ContextPruner`, `AsyncIdempotencyGuard` prompt cache, `token.usage` EventLog schema, Caddy TLS in docker-compose | +63 (336 total) |
| M010 | Production analyst demo (`scripts/demo_analyst.py`), provider-switch env var, OpenTelemetry setup | +0 (336) |
| M011 | Dockerized observable reference architecture: `docker compose --profile full` brings up 12 services; OTel traces in Jaeger; Prometheus + Grafana dashboards; smoke test script | +22 (358 unit + 12 integration = 370 total) |
| Hotfix | OTel integration tests now skip automatically when the Jaeger/Collector stack is down (`@pytest.mark.integration`); `pip install -e .` on a fresh machine now installs all required runtime deps (fastapi, uvicorn, pydantic, authlib, sse-starlette, numpy previously missing from `pyproject.toml`) | +0 (370) |
| M012 | Live demo: `agents/analyze` JSON-RPC method via `_agents_dispatch()` sub-router; 4 OTel child spans (pdf_extract, prune, pii_scrub, llm_route) with token count attributes visible in Jaeger; `scripts/demo.sh` three-phase zero-touch demo (Privacy-First RAG → OTel trace → provider switch with -32602 fail-fast); contract tests cover response shape, -32602, and -32603 | +3 (361 unit + 14 integration) |
| Hotfix | Auth server OTel instrumentation: `FastAPIInstrumentor` wired into `auth_app`; docker-compose auth service exports `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME=mcp-auth` so auth server spans appear alongside gateway spans in Jaeger | +0 (361 unit + 14 integration) |
| Hotfix | `test_m010_s01.py`: updated Gemini model reference from `gemini-1.5-flash` to `gemini-2.5-flash`; `test_m011_otel_integration.py`: `require_full_stack` fixture now probes gateway dev mode and skips with an actionable message when auth is enforced | +0 (361 unit + 14 integration) |
| Hotfix | Smoke test skips (not fails) the unauthenticated auth check when `MCP_DEV_MODE=1` — dev mode bypasses auth by design | +0 (361 unit + 14 integration) |
| Hotfix | Grafana dashboard: rate windows widened from `[1m]` to `[5m]` and default time range extended to `now-30m` so panels stay populated after `demo.sh` finishes | +0 (361 unit + 14 integration) |
| Hotfix | Grafana Agent Pipeline panels: removed high-cardinality spanmetrics dimensions; added direct Prometheus counters for token/cost tracking | +0 (361 unit + 14 integration) |
| Hotfix | Grafana Agent Pipeline PromQL: replaced invalid `\.` RE2 escape sequences with `[.]` | +0 (361 unit + 14 integration) |
| Hotfix | Grafana Token Consumption and Provider Distribution panels generalised to all providers | +0 (361 unit + 14 integration) |
| Hotfix | Grafana cost panels updated to 4 decimal places; `cost_usd` injected into `route()` result dict | +0 (361 unit + 14 integration) |
| Feature | `DeterministicOrchestrator` + `OrchestratorPlan`/`OrchestratorResult` Pydantic contracts; `CriticActorEvaluator`; Kafka UI + Redis Commander in docker-compose | +0 (361 unit + 14 integration) |
| Hotfix | Phase 4 orchestrator modes unblocked; `graph_orchestrator.py` accepts both step-key formats; MCP Inspector service added on `:6274` | +0 (361 unit + 14 integration) |
| **Layer 3** | `MCPCrew`, `ScopedAgent`, `scope_tools`, `build_scoped_call_fn` — per-role MCP tool scoping with hard `PermissionError` boundary; CrewAI or native PydanticAI sequential runner | +20 (381 unit + 14 integration) |
| **Layer 4** | `PromptOptimizer` (Kafka trace ingestion → DSPy `BootstrapFewShot` → `GEPAEvolver` genetic mutation); `SkillCompiler` writes hot-reloadable JSON assets; entirely offline | +22 (403 unit + 14 integration) |
| **Cross-layer** | Full 4-layer pipeline integration (Layer 1 PydanticAI → Layer 2 LangGraph FSM → Layer 3 CrewAI → Layer 4 DSPy+GEPA skill compilation) | +5 (408 unit + 14 integration) — **v1.0.0 pipeline complete** |
| Feature | Multi-step plan output chaining: typed `PlanStep`, `{{steps.<id>.output}}` reference resolution, DAG-based parallel execution with bounded concurrency, async checkpointer, HITL replay safety, `ORCHESTRATOR_MODE` default alignment | +26 (434 unit + 14 integration) |
| **Eval Harness** | LLM evaluation framework: 55 hand-curated examples (25 RAG Q&A, 15 extraction, 15 refusal), Wilson CI on all rates, LLM-as-judge with 20-example calibration subset, per-example regression comparison, baseline run committed | +0 (434 unit + 14 integration) — **evaluation infrastructure** |
