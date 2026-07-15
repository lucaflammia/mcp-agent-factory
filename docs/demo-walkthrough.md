# demo.sh — Walkthrough

`scripts/demo.sh` is the end-to-end live demo for **MCP Agent Factory**. It exercises every layer of the stack in a single run: the MCP gateway, the analyst agent pipeline, OpenTelemetry tracing, Prometheus metrics, Gemini provider switching, and the three orchestrator backends (legacy ReAct, PydanticAI structured, LangGraph state machine).

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
| `ORCHESTRATOR_MODE` | `react` | Orchestration backend: `react`, `pydantic_ai`, or `langgraph` |
| `PYDANTIC_AI_MODEL` | `google-gla:gemini-2.5-flash` | Model used by the PydanticAI and LangGraph backends |

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
| **MCP Inspector** | `http://localhost:6274` | Verify MCP tool handshake and test tool calls against the gateway |

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
| 2 | `langgraph` | `"Add the numbers 17 and 25 using the add tool"` | Cyclic state machine (validate → plan → execute → evaluate → done) with `thread_id` checkpointing via `RedisSaver`; max 15 iterations |

Tasks are chosen to be concrete and unambiguous: each maps to exactly one available tool (`echo` or `add`), so neither the planner nor the evaluator can route to a non-existent tool. Do not change these to open-ended prompts — generic tasks like "list the available tools" cause the LLM to emit `tool_name="None"`, which fails the tool-dispatch gate.

#### HITL interrupt behaviour

If the planner emits a step whose tool name matches a destructive pattern (`write`, `delete`, `drop`, `deploy`, …), the `execute_node` calls `langgraph.types.interrupt()` **before** running the tool. LangGraph serialises the current `GraphState` checkpoint to Redis and returns a `GraphInterrupt` value instead of a final state. The graph is paused in mid-flight.

To resume after approval, call `compiled.ainvoke(None, config)` with the same `thread_id`. The graph continues from the exact point of interruption — no state is lost because Redis holds the full checkpoint.

Inspect interrupted state in Redis Commander → `http://localhost:8086` (keys prefixed by the `thread_id`). The `require_user_approval` flag and `hitl_reason` string are visible in the stored checkpoint.

The `evaluate_node` also triggers an interrupt when the LLM critic scores the output `0.0` (absolute failure) — an autonomous retry would likely produce the same result; human context is required.

The active default mode is controlled by `ORCHESTRATOR_MODE` in `.env` (or the gateway container env). Valid values: `react` (default), `pydantic_ai`, `langgraph`.

```bash
# Switch the running stack to pydantic_ai mode
ORCHESTRATOR_MODE=pydantic_ai docker compose --profile full up -d
```

**Dependency note:** The codebase uses **pydantic-ai 0.0.20** (`result_type` / `result.data` API). Later versions (≥ 0.0.21) renamed these to `output_type` / `result.output`. The Docker image is built with the pinned version from `pyproject.toml`; do not upgrade without updating all call sites in `structured_agent.py`, `graph_orchestrator.py`, and `evaluator.py`.

---

## Enterprise Architecture Reference

The demo exercises three enterprise production patterns documented in depth in `README.md`:

| Pattern | Where it runs | What to observe |
|---------|--------------|-----------------|
| **Handling Non-Determinism** — Pydantic schemas gate all LLM output before execution | `graph_orchestrator.py` `plan_node` | Any schema violation raises `ValidationError` logged to stderr before any tool fires |
| **Critic-Actor** — isolated evaluator re-scores actor output against original constraints | `evaluator.py` → `evaluate_node` | `EvaluationResult.score` and per-criterion breakdown logged after each execution round |
| **HITL Interrupt** — destructive tools and zero-score failures pause the graph in Redis | `graph_orchestrator.py` `execute_node` / `evaluate_node` | `GraphInterrupt` returned to caller; checkpoint visible in Redis Commander at `:8086` |

See `README.md → Enterprise Production Patterns` for the full rationale and state-flag reference.

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
