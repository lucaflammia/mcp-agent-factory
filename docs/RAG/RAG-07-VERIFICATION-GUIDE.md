# RAG Production Pipeline — Verification Guide

This guide walks through verifying every acceptance criterion for the production RAG pipeline (RAG-02 through RAG-06).

---

## Prerequisites

```bash
# Install dependencies (includes sentence-transformers for 384-dim embeddings)
pip install -e ".[dev]"
pip install sentence-transformers psycopg[binary]

# Start supporting services (Postgres + pgvector, Redis, Prometheus, Grafana)
docker-compose up -d

# Run DB migrations
psql $DATABASE_URL -f migrations/001_pgvector_init.sql
psql $DATABASE_URL -f migrations/002_rag05_embedder_versioning.sql
psql $DATABASE_URL -f migrations/003_rag_source_id.sql
```

---

## 1. Idempotent Ingestion (RAG-02)

### Run ingestion twice, expect no duplicates

```bash
# First ingest (DATABASE_URL required — omitting it uses an in-memory store that is discarded on exit)
DATABASE_URL=postgresql://mcp:mcp-dev-password@localhost:5432/knowledge \
python -m mcp_agent_factory.knowledge.ingest --source data/samples/finance_q3_2024.pdf

# Second ingest of same file — must be a no-op (same content_hash)
DATABASE_URL=postgresql://mcp:mcp-dev-password@localhost:5432/knowledge \
python -m mcp_agent_factory.knowledge.ingest --source data/samples/finance_q3_2024.pdf
```

**Expected:** second run logs `Skipping chunk <id>: content_hash already exists` for every chunk; row count in `chunks` table is unchanged.

### Verify chunk metadata

```sql
SELECT owner_id, embedder_id, content_hash, source_id FROM chunks LIMIT 5;
```

All four columns must be non-null (or source_id may be null for backfilled rows).

### Verify PII scrubbing

```bash
python -m pytest tests/test_rag02_idempotent_ingestion.py -v -k "pii"
```

---

## 2. Guarded Retrieval (RAG-03)

### Tenant isolation smoke test

```bash
python -m pytest tests/test_pgvector_store.py -v -k "tenant"
```

A query with `tenant=A` must return zero results for chunks ingested under `tenant=B`.

### Full RAG-02 / ingestion test suite

```bash
python -m pytest tests/test_rag02_idempotent_ingestion.py tests/test_ingest.py -v
```

---

## 3. Validated Generation with Citations (RAG-04)

### Schema validation and citation check

```bash
python -m pytest tests/test_rag04_validated_generation.py -v
```

Inject a question with known source chunks; assert the response includes `citations` referencing the correct `chunk_id` values and passes schema validation.

---

## 4. Embedder Versioning and Dual-Write Cutover (RAG-05)

### Version recorded in every embedding, dual-write, and cutover

```bash
python -m pytest tests/test_rag05_embedder_versioning.py -v
```

---

## 5. Evaluation Gates (RAG-06)

### Run the eval harness against the golden set

```bash
python -m evals.runner --dataset rag_qa --tag manual-run
```

Output must include `golden_set_version` in `meta` and separate `retrieval` / `generation` metric blocks.

### Simulate a quality regression

```bash
# Compare two run tags — the compare tool exits non-zero on regression
python -m evals.compare baseline manual-run

# To see raw JSON diff
python -m evals.compare baseline manual-run --json
```

Run tags are set via `--tag` when calling `evals.runner`. The baseline tag is `baseline` (file: `evals/results/baseline.json`).

---

## 6. Operations (RAG-06)

### Backup and restore drill

```bash
python -c "
import asyncio
from mcp_agent_factory.knowledge.vector_store import PgVectorStore
import os

store = PgVectorStore(os.environ['DATABASE_URL'])

async def drill():
    import time
    meta = await store.backup('/tmp/rag-backup-drill.sql')
    print(f'Backup written to {meta[\"backup_path\"]} ({meta[\"chunk_count\"]} chunks)')
    t0 = time.time()
    result = await store.restore(meta)
    elapsed = time.time() - t0
    print(f'Restore complete: {result[\"chunks_restored\"]} chunks in {elapsed:.2f}s')

asyncio.run(drill())
"
```

Record the restore time. This satisfies the documented backup/restore drill requirement.

### Right to be forgotten

