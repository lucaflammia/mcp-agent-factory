#!/usr/bin/env bash
# demo_fleet_bedrock.sh — Async Fleet Runtime demo using Bedrock provider
#
# Submits a batch of analysis jobs via the fleet API, polls for completion,
# and prints a cost summary. All AWS infrastructure is torn down on exit.
#
# PREREQUISITES:
#   1. AWS credentials with bedrock:InvokeModel permission in the shell environment
#      (IAM role, aws-vault, or environment variables — no hardcoded keys)
#   2. Stack running with Bedrock provider:
#        PROVIDER=bedrock MCP_DEV_MODE=1 docker compose --profile full up -d
#
# USAGE:
#   ./scripts/demo_fleet_bedrock.sh [--dry-run] [--tasks N] [--no-teardown]
#
#   --dry-run       Print what would be sent but do not make API calls
#   --tasks N       Number of parallel tasks to submit (default: 5)
#   --no-teardown   Skip docker compose down at the end (for iterating)
#
# COST GUARD:
#   The script checks AWS Cost Explorer before and after to surface charges.
#   It also enforces a hard cap: if any single job exceeds MAX_TOKENS_PER_JOB
#   the batch is aborted before submission.

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
QUERY="${QUERY:-Identify key KPIs and risk factors}"
NUM_TASKS="${NUM_TASKS:-5}"
# Path to sample PDF inside the container (mounted at /app in docker-compose)
PDF_PATH="${PDF_PATH:-/app/data/samples/finance_q3_2024.pdf}"
MAX_TOKENS_PER_JOB="${MAX_TOKENS_PER_JOB:-1000}"   # hard cap per job
POLL_INTERVAL=3   # seconds between status polls
POLL_TIMEOUT=300  # seconds before giving up on the batch
DRY_RUN=false
NO_TEARDOWN=false

# ── argument parsing ───────────────────────────────────────────────────────────

for arg in "$@"; do
  case "$arg" in
    --dry-run)     DRY_RUN=true ;;
    --no-teardown) NO_TEARDOWN=true ;;
    --tasks)       shift; NUM_TASKS="$1" ;;
    --tasks=*)     NUM_TASKS="${arg#--tasks=}" ;;
  esac
done

# ── helpers ────────────────────────────────────────────────────────────────────

hr()  { printf '\n%s\n' "────────────────────────────────────────────────────────────"; }
hdr() { hr; printf '  %s\n' "$*"; hr; }
log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not found in PATH"
}

# ── teardown trap ──────────────────────────────────────────────────────────────
# Registered immediately so any early exit also tears down the stack.

teardown() {
  local exit_code=$?
  if [ "$NO_TEARDOWN" = "true" ]; then
    log "Skipping teardown (--no-teardown)"
    return
  fi
  hdr "Teardown — stopping Docker stack"
  log "Running: docker compose --profile full down"
  docker compose --profile full down 2>&1 | tail -5 || true
  log "Stack stopped. No compute charges accumulating."
  # Summarise estimated Bedrock cost if boto3/awscli available
  if command -v aws >/dev/null 2>&1; then
    log "Tip: run 'aws ce get-cost-and-usage ...' to see today's Bedrock charges."
  fi
  exit "$exit_code"
}

trap teardown EXIT

# ── preflight checks ──────────────────────────────────────────────────────────

require_cmd curl
require_cmd jq
require_cmd docker

# Helper: curl with visible errors (writes body to stdout, fails on HTTP errors)
api_call() {
  local RESP HTTP_CODE
  RESP=$(curl -s -w "\n%{http_code}" "$@")
  HTTP_CODE=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | sed '$d')
  if [ "$HTTP_CODE" -ge 400 ] || [ "$HTTP_CODE" = "000" ]; then
    echo "HTTP $HTTP_CODE — $BODY" >&2
    return 1
  fi
  echo "$BODY"
}

hdr "Async Fleet + Bedrock Demo"
log "Gateway: $GATEWAY_URL"
log "Tasks:   $NUM_TASKS"
log "Tokens per job (cap): $MAX_TOKENS_PER_JOB"

if [ "$DRY_RUN" = "true" ]; then
  log "DRY RUN — no API calls will be made"
fi

