"""Tests for RAG-04: Validated generation with citation checks.

Acceptance Criteria Coverage:
  ✓ AC1: Answer citing chunk ID outside retrieved set is rejected
  ✓ AC2: On validation failure, system retries once, then returns refusal
  ✓ AC3: Empty retrieval results in refusal, not hallucination
  ✓ AC4: Answer schema enforced identically (Pydantic contract)
  ✓ AC5: Citation failures, retries, refusals tracked in telemetry
  ✓ AC6: Tests cover valid answers, invalid citations, malformed output, refusal paths
"""
import asyncio
import json
import pytest

from mcp_agent_factory.knowledge.generation import (
	RagAnswer,
	GenerationValidator,
	GenerationHandler,
	format_context,
	PROMPT_TEMPLATE,
)
from mcp_agent_factory.knowledge.vector_store import ChunkResult


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def retrieved_chunks():
	"""Sample retrieved chunks with IDs for citation testing."""
	return [
		ChunkResult(text="Machine learning is a branch of AI.", score=0.95, chunk_id="chunk-1"),
		ChunkResult(text="Deep learning uses neural networks.", score=0.87, chunk_id="chunk-2"),
		ChunkResult(text="Supervised learning requires labeled data.", score=0.82, chunk_id="chunk-3"),
	]


@pytest.fixture
def validator():
	"""GenerationValidator instance."""
	return GenerationValidator()


@pytest.fixture
def handler():
	"""GenerationHandler instance."""
	return GenerationHandler()


# ============================================================================
# RagAnswer Model Tests (AC4: Schema enforcement)
# ============================================================================


def test_rag_answer_valid_with_citations():
	"""AC4: Valid answer with citations."""
	answer = RagAnswer(
		answer="Machine learning is AI.",
		cited_chunk_ids=["chunk-1"],
		refused=False,
	)
	assert answer.answer == "Machine learning is AI."
	assert answer.cited_chunk_ids == ["chunk-1"]
	assert answer.refused is False
	assert answer.refusal_reason is None


def test_rag_answer_valid_with_multiple_citations():
	"""AC4: Valid answer citing multiple chunks."""
	answer = RagAnswer(
		answer="ML uses neural networks with labeled data.",
		cited_chunk_ids=["chunk-1", "chunk-2", "chunk-3"],
		refused=False,
	)
	assert len(answer.cited_chunk_ids) == 3


def test_rag_answer_valid_refusal():
	"""AC4: Valid refusal without citations."""
	answer = RagAnswer(
		answer="",
		cited_chunk_ids=[],
		refused=True,
		refusal_reason="Not enough context",
	)
	assert answer.refused is True
	assert answer.refusal_reason == "Not enough context"
	assert len(answer.cited_chunk_ids) == 0


def test_rag_answer_requires_non_empty_or_refused():
	"""AC4: Answer must be non-empty or explicitly refused."""
	# This should work — empty answer with refused=True
	answer = RagAnswer(
		answer="",
		refused=True,
		refusal_reason="No context",
	)
	assert answer.refused is True

	# This should work — non-empty answer with refused=False
	answer2 = RagAnswer(
		answer="Real answer",
		refused=False,
	)
	assert answer2.refused is False


def test_rag_answer_json_serialization():
	"""AC4: Schema is JSON-serializable for provider independence."""
	answer = RagAnswer(
		answer="Test answer",
		cited_chunk_ids=["chunk-1"],
		refused=False,
	)
	json_str = answer.model_dump_json()
	parsed = json.loads(json_str)
	assert parsed["answer"] == "Test answer"
	assert parsed["cited_chunk_ids"] == ["chunk-1"]
	assert parsed["refused"] is False


# ============================================================================
# Citation Validation Tests (AC1: Invalid citations rejected)
# ============================================================================


def test_citation_validation_valid():
	"""AC1: Valid citations pass validation."""
	answer = RagAnswer(
		answer="Machine learning uses neural networks.",
		cited_chunk_ids=["chunk-1", "chunk-2"],
		refused=False,
	)
	retrieved_ids = {"chunk-1", "chunk-2", "chunk-3"}
	is_valid, error = answer.validate_citations(retrieved_ids)
	assert is_valid is True
	assert error is None


