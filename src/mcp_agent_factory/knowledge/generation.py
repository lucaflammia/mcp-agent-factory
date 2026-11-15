"""Validated generation with structured output and citation checking.

RAG-04: Validated generation applies the same Pydantic discipline used in
the orchestration layer to LLM generation. Every answer is:
  1. Generated under a strict JSON schema (RagAnswer)
  2. Validated for citation correctness (cited IDs ⊆ retrieved IDs)
  3. Retried once on validation failure
  4. Refused if validation fails after retry
  5. Tracked with OTel spans and telemetry counters

This module is provider-independent — the same validation logic applies to
Anthropic, OpenAI, Ollama, Bedrock, and any other LLM behind the unified router.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from mcp_agent_factory.gateway.telemetry import get_tracer

logger = logging.getLogger(__name__)

try:
	from prometheus_client import REGISTRY, Counter

	def _get_or_create_counter(name, doc, labelnames):
		if name in REGISTRY._names_to_collectors:
			return REGISTRY._names_to_collectors[name]
		return Counter(name, doc, labelnames)

	_citation_validation_failures = _get_or_create_counter(
		"rag_citation_validation_failures_total",
		"Total citation validation failures (invalid or missing citations)",
		["reason"],
	)
	_generation_retries = _get_or_create_counter(
		"rag_generation_retries_total",
		"Total generation retries due to validation failure",
		["provider"],
	)
	_generation_refusals = _get_or_create_counter(
		"rag_generation_refusals_total",
		"Total refusals returned after validation failure or empty retrieval",
		["reason"],
	)
except ImportError:
	class _NoOp:
		def labels(self, **kw):
			return self

		def inc(self, v=1):
			pass

	_citation_validation_failures = _NoOp()
	_generation_retries = _NoOp()
	_generation_refusals = _NoOp()


class RagAnswer(BaseModel):
	"""Structured answer with mandatory citations and refusal semantics.

	RAG-04: Every answer is validated for:
	  - Non-empty or explicit refusal
	  - Citation correctness (cited IDs exist in retrieved set)
	  - Explicit refusal path when retrieval is empty
	"""

	answer: str = Field(default="", description="The answer text or empty if refused")
	cited_chunk_ids: list[str] = Field(default_factory=list, description="Chunk IDs cited in the answer")
	refused: bool = Field(default=False, description="True if the system is refusing to answer")
	refusal_reason: str | None = Field(default=None, description="Reason for refusal if refused=True")

	def validate_citations(self, retrieved_chunk_ids: set[str]) -> tuple[bool, str | None]:
		"""Validate that all cited chunk IDs exist in the retrieved set.

		Args:
			retrieved_chunk_ids: set of chunk IDs that were retrieved

		Returns:
			(is_valid, error_message) — error_message is None if valid
		"""
		if self.refused:
			# Refusals don't need citations
			return True, None

		if not self.answer or not self.answer.strip():
			# Empty answer without explicit refusal is invalid
			return False, "Answer is empty but refused=False"

		cited_set = set(self.cited_chunk_ids)
		if not cited_set:
			# Non-refused answer must cite at least one chunk
			return False, "Non-refused answer must cite at least one chunk"

		invalid_citations = cited_set - retrieved_chunk_ids
		if invalid_citations:
			return False, f"Cited chunk IDs not in retrieved set: {invalid_citations}"

		return True, None


PROMPT_TEMPLATE = """You are a helpful assistant answering questions based on retrieved context.

## Context

{context}

## Instructions

1. Answer the question using ONLY the context provided above.
2. If the context does not contain enough information to answer the question, refuse to answer.
3. Always cite which chunks you used by their IDs (e.g., [chunk-1], [chunk-2]).
4. Be concise and accurate.

## Question

{question}

## Response

Respond with a JSON object in this exact format:
{{
	"answer": "Your answer here or empty if refusing",
	"cited_chunk_ids": ["chunk-id-1", "chunk-id-2"],
	"refused": false,
	"refusal_reason": null
}}

