# demo.sh — Walkthrough

`scripts/demo.sh` is the end-to-end live demo for **MCP Agent Factory**. It exercises all four pipeline layers in a single run: MCP gateway, analyst agent pipeline, OpenTelemetry tracing, Prometheus metrics, Gemini provider switching, three orchestrator backends, CrewAI multi-agent scoping (Layer 3), and offline DSPy + GEPA prompt optimization (Layer 4).

---

## Running Individual Steps

By default `./scripts/demo.sh` runs all seven phases sequentially. Pass a step name or number to run only that phase:

```bash
./scripts/demo.sh              # All phases (0–6) + monitor
./scripts/demo.sh infra        # Infrastructure seed: Kafka topics + Redis KV data only
./scripts/demo.sh 0            # Phase 0 — Deterministic Orchestration validation
./scripts/demo.sh 1            # Phase 1 — Privacy-First RAG (agents/analyze)
./scripts/demo.sh 2            # Phase 2 — Jaeger trace observation
./scripts/demo.sh 3            # Phase 3 — Live provider switch (Gemini)
./scripts/demo.sh 4            # Phase 4 — Orchestrator modes (pydantic_ai + langgraph)
./scripts/demo.sh 5            # Phase 5 — CrewAI multi-agent scoping (Layer 3)
./scripts/demo.sh 6            # Phase 6 — DSPy + GEPA offline optimization (Layer 4)
./scripts/demo.sh monitor      # Grafana panel verification + 5-minute traffic keeper
```

Phases 5 and 6 require only Python (no live gateway): they run inline scripts that import `crew.py` and `optimizer.py` directly, so `./scripts/demo.sh 5` and `./scripts/demo.sh 6` work without Docker.

---

## Prerequisites

| Requirement | How to satisfy |
|---|---|
| Docker stack running | `MCP_DEV_MODE=1 docker compose --profile full up --build -d` |
| Ollama running on host | `OLLAMA_HOST=0.0.0.0 ollama serve` |
| Ollama model pulled | `ollama pull qwen3:0.6b-q4_K_M` (or set `$OLLAMA_MODEL`) |
| `curl` and `jq` installed | standard OS packages |
| PDF file present | `data/samples/finance_q3_2024.pdf` (bundled) or set `$PDF_PATH` |

`MCP_DEV_MODE=1` must be set **before** `docker compose up`. It disables auth inside the gateway container; changing it later requires a container restart.

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `GATEWAY_URL` | `http://localhost:8000` | MCP gateway address |
| `PDF_PATH` | `data/samples/finance_q3_2024.pdf` | PDF to analyse |
| `QUERY` | `"Identify key KPIs and risk areas"` | Question sent to the analyst |
| `PROMETHEUS_URL` | `http://localhost:9090` | Used for panel verification |
| `JAEGER_URL` | `http://localhost:16686` | Health-checked at startup |
| `OLLAMA_MODEL` | `qwen3:0.6b-q4_K_M` | Local model for Ollama provider |
| `ORCHESTRATOR_MODE` | `legacy` | Orchestration backend: `legacy` (ReAct loop), `pydantic_ai`, or `langgraph` |
| `PYDANTIC_AI_MODEL` | `google-gla:gemini-2.5-flash` | Model used by the PydanticAI and LangGraph backends |
| `CREW_PROCESS` | `sequential` | `MCPCrew` execution strategy: `sequential` or `hierarchical` |
| `SKILLS_DIR` | `/opt/mcp/skills` | Directory where `SkillCompiler` writes hot-reloadable JSON prompt assets |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka broker for `PromptOptimizer` trace ingestion |
| `CRITIC_MODEL` | `google-gla:gemini-2.5-flash` | LLM model for the `CriticActorEvaluator` LLM judge (should differ from the actor model) |

---

## 4-Layer Execution Pipeline

```text
[MCP Resources / Tools]
│
▼
┌────────────────────────────────────────────────────────────────────────┐
│                        MCP-AGENT-FACTORY PIPELINE                      │
│                                                                        │
│  ✅ Layer 1: Foundations (PydanticAI)  ──► Validated I/O               │
│  ✅ Layer 2: Production (LangGraph)    ──► Deterministic State Machines │
│  ✅ Layer 3: Orchestration (CrewAI)    ──► Multi-Agent Workflows        │
│  ✅ Layer 4: Optimization (DSPy+GEPA)  ──► Offline Prompt Tuning        │
└────────────────────────────────────────────────────────────────────────┘
│
▼
[Predictable Enterprise Output & Dynamic Skillsets → v1.0.0]
```

