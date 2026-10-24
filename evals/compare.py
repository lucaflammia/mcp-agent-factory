"""Compare two evaluation runs and list per-example regressions.

Usage:
  python -m evals.compare <sha-a> <sha-b>
  python -m evals.compare baseline 47fee39
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evals.metrics.statistics import mcnemar_test, wilson_ci

RESULTS_DIR = Path(__file__).parent / "results"


def load_run(tag: str) -> dict:
  path = RESULTS_DIR / f"{tag}.json"
  if not path.exists():
    candidates = sorted(RESULTS_DIR.glob(f"{tag}*.json"))
    if candidates:
      path = candidates[0]
    else:
      print(f"Error: No results found for tag '{tag}'", file=sys.stderr)
      print(f"Available: {', '.join(p.stem for p in sorted(RESULTS_DIR.glob('*.json')))}", file=sys.stderr)
      sys.exit(1)
  with open(path) as f:
    return json.load(f)


def extract_per_example(run: dict) -> dict[str, bool]:
  """Extract {example_id: passed} from a run."""
  results = {}
  for ds_name, ds_data in run.get("datasets", {}).items():
    for r in ds_data.get("results", []):
      eid = r.get("id", "")
      results[eid] = r.get("pass", False)
  return results


def compare_runs(run_a: dict, run_b: dict, tag_a: str, tag_b: str) -> dict:
  """Compare two runs and produce a structured diff."""
  examples_a = extract_per_example(run_a)
  examples_b = extract_per_example(run_b)

  all_ids = sorted(set(examples_a) | set(examples_b))

  regressions = []
  improvements = []
  unchanged_pass = []
  unchanged_fail = []
  only_in_a = []
  only_in_b = []

  wins_a = 0
  wins_b = 0

  for eid in all_ids:
    in_a = eid in examples_a
    in_b = eid in examples_b

    if in_a and not in_b:
      only_in_a.append(eid)
      continue
    if in_b and not in_a:
      only_in_b.append(eid)
      continue

    passed_a = examples_a[eid]
    passed_b = examples_b[eid]

    if passed_a and not passed_b:
      regressions.append(eid)
      wins_a += 1
    elif not passed_a and passed_b:
      improvements.append(eid)
      wins_b += 1
    elif passed_a and passed_b:
      unchanged_pass.append(eid)
    else:
      unchanged_fail.append(eid)

  mcnemar = mcnemar_test(wins_a, wins_b)

  sum_a = run_a.get("summary", {}).get("overall_pass_rate", {})
  sum_b = run_b.get("summary", {}).get("overall_pass_rate", {})

  return {
    "comparison": {
      "run_a": {"tag": tag_a, "sha": run_a.get("meta", {}).get("git_sha", "")},
      "run_b": {"tag": tag_b, "sha": run_b.get("meta", {}).get("git_sha", "")},
    },
    "pass_rates": {
      "run_a": sum_a,
      "run_b": sum_b,
      "delta": round(sum_b.get("proportion", 0) - sum_a.get("proportion", 0), 4),
    },
    "per_example": {
      "regressions": regressions,
      "improvements": improvements,
      "unchanged_pass": len(unchanged_pass),
      "unchanged_fail": len(unchanged_fail),
      "only_in_a": only_in_a,
      "only_in_b": only_in_b,
    },
    "mcnemar_test": mcnemar,
  }


def format_comparison(diff: dict) -> str:
  lines = []
  comp = diff["comparison"]
  lines.append(f"Comparing: {comp['run_a']['tag']} → {comp['run_b']['tag']}")
  lines.append("=" * 60)

  pr = diff["pass_rates"]
  rate_a = pr.get("run_a", {})
  rate_b = pr.get("run_b", {})
  delta = pr.get("delta", 0)
  direction = "+" if delta >= 0 else ""

  lines.append(f"\nPass rate:  {rate_a.get('proportion', 0):.1%} → {rate_b.get('proportion', 0):.1%} ({direction}{delta:.1%})")
  lines.append(f"  A: [{rate_a.get('lower', 0):.1%}, {rate_a.get('upper', 0):.1%}]")
  lines.append(f"  B: [{rate_b.get('lower', 0):.1%}, {rate_b.get('upper', 0):.1%}]")

  pe = diff["per_example"]
  regs = pe["regressions"]
  imps = pe["improvements"]

  if regs:
    lines.append(f"\nRegressions ({len(regs)}):")
    for eid in regs:
      lines.append(f"  - {eid}  (PASS → FAIL)")

  if imps:
    lines.append(f"\nImprovements ({len(imps)}):")
    for eid in imps:
      lines.append(f"  + {eid}  (FAIL → PASS)")

  if not regs and not imps:
    lines.append("\nNo per-example changes.")

  lines.append(f"\nUnchanged: {pe['unchanged_pass']} pass, {pe['unchanged_fail']} fail")

  if pe["only_in_a"]:
    lines.append(f"Only in A: {pe['only_in_a']}")
  if pe["only_in_b"]:
    lines.append(f"Only in B: {pe['only_in_b']}")

  mc = diff["mcnemar_test"]
  lines.append(f"\nMcNemar test: chi2={mc['chi2']}, p={mc['p_value']}")
  if mc["significant"]:
    lines.append("  → Statistically significant difference (p < 0.05)")
  else:
    lines.append(f"  → Not significant (n_discordant={mc['n_discordant']})")

  return "\n".join(lines)


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Compare two evaluation runs",
    prog="python -m evals.compare",
  )
  parser.add_argument("run_a", help="Tag or SHA of the first (baseline) run")
  parser.add_argument("run_b", help="Tag or SHA of the second run")
  parser.add_argument("--json", action="store_true", help="Output raw JSON")

  args = parser.parse_args()

  data_a = load_run(args.run_a)
  data_b = load_run(args.run_b)

  diff = compare_runs(data_a, data_b, args.run_a, args.run_b)

  if args.json:
    print(json.dumps(diff, indent=2))
  else:
    print(format_comparison(diff))


if __name__ == "__main__":
  main()
