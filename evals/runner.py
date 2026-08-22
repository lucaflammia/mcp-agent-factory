"""Evaluation runner — produces a JSON report tagged with the commit SHA.

Usage:
  python -m evals.runner --dataset rag_qa --tag $(git rev-parse --short HEAD)
  python -m evals.runner --all
  python -m evals.runner --dataset refusal --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.metrics.groundedness import check_groundedness
from evals.metrics.ranking import evaluate_retrieval, aggregate_retrieval_metrics
from evals.metrics.retrieval import check_match, check_refusal
from evals.metrics.statistics import wilson_ci, minimum_detectable_effect

logger = logging.getLogger(__name__)

EVALS_DIR = Path(__file__).parent
DATASETS_DIR = EVALS_DIR / "datasets"
RESULTS_DIR = EVALS_DIR / "results"
CALIBRATION_PATH = EVALS_DIR / "judge" / "calibration.jsonl"


def git_sha() -> str:
  try:
    return subprocess.check_output(
      ["git", "rev-parse", "--short", "HEAD"],
      text=True, stderr=subprocess.DEVNULL,
    ).strip()
  except Exception:
    return "unknown"


def git_sha_full() -> str:
  try:
    return subprocess.check_output(
      ["git", "rev-parse", "HEAD"],
      text=True, stderr=subprocess.DEVNULL,
    ).strip()
  except Exception:
    return "unknown"


def load_dataset(name: str) -> list[dict[str, Any]]:
  path = DATASETS_DIR / f"{name}.jsonl"
  if not path.exists():
    raise FileNotFoundError(f"Dataset not found: {path}")
  examples = []
  with open(path) as f:
    for line in f:
      line = line.strip()
      if line:
        examples.append(json.loads(line))
  return examples


def list_datasets() -> list[str]:
  return sorted(p.stem for p in DATASETS_DIR.glob("*.jsonl"))


def simulate_answer(example: dict[str, Any]) -> str:
  """Generate a simulated answer for baseline evaluation.

  In a real eval run, this would call the actual system. For the baseline,
  we use the expected answer as-is for answerable questions and generate
  a refusal for unanswerable ones.
  """
  expected = example.get("expected", "")
  if expected == "REFUSE":
    return "I cannot determine this from the available information. The provided context does not contain the data needed to answer this question."

  if isinstance(expected, dict):
    return json.dumps(expected, indent=2)
  if isinstance(expected, list):
    return json.dumps(expected, indent=2)
  return str(expected)


def evaluate_rag_qa(example: dict[str, Any], answer: str) -> dict[str, Any]:
  category = example.get("category", "unknown")
  expected = str(example.get("expected", ""))

  # Cross-tenant isolation: evaluate as refusal, not match
  if category == "cross_tenant_isolation":
    refused = check_refusal(answer)
    result: dict[str, Any] = {
      "id": example["id"],
      "category": category,
      "refused": refused,
      "pass": refused,
    }
  else:
    match_result = check_match(answer, expected)

    context_text = example.get("context", "")
    if isinstance(context_text, str):
      chunks = [context_text] if context_text else []
    else:
      chunks = context_text

    ground = check_groundedness(answer, chunks)

    result = {
      "id": example["id"],
      "category": category,
      "match": match_result.to_dict(),
      "groundedness": ground.to_dict(),
      "pass": match_result.keyword_recall >= 0.5,
    }

  # Retrieval metrics (simulate perfect retrieval = relevant_chunks as retrieved list)
  relevant_chunks = example.get("relevant_chunks", [])
  retrieved_chunks = list(relevant_chunks)  # baseline: perfect retrieval
  retrieval_result = evaluate_retrieval(example["id"], retrieved_chunks, relevant_chunks)
  result["retrieval"] = retrieval_result.to_dict()

  # Oracle comparison
  retrieved_pass = result["pass"]
  oracle_pass = result["pass"]  # with simulation, oracle == retrieved

  if oracle_pass and retrieved_pass:
    diagnosis = "working"
  elif oracle_pass and not retrieved_pass:
    diagnosis = "retrieval_failure"
  elif not oracle_pass and retrieved_pass:
    diagnosis = "generation_failure"
  else:
    diagnosis = "both_failing"

  result["oracle_comparison"] = {
    "retrieved_pass": retrieved_pass,
    "oracle_pass": oracle_pass,
    "diagnosis": diagnosis,
  }

  return result


def evaluate_extraction(example: dict[str, Any], answer: str) -> dict[str, Any]:
  expected = example.get("expected", "")

  if isinstance(expected, (dict, list)):
    expected_str = json.dumps(expected, sort_keys=True)
    answer_normalized = answer.strip()
    try:
      answer_parsed = json.loads(answer_normalized)
      answer_str = json.dumps(answer_parsed, sort_keys=True)
      exact = answer_str == expected_str
    except json.JSONDecodeError:
      exact = False
      answer_str = answer_normalized

    match_result = check_match(answer, expected_str)
  else:
    match_result = check_match(answer, str(expected))
    exact = match_result.exact_match

  passed = exact or match_result.keyword_recall >= 0.6

  return {
    "id": example["id"],
    "category": example.get("category", "unknown"),
    "match": match_result.to_dict(),
    "pass": passed,
  }


def evaluate_refusal(example: dict[str, Any], answer: str) -> dict[str, Any]:
  refused = check_refusal(answer)

  return {
    "id": example["id"],
    "category": example.get("category", "unknown"),
    "refused": refused,
    "pass": refused,
  }


def run_calibration() -> dict[str, Any]:
  """Run judge calibration on the 20-example subset using heuristic groundedness.

  Returns agreement metrics between heuristic judge and human labels.
  """
  if not CALIBRATION_PATH.exists():
    return {"error": "calibration.jsonl not found", "n": 0}

  examples = []
  with open(CALIBRATION_PATH) as f:
    for line in f:
      line = line.strip()
      if line:
        examples.append(json.loads(line))

  judge_verdicts = []
  human_labels = []

  for ex in examples:
    answer = ex["answer"]
    context = ex.get("context", [])
    human = ex["human_grounded"]

    ground = check_groundedness(answer, context, threshold=0.3)
    judge_grounded = ground.score >= 0.7

    judge_verdicts.append(judge_grounded)
    human_labels.append(human)

  from evals.judge.judge import compute_judge_human_agreement
  agreement = compute_judge_human_agreement(judge_verdicts, human_labels)
  agreement["method"] = "heuristic_groundedness"
  agreement["threshold"] = 0.7
  return agreement


def build_report(
  dataset_results: dict[str, list[dict[str, Any]]],
  tag: str,
  calibration: dict[str, Any],
  elapsed_s: float,
) -> dict[str, Any]:
  """Build the final evaluation report with Wilson CIs on all rates."""

  report: dict[str, Any] = {
    "meta": {
      "tag": tag,
      "git_sha": git_sha_full(),
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "elapsed_seconds": round(elapsed_s, 2),
    },
    "calibration": calibration,
    "datasets": {},
    "summary": {},
  }

  total_pass = 0
  total_examples = 0

  for ds_name, results in dataset_results.items():
    n = len(results)
    passes = sum(1 for r in results if r.get("pass", False))
    total_pass += passes
    total_examples += n

    ci = wilson_ci(passes, n)

    ds_report: dict[str, Any] = {
      "n": n,
      "pass_rate": ci.to_dict(),
      "results": results,
    }

    if ds_name == "rag_qa":
      ground_scores = [r["groundedness"]["score"] for r in results if "groundedness" in r]
      if ground_scores:
        ds_report["avg_groundedness"] = round(sum(ground_scores) / len(ground_scores), 4)
      fuzzy_scores = [r["match"]["fuzzy_score"] for r in results if "match" in r]
      if fuzzy_scores:
        ds_report["avg_fuzzy_score"] = round(sum(fuzzy_scores) / len(fuzzy_scores), 4)
      kw_recalls = [r["match"]["keyword_recall"] for r in results if "match" in r]
      if kw_recalls:
        ds_report["avg_keyword_recall"] = round(sum(kw_recalls) / len(kw_recalls), 4)

      # Retrieval metrics (separate from generation metrics)
      from evals.metrics.ranking import RetrievalResult
      retrieval_objs = []
      for r in results:
        if "retrieval" in r:
          rd = r["retrieval"]
          retrieval_objs.append(RetrievalResult(
            query_id=rd["query_id"],
            relevant=frozenset(),  # not needed for aggregation
            retrieved=tuple(),
            recall_at_1=rd["recall@1"],
            recall_at_3=rd["recall@3"],
            recall_at_5=rd["recall@5"],
            recall_at_10=rd["recall@10"],
            mrr=rd["mrr"],
            ndcg_at_10=rd["ndcg@10"],
            context_precision=rd["context_precision"],
          ))
      if retrieval_objs:
        ds_report["retrieval_metrics"] = aggregate_retrieval_metrics(retrieval_objs)

      # Oracle comparison summary
      oracle_counts: dict[str, int] = {
        "working": 0,
        "retrieval_failure": 0,
        "generation_failure": 0,
        "both_failing": 0,
      }
      for r in results:
        if "oracle_comparison" in r:
          diag = r["oracle_comparison"]["diagnosis"]
          oracle_counts[diag] = oracle_counts.get(diag, 0) + 1
      ds_report["oracle_comparison_summary"] = oracle_counts

    elif ds_name == "refusal":
      refusals = sum(1 for r in results if r.get("refused", False))
      refusal_ci = wilson_ci(refusals, n)
      ds_report["refusal_rate"] = refusal_ci.to_dict()

    elif ds_name == "extraction":
      kw_recalls = [r["match"]["keyword_recall"] for r in results if "match" in r]
      if kw_recalls:
        ds_report["avg_keyword_recall"] = round(sum(kw_recalls) / len(kw_recalls), 4)

    report["datasets"][ds_name] = ds_report

  overall_ci = wilson_ci(total_pass, total_examples)
  mde = minimum_detectable_effect(total_examples)

  report["summary"] = {
    "total_examples": total_examples,
    "overall_pass_rate": overall_ci.to_dict(),
    "minimum_detectable_effect": round(mde, 4),
    "mde_note": (
      f"With n={total_examples}, changes smaller than "
      f"{mde:.1%} are indistinguishable from noise."
    ),
  }

  return report


def run_eval(
  datasets: list[str],
  tag: str | None = None,
  dry_run: bool = False,
) -> dict[str, Any]:
  """Run evaluation on specified datasets and produce a report."""
  start = time.monotonic()
  tag = tag or git_sha()

  dataset_results: dict[str, list[dict[str, Any]]] = {}

  for ds_name in datasets:
    examples = load_dataset(ds_name)
    results = []

    for example in examples:
      if dry_run:
        results.append({"id": example["id"], "pass": True, "dry_run": True})
        continue

      answer = simulate_answer(example)

      if ds_name == "rag_qa":
        result = evaluate_rag_qa(example, answer)
      elif ds_name == "extraction":
        result = evaluate_extraction(example, answer)
      elif ds_name == "refusal":
        result = evaluate_refusal(example, answer)
      else:
        result = evaluate_rag_qa(example, answer)

      results.append(result)

    dataset_results[ds_name] = results

  calibration = run_calibration() if not dry_run else {"skipped": True}
  elapsed = time.monotonic() - start

  report = build_report(dataset_results, tag, calibration, elapsed)

  RESULTS_DIR.mkdir(parents=True, exist_ok=True)
  output_path = RESULTS_DIR / f"{tag}.json"
  with open(output_path, "w") as f:
    json.dump(report, f, indent=2)

  return report


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Run LLM evaluation harness",
    prog="python -m evals.runner",
  )
  parser.add_argument(
    "--dataset", "-d",
    help="Dataset name (e.g. rag_qa, extraction, refusal)",
  )
  parser.add_argument(
    "--all", "-a",
    action="store_true",
    help="Run all datasets",
  )
  parser.add_argument(
    "--tag", "-t",
    help="Tag for this run (defaults to git SHA)",
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Validate dataset loading without running evaluation",
  )
  parser.add_argument(
    "--list",
    action="store_true",
    dest="list_datasets",
    help="List available datasets",
  )

  args = parser.parse_args()

  if args.list_datasets:
    for name in list_datasets():
      count = len(load_dataset(name))
      print(f"  {name}: {count} examples")
    return

  if args.all:
    datasets = list_datasets()
  elif args.dataset:
    datasets = [args.dataset]
  else:
    parser.error("Specify --dataset NAME or --all")
    return

  logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

  report = run_eval(datasets, tag=args.tag, dry_run=args.dry_run)

  tag = report["meta"]["tag"]
  output_path = RESULTS_DIR / f"{tag}.json"

  summary = report.get("summary", {})
  overall = summary.get("overall_pass_rate", {})
  cal = report.get("calibration", {})

  print(f"\n{'='*60}")
  print(f"Eval complete: {tag}")
  print(f"{'='*60}")
  print(f"Examples:    {summary.get('total_examples', 0)}")
  print(f"Pass rate:   {overall.get('proportion', 0):.1%} "
     f"[{overall.get('lower', 0):.1%}, {overall.get('upper', 0):.1%}]")
  print(f"MDE:         {summary.get('minimum_detectable_effect', 0):.1%}")

  # Retrieval metrics for rag_qa (printed before generation metrics)
  rag_ds = report.get("datasets", {}).get("rag_qa", {})
  ret_metrics = rag_ds.get("retrieval_metrics")
  if ret_metrics:
    print(f"\n--- Retrieval Metrics (rag_qa) ---")
    print(f"recall@1:          {ret_metrics.get('recall@1', 0):.4f}")
    print(f"recall@5:          {ret_metrics.get('recall@5', 0):.4f}")
    print(f"MRR:               {ret_metrics.get('mrr', 0):.4f}")
    print(f"nDCG@10:           {ret_metrics.get('ndcg@10', 0):.4f}")
    print(f"context_precision: {ret_metrics.get('context_precision', 0):.4f}")
    oracle_summary = rag_ds.get("oracle_comparison_summary", {})
    if oracle_summary:
      print(f"Oracle comparison: working={oracle_summary.get('working', 0)}, "
            f"retrieval_failure={oracle_summary.get('retrieval_failure', 0)}, "
            f"generation_failure={oracle_summary.get('generation_failure', 0)}, "
            f"both_failing={oracle_summary.get('both_failing', 0)}")

  if "accuracy" in cal:
    print(f"Judge-human: {cal['accuracy']:.1%} accuracy, "
       f"kappa={cal.get('cohens_kappa', 0):.2f}")

  print(f"Results:     {output_path}")
  print(f"Elapsed:     {report['meta']['elapsed_seconds']:.1f}s")


if __name__ == "__main__":
  main()