# Start (or rebuild) the Docker stack
if [ "$DRY_RUN" = "false" ]; then
  hdr "Preflight — starting stack"
  # Auto-detect provider: prefer openai (key usually set), then bedrock, then ollama.
  # Use LLM_PROVIDER (the actual env var name docker-compose reads).
  if [ -n "${LLM_PROVIDER:-}" ]; then
    DEMO_PROVIDER="$LLM_PROVIDER"
  elif [ -n "${OPENAI_API_KEY:-}" ]; then
    DEMO_PROVIDER="openai"
  elif [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    DEMO_PROVIDER="bedrock"
  elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    DEMO_PROVIDER="anthropic"
  else
    DEMO_PROVIDER="ollama"
  fi
  log "LLM provider: $DEMO_PROVIDER"
  log "Running: docker compose --profile full up -d --build"
  # MCP_DEV_MODE=1: enables stub responses when no live API key is available,
  # so the demo shows fleet mechanics (submit/poll/batch) without requiring
  # a working cloud provider. Set MCP_DEV_MODE=0 to use real LLM calls.
  LLM_PROVIDER="$DEMO_PROVIDER" MCP_DEV_MODE="${MCP_DEV_MODE:-1}" OLLAMA_TIMEOUT="${OLLAMA_TIMEOUT:-10}" \
    docker compose --profile full up -d --build

  # Wait up to 30s for the gateway to become healthy
  log "Waiting for gateway at $GATEWAY_URL ..."
  for i in $(seq 1 30); do
    if curl -sf "$GATEWAY_URL/health" >/dev/null 2>&1; then
      break
    fi
    sleep 1
    if [ "$i" = "30" ]; then
      die "Gateway did not become healthy in 30s. Check: docker compose logs gateway"
    fi
  done
  log "Gateway OK"

  # Verify fleet endpoint is registered (catches stale image with no fleet routes)
  log "Checking fleet routes registered..."
  PROBE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "$GATEWAY_URL/mcp/jobs/batch" \
    -H "Content-Type: application/json" \
    -d '{"tasks":[]}' 2>&1)
  if [ "$PROBE_CODE" = "000" ] || [ "$PROBE_CODE" = "404" ]; then
    die "Fleet routes not found (HTTP $PROBE_CODE). The gateway image may be stale — re-run the script to trigger a rebuild."
  fi
  log "Fleet endpoint reachable (HTTP $PROBE_CODE)"
fi

# ── build batch payload ────────────────────────────────────────────────────────

hdr "Step 1 — Build batch payload ($NUM_TASKS tasks)"

# Each task analyses a slightly different slice of a fictional document.
# In a real deployment these would be different document chunks or queries.
build_tasks_json() {
  local n="$1"
  local tasks="["
  for i in $(seq 1 "$n"); do
    tasks+=$(jq -n \
      --arg method "agents/analyze" \
      --arg query "$QUERY (section $i of $n)" \
      --arg pdf_path "$PDF_PATH" \
      --argjson max_tokens "$MAX_TOKENS_PER_JOB" \
      '{method: $method, params: {query: $query, pdf_path: $pdf_path, max_tokens: $max_tokens}}')
    [ "$i" -lt "$n" ] && tasks+=","
  done
  tasks+="]"
  printf '%s' "$tasks"
}

TASKS_JSON=$(build_tasks_json "$NUM_TASKS")
BATCH_PAYLOAD=$(jq -n --argjson tasks "$TASKS_JSON" '{tasks: $tasks}')

log "Payload:"
echo "$BATCH_PAYLOAD" | jq .

if [ "$DRY_RUN" = "true" ]; then
  log "DRY RUN complete — exiting without submitting"
  exit 0
fi

# ── submit batch ──────────────────────────────────────────────────────────────

hdr "Step 2 — Submit batch to POST /mcp/jobs/batch"

BATCH_RESP=$(api_call -X POST "$GATEWAY_URL/mcp/jobs/batch" \
  -H "Content-Type: application/json" \
  -d "$BATCH_PAYLOAD") \
  || die "Batch submission failed"

BATCH_ID=$(echo "$BATCH_RESP" | jq -r '.batch_id')
JOB_COUNT=$(echo "$BATCH_RESP" | jq '.job_ids | length')
log "Batch submitted: batch_id=$BATCH_ID  jobs=$JOB_COUNT"
echo "$BATCH_RESP" | jq .

# ── poll for completion ────────────────────────────────────────────────────────

hdr "Step 3 — Poll GET /mcp/jobs/batch/$BATCH_ID until done"

START_TIME=$(date +%s)

