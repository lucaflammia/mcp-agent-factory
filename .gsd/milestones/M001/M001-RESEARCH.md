# M001: Core Orchestrator and MCP Foundation — Research

**Date:** 2026-03-26
**Status:** Complete

## Summary

This is a **greenfield project** — the working directory contains only `.git` and `.gitignore`. No prior application code exists. The Fargin Curriculum materials (6 chapters) located at `/home/luca/Documents/Misc/Fargin/CorsoAgentiAI&ProtocolloMCP/Teoria` are the sole prior art and serve as both theoretical foundation and direct source of implementation patterns.

The Python MCP SDK (`mcp==1.25.0`) is **already installed** in the active pyenv (Python 3.11.0), along with Pydantic (2.12.5), FastMCP, and all transport dependencies. This eliminates the primary setup risk and means M001 can build directly on the official SDK rather than hand-rolling the protocol.

The curriculum provides concrete, directly usable patterns: a custom JSON-RPC 2.0 dataclass layer (Cap 3 `demo.py`), an Orchestrator + specialized-agents pipeline (Cap 4), a task scheduler with priority queues, and async message routing via in-memory deques. The recommended path is to move from these illustrative patterns to the official `FastMCP` + `mcp.ClientSession` abstractions for production quality.

## Recommendation

**Use `FastMCP` (server side) + `mcp.ClientSession` (client/orchestrator side) over STDIO transport for M001.** This aligns with the curriculum's own "best practice alert" (Cap 3), leverages the already-installed SDK, and delivers automatic schema generation via Python type hints/Pydantic — satisfying R005 without extra plumbing. The STDIO transport is the right choice for local simulation; HTTP can be deferred to later milestones.

Structure the milestone into three slices ordered by dependency:
1. **S01 — MCP Foundation**: FastMCP server stub + ClientSession orchestrator + initialize/tools/list/tools/call lifecycle. This unblocks everything.
2. **S02 — ReAct Loop**: Perception→Reasoning→Action cycle with CoT, wired into the MCP tool call channel. Depends on S01.
3. **S03 — Security & Privacy Layer**: Pydantic-enforced schemas on all tool inputs/outputs, privacy-first configuration patterns (local-only inference, no data egress). Depends on S01.

## Implementation Landscape

### Key Files (to create)

- `src/orchestrator/host.py` — MCP Host/Orchestrator; manages ClientSession connections to MCP servers, routes tasks, runs the ReAct loop
- `src/orchestrator/react_loop.py` — Perception→Reasoning→Action implementation with CoT chain
- `src/servers/simulation_server.py` — FastMCP-based simulated specialist MCP server (exposes demo tools)
- `src/models/messages.py` — Pydantic models for all inter-agent messages and tool I/O (satisfies R005)
- `src/config/privacy.py` — Privacy-first defaults: local-only inference flag, data egress controls
- `tests/` — pytest unit tests for MCP lifecycle, ReAct loop, and schema validation
- `pyproject.toml` — project packaging, dependency pinning (`mcp>=1.25.0`, `pydantic>=2.0`)

### Curriculum Code Patterns to Reuse

| Pattern | Source | How to Adapt |
|---------|--------|--------------|
| `MCPMessageType` / `MCPErrorCode` enums | Cap 3 `demo.py` | Replace with `mcp.types` from official SDK; keep as reference |
| `MiniAgent.run_cycle()` — inbox/outbox async loop | Cap 2/3 `demo.py` | Restructure as orchestrator's async task dispatch |
| `AnalystAgent` + `WriterAgent` + `Orchestrator` pipeline | Cap 4 `collaborative_agents.py` | Use as template for simulated specialist servers |
| `TaskScheduler` with priority queue | Cap 3/4 | Embed in orchestrator for task prioritization |
| `gemini_api_call` payload construction | Cap 3 `mcp_client_debug_gemini.py` | Reference for future LLM integration; not needed for S01 simulation |

### Build Order

1. **`pyproject.toml` + `src/` skeleton** — establishes import paths, pins `mcp`, `pydantic`
2. **`src/servers/simulation_server.py`** with FastMCP — proves the server side; tool list must be discoverable before the client can do anything
3. **`src/orchestrator/host.py`** with `ClientSession` over STDIO — proves initialize → tools/list → tools/call lifecycle; this is the integration test backbone
4. **`src/orchestrator/react_loop.py`** — wires perception/reasoning/action on top of working MCP channel
5. **`src/models/messages.py`** with Pydantic — locks down schema validation; apply to tool I/O in both server and client
6. **`tests/`** — unit + integration tests confirming each layer

