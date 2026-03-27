# M002: 

## Vision
Evolve M001's synchronous STDIO prototype into a production-grade async system: an asyncio-native TaskScheduler for autonomous agent loops, a FastAPI HTTP MCP server with LLM function-calling adapters, and a full OAuth 2.1 + PKCE authorization stack — directly applying the Fargin Curriculum's async and security theory in executable, testable code.

## Slice Overview
| ID | Slice | Risk | Depends | Done | After this |
|----|-------|------|---------|------|------------|
| S01 | Async TaskScheduler | high | — | ✅ | pytest tests/test_scheduler.py -v passes — asyncio task loop with priority queue, retry logic, and state transitions proven by async tests. |
| S02 | FastAPI HTTP MCP Server + LLM Adapters | high | S01 | ✅ | pytest tests/test_server_http.py tests/test_adapters.py -v passes — HTTP MCP lifecycle and Claude/GPT/Gemini adapter payloads verified. |
| S03 | OAuth 2.1 Auth Server + Resource Server | high | S02 | ✅ | pytest tests/test_auth.py -v passes — full PKCE flow, scope gating, and confused deputy protection proven. |
| S04 | Security Audit & Integration Wiring | low | S03 | ✅ | pytest tests/ -v passes in full — M001 + M002 tests all green; docs/security_audit.md written and cross-referenced to Fargin Curriculum. |
