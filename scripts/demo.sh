#!/usr/bin/env bash
# demo.sh — "AI Agents at Work" live demo
#
# REQUIRED SETUP:
#   MCP_DEV_MODE=1 docker compose --profile full up -d
#
# MCP_DEV_MODE=1 must be set in the environment BEFORE starting the stack so
# the gateway process boots with auth bypass enabled. It cannot be changed
# without restarting the gateway container.
#
# OPTIONAL ENV VARS (client-side):
#   GATEWAY_URL   default: http://localhost:8000
#   PDF_PATH      default: data/samples/finance_q3_2024.pdf
#   QUERY         default: "Identify key KPIs and risk areas"
#
# Phase 1: Privacy-First RAG  — agents/analyze on the local PDF
# Phase 2: Jaeger trace link  — shows the full span chain
# Phase 3: Provider switch    — re-runs with LLM_PROVIDER=openai; shows -32602 on missing key

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
PDF_PATH="${PDF_PATH:-data/samples/finance_q3_2024.pdf}"
QUERY="${QUERY:-Identify key KPIs and risk areas}"

# ── helpers ──────────────────────────────────────────────────────────────────

hr()  { printf '\n%s\n' "────────────────────────────────────────────────────"; }
hdr() { hr; printf '  %s\n' "$*"; hr; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 is required but not installed."; exit 1; }
}

check_health() {
  local url="$GATEWAY_URL/health"
  local max_wait=30
  local waited=0
  printf 'Waiting for gateway at %s ' "$url"
  until curl -sf "$url" >/dev/null 2>&1; do
    if [ "$waited" -ge "$max_wait" ]; then
      echo ""
      echo "ERROR: Gateway not ready after ${max_wait}s. Run: docker compose up -d"
      exit 1
    fi
    printf '.'
    sleep 2
    waited=$((waited + 2))
  done
  echo " ready."
}

mcp_call() {
  # mcp_call <method> <params_json> [extra_curl_opts...]
  local method="$1"
  local params="$2"
  shift 2
  curl -sf "$@" \
    -X POST "$GATEWAY_URL/mcp" \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$method\",\"params\":$params}"
}

# ── preflight ─────────────────────────────────────────────────────────────────

require_cmd curl
require_cmd jq

check_health

if [ ! -f "$PDF_PATH" ]; then
  echo "ERROR: PDF not found at '$PDF_PATH'. Set PDF_PATH to a valid path."
  exit 1
fi

# Gateway runs in Docker; ./data is mounted at /app/data inside the container.
# Strip the leading "data/" prefix and prepend the container mount point.
CONTAINER_PDF_PATH="/app/${PDF_PATH}"
PARAMS="{\"pdf_path\":\"$CONTAINER_PDF_PATH\",\"query\":\"$QUERY\"}"
PARAMS_OPENAI="{\"pdf_path\":\"$CONTAINER_PDF_PATH\",\"query\":\"$QUERY\",\"provider\":\"openai\"}"

# Verify the gateway started with MCP_DEV_MODE=1 (auth bypass).
GATEWAY_CONTAINER=$(docker ps --filter "name=mcp-agent-factory-gateway" --format "{{.Names}}" 2>/dev/null | head -1)
if [ -n "$GATEWAY_CONTAINER" ]; then
  GW_DEV_MODE=$(docker exec "$GATEWAY_CONTAINER" sh -c 'echo $MCP_DEV_MODE' 2>/dev/null)
  if [ "$GW_DEV_MODE" != "1" ]; then
    echo "ERROR: Gateway is running without MCP_DEV_MODE=1 — auth is enforced."
    echo ""
    echo "  Restart the stack with:"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up --build -d"
    echo ""
    exit 1
  fi
fi

# Check Ollama is reachable on the host.
if ! curl -sf "http://localhost:11434/" >/dev/null 2>&1; then
  echo "ERROR: Ollama is not running on localhost:11434."
  echo ""
  echo "  Start Ollama and pull the required model, then retry:"
  echo "    OLLAMA_HOST=0.0.0.0 ollama serve &"
  echo "    ollama pull llama3.2"
  echo ""
  echo "  Or set OLLAMA_MODEL to a model you have already pulled."
  exit 1
fi

