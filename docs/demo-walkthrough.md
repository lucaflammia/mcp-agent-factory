# demo.sh — Walkthrough

`scripts/demo.sh` is the end-to-end live demo for **MCP Agent Factory**. It exercises every layer of the stack in a single run: the MCP gateway, the analyst agent pipeline, OpenTelemetry tracing, Prometheus metrics, and Gemini provider switching.

---

## Prerequisites

| Requirement | How to satisfy |
|---|---|
| Docker stack running | `MCP_DEV_MODE=1 docker compose --profile full up -d` |
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

## Grafana Dashboard

After a successful run open:

```
http://localhost:3000/d/mcp-overview/mcp-agent-factory-e28094-overview?orgId=1&refresh=10s
```

The dashboard auto-refreshes every 10 s. If panels show "No data" immediately after the demo, wait one Prometheus scrape interval (≤ 15 s) and the panels will populate.

---

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `Gateway not ready` | Stack not running | `MCP_DEV_MODE=1 docker compose --profile full up -d` |
| `auth is enforced` | Gateway started without `MCP_DEV_MODE=1` | Restart stack with the env var |
| `Method not found (-32601)` | Stale gateway image | `docker compose --profile full up --build -d` |
| `Ollama is not running` | Ollama process stopped | `OLLAMA_HOST=0.0.0.0 ollama serve` |
| `model not pulled` | Ollama model absent | `ollama pull qwen3:0.6b-q4_K_M` |
| `Gateway cannot reach Ollama` | Ollama bound to `127.0.0.1` only | Restart with `OLLAMA_HOST=0.0.0.0` |
| `Agent Pipeline: no-data` | OTel collector not running or scrape lag | Wait 30 s; check `docker ps` for `otel-collector` |
| `cost_usd: 0` for Gemini | Model name not in pricing table | Ensure `router.py` `_COST_PER_M` includes the active Gemini model |