Phases 1–3 exercise Layers 1–2. Phase 5 exercises Layer 3. Phase 6 exercises Layer 4.

---

## What the Script Does

### Preflight checks

Before any agent call the script validates the full stack:

1. **Gateway health** — polls `GET /health` until ready (30 s timeout).
2. **Prometheus health** — `GET /-/healthy`.
3. **Jaeger health** — `GET /api/services`.
4. **PDF file** — confirms `$PDF_PATH` exists on the host.
5. **`MCP_DEV_MODE=1`** — inspects the gateway container env; aborts if missing.
6. **Ollama reachable** — checks `http://localhost:11434/`.
7. **Ollama model pulled** — queries `/api/tags`; aborts with `ollama pull` hint if missing.
8. **Container → Ollama connectivity** — verifies `host.docker.internal:11434` is reachable from inside the gateway container (Linux requires `OLLAMA_HOST=0.0.0.0`).

---

### Infra Seed — Kafka topics + Redis KV store

Before any agent call the script idempotently creates three Kafka topics and seeds the Redis KV store with demo phrases:

| Kafka topic | Purpose |
|---|---|
| `agents.analyze` | Per-call event envelope written after each `agents/analyze` invocation |
| `token.usage` | Token consumption events (`input_tokens`, `output_tokens`, `cost_usd`) emitted per LLM call |
| `gateway.tool_calls` | Tool dispatch events for audit and replay |

Five KV phrases are seeded into two topics (`finance`, `risk`) via the `kv/add_phrase` MCP tool. These power the `kv/check_affinity` call later in the pipeline. Inspect them live in **Redis Commander** at `http://localhost:8086/`.

The `kafka-ui` consumer group `mcp-demo-consumer` appears approximately 20 seconds after the first `agents/analyze` call:

- Topics → `http://localhost:8085/ui/clusters/local/topics`
- Consumer groups → `http://localhost:8085/ui/clusters/local/consumer-groups`

---

### Phase 0 — Deterministic Orchestration

**Goal:** Demonstrate the LLM output validation gate added in v1.0.0.

`DeterministicOrchestrator` (in `orchestrator.py`) enforces a strict two-phase protocol between the LLM and the execution layer. The script runs three inline cases via a Python heredoc:

| Case | Input | Expected result |
|---|---|---|
| 1 — valid plan | `intent` + 2 distinct steps | ✓ Plan accepted, returns `OrchestratorPlan` object |
| 2 — missing `intent` | Steps only | ✓ `ValidationError` raised; execution blocked |
| 3 — duplicate adjacent steps | Identical tool call twice | ✓ `ValidationError` raised; copy-paste LLM error caught |

#### Critic-Actor isolation

Immediately after the validation cases the script prints the following explanation:

> The evaluator (`evaluator.py`) runs as a stateless sandbox with no shared context from the executing agent. It ingests the original constraints and the final output, then runs a double-pass check:
> 1. Deterministic schema fulfillment validation
> 2. Isolated LLM call acting as a cynical QA auditor (0.0–1.0 score)
>
> If the score is `0.0` (absolute failure) or a destructive tool is attempted, the graph pauses via LangGraph `interrupt()` and persists state to Redis. Resume with `compiled.ainvoke(None, config)` using the same `thread_id`. Inspect paused state at `http://localhost:8086` (Redis Commander).

This block bridges the output-gate explanation in Phase 0 with the HITL interrupt details covered in Phase 4.

---

### Phase 1 — Privacy-First RAG

**Goal:** Demonstrate the analyst agent pipeline with a local PDF and no data egress.

The script sends `agents/analyze` MCP calls to the gateway. Inside the gateway each call executes a five-span pipeline:

