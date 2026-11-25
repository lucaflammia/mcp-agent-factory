# RAG-05: Embedder Versioning and Dual-Write Cutover

## Overview

Embeddings from different models are not comparable. If the embedder changes (model upgrade, provider switch) and the index mixes old and new vectors, retrieval quality degrades silently.

RAG-05 implements a disciplined versioning system that allows multiple embedder versions to coexist in the index without mixing at query time, with a documented procedure for upgrading embedders end-to-end.

## Design Principles

1. **Version isolation**: Every chunk stores `embedder_id` (model name + version) in metadata. Queries only search vectors from a single version.
2. **Dual-write procedure**: New embedders are deployed alongside existing ones; ingestion writes both versions in parallel.
3. **Content-hash deduplication**: Backfill skips unchanged content to avoid redundant re-embedding.
4. **Configuration-driven rollback**: Switching versions is a config change (query-time `embedder_id`), not a re-ingest.
5. **Validation gates**: Golden set comparison (RAG-06) validates parity before cutover.

## Schema

### Chunks Table Extensions (Migration 002)

```sql
ALTER TABLE chunks
    ADD COLUMN embedder_id TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN content_hash TEXT NOT NULL,
    ADD COLUMN version_added_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Unique constraint on (owner_id, embedder_id, content_hash) for deduplication
ALTER TABLE chunks
    ADD CONSTRAINT uq_chunks_owner_embedder_hash
    UNIQUE (owner_id, embedder_id, content_hash);

-- Indices for efficient version-specific queries
CREATE INDEX idx_chunks_owner_embedder_id
    ON chunks (owner_id, embedder_id);
```

### Chunk Metadata (RAG-02)

Every chunk carries:
```json
{
  "source_id": "doc-1",
  "tenant": "acme",
  "acl": ["user:alice"],
  "created_at": "2026-01-15T10:30:00Z",
  "updated_at": "2026-01-15T10:35:00Z",
  "embedder_id": "all-MiniLM-L6-v2@v1",
  "content_hash": "sha256(...)",
  "position": 0,
  "chunk_size": 400,
  "overlap": 50,
  "source_type": "default"
}
```

## Dual-Write Procedure

### Phase 1: Deploy New Embedder (Dual-Write)

1. **Update `IdempotentIngestionPipeline` configuration** to use new embedder:
   ```python
   new_embedder = LocalEmbedder("all-MiniLM-L6-v2")  # Upgraded model
   new_embedder_id = "all-MiniLM-L6-v2@v2"
   
   pipeline = IdempotentIngestionPipeline(
       store=store,
       embedder=current_embedder,
       embedder_id="all-MiniLM-L6-v2@v1",
   )
   ```

2. **Activate dual-write** to ingest both versions in parallel:
   ```python
   await pipeline.dual_write(
       adapter=source_adapter,
       new_embedder=new_embedder,
       new_embedder_id="all-MiniLM-L6-v2@v2",
   )
   ```

   - All documents are ingested with the current embedder (v1).
   - All documents are re-embedded with the new embedder (v2) and stored with `embedder_id="v2"`.
   - No chunks are skipped, even if they already exist; both versions are stored.

3. **Backfill old chunks** (optional, for efficiency):
   ```python
   await pipeline.backfill(
       owner_id="tenant-a",
       new_embedder=new_embedder,
       new_embedder_id="all-MiniLM-L6-v2@v2",
   )
   ```

   - Retrieves chunks with `embedder_id="v1"`.
   - Re-embeds with the new embedder.
   - Stores with `embedder_id="v2"`.
   - **Skips chunks where `content_hash` already exists** for the new version (deduplication).

### Phase 2: Validation (RAG-06)

1. **Run the golden set** against both versions:
   ```python
   # Query with v1
   context_v1 = {
       "tenant": "acme",
       "acl": ["user:alice"],
       "embedder_id": "all-MiniLM-L6-v2@v1",
   }
   results_v1 = handler.retrieve("query", context_v1)
   
   # Query with v2
   context_v2 = {
       "tenant": "acme",
       "acl": ["user:alice"],
       "embedder_id": "all-MiniLM-L6-v2@v2",
   }
   results_v2 = handler.retrieve("query", context_v2)
   ```

2. **Compare retrieval quality** (RAG-06 evaluation gates):
   - NDCG@5, MRR, recall — both versions must meet baseline or better.
   - If parity is achieved or improved, proceed to Phase 3.
   - If new version is worse, stay on v1; investigate and iterate.

### Phase 3: Cutover

1. **Switch queries to the new version** by updating `embedder_id` in query context:
   ```python
   # Before: all queries include "embedder_id": "all-MiniLM-L6-v2@v1"
   # After: all queries include "embedder_id": "all-MiniLM-L6-v2@v2"
   ```

   - This is a **configuration change only**; no re-ingest required.
   - Queries will now search vectors from the new embedder.

2. **Monitor retrieval metrics** for 48–72 hours:
   - NDCG, MRR, user feedback scores.
   - If degradation is detected, rollback (Phase 4).

### Phase 4: Cleanup (Optional Grace Period)

1. **Keep old version for 30–90 days** for quick rollback.
2. **Delete old version** after grace period:
   ```sql
   DELETE FROM chunks WHERE embedder_id = 'all-MiniLM-L6-v2@v1' AND version_added_at < now() - interval '90 days';
   ```

## Rollback Procedure

**A cutover can be rolled back by configuration only, without re-ingesting.**

1. **Revert the query context** to point to the old version:
   ```python
   # Change from:
   context = {
       "tenant": "acme",
       "acl": ["user:alice"],
       "embedder_id": "all-MiniLM-L6-v2@v2",  # New version
   }
   
   # To:
   context = {
       "tenant": "acme",
       "acl": ["user:alice"],
       "embedder_id": "all-MiniLM-L6-v2@v1",  # Old version
   }
   ```

