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

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .semantics.column_roles import ColumnRole
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
    "SUM",
    "State",
    "check_measure",
    "check_rollup",
    "finalize",
    "kind_named",
    "lift",
    "merge",
    "measure_from_declaration",
    "measure_of_role",
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
    #: Whether the finalised values of disjoint parts add up to the whole's (a count, a sum): what makes a total, a
    #: stack or a symbol sized by value honest. A mean, a variance or an extreme of two groups is not their sum.
    parts_sum: bool = False

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
    """A sum over the values that parse. A cell none of whose rows holds a value has NO sum (``None``, as SQL's
    ``SUM``), not a sum of zero: a column a generation lacks, or one that is blank for a month, is missing, and
    reading it as 0 is a claim nobody made. ``None`` is the identity of the merge; a state is stored as a column
    that is null in such a cell."""

    def identity(self) -> State:
        return (None,)  # type: ignore[return-value]

    def lift(self, value: Any) -> State:
        return (_number(value),)  # type: ignore[return-value]

    def merge(self, left: State, right: State) -> State:
        a, b = left[0], right[0]
        return (b,) if a is None else (a,) if b is None else (a + b,)

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
class _Moments(Kind):
    """(n, sum, sum of squares): a mark's exact, mergeable summary.

    The mean and the variance of any union of cells follow from the summed
    states (DESIGN §6.2 of PegaSUS: mark summaries are accumulator states);
    `finalize` projects the mean, and `finalize=False` hands out the state.
    """

    def identity(self) -> State:
        return (0.0, 0.0, 0.0)

    def lift(self, value: Any) -> State:
        number = _number(value)
        return (0.0, 0.0, 0.0) if number is None else (1.0, number, number * number)

    def merge(self, left: State, right: State) -> State:
        return (left[0] + right[0], left[1] + right[1], left[2] + right[2])

    def finalize(self, state: State) -> float | None:
        return None if state[0] == 0 else state[1] / state[0]

    def formula(self, measure: str) -> str:
        return f"{measure}_sum / {measure}_n"


@dataclass(frozen=True, slots=True)
class _LogMoments(Kind):
    """(n, Σ log m, Σ (log m)²) of a positive mark: the sufficient statistics of a log-normal.

    PegaSUS models positive continuous marks (length of stay, cost, birth weight)
    as log-normal per cell (its ARCHITECTURE §4.4); these three sums are all the
    likelihood needs, and they merge by addition. A value that is not positive
    has no logarithm: it is left out of the state, as a blank is, not clipped.
    `finalize` projects the mean of log m (the log of the geometric mean).
    """

    def identity(self) -> State:
        return (0.0, 0.0, 0.0)

    def lift(self, value: Any) -> State:
        number = _number(value)
        if number is None or number <= 0:
            return (0.0, 0.0, 0.0)
        log = math.log(number)
        return (1.0, log, log * log)

    def merge(self, left: State, right: State) -> State:
        return (left[0] + right[0], left[1] + right[1], left[2] + right[2])

    def finalize(self, state: State) -> float | None:
        return None if state[0] == 0 else state[1] / state[0]

    def formula(self, measure: str) -> str:
        return f"{measure}_sumlog / {measure}_n"


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


COUNT = _Count(name="count", state_fields=("n",), needs_field=False, parts_sum=True)
SUM = _Sum(name="sum", state_fields=("sum",), parts_sum=True)
MEAN = _Mean(name="mean", state_fields=("n", "sum"))
MOMENTS = _Moments(name="moments", state_fields=("n", "sum", "sumsq"))
LOGMOMENTS = _LogMoments(name="logmoments", state_fields=("n", "sumlog", "sumsqlog"))
MIN = _Extreme(name="min", state_fields=("min",))
MAX = _Extreme(name="max", state_fields=("max",))

