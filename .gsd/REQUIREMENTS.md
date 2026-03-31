# Requirements

## Active

### R101 — Multi-tenant vector namespace isolation
- Class: compliance/security
- Status: active
- Description: Every vector upsert and search must include a mandatory `owner_id` filter derived from the JWT `sub` claim. Cross-tenant queries must return empty results.
- Why it matters: Without isolation, one user's indexed reports contaminate another's retrieval results — a hard security boundary.
- Source: user
- Primary owning slice: M005/S01
- Supporting slices: M005/S02, M005/S04
- Validation: unmapped
- Notes: Proven by two-user isolation test: upsert as user A, query as user B → empty result.

### R102 — Auto-ingestion of WriterAgent output
- Class: primary-user-loop
- Status: active
- Description: An Ingestion Worker subscribes to `agent.output.final` on the MessageBus. When a WriterAgent completes a report, the content is automatically chunked, embedded, and stored in the vector store.
- Why it matters: Creates persistent cross-session memory — future tasks can retrieve prior analysis without re-running the pipeline.
- Source: user
- Primary owning slice: M005/S02
- Supporting slices: M005/S01
- Validation: unmapped
- Notes: Worker must not block the bus — fire-and-forget async ingest.

### R103 — Knowledge-augmented utility scoring (+20% boost)
- Class: differentiator
- Status: active
- Description: Before auction, the Auctioneer performs a shallow probe of the vector store. Agents with the `knowledge_retrieval` capability receive a +20% utility score boost when relevant prior context is found.
- Why it matters: Incentivises specialised retrieval agents to win tasks they are genuinely better equipped to handle.
- Source: user
- Primary owning slice: M005/S03
- Supporting slices: M005/S01
- Validation: unmapped
- Notes: +20% means `raw_score * 1.2`, clamped to 1.0.

### R104 — `query_knowledge_base` MCP tool
- Class: core-capability
- Status: active
- Description: An MCP-compliant tool exposed on the gateway that accepts a natural-language query and returns ranked chunks from the vector store, scoped to the calling user's namespace.
- Why it matters: Makes the knowledge layer accessible to external MCP clients without bypassing auth.
- Source: user
- Primary owning slice: M005/S04
- Supporting slices: M005/S01
- Validation: unmapped
- Notes: Callable via `mcp_call` in dev mode; requires valid JWT in production.

### R105 — LibrarianAgent for cross-session synthesis
- Class: core-capability
- Status: active
- Description: A specialised agent type (`LibrarianAgent`) focused on high-recall retrieval and synthesising results across multiple stored reports.
- Why it matters: Separates retrieval logic from analytical/writing logic — maintains single-responsibility across agent types.
- Source: user
- Primary owning slice: M005/S04
- Supporting slices: M005/S01, M005/S02
- Validation: unmapped
- Notes: Follows the AnalystAgent/WriterAgent pattern established in M003.

### R106 — SSE `knowledge_retrieved` event
- Class: operability
- Status: active
- Description: The SSE v1 router emits a `knowledge_retrieved` event whenever a RAG query completes, carrying chunk count and a source label.
- Why it matters: Gives clients real-time visibility into retrieval activity without polling.
- Source: user
- Primary owning slice: M005/S04
- Supporting slices: none
- Validation: unmapped
- Notes: Source field is a label string — not a real URI (source tracking is out of scope).

### R107 — VectorStore / Embedder protocol abstraction
- Class: quality-attribute
- Status: active
- Description: The vector store and embedding function must be defined as protocols with an in-memory numpy implementation for tests and a swappable interface for production backends (Qdrant, ChromaDB, etc.).
- Why it matters: Keeps the milestone self-contained (no heavy deps required) and production-ready (real backends slot in without code changes).
- Source: inferred
- Primary owning slice: M005/S01
- Supporting slices: all M005 slices
- Validation: unmapped
- Notes: Stub embedder uses random projection or TF-IDF hash. Real sentence-transformers can be wired behind the Embedder protocol later.

## Validated

*(none yet for M005)*

## Deferred

*(none)*

## Out of Scope

### R108 — Source URI tracking on stored chunks
- Class: anti-feature
- Status: out-of-scope
- Description: Tracking real source URIs (e.g. `s3://...`) on vector chunks.
- Why it matters: Prevents scope creep into storage integration.
- Source: user (rejected)
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Source field in SSE events is a label string only.

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|----|-------|--------|---------------|------------|-------|
| R101 | compliance/security | active | M005/S01 | S02, S04 | unmapped |
| R102 | primary-user-loop | active | M005/S02 | S01 | unmapped |
| R103 | differentiator | active | M005/S03 | S01 | unmapped |
| R104 | core-capability | active | M005/S04 | S01 | unmapped |
| R105 | core-capability | active | M005/S04 | S01, S02 | unmapped |
| R106 | operability | active | M005/S04 | none | unmapped |
| R107 | quality-attribute | active | M005/S01 | all | unmapped |
| R108 | anti-feature | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 7
- Mapped to slices: 7
- Validated: 0
- Unmapped active requirements: 0
