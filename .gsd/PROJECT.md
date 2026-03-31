# MCP Agent Factory

## What This Is

A production-grade Model Context Protocol (MCP) server ecosystem demonstrating collaborative multi-agent architectures, economic task allocation, async messaging, OAuth 2.1 security, and — from M005 — vector-backed knowledge retrieval with multi-tenant isolation.

## Core Value

A fully wired multi-agent pipeline that can receive a task, allocate it economically, execute it through specialised agents, persist the result as searchable knowledge, and serve future queries through a secured MCP gateway.

## Current State

M001–M003 complete. Provides: STDIO + HTTP MCP servers, ReAct loop, priority scheduler, LLM adapters, Analyst→Writer pipeline with Redis session handoffs, utility-based auction, async MessageBus with SSE transport, OAuth 2.1 auth (PKCE), MCP API Gateway with tool routing and sampling handler, OAuthMiddleware + MCPGatewayClient bridge. 183 tests passing.

M005 in progress: adding vector-backed RAG layer with multi-tenant isolation, async ingestion, knowledge-augmented bidding, LibrarianAgent, and `query_knowledge_base` MCP tool.

## Architecture / Key Patterns

- **Tab indentation** throughout all Python source files
- **Protocol/stub pattern**: every external dependency (Redis → FakeRedis, LLM → StubSamplingClient, vector DB → InMemoryVectorStore) has a swappable protocol interface — tests use stubs, production swaps to real backends
- **MessageBus fan-out**: agents communicate via named topics; SSE router streams events to external clients
- **JWT-bound namespacing**: OAuth `sub` claim is the isolation unit — vector chunks, session keys, and audit logs all carry `owner_id = claims['sub']`
- **Module layout**: `src/mcp_agent_factory/{agents,auth,bridge,economics,gateway,knowledge,messaging,session}/`

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Orchestrator and MCP Foundation — STDIO + HTTP MCP servers, ReAct loop, scheduler, LLM adapters
- [x] M002: Autonomous Orchestrator & Production Security — OAuth 2.1 PKCE, JWT middleware, secured gateway, integration tests
- [x] M003: Distributed Multi-Agent Ecosystem — Analyst→Writer pipeline, auctions, MessageBus/SSE, MCP API Gateway, OAuth bridge
- [ ] M005: Neural Knowledge Integration (RAG) — vector store, async ingestion, knowledge-augmented bidding, LibrarianAgent