_KINDS: dict[str, Kind] = {k.name: k for k in (COUNT, SUM, MEAN, MOMENTS, LOGMOMENTS, MIN, MAX)}

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
    #: The source columns `lift` reads, summed per row when there are several
    #: -- CNES splits "beds" across the three legacy rollup columns, and a
    #: total that IS the row-wise sum belongs in the declaration, not in a
    #: client stitching three partial measures together. Empty for `count`,
    #: which counts rows.
    source_fields: tuple[str, ...] = ()
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
    fields: tuple[str, ...] = (
        tuple(str(f) for f in source)
        if isinstance(source, (list, tuple))
        else (str(source),) if source else ()
    )
    if kind.needs_field and not fields:
        raise AggregationRefused(
            f"measure {name!r} is a {kind.name} and names no source field"
        )
    if len(fields) > 1 and kind.name != "sum":
        raise AggregationRefused(
            f"measure {name!r} names {len(fields)} fields but is a "
            f"{kind.name}; only `sum` composes row-wise across columns -- a "
            "mean or extreme of a sum of columns is a different statement"
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
        source_fields=fields,
        unit=str(body.get("unit") or ""),
        label=str(body.get("label") or ""),
        additive_over=additive,
        time_reducer=str(reducer) if reducer else None,
        multi_valued=bool(body.get("multi_valued", False)),
    )


def measure_of_role(role: ColumnRole, declared: Sequence[Measure] = ()) -> Measure:
    """The ``(n, sum)`` measure of a quantity a record carries, from its column role (``curation/roles``).

    The roles layer says what the number IS: a quantity (``measure``), in a ``unit``, with the codes that mean "not
    recorded" (``missing``). It says nothing of how the number combines; that is the recipes' ``additive_over`` and
    ``time_reducer`` (`_aggregate.declared_measures`), passed as ``declared``: the measure keeps the axes every one of them
    allows. With none declared the number is a quantity of ONE record (a stay's days, an admission's value, a birth's
    weight) and a record is in one cell of any grouping, so it adds along every axis; only a recipe that declares a stock
    (CNES beds: rooms in a quarter are not rooms x 3) takes an axis away, and `check_rollup` then refuses it with the reason.

    The state is the mean's, ``(n, sum)``: the columns ``<role>_n`` and ``<role>_sum`` (`Measure.state_columns`), never the
    finished mean, which `Measure.formula` derives. Refuses a number that is not a quantity (a coded or packed value, whose
    sums mean nothing, ADR-0154) and a quantity whose "not recorded" values are undeclared, which a sum could not tell from a
    filler (a column the query derives, an age in years, declares none)."""
    if role.kind != "number" or not role.measure:
        what = "a number whose values are codes or packed units" if role.kind == "number" else f"a {role.kind}"
        raise AggregationRefused(f"{role.role} ({role.column}) is not a quantity: it is {what}, and the sum of codes "
                                 "means nothing. Name a role the roles table declares as a measure.")
    if role.missing is None and not role.derived:
        why = f" ({role.missing_unknown})" if role.missing_unknown else ""
        raise AggregationRefused(f"{role.role} ({role.column}) does not declare which of its values mean 'not recorded'{why}; "
                                 "a sum cannot tell a measurement from a filler without it")
    additive = frozenset(AXES)
    reducers: set[str] = set()
    for measure in declared:
        additive &= measure.additive_over
        if measure.time_reducer:
            reducers.add(measure.time_reducer)
    return Measure(name=role.role, kind=MEAN, source_fields=(role.column,), unit=role.unit or "", additive_over=additive,
                   time_reducer=next(iter(reducers)) if len(reducers) == 1 else None, label=role.name or "")


# ---------------------------------------------------------------- operations


def lift(measure: Measure, row: Mapping[str, Any]) -> State:
    if not measure.source_fields:
        return measure.kind.lift(None)
    if len(measure.source_fields) == 1:
        return measure.kind.lift(row.get(measure.source_fields[0]))
    # Row-wise sum across columns; a row where NO column parses stays null.
    total: float | None = None
    for field_name in measure.source_fields:
        value = row.get(field_name)
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        total = number if total is None else total + number
    return measure.kind.lift(total)


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
