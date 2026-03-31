# S01: Vector Store + Multi-Tenant Middleware — UAT

**Milestone:** M005
**Written:** 2026-03-31T07:17:35.524Z

# S01: Vector Store + Multi-Tenant Middleware — UAT

**Milestone:** M005
**Written:** 2026-03-31

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: The slice delivers a pure-Python library with no runtime server component. All correctness and isolation properties are fully expressed by the pytest suite.

## Preconditions

- Working directory: repo root
- Python environment active with numpy installed
- `PYTHONPATH=src` set (or run via `pytest` with pyproject.toml config)

## Smoke Test

```
PYTHONPATH=src python -c "
from mcp_agent_factory.knowledge import StubEmbedder, InMemoryVectorStore
e = StubEmbedder()
s = InMemoryVectorStore()
v = e.embed('hello')
s.upsert('u1', 'hello', v)
r = s.search('u1', v, 1)
assert len(r) == 1 and r[0][0] == 'hello'
print('OK')
"
```

Expected: prints `OK`, exit 0.

## Test Cases

### 1. Upsert and query returns result

1. Create `StubEmbedder` and `InMemoryVectorStore`.
2. Embed text `'hello'`, upsert as `owner_id='u1'`.
3. Search with the same vector, `top_k=1`.
4. **Expected:** list of length 1, first element text is `'hello'`.

### 2. Cosine ranking correct

1. Embed text `'apple'` → store as `owner_id='user'` with text `'apple'`.
2. Embed text `'orange'` → store as `owner_id='user'` with text `'orange'`.
3. Search with vector for `'apple'`, `top_k=2`.
4. **Expected:** first result text is `'apple'` (cosine similarity = 1.0 for identical vector).

### 3. Cross-tenant isolation

1. Embed `'secret'`, upsert as `owner_id='alice'`.
2. Search with the same vector as `owner_id='bob'`, `top_k=5`.
3. **Expected:** empty list `[]` — no cross-namespace leakage.

### 4. Empty store returns empty

1. Create a fresh `InMemoryVectorStore`.
2. Search any vector as any `owner_id`.
3. **Expected:** `[]`.

### 5. top_k respected

1. Upsert 5 distinct chunks as `owner_id='user'`.
2. Search with `top_k=2`.
3. **Expected:** exactly 2 results returned.

### 6. StubEmbedder determinism

1. Call `embed('foo')` twice on the same `StubEmbedder` instance.
2. **Expected:** `np.array_equal(v1, v2)` is True — same input always produces same vector.

## Edge Cases

### Zero-vector guard

1. Embed any text with `StubEmbedder`.
2. Verify `np.linalg.norm(vector) > 0`.
3. **Expected:** norm is non-zero (epsilon offset prevents division-by-zero in cosine similarity).

## Failure Signals

- `ImportError` from `mcp_agent_factory.knowledge` → knowledge package not on PYTHONPATH or `__init__.py` missing.
- Cosine ranking test fails → numpy not installed or vector math broken.
- Cross-tenant test fails with non-empty result → owner_id scoping broken in InMemoryVectorStore.

## Not Proven By This UAT

- Persistence across process restarts (InMemoryVectorStore is ephemeral by design).
- Semantic quality of StubEmbedder vectors (hash projection, not sentence-transformers).
- Thread safety under concurrent upsert/search (single-threaded only).
- Integration with JWT sub claim extraction (done in S02/S04).

## Notes for Tester

Run the full suite to confirm no regressions: `PYTHONPATH=src pytest tests/ -v` (expects 189 passed).

