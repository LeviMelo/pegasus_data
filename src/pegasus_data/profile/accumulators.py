"""Per-field streaming statistics.

A port of the prior ``FieldAccumulator`` — which was one of the sound parts of
the old implementation — reworked in two ways:

* it consumes Arrow arrays in bulk rather than Python values one at a time, so
  profiling a 113-column file is not slower than downloading it (P3); and
* it keeps the *distributional* summaries the semantic detectors need (first-
  character histogram, numeric-tail density and contiguity, length histogram),
  because per-value regex matching cannot separate an age code from a diagnosis
  code and pretending otherwise is defect D5.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from ..decode.base import FieldMeta

#: Tokens that are physically absent, as opposed to coded-as-missing. Sentinel
#: codes such as "9" or "9999" are per-field and ledger-driven; they are NOT here.
NULL_TOKENS = frozenset({"", " ", "NA", "N/A", "NULL", "NONE", "NAN", "."})


@dataclass(slots=True)
class FieldStats:
    """The evidence a semantic verdict is allowed to rest on."""

    name: str
    non_null: int = 0
    nulls: int = 0
    distinct_count: int = 0
    distinct_truncated: bool = False
    top_values: list[tuple[str, int]] = field(default_factory=list)
    lengths: dict[int, int] = field(default_factory=dict)
    first_char_hist: dict[str, int] = field(default_factory=dict)
    first_char_entropy: float = 0.0
    numeric_rate: float = 0.0
    digit_rate: float = 0.0
    alpha_rate: float = 0.0
    numeric_min: float | None = None
    numeric_max: float | None = None
    numeric_mean: float | None = None
    numeric_std: float | None = None
    quantiles: dict[int, float] = field(default_factory=dict)
    tail_density: float | None = None      # distinct numeric tails / span
    tail_contiguity: float | None = None   # fraction of the span actually present
    tail_min: int | None = None
    tail_max: int | None = None
    leading_zero_rate: float = 0.0         # zero-padded ⇒ a code, not a measure
    physical_type: str | None = None
    width: int | None = None
    decimals: int | None = None

    @property
    def total(self) -> int:
        return self.non_null + self.nulls

    @property
    def missingness(self) -> float | None:
        return self.nulls / self.total if self.total else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "non_null": self.non_null,
            "nulls": self.nulls,
            "missingness": self.missingness,
            "distinct_count": self.distinct_count,
            "distinct_truncated": self.distinct_truncated,
            "lengths": self.lengths,
            "first_char_hist": dict(sorted(self.first_char_hist.items(), key=lambda kv: -kv[1])[:32]),
            "first_char_entropy": round(self.first_char_entropy, 4),
            "numeric_rate": round(self.numeric_rate, 4),
            "digit_rate": round(self.digit_rate, 4),
            "alpha_rate": round(self.alpha_rate, 4),
            "numeric_min": self.numeric_min,
            "numeric_max": self.numeric_max,
            "numeric_mean": self.numeric_mean,
            "numeric_std": self.numeric_std,
            "quantiles": self.quantiles,
            "tail_density": self.tail_density,
            "tail_contiguity": self.tail_contiguity,
            "tail_min": self.tail_min,
            "tail_max": self.tail_max,
            "leading_zero_rate": round(self.leading_zero_rate, 4),
            "physical_type": self.physical_type,
            "width": self.width,
            "decimals": self.decimals,
        }


class FieldAccumulator:
    """Streams one column's statistics across an arbitrary number of batches."""

    def __init__(self, meta: FieldMeta, *, max_distinct: int = 50_000, top_values: int = 200) -> None:
        self.meta = meta
        self.name = meta.name
        self.max_distinct = max_distinct
        self.top_values = top_values
        self.counter: Counter[str] = Counter()
        self.counter_truncated = False
        self.non_null = 0
        self.nulls = 0
        self.lengths: Counter[int] = Counter()
        self.first_chars: Counter[str] = Counter()
        self.digit_count = 0
        self.alpha_count = 0
        self.numeric_count = 0
        self.leading_zero_count = 0
        self._num_sum = 0.0
        self._num_sumsq = 0.0
        self._num_min: float | None = None
        self._num_max: float | None = None
        self._num_reservoir: list[float] = []
        self._reservoir_cap = 100_000

    # ------------------------------------------------------------------ input

    def add_array(self, array: pa.Array | pa.ChunkedArray) -> None:
        """Fold one Arrow column chunk into the running statistics."""
        if isinstance(array, pa.ChunkedArray):
            for chunk in array.chunks:
                self.add_array(chunk)
            return
        if array.type != pa.string():
            try:
                array = array.cast(pa.string())
            except (pa.ArrowInvalid, pa.ArrowNotImplementedError):
                array = pa.array([None if v is None else str(v) for v in array.to_pylist()], type=pa.string())

        total = len(array)
        null_count = array.null_count
        # Whitespace-only and the conventional null tokens count as absent.
        trimmed = pc.utf8_trim_whitespace(array)
        blank = pc.is_in(trimmed, value_set=pa.array(sorted(NULL_TOKENS), type=pa.string()))
        blank_count = int(pc.sum(pc.cast(pc.fill_null(blank, False), pa.int64())).as_py() or 0)
        self.nulls += null_count + blank_count
        self.non_null += total - null_count - blank_count

        values = pc.filter(trimmed, pc.and_(pc.is_valid(trimmed), pc.invert(pc.fill_null(blank, True))))
        if len(values) == 0:
            return

        # Value frequencies, with a bounded counter: once the cap is passed we
        # keep the head and mark the count approximate rather than lie about it.
        if not self.counter_truncated:
            table = values.value_counts()
            for entry in table:
                self.counter[entry["values"].as_py()] += entry["counts"].as_py()
            if len(self.counter) > self.max_distinct:
                self.counter = Counter(dict(self.counter.most_common(self.max_distinct)))
                self.counter_truncated = True
        else:
            table = values.value_counts()
            for entry in table:
                key = entry["values"].as_py()
                if key in self.counter:
                    self.counter[key] += entry["counts"].as_py()

        lengths = pc.utf8_length(values)
        for entry in lengths.value_counts():
            self.lengths[int(entry["values"].as_py())] += int(entry["counts"].as_py())

        firsts = pc.utf8_slice_codeunits(values, 0, 1)
        for entry in firsts.value_counts():
            key = entry["values"].as_py()
            if key is not None:
                self.first_chars[key] += int(entry["counts"].as_py())

        digits = pc.utf8_is_numeric(values)
        self.digit_count += int(pc.sum(pc.cast(pc.fill_null(digits, False), pa.int64())).as_py() or 0)
        alphas = pc.utf8_is_alpha(values)
        self.alpha_count += int(pc.sum(pc.cast(pc.fill_null(alphas, False), pa.int64())).as_py() or 0)

        # Zero padding is the cleanest signal that a numeric-looking column is a
        # code rather than a measure: '0303140151' is a procedure, not a count.
        padded = pc.fill_null(pc.match_substring_regex(values, r"^0\d"), False)
        self.leading_zero_count += int(pc.sum(pc.cast(padded, pa.int64())).as_py() or 0)

        # Cast only what already looks numeric: Arrow's cast raises on the first
        # non-numeric token, and a diagnosis column full of 'O48' must not abort
        # the profile of the file it lives in.
        looks_numeric = pc.fill_null(pc.match_substring_regex(values, r"^[+-]?\d+([.,]\d+)?$"), False)
        numeric_tokens = pc.filter(values, looks_numeric)
        if len(numeric_tokens):
            numeric = pc.cast(
                pc.replace_substring_regex(numeric_tokens, r"^([+-]?\d+),(\d+)$", r"\1.\2"),
                pa.float64(),
            )
        else:
            numeric = pa.array([], type=pa.float64())
        valid = pc.drop_null(numeric)
        n_valid = len(valid)
        if n_valid:
            self.numeric_count += n_valid
            self._num_sum += float(pc.sum(valid).as_py() or 0.0)
            self._num_sumsq += float(pc.sum(pc.multiply(valid, valid)).as_py() or 0.0)
            vmin = float(pc.min(valid).as_py())
            vmax = float(pc.max(valid).as_py())
            self._num_min = vmin if self._num_min is None else min(self._num_min, vmin)
            self._num_max = vmax if self._num_max is None else max(self._num_max, vmax)
            if len(self._num_reservoir) < self._reservoir_cap:
                room = self._reservoir_cap - len(self._num_reservoir)
                self._num_reservoir.extend(valid.slice(0, room).to_pylist())

    def add_table(self, table: pa.Table) -> None:
        if self.name in table.schema.names:
            self.add_array(table.column(self.name))

    # ----------------------------------------------------------------- output

    def stats(self) -> FieldStats:
        s = FieldStats(
            name=self.name,
            non_null=self.non_null,
            nulls=self.nulls,
            distinct_count=len(self.counter),
            distinct_truncated=self.counter_truncated,
            top_values=self.counter.most_common(self.top_values),
            lengths=dict(sorted(self.lengths.items())),
            first_char_hist=dict(self.first_chars),
            physical_type=self.meta.physical_type,
            width=self.meta.width,
            decimals=self.meta.decimals,
        )
        s.first_char_entropy = _entropy(self.first_chars)
        if self.non_null:
            s.numeric_rate = self.numeric_count / self.non_null
            s.digit_rate = self.digit_count / self.non_null
            s.alpha_rate = self.alpha_count / self.non_null
            s.leading_zero_rate = self.leading_zero_count / self.non_null
        if self.numeric_count:
            mean = self._num_sum / self.numeric_count
            s.numeric_mean = mean
            variance = max(0.0, self._num_sumsq / self.numeric_count - mean * mean)
            s.numeric_std = math.sqrt(variance)
            s.numeric_min = self._num_min
            s.numeric_max = self._num_max
            s.quantiles = _quantiles(sorted(self._num_reservoir))
        _fill_tail_shape(s, self.counter)
        return s


