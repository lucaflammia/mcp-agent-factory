"""Tests for CriticActorEvaluator LLM judge extension."""
from __future__ import annotations

import pytest

from mcp_agent_factory.evaluator import (
	CriticActorEvaluator,
	EvaluationContract,
	EvaluationScore,
)


def test_deterministic_still_works():
	"""Existing deterministic evaluator is not broken."""
	contract = EvaluationContract(
		task_description="Summarise revenue",
		input_constraints={"must_include": ["revenue"], "max_words": 50},
		actor_output="Revenue grew 12% in Q3.",
	)
	verdict = CriticActorEvaluator.evaluate(contract)
	assert verdict.passed
	assert verdict.score == EvaluationScore.PASS


def test_deterministic_fail():
	contract = EvaluationContract(
		task_description="Summarise revenue",
		input_constraints={"must_include": ["revenue", "profit"]},
		actor_output="Sales increased.",
	)
	verdict = CriticActorEvaluator.evaluate(contract)
	assert not verdict.passed


@pytest.mark.integration
async def test_llm_judge_pass():
	"""Full two-pass evaluation with LLM judge. Requires GEMINI_API_KEY."""
	import os
	if not os.getenv("GEMINI_API_KEY") and not os.getenv("OLLAMA_BASE_URL"):
		pytest.skip("No LLM provider configured")

	contract = EvaluationContract(
		task_description="Summarise the quarterly revenue",
		input_constraints={"must_include": ["revenue"]},
		actor_output="Revenue grew 12% in Q3, driven by enterprise sales.",
	)
	verdict = await CriticActorEvaluator.evaluate_with_llm(contract)
	# The deterministic pass should propagate; LLM may add findings
	assert verdict.score in (EvaluationScore.PASS, EvaluationScore.PARTIAL)


@pytest.mark.integration
async def test_llm_judge_deterministic_fail_short_circuits():
	"""If deterministic checks FAIL, LLM judge is skipped."""
	import os
	if not os.getenv("GEMINI_API_KEY") and not os.getenv("OLLAMA_BASE_URL"):
		pytest.skip("No LLM provider configured")

	contract = EvaluationContract(
		task_description="List all products",
		input_constraints={"must_include": ["product_a", "product_b"], "max_words": 5},
		actor_output="Here is a very long response that exceeds the word limit and also doesn't mention the required products at all",
	)
	verdict = await CriticActorEvaluator.evaluate_with_llm(contract)
	assert verdict.score == EvaluationScore.FAIL
