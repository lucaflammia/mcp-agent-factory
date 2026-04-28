---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Implement ContextPruner in gateway/pruner.py

Build ContextPruner class with prune(query, chunks, embedder, threshold) method. Reads threshold from MCP_CONTEXT_THRESHOLD env var when not supplied explicitly (default 0.3). Computes cosine similarity between embedded query and each chunk embedding; drops chunks below threshold. Returns empty list safely when all chunks fall below threshold or input is empty.

## Inputs

- `src/mcp_agent_factory/knowledge/embedder.py — Embedder Protocol and StubEmbedder for type reference`
- `src/mcp_agent_factory/knowledge/vector_store.py — cosine similarity pattern already used in InMemoryVectorStore.search()`

## Expected Output

- `src/mcp_agent_factory/gateway/pruner.py — ContextPruner class with prune() method and env-var threshold`

## Verification

python -c "from mcp_agent_factory.gateway.pruner import ContextPruner; print('import ok')"

## Observability Impact

none — synchronous pure function, no runtime signals needed