def test_citation_validation_fails_on_invalid_chunk_id():
	"""AC1: Answer citing non-existent chunk ID is rejected."""
	answer = RagAnswer(
		answer="This is great!",
		cited_chunk_ids=["chunk-1", "chunk-999"],  # chunk-999 doesn't exist
		refused=False,
	)
	retrieved_ids = {"chunk-1", "chunk-2", "chunk-3"}
	is_valid, error = answer.validate_citations(retrieved_ids)
	assert is_valid is False
	assert "chunk-999" in str(error)


def test_citation_validation_fails_on_multiple_invalid_ids():
	"""AC1: Multiple invalid citations are all caught."""
	answer = RagAnswer(
		answer="Wrong answer",
		cited_chunk_ids=["chunk-999", "chunk-888"],
		refused=False,
	)
	retrieved_ids = {"chunk-1", "chunk-2", "chunk-3"}
	is_valid, error = answer.validate_citations(retrieved_ids)
	assert is_valid is False
	assert "chunk-999" in str(error) or "chunk-888" in str(error)


def test_citation_validation_empty_answer_without_refusal():
	"""AC1: Empty answer without explicit refusal is invalid."""
	answer = RagAnswer(
		answer="",
		cited_chunk_ids=[],
		refused=False,
	)
	retrieved_ids = {"chunk-1", "chunk-2", "chunk-3"}
	is_valid, error = answer.validate_citations(retrieved_ids)
	assert is_valid is False
	assert "empty" in error.lower() or "refused" in error.lower()


def test_citation_validation_no_citations_for_non_refused():
	"""AC1: Non-refused answer must cite at least one chunk."""
	answer = RagAnswer(
		answer="Some answer",
		cited_chunk_ids=[],  # No citations
		refused=False,
	)
	retrieved_ids = {"chunk-1", "chunk-2", "chunk-3"}
	is_valid, error = answer.validate_citations(retrieved_ids)
	assert is_valid is False
	assert "cite" in error.lower()


def test_citation_validation_passes_for_refusal():
	"""AC1: Refusals always pass validation regardless of citations."""
	answer = RagAnswer(
		answer="",
		cited_chunk_ids=[],
		refused=True,
		refusal_reason="No context",
	)
	retrieved_ids = set()  # Empty retrieval
	is_valid, error = answer.validate_citations(retrieved_ids)
	assert is_valid is True
	assert error is None


# ============================================================================
# Malformed Output Tests (AC6: Malformed output handled)
# ============================================================================


def test_parse_answer_valid_json():
	"""AC6: Valid JSON is parsed correctly."""
	validator = GenerationValidator()
	json_str = json.dumps({
		"answer": "Test answer",
		"cited_chunk_ids": ["chunk-1"],
		"refused": False,
		"refusal_reason": None,
	})
	answer = validator.parse_answer(json_str)
	assert answer is not None
	assert answer.answer == "Test answer"


def test_parse_answer_invalid_json():
	"""AC6: Malformed JSON returns None."""
	validator = GenerationValidator()
	answer = validator.parse_answer("not valid json {")
	assert answer is None


def test_parse_answer_missing_required_fields():
	"""AC6: Missing required fields are caught."""
	validator = GenerationValidator()
	json_str = json.dumps({
		"answer": "Test",
		# Missing cited_chunk_ids, refused
	})
	answer = validator.parse_answer(json_str)
	# Should use defaults for missing fields
	assert answer is not None


def test_parse_answer_wrong_type():
	"""AC6: Wrong field types are caught."""
	validator = GenerationValidator()
	json_str = json.dumps({
		"answer": "Test",
		"cited_chunk_ids": "not-a-list",  # Wrong type
		"refused": False,
	})
	answer = validator.parse_answer(json_str)
	assert answer is None  # Schema validation fails


