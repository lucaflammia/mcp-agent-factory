# MCP Agent Factory

A production-grade **Model Context Protocol (MCP)** server ecosystem demonstrating collaborative multi-agent architectures, economic task allocation, async messaging, and OAuth 2.1 security — built across three progressive milestones.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  External Clients                    │
│           MCPGatewayClient + OAuthMiddleware         │
└─────────────────────┬───────────────────────────────┘
                      │ Bearer JWT (OAuth 2.1)
┌─────────────────────▼───────────────────────────────┐
│              MCP API Gateway (FastAPI)               │
│  POST /mcp   POST /sampling   GET /health  /sse/*   │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────────────┐
│  Analyst→   │ │  Auction  │ │    MessageBus +     │
│  Writer     │ │  (econ)   │ │    SSE Transport    │
│  Pipeline   │ └───────────┘ └────────────────────-┘
└─────────────┘
       │
┌──────▼──────────────────────────────────────────────┐
│            Redis Session Manager (fakeredis)         │
└─────────────────────────────────────────────────────┘
```

## Features

| Layer | Module | What it does |
|-------|--------|--------------|
| **MCP Protocol** | `server.py` (STDIO), `server_http.py` (HTTP) | JSON-RPC 2.0 over STDIO and FastAPI; echo + add tools |
| **Task Scheduler** | `scheduler.py` | Priority queue, retry logic, structured state-transition logging |
| **LLM Adapters** | `adapters.py` | Normalises tool schemas for Claude, OpenAI, and Gemini |
| **ReAct Loop** | `react_loop.py` | Perception → Reasoning → Action agent loop |
| **Agent Pipeline** | `agents/` | `AnalystAgent` → `WriterAgent` coordinated by `MultiAgentOrchestrator` |
| **Session State** | `session/manager.py` | Redis-backed key/value store for cross-agent handoffs |
| **Economics** | `economics/` | Utility scoring + sealed-bid auction for task allocation |
| **Messaging** | `messaging/` | Async `MessageBus` (fan-out by topic) + SSE router for streaming |
| **Gateway** | `gateway/` | Authenticated MCP API gateway; stub sampling/createMessage handler |
| **Auth (OAuth 2.1)** | `auth/` | PKCE auth server, JWT resource middleware, session tokens |
| **Bridge** | `bridge/` | `OAuthMiddleware` (token caching) + `MCPGatewayClient` for external callers |

## Quick Start

```bash
pip install -e .

# STDIO server
python -m mcp_agent_factory.server

# HTTP server (unauthenticated)
uvicorn mcp_agent_factory.server_http:app --reload

# HTTP server (OAuth-secured)
uvicorn mcp_agent_factory.server_http_secured:secured_app --reload

# MCP API Gateway (full stack)
uvicorn mcp_agent_factory.gateway.app:gateway_app --reload
```

## Running Tests

```bash
pytest tests/ -v          # all 157 tests
pytest tests/test_pipeline.py       # agent pipeline
pytest tests/test_economics.py      # utility + auction
pytest tests/test_message_bus.py    # MessageBus + SSE
pytest tests/test_gateway.py        # API gateway
pytest tests/test_langchain_bridge.py  # OAuth bridge
```

## Code Style

All Python source files use **tab indentation** (1 tab = 1 indent level).

## Project Layout

```
src/mcp_agent_factory/
├── server.py                   # STDIO MCP server
├── server_http.py              # FastAPI HTTP MCP server
├── server_http_secured.py      # OAuth-secured variant
├── models.py                   # Pydantic tool input models
├── adapters.py                 # LLM adapter layer
├── react_loop.py               # ReAct agent loop
├── scheduler.py                # Task scheduler + priority queue
├── orchestrator.py             # MCP orchestrator client
├── config/privacy.py           # PrivacyConfig + egress guard
├── agents/                     # Multi-agent pipeline
│   ├── models.py               # AgentTask, MCPContext, shared models
│   ├── analyst.py              # AnalystAgent
│   ├── writer.py               # WriterAgent
│   └── pipeline_orchestrator.py
├── session/manager.py          # Redis session manager
├── economics/
│   ├── utility.py              # Utility function scoring
│   └── auction.py              # Sealed-bid auction
├── messaging/
│   ├── bus.py                  # Async MessageBus (topic fan-out)
│   └── sse_router.py           # FastAPI SSE event stream
├── gateway/
│   ├── app.py                  # MCP API Gateway FastAPI app
│   └── sampling.py             # Sampling/createMessage handler
├── auth/
│   ├── server.py               # OAuth 2.1 auth server (PKCE)
│   ├── resource.py             # JWT Bearer middleware
│   └── session.py              # Session ID utilities
└── bridge/
    ├── oauth_middleware.py     # Token-caching OAuth middleware
    └── gateway_client.py       # MCPGatewayClient (httpx)

tests/
├── test_mcp_lifecycle.py       # STDIO protocol lifecycle
├── test_react_loop.py          # ReAct loop unit tests
├── test_e2e_routing.py         # End-to-end routing
├── test_scheduler.py           # Scheduler + retry logic
├── test_adapters.py            # LLM adapter normalisation
├── test_server_http.py         # HTTP server endpoints
├── test_schema_validation.py   # Pydantic validation + privacy
├── test_auth.py                # OAuth 2.1 full flow
├── test_integration.py         # Scheduler ↔ HTTP integration
├── test_pipeline.py            # Analyst→Writer pipeline
├── test_economics.py           # Utility + auction
├── test_message_bus.py         # MessageBus + SSE
├── test_gateway.py             # API Gateway
└── test_langchain_bridge.py    # OAuth bridge + client
```

## Security Notes

- JWT tokens use HS256 with a randomly-generated `OctKey` per server start. Rotate to RS256 + JWKS for multi-service deployments.
- `PrivacyConfig.assert_no_egress()` guards against accidental outbound calls — checked at startup via FastAPI lifespan.
- PKCE S256 enforced on all authorization code exchanges; codes are single-use.
- Audience binding (`aud: mcp-server`) prevents confused-deputy attacks.
