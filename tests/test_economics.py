"""
Tests for economic task allocation: UtilityFunction, AgentProfile, Auction.
"""
from __future__ import annotations

import json
import logging

import pytest

from mcp_agent_factory.agents.models import AgentTask
from mcp_agent_factory.economics.auction import Auction, BidResult
from mcp_agent_factory.economics.utility import AgentProfile, UtilityFunction

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def analysis_task():
	return AgentTask(
		name="analyse_data",
		payload={"value": 100},
		complexity=0.5,
		required_capability="analysis",
	)


@pytest.fixture
def analyst_profile():
	return AgentProfile(
		agent_id="analyst-agent",
		capabilities=["analysis", "metrics"],
		expertise_score=0.9,
		cost_per_unit=0.5,
	)


@pytest.fixture
def writer_profile():
	return AgentProfile(
		agent_id="writer-agent",
		capabilities=["writing", "reporting"],
		expertise_score=0.8,
		cost_per_unit=0.3,
	)


@pytest.fixture
def cheap_profile():
	return AgentProfile(
		agent_id="cheap-agent",
		capabilities=["analysis"],
		expertise_score=0.6,
		cost_per_unit=0.1,
	)


# ---------------------------------------------------------------------------
# UtilityFunction tests
# ---------------------------------------------------------------------------

class TestUtilityFunction:
	def test_utility_score_capability_match(self, analysis_task, analyst_profile, writer_profile):
		uf = UtilityFunction()
		score_match = uf.score(analysis_task, analyst_profile)
		score_no_match = uf.score(analysis_task, writer_profile)
		assert score_match > score_no_match

	def test_utility_score_high_cost_lowers_score(self, analysis_task):
		uf = UtilityFunction()
		cheap = AgentProfile(agent_id="cheap", capabilities=["analysis"], expertise_score=0.8, cost_per_unit=0.1)
		expensive = AgentProfile(agent_id="exp", capabilities=["analysis"], expertise_score=0.8, cost_per_unit=5.0)
		assert uf.score(analysis_task, cheap) > uf.score(analysis_task, expensive)

	def test_utility_score_clamped_to_unit_interval(self, analysis_task):
		uf = UtilityFunction()
		# Edge: very high cost should clamp to 0, not go negative
		very_expensive = AgentProfile(agent_id="x", capabilities=["analysis"], expertise_score=1.0, cost_per_unit=100.0)
		score = uf.score(analysis_task, very_expensive)
		assert 0.0 <= score <= 1.0

	def test_utility_score_complexity_impact(self):
		uf = UtilityFunction()
		profile = AgentProfile(agent_id="a", capabilities=["analysis"], expertise_score=0.8, cost_per_unit=0.5)
		low_complexity = AgentTask(name="easy", payload={}, complexity=0.1, required_capability="analysis")
		high_complexity = AgentTask(name="hard", payload={}, complexity=0.9, required_capability="analysis")
		assert uf.score(low_complexity, profile) > uf.score(high_complexity, profile)

	def test_utility_score_no_capability_match_uses_partial(self, analysis_task):
		uf = UtilityFunction()
		no_cap = AgentProfile(agent_id="b", capabilities=["writing"], expertise_score=1.0, cost_per_unit=0.0)
		score = uf.score(analysis_task, no_cap)
		# expertise_match=0.3 * 1.0 - 0.2*0.5 - 0 = 0.3 - 0.1 = 0.2
		assert 0.0 < score < 0.5


# ---------------------------------------------------------------------------
# Auction tests
# ---------------------------------------------------------------------------

class TestAuction:
	def test_auction_selects_highest_bidder(self, analysis_task, analyst_profile, writer_profile, cheap_profile):
		auction = Auction()
		result = auction.run(analysis_task, [analyst_profile, writer_profile, cheap_profile])
		assert isinstance(result, BidResult)
		# analyst has matching capability + high expertise → should win
		assert result.winner_id == "analyst-agent"

	def test_auction_tiebreak_by_agent_id(self, analysis_task):
		auction = Auction()
		# Identical profiles except agent_id
		p1 = AgentProfile(agent_id="agent-b", capabilities=["analysis"], expertise_score=0.7, cost_per_unit=0.5)
		p2 = AgentProfile(agent_id="agent-a", capabilities=["analysis"], expertise_score=0.7, cost_per_unit=0.5)
		result = auction.run(analysis_task, [p1, p2])
		# Tie-break: alphabetically lowest wins → "agent-a"
		assert result.winner_id == "agent-a"

	def test_auction_empty_profiles_raises(self, analysis_task):
		auction = Auction()
		with pytest.raises(ValueError, match="at least one"):
			auction.run(analysis_task, [])

	def test_auction_bid_result_contains_all_bids(self, analysis_task, analyst_profile, writer_profile):
		auction = Auction()
		result = auction.run(analysis_task, [analyst_profile, writer_profile])
		assert "analyst-agent" in result.bids
		assert "writer-agent" in result.bids
		assert len(result.bids) == 2

	def test_auction_logs_bidding_trace(self, analysis_task, analyst_profile, caplog):
		auction = Auction()
		with caplog.at_level(logging.DEBUG, logger="mcp_agent_factory.economics.auction"):
			auction.run(analysis_task, [analyst_profile])
		log_messages = [r.message for r in caplog.records]
		parsed = [json.loads(m) for m in log_messages if m.startswith("{")]
		auction_logs = [p for p in parsed if p.get("event") == "auction_result"]
		assert len(auction_logs) == 1
		assert "winner_id" in auction_logs[0]
		assert "bids" in auction_logs[0]

	def test_single_agent_wins_auction(self, analysis_task, analyst_profile):
		auction = Auction()
		result = auction.run(analysis_task, [analyst_profile])
		assert result.winner_id == "analyst-agent"
		assert result.winning_bid == result.bids["analyst-agent"]

	def test_winning_bid_equals_bid_in_dict(self, analysis_task, analyst_profile, writer_profile):
		auction = Auction()
		result = auction.run(analysis_task, [analyst_profile, writer_profile])
		assert result.winning_bid == result.bids[result.winner_id]