```
mcp.agents/analyze
  └─ agent.pdf_extract   extracts text pages and chunk count from the PDF
  └─ agent.prune         scores chunks for relevance; drops low-score chunks
  └─ agent.pii_scrub     strips PII (names, emails, account numbers) from context
  └─ agent.llm_route     routes the scrubbed prompt to the configured LLM provider
```

To seed Grafana panels the script runs **4 warm-up calls** spaced 12 s apart (~48 s total) before the display call. Prometheus scrapes every 15 s; `rate()` requires counter increments at ≥ 2 distinct scrape timestamps to return a non-zero value.

After warm-up it sleeps 20 s to allow the OTel `BatchSpanProcessor` to flush spans to the collector and Prometheus to complete one more scrape.

The display call result is printed as:

```json
{
  "provider": "ollama",
  "pages_read": 12,
  "chunks_before": 48,
  "chunks_after": 9,
  "input_tokens": 2840,
  "output_tokens": 312,
  "cost_usd": 0
}
```

---

### Phase 2 — Jaeger Trace

The script prints the Jaeger deep-link URL for the `mcp.agents/analyze` operation:

```
http://localhost:16686/search?service=mcp-gateway&operation=mcp.agents%2Fanalyze
```

Opening this URL shows the full span chain with latency breakdowns for each sub-agent stage.

---

### Phase 3 — Live Provider Switch (Gemini)

If `GEMINI_API_KEY` is set inside the gateway container the script re-runs the same analysis with `"provider": "gemini"`. This demonstrates hot provider switching without restarting the stack.

- If the key is present and Gemini responds, the summary and token metadata are printed.
- If the key is absent, the script exits cleanly with instructions for adding it to `.env`.

To enable Gemini:

```bash
echo 'GEMINI_API_KEY=<your-key>' >> .env
MCP_DEV_MODE=1 docker compose --profile full up --build -d
```

---

### Grafana Panel Verification

After the demo phases complete, the script queries Prometheus directly and prints a status table:

```
    Auction Bids                        ok
    Agent Pipeline (calls rate)         ok
    Pages Read (pdf_extract rate)       ok
    Token Consumption (llm_route rate)  ok
```

| Status | Meaning |
|---|---|
| `ok` | Prometheus returned ≥ 1 result for the query |
| `no-data` | Prometheus is reachable but no matching series yet; wait 30 s and retry |
| `unreachable` | Prometheus itself is not responding |

---

## Metrics Emitted

The demo populates three categories of Prometheus metrics:

### Auction metrics (from gateway auction subsystem)

| Metric | Labels | Description |
|---|---|---|
| `mcp_auction_bids_total` | `job` | Count of bids placed in the internal LLM routing auction |

### Agent pipeline counters (from `analyst.py`)

| Metric | Labels | Description |
|---|---|---|
| `mcp_agent_input_tokens_total` | `provider` | Cumulative input tokens sent to the LLM |
| `mcp_agent_output_tokens_total` | `provider` | Cumulative output tokens received |
| `mcp_agent_cost_usd_total` | `provider` | Cumulative cost in USD |

### OTel spanmetrics (from otel-collector → Prometheus)

The OTel collector converts spans to Prometheus metrics via the `spanmetrics` connector:

| Metric | Key dimensions | Description |
|---|---|---|
| `traces_calls_total` | `span_name`, `agent.provider`, `agent.pages_read`, `agent.chunk_count` | Call count per span |
| `traces_duration_milliseconds_*` | same | Histogram of span latency |

These back the **Agent Pipeline** panels in the Grafana dashboard. They require the OTel collector to be running and Prometheus to be scraping port `8889`.

---

## Web UI Services

The `--profile full` stack exposes several browser-based management UIs alongside the demo:

| Service | URL | Purpose |
|---|---|---|
| **Grafana** | `http://localhost:3000` | Live metrics dashboard (`mcp-overview`) |
| **Prometheus** | `http://localhost:9090` | Raw metric queries |
| **Jaeger** | `http://localhost:16686` | Distributed trace explorer |
| **Kafka UI** | `http://localhost:8085` | Topic browser, consumer-group lag, message inspector |
| **Redis Commander** | `http://localhost:8086` | Live key-value explorer — inspect LangGraph checkpointer state and session data |
| **MCP Inspector** | `http://localhost:6274` | Verify MCP tool handshake and test tool calls against the gateway — see transport options below |

