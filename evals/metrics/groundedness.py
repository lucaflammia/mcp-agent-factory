"""Groundedness metric — is every claim in the answer supported by retrieved context?

Two evaluation modes:
1. Heuristic: keyword overlap between answer and context chunks.
2. LLM judge: asks a judge model to verify each claim (see evals/judge/).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GroundednessResult:
  """Result of a groundedness check on a single answer."""
  score: float
  supported_claims: int
  total_claims: int
  unsupported: list[str]

  def to_dict(self) -> dict:
    return {
      "score": round(self.score, 4),
      "supported_claims": self.supported_claims,
      "total_claims": self.total_claims,
      "unsupported": self.unsupported,
    }


def extract_claims(text: str) -> list[str]:
  """Split text into individual factual claims.

  Uses sentence splitting as a proxy — each sentence with a number,
  percentage, or proper noun is treated as a claim.
  """
  sentences = re.split(r'(?<=[.!?])\s+', text.strip())
  claims = []
  for s in sentences:
    s = s.strip()
    if not s:
      continue
    has_fact = bool(re.search(r'\d|%|\$|USD|EUR|Q[1-4]', s))
    if has_fact:
      claims.append(s)
    elif len(s.split()) >= 5:
      claims.append(s)
  return claims if claims else [text.strip()]


def check_groundedness(
  answer: str,
  context_chunks: list[str],
  threshold: float = 0.3,
) -> GroundednessResult:
  """Heuristic groundedness check via keyword overlap.

  For each claim in the answer, checks whether sufficient keywords
  appear in at least one context chunk. This is intentionally simple —
  the LLM judge in evals/judge/ provides the semantic check.

  Args:
    answer: The generated answer text.
    context_chunks: Retrieved context passages.
    threshold: Minimum keyword overlap ratio to consider a claim supported.
  """
  if not context_chunks:
    claims = extract_claims(answer)
    return GroundednessResult(
      score=0.0,
      supported_claims=0,
      total_claims=len(claims),
      unsupported=claims,
    )

  claims = extract_claims(answer)
  context_text = " ".join(context_chunks).lower()
  context_tokens = set(re.findall(r'\w+', context_text))

  supported = 0
  unsupported = []

  for claim in claims:
    claim_tokens = set(re.findall(r'\w+', claim.lower()))
    if not claim_tokens:
      supported += 1
      continue
    overlap = len(claim_tokens & context_tokens) / len(claim_tokens)
    if overlap >= threshold:
      supported += 1
    else:
      unsupported.append(claim)

  total = len(claims)
  score = supported / total if total > 0 else 0.0

  return GroundednessResult(
    score=score,
    supported_claims=supported,
    total_claims=total,
    unsupported=unsupported,
  )
