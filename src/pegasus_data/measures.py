"""The aggregation algebra: what may be combined, and along which axis.

`docs/AGGREGATE_ALGEBRA.md` is the derivation; this is the enforcement.

An aggregate cell holds an **accumulator state**, not a number. A measure is
three functions — ``lift`` turns one observation into a state, ``merge``
combines two states, ``finalize`` turns a state into the number displayed — and
``(state, merge, identity)`` must be a commutative monoid. That is exactly what
makes "combine in any order, in any grouping" give one answer, which is what a
roll-up is.

Storing ``finalize(lift(x))`` destroys the state, and the state is the only
thing that can be merged. Once a mean is written down it can never legitimately
be combined with another. So the artifact holds states and only the display
holds numbers.

Two rules this module exists to enforce, both of which produce a plausible wrong
number when they are not:

**Additivity is per AXIS, not global.** CNES bed counts sum correctly across
municipalities and produce "bed-months" across time. A stock is a thing that
*was the case* at an instant; a flow is a thing that *happened* during an
interval. Only flows accumulate over time. `ledger.aggregation` is a global
claim about a field and is therefore a first approximation, never the answer.

**The grain types the measure.** ``COUNT(*)`` means nothing until you say what a
row is. On CNES.ST — grain ``establishment-month`` — it counts
establishment-months, so ``count(establishment)`` is refused in favour of naming
the honest alternative.

Refusal is the product. Anyone can sum a column.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .semantics.curation import Grain

__all__ = [
    "AXES",
    "AggregationRefused",
    "COUNT",
    "Kind",
    "MAX",
    "MEAN",
    "MIN",
    "Measure",
    "RATIO",
    "SUM",
    "State",
    "check_measure",
    "check_rollup",
    "finalize",
    "kind_named",
    "lift",
    "merge",
    "measure_from_declaration",
]

#: The axes a cell can be rolled up along. Additivity is declared per axis
#: because it genuinely differs per axis; see the module docstring.
AXES: tuple[str, ...] = ("geography", "time", "dimensions")

#: An accumulator state, stored as a fixed tuple of numbers so it lands in
#: Parquet as ordinary columns. `mean` is `(n, sum)`; `count` is `(n,)`.
State = tuple[float, ...]


class AggregationRefused(RuntimeError):
    """A requested combination is not arithmetically valid.

    Raised rather than returning a number, on the same principle as
    `LabelUnavailable`: silently handing back a plausible wrong figure is the
    failure this layer exists to prevent.
    """


# ------------------------------------------------------------------- kinds


@dataclass(frozen=True, slots=True)
class Kind:
    """One accumulator: a commutative monoid plus a projection out of it."""

    name: str
    #: Column suffixes the state occupies. `mean` stores `_n` and `_sum`.
    state_fields: tuple[str, ...]
    #: Whether `lift` needs a source field, or counts rows regardless.
    needs_field: bool = True

    def identity(self) -> State:
        raise NotImplementedError

    def lift(self, value: Any) -> State:
        raise NotImplementedError

    def merge(self, left: State, right: State) -> State:
        raise NotImplementedError

    def finalize(self, state: State) -> float | None:
        raise NotImplementedError

    def formula(self, measure: str) -> str:
        """An expression over this measure's state columns, equal to `finalize`.

        A client that receives state columns over HTTP cannot call `finalize`,
        so the wire carries this string and the client evaluates it generically.
        The default is the single state column; a kind with more than one
        overrides. `test_formula_matches_finalize` checks the two agree for
        every kind, which is what stops them drifting.

        The expression is deliberately restricted to names, `/`, `*` and
        numbers: it is data on a wire, and anything a client would have to
        `eval` unsafely does not belong here.
        """
        return f"{measure}_{self.state_fields[0]}"


def _number(value: Any) -> float | None:
    """DATASUS writes numbers as fixed-width text; blank is absent, not zero."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class _Count(Kind):
    def identity(self) -> State:
        return (0.0,)

    def lift(self, value: Any) -> State:
        return (1.0,)

    def merge(self, left: State, right: State) -> State:
        return (left[0] + right[0],)

    def finalize(self, state: State) -> float | None:
        return state[0]


@dataclass(frozen=True, slots=True)
class _Sum(Kind):
    def identity(self) -> State:
        return (0.0,)

    def lift(self, value: Any) -> State:
        number = _number(value)
        return (0.0,) if number is None else (number,)

    def merge(self, left: State, right: State) -> State:
        return (left[0] + right[0],)

    def finalize(self, state: State) -> float | None:
        return state[0]


