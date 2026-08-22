"""Structure-aware text chunking with overlap and per-chunk metadata."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
  text: str
  metadata: dict = field(default_factory=dict)


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