### MCP Inspector Transport Options

The gateway supports two MCP transports. In the MCP Inspector sidebar, select the correct **Transport Type** before clicking **Connect**:

| Transport | Transport Type in Inspector | URL |
|---|---|---|
| Streamable HTTP (recommended) | `Streamable HTTP` | `http://localhost:8000/mcp` |
| Legacy SSE (2024-11-05 spec) | `SSE` | `http://localhost:8000/sse` |

**Streamable HTTP** is the current MCP standard and works out of the box.

**Legacy SSE** uses a session-scoped stream: `GET /sse` opens the stream and emits an `endpoint` event containing `http://localhost:8000/sse/messages?sessionId=<uuid>`. Subsequent JSON-RPC requests `POST` to that URL, receive `202 Accepted` immediately, and the response arrives on the open SSE stream as a `message` event. The Inspector handles this automatically once connected.

---

## Grafana Dashboard

After a successful run open:

```
http://localhost:3000/d/mcp-overview/mcp-agent-factory-e28094-overview?orgId=1&refresh=10s
```

The dashboard auto-refreshes every 10 s. If panels show "No data" immediately after the demo, wait one Prometheus scrape interval (≤ 15 s) and the panels will populate.

---

### Phase 4 — Orchestrator Modes

**Goal:** Show the three available orchestration backends side-by-side.

The script lists all three modes and their descriptions, then fires two live `orchestrate` calls:

| Call | Mode | Task | What it shows |
|---|---|---|---|
| 1 | `pydantic_ai` | `"Echo the text: hello from pydantic_ai structured output"` | Structured agent (pydantic-ai 0.0.20 `result_type` API) with Gemini back-end; calls the `echo` tool and returns a typed `StructuredResult` object |
| 2 | `langgraph` | `"Add the numbers 17 and 25 using the add tool"` | Cyclic state machine (validate → plan → execute → evaluate → done) with `thread_id` checkpointing via `AsyncRedisSaver`; max 15 iterations |

Tasks are chosen to be concrete and unambiguous: each maps to exactly one available tool (`echo` or `add`), so neither the planner nor the evaluator can route to a non-existent tool. Do not change these to open-ended prompts — generic tasks like "list the available tools" cause the LLM to emit `tool_name="None"`, which fails the tool-dispatch gate.

#### HITL interrupt behaviour

If the planner emits a step whose tool name matches a destructive pattern (`write`, `delete`, `drop`, `deploy`, …), the `execute_node` calls `langgraph.types.interrupt()` **before** running the tool. LangGraph serialises the current `GraphState` checkpoint to Redis and returns a `GraphInterrupt` value instead of a final state. The graph is paused in mid-flight.

To resume after approval, call `compiled.ainvoke(None, config)` with the same `thread_id`. The graph continues from the exact point of interruption — no state is lost because Redis holds the full checkpoint.

Inspect interrupted state in Redis Commander → `http://localhost:8086` (keys prefixed by the `thread_id`). The `require_user_approval` flag and `hitl_reason` string are visible in the stored checkpoint.

The `evaluate_node` also triggers an interrupt when the LLM critic scores the output `0.0` (absolute failure) — an autonomous retry would likely produce the same result; human context is required.

The active default mode is controlled by `ORCHESTRATOR_MODE` in `.env` (or the gateway container env). Valid values: `legacy` (default, ReAct loop), `pydantic_ai`, `langgraph`.

```bash
# Switch the running stack to pydantic_ai mode
ORCHESTRATOR_MODE=pydantic_ai docker compose --profile full up -d
```

#### LangGraph Finite State Machine Lifecycle

When `ORCHESTRATOR_MODE=langgraph`, every request flows through a bounded cyclic FSM implemented with LangGraph's `StateGraph`:

```text
  task ──► VALIDATE ──► PLAN ──► EXECUTE ──► EVALUATE
              ▲                                  │
              └──── retry (score < 0.7) ─────────┘
                                          pass ──► DONE
                                          fail ──► FAILED
                                          HITL ──► interrupt()
```

