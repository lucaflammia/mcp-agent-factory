# Project

## What This Is

An industrial-grade Multi-Agent Orchestrator using the Model Context Protocol (MCP) as its universal connection layer. Establishes a standardized "system nervous" that allows autonomous agents to perceive, reason, and act within a secure enterprise environment, integrating Fargin Curriculum materials as the foundational "Theory-to-Action" bridge.

## Core Value

A distributed multi-agent ecosystem where specialized agents collaborate and compete economically over a production-grade async transport, protected by OAuth 2.1 / PKCE — all accessible to external clients via an MCP API Gateway.

## Current State

M001 and M002 complete (100 passing tests). Full stack implemented:
- **STDIO MCP server** — JSON-RPC 2.0 over subprocess STDIO
- **ReActAgent** — synchronous Perception→Reasoning→Action loop
- **AsyncTaskScheduler** — asyncio-native autonomous agent loop with priority queue and retry
- **FastAPI HTTP MCP Server** — MCP protocol over TCP/IP HTTP
- **LLM Adapters** — Claude/OpenAI/Gemini function-calling schema translation
- **OAuth 2.1 Auth Server** — PKCE S256, scopes, one-time codes, JWT issuance
- **Resource Server middleware** — audience binding (confused deputy), scope enforcement
- **Session module** — user-bound non-deterministic session IDs

M003 in progress: specialized agent roles, economic task allocation, async message bus, MCP API Gateway, sampling, and LangChain bridge.

## Architecture / Key Patterns

- **Transport:** STDIO (M001) + HTTP FastAPI (M002) + SSE async bus (M003)
- **Agent roles:** ReActAgent (generic) + AnalystAgent + WriterAgent (specialized, M003)
- **Agent loop:** TaskScheduler (asyncio) + Orchestrator (multi-agent coordinator, M003)
- **Economics:** Utility functions + auction bidding for task allocation (M003)
- **Validation:** Pydantic v2 at all tool dispatch boundaries
- **Auth:** OAuth 2.1 + PKCE, audience-bound tokens, scope enforcement
- **Session state:** Redis Session Manager for cross-agent state (M003)
- **Observability:** MCP Context primitive per-tool + structured JSON logs
- **LangChain:** MultiServerMCPClient + OAuth 2.1 security middleware (M003)

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Orchestrator and MCP Foundation — STDIO MCP lifecycle, ReAct loop, schema validation, privacy-first config; proven by 31 tests.
- [x] M002: Autonomous Orchestrator & Production Security — Async TaskScheduler, FastAPI HTTP MCP server, LLM adapters, OAuth 2.1 + PKCE auth server; proven by 69 new tests (100 total).
- [ ] M003: Multi-Agent Ecosystem & Distributed Context Management — Specialized agent pipeline, economic task allocation, async message bus, MCP API Gateway, sampling, LangChain bridge.
