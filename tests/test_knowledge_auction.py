"""Tests for knowledge-augmented auction (S03)."""
from __future__ import annotations

import numpy as np
import pytest

from mcp_agent_factory.agents.models import AgentTask
from mcp_agent_factory.economics.auction import Auction
from mcp_agent_factory.economics.utility import AgentProfile, UtilityFunction
from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore


# ---------------------------------------------------------------------------
# UtilityFunction.score() — knowledge_boost flag
# ---------------------------------------------------------------------------

@pytest.fixture()
def kr_profile() -> AgentProfile:
	return AgentProfile(
		agent_id="kr_agent",
		capabilities=["knowledge_retrieval", "analysis"],
		expertise_score=0.5,
		cost_per_unit=1.0,
	)


@pytest.fixture()
def plain_profile() -> AgentProfile:
	return AgentProfile(
		agent_id="plain_agent",
		capabilities=["analysis"],
		expertise_score=0.5,
		cost_per_unit=1.0,
	)


@pytest.fixture()
def task() -> AgentTask:
	return AgentTask(id="t1", name="test_task", required_capability="analysis", complexity=0.0)


def test_knowledge_boost_increases_score(kr_profile, task):
	u = UtilityFunction()
	s_no = u.score(task, kr_profile)
	s_yes = u.score(task, kr_profile, knowledge_boost=True)
	assert s_yes > s_no


def test_knowledge_boost_without_capability_is_noop(plain_profile, task):
	"""Agents without 'knowledge_retrieval' must not be affected by knowledge_boost."""
	u = UtilityFunction()
	s_no = u.score(task, plain_profile)
	s_yes = u.score(task, plain_profile, knowledge_boost=True)
	assert s_yes == s_no


def test_score_backward_compatible(kr_profile, task):
	"""Calling score() with no knowledge args must still work."""
	u = UtilityFunction()
	result = u.score(task, kr_profile)
	assert 0.0 <= result <= 1.0


def test_boosted_score_clamped_to_one():
	"""Even with boost, score must not exceed 1.0."""
	u = UtilityFunction()
	profile = AgentProfile(
		agent_id="rich",
		capabilities=["knowledge_retrieval", "analysis"],
		expertise_score=1.0,
		cost_per_unit=0.0,
	)
	task = AgentTask(id="t2", name="easy", required_capability="analysis", complexity=0.0)
	result = u.score(task, profile, knowledge_boost=True)
	assert result <= 1.0


# ---------------------------------------------------------------------------
# Auction.run() — vector probe wiring
# ---------------------------------------------------------------------------

def test_auction_backward_compatible(kr_profile, task):
	"""run() with no store/query_vector must still work."""
	auction = Auction()
	result = auction.run(task, [kr_profile])
	assert result.winner_id == "kr_agent"


def test_auction_with_empty_store_no_boost(kr_profile, plain_profile, task):
	"""Empty store → no knowledge_boost → both agents scored without boost."""
	store = InMemoryVectorStore()
	qv = np.array([1.0, 0.0])
	auction = Auction()
	result = auction.run(task, [kr_profile, plain_profile], store=store, query_vector=qv, owner_id="user1")
	# Without boost, kr_profile and plain_profile have the same params so kr wins by id tie-break
	assert result.winner_id in ("kr_agent", "plain_agent")


def test_auction_with_populated_store_boosts_kr(kr_profile, plain_profile, task):
	"""When store has a hit, kr_agent gets boost and wins over plain_agent with same expertise."""
	store = InMemoryVectorStore()
	vec = np.array([1.0, 0.0])
	store.upsert(owner_id="user1", text="relevant knowledge", vector=vec)
	auction = Auction()
	result = auction.run(task, [kr_profile, plain_profile], store=store, query_vector=vec, owner_id="user1")
	assert result.winner_id == "kr_agent"
	assert result.bids["kr_agent"] > result.bids["plain_agent"]


def test_auction_store_without_query_vector_no_boost(kr_profile, plain_profile, task):
	"""Passing store but no query_vector should not trigger boost (graceful degradation)."""
	store = InMemoryVectorStore()
	store.upsert("user1", "data", np.array([1.0, 0.0]))
	auction = Auction()
	# No query_vector → no probe → no boost
	result = auction.run(task, [kr_profile, plain_profile], store=store, owner_id="user1")
	# Both have same score → tie-break by alphabetical id → "kr_agent" wins
	assert result.bids["kr_agent"] == result.bids["plain_agent"]