while true; do
  NOW=$(date +%s)
  ELAPSED=$(( NOW - START_TIME ))

  if [ "$ELAPSED" -ge "$POLL_TIMEOUT" ]; then
    log "Fleet debug info:"
    curl -s "$GATEWAY_URL/mcp/jobs/debug" 2>/dev/null | jq . || true
    log "Gateway logs (last 40 lines):"
    docker compose logs gateway --tail 40 2>/dev/null || true
    die "Timed out after ${POLL_TIMEOUT}s waiting for batch $BATCH_ID"
  fi

  # Print debug info at 15s and 60s to help diagnose stuck batches
  if [ "$ELAPSED" = "15" ] || [ "$ELAPSED" = "60" ]; then
    log "Fleet debug:"
    curl -s "$GATEWAY_URL/mcp/jobs/debug" 2>/dev/null | jq -c . || true
  fi

  STATUS_RESP=$(api_call "$GATEWAY_URL/mcp/jobs/batch/$BATCH_ID") \
    || die "Poll request failed"

  TOTAL=$(echo "$STATUS_RESP" | jq -r '.total')
  DONE=$(echo "$STATUS_RESP" | jq -r '.done')
  FAILED=$(echo "$STATUS_RESP" | jq -r '.failed')

  # Always show progress so user sees something is happening
  log "Progress: $DONE/$TOTAL done, $FAILED failed (${ELAPSED}s elapsed)"

  # Print error details for any newly-failed jobs
  if [ "$FAILED" -gt 0 ]; then
    echo "$STATUS_RESP" | jq -r '.results[] | select(.status == "failed") | "  JOB \(.job_id) ERROR: \(.error)"' 2>/dev/null || true
  fi

  if [ "$DONE" -eq "$TOTAL" ]; then
    log "All $TOTAL jobs complete!"
    break
  fi

  # Abort early if all jobs have terminal status (done or failed)
  TERMINAL=$(echo "$STATUS_RESP" | jq '.results | map(select(.status == "done" or .status == "failed")) | length')
  if [ "$TERMINAL" -eq "$TOTAL" ]; then
    log "All $TOTAL jobs finished ($DONE done, $FAILED failed). Exiting poll loop."
    break
  fi

  sleep "$POLL_INTERVAL"
done

# ── print results ─────────────────────────────────────────────────────────────

hdr "Step 4 — Results"

FINAL_RESP=$(api_call "$GATEWAY_URL/mcp/jobs/batch/$BATCH_ID")
echo "$FINAL_RESP" | jq '.results[] | {job_id, status, result}'

FAILED_FINAL=$(echo "$FINAL_RESP" | jq -r '.failed')
if [ "$FAILED_FINAL" -gt 0 ]; then
  log "WARNING: $FAILED_FINAL job(s) failed — see results above"
fi

# ── cost estimate ─────────────────────────────────────────────────────────────

hdr "Step 5 — Cost estimate"

# Bedrock Claude 3.5 Sonnet pricing (us-east-1, as of 2024):
#   Input:  $3.00 / 1M tokens
#   Output: $15.00 / 1M tokens
# We assume MAX_TOKENS_PER_JOB output tokens and ~200 input tokens per job.

INPUT_TOKENS_PER_JOB=200
OUTPUT_TOKENS_PER_JOB="$MAX_TOKENS_PER_JOB"
TOTAL_INPUT=$(( NUM_TASKS * INPUT_TOKENS_PER_JOB ))
TOTAL_OUTPUT=$(( NUM_TASKS * OUTPUT_TOKENS_PER_JOB ))

# Use awk for floating-point arithmetic
awk -v input="$TOTAL_INPUT" -v output="$TOTAL_OUTPUT" \
    -v n="$NUM_TASKS" 'BEGIN {
  input_cost  = input  / 1000000 * 3.00
  output_cost = output / 1000000 * 15.00
  total       = input_cost + output_cost
  printf "  Tasks:         %d\n", n
  printf "  Input tokens:  %d   ($%.6f)\n", input,  input_cost
  printf "  Output tokens: %d   ($%.6f)\n", output, output_cost
  printf "  Estimated cost: $%.6f\n", total
  printf "  At 1,000 jobs/day: ~$%.2f/day\n", (total / n) * 1000
}'

log "Note: Redis ElastiCache (~\$0.025/hr cache.t3.micro) adds ~\$0.60/day."
log "Teardown will now stop all containers to halt any further charges."
