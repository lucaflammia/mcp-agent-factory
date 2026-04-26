# Summary: LocalEmbedder

## What was built
`LocalEmbedder` — a semantic embedder backed by `sentence-transformers/all-MiniLM-L6-v2`.
Runs fully offline (no API key), 22 MB model, 384-dim float32 vectors with genuine cosine
similarity (`cosine("climate change", "prior climate analysis") ≈ 0.49` vs ~0 for unrelated text).

## Files changed
- `src/mcp_agent_factory/knowledge/embedder.py` — added `LocalEmbedder` class (lazy model load)
- `src/mcp_agent_factory/knowledge/__init__.py` — exported `LocalEmbedder`
- `src/mcp_agent_factory/gateway/app.py` — default `_embedder` switched to `LocalEmbedder`
- `pyproject.toml` — added `ml = ["sentence-transformers>=2.2"]` optional dep group
- `README.md` — updated knowledge layer example to use `LocalEmbedder`

## How to use
```python
from mcp_agent_factory.knowledge import LocalEmbedder
embedder = LocalEmbedder()  # model loaded on first .embed() call
vec = embedder.embed("climate change")  # shape (384,), float32
```

The gateway uses it automatically. For tests/CI, continue using `StubEmbedder` (no download).

## Verification
- 278 unit tests pass (`pytest -m "not integration"`)
- `cosine("climate change", "prior climate analysis") = 0.485`
- `cosine("climate change", "banana smoothie recipe") = -0.003`
