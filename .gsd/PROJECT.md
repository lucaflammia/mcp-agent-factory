# MCP Agent Factory

## What This Is

A production-grade Model Context Protocol (MCP) server ecosystem demonstrating collaborative multi-agent architectures, economic task allocation, async messaging, OAuth 2.1 security, external client connectivity, vector-backed RAG, and distributed fault-tolerant infrastructure.

## Core Value

A runnable, testable reference implementation of the full MCP agent stack — from protocol wire format to multi-agent pipelines to distributed task distribution — with no hand-waving: every layer is real, observable, and regression-tested.

## Current State

Five milestones complete. The ecosystem has:
- STDIO + HTTP MCP servers with JSON-RPC 2.0
- ReAct loop, TaskScheduler (asyncio heap), LLM adapters
- OAuth 2.1 auth server + PKCE S256, JWT resource middleware
- MultiAgentOrchestrator (Analyst → Writer pipeline) with Redis session handoff
- Sealed-bid economic auction with knowledge-augmented bidding
- In-process MessageBus (asyncio.Queue fan-out) + SSE v1 streaming
- Vector RAG layer (InMemoryVectorStore, StubEmbedder, IngestionWorker, LibrarianAgent)
- MCP API Gateway with sampling handler, SSE /v1 endpoints, query_knowledge_base tool

M001–M007 complete. M008 in progress: wiring production infrastructure into all application paths (real Redis, persistent OAuth state, Kafka EventLog).

## Architecture / Key Patterns

- **Tab indentation** throughout all Python source files
- **Module-level singletons + set_* injection helpers** pattern for testability
- **Protocol classes** (VectorStore, Embedder, EventLog) with real and fake/stub implementations
- **fakeredis** for Redis tests (xadd, xreadgroup, xack, xpending all supported)
- **FastAPI** gateway with lifespan startup validation, OAuth Bearer middleware
- **Pydantic v2** for all models and validation gates
- Tests live in `tests/`, use `PYTHONPATH=src pytest`

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: STDIO MCP Foundation — protocol lifecycle, ReAct loop, schema validation
- [x] M002: Autonomous Orchestrator & Production Security — scheduler, HTTP server, OAuth 2.1
- [x] M003: Multi-Agent Pipeline & Economic Allocation — Analyst/Writer pipeline, auction, message bus, gateway
- [x] M004: Production-Ready Client Connectivity — SSE /v1, PKCE hardening, MCPGatewayClient, mcp.json
- [x] M005: RAG Layer — vector store, ingestion, knowledge-augmented auction, LibrarianAgent
- [x] M006: Distributed Orchestration & Monolith Refactoring — Redis Streams workers, event log, validation gate, idempotency, circuit breakers
- [x] M007: Real Infrastructure — docker-compose stack, Kafka integration, Redlock 3-node quorum, multi-process horizontal scaling
- [ ] M008: Production-Grade Infrastructure Wiring — replace all in-memory/fake defaults with env-driven real implementations
- [ ] M009: Model Agnosticism & Token Economy — unified provider router, PII gate, context pruning, async caching, Caddy TLS
