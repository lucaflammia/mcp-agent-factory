"""Statistical utilities for evaluation metrics.

Wilson confidence intervals and paired comparison tests for small-n eval sets.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class WilsonInterval:
  """Wilson score confidence interval for a binomial proportion."""
  proportion: float
  lower: float
  upper: float
  n: int
  successes: int
  z: float

  def __str__(self) -> str:
    return f"{self.proportion:.1%} [{self.lower:.1%}, {self.upper:.1%}] (n={self.n})"

  def to_dict(self) -> dict:
    return {
      "proportion": round(self.proportion, 4),
      "lower": round(self.lower, 4),
      "upper": round(self.upper, 4),
      "n": self.n,
      "successes": self.successes,
    }


def wilson_ci(successes: int, n: int, confidence: float = 0.95) -> WilsonInterval:
  """Compute Wilson score interval for a binomial proportion.

  Preferred over the normal approximation for small n because it never
  produces intervals outside [0, 1] and has better coverage properties.

  Args:
    successes: Number of positive outcomes.
    n: Total number of trials.
    confidence: Confidence level (default 0.95 for 95% CI).

  Returns:
    WilsonInterval with proportion, lower, upper bounds.
  """
  if n == 0:
    return WilsonInterval(0.0, 0.0, 1.0, 0, 0, 0.0)

  z = _z_score(confidence)
  p_hat = successes / n
  denominator = 1 + z * z / n
  centre = p_hat + z * z / (2 * n)
  spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n)

  lower = max(0.0, (centre - spread) / denominator)
  upper = min(1.0, (centre + spread) / denominator)

  return WilsonInterval(
    proportion=p_hat,
    lower=lower,
    upper=upper,
    n=n,
    successes=successes,
    z=z,
  )


def minimum_detectable_effect(n: int, confidence: float = 0.95) -> float:
  """Estimate the minimum detectable effect for the current sample size.

  With n=50, changes smaller than this are indistinguishable from noise.
  """
  if n == 0:
    return 1.0
  z = _z_score(confidence)
  return z * math.sqrt(0.25 / n) * 2


def mcnemar_test(
  wins_a: int, wins_b: int
) -> dict:
  """McNemar's test for paired nominal data.

  Compares two systems on the same examples. Only discordant pairs matter:
  - wins_a: examples where A is correct and B is wrong
  - wins_b: examples where B is correct and A is wrong

  Returns dict with chi2, p_value, and significant flag.
  """
  total_discordant = wins_a + wins_b
  if total_discordant == 0:
    return {"chi2": 0.0, "p_value": 1.0, "significant": False, "n_discordant": 0}

  chi2 = (abs(wins_a - wins_b) - 1) ** 2 / total_discordant
  p_value = _chi2_survival(chi2, df=1)

  return {
    "chi2": round(chi2, 4),
    "p_value": round(p_value, 4),
    "significant": p_value < 0.05,
    "n_discordant": total_discordant,
  }


def _z_score(confidence: float) -> float:
  """Approximate z-score for common confidence levels."""
  table = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
  if confidence in table:
    return table[confidence]
  from math import erfinv
  return math.sqrt(2) * erfinv(confidence)


def _chi2_survival(x: float, df: int = 1) -> float:
  """Approximate chi-squared survival function (1 - CDF) for df=1.

  Uses the complementary error function. Avoids scipy dependency.
  """
  if df != 1:
    raise ValueError("Only df=1 supported")
  return math.erfc(math.sqrt(x / 2))