def _entropy(counter: Counter[str]) -> float:
    """Shannon entropy in bits over the observed symbol distribution.

    This is the statistic that separates a DATASUS age field (first character
    drawn from ~4 symbols: A/M/D/H) from a diagnosis field (~20 ICD chapters).
    """
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    acc = 0.0
    for count in counter.values():
        if count <= 0:
            continue
        p = count / total
        acc -= p * math.log2(p)
    return acc


def _quantiles(values: list[float]) -> dict[int, float]:
    if not values:
        return {}
    out: dict[int, float] = {}
    n = len(values)
    for q in (1, 5, 25, 50, 75, 95, 99):
        idx = min(n - 1, max(0, int(round((q / 100) * (n - 1)))))
        out[q] = values[idx]
    return out


def _fill_tail_shape(stats: FieldStats, counter: Counter[str]) -> None:
    """Measure the numeric tail after a leading letter.

    A DATASUS unit-prefixed age (``A020`` = 20 years) has a **dense, contiguous**
    tail running 0…120; an ICD-10 code (``A020`` = salmonellosis subcategory) has
    a **sparse** one. This is the separating statistic the brief calls for, and
    it is stored so a downstream consumer can re-audit the verdict without
    re-reading the raw file.
    """
    tails: Counter[int] = Counter()
    for value, count in counter.items():
        if len(value) < 2 or not value[0].isalpha():
            continue
        tail = value[1:]
        if not tail.isdigit():
            continue
        tails[int(tail)] += count
    if len(tails) < 5:
        return
    lo, hi, inside = robust_tail_span(tails)
    if lo is None or hi is None:
        return
    span = hi - lo + 1
    stats.tail_min = lo
    stats.tail_max = hi
    stats.tail_density = inside / span if span else None
    stats.tail_contiguity = inside / span if span else None


def robust_tail_span(tails: Counter[int], *, trim: float = 0.005) -> tuple[int | None, int | None, int]:
    """Span of the numeric tail, ignoring the outer ``trim`` of observed mass.

    DATASUS writes sentinels into age fields — ``A999``, ``4999`` for unknown.
    A raw min/max would stretch the span to 0–999 and drive the density statistic
    to near zero, which would then let an age field be mistaken for a diagnosis
    field. Trimming by *mass* rather than by value keeps the real run intact while
    dropping the handful of sentinel rows.
    """
    total = sum(tails.values())
    if total <= 0:
        return None, None, 0
    ordered = sorted(tails.items())
    cutoff = total * trim
    cumulative = 0
    lo: int | None = None
    for value, count in ordered:
        cumulative += count
        if cumulative >= cutoff:
            lo = value
            break
    cumulative = 0
    hi: int | None = None
    for value, count in reversed(ordered):
        cumulative += count
        if cumulative >= cutoff:
            hi = value
            break
    if lo is None or hi is None or hi < lo:
        return None, None, 0
    inside = sum(1 for v in tails if lo <= v <= hi)
    return lo, hi, inside
