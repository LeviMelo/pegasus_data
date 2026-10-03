"""Carrying linkage error into an analysis (docs/plans/linkage-theory.md §6, step T5).

Every probabilistic pair carries ``p_match``: one minus the local false-match
rate at its score, calibrated on the placebo. An analysis on linked data can

- **weight** each linked record by ``p_match`` (``weights``);
- **multiply impute** the links: draw which uncertain pairs are true, analyse
  each draw, and combine (``draws``, ``combine``), so the interval of the final
  estimate widens by the linkage uncertainty instead of treating every link as
  certain.

A pair with ``p_match`` 1.0 is in every draw; one at 0.6 in about six of ten.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc


def weights(pairs: pa.Table) -> pa.Array:
    """``p_match`` of each pair; 1.0 for a pair from a method that carries none."""
    if "p_match" not in pairs.column_names:
        return pa.array(np.ones(pairs.num_rows))
    return pc.fill_null(pairs.column("p_match"), 1.0)


def draws(pairs: pa.Table, n: int = 20, seed: int = 0) -> Iterator[pa.Table]:
    """``n`` plausible link sets: each pair kept with probability ``p_match``."""
    p = weights(pairs).to_numpy(zero_copy_only=False)
    rng = np.random.default_rng(seed)
    for _ in range(n):
        yield pairs.filter(pa.array(rng.random(len(p)) < p))


@dataclass(frozen=True, slots=True)
class Combined:
    estimate: float
    within_variance: float
    between_variance: float
    total_variance: float
    draws: int

    @property
    def standard_error(self) -> float:
        return float(np.sqrt(self.total_variance))


def combine(estimates: list[float], variances: list[float]) -> Combined:
    """Rubin's rules over the analyses of each draw.

    ``variances`` are each draw's sampling variance of its estimate (0.0 when
    the estimate is a count over the whole population).
    """
    m = len(estimates)
    est = np.asarray(estimates, dtype=float)
    within = float(np.mean(variances)) if variances else 0.0
    between = float(est.var(ddof=1)) if m > 1 else 0.0
    return Combined(float(est.mean()), within, between, within + (1 + 1 / m) * between, m)


#: The package-level name (``pegasus_data.link_draws``).
link_draws = draws

__all__ = ["Combined", "combine", "draws", "link_draws", "weights"]
