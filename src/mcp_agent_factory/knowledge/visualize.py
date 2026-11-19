"""UMAP projection endpoint helper for RAG-07 vector visualization.

Projects query + top-k retrieval results + background sample to 2D so Grafana
Infinity datasource can render a scatter plot of the vector space.

The background sample is capped at 50 chunks to keep latency < 2 s on a single
CPU core. UMAP random_state=42 ensures deterministic coordinates for the same
set of vectors.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class ProjectedPoint:
    x: float
    y: float
    label: str
    score: float | None
    kind: str = "background"  # "query" | "result" | "background"
    preview: str = ""


@dataclass
class VisualizeResult:
    query: ProjectedPoint
    results: list[ProjectedPoint]
    background: list[ProjectedPoint]

    def to_dict(self) -> dict[str, Any]:
        def _pt(p: ProjectedPoint) -> dict:
            return {"x": p.x, "y": p.y, "label": p.label, "score": p.score, "kind": p.kind, "preview": p.preview}

        return {
            "query": _pt(self.query),
            "results": [_pt(r) for r in self.results],
            "background": [_pt(b) for b in self.background],
        }

    def to_flat(self) -> dict[str, Any]:
        """Return {points: [...]} — a single flat array for Grafana Infinity table parsing."""
        def _pt(p: ProjectedPoint) -> dict:
            return {"x": p.x, "y": p.y, "label": p.label, "score": p.score, "kind": p.kind, "preview": p.preview}

        return {"points": [_pt(self.query)] + [_pt(r) for r in self.results] + [_pt(b) for b in self.background]}


def _try_import_umap():
    try:
        import umap  # noqa: PLC0415
        return umap.UMAP
    except ImportError:
        return None


def project(
    query_text: str,
    query_vector: list[float],
    top_k_results: list[Any],  # list[ChunkResult]
    background_chunks: list[Any],  # list[ChunkResult] — already sampled by caller
    result_vectors: list[list[float]] | None = None,  # pre-computed embeddings for top_k_results
    background_vectors: list[list[float]] | None = None,  # pre-computed embeddings for background_chunks
    random_state: int = 42,
) -> VisualizeResult:
    """Run UMAP on query + results + background, return 2D projections.

    Falls back to PCA (via numpy SVD) when umap-learn is not installed so the
    endpoint still works without the optional dependency.

    result_vectors and background_vectors are pre-computed embeddings. If not
    provided, .vector attribute is read from each chunk (legacy path).
    """
    UMAP = _try_import_umap()

    def _vec(chunk: Any, precomputed: list[float] | None) -> list[float]:
        if precomputed is not None:
            return precomputed
        return chunk.vector  # legacy: chunk carries its own vector

    rv = result_vectors or [None] * len(top_k_results)
    bv = background_vectors or [None] * len(background_chunks)
    all_vectors = (
        [query_vector]
        + [_vec(r, v) for r, v in zip(top_k_results, rv)]
        + [_vec(b, v) for b, v in zip(background_chunks, bv)]
    )
    matrix = np.array(all_vectors, dtype=np.float32)

    n = len(matrix)
    if UMAP is not None and n > 3:
        reducer = UMAP(n_components=2, random_state=random_state, n_neighbors=min(15, n - 1), min_dist=0.1)
        coords = reducer.fit_transform(matrix)
    else:
        # Fallback: 2-component PCA via SVD
        centered = matrix - matrix.mean(axis=0)
        _, _, Vt = np.linalg.svd(centered, full_matrices=False)
        coords = centered @ Vt[:2].T

    coords = coords.tolist()

    q_pt = ProjectedPoint(x=coords[0][0], y=coords[0][1], label="query", score=None, kind="query", preview=query_text[:120])

    result_pts = []
    for i, chunk in enumerate(top_k_results, start=1):
        result_pts.append(ProjectedPoint(
            x=coords[i][0],
            y=coords[i][1],
            label=f"doc:{chunk.chunk_id}",
            score=round(float(chunk.score), 4),
            kind="result",
            preview=chunk.text[:120] if hasattr(chunk, "text") else "",
        ))

    bg_offset = 1 + len(top_k_results)
    bg_pts = []
    for i, chunk in enumerate(background_chunks):
        bg_pts.append(ProjectedPoint(
            x=coords[bg_offset + i][0],
            y=coords[bg_offset + i][1],
            label=f"bg:{chunk.chunk_id}",
            score=None,
            kind="background",
            preview=chunk.text[:80] if hasattr(chunk, "text") else "",
        ))

    return VisualizeResult(query=q_pt, results=result_pts, background=bg_pts)
