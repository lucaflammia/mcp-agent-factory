# Plan: LocalEmbedder

## Task 1 — Add `LocalEmbedder` to `embedder.py`
- **File:** `src/mcp_agent_factory/knowledge/embedder.py`
- Add `LocalEmbedder` class using `sentence_transformers.SentenceTransformer`
- Lazy-load model on first call (class-level cache)
- Default model: `"all-MiniLM-L6-v2"`
- Returns `np.ndarray` float32, shape `(384,)`
- **Verify:** `python -c "from mcp_agent_factory.knowledge.embedder import LocalEmbedder; e=LocalEmbedder(); print(e.embed('hello').shape)"`

## Task 2 — Export and wire into app
- **Files:** `knowledge/__init__.py`, `gateway/app.py`
- Add `LocalEmbedder` to `__all__` in `__init__.py`
- Change `app.py` default `_embedder` from `StubEmbedder()` to `LocalEmbedder()`
- **Verify:** imports work, `_embedder` type is `LocalEmbedder`

## Task 3 — Add optional dep + update README
- **Files:** `pyproject.toml`, `README.md`
- Add `ml = ["sentence-transformers>=2.2"]` to `[project.optional-dependencies]`
- Update README note: replace "Use a real embedding model" sentence with pointer to `LocalEmbedder`
- **Verify:** `pip install -e ".[ml]"` passes (already installed, so just confirms spec)

## Task 4 — Run full test suite
- `python -m pytest tests/ -x -q` must be green