@dataclass(frozen=True, slots=True)
class _Mean(Kind):
    def identity(self) -> State:
        return (0.0, 0.0)

    def lift(self, value: Any) -> State:
        number = _number(value)
        # An absent value contributes nothing rather than a zero: a blank
        # DIAS_PERM is a stay of unknown length, not a stay of no days, and
        # counting it as 0 drags the mean down invisibly.
        return (0.0, 0.0) if number is None else (1.0, number)

    def merge(self, left: State, right: State) -> State:
        return (left[0] + right[0], left[1] + right[1])

    def finalize(self, state: State) -> float | None:
        # 0/0 is undefined, NOT zero. An empty cell must not display a mean of
        # nought; that is a claim nobody made.
        return None if state[0] == 0 else state[1] / state[0]

    def formula(self, measure: str) -> str:
        return f"{measure}_sum / {measure}_n"


@dataclass(frozen=True, slots=True)
class _Ratio(Kind):
    """Numerator and denominator kept apart, so rates recombine correctly.

    The rate of two municipalities together is the summed numerator over the
    summed denominator — never the mean of the two rates.
    """

    def identity(self) -> State:
        return (0.0, 0.0)

    def lift(self, value: Any) -> State:
        number = _number(value)
        return (0.0, 0.0) if number is None else (number, 1.0)

    def merge(self, left: State, right: State) -> State:
        return (left[0] + right[0], left[1] + right[1])

    def finalize(self, state: State) -> float | None:
        return None if state[1] == 0 else state[0] / state[1]

    def formula(self, measure: str) -> str:
        return f"{measure}_num / {measure}_den"


@dataclass(frozen=True, slots=True)
class _Extreme(Kind):
    """`min` or `max`, discriminated by `name`."""

    def identity(self) -> State:
        return (float("inf") if self.name == "min" else float("-inf"),)

    def lift(self, value: Any) -> State:
        number = _number(value)
        return self.identity() if number is None else (number,)

    def merge(self, left: State, right: State) -> State:
        return (min(left[0], right[0]),) if self.name == "min" else (max(left[0], right[0]),)

    def finalize(self, state: State) -> float | None:
        return None if state[0] in (float("inf"), float("-inf")) else state[0]


COUNT = _Count(name="count", state_fields=("n",), needs_field=False)
SUM = _Sum(name="sum", state_fields=("sum",))
MEAN = _Mean(name="mean", state_fields=("n", "sum"))
RATIO = _Ratio(name="ratio", state_fields=("num", "den"))
MIN = _Extreme(name="min", state_fields=("min",))
MAX = _Extreme(name="max", state_fields=("max",))

_KINDS: dict[str, Kind] = {k.name: k for k in (COUNT, SUM, MEAN, RATIO, MIN, MAX)}

#: Asked for often and impossible to merge exactly. There is no bounded state
#: and associative operation that yields an exact median of a union from
#: summaries of the parts, so an artifact cannot carry one. A mergeable sketch
#: (t-digest, KLL) would be an approximation and must be labelled as one.
_NOT_MERGEABLE = frozenset({"median", "percentile", "quantile", "p50", "p95", "mode"})


def kind_named(name: str) -> Kind:
    key = str(name).strip().lower()
    if key in _NOT_MERGEABLE:
        raise AggregationRefused(
            f"{key!r} has no finite-state associative merge, so it cannot be "
            "stored in an aggregate and combined later. Compute it from "
            "microdata at the grain you need, or ask for a mergeable sketch and "
            "accept a labelled approximation."
        )
    if key not in _KINDS:
        raise AggregationRefused(
            f"unknown measure kind {name!r}; known kinds are {sorted(_KINDS)}"
        )
    return _KINDS[key]


# ----------------------------------------------------------------- measures


@dataclass(frozen=True, slots=True)
class Measure:
    """One column of an aggregate, and the rules for combining it."""

    name: str
    kind: Kind
    #: The source column `lift` reads. None for `count`, which counts rows.
    source_field: str | None = None
    #: What one increment counts — `admission`, `death`, `brl`. Checked against
    #: the dataset's grain, because `count` of anything else is a different
    #: measure wearing the same name.
    unit: str = ""
    #: Axes this may be summed along. A stock omits `time`.
    additive_over: frozenset[str] = field(default_factory=lambda: frozenset(AXES))
    #: How to combine across time when `time` is not additive: mean | last | max.
    time_reducer: str | None = None
    #: Set when the source column holds several values per row, which makes
    #: counts of the grain non-additive along any dimension built from it.
    multi_valued: bool = False
    #: What to call this on screen. Empty means the interface falls back to the
    #: name, which is honest but is a column identifier rather than a label.
    label: str = ""

    @property
    def is_semi_additive(self) -> bool:
        return bool(set(AXES) - set(self.additive_over))

    def state_columns(self) -> tuple[str, ...]:
        """Physical column names this measure occupies in the artifact."""
        return tuple(f"{self.name}_{suffix}" for suffix in self.kind.state_fields)

    def formula(self) -> str:
        """The expression over `state_columns()` that a client evaluates."""
        return self.kind.formula(self.name)


