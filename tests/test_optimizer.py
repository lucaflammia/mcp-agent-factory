"""
Tests for Layer 4: Offline Prompt Optimization (optimizer.py).

All tests are offline — no Kafka, no DSPy/GEPA install required.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from mcp_agent_factory.optimizer import (
  GEPAEvolver,
  PromptOptimizer,
  SkillAsset,
  SkillCompiler,
  TraceRecord,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def failing_traces() -> list[TraceRecord]:
  return [
    TraceRecord(
      trace_id=f"t{i:04d}",
      task=f"Summarise report {i}",
      phase="plan",
      prompt_template="You are a planning agent.",
      actor_output="ok" if i % 4 == 0 else "",
      evaluation_score=0.9 if i % 4 == 0 else 0.3,
      evaluation_findings=[] if i % 4 == 0 else ["Output too short", "Required field missing"],
      metadata={"role": "actor"},
    )
    for i in range(12)
  ]


@pytest.fixture
def passing_traces() -> list[TraceRecord]:
  return [
    TraceRecord(
      trace_id=f"p{i:04d}",
      task=f"List items {i}",
      phase="execute",
      prompt_template="You are an execution agent.",
      actor_output=f"Item {i}: done",
      evaluation_score=0.95,
      evaluation_findings=[],
      metadata={"role": "actor"},
    )
    for i in range(5)
  ]


# ---------------------------------------------------------------------------
# TraceRecord
# ---------------------------------------------------------------------------

class TestTraceRecord:
  def test_is_failure_when_score_below_threshold(self):
    t = TraceRecord(
      trace_id="x", task="t", phase="plan",
      prompt_template="p", actor_output="o",
      evaluation_score=0.5,
    )
    assert t.is_failure is True

  def test_is_not_failure_when_score_above_threshold(self):
    t = TraceRecord(
      trace_id="x", task="t", phase="plan",
      prompt_template="p", actor_output="o",
      evaluation_score=0.8,
    )
    assert t.is_failure is False

  def test_timestamp_auto_populated(self):
    before = time.time()
    t = TraceRecord(
      trace_id="x", task="t", phase="plan",
      prompt_template="p", actor_output="o",
      evaluation_score=0.7,
    )
    assert t.timestamp >= before


# ---------------------------------------------------------------------------
# GEPAEvolver — built-in mutation path
# ---------------------------------------------------------------------------

class TestGEPAEvolver:
  def test_evolve_returns_string_and_float(self, failing_traces):
    evolver = GEPAEvolver(max_generations=2, population_size=2)
    best_prompt, score = evolver.evolve(
      "You are a planning agent.",
      [t for t in failing_traces if t.is_failure],
    )
    assert isinstance(best_prompt, str)
    assert 0.0 <= score <= 1.0

  def test_evolve_improves_upon_finding_patterns(self):
    traces = [
      TraceRecord(
        trace_id="e1", task="t", phase="plan",
        prompt_template="base",
        actor_output="short",
        evaluation_score=0.3,
        evaluation_findings=["Output too short — word limit exceeded"],
        metadata={"role": "actor"},
      )
    ]
    evolver = GEPAEvolver()
    best_prompt, _ = evolver.evolve("Base prompt.", traces)
    # The evolved prompt should address the finding
    assert "word" in best_prompt.lower() or "length" in best_prompt.lower() or "constraint" in best_prompt.lower()

  def test_evolve_with_empty_failures_returns_base_prompt(self):
    evolver = GEPAEvolver()
    best_prompt, score = evolver.evolve("My base prompt.", [])
    assert best_prompt == "My base prompt."
    assert score == 1.0

  def test_generate_candidates_adds_constraint_clauses(self):
    evolver = GEPAEvolver(population_size=3)
    traces = [
      TraceRecord(
        trace_id="c1", task="t", phase="plan",
        prompt_template="p", actor_output="x",
        evaluation_score=0.2,
        evaluation_findings=["Required field missing", "word count exceeded"],
        metadata={},
      )
    ]
    candidates = evolver._generate_candidates("Base.", traces)
    assert len(candidates) > 0
    assert all(c.startswith("Base.") for c in candidates)

  def test_score_candidate_is_normalised(self, failing_traces):
    evolver = GEPAEvolver()
    failures = [t for t in failing_traces if t.is_failure]
    score = evolver._score_candidate("word field required short", failures)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# PromptOptimizer — dry_run mode
# ---------------------------------------------------------------------------

class TestPromptOptimizerDryRun:
  @pytest.mark.asyncio
  async def test_ingest_synthetic_traces(self):
    opt = PromptOptimizer(dry_run=True)
    traces = await opt.ingest_traces(limit=10)
    assert len(traces) == 10
    assert all(isinstance(t, TraceRecord) for t in traces)

  @pytest.mark.asyncio
  async def test_synthetic_traces_include_failures(self):
    opt = PromptOptimizer(dry_run=True)
    traces = await opt.ingest_traces(limit=10)
    assert any(t.is_failure for t in traces)

  @pytest.mark.asyncio
  async def test_compile_produces_skill_assets(self):
    opt = PromptOptimizer(dry_run=True)
    traces = await opt.ingest_traces(limit=10)
    assets = await opt.compile(traces)
    assert isinstance(assets, list)
    # Should produce at least one asset since dry-run traces include failures
    assert len(assets) >= 1
    assert all(isinstance(a, SkillAsset) for a in assets)

  @pytest.mark.asyncio
  async def test_compile_skips_pairs_with_no_failures(self, passing_traces):
    opt = PromptOptimizer(dry_run=False)
    assets = await opt.compile(passing_traces)
    # No failures → nothing to optimise → empty list
    assert assets == []

  @pytest.mark.asyncio
  async def test_compile_asset_fields_are_populated(self):
    opt = PromptOptimizer(dry_run=True)
    traces = await opt.ingest_traces(limit=10)
    assets = await opt.compile(traces)
    for asset in assets:
      assert asset.skill_id
      assert asset.role
      assert asset.phase
      assert asset.system_prompt
      assert 0.0 <= asset.performance_score <= 1.0

  @pytest.mark.asyncio
  async def test_compile_with_failing_traces(self, failing_traces):
    opt = PromptOptimizer(dry_run=False)
    assets = await opt.compile(failing_traces)
    assert len(assets) >= 1
    assert assets[0].phase == "plan"
    assert assets[0].role == "actor"

  def test_default_prompt_covers_known_roles_and_phases(self):
    opt = PromptOptimizer.__new__(PromptOptimizer)
    for role in ["actor", "critic"]:
      for phase in ["plan", "execute", "evaluate"]:
        prompt = opt._default_prompt(role, phase)
        assert isinstance(prompt, str)
        assert len(prompt) > 10

  def test_skill_id_is_stable(self):
    opt = PromptOptimizer.__new__(PromptOptimizer)
    id1 = opt._skill_id("actor", "plan")
    id2 = opt._skill_id("actor", "plan")
    assert id1 == id2
    assert id1 != opt._skill_id("critic", "plan")


# ---------------------------------------------------------------------------
# SkillCompiler
# ---------------------------------------------------------------------------

class TestSkillCompiler:
  def test_compile_all_writes_json_files(self, tmp_path):
    assets = [
      SkillAsset(
        skill_id="abc12345",
        role="actor",
        phase="plan",
        system_prompt="You are a planning agent.",
        performance_score=0.85,
      ),
      SkillAsset(
        skill_id="def67890",
        role="critic",
        phase="evaluate",
        system_prompt="You are an independent critic.",
        performance_score=0.9,
      ),
    ]
    compiler = SkillCompiler(output_dir=str(tmp_path))
    paths = compiler.compile_all(assets)

    assert len(paths) == 2
    for path in paths:
      assert path.exists()
      data = json.loads(path.read_text())
      assert "skill_id" in data
      assert "system_prompt" in data

  def test_compile_all_writes_index(self, tmp_path):
    assets = [
      SkillAsset(
        skill_id="idx00001",
        role="actor",
        phase="execute",
        system_prompt="Execute the plan.",
        performance_score=0.75,
      )
    ]
    compiler = SkillCompiler(output_dir=str(tmp_path))
    compiler.compile_all(assets)

    index_path = tmp_path / "index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text())
    assert "skills" in index
    assert index["skills"][0]["skill_id"] == "idx00001"
    assert index["skills"][0]["file"] == "idx00001.json"

  def test_compile_all_creates_output_dir(self, tmp_path):
    nested = tmp_path / "deep" / "nested" / "skills"
    compiler = SkillCompiler(output_dir=str(nested))
    assets = [
      SkillAsset(
        skill_id="new00001",
        role="actor",
        phase="plan",
        system_prompt="Plan.",
        performance_score=0.8,
      )
    ]
    compiler.compile_all(assets)
    assert nested.exists()

  def test_empty_assets_writes_empty_index(self, tmp_path):
    compiler = SkillCompiler(output_dir=str(tmp_path))
    paths = compiler.compile_all([])
    assert paths == []
    index = json.loads((tmp_path / "index.json").read_text())
    assert index["skills"] == []

  def test_skill_json_is_valid_skill_asset(self, tmp_path):
    asset = SkillAsset(
      skill_id="v00001",
      role="critic",
      phase="evaluate",
      system_prompt="Be strict.",
      few_shot_examples=[{"task": "t", "output": "o", "score": 0.9}],
      performance_score=0.88,
    )
    compiler = SkillCompiler(output_dir=str(tmp_path))
    [path] = compiler.compile_all([asset])
    loaded = SkillAsset(**json.loads(path.read_text()))
    assert loaded.skill_id == "v00001"
    assert loaded.few_shot_examples[0]["task"] == "t"