# Check the required Ollama model is pulled.
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:0.6b-q4_K_M}"
if ! curl -sf "http://localhost:11434/api/tags" 2>/dev/null | grep -q "\"${OLLAMA_MODEL}"; then
  echo "ERROR: Ollama model \"${OLLAMA_MODEL}\" is not pulled."
  echo ""
  echo "  Pull it with:"
  echo "    ollama pull ${OLLAMA_MODEL}"
  echo ""
  echo "  Or set OLLAMA_MODEL to a model you already have (e.g. qwen3:0.6b-q4_K_M)."
  exit 1
fi

# Verify the gateway container can reach Ollama.
# On Linux, Ollama must bind to 0.0.0.0 (not just 127.0.0.1) for host.docker.internal to work.
if [ -n "$GATEWAY_CONTAINER" ]; then
  if ! docker exec "$GATEWAY_CONTAINER" wget -qO- "http://host.docker.internal:11434/" >/dev/null 2>&1; then
    echo "ERROR: Gateway container cannot reach Ollama at host.docker.internal:11434."
    echo ""
    echo "  On Linux, Ollama must listen on all interfaces, not just 127.0.0.1."
    echo "  Restart Ollama with:"
    echo "    OLLAMA_HOST=0.0.0.0 ollama serve"
    echo ""
    echo "  Then retry the demo."
    exit 1
  fi
fi

# ── Phase 1: Privacy-First RAG ────────────────────────────────────────────────

hdr "PHASE 1 — Privacy-First RAG (agents/analyze)"
echo "  PDF:   $PDF_PATH"
echo "  Query: $QUERY"
echo ""

PHASE1=$(mcp_call "agents/analyze" "$PARAMS")

if echo "$PHASE1" | jq -e '.error' >/dev/null 2>&1; then
  ERROR_CODE=$(echo "$PHASE1" | jq -r '.error.code // empty')
  if [ "$ERROR_CODE" = "-32601" ]; then
    echo "ERROR: Method not found — the gateway image is stale."
    echo ""
    echo "  Rebuild and restart with:"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up --build -d"
    echo ""
    echo "  (The agents/analyze handler was added after this image was built.)"
  elif [ "$ERROR_CODE" = "-32001" ]; then
    echo "ERROR: Authentication required — gateway started without MCP_DEV_MODE=1."
    echo ""
    echo "  Restart the stack with:"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up --build -d"
    echo ""
  else
    echo "ERROR from gateway:"
    echo "$PHASE1" | jq '.error'
  fi
  exit 1
fi

echo "$PHASE1" | jq '{
  provider: .result.provider,
  pages_read: .result.pages_read,
  chunks_before: .result.chunks_before_pruning,
  chunks_after: .result.chunks_after_pruning,
  input_tokens: .result.input_tokens,
  output_tokens: .result.output_tokens,
  cost_usd: .result.cost_usd
}'
echo ""
echo "EXECUTIVE SUMMARY:"
echo "$PHASE1" | jq -r '.result.summary'

# ── Phase 2: Jaeger Trace ─────────────────────────────────────────────────────

hdr "PHASE 2 — Observe the Trace (Jaeger)"
echo "  Open Jaeger and search for service 'mcp-gateway':"
echo ""
echo "    http://localhost:16686/search?service=mcp-gateway&operation=agents%2Fanalyze"
echo ""
echo "  Expected span chain:"
echo "    mcp.agents/analyze"
echo "      └─ agent.pdf_extract   [pages_read, chunk_count]"
echo "      └─ agent.prune         [input_tokens, output_tokens]"
echo "      └─ agent.pii_scrub     [input_tokens, output_tokens]"
echo "      └─ agent.llm_route     [provider, cost_usd]"

# ── Phase 3: Provider Switch ──────────────────────────────────────────────────

hdr "PHASE 3 — Live Provider Switch (fail-fast on missing key)"
echo "  Requesting provider=openai with no OPENAI_API_KEY configured on the gateway..."
echo ""

PHASE3=$(mcp_call "agents/analyze" "$PARAMS_OPENAI" || true)

echo "Gateway response:"
echo "$PHASE3" | jq '{code: .error.code, message: .error.message}' 2>/dev/null \
  || echo "$PHASE3"

if echo "$PHASE3" | jq -e '.error.code == -32602' >/dev/null 2>&1; then
  echo ""
  echo "  ✓ Correct: -32602 Invalid params — provider not configured."
else
  echo ""
  echo "  NOTE: Expected -32602 but got a different response."
fi

hr
echo "  Demo complete."
hr
echo ""
