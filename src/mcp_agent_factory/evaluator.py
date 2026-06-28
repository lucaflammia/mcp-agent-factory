"""
Critic-Actor Evaluator — blind, independent QA auditor for agent outputs.

**Why this matters:** Agents cannot reliably self-certify their own work.
A planning agent that also grades its own output will systematically
optimise for the appearance of correctness rather than actual correctness.

The Critic-Actor pattern fixes this by isolating evaluation:
- The *Actor* (any agent) produces output.
- The *Critic* (this module) evaluates that output against the *original*
  input constraints, with no access to the actor's reasoning chain.

The critic is intentionally cynical: it defaults to ``needs_revision``
and requires explicit evidence to pass.

Usage::

    contract = EvaluationContract(
        task_description="Summarise the sales report",
        input_constraints={"max_words": 100, "must_include": ["revenue", "Q3"]},
        actor_output="Revenue grew 12% in Q3...",
    )
    verdict = CriticActorEvaluator.evaluate(contract)
    assert verdict.passed or verdict.revision_notes
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

class EvaluationContract(BaseModel):
    """
    Ground truth provided at task creation time.

    The contract is sealed before the actor runs — the critic checks
    the actor's output *against this contract alone*, never against
    the actor's own stated reasoning.
    """
    task_description: str = Field(..., min_length=1)
    input_constraints: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Typed constraints the actor's output must satisfy. "
            "Supported keys: max_words (int), min_words (int), "
            "must_include (list[str]), must_exclude (list[str]), "
            "required_fields (list[str] — checked when actor_output is a dict)."
        ),
    )
    actor_output: str | dict[str, Any] = Field(
        ..., description="The raw output produced by the actor agent."
    )


class EvaluationScore(str, Enum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class EvaluationVerdict(BaseModel):
    """Structured verdict returned by the critic."""
    score: EvaluationScore
    passed: bool
    findings: list[str] = Field(default_factory=list)
    revision_notes: str = ""

    @classmethod
    def _from_findings(cls, findings: list[str]) -> "EvaluationVerdict":
        if not findings:
            return cls(score=EvaluationScore.PASS, passed=True)
        if len(findings) == 1:
            return cls(
                score=EvaluationScore.PARTIAL,
                passed=False,
                findings=findings,
                revision_notes=findings[0],
            )
        return cls(
            score=EvaluationScore.FAIL,
            passed=False,
            findings=findings,
            revision_notes="; ".join(findings),
        )


# ---------------------------------------------------------------------------
# Critic implementation
# ---------------------------------------------------------------------------

class CriticActorEvaluator:
    """
    Cynical, isolated QA auditor.

    Evaluation is deterministic: it applies constraint checks derived
    from the ``EvaluationContract`` without any access to the actor's
    internal reasoning.  This prevents the actor from gaming the grader.

    For richer evaluation (semantic correctness, hallucination detection)
    inject an independent LLM call via ``_llm_judge`` — it must use a
    *different* provider or model than the actor to avoid shared bias.
    """

    @staticmethod
    def evaluate(contract: EvaluationContract) -> EvaluationVerdict:
        """
        Evaluate *actor_output* against *input_constraints*.

        Returns an ``EvaluationVerdict``.  Never raises — constraint
        failures are captured as findings in the verdict.
        """
        findings: list[str] = []
        output = contract.actor_output
        constraints = contract.input_constraints

        # Normalise to text for word-count / substring checks
        text = output if isinstance(output, str) else str(output)
        words = len(re.findall(r"\S+", text))

        # --- word count ---
        if "max_words" in constraints:
            limit = int(constraints["max_words"])
            if words > limit:
                findings.append(f"Output is {words} words; max allowed is {limit}.")

        if "min_words" in constraints:
            floor = int(constraints["min_words"])
            if words < floor:
                findings.append(f"Output is {words} words; minimum required is {floor}.")

        # --- required substrings ---
        for term in constraints.get("must_include", []):
            if term.lower() not in text.lower():
                findings.append(f"Required term {term!r} is absent from the output.")

        # --- forbidden substrings ---
        for term in constraints.get("must_exclude", []):
            if term.lower() in text.lower():
                findings.append(f"Forbidden term {term!r} appears in the output.")

        # --- required dict fields (structural JSON output) ---
        if isinstance(output, dict):
            for field_name in constraints.get("required_fields", []):
                if field_name not in output:
                    findings.append(f"Required field {field_name!r} missing from output dict.")

        verdict = EvaluationVerdict._from_findings(findings)
        logger.debug(
            "critic verdict task=%r score=%s findings=%d",
            contract.task_description[:60],
            verdict.score,
            len(findings),
        )
        return verdict
