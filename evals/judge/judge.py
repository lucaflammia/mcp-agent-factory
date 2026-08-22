"""LLM-as-judge for groundedness and answer quality.

Uses a judge model distinct from the generator to evaluate answers.
See KNOWN_BIASES.md for documented limitations and mitigations.
"""
from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "google-gla:gemini-2.5-flash")


@dataclass(frozen=True)
class JudgeVerdict:
  """Structured verdict from the LLM judge."""
  score: float
  grounded: bool
  explanation: str
  claims_checked: int
  claims_supported: int

  def to_dict(self) -> dict:
    return {
      "score": round(self.score, 4),
      "grounded": self.grounded,
      "explanation": self.explanation,
      "claims_checked": self.claims_checked,
      "claims_supported": self.claims_supported,
    }


async def judge_answer(
  question: str,
  answer: str,
  context_chunks: list[str],
  expected: str | None = None,
  model: str | None = None,
) -> JudgeVerdict:
  """Evaluate an answer using an LLM judge.

  Mitigations applied (see KNOWN_BIASES.md):
  - Option order randomized to counter position bias
  - Judge model is distinct from the generator by default
  - Prompt asks for claim-by-claim verification, not holistic impression

  Args:
    question: The original question.
    answer: The generated answer to evaluate.
    context_chunks: Retrieved context passages.
    expected: Optional expected answer for comparison.
    model: Override judge model (defaults to EVAL_JUDGE_MODEL env var).
  """
  judge_model = model or JUDGE_MODEL

  context_text = "\n---\n".join(context_chunks) if context_chunks else "(no context provided)"

  options = ["SUPPORTED", "NOT SUPPORTED"]
  random.shuffle(options)
  options_str = " / ".join(options)

  prompt = f"""You are an independent evaluation judge. Your task is to verify whether
the answer is grounded in the provided context.

CONTEXT:
{context_text}

QUESTION: {question}

ANSWER TO EVALUATE: {answer}

{f"REFERENCE ANSWER: {expected}" if expected else ""}

Instructions:
1. Break the answer into individual factual claims.
2. For each claim, determine if it is {options_str} by the context.
3. A claim is SUPPORTED only if the context explicitly states or directly implies it.
4. Do NOT use your own knowledge — only the provided context.

Respond in this exact JSON format:
{{
 "claims": [
  {{"claim": "...", "verdict": "SUPPORTED" or "NOT SUPPORTED", "evidence": "..."}}
 ],
 "overall_grounded": true/false,
 "explanation": "one sentence summary"
}}"""

  try:
    from pydantic_ai import Agent
    from pydantic import BaseModel, Field

    class ClaimCheck(BaseModel):
      claim: str
      verdict: str
      evidence: str = ""

    class JudgeOutput(BaseModel):
      claims: list[ClaimCheck] = Field(default_factory=list)
      overall_grounded: bool = False
      explanation: str = ""

    agent: Agent[None, JudgeOutput] = Agent(
      judge_model,
      system_prompt="You are a factual verification judge. Respond only in the requested JSON format.",
      result_type=JudgeOutput,
      retries=1,
    )

    result = await agent.run(prompt)
    data = result.data

    total = len(data.claims)
    supported = sum(1 for c in data.claims if c.verdict.upper() == "SUPPORTED")
    score = supported / total if total > 0 else 0.0

    return JudgeVerdict(
      score=score,
      grounded=data.overall_grounded,
      explanation=data.explanation,
      claims_checked=total,
      claims_supported=supported,
    )

  except Exception as exc:
    logger.warning("LLM judge failed: %s — returning zero score", exc)
    return JudgeVerdict(
      score=0.0,
      grounded=False,
      explanation=f"Judge error: {exc}",
      claims_checked=0,
      claims_supported=0,
    )


def compute_judge_human_agreement(
  judge_verdicts: list[bool],
  human_labels: list[bool],
) -> dict[str, Any]:
  """Compute agreement between judge verdicts and human labels.

  Returns accuracy, Cohen's kappa, and a confusion matrix.
  Used on the 20-example calibration subset.
  """
  n = len(judge_verdicts)
  if n == 0:
    return {"accuracy": 0.0, "cohens_kappa": 0.0, "n": 0}

  agree = sum(1 for j, h in zip(judge_verdicts, human_labels) if j == h)
  accuracy = agree / n

  # Cohen's kappa
  p_yes_judge = sum(judge_verdicts) / n
  p_yes_human = sum(human_labels) / n
  p_e = p_yes_judge * p_yes_human + (1 - p_yes_judge) * (1 - p_yes_human)
  p_o = accuracy

  kappa = (p_o - p_e) / (1 - p_e) if p_e < 1.0 else 1.0

  # Confusion matrix
  tp = sum(1 for j, h in zip(judge_verdicts, human_labels) if j and h)
  fp = sum(1 for j, h in zip(judge_verdicts, human_labels) if j and not h)
  fn = sum(1 for j, h in zip(judge_verdicts, human_labels) if not j and h)
  tn = sum(1 for j, h in zip(judge_verdicts, human_labels) if not j and not h)

  return {
    "accuracy": round(accuracy, 4),
    "cohens_kappa": round(kappa, 4),
    "n": n,
    "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
  }