| Phase | What happens |
|-------|-------------|
| **VALIDATE** | Rejects malformed input before any LLM call |
| **PLAN** | LLM generates a Pydantic-validated `ExecutionPlan` with typed `PlanStep` objects; steps can reference predecessors via `{{steps.<id>.output}}` |
| **EXECUTE** | Validates step references, builds a DAG via `graphlib.TopologicalSorter`, executes with bounded concurrency (`PLAN_MAX_PARALLEL=4`, `STEP_TIMEOUT_S=30`); destructive tools trigger HITL `interrupt()` before any execution; `completed_step_ids` prevents replay duplication |
| **EVALUATE** | `CriticActorEvaluator` scores output; collects all step outputs (not just the last); score < 0.7 retries, score = 0.0 triggers HITL |
| **DONE/FAILED** | Terminal states; `AsyncRedisSaver` persists the final checkpoint without blocking the event loop |

The FSM is bounded to `MAX_ITERATIONS=15` (configurable via `GRAPH_MAX_ITERATIONS` env var). `AsyncRedisSaver` checkpoints state at every transition, enabling crash recovery and cross-process HITL resume. Execution ordering is derived by static inspection of `{{steps.*}}` references — never from model-generated fields. `PLAN_PARALLEL_ENABLED=1` enables concurrent execution of independent steps; the default is sequential. This FSM is the backbone of the 4-layer pipeline — Layer 1 validates I/O within PLAN/EXECUTE nodes, Layer 3 orchestrates multiple FSM instances across roles, and Layer 4 optimizes prompts feeding PLAN offline.

**Dependency note:** The codebase uses **pydantic-ai 0.0.20** (`result_type` / `result.data` API). Later versions (≥ 0.0.21) renamed these to `output_type` / `result.output`. The Docker image is built with the pinned version from `pyproject.toml`; do not upgrade without updating all call sites in `structured_agent.py`, `graph_orchestrator.py`, and `evaluator.py`.

---

### Phase 5 — Multi-Agent Crew (Layer 3)

**Goal:** Show per-role MCP tool scoping and the security boundary enforced by `MCPCrew`.

The demo script verifies:

1. `scope_tools("analyst", tools)` returns only `read_*` / `search_*` / `fetch_*` tools.
2. `scope_tools("writer", tools)` returns only `write_*` / `publish_*` tools.
3. `build_scoped_call_fn("analyst", ...)` raises `PermissionError` when the analyst tries to call a writer tool.
4. A two-agent crew (`analyst → writer`) is constructed and its role resolution chain is printed.

```bash
python3 - <<'EOF'
from mcp_agent_factory.crew import MCPCrew, ScopedAgent, scope_tools, build_scoped_call_fn

tools = [
	{"name": "read_file", "description": "Read a file"},
	{"name": "search_web", "description": "Web search"},
	{"name": "write_report", "description": "Write report"},
]

# Verify analyst scope
analyst_tools = scope_tools("analyst", tools)
print(f"Analyst tools ({len(analyst_tools)}):", [t["name"] for t in analyst_tools])

# Verify writer scope
writer_tools = scope_tools("writer", tools)
print(f"Writer tools ({len(writer_tools)}):", [t["name"] for t in writer_tools])

# Verify security boundary
scoped_call = build_scoped_call_fn("analyst", analyst_tools, lambda n, a: {})
try:
	scoped_call("write_report", {})
	print("ERROR: PermissionError not raised")
except PermissionError as e:
	print("PermissionError raised correctly:", str(e)[:60])
EOF
```

---

### Phase 6 — Offline Prompt Optimization (Layer 4)

**Goal:** Show the full DSPy + GEPA optimization loop in dry-run mode (no Kafka, no LLM calls).

The demo script:

1. Ingests 10 synthetic traces (mix of passing and failing).
2. Runs `PromptOptimizer.compile()` to produce `SkillAsset` objects for each failing `(role, phase)` pair.
3. Writes the compiled JSON assets to `$SKILLS_DIR` via `SkillCompiler`.
4. Prints the `index.json` manifest to confirm hot-reloadable output.

