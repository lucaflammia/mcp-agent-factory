# Project

## What This Is

An industrial-grade Multi-Agent Orchestrator using the Model Context Protocol (MCP) as its universal connection layer. Establishes a standardized "system nervous" that allows autonomous agents to perceive, reason, and act within a secure enterprise environment, integrating Fargin Curriculum materials as the foundational "Theory-to-Action" bridge.

## Core Value

A distributed multi-agent ecosystem where specialized agents collaborate and compete economically over a production-grade async transport, protected by OAuth 2.1 / PKCE — all accessible to external clients (Cursor, Claude Desktop, custom apps) via a secured HTTP/SSE Gateway.

## Current State

M001–M004 complete (198 passing tests). Full production-ready stack:
- **STDIO MCP server** — JSON-RPC 2.0 over subprocess STDIO
- **ReActAgent** — synchronous Perception→Reasoning→Action loop
- **AsyncTaskScheduler** — asyncio-native autonomous agent loop with priority queue and retry
- **FastAPI HTTP MCP Server** — MCP protocol over TCP/IP HTTP
- **LLM Adapters** — Claude/OpenAI/Gemini function-calling schema translation
- **OAuth 2.1 Auth Server** — PKCE S256, scopes, one-time codes, JWT issuance
- **Resource Server middleware** — audience binding, scope enforcement, 401/403 enforcement
- **Session module** — user-bound non-deterministic session IDs
- **AnalystAgent + WriterAgent** — specialized agent pipeline via Redis session handoff
- **Economic Task Allocation** — utility functions + auction bidding
- **MessageBus + SSE transport** — async event streaming (`/sse/v1/events`, `/sse/v1/messages`)
- **MCP API Gateway** — unified HTTP endpoint with Bearer token enforcement
- **Sampling handler** — stub sampling/createMessage implementation
- **LangChain bridge** — MultiServerMCPClient + OAuth middleware
- **MCPGatewayClient** — PKCE-aware Python client with token cache, refresh, and SSE stream
- **mcp.json** — external IDE config for Cursor/Claude Desktop connectivity

## Architecture / Key Patterns

- **Transport:** STDIO (M001) + HTTP FastAPI (M002) + SSE async bus (M003) + HTTP/SSE Gateway (M004)
- **Agent roles:** ReActAgent (generic) + AnalystAgent + WriterAgent (specialized, M003)
- **Agent loop:** TaskScheduler (asyncio) + MultiAgentOrchestrator (multi-agent coordinator, M003)
- **Economics:** Utility functions + auction bidding for task allocation (M003)
- **Validation:** Pydantic v2 at all tool dispatch boundaries
- **Auth:** OAuth 2.1 + PKCE S256, audience-bound JWTs, scope enforcement, 401 on all invalid tokens
- **Session state:** Redis Session Manager for cross-agent state (M003)
- **Observability:** MCP Context primitive per-tool + structured JSON logs + SSE event streaming
- **Client bridge:** MCPGatewayClient with OAuthMiddleware (token cache, 60s refresh threshold)
- **External config:** mcp.json at project root for IDE integration

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Orchestrator and MCP Foundation — STDIO MCP lifecycle, ReAct loop, schema validation, privacy-first config; proven by 31 tests.
- [x] M002: Autonomous Orchestrator & Production Security — Async TaskScheduler, FastAPI HTTP MCP server, LLM adapters, OAuth 2.1 + PKCE auth server; proven by 69 new tests (100 total).
- [x] M003: Multi-Agent Ecosystem & Distributed Context Management — Specialized agent pipeline, economic task allocation, async message bus, MCP API Gateway, sampling, LangChain bridge; proven by 61 new tests (161 total).
- [x] M004: Production-Ready Client Connectivity — SSE /v1 endpoints with connected event, PKCE hardening tests, MCPGatewayClient with token cache/refresh/SSE, gateway run.py, mcp.json; proven by 37 new tests (198 total).