```bash
python -c "
import asyncio
from mcp_agent_factory.knowledge.vector_store import PgVectorStore
import os

store = PgVectorStore(os.environ['DATABASE_URL'])

async def rtbf():
    # Delete by source
    deleted = await store.delete_by_source_id('finance_q3_2024.pdf')
    print(f'Deleted {deleted} chunks by source_id')

    # Verification query — must return 0 results
    results = await store.search('finance Q3 revenue', filters={'source_id': 'finance_q3_2024.pdf'})
    assert len(results) == 0, f'Expected 0 results, got {len(results)}'
    print('Verification query returned 0 results — RTBF confirmed')

asyncio.run(rtbf())
"
```

### Weekly compaction

```bash
python -c "
import asyncio
from mcp_agent_factory.knowledge.vector_store import PgVectorStore
import os

store = PgVectorStore(os.environ['DATABASE_URL'])
asyncio.run(store.compact())
print('Compaction complete')
"
```

---

## 7. Observability and Grafana Dashboards (RAG-07)

### Prerequisites: start the full stack

```bash
docker compose --profile full up -d
```

Open `http://localhost:3000/d/rag-metrics` (login: admin / admin).

---

### Dashboard overview

The **RAG Pipeline — Metrics & Quality Gates** dashboard has five panels, each answering one plain question:

| Panel | Type | Question it answers | Good / Bad signal |
|---|---|---|---|
| **Chunks in Index** | Time series | Is there data in the index, and is it growing? | Green line = data present; red = 0 chunks (nothing to search) |
| **Empty Result Rate** | Time series | Are queries consistently returning results? (retrieval layer only) | Green <10 %; Yellow 10–25 %; Red >25 % |
| **Refusal Rate** | Time series | Is the generation pipeline refusing over time? (retrieval + LLM validation) | Green <10 %; Yellow 10–30 %; Red >30 %; tracks same as Empty Result Rate with stub LLM — diverges once real LLM is configured |
| **Similarity Score Distribution** | Time series | Is retrieval finding relevant chunks? | p50 above 0.5 = good coverage; p50 below 0.3 = coverage gap |
| **Best Match Score Per Query** | Time series | How good was the last query? | Above 0.7 = strong match; below 0.4 = off-topic or missing data |

---

### How to trigger data

Run a few semantically relevant queries (the index holds financial data):

```bash
for q in "revenue Q3" "net income" "operating margin" "cash flow"; do
  curl -s -X POST http://localhost:8000/query \
    -H 'Content-Type: application/json' \
    -d "{\"question\": \"$q\", \"tenant\": \"default\"}" > /dev/null
done
```

Prometheus scrapes every 15 s, so panels update within ~30 s of the queries.

---

### Panel 1 — Chunks in Index (time series)

Shows the total chunk count over time — useful for confirming ingestion happened and spotting unexpected drops.

**What to verify:**
```bash
curl -s http://localhost:8000/metrics | grep rag_index_chunk_count
# Expected: rag_index_chunk_count 4  (or however many chunks were ingested)
```

If the line stays at 0, ingest the sample document first:
```bash
DATABASE_URL=postgresql://mcp:mcp-dev-password@localhost:5432/knowledge \
python -m mcp_agent_factory.knowledge.ingest \
  --source data/samples/finance_q3_2024.pdf \
  --tenant default
```

---

### Panel 2 — Empty Result Rate (time series)

Shows the fraction of queries where retrieval returned **no chunks at all** (`reason="empty_retrieval"`). A spike here means new query types aren't covered by the index.

> **Note — same curve as Refusal Rate with the stub LLM:** Without a real LLM configured, every refusal has `reason="empty_retrieval"`, so both panels track identically. They diverge once a real LLM is wired in: LLM calls that fail JSON schema validation increment `reason="validation_failure"` on the Refusal Rate panel only, while this panel stays low if retrieval itself is working. Use Empty Result Rate to diagnose the retrieval layer; use Refusal Rate to diagnose the full generation pipeline.

**What to verify:**
```bash
curl -s http://localhost:8000/metrics | grep rag_query_empty_results_total
```

A non-zero value means some queries returned no chunks. Expected to be low for financial domain queries against the sample index.

---

### Panel 3 — Refusal Rate (time series)

Shows the fraction of queries the model refused to answer over time. A rising trend after ingesting new content suggests the new chunks score below the similarity threshold.