```bash
python3 - <<'EOF'
import asyncio, json
from pathlib import Path
from mcp_agent_factory.optimizer import PromptOptimizer, SkillCompiler

SKILLS_DIR = "/tmp/mcp_demo_skills"

async def main():
	opt = PromptOptimizer(dry_run=True, skills_dir=SKILLS_DIR)
	traces = await opt.ingest_traces(limit=10)
	print(f"Ingested {len(traces)} traces ({sum(t.is_failure for t in traces)} failures)")

	assets = await opt.compile(traces)
	print(f"Compiled {len(assets)} skill assets")

	compiler = SkillCompiler(output_dir=SKILLS_DIR)
	paths = compiler.compile_all(assets)
	for p in paths:
		print(f"  {p}")

	index = json.loads((Path(SKILLS_DIR) / "index.json").read_text())
	print(f"\nindex.json — {len(index['skills'])} skills registered")

asyncio.run(main())
EOF
```

To run against a live Kafka topic (requires `pip install -e ".[optimizer]"`):

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 python3 -c "
import asyncio
from mcp_agent_factory.optimizer import PromptOptimizer, SkillCompiler
async def main():
	opt = PromptOptimizer(kafka_topic='mcp-traces')
	traces = await opt.ingest_traces(limit=500)
	assets = await opt.compile(traces)
	SkillCompiler().compile_all(assets)
asyncio.run(main())
"
```

**Hot-reload without restart:** After `SkillCompiler` writes new `{skill_id}.json` assets, send `SIGHUP` to the running gateway process to reload them without a service restart:

```bash
kill -HUP $(pgrep -f "mcp_agent_factory.gateway.run")
```

The SIGHUP handler lives in the gateway process (`gateway/run.py`), not in the optimizer. The optimizer's only job is writing JSON to `$SKILLS_DIR`; the gateway reacts to the signal and hot-swaps the skill assets in place.

---

## Enterprise Architecture Reference

The demo exercises all four layers of the production pipeline documented in depth in `README.md`:

| Pattern | Where it runs | What to observe |
|---------|--------------|-----------------|
| **LangGraph FSM** — bounded cyclic state machine (VALIDATE→PLAN→EXECUTE→EVALUATE→DONE) with async Redis checkpointing, typed `PlanStep` output chaining, and DAG-derived concurrency | `graph_orchestrator.py` `GraphOrchestrator` | Phase transitions logged; `MAX_ITERATIONS=15` prevents infinite loops; `AsyncRedisSaver` checkpoints visible in Redis Commander |
| **Typed Plan Steps + Output Chaining** — `PlanStep(BaseModel)` with `{{steps.<id>.output}}` references; DAG built via `graphlib.TopologicalSorter`; bounded by `PLAN_MAX_PARALLEL` and `STEP_TIMEOUT_S` | `graph_orchestrator.py` `PlanStep`, `_build_dag`, `_resolve_references` | Unknown step references rejected at validation time; cyclic refs fall back to sequential; hung tools cancelled at timeout |
| **Handling Non-Determinism** — Pydantic schemas gate all LLM output before execution | `graph_orchestrator.py` `plan_node` | Any schema violation raises `ValidationError` logged to stderr before any tool fires |
| **Critic-Actor** — isolated evaluator re-scores actor output against original constraints | `evaluator.py` → `evaluate_node` | `EvaluationResult.score` and per-criterion breakdown logged after each execution round |
| **HITL Interrupt** — destructive tools and zero-score failures pause the graph in Redis | `graph_orchestrator.py` `execute_node` / `evaluate_node` | `GraphInterrupt` returned to caller; checkpoint visible in Redis Commander at `:8086` |
| **Decoupled I/O Interface** — graph entrypoint is transport-agnostic (`task`, `tools`, `call_tool_fn`) | `graph_orchestrator.py` `GraphOrchestrator.run()` | Same state machine handles CLI, HTTP, and future Slack/Telegram adapters without modification |
| **Multi-Agent Tool Scoping** — per-role MCP tool whitelists with hard `PermissionError`; `use_langgraph=True` delegates each agent's subtask to the Layer 2 FSM | `crew.py` `scope_tools` / `build_scoped_call_fn` / `MCPCrew._run_with_langgraph` | `PermissionError` raised on out-of-scope call; each role's allowed tool list printed in Phase 5 |
| **Offline Prompt Optimization** — real DSPy compilation (when installed) + GEPA genetic mutation; compiles hot-reloadable skill JSON assets | `optimizer.py` `PromptOptimizer` / `SkillCompiler` | `{skill_id}.json` files written to `$SKILLS_DIR`; `index.json` manifest printed in Phase 6 |
| **Cross-Layer Integration** — full 4-layer pipeline tested end-to-end | `test_cross_layer_integration.py` | 5 tests exercise Layer 1→2→3→4 with mocked LLM calls |

See `README.md → Enterprise Production Patterns` for the full rationale and state-flag reference.

---

## v1.0.0 Pipeline Complete

All four execution layers are implemented and validated:

| Layer | Module | Status |
|-------|--------|--------|
| **Layer 1 — Foundations** | `structured_agent.py`, `orchestrator.py` | ✅ PydanticAI I/O validation, schema-gated tool calls |
| **Layer 2 — Production** | `graph_orchestrator.py`, `evaluator.py` | ✅ LangGraph state machine, critic-actor loop, HITL interrupt |
| **Layer 3 — Orchestration** | `crew.py` | ✅ CrewAI multi-role crews, scoped MCP tool allow-lists, `PermissionError` boundary; `use_langgraph=True` delegates per-agent execution to Layer 2 FSM |
| **Layer 4 — Optimization** | `optimizer.py` | ✅ Real DSPy `BootstrapFewShot` compilation (when installed) + GEPA genetic mutation, hot-reloadable JSON skill assets |

Merging this branch into `main` and tagging `v1.0.0` closes the roadmap defined in the project epic.

### Release Procedure

```bash
# 1. Merge the feature branch into main
git checkout main
git merge --no-ff 3-epic-evolving-mcp-agent-factory-into-a-controllable-production-ready-multi-agent-architecture