def measure_from_declaration(name: str, body: Mapping[str, Any]) -> Measure:
    """Build a `Measure` from one entry of a spec's `measures:` block."""
    kind = kind_named(str(body.get("kind", "count")))
    source = body.get("field")
    if kind.needs_field and not source:
        raise AggregationRefused(
            f"measure {name!r} is a {kind.name} and names no source field"
        )
    declared = body.get("additive_over")
    if declared is None:
        additive = frozenset(AXES)
    else:
        additive = frozenset(str(a) for a in declared)
        unknown = additive - set(AXES)
        if unknown:
            raise AggregationRefused(
                f"measure {name!r} declares additivity over unknown axes "
                f"{sorted(unknown)}; the axes are {list(AXES)}"
            )
    reducer = body.get("time_reducer")
    if "time" not in additive and not reducer:
        raise AggregationRefused(
            f"measure {name!r} is not additive over time and names no "
            "time_reducer. A stock quantity summed across months yields "
            "'thing-months'; say mean, last or max instead."
        )
    return Measure(
        name=name,
        kind=kind,
        source_field=str(source) if source else None,
        unit=str(body.get("unit") or ""),
        label=str(body.get("label") or ""),
        additive_over=additive,
        time_reducer=str(reducer) if reducer else None,
        multi_valued=bool(body.get("multi_valued", False)),
    )


# ---------------------------------------------------------------- operations


def lift(measure: Measure, row: Mapping[str, Any]) -> State:
    if measure.source_field is None:
        return measure.kind.lift(None)
    return measure.kind.lift(row.get(measure.source_field))


def merge(measure: Measure, left: State, right: State) -> State:
    return measure.kind.merge(left, right)


def finalize(measure: Measure, state: State) -> float | None:
    return measure.kind.finalize(state)


def merge_all(measure: Measure, states: Sequence[State]) -> State:
    total = measure.kind.identity()
    for state in states:
        total = measure.kind.merge(total, state)
    return total


# ----------------------------------------------------------------- refusals


def check_rollup(measure: Measure, axis: str) -> None:
    """Refuse a roll-up the measure's additivity does not permit."""
    if axis not in AXES:
        raise AggregationRefused(f"unknown axis {axis!r}; the axes are {list(AXES)}")
    if axis in measure.additive_over:
        return
    hint = (
        f" Use time_reducer={measure.time_reducer!r} instead."
        if axis == "time" and measure.time_reducer
        else ""
    )
    raise AggregationRefused(
        f"{measure.name!r} is not additive over {axis}: it is a stock, and "
        f"summing it across {axis} produces '{measure.unit or 'unit'}-{axis}' "
        f"rather than {measure.unit or 'the quantity'}.{hint}"
    )


def check_measure(measure: Measure, grain: Grain) -> None:
    """Refuse a measure whose unit contradicts what one row of the source IS.

    The case this exists for: CNES.ST is one row per establishment per month, so
    `count` there counts establishment-months. Naming that measure
    "establishments" is not a rounding error — it is three times the answer for
    a quarter, and it looks entirely reasonable.
    """
    if measure.kind is not COUNT or not grain.analysable:
        return
    counts = grain.counts()
    unit = measure.unit.strip().lower()
    if not unit or unit == counts.lower():
        return
    if grain.is_period_bearing and unit in {c.lower() for c in grain.entity_components}:
        raise AggregationRefused(
            f"{measure.name!r} counts {measure.unit!r}, but one row of this "
            f"dataset is a {counts!r}. Counting rows gives {counts}s, not "
            f"{measure.unit}s — over a quarter it is roughly three times the "
            f"figure. Declare unit={counts!r}, or use a distinct-count of "
            f"{measure.unit!r}, which needs a mergeable sketch rather than a sum."
        )


def check_dimension(measure: Measure, dimension_is_multi_valued: bool) -> None:
    """Refuse a grain-count rolled up along a multi-valued dimension.

    `CODANOMAL` holds up to five ICD-10 codes. A birth with three anomalies sits
    in three cells, so summing across anomalies triple-counts the birth: the
    dimension is a relation, not a partition. Counting *mentions* is additive
    and is a different, legitimate measure — the caller has to say which.
    """
    if dimension_is_multi_valued and measure.kind is COUNT:
        raise AggregationRefused(
            f"{measure.name!r} counts one row each, and this dimension holds "
            "several values per row — so a row lands in several cells and "
            "summing over them counts it more than once. Count mentions "
            "instead, which is additive, and say so in the name."
        )
