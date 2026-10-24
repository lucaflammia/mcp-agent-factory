# Known Biases — LLM-as-Judge

This document records the known failure modes of the LLM judge used in
`evals/judge/judge.py` and the mitigations applied. An LLM judge you
haven't calibrated is a metric you can't defend.

## Failure Modes

### 1. Position Bias

LLM judges tend to favour the first or last option presented in a
multiple-choice evaluation. Studies show up to 10–15% verdict shift
depending on option ordering.

**Mitigation:** `judge.py` randomises the order of `SUPPORTED / NOT
SUPPORTED` options in every prompt. This doesn't eliminate the bias but
prevents it from being systematic across the eval set.

### 2. Verbosity Bias

Longer answers tend to receive higher scores regardless of accuracy.
The judge conflates thoroughness with correctness.

**Mitigation:** The prompt instructs claim-by-claim verification rather
than holistic impression scoring. Each claim is judged independently,
so padding an answer with correct-but-irrelevant detail doesn't inflate
the groundedness score for the claims that matter.

### 3. Self-Preference Bias

When the judge and generator share a model family, the judge
systematically rates its own family's outputs higher. This is measurable
and persistent across prompt variations.

**Mitigation:** The default judge model (`EVAL_JUDGE_MODEL`) is set to a
different provider than the default generator. If both must use the same
provider, the calibration subset quantifies the agreement gap so it can
be stated alongside results.

### 4. Poor Calibration Near the Decision Boundary

LLM judges are least reliable on borderline cases — answers that are
mostly correct but contain one unsupported inference, or answers that
are technically supported but misleadingly framed.

**Mitigation:** The 20-example calibration subset (`calibration.jsonl`)
includes 8 deliberately borderline cases (subtle unit errors, over-
generalisation, fabricated percentages mixed with correct facts). The
judge–human agreement rate on this subset is reported in every eval run,
so reviewers know how much to trust borderline verdicts.

### 5. Anchoring on Expected Answer

When provided with a reference answer, judges tend to penalise correct
paraphrases that differ structurally from the reference. This is
especially pronounced with extractive questions where the reference is
a direct quote.

**Mitigation:** The expected answer is passed as optional context, not
as the ground truth. The prompt's primary instruction is to verify
against the *retrieved context*, not the expected answer.

## Calibration Protocol

1. Run the judge on all 20 calibration examples.
2. Compare judge verdicts to `human_grounded` labels.
3. Compute accuracy and Cohen's kappa.
4. Report both numbers in the eval results JSON.
5. If kappa < 0.6 (below "substantial agreement"), flag the judge as
   unreliable and fall back to heuristic groundedness only.

## What This Does Not Catch

- **Reasoning errors:** The judge checks factual grounding, not logical
  validity. An answer can be grounded in context but draw an invalid
  conclusion.
- **Omission:** The judge checks what's *in* the answer, not what's
  *missing*. Keyword recall from `metrics/retrieval.py` covers this.
- **Hallucination of structure:** A perfectly grounded answer can still
  fail schema conformance. These are separate metrics.
