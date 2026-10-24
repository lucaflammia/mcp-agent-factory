"""Retrieval quality metrics for RAG evaluation.

Measures how well the answer matches the expected answer using
exact match, fuzzy match, and keyword recall.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MatchResult:
  """Result of answer matching."""
  exact_match: bool
  fuzzy_score: float
  keyword_recall: float
  matched_keywords: list[str]
  missed_keywords: list[str]

  def to_dict(self) -> dict:
    return {
      "exact_match": self.exact_match,
      "fuzzy_score": round(self.fuzzy_score, 4),
      "keyword_recall": round(self.keyword_recall, 4),
      "matched_keywords": self.matched_keywords,
      "missed_keywords": self.missed_keywords,
    }


def normalize(text: str) -> str:
  """Normalize text for comparison: lowercase, collapse whitespace, strip punctuation."""
  text = text.lower().strip()
  text = re.sub(r'[^\w\s%.$,/-]', '', text)
  text = re.sub(r'\s+', ' ', text)
  return text


def extract_keywords(text: str) -> set[str]:
  """Extract meaningful keywords — numbers, percentages, currency values, and significant words."""
  tokens = set()
  for match in re.finditer(r'(?:USD\s*)?\$?\d[\d,]*\.?\d*[MBKmk]?%?', text):
    tokens.add(normalize(match.group()))
  for match in re.finditer(r'\d+\.?\d*%', text):
    tokens.add(match.group())
  words = re.findall(r'[A-Za-z]{3,}', text)
  stop = {'the', 'and', 'was', 'were', 'for', 'from', 'with', 'that', 'this',
      'has', 'have', 'had', 'are', 'but', 'not', 'also', 'its', 'than',
      'compared', 'which', 'while', 'about', 'over', 'each', 'due'}
  for w in words:
    wl = w.lower()
    if wl not in stop:
      tokens.add(wl)
  return tokens


def check_match(actual: str, expected: str) -> MatchResult:
  """Compare actual answer against expected answer.

  Returns exact match, fuzzy score (token overlap), and keyword recall.
  """
  norm_actual = normalize(actual)
  norm_expected = normalize(expected)

  exact = norm_actual == norm_expected

  actual_tokens = set(norm_actual.split())
  expected_tokens = set(norm_expected.split())
  if expected_tokens:
    overlap = len(actual_tokens & expected_tokens)
    fuzzy = overlap / max(len(expected_tokens), 1)
  else:
    fuzzy = 1.0 if not actual_tokens else 0.0

  expected_kw = extract_keywords(expected)
  actual_kw = extract_keywords(actual)
  matched = sorted(expected_kw & actual_kw)
  missed = sorted(expected_kw - actual_kw)
  kw_recall = len(matched) / max(len(expected_kw), 1)

  return MatchResult(
    exact_match=exact,
    fuzzy_score=min(fuzzy, 1.0),
    keyword_recall=kw_recall,
    matched_keywords=matched,
    missed_keywords=missed,
  )


def check_refusal(actual: str) -> bool:
  """Detect whether the system correctly refused to answer.

  Looks for refusal indicators in the response.
  """
  refusal_patterns = [
    r"(?:i\s+)?(?:cannot|can't|don't|do not)\s+(?:find|determine|answer|provide|confirm)",
    r"not\s+(?:available|mentioned|stated|provided|included|present)\s+in",
    r"(?:no|insufficient)\s+(?:information|data|evidence|details)",
    r"(?:the\s+)?(?:report|document|corpus|context)\s+does\s+not\s+(?:contain|mention|include|provide|state)",
    r"unable\s+to\s+(?:determine|answer|find|provide)",
    r"(?:beyond|outside)\s+(?:the\s+)?(?:scope|available\s+data|provided\s+context)",
    r"this\s+(?:information|data)\s+is\s+not",
  ]
  text = actual.lower()
  return any(re.search(p, text) for p in refusal_patterns)
