# Project

## What This Is

An industrial-grade Multi-Agent Orchestrator using the Model Context Protocol (MCP) as its universal connection layer. Establishes a standardized "system nervous" that allows autonomous agents to perceive, reason, and act within a secure enterprise environment, integrating Fargin Curriculum materials as the foundational "Theory-to-Action" bridge.

## Core Value

A production-grade async MCP orchestration engine where agents can discover and call tools over a real network transport, protected by OAuth 2.1 / PKCE with confused deputy safeguards — directly proving the Fargin Curriculum's theory in executable, testable code.

## Current State

M001 and M002 complete. The full stack is implemented and proven by 100 passing pytest tests:

- **STDIO MCP server** (M001) — JSON-RPC 2.0 over subprocess STDIO, echo + add tools
- **ReActAgent** (M001) — synchronous Perception→Reasoning→Action loop
- **AsyncTaskScheduler** (M002) — asyncio-native autonomous agent loop with priority queue and retry
- **FastAPI HTTP MCP Server** (M002) — same MCP protocol over TCP/IP HTTP
- **LLM Adapters** (M002) — Claude/OpenAI/Gemini function-calling schema translation
- **OAuth 2.1 Auth Server** (M002) — PKCE S256, scopes, one-time codes, JWT issuance
- **Resource Server middleware** (M002) — audience binding (confused deputy protection), scope enforcement
- **Session module** (M002) — user-bound non-deterministic session IDs

## Architecture / Key Patterns

- **Transport:** STDIO (M001, local/subprocess) + HTTP via FastAPI (M002, networked)
- **Agent loop:** ReActAgent (sync, M001) + TaskScheduler (async asyncio, M002)
- **Validation:** Pydantic v2 at all tool dispatch boundaries
- **Auth:** OAuth 2.1 + PKCE, audience-bound tokens, scope enforcement (M002)
- **Privacy:** PrivacyConfig with local_only / allow_egress defaults + assert_no_egress() guard
- **LLM adapters:** Schema translation only (Claude/OpenAI/Gemini) — no live API calls

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Orchestrator and MCP Foundation — STDIO MCP lifecycle, ReAct loop, schema validation, privacy-first config; proven by 31 tests.
- [x] M002: Autonomous Orchestrator & Production Security — Async TaskScheduler, FastAPI HTTP MCP server, LLM adapters, OAuth 2.1 + PKCE auth server; proven by 69 new tests (100 total).