### Verification Approach

```bash
# Smoke test: server starts and lists tools
python -m pytest tests/test_mcp_lifecycle.py -v

# Integration: orchestrator routes a task through ReAct loop
python -m pytest tests/test_react_loop.py -v

# Schema validation: invalid input rejected
python -m pytest tests/test_schema_validation.py -v

# End-to-end: task routed from simulated agent A → orchestrator → simulated agent B
python -m pytest tests/test_e2e_routing.py -v
```

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| MCP protocol implementation | `mcp>=1.25.0` (already installed) | Full JSON-RPC 2.0 + lifecycle; FastMCP gives decorator-based tool registration |
| Schema validation | `pydantic>=2.0` (already installed, pulled by mcp) | FastMCP auto-generates JSON Schema from type hints; zero extra code |
| Async transport | `anyio` (pulled by mcp) | Handles STDIO and HTTP transports transparently |
| Test runner | `pytest` | Standard; add `pytest-anyio` for async test support |

## Constraints

- Python 3.11.0 (pyenv). Must stay compatible — no 3.12+ syntax.
- `mcp` SDK uses `anyio`; async code must be `anyio`-compatible (avoid `asyncio` primitives directly).
- All tool arguments and results **must** use Pydantic models or TypedDict — no bare `dict` (R005 requirement).
- Privacy-first (R006): no calls to external LLM APIs in M001 simulation layer; orchestrator reasoning can be rule-based or stub.

## Common Pitfalls

- **STDIO transport process lifecycle** — FastMCP server must be launched as a subprocess by the ClientSession; forgetting to properly `await` the process teardown causes hanging tests.
- **`isError` vs JSON-RPC error** — Tool execution errors must set `isError=True` inside `CallToolResult`, not raise protocol-level exceptions. The curriculum (Cap 3) explicitly flags this discrepancy.
- **Capability negotiation** — `notifications/initialized` must be sent after `initialize` response before any `tools/list` calls; skipping this step silently breaks the session.
- **Pydantic v2 vs v1** — `mcp 1.25.0` requires Pydantic v2; do not use deprecated v1 validators (`@validator`), use `@field_validator` instead.

## Open Risks

- The curriculum references `mcp_use` (a third-party library) in some examples; this is **not** the official `mcp` SDK. Care needed to avoid importing from `mcp_use` accidentally.
- R006 (Privacy-First): local model inference (Ollama etc.) is mentioned in the curriculum but not demonstrated. M001 scope correctly defers this to a stub; a future milestone will need to benchmark local inference options.

## Requirements Assessment

All 6 active requirements are well-scoped for M001:

| Req | Assessment |
|-----|------------|
| R001 — Core Orchestration | Table stakes; directly addressable with ClientSession + task router |
| R002 — MCP Communication | Table stakes; FastMCP + JSON-RPC 2.0 is the implementation |
| R003 — ReAct Pattern | Core; Perception→Reasoning→Action from Cap 1 theory, S02 |
| R004 — Fargin Curriculum Integration | Doc-level: behavior must trace to Cap 1–4 theory; architecture comments should cite sections |
| R005 — Schema Validation | Directly met by Pydantic models on all tool I/O |
| R006 — Privacy-First | Met by config flag + no-egress assertion in tests; full local inference is out of scope for M001 |

**Candidate requirement (advisory, not binding):** An observability/logging layer (structured logs per `ctx.info()` / OpenTelemetry) is mentioned prominently in Cap 6 as enterprise-mandatory. Not in scope for M001 but worth adding as R007 for a future milestone.

## Sources

- Fargin Curriculum Cap 1: `note_intro_agenti.md` — ReAct loop definition, MCP as system nervous
- Fargin Curriculum Cap 2: `note_anatomia_agenti_flussi_mcp.md` — Host/Client/Server architecture, STDIO vs HTTP transport
- Fargin Curriculum Cap 3: `note_implementazione_protocollo_mcp.md` — JSON-RPC 2.0 message spec, FastMCP best practices, `CallToolResult` structure
- Fargin Curriculum Cap 4: `note_agenti_collaborativi_e_catene_di_ragionamento.md` — Multi-agent pipelines, async message routing, MCP vs A2A comparison
- Fargin Curriculum Cap 6: `note_ottimizzazione_debugging_deployment.md` — Observability, error handling, migration from `mcp_use` to official SDK
- MCP SDK: `pip show mcp` — v1.25.0 installed, FastMCP and ClientSession confirmed importable