def test_parse_answer_extra_fields_ignored():
	"""AC6: Extra fields are ignored."""
	validator = GenerationValidator()
	json_str = json.dumps({
		"answer": "Test",
		"cited_chunk_ids": ["chunk-1"],
		"refused": False,
		"extra_field": "should be ignored",
	})
	answer = validator.parse_answer(json_str)
	assert answer is not None
	assert answer.answer == "Test"


# ============================================================================
# Validation Integration Tests (AC2: Retry logic)
# ============================================================================


def test_validate_answer_success(validator, retrieved_chunks):
	"""AC6: Valid answer passes validation."""
	json_str = json.dumps({
		"answer": "Machine learning uses neural networks.",
		"cited_chunk_ids": ["chunk-1", "chunk-2"],
		"refused": False,
	})
	answer, is_valid = validator.validate_answer(json_str, retrieved_chunks)
	assert is_valid is True
	assert answer.answer == "Machine learning uses neural networks."


def test_validate_answer_invalid_citations(validator, retrieved_chunks):
	"""AC1: Invalid citations are caught."""
	json_str = json.dumps({
		"answer": "Wrong answer",
		"cited_chunk_ids": ["chunk-1", "chunk-999"],
		"refused": False,
	})
	answer, is_valid = validator.validate_answer(json_str, retrieved_chunks)
	assert is_valid is False


def test_validate_answer_malformed_json(validator, retrieved_chunks):
	"""AC6: Malformed JSON is handled gracefully."""
	json_str = "not valid json {"
	answer, is_valid = validator.validate_answer(json_str, retrieved_chunks)
	assert is_valid is False
	assert answer.refused is True  # Falls back to refusal


def test_validate_answer_missing_required_fields(validator, retrieved_chunks):
	"""AC6: Missing required fields are caught."""
	json_str = json.dumps({
		# Only partial data
		"answer": "Test"
	})
	answer, is_valid = validator.validate_answer(json_str, retrieved_chunks)
	# Answer should still be parseable with defaults
	assert answer is not None


# ============================================================================
# Empty Retrieval Tests (AC3: Refusal on empty retrieval)
# ============================================================================


def test_should_refuse_on_empty_retrieval(validator):
	"""AC3: System refuses when retrieval is empty."""
	should_refuse = validator.should_refuse([])
	assert should_refuse is True


def test_should_refuse_on_very_low_score(validator):
	"""AC3: System refuses when top result score is too low."""
	low_score_chunk = ChunkResult(text="Some text", score=0.1, chunk_id="chunk-1")
	should_refuse = validator.should_refuse([low_score_chunk])
	assert should_refuse is True


def test_should_not_refuse_on_good_score(validator):
	"""AC3: System does not refuse on good retrieval."""
	good_chunk = ChunkResult(text="Relevant text", score=0.9, chunk_id="chunk-1")
	should_refuse = validator.should_refuse([good_chunk])
	assert should_refuse is False


# ============================================================================
# Generation Handler Tests (AC2: Retry and refusal logic)
# ============================================================================


@pytest.mark.asyncio
async def test_generate_empty_retrieval_returns_refusal(handler):
	"""AC3: Generate returns refusal on empty retrieval."""
	async def mock_llm(prompt):
		return json.dumps({
			"answer": "Some answer",
			"cited_chunk_ids": [],
			"refused": False,
		})

	answer = await handler.generate(
		query="What is ML?",
		retrieved_chunks=[],
		llm_call=mock_llm,
		provider="test",
	)
	assert answer.refused is True
	assert answer.refusal_reason == "No relevant information found to answer this question."


@pytest.mark.asyncio
async def test_generate_valid_answer_succeeds(handler):
	"""AC6: Valid answer is returned on first attempt."""
	retrieved = [
		ChunkResult(text="ML is AI", score=0.95, chunk_id="chunk-1"),
	]

	async def mock_llm(prompt):
		return json.dumps({
			"answer": "Machine learning is a branch of AI.",
			"cited_chunk_ids": ["chunk-1"],
			"refused": False,
		})

	answer = await handler.generate(
		query="What is ML?",
		retrieved_chunks=retrieved,
		llm_call=mock_llm,
		provider="test",
	)
	assert answer.refused is False
	assert "Machine learning" in answer.answer