# 2. Tag the release
git tag -a v1.0.0 -m "v1.0.0: 4-layer execution pipeline complete

Layer 1 — PydanticAI I/O validation (structured_agent.py, orchestrator.py)
Layer 2 — LangGraph deterministic state machine (graph_orchestrator.py, evaluator.py)
Layer 3 — CrewAI multi-agent orchestration with scoped MCP tool access (crew.py)
Layer 4 — DSPy+GEPA offline prompt optimization with hot-reloadable skill assets (optimizer.py)"

# 3. Push tag
git push origin main --tags
```

---

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `Gateway not ready` | Stack not running | `MCP_DEV_MODE=1 docker compose --profile full up --build -d` |
| `auth is enforced` | Gateway started without `MCP_DEV_MODE=1` | Restart stack with the env var |
| `Method not found (-32601)` | Stale gateway image | `docker compose --profile full up --build -d` |
| `Ollama is not running` | Ollama process stopped | `OLLAMA_HOST=0.0.0.0 ollama serve` |
| `model not pulled` | Ollama model absent | `ollama pull qwen3:0.6b-q4_K_M` |
| `Gateway cannot reach Ollama` | Ollama bound to `127.0.0.1` only | Restart with `OLLAMA_HOST=0.0.0.0` |
| `Agent Pipeline: no-data` | OTel collector not running or scrape lag | Wait 30 s; check `docker ps` for `otel-collector` |
| `cost_usd: 0` for Gemini | Model name not in pricing table | Ensure `router.py` `_COST_PER_M` includes the active Gemini model |
| `unexpected keyword argument 'result_type'` | Docker cache served stale image with pydantic-ai ≥ 0.0.21 | Run `docker compose --profile full down && docker compose --profile full up --build -d` to force a clean rebuild |
| Phase 4 `pydantic_ai` / `langgraph` error | `PYDANTIC_AI_MODEL` set to a deprecated model name | Use `PYDANTIC_AI_MODEL=google-gla:gemini-2.5-flash` (the default in `.env.example`) |
| Phase 4 `Tool 'None' not in available tools` | Task is open-ended; LLM emits `tool_name="None"` because no tool maps to the intent | Use the bundled concrete tasks (`echo` / `add`) — do not replace them with generic prompts like "list tools" |
| Phase 4 `Max iterations (15) reached` | Planner used wrong step-key format (`name`/`args` instead of `tool_name`/`arguments`) or evaluator kept rejecting | Rebuild the image (`--build`) so the latest `graph_orchestrator.py` (which accepts both key formats) is present |
