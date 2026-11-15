# RAG Production Pipeline — Verification Guide

This guide walks through verifying every acceptance criterion for the production RAG pipeline (RAG-02 through RAG-06).

---

## Prerequisites

```bash
# Install dependencies
pip install -e ".[dev]"

# Start supporting services (Postgres + pgvector, Redis, Prometheus, Grafana)
docker-compose up -d

# Run DB migrations
psql $DATABASE_URL -f migrations/001_pgvector_init.sql
psql $DATABASE_URL -f migrations/002_rag05_embedder_versioning.sql
```

---

## 1. Idempotent Ingestion (RAG-02)

### Run ingestion twice, expect no duplicates

```bash
# First ingest
python -m mcp_agent_factory.knowledge.ingest --source data/samples/finance_q3_2024.pdf

# Second ingest of same file — must be a no-op (same content_hash)
python -m mcp_agent_factory.knowledge.ingest --source data/samples/finance_q3_2024.pdf
```

**Expected:** second run logs `Skipping chunk <id>: content_hash already exists` for every chunk; row count in `chunks` table is unchanged.

### Verify chunk metadata

```sql
SELECT tenant, embedder_id, content_hash FROM chunks LIMIT 5;
```

All three columns must be non-null.

### Verify PII scrubbing

```bash
python -m pytest tests/test_pii.py -v
```

---

## 2. Guarded Retrieval (RAG-03)

### Tenant isolation smoke test

```bash
python -m pytest tests/test_query_handler.py -v -k "tenant"
```

A query with `tenant=A` must return zero results for chunks ingested under `tenant=B`.

### Embedder version check at query time

```bash
python -m pytest tests/test_query_handler.py -v -k "embedder"
```

A query using a deprecated embedder version must be rejected with a clear error.

### Hard filters

```bash
python -m pytest tests/test_query_handler.py -v -k "filter"
```

---

## 3. Validated Generation with Citations (RAG-04)

### Schema validation and citation check

```bash
python -m pytest tests/test_generation.py -v
```

Inject a question with known source chunks; assert the response includes `citations` referencing the correct `chunk_id` values and passes schema validation.

### Refusal on out-of-scope questions

```bash
python -c "
from mcp_agent_factory.knowledge.generation import generate
result = generate('What is the boiling point of tungsten?', chunks=[])
assert result['answer'].startswith('I cannot'), f'Expected refusal, got: {result[\"answer\"]}'
print('Refusal OK')
"
```

---

## 4. Embedder Versioning and Dual-Write Cutover (RAG-05)

### Version recorded in every embedding

```bash
python -m pytest tests/test_embedder.py -v -k "version"
```

### Dual-write mode: both old and new index get writes

```bash
python -m pytest tests/test_embedder.py -v -k "dual_write"
```

### Cutover: disable old version, verify queries use new

```bash
python -m pytest tests/test_embedder.py -v -k "cutover"
```

---

## 5. Evaluation Gates (RAG-06)

### Run the eval harness against the golden set

```bash
python -m evals.runner --dataset evals/datasets/rag_qa.jsonl --output evals/results/manual-run.json
```

Output must include `golden_set_version` in `meta` and separate `retrieval` / `generation` metric blocks.

### Simulate a quality regression

```bash
# Compare against baseline — should pass
python -m evals.compare evals/results/baseline.json evals/results/manual-run.json

# Degrade the baseline threshold to force a failure
python -m evals.compare evals/results/baseline.json evals/results/manual-run.json --threshold 0.01
echo "Exit code: $?"  # expect non-zero
```

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
    path = await store.backup('/tmp/rag-backup-drill.sql')
    print(f'Backup written to {path}')
    await store.restore(path)
    print('Restore complete')

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

## 7. Observability

### Grafana dashboards

1. Open Grafana at `http://localhost:3000` (default: admin/admin).
2. Navigate to **Dashboards → RAG Metrics**.
3. Verify panels: top-1 score distribution, score gap, empty-result rate, refusal rate.

### Alert simulation

```bash
# Trigger a burst of refusals by querying out-of-scope questions in a loop
for i in $(seq 1 20); do
  curl -s -X POST http://localhost:8000/query \
    -H 'Content-Type: application/json' \
    -d '{"question": "out-of-scope '"$i"'", "tenant": "test"}' > /dev/null
done
# Check Prometheus alert manager for RAG refusal spike alert firing
curl -s http://localhost:9090/api/v1/alerts | python -m json.tool | grep -A3 "refusal"
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
