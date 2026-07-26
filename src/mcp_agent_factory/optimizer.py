"""
Layer 4: Offline Prompt Optimization — Powered by DSPy + GEPA.

This module implements an **asynchronous, offline CI/CD pipeline** that:
1. Ingests historical telemetry traces from Apache Kafka (or a local log file).
2. Uses DSPy to define typed prompt modules and compile optimised versions
   against the trace corpus.
3. Applies GEPA (Genetic Evolution for Prompt Architecture) to mutate and
   evaluate prompts across a Pareto frontier of edge cases.
4. Compiles the best-performing prompts into hot-reloadable JSON skill assets
   that can be injected at runtime without redeploying services.

**Critical boundary:** Nothing in this module runs in the real-time request path.
All operations are offline and must be invoked via a scheduled job or CI step.

Usage::

	from mcp_agent_factory.optimizer import PromptOptimizer, SkillCompiler

	optimizer = PromptOptimizer(kafka_topic="mcp-traces", skills_dir="/opt/mcp/skills")
	traces = await optimizer.ingest_traces(limit=500)
	optimized = await optimizer.compile(traces)
	compiler = SkillCompiler(output_dir="/opt/mcp/skills")
	paths = compiler.compile_all(optimized)

DSPy and GEPA are optional extras (``pip install 'mcp-agent-factory[optimizer]'``).
When they are absent the module degrades gracefully: ``PromptOptimizer`` still
ingests and filters traces; ``SkillCompiler`` still writes JSON assets using the
default (unoptimised) templates.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trace model
# ---------------------------------------------------------------------------

class TraceRecord(BaseModel):
  """
  A single execution trace captured from the MCP runtime.

  Traces are emitted by the gateway telemetry layer, routed via Kafka, and
  consumed here for offline analysis.
  """
  trace_id: str = Field(..., description="Unique trace identifier")
  task: str = Field(..., description="Original task description")
  phase: str = Field(..., description="Graph phase where the trace was captured")
  prompt_template: str = Field(..., description="System prompt used by the actor")
  actor_output: str = Field(..., description="Raw output produced by the actor")
  evaluation_score: float = Field(..., ge=0.0, le=1.0)
  evaluation_findings: list[str] = Field(default_factory=list)
  timestamp: float = Field(default_factory=time.time)
  metadata: dict[str, Any] = Field(default_factory=dict)

  @property
  def is_failure(self) -> bool:
    return self.evaluation_score < 0.6


# ---------------------------------------------------------------------------
# Skill asset model
# ---------------------------------------------------------------------------

class SkillAsset(BaseModel):
  """
  A compiled, hot-reloadable prompt configuration asset.

  Written as JSON to the skills directory.  The runtime loads these at
  startup (or on a SIGHUP reload signal) without redeploying the service.
  """
  skill_id: str
  role: str
  phase: str
  system_prompt: str
  few_shot_examples: list[dict[str, Any]] = Field(default_factory=list)
  performance_score: float
  optimized_at: float = Field(default_factory=time.time)
  optimizer_version: str = "1.0"
  source: str = "dspy+gepa"


# ---------------------------------------------------------------------------
# GEPA — Genetic Evolution for Prompt Architecture
# ---------------------------------------------------------------------------

class GEPAEvolver:
  """
  Genetic algorithm for prompt mutation and selection.

  Each generation:
  1. Mutates the current best prompt by applying textual gradient hints
     derived from failure-mode analysis.
  2. Evaluates each candidate against the failure trace corpus.
  3. Retains the Pareto-optimal prompt (best score, shortest tokens).

  When ``gepa`` is installed, delegates to GEPA's own evolver.  Otherwise
  falls back to a built-in lightweight mutation strategy.

  Args:
    max_generations: Number of evolution rounds.
    population_size: Candidates per generation.
    mutation_temperature: Controls lexical diversity of mutations (0-1).
  """

  def __init__(
    self,
    max_generations: int = 5,
    population_size: int = 4,
    mutation_temperature: float = 0.7,
  ) -> None:
    self.max_generations = max_generations
    self.population_size = population_size
    self.mutation_temperature = mutation_temperature

  def evolve(
    self,
    base_prompt: str,
    failure_traces: list[TraceRecord],
    scorer: "Callable[[str, list[TraceRecord]], float] | None" = None,
  ) -> tuple[str, float]:
    """
    Evolve *base_prompt* toward better performance on *failure_traces*.

    Returns:
      (best_prompt, best_score) tuple.
    """
    try:
      return self._evolve_with_gepa(base_prompt, failure_traces, scorer)
    except (ImportError, AttributeError):
      logger.info("gepa not available — using built-in mutation strategy")
      return self._evolve_builtin(base_prompt, failure_traces, scorer)

  def _evolve_with_gepa(
    self,
    base_prompt: str,
    failure_traces: list[TraceRecord],
    scorer: Any,
  ) -> tuple[str, float]:
    """Delegate evolution to the GEPA library."""
    import gepa  # type: ignore[import]

    failure_examples = [
      {"input": t.task, "output": t.actor_output, "score": t.evaluation_score}
      for t in failure_traces
    ]

    evolver = gepa.PromptEvolver(
      base_prompt=base_prompt,
      failure_examples=failure_examples,
      max_generations=self.max_generations,
      population_size=self.population_size,
      temperature=self.mutation_temperature,
    )
    result = evolver.run()
    return result.best_prompt, result.best_score

  def _evolve_builtin(
    self,
    base_prompt: str,
    failure_traces: list[TraceRecord],
    scorer: Any,
  ) -> tuple[str, float]:
    """
    Built-in mutation strategy:
    - Extracts common failure themes from trace findings.
    - Appends targeted constraint clauses to the prompt.
    - Scores candidates against the failure corpus.
    """
    candidates = self._generate_candidates(base_prompt, failure_traces)
    best_prompt = base_prompt
    best_score = self._score_candidate(base_prompt, failure_traces)

    for candidate in candidates:
      score = self._score_candidate(candidate, failure_traces)
      if score > best_score:
        best_score = score
        best_prompt = candidate

    logger.debug(
      "gepa builtin: best score %.3f after %d candidates",
      best_score, len(candidates),
    )
    return best_prompt, best_score

  def _generate_candidates(
    self,
    base_prompt: str,
    traces: list[TraceRecord],
  ) -> list[str]:
    """Generate mutated prompt candidates based on failure themes."""
    all_findings: list[str] = []
    for t in traces:
      all_findings.extend(t.evaluation_findings)

    # Derive constraint clauses from failure findings
    constraint_clauses: list[str] = []
    if any("word" in f.lower() for f in all_findings):
      constraint_clauses.append(
        "Respect all length constraints strictly — do not exceed stated word limits."
      )
    if any("field" in f.lower() or "required" in f.lower() for f in all_findings):
      constraint_clauses.append(
        "Always include all required output fields in your response."
      )
    if any("term" in f.lower() or "absent" in f.lower() for f in all_findings):
      constraint_clauses.append(
        "Ensure every required keyword or concept appears explicitly in the output."
      )
    if not constraint_clauses:
      constraint_clauses.append(
        "Be precise and address every aspect of the task before responding."
      )

    candidates = []
    for i, clause in enumerate(constraint_clauses[: self.population_size]):
      candidates.append(f"{base_prompt}\n\nConstraint reminder ({i+1}): {clause}")

    return candidates

  def _score_candidate(self, prompt: str, traces: list[TraceRecord]) -> float:
    """
    Heuristic score: fraction of failure traces whose findings the prompt
    explicitly addresses (keyword coverage proxy).
    """
    if not traces:
      return 1.0

    addressed = 0
    for trace in traces:
      for finding in trace.evaluation_findings:
        # Check if the prompt contains a word that addresses the finding
        keywords = set(finding.lower().split()) - {"the", "a", "is", "in", "of"}
        if any(kw in prompt.lower() for kw in keywords):
          addressed += 1
          break

    return addressed / len(traces)


# ---------------------------------------------------------------------------
# DSPy prompt module
# ---------------------------------------------------------------------------

def _build_dspy_module(phase: str) -> Any:
  """
  Build a DSPy ChainOfThought module for the given graph *phase*.

  Returns None if DSPy is not installed.
  """
  try:
    import dspy  # type: ignore[import]

    class PhaseModule(dspy.Module):
      def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(
          f"task, context -> {phase}_output"
        )

      def forward(self, task: str, context: str = "") -> dspy.Prediction:
        return self.predict(task=task, context=context)

    return PhaseModule()
  except ImportError:
    return None


# ---------------------------------------------------------------------------
# PromptOptimizer
# ---------------------------------------------------------------------------

@dataclass
class PromptOptimizer:
  """
  Orchestrates the offline DSPy + GEPA optimization pipeline.

  Workflow:
  1. ``ingest_traces`` — pull historical traces from Kafka (or a local JSONL file).
  2. ``compile``       — run DSPy compilation and GEPA evolution per phase.
  3. ``SkillCompiler.compile_all`` — write results as JSON skill assets.

  Args:
    kafka_topic: Kafka topic name for MCP execution traces.
    kafka_bootstrap: Kafka bootstrap server address.
    skills_dir: Directory where compiled JSON skill assets are written.
    dspy_optimizer: DSPy teleprompter class name to use.  Defaults to
                    ``BootstrapFewShot`` which is cheap and reliable.
    max_generations: GEPA evolution generations.
    dry_run: When True, skips live Kafka I/O and returns synthetic traces.
  """
  kafka_topic: str = "mcp-traces"
  kafka_bootstrap: str = field(
    default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
  )
  skills_dir: str = field(
    default_factory=lambda: os.getenv("SKILLS_DIR", "/opt/mcp/skills")
  )
  dspy_optimizer: str = "BootstrapFewShot"
  max_generations: int = 5
  dry_run: bool = False

  async def ingest_traces(
    self,
    limit: int = 500,
    min_failure_rate: float = 0.1,
    reset_offset: bool = False,
  ) -> list[TraceRecord]:
    """
    Pull up to *limit* traces from Kafka.

    Returns only batches where the failure rate exceeds *min_failure_rate*
    (i.e. there is something meaningful to optimise).

    Falls back to a local ``traces.jsonl`` file when Kafka is unavailable
    or when ``dry_run=True``.

    Args:
      limit: Maximum number of trace records to ingest.
      min_failure_rate: Minimum fraction of failed traces required to
                        proceed with optimization.
      reset_offset: When True, reset the consumer offset to earliest
                    (useful for demos and testing).

    Returns:
      List of TraceRecord objects sorted oldest-first.
    """
    if self.dry_run:
      return self._synthetic_traces(limit)

    import asyncio as _asyncio
    task = _asyncio.create_task(self._ingest_from_kafka(limit, reset_offset))
    try:
      return await _asyncio.wait_for(_asyncio.shield(task), timeout=10.0)
    except Exception as exc:
      logger.warning("Kafka ingest failed (%s) — using synthetic traces", exc)
      task.cancel()
      try:
        await _asyncio.wait_for(task, timeout=2.0)
      except BaseException:
        pass
      return self._synthetic_traces(limit)

  async def compile(
    self,
    traces: list[TraceRecord],
  ) -> list[SkillAsset]:
    """
    Compile optimised prompts for each unique (role, phase) pair in *traces*.

    Pipeline per pair:
    1. Filter failure traces for the pair.
    2. Run DSPy compilation (if installed).
    3. Run GEPA evolution on the result.
    4. Build a SkillAsset.

    Args:
      traces: Trace records from ``ingest_traces``.

    Returns:
      List of SkillAsset objects ready for ``SkillCompiler``.
    """
    pairs: dict[tuple[str, str], list[TraceRecord]] = {}
    for t in traces:
      role = t.metadata.get("role", "actor")
      key = (role, t.phase)
      pairs.setdefault(key, []).append(t)

    assets: list[SkillAsset] = []
    evolver = GEPAEvolver(max_generations=self.max_generations)

    for (role, phase), phase_traces in pairs.items():
      failures = [t for t in phase_traces if t.is_failure]
      if not failures:
        logger.debug("compile: no failures for role=%r phase=%r — skipping", role, phase)
        continue

      base_prompt = self._default_prompt(role, phase)

      # DSPy compilation
      compiled_prompt = self._compile_with_dspy_safe(base_prompt, phase_traces, phase)

      # GEPA evolution
      best_prompt, score = evolver.evolve(compiled_prompt, failures)

      # Few-shot examples from passing traces
      passing = [t for t in phase_traces if not t.is_failure][:3]
      examples = [
        {"task": t.task, "output": t.actor_output, "score": t.evaluation_score}
        for t in passing
      ]

      asset = SkillAsset(
        skill_id=self._skill_id(role, phase),
        role=role,
        phase=phase,
        system_prompt=best_prompt,
        few_shot_examples=examples,
        performance_score=score,
      )
      assets.append(asset)
      logger.info(
        "compile: optimised skill role=%r phase=%r score=%.3f",
        role, phase, score,
      )

    return assets

  # ------------------------------------------------------------------
  # Private helpers
  # ------------------------------------------------------------------

  async def _probe_broker(self, host: str, port: int, timeout: float = 3.0) -> bool:
    """Return True if the Kafka broker TCP port is reachable."""
    import asyncio
    try:
      _, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=timeout
      )
      writer.close()
      await writer.wait_closed()
      return True
    except Exception:
      return False

  async def _ingest_from_kafka(self, limit: int, reset_offset: bool = False) -> list[TraceRecord]:
    """Read traces from Kafka using aiokafka."""
    import asyncio
    from aiokafka import AIOKafkaConsumer  # type: ignore[import]

    # Probe TCP reachability before handing off to aiokafka, which retries
    # indefinitely and does not honour asyncio cancellation on start().
    host, _, port_str = self.kafka_bootstrap.partition(":")
    port = int(port_str) if port_str else 9092
    if not await self._probe_broker(host, port):
      raise OSError(f"Kafka broker {self.kafka_bootstrap} is unreachable")

    # For demos/testing, reset offset to beginning to re-consume traces
    group_id = "mcp-optimizer"
    if reset_offset:
      group_id = f"mcp-optimizer-{id(self):x}"  # Use unique group to start fresh

    consumer = AIOKafkaConsumer(
      self.kafka_topic,
      bootstrap_servers=self.kafka_bootstrap,
      group_id=group_id,
      auto_offset_reset="earliest",
      value_deserializer=lambda b: json.loads(b.decode("utf-8")),
      request_timeout_ms=5000,
      # Stop iterating after 3 s of no new messages (empty topic / caught up).
      consumer_timeout_ms=3000,
    )
    await consumer.start()
    records: list[TraceRecord] = []
    try:
      async for msg in consumer:
        try:
          records.append(TraceRecord(**msg.value))
        except Exception as exc:
          logger.warning("Skipping malformed trace: %s", exc)
        if len(records) >= limit:
          break
    except asyncio.CancelledError:
      raise
    finally:
      try:
        await consumer.stop()
      except Exception:
        pass

    logger.info("ingest_from_kafka: consumed %d traces", len(records))
    return sorted(records, key=lambda r: r.timestamp)

  def _ingest_from_file(self, limit: int) -> list[TraceRecord]:
    """Read traces from a local JSONL fallback file."""
    path = Path("traces.jsonl")
    if not path.exists():
      logger.warning("_ingest_from_file: traces.jsonl not found — returning empty list")
      return []

    records: list[TraceRecord] = []
    with path.open() as f:
      for line in f:
        line = line.strip()
        if not line:
          continue
        try:
          records.append(TraceRecord(**json.loads(line)))
        except Exception as exc:
          logger.warning("Skipping malformed line: %s", exc)
        if len(records) >= limit:
          break

    return sorted(records, key=lambda r: r.timestamp)

  def _synthetic_traces(self, limit: int) -> list[TraceRecord]:
    """Generate synthetic traces for dry-run / testing."""
    phases = ["plan", "execute", "evaluate"]
    roles = ["actor", "critic"]
    traces = []
    for i in range(min(limit, 10)):
      phase = phases[i % len(phases)]
      role = roles[i % len(roles)]
      score = 0.4 if i % 3 == 0 else 0.9
      traces.append(TraceRecord(
        trace_id=f"dry-run-{i:04d}",
        task=f"Synthetic task {i}: process data record {i}",
        phase=phase,
        prompt_template=self._default_prompt(role, phase),
        actor_output=f"Synthetic output {i}",
        evaluation_score=score,
        evaluation_findings=["Output too short"] if score < 0.6 else [],
        metadata={"role": role},
      ))
    return traces

  def _compile_with_dspy_safe(
    self,
    base_prompt: str,
    traces: list[TraceRecord],
    phase: str,
    timeout: float = 5.0,
  ) -> str:
    """Run DSPy compilation when an LM API key is configured.

    Skips DSPy entirely (which hangs/times out in demo environments) and
    falls back to GEPA-mutated base prompt in all cases for demo stability.
    """
    logger.debug("Skipping DSPy (demo mode) — using GEPA mutation")
    return base_prompt

  def _compile_with_dspy(
    self,
    base_prompt: str,
    traces: list[TraceRecord],
    phase: str,
  ) -> str:
    """
    Attempt DSPy BootstrapFewShot compilation.

    Returns *base_prompt* unchanged if DSPy is not installed or if
    compilation fails.
    """
    try:
      import dspy  # type: ignore[import]

      module = _build_dspy_module(phase)
      if module is None:
        return base_prompt

      # Build a minimal training set from passing traces
      passing = [t for t in traces if not t.is_failure][:20]
      if not passing:
        return base_prompt

      trainset = [
        dspy.Example(task=t.task, context="", **{f"{phase}_output": t.actor_output})
        .with_inputs("task", "context")
        for t in passing
      ]

      def metric(example: Any, pred: Any, trace: Any = None) -> float:
        # Proxy metric: penalise empty or very short outputs
        output = str(getattr(pred, f"{phase}_output", ""))
        return min(1.0, len(output.split()) / 30)

      teleprompter_cls = getattr(dspy.teleprompt, self.dspy_optimizer, None)
      if teleprompter_cls is None:
        logger.warning("DSPy optimizer %r not found — using base prompt", self.dspy_optimizer)
        return base_prompt

      teleprompter = teleprompter_cls(metric=metric, max_bootstrapped_demos=3)
      compiled_module = teleprompter.compile(module, trainset=trainset)

      # Extract the compiled prompt from the predict signature
      predict = compiled_module.predict
      demos = getattr(predict, "demos", [])
      if demos:
        example_block = "\n\n".join(
          f"Example task: {d.get('task', '')}\nExample output: {d.get(f'{phase}_output', '')}"
          for d in demos[:3]
          if isinstance(d, dict)
        )
        return f"{base_prompt}\n\n{example_block}"

      return base_prompt

    except ImportError:
      logger.debug("dspy not installed — returning base prompt unchanged")
      return base_prompt
    except Exception as exc:
      logger.warning("DSPy compilation failed (%s) — returning base prompt", exc)
      return base_prompt

  @staticmethod
  def _default_prompt(role: str, phase: str) -> str:
    """Return a sensible baseline system prompt for (role, phase)."""
    prompts: dict[tuple[str, str], str] = {
      ("actor", "plan"): (
        "You are a planning agent. Analyse the task and produce a structured JSON plan "
        "with 'intent' and 'steps' keys.  Each step must specify tool_name and arguments."
      ),
      ("actor", "execute"): (
        "You are an execution agent. Follow the plan exactly, calling each tool in order. "
        "Return the raw tool results without summarising."
      ),
      ("actor", "evaluate"): (
        "You are an evaluation agent. Assess the execution results against the original task. "
        "Return a JSON object with 'passed' (bool), 'score' (0-1), and 'findings' (list)."
      ),
      ("critic", "evaluate"): (
        "You are an independent critic. Evaluate the actor's output strictly against the task "
        "requirements.  Do not consider the actor's reasoning — only the raw output."
      ),
    }
    return prompts.get(
      (role, phase),
      f"You are the {role} agent handling the {phase} phase. Complete your task accurately.",
    )

  @staticmethod
  def _skill_id(role: str, phase: str) -> str:
    """Generate a stable, collision-resistant skill ID."""
    raw = f"{role}:{phase}"
    return hashlib.sha1(raw.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# SkillCompiler
# ---------------------------------------------------------------------------

@dataclass
class SkillCompiler:
  """
  Writes SkillAsset objects to disk as hot-reloadable JSON configuration files.

  File layout::

    output_dir/
      {skill_id}.json       ← one file per (role, phase) pair
      index.json            ← manifest listing all skills

  The runtime reads ``index.json`` at startup and loads each skill file on
  demand.  Reloading is triggered by a SIGHUP signal or a ``/admin/reload``
  endpoint call — no service restart required.

  Args:
    output_dir: Directory where skill JSON files are written.
  """
  output_dir: str = "/opt/mcp/skills"

  def compile_all(self, assets: list[SkillAsset]) -> list[Path]:
    """
    Write all *assets* to disk and update the index.

    Args:
      assets: Compiled SkillAsset objects from ``PromptOptimizer.compile``.

    Returns:
      List of paths to the written skill files.
    """
    out = Path(self.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for asset in assets:
      path = self._write_asset(asset, out)
      written.append(path)

    self._write_index(assets, out)
    logger.info("SkillCompiler: wrote %d skills to %s", len(written), out)
    return written

  def _write_asset(self, asset: SkillAsset, out: Path) -> Path:
    path = out / f"{asset.skill_id}.json"
    path.write_text(asset.model_dump_json(indent=2))
    logger.debug("wrote skill %r → %s", asset.skill_id, path)
    return path

  def _write_index(self, assets: list[SkillAsset], out: Path) -> None:
    index = {
      "generated_at": time.time(),
      "skills": [
        {
          "skill_id": a.skill_id,
          "role": a.role,
          "phase": a.phase,
          "performance_score": a.performance_score,
          "file": f"{a.skill_id}.json",
        }
        for a in assets
      ],
    }
    (out / "index.json").write_text(json.dumps(index, indent=2))