Or if refusing:
{{
	"answer": "",
	"cited_chunk_ids": [],
	"refused": true,
	"refusal_reason": "Reason why you cannot answer based on the context"
}}
"""


def format_context(retrieved_chunks: list[Any]) -> str:
	"""Format retrieved chunks into a prompt context section.

	Args:
		retrieved_chunks: List of ChunkResult or objects with text and chunk_id

	Returns:
		Formatted context string with chunk ID tags
	"""
	if not retrieved_chunks:
		return "(No relevant context found)"

	lines = []
	for i, chunk in enumerate(retrieved_chunks, 1):
		# Handle both ChunkResult objects and tuples
		if hasattr(chunk, "chunk_id"):
			chunk_id = chunk.chunk_id
			text = chunk.text
		else:
			# Fallback for backward compat
			chunk_id = f"chunk-{i}"
			text = chunk[0] if isinstance(chunk, (tuple, list)) else str(chunk)

		lines.append(f"[{chunk_id}]\n{text}")

	return "\n\n".join(lines)


class GenerationValidator:
	"""Validates and sanitizes LLM-generated answers with citation checking.

	Usage::

		validator = GenerationValidator()
		retrieved = [ChunkResult(text="...", score=0.9, chunk_id="chunk-1"), ...]
		answer = validator.validate_answer(raw_llm_output, retrieved)
	"""

	def __init__(self) -> None:
		self._tracer = get_tracer("mcp_gateway.generation")

	def parse_answer(self, raw_output: str) -> RagAnswer | None:
		"""Parse LLM output as JSON RagAnswer.

		Returns None if output is not valid JSON or doesn't match schema.
		"""
		try:
			data = json.loads(raw_output)
			return RagAnswer(**data)
		except (json.JSONDecodeError, ValueError) as e:
			logger.debug(f"Failed to parse answer JSON: {e}")
			return None

	def validate_answer(
		self,
		raw_output: str,
		retrieved_chunks: list[Any],
	) -> tuple[RagAnswer, bool]:
		"""Validate an answer against retrieved chunks.

		Args:
			raw_output: Raw LLM output (should be JSON)
			retrieved_chunks: List of ChunkResult objects with text, score, chunk_id

		Returns:
			(answer, is_valid) — is_valid=True if answer passes validation
		"""
		with self._tracer.start_as_current_span("generation.validate_answer") as span:
			span.set_attribute("output_length", len(raw_output))
			span.set_attribute("retrieved_count", len(retrieved_chunks))

			# Parse answer
			answer = self.parse_answer(raw_output)
			if answer is None:
				span.set_attribute("parse_error", True)
				_citation_validation_failures.labels(reason="malformed_json").inc()
				logger.warning(f"Malformed JSON from LLM: {raw_output[:200]}")
				return (
					RagAnswer(
						answer="",
						refused=True,
						refusal_reason="System error: malformed response",
					),
					False,
				)

			# Extract retrieved chunk IDs
			retrieved_ids = set()
			for chunk in retrieved_chunks:
				if hasattr(chunk, "chunk_id"):
					retrieved_ids.add(chunk.chunk_id)
				else:
					# Backward compat: use index-based IDs
					retrieved_ids.add(f"chunk-{retrieved_chunks.index(chunk)}")

			span.set_attribute("retrieved_ids_count", len(retrieved_ids))

			# Validate citations
			is_valid, error_msg = answer.validate_citations(retrieved_ids)
			span.set_attribute("is_valid", is_valid)

			if is_valid:
				span.set_attribute("cited_count", len(answer.cited_chunk_ids))
				return answer, True

			# Invalid citations — log and fail
			span.set_attribute("validation_error", error_msg)
			_citation_validation_failures.labels(reason="invalid_citations").inc()
			logger.warning(f"Citation validation failed: {error_msg}, answer: {answer.answer[:100]}")

			return answer, False

	def should_refuse(self, retrieved_chunks: list[Any]) -> bool:
		"""Check if retrieval is empty or insufficient.

		Returns True if the system should refuse to generate.
		"""
		if not retrieved_chunks:
			return True

		# Check if top result has very low score (e.g., < 0.3)
		top_chunk = retrieved_chunks[0]
		if hasattr(top_chunk, "score"):
			if top_chunk.score < 0.3:
				return True

		return False


class GenerationHandler:
	"""Wraps LLM calls with structured output enforcement and citation validation.

	Coordinates with the unified router to:
	1. Assemble prompts with context and chunk IDs
	2. Call LLM under structured output schema
	3. Validate citations
	4. Retry once on validation failure
	5. Return refusal on failure or empty retrieval

	Usage::

		handler = GenerationHandler()
		answer = await handler.generate(
			query="What is machine learning?",
			retrieved_chunks=[...],
			llm_provider=anthropic_client,
		)
	"""

	def __init__(self) -> None:
		self._validator = GenerationValidator()
		self._tracer = get_tracer("mcp_gateway.generation")

	async def generate(
		self,
		query: str,
		retrieved_chunks: list[Any],
		llm_call: callable,
		provider: str = "unknown",
	) -> RagAnswer:
		"""Generate an answer with structured validation and retry logic.

		Args:
			query: The user's question
			retrieved_chunks: List of ChunkResult objects from retrieval
			llm_call: Async callable that takes a prompt and returns raw LLM output
			provider: Provider name for telemetry (anthropic, openai, etc.)

		Returns:
			RagAnswer with validation guarantees
		"""
		with self._tracer.start_as_current_span("generation.generate") as span:
			span.set_attribute("query_length", len(query))
			span.set_attribute("retrieved_count", len(retrieved_chunks))
			span.set_attribute("provider", provider)

			# Check if retrieval is empty or poor
			if self._validator.should_refuse(retrieved_chunks):
				_generation_refusals.labels(reason="empty_retrieval").inc()
				logger.info("Refusing generation: retrieval returned no relevant chunks")
				span.set_attribute("refused_reason", "empty_retrieval")
				return RagAnswer(
					answer="",
					refused=True,
					refusal_reason="No relevant information found to answer this question.",
				)

			# Format context with chunk IDs
			context = format_context(retrieved_chunks)

			# Assemble prompt
			prompt = PROMPT_TEMPLATE.format(
				context=context,
				question=query,
			)

			# First attempt
			span.set_attribute("attempt", 1)
			raw_output = await llm_call(prompt)
			answer, is_valid = self._validator.validate_answer(raw_output, retrieved_chunks)

			if is_valid:
				span.set_attribute("success", True)
				return answer

			# Retry once
			span.set_attribute("attempt", 2)
			_generation_retries.labels(provider=provider).inc()
			logger.info(f"Retrying generation after validation failure: {answer}")

			raw_output_2 = await llm_call(prompt)
			answer_2, is_valid_2 = self._validator.validate_answer(raw_output_2, retrieved_chunks)

			if is_valid_2:
				span.set_attribute("success_on_retry", True)
				return answer_2

			# Both attempts failed — return refusal
			_generation_refusals.labels(reason="validation_failure").inc()
			logger.warning(f"Generation validation failed twice, refusing answer")
			span.set_attribute("refused_reason", "validation_failure_after_retry")

			return RagAnswer(
				answer="",
				refused=True,
				refusal_reason="Could not generate a reliable answer. Please rephrase your question.",
			)