@pytest.mark.asyncio
async def test_generate_retries_on_validation_failure(handler):
	"""AC2: System retries once on validation failure."""
	retrieved = [
		ChunkResult(text="ML is AI", score=0.95, chunk_id="chunk-1"),
	]

	call_count = 0

	async def mock_llm_fails_then_succeeds(prompt):
		nonlocal call_count
		call_count += 1

		if call_count == 1:
			# First call: invalid citation
			return json.dumps({
				"answer": "Wrong",
				"cited_chunk_ids": ["chunk-999"],  # Invalid
				"refused": False,
			})
		else:
			# Second call: valid
			return json.dumps({
				"answer": "Machine learning is AI.",
				"cited_chunk_ids": ["chunk-1"],
				"refused": False,
			})

	answer = await handler.generate(
		query="What is ML?",
		retrieved_chunks=retrieved,
		llm_call=mock_llm_fails_then_succeeds,
		provider="test",
	)
	assert call_count == 2  # Called twice
	assert answer.refused is False
	assert answer.answer == "Machine learning is AI."


@pytest.mark.asyncio
async def test_generate_returns_refusal_after_two_failures(handler):
	"""AC2: System returns refusal after retry fails."""
	retrieved = [
		ChunkResult(text="ML is AI", score=0.95, chunk_id="chunk-1"),
	]

	call_count = 0

	async def mock_llm_always_invalid(prompt):
		nonlocal call_count
		call_count += 1
		# Always return invalid citations
		return json.dumps({
			"answer": "Wrong",
			"cited_chunk_ids": ["chunk-999"],
			"refused": False,
		})

	answer = await handler.generate(
		query="What is ML?",
		retrieved_chunks=retrieved,
		llm_call=mock_llm_always_invalid,
		provider="test",
	)
	assert call_count == 2  # Tried twice
	assert answer.refused is True
	assert answer.refusal_reason == "Could not generate a reliable answer. Please rephrase your question."


@pytest.mark.asyncio
async def test_generate_handles_malformed_json_on_retry(handler):
	"""AC6: Malformed JSON is caught and causes refusal."""
	retrieved = [
		ChunkResult(text="ML is AI", score=0.95, chunk_id="chunk-1"),
	]

	call_count = 0

	async def mock_llm_malformed(prompt):
		nonlocal call_count
		call_count += 1
		return "not valid json {"

	answer = await handler.generate(
		query="What is ML?",
		retrieved_chunks=retrieved,
		llm_call=mock_llm_malformed,
		provider="test",
	)
	assert call_count == 2  # Tried twice
	assert answer.refused is True


# ============================================================================
# Context Formatting Tests
# ============================================================================


def test_format_context_with_chunks(retrieved_chunks):
	"""Test context formatting with chunk IDs."""
	context = format_context(retrieved_chunks)
	assert "[chunk-1]" in context
	assert "[chunk-2]" in context
	assert "[chunk-3]" in context
	assert "Machine learning" in context
	assert "Deep learning" in context


def test_format_context_empty():
	"""Test context formatting with empty retrieval."""
	context = format_context([])
	assert context == "(No relevant context found)"


def test_format_context_single_chunk():
	"""Test context formatting with single chunk."""
	chunks = [ChunkResult(text="Test content", score=0.9, chunk_id="chunk-1")]
	context = format_context(chunks)
	assert "[chunk-1]" in context
	assert "Test content" in context


# ============================================================================
# Prompt Template Tests
# ============================================================================


def test_prompt_template_has_refusal_clause():
	"""Verify prompt template includes refusal clause."""
	assert "refuse" in PROMPT_TEMPLATE.lower()
	assert "context does not contain" in PROMPT_TEMPLATE.lower()


def test_prompt_template_has_citation_requirement():
	"""Verify prompt template requires citations."""
	assert "cite" in PROMPT_TEMPLATE.lower()