2. **Queries immediately revert** to searching the old version's vectors.

3. **No data migration, re-embedding, or downtime required.**

## Quarterly Review Checklist

Evaluate whether a newer embedder is worth the cutover:

### Technical Evaluation
- [ ] **Semantic quality**: Does the new embedder produce more semantically meaningful vectors?
  - Run golden set on sample queries; compare NDCG@5, MRR.
  - Is semantic distance correlated with relevance?
- [ ] **Performance**: Is embedding latency acceptable for ingestion and query time?
  - Benchmark ingest throughput (docs/sec).
  - Benchmark query latency (p50, p99).
- [ ] **Model maturity**: Is the new model stable (no breaking API changes expected)?
  - Check model release notes and maintenance schedule.
- [ ] **Maintenance cost**: Is the new model smaller/simpler (easier to deploy, lower memory)?
  - Embedding dimension, model size (MB), inference hardware requirements.

### Operational Evaluation
- [ ] **Tenant impact**: How many chunks need backfill?
  - Estimate dual-write overhead (2x ingestion cost).
  - Estimate storage cost (temporary 2x, then back to 1x after cleanup).
- [ ] **Rollback risk**: Is the old version still in service and tested?
  - Confirm old vectors can be queried end-to-end.
  - Run smoke tests before deployment.
- [ ] **Monitoring**: Are retrieval metrics instrumented and alarmed?
  - NDCG, MRR, user feedback scores, latency percentiles.

### Business Evaluation
- [ ] **Cutover cost**: Is the engineering effort justified by retrieval quality gains?
  - Estimate time for dual-write, backfill, validation, monitoring.
  - Estimate storage cost delta (temporary 2x).
- [ ] **User impact**: Will end users notice a difference?
  - Run A/B test or collect feedback from power users.
- [ ] **Precedent**: Have we updated embedders before in this codebase?
  - Document lessons learned from previous cutovers.

## Implementation Status

### Completed (RAG-05)
- ✅ Schema extended with `embedder_id`, `content_hash`, `version_added_at` columns.
- ✅ `VectorStore` methods accept and enforce `embedder_id`:
  - `upsert()` stores `embedder_id`.
  - `search_with_filters()` filters by `embedder_id` and raises error on mismatch.
- ✅ Dual-write pipeline: `IdempotentIngestionPipeline.dual_write()`.
- ✅ Backfill pipeline: `IdempotentIngestionPipeline.backfill()` with content-hash deduplication.
- ✅ Query handler enforces `embedder_id` via auth context.
- ✅ Comprehensive tests covering coexistence, cutover, rollback, and deduplication.
- ✅ This documentation.

### Out of Scope (Future)
- [ ] Automated evaluation gates (handled by RAG-06).
- [ ] Automated cleanup scheduled jobs.
- [ ] Multi-tenant embedder upgrade coordination.
- [ ] Embedder performance profiling harness.

## Error Handling

### Embedder Version Mismatch

If a query requests an `embedder_id` that doesn't exist in the index:

```
ValueError: Embedder version mismatch: requested 'all-MiniLM-L6-v2@v2' but index has versions ['all-MiniLM-L6-v2@v1'].
The embedder_id may have changed; consider running backfill for the new version.
```

**Action**: Either:
1. Roll back query context to use an available version.
2. Run dual-write + backfill to populate the requested version.

## Examples

### Complete Cutover Flow

```python
import asyncio
from mcp_agent_factory.knowledge import (
    IdempotentIngestionPipeline,
    LocalEmbedder,
    GuardedQueryHandler,
    DefaultFilterResolver,
)

async def cutover_embedder():
    # Phase 1: Dual-write both versions
    current_embedder = LocalEmbedder("all-MiniLM-L6-v2")
    new_embedder = LocalEmbedder("all-mpnet-base-v2")  # New model
    
    pipeline = IdempotentIngestionPipeline(
        store=store,
        embedder=current_embedder,
        embedder_id="all-MiniLM-L6-v2@v1",
    )
    
    stats = await pipeline.dual_write(
        adapter=source_adapter,
        new_embedder=new_embedder,
        new_embedder_id="all-mpnet-base-v2@v1",
    )
    print(f"Dual-write completed: {stats}")
    
    # Phase 2: Run golden set comparison (RAG-06)
    # ... (implement golden set evaluation)
    
    # Phase 3: Switch to new version
    # Update query context: "embedder_id": "all-mpnet-base-v2@v1"
    
    # Phase 4: Monitor (48–72 hours)
    # ... (collect retrieval metrics)
    
    # Phase 5: Cleanup (after 90 days)
    # DELETE FROM chunks WHERE embedder_id = 'all-MiniLM-L6-v2@v1' ...
```

### Rollback Example

```python
# During monitoring, if retrieval quality drops:

# Revert to v1
context = {
    "tenant": "acme",
    "acl": ["user:alice"],
    "embedder_id": "all-MiniLM-L6-v2@v1",  # Back to v1
}

# Queries immediately use v1 vectors again
results = handler.retrieve("query", context)
```

## References

- **RAG-02**: Idempotent ingestion pipeline, chunk metadata schema, `content_hash`.
- **RAG-03**: Guarded retrieval, filter validation, mandatory `embedder_id` checks.
- **RAG-04**: Validated generation, citation tracking (uses chunk IDs from RAG-05 versioning).
- **RAG-06**: Evaluation gates, golden set, cutover validation.

## Related Issues

- #35 (RAG-03: Guarded Retrieval) — filters + embedder validation.
- #36 (RAG-04: Validated Generation) — uses embedder_id from this work.
- #33 (RAG-06: Evaluation Gates) — validates cutover with golden set.
