---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T02: Instrument LibrarianAgent and VectorStore with child spans

Add OTel spans to LibrarianAgent.extract() (span: agent.librarian.extract) and VectorStore.search() (span: agent.vector_store.search) so the trace descends to the local data layer. These are leaf spans under agent.pdf_extract and agent.llm_route respectively. No token counts needed here — record document chunk counts and query vector dimension as span attributes instead.

## Inputs

- `T01 parent span context`
- `LibrarianAgent.extract() signature`
- `VectorStore.search() signature`

## Expected Output

- `LibrarianAgent.extract() emits agent.librarian.extract span with chunk_count attribute`
- `VectorStore.search() emits agent.vector_store.search span with result_count attribute`
- `Full trace chain visible in Jaeger`

## Verification

Jaeger trace shows agent.librarian.extract and agent.vector_store.search as leaf spans under mcp.agents/analyze.