**What to verify:**
```bash
curl -s http://localhost:8000/metrics | grep rag_generation_refusal_total
```

Refusals occur when the best matching chunk scores below the minimum threshold (0.3). Out-of-scope queries like "weather forecast" will be refused.

**Simulate an accepted query (non-refusal):**

A query whose top-ranked chunk scores above the threshold produces a full LLM answer with citations. Use a question that maps directly to indexed content:

```bash
curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"question": "What was the net income in Q3 2024?", "tenant": "default"}' \
  | python -m json.tool
```

Expected shape — `answer` is populated, `citations` is a non-empty array of chunk IDs, `refused` is `false`, and `refusal_reason` is `null`:

```json
{
    "answer": "Q3 2024 Financial Report - Confidential\nExecutive Summary\nTotal revenue for Q3 2024 reached USD 52.4 million, representing a 14% year-over-year growth. EBITDA margin\nimproved to 19.2% from 16.8% in Q3 2023. Net income was USD 8.1 million.",
    "refused": false,
    "refusal_reason": null,
    "citations": [
        "chunk-1"
    ]
}
```

> **Note:** Without a real LLM configured, the gateway returns the raw text of the top-ranked chunk as the answer. With an LLM, `answer` will be a synthesised natural-language response grounded in the retrieved chunks.

After this call, check that `rag_generation_refusal_total` did **not** increment while `rag_retrieval_score_bucket` updated:

```bash
curl -s http://localhost:8000/metrics | grep -E 'rag_generation_refusal_total|rag_top1_score'
# rag_top1_score{tenant="default"} 0.69
# rag_generation_refusal_total{tenant="default"} 0  (unchanged from before)
```

This confirms the refusal rate stays below 100% when the index contains relevant content.

**Simulate refusals to test alerting:**
```bash
for i in $(seq 1 10); do
  curl -s -X POST http://localhost:8000/query \
    -H 'Content-Type: application/json' \
    -d "{\"question\": \"out-of-scope $i\", \"tenant\": \"default\"}" > /dev/null
done
# Wait ~15s for Prometheus to scrape, then check if RagRefusalSpike is firing.
# IMPORTANT: run this within 5 minutes of the queries above — the alert uses a 5m window.
sleep 15
curl -s http://localhost:9090/api/v1/alerts | python -m json.tool | grep -i -A5 "refusal"
```

> **Troubleshooting — empty alert output:** If the grep returns nothing, check that the queries were fired recently (within the last 5 minutes). The alert uses `increase(rag_generation_refusal_total[5m]) > 5`, which requires at least two Prometheus scrapes capturing the counter going up. Run the query loop again and check immediately after the `sleep 15`.


---

### Panel 4 — Similarity Score Distribution

**What it shows:** p50, p75, p90, p95 percentile lines over time. A healthy index keeps p50 above 0.5 for domain-relevant queries.

**What to verify:**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=rag_retrieval_score_bucket' \
  | python -m json.tool | head -30
```

If the panel shows "No data", confirm Prometheus is scraping the gateway:
```bash
curl -s 'http://localhost:9090/api/v1/targets' | python -m json.tool | grep -B2 '"mcp-gateway"'
```

The target health must be `"health": "up"`.

---

### Panel 5 — Best Match Score Per Query

**What it shows:** the cosine similarity of the top-ranked chunk for the most recent query, as a live gauge.

**What to verify:**
```bash
curl -s http://localhost:8000/metrics | grep rag_top1_score
# Expected: rag_top1_score{tenant="default"} 0.7x  (for a financial query)
```

Run one more query and confirm the value updates within 15 s:
```bash
curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"question": "EBITDA margin", "tenant": "default"}' | python -m json.tool
```

---

## 8. Full Test Suite

```bash
pytest tests/ -v --tb=short
```

All tests must pass with no failures.

---

## 9. CI Nightly Eval Gate

The nightly job runs automatically at `02:00 UTC` via `.github/workflows/ci.yml`. To trigger it manually:

```bash
gh workflow run ci.yml --ref rag-prod
```

Monitor the run:

```bash
node scripts/ci_monitor.cjs runs --branch rag-prod
node scripts/ci_monitor.cjs watch <run-id>
```

A regression beyond 5% on any metric causes a non-zero exit and marks the run red.