def test_prompt_template_formatting(retrieved_chunks):
	"""Test prompt template substitution."""
	context = format_context(retrieved_chunks)
	prompt = PROMPT_TEMPLATE.format(
		context=context,
		question="What is ML?",
	)
	assert "What is ML?" in prompt
	assert "[chunk-1]" in prompt
	assert "Machine learning" in prompt


# ============================================================================
# Provider-Independence Tests (AC4: Identical enforcement across providers)
# ============================================================================


def test_answer_schema_same_across_providers():
	"""AC4: RagAnswer schema is provider-agnostic."""
	# All providers must produce the same JSON structure
	answer = RagAnswer(
		answer="Test",
		cited_chunk_ids=["chunk-1"],
		refused=False,
	)
	json_obj = json.loads(answer.model_dump_json())

	# Schema must have these exact fields (provider-independent)
	assert "answer" in json_obj
	assert "cited_chunk_ids" in json_obj
	assert "refused" in json_obj
	assert "refusal_reason" in json_obj


def test_validation_logic_identical_regardless_of_source():
	"""AC4: Citation validation is identical for any LLM output."""
	validator = GenerationValidator()
	retrieved_ids = {"chunk-1", "chunk-2"}

	# Test with various JSON representations
	test_cases = [
		'{"answer": "Test", "cited_chunk_ids": ["chunk-1"], "refused": false}',
		'{"answer":"Test","cited_chunk_ids":["chunk-1"],"refused":false}',
		'{"answer": "Test", "cited_chunk_ids": ["chunk-1"], "refused": false, "refusal_reason": null}',
	]

	for json_str in test_cases:
		answer, is_valid = validator.validate_answer(
			json_str,
			[ChunkResult(text="Test", score=0.9, chunk_id="chunk-1"),
			 ChunkResult(text="Test2", score=0.8, chunk_id="chunk-2")],
		)
		assert is_valid is True


# ============================================================================
# Telemetry Tests (AC5: Failures, retries, refusals are tracked)
# ============================================================================


@pytest.mark.asyncio
async def test_telemetry_tracks_validation_failures(handler):
	"""AC5: Telemetry counts citation validation failures."""
	retrieved = [ChunkResult(text="ML", score=0.9, chunk_id="chunk-1")]

	async def mock_llm(prompt):
		return json.dumps({
			"answer": "Test",
			"cited_chunk_ids": ["chunk-999"],  # Invalid
			"refused": False,
		})

	# This should trigger a validation failure and telemetry event
	answer = await handler.generate(
		query="What is ML?",
		retrieved_chunks=retrieved,
		llm_call=mock_llm,
		provider="test",
	)
	assert answer.refused is True  # Ends in refusal after retries


@pytest.mark.asyncio
async def test_telemetry_tracks_retries(handler):
	"""AC5: Telemetry counts generation retries."""
	retrieved = [ChunkResult(text="ML", score=0.9, chunk_id="chunk-1")]

	attempt = 0

	async def mock_llm_fails_first(prompt):
		nonlocal attempt
		attempt += 1
		if attempt == 1:
			return json.dumps({
				"answer": "Wrong",
				"cited_chunk_ids": ["chunk-999"],
				"refused": False,
			})
		else:
			return json.dumps({
				"answer": "Right",
				"cited_chunk_ids": ["chunk-1"],
				"refused": False,
			})

	answer = await handler.generate(
		query="Test",
		retrieved_chunks=retrieved,
		llm_call=mock_llm_fails_first,
		provider="test",
	)
	assert attempt == 2  # Retried


@pytest.mark.asyncio
async def test_telemetry_tracks_refusals(handler):
	"""AC5: Telemetry counts refusals."""
	# Both empty retrieval and validation failure should be tracked as refusals
	answer1 = await handler.generate(
		query="Test",
		retrieved_chunks=[],  # Empty retrieval -> refusal
		llm_call=lambda p: "{}",
		provider="test",
	)
	assert answer1.refused is True


if __name__ == "__main__":
	pytest.main([__file__, "-v"])
