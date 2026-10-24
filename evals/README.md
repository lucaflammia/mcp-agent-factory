# Evaluation Harness

Tests prove the code does what it was written to do; they say nothing about
whether the system gives correct answers. This harness measures output quality.

## Datasets

55 hand-curated examples across 3 datasets:

| Dataset | File | Examples | Purpose |
|---------|------|----------|---------|
| **RAG Q&A** | `datasets/rag_qa.jsonl` | 25 | Factual extraction, comparison, reasoning, summarization against the Q3 2024 financial report |
| **Extraction** | `datasets/extraction.jsonl` | 15 | Structured extraction, constrained generation, numeric transformation |
| **Refusal** | `datasets/refusal.jsonl` | 15 | Unanswerable questions where the correct behavior is to decline |

Format: `{"id", "input", "expected", "category", "notes"}` (JSONL).

## Metrics

| Metric | Module | What it catches |
|--------|--------|-----------------|
| Exact / fuzzy match | `metrics/retrieval.py` | Deterministic pipeline regressions |
| Keyword recall | `metrics/retrieval.py` | Missing key facts in answers |
| Groundedness | `metrics/groundedness.py` | Hallucination (claims not in context) |
| Refusal detection | `metrics/retrieval.py` | Over-eagerness on unanswerable questions |
| Schema conformance | `metrics/schema_conformance.py` | Structured-output drift in OrchestratorPlan |
| Wilson confidence interval | `metrics/statistics.py` | Honest uncertainty on all reported rates |
| McNemar test | `metrics/statistics.py` | Paired comparison between two prompt versions |

Every reported rate carries a **Wilson 95% confidence interval**. With n=55,
the minimum detectable effect is **26.4%** — changes smaller than this are
indistinguishable from noise. The eval set needs to grow to detect smaller
improvements.

## LLM Judge

`judge/judge.py` uses a judge model (default: `google-gla:gemini-2.5-flash`)
distinct from the generator to evaluate groundedness claim-by-claim.

**Known failure modes** are documented in [`judge/KNOWN_BIASES.md`](judge/KNOWN_BIASES.md):
position bias, verbosity bias, self-preference, poor calibration near the
decision boundary, and anchoring on expected answers. Mitigations applied:
option order randomization, separate provider default, claim-level verification.

### Calibration

`judge/calibration.jsonl` contains **20 hand-labeled examples** (12 grounded,
8 ungrounded) including borderline cases. The runner computes judge–human
agreement (accuracy + Cohen's kappa) on every run.

**Current heuristic agreement:** 65.0% accuracy, kappa=0.15 (heuristic keyword
overlap only — LLM judge calibration requires live API keys).

## Usage

```bash
# List available datasets
python -m evals.runner --list

# Run all datasets
python -m evals.runner --all

# Run a single dataset with custom tag
python -m evals.runner --dataset rag_qa --tag my-experiment

# Dry run (validate loading without evaluation)
python -m evals.runner --all --dry-run

# Compare two runs
python -m evals.compare baseline my-experiment
```

## Results

Results are stored as `results/<tag>.json`. Each report contains:

- Git SHA and timestamp
- Per-example results with match scores and groundedness
- Per-dataset pass rates with Wilson confidence intervals
- Overall pass rate with minimum detectable effect
- Judge–human calibration agreement

## Baseline

The committed baseline (`results/baseline.json`) uses simulated answers
(expected values as responses). It establishes the evaluation infrastructure
and provides a reference point for future runs with live system responses.

| Metric | Value | 95% CI |
|--------|-------|--------|
| Overall pass rate | 100.0% | [93.5%, 100.0%] |
| RAG Q&A pass rate | 100.0% | [86.7%, 100.0%] |
| Extraction pass rate | 100.0% | [78.2%, 100.0%] |
| Refusal rate (on unanswerable) | 100.0% | [78.2%, 100.0%] |
| Judge–human agreement | 65.0% | (heuristic, kappa=0.15) |
| MDE at n=55 | 26.4% | — |

## Prompt-Version Regression Tracking

`compare.py` diffs two runs and lists per-example regressions — not just
aggregates. This connects directly to the DSPy + GEPA layer: optimized
prompts are versioned artifacts, so their effect must be measurable.

```
$ python -m evals.compare baseline <new-sha>
Comparing: baseline → <new-sha>
============================================================

Pass rate:  100.0% → 96.4% (-3.6%)
  A: [93.5%, 100.0%]
  B: [87.7%, 99.6%]

Regressions (2):
  - rag-015  (PASS → FAIL)
  - ext-009  (PASS → FAIL)

Improvements (0):

McNemar test: chi2=0.5, p=0.4795
  → Not significant (n_discordant=2)
```
