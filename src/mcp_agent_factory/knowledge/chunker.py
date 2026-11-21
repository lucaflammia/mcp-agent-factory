"""Structure-aware text chunking with overlap and per-chunk metadata.

RAG-02 additions:
- ChunkerConfig — per-source-type hyperparameters
- CHUNKER_CONFIGS — registry keyed by source_type string
- chunk_document() — chunks a SourceDocument and attaches the full RAG-02
  metadata schema (source_id, tenant, acl, embedder_id, content_hash,
  created_at, updated_at) to every Chunk
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_agent_factory.knowledge.source import SourceDocument


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ChunkerConfig:
    chunk_size: int = 400
    overlap: int = 50
    source_type: str = "default"


CHUNKER_CONFIGS: dict[str, ChunkerConfig] = {
    "default": ChunkerConfig(chunk_size=400, overlap=50, source_type="default"),
    "pdf": ChunkerConfig(chunk_size=600, overlap=80, source_type="pdf"),
    "markdown": ChunkerConfig(chunk_size=500, overlap=60, source_type="markdown"),
    "code": ChunkerConfig(chunk_size=300, overlap=30, source_type="code"),
    "transcript": ChunkerConfig(chunk_size=350, overlap=50, source_type="transcript"),
}


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Low-level splitter (backward-compatible)
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    source: str = "",
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[Chunk]:
    """Split text into overlapping chunks, respecting paragraph and sentence boundaries.

    Strategy:
    1. Split on double-newline paragraph boundaries first.
    2. If a paragraph exceeds chunk_size, split further on sentence boundaries.
    3. Apply overlap by carrying the tail of the previous chunk into the next.

    chunk_size and overlap are hyperparameters recorded in chunk metadata so the
    eval report can treat them as such.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    sentences: list[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            sentences.append(para)
        else:
            parts = re.split(r"(?<=[.!?])\s+", para)
            sentences.extend(p.strip() for p in parts if p.strip())

    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0
    position = 0

    for sent in sentences:
        sent_len = len(sent)
        if current_len + sent_len > chunk_size and current:
            chunk_text_str = " ".join(current)
            chunks.append(Chunk(
                text=chunk_text_str,
                metadata={
                    "source": source,
                    "position": position,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                },
            ))
            position += 1
            overlap_sents: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len + len(s) > overlap:
                    break
                overlap_sents.insert(0, s)
                overlap_len += len(s)
            current = overlap_sents
            current_len = overlap_len

        current.append(sent)
        current_len += sent_len

    if current:
        chunks.append(Chunk(
            text=" ".join(current),
            metadata={"source": source, "position": position, "chunk_size": chunk_size, "overlap": overlap},
        ))

    return chunks if chunks else [Chunk(text=text, metadata={"source": source, "position": 0, "chunk_size": chunk_size, "overlap": overlap})]


# ---------------------------------------------------------------------------
# Document chunker (RAG-02 — full metadata schema)
# ---------------------------------------------------------------------------

REQUIRED_METADATA_FIELDS = frozenset({
    "source_id",
    "tenant",
    "acl",
    "created_at",
    "updated_at",
    "embedder_id",
    "content_hash",
})


def chunk_document(
    doc: "SourceDocument",
    embedder_id: str,
    config: ChunkerConfig | None = None,
) -> list[Chunk]:
    """Chunk a SourceDocument and attach the full RAG-02 metadata schema.

    Every Chunk carries:
      source_id, tenant, acl, created_at, updated_at, embedder_id, content_hash
    plus chunker hyperparameters (position, chunk_size, overlap, source_type).
    """
    if config is None:
        source_type = doc.extra.get("source_type", "default")
        config = CHUNKER_CONFIGS.get(source_type, CHUNKER_CONFIGS["default"])

    raw_chunks = chunk_text(
        doc.text,
        source=doc.source_id,
        chunk_size=config.chunk_size,
        overlap=config.overlap,
    )

    now = datetime.now(timezone.utc).isoformat()

    result: list[Chunk] = []
    for chunk in raw_chunks:
        content_hash = hashlib.sha256(chunk.text.encode()).hexdigest()
        metadata = {
            # RAG-02 mandatory fields
            "source_id": doc.source_id,
            "tenant": doc.tenant,
            "acl": doc.acl,
            "created_at": doc.modified_at.isoformat(),
            "updated_at": now,
            "embedder_id": embedder_id,
            "content_hash": content_hash,
            # Chunker hyperparameters (kept for eval traceability)
            "position": chunk.metadata["position"],
            "chunk_size": config.chunk_size,
            "overlap": config.overlap,
            "source_type": config.source_type,
        }
        result.append(Chunk(text=chunk.text, metadata=metadata))
    return result


def validate_chunk_metadata(metadata: dict) -> None:
    """Raise ValueError if any required RAG-02 metadata field is missing."""
    missing = REQUIRED_METADATA_FIELDS - metadata.keys()
    if missing:
        raise ValueError(f"Chunk metadata missing required fields: {sorted(missing)}")
