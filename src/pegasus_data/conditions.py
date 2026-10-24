"""Record conditions: a topic that is a CONDITION on a record's typed fields, written on roles (ADR-0193).

Low birth weight is the births whose weight is under 2,500 g, an infant death a death at an age under one year, a
caesarean birth the births whose delivery is the caesarean's code. None is a set of codes, so ``rows=`` (code prefixes)
cannot say it. A condition is a list of clauses, ANDed, each on a ROLE of ``curation/roles/<dataset>.yml``, never on a
column: the same role is another column in another layout (a birth's gestation is ``GESTACAO`` before 2010, its weeks
``SEMAGESTAC`` from then)::

    [{"role": "birth.weight", "op": "<", "value": 2500},
     {"role": "birth.delivery", "in": ["2"]}]                 # the operator may be the key itself
    [{"role": "deceased.age_years", "op": "<", "value": 28, "unit": "days"}]

``op`` is one of ``<  <=  >  >=  ==  in  not in``. ``unit`` (days, weeks, months, years) restates a value in time for a
role measured in years; without it the value is in the role's own unit (``birth.weight``: grams).

Three values, never two. A clause is true, false, or UNKNOWN, and a record is unknown when no clause is false and some
cannot be told (Kleene's AND). A clause is unknown where the role's column holds no valid value:

* a number is read from the text as filed (a decimal comma is accepted), and the role's declared ``missing`` codes and
  values outside its declared ``domain`` are not measurements: a weight of 9999 is not "over 2,500", nor is 0000 "under";
* a category is matched as filed, exact width, never padded; a blank value and the role's ``missing`` codes are unknown
  (a delivery filed 9 is not "not a caesarean");
* the role is carried by no column in the record's year (SINASC's gestation weeks before 2010), or the layout of its
  family lacks the column.

Only records for which the condition is false leave the result. The unknown ones are counted apart (``QueryReport
.condition``, the table's ``CONDITION`` metadata, ``count_events``' ``unknown`` column) so a consumer reports how many
records the condition could not decide. A number is compared as the role's declared unit says; an age is the role
pegasus_data derives in years from the source's coded age (`_age`, ADR-0070): ``deceased.age_years``,
``patient.age_years``. A role that no declaration of the dataset carries raises, and a clause that is
ambiguous (two columns of one role in the same year) raises.

Raw columns are tested in the lake's scan (the records not false are read), a derived one (an age) after the read; both
before anything is rendered, so a label never takes the place of the code a clause tests.

The two readings a clause rests on are functions of their own, shared with whatever else reads a role's column:
`role_column` (the column that carries a role in a year) and `measurement` (a measure's text as a number, with what is
recorded and what is a measurement). `proximity.care_flows(measure=)` sums with them (ADR-0201).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from .semantics.column_roles import ColumnRole, declared_columns

__all__ = ["CONDITION", "CONDITION_META", "Clause", "Condition", "condition_report", "measurement", "prepare", "role_column"]

#: The column that carries a record's three-valued answer between the read and the result (True: satisfies, null:
#: unknown; the records that do not satisfy are already out). Internal: it never reaches a caller of ``query``.
CONDITION = "_condition"
#: Schema-metadata key a result carries when a condition was applied: JSON ``{"clauses", "satisfied", "unknown", "unit"}``.
CONDITION_META = b"pegasus.condition"

OPS = ("<", "<=", ">", ">=", "==", "in", "not in")
_ORDER = ("<", "<=", ">", ">=")
_OP_NAMES = {"not_in": "not in", "=": "==", "eq": "=="}
_TIME_UNITS = ("days", "weeks", "months", "years")
#: A decimal number as the files write it: digits, optionally a point or a comma and digits.
_NUMBER = r"^\d+([.,]\d+)?$"
_TRUE, _FALSE = pa.scalar(True), pa.scalar(False)
_UNKNOWN = pa.scalar(None, pa.bool_())


@dataclass(frozen=True, slots=True)
class Clause:
    """One clause: ``role op value``, ``value`` a number, a code, or a tuple of them (``in``, ``not in``)."""

    role: str
    op: str
    value: float | str | tuple[float, ...] | tuple[str, ...]
    unit: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"role": self.role, "op": self.op,
                "value": list(self.value) if isinstance(self.value, tuple) else self.value,
                **({"unit": self.unit} if self.unit else {})}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _clause(spec: Any, i: int) -> Clause:
    if isinstance(spec, Clause):
        return spec
    where = f"condition[{i}]"
    if not isinstance(spec, Mapping):
        raise ValueError(f"{where}: a clause is a mapping with a role and an operator, not {spec!r}")
    keys = {str(k): k for k in spec}
    unknown = sorted(set(keys) - {"role", "op", "value", "unit", *OPS, *_OP_NAMES})
    if unknown:
        raise ValueError(f"{where}: unknown keys {unknown}: a misspelt key would be silently ignored")
    role = spec.get("role")
    if not isinstance(role, str) or not role.strip():
        raise ValueError(f"{where}: names no role (<entity>.<property>, e.g. birth.weight)")
    named = [k for k in keys if k in OPS or k in _OP_NAMES]
    if "op" in spec:
        if named:
            raise ValueError(f"{where}: the operator is given twice ('op' and {named[0]!r})")
        if "value" not in spec:
            raise ValueError(f"{where}: operator {spec['op']!r} has no 'value'")
        op, value = str(spec["op"]).strip().lower(), spec["value"]
    elif len(named) == 1:
        op, value = named[0], spec[keys[named[0]]]
    else:
        raise ValueError(f"{where}: needs exactly one operator ('op' and 'value', or one of {list(OPS)} as a key)")
    op = _OP_NAMES.get(op, op)
    if op not in OPS:
        raise ValueError(f"{where}: operator {op!r} is not one of {list(OPS)}")
    unit = spec.get("unit")
    if unit is not None and unit not in _TIME_UNITS:
        raise ValueError(f"{where}: unit {unit!r} is not one of {list(_TIME_UNITS)}")
    if op in ("in", "not in"):
        if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set, frozenset)) or not value:
            raise ValueError(f"{where}: '{op}' takes a non-empty list")
        items = tuple(dict.fromkeys(sorted(value, key=str) if isinstance(value, (set, frozenset)) else value))
        if not (all(isinstance(v, str) for v in items) or all(_number(v) for v in items)):
            raise ValueError(f"{where}: '{op}' takes codes (strings, as filed) or numbers, not a mixture: {list(items)}")
        value = tuple(float(v) if _number(v) else v for v in items)
    elif isinstance(value, str):
        if op in _ORDER:
            raise ValueError(f"{where}: '{op}' compares numbers; {value!r} is a code")
    elif _number(value):
        value = float(value)
    else:
        raise ValueError(f"{where}: the value of '{op}' is a number or a code, not {value!r}")
    if unit is not None and (isinstance(value, str) or (isinstance(value, tuple) and value and isinstance(value[0], str))):
        raise ValueError(f"{where}: a unit goes with a number")
    return Clause(role.strip(), op, value, unit)


@dataclass(frozen=True, slots=True)
class Bound:
    """A clause on the column of one dataset and year that carries its role."""

    clause: Clause
    role: ColumnRole
    #: a number (compared as a number) or a category (compared as filed)
    numeric: bool
    #: made by the query from the source's coded age, not filed
    derived: bool
    #: the clause's value in the role's own unit (numbers) or the codes (categories)
    operand: tuple[float, ...] | tuple[str, ...]

    @property
    def column(self) -> str:
        return self.role.column


def _in_role_unit(value: float, unit: str | None, role: ColumnRole, where: str) -> float:
    """``value`` in ``role``'s own unit. A time restated for a role in years uses the converter's constants
    (`_age`), the way the age was made, so that 28 days is exactly where a 28-day age ends."""
    if unit is None or unit == role.unit:
        return value
    if role.unit == "years" and unit in ("days", "weeks", "months"):
        from ._age import _DAY, _MONTH

        return {"days": value * _DAY, "weeks": (value * 7) * _DAY, "months": value * _MONTH}[unit]
    raise ValueError(f"{where}: unit {unit!r} cannot restate {role.role}, which is measured in {role.unit or 'no declared unit'}")


def _candidates(columns: Sequence[ColumnRole], role: str) -> list[ColumnRole]:
    return [c for c in columns if c.role == role or role in c.also]


def _covers(column: ColumnRole, year: int | None) -> bool:
    lo, hi = column.years
    return year is None or ((lo is None or lo <= year) and (hi is None or year <= hi))


def role_column(columns: Sequence[ColumnRole], role: str, year: int | None, where: str) -> ColumnRole | None:
    """The column of ``columns`` that carries ``role`` in ``year`` (None: any declared span), or None when no column does
    (the role sits on another column in another layout). Two columns of one role in one year raise, ``where`` leading the
    message: the role tables must name one column for it, or its years must not overlap."""
    found = [c for c in _candidates(columns, role) if _covers(c, year)]
    if len(found) > 1:
        raise ValueError(f"{where} files the role in {[c.column for c in found]}"
                         f"{f' in {year}' if year is not None else ''}: the role tables must name one column "
                         "for it, or its years must not overlap")
    return found[0] if found else None


def _is_number(role: ColumnRole) -> bool:
    """A number compared as a number: a quantity (``measure``), not a coded or packed one (``age_coded``, a clock time)."""
    return role.kind == "number" and bool(role.measure)


class Condition:
    """A validated condition on one dataset: its clauses, and what they read."""

    def __init__(self, dataset: str, clauses: tuple[Clause, ...]) -> None:
        self.dataset = dataset
        self.clauses = clauses
        self._columns = declared_columns(dataset)
        for i, clause in enumerate(clauses):
            self._check(clause, f"condition[{i}] ({clause.role})")

    # ------------------------------------------------------------------ declaration

    def _check(self, clause: Clause, where: str) -> None:
        found = _candidates(self._columns, clause.role)
        if not found:
            import difflib

            roles = sorted({c.role for c in self._columns} | {a for c in self._columns for a in c.also})
            near = difflib.get_close_matches(clause.role, roles, n=5, cutoff=0.5)
            raise ValueError(f"{where}: {self.dataset} declares no column with the role {clause.role!r}"
                             + (f"; closest: {', '.join(near)}" if near else f"; it declares {len(roles)} roles"))
        if len({_is_number(c) for c in found}) > 1:
            raise ValueError(f"{where}: the columns {[c.column for c in found]} are of different kinds")
        for role in found:
            self._operand(clause, role, where)

    def _operand(self, clause: Clause, role: ColumnRole, where: str) -> tuple[float, ...] | tuple[str, ...]:
        """The clause's operand for ``role``, checked against what the role is."""
        raw = clause.value if isinstance(clause.value, tuple) else (clause.value,)
        if _is_number(role):
            if not all(isinstance(v, float) for v in raw):
                raise ValueError(f"{where}: {role.role} ({role.column}) is a number; give numbers, not codes {list(raw)}")
            if not role.derived and role.missing is None:
                raise ValueError(
                    f"{where}: {role.role} ({role.column}) does not declare which of its values mean 'not recorded'"
                    f"{' (' + role.missing_unknown + ')' if role.missing_unknown else ''}; a condition cannot tell a "
                    "measurement from a filler without it")
            return tuple(_in_role_unit(v, clause.unit, role, where) for v in raw)
        if role.kind in ("date", "identifier"):
            raise ValueError(f"{where}: {role.role} ({role.column}) has kind {role.kind}; a condition tests a number or a category")
        if role.kind == "number" and clause.op in _ORDER:
            raise ValueError(f"{where}: {role.role} ({role.column}) holds coded numbers (a unit packed with the value), not a "
                             "quantity: use the role the query derives from it (an age: deceased.age_years, patient.age_years)")
        if clause.op in _ORDER:
            raise ValueError(f"{where}: {role.role} ({role.column}) is a category; an order between codes means nothing "
                             "(use ==, in, not in)")
        if clause.unit:
            raise ValueError(f"{where}: {role.role} is a category; a unit goes with a number")
        if not all(isinstance(v, str) for v in raw):
            raise ValueError(f"{where}: {role.role} ({role.column}) is a category; give its codes as strings "
                             f"('2', not 2): a code is matched as filed, {list(raw)}")
        if role.missing and (hit := sorted(set(raw) & set(role.missing))):
            raise ValueError(f"{where}: {hit} are codes {role.column} files for 'not recorded'; a missing code is "
                             "never a value a record satisfies")
        return tuple(raw)

    def bind(self, year: int | None) -> tuple[Bound | None, ...]:
        """Each clause on the column that carries its role in ``year`` (None: no year known, any declared span);
        None for a clause whose role no column carries then. Two columns of one role in one year raise."""
        out: list[Bound | None] = []
        for i, clause in enumerate(self.clauses):
            where = f"condition[{i}] ({clause.role})"
            role = role_column(self._columns, clause.role, year, f"{where}: {self.dataset}")
            if role is None:
                out.append(None)
                continue
            out.append(Bound(clause, role, _is_number(role), role.derived, self._operand(clause, role, where)))
        return tuple(out)

    def require(self, years: Sequence[int | None]) -> None:
        """Refuse a clause no column carries in any of ``years``: every record would be unknown, and an answer of
        zero satisfied records must not look like a measurement. A clause carried in some of the years is unknown in
        the others (counted, not refused)."""
        held = sorted({int(y) for y in years if y})
        if not held:
            return
        for i, clause in enumerate(self.clauses):
            if all(self.bind(y)[i] is None for y in held):
                spans = sorted({c.years for c in _candidates(self._columns, clause.role)}, key=str)
                raise ValueError(
                    f"condition[{i}] ({clause.role}): no column of {self.dataset} carries the role in {held[0]}-{held[-1]}"
                    f" (declared for {', '.join(f'{lo}-{hi}' for lo, hi in spans)}): every record would be unknown")

    def columns(self) -> frozenset[str]:
        """The columns (as declared) any year's reading of the condition tests: a derived one stands for its inputs."""
        return frozenset(c.column for clause in self.clauses for c in _candidates(self._columns, clause.role))

    def key(self) -> str:
        """A canonical text of the condition: equal conditions have equal keys, so a result is cached under it."""
        return json.dumps(sorted(json.dumps(c.as_dict(), sort_keys=True, ensure_ascii=False) for c in self.clauses))

    def as_list(self) -> list[dict[str, Any]]:
        return [c.as_dict() for c in self.clauses]

    # ------------------------------------------------------------------ the scan

    def scan(self, years: Sequence[int]) -> ds.Expression | None:
        """The lake scan's predicate: the records the raw columns do not rule out (true or unknown). A derived column
        is not in the scan; a clause whose column the family lacks cannot rule anything out."""
        by_year = {y: self.bind(y) for y in years} or {None: self.bind(None)}
        signatures = {tuple(b.column if b is not None else None for b in bound) for bound in by_year.values()}
        if len(signatures) != 1:
            return None                     # the columns change inside the family's years: tested after the read
        out = None
        for b in next(iter(by_year.values())):
            if b is None or b.derived:
                continue
            keep = pc.coalesce(_state(b, ds.field(b.column)), _TRUE)
            out = keep if out is None else (out & keep)
        return out

    # ------------------------------------------------------------------ the answer

    def state(self, table: pa.Table, docs: Mapping[str, Any] | Callable[[], Mapping[str, Any]],
              years: Sequence[int] | None = None) -> pa.Array:
        """Each record's answer: True, False, or null (unknown), for the raw ``table`` a read returned. The record's
        year is its ``year`` column when it has one, else ``years`` (the request's); several layouts in one table are
        each tested on their own column."""
        names = {n.upper(): n for n in table.column_names}
        if "YEAR" in names:
            column = table.column(names["YEAR"])
            held = sorted(int(y) for y in pc.unique(column).drop_null().to_pylist() if y)
        else:
            column, held = None, sorted({int(y) for y in years or ()})
        groups: dict[tuple[str | None, ...], list[Any]] = {}
        for y in held or [None]:
            bound = self.bind(y)
            groups.setdefault(tuple(b.column if b else None for b in bound), []).append(y)
        if len(groups) == 1:
            return _combine(table, names, self.bind(held[0] if held else None), docs)
        if column is None:
            raise ValueError(f"{self.dataset}: the years {held} file the condition's roles in different columns and the "
                             "records carry no year to tell them apart; read one year at a time")
        out: pa.Array = pa.nulls(table.num_rows, pa.bool_())
        for members in groups.values():
            mine = _combine(table, names, self.bind(members[0]), docs)
            out = pc.if_else(pc.is_in(column, value_set=pa.array(members, column.type)), mine, out)
        return out


def _trim(x: Any) -> Any:
    return pc.utf8_trim_whitespace(x.cast(pa.string()) if isinstance(x, ds.Expression) else pc.cast(x, pa.string()))


def measurement(role: ColumnRole, x: Any) -> tuple[Any, Any, Any]:
    """A measure's column ``x`` (an array, or a scan expression) read as the role declares: ``(value, recorded, known)``.

    ``value`` is the number as float64 (a decimal comma accepted; 0 where the text is no number, which ``known`` excludes).
    ``recorded`` is true where the text is a number that is none of the role's declared ``missing`` codes, as text or as a
    number; blank, null, unparsable text and a missing code are not recorded. ``known`` is ``recorded`` and inside the
    role's declared ``domain``: the values a measurement may be. Booleans, never null. The one reading of a measure's
    "not recorded" and "not a measurement", for a condition (`_state`) and for a sum (`proximity.care_flows(measure=)`)."""
    text = _trim(x)
    syntax = pc.coalesce(pc.match_substring_regex(text, _NUMBER), _FALSE)
    safe = pc.if_else(syntax, pc.replace_substring(text, ",", "."), pa.scalar("0"))
    value = safe.cast(pa.float64()) if isinstance(safe, ds.Expression) else pc.cast(safe, pa.float64())
    recorded = syntax
    missing = tuple(role.missing or ())
    if missing:
        recorded = pc.and_kleene(recorded, pc.invert(pc.is_in(text, value_set=pa.array(missing, pa.string()))))
        numbers = []
        for code in missing:
            try:
                numbers.append(float(code.replace(",", ".")))
            except ValueError:
                pass
        if numbers:
            recorded = pc.and_kleene(recorded, pc.invert(pc.is_in(value, value_set=pa.array(numbers, pa.float64()))))
    known = recorded
    if role.domain is not None:
        lo, hi = role.domain
        known = pc.and_kleene(known, pc.and_kleene(pc.greater_equal(value, lo), pc.less_equal(value, hi)))
    return value, recorded, known


def _state(b: Bound, x: Any) -> Any:
    """The three-valued answer of one clause on ``x``: the raw column (an array, or a scan expression), or the derived
    number. The same arithmetic builds the scan's predicate and tests the records read."""
    if b.derived:
        value, known = x, pc.is_valid(x)
    elif b.numeric:
        value, _recorded, known = measurement(b.role, x)
    else:
        value = text = _trim(x)
        known = pc.and_kleene(pc.invert(pc.coalesce(pc.equal(text, ""), _TRUE)),
                              pc.invert(pc.is_in(text, value_set=pa.array(tuple(b.role.missing or ()), pa.string()))))
    op = b.clause.op
    if op in _ORDER:
        hit = {"<": pc.less, "<=": pc.less_equal, ">": pc.greater, ">=": pc.greater_equal}[op](value, b.operand[0])
    elif b.numeric or b.derived:
        hit = pc.equal(value, b.operand[0]) if op == "==" else pc.is_in(value, value_set=pa.array(b.operand, pa.float64()))
        hit = pc.invert(hit) if op == "not in" else hit
    else:
        hit = pc.is_in(value, value_set=pa.array(b.operand, pa.string()))
        hit = pc.invert(hit) if op == "not in" else hit
    return pc.if_else(known, hit, _UNKNOWN)


def _combine(table: pa.Table, names: Mapping[str, str], bound: Sequence[Bound | None],
             docs: Mapping[str, Any] | Callable[[], Mapping[str, Any]]) -> pa.Array:
    out: Any = pa.repeat(_TRUE, table.num_rows)
    for b in bound:
        if b is None:
            state: Any = pa.nulls(table.num_rows, pa.bool_())
        elif b.derived:
            number = table.column(names[b.column.upper()]) if b.column.upper() in names else None
            if number is None or not pa.types.is_floating(number.type):
                from .view import derived_age_years

                number = derived_age_years(docs() if callable(docs) else docs, b.column, table)
            state = pa.nulls(table.num_rows, pa.bool_()) if number is None else _state(b, number)
        elif b.column.upper() in names:
            state = _state(b, table.column(names[b.column.upper()]))
        else:
            state = pa.nulls(table.num_rows, pa.bool_())      # this layout lacks the column: undecidable, not false
        out = pc.and_kleene(out, state)
    return out.combine_chunks() if isinstance(out, pa.ChunkedArray) else out


def prepare(dataset: str, condition: object) -> Condition | None:
    """``condition`` (a list of clauses, one clause, or a :class:`Condition`) checked against the roles of ``dataset``;
    None when there is none. Refuses an empty condition, which would select every record, an unknown role, a number
    compared with a code, and a measure whose not-recorded values are undeclared."""
    if condition is None:
        return None
    if isinstance(condition, Condition):
        return condition
    if isinstance(condition, (Mapping, Clause)):
        condition = [condition]
    if isinstance(condition, (str, bytes)) or not isinstance(condition, Sequence):
        raise ValueError(f"a condition is a list of clauses, not {condition!r}")
    if not condition:
        raise ValueError("an empty condition selects every record (give clauses, or drop it)")
    return Condition(dataset, tuple(_clause(c, i) for i, c in enumerate(condition)))


def settle(table: pa.Table, condition: Condition, *, keep_unknown: bool) -> tuple[pa.Table, dict[str, Any]]:
    """The records of ``table`` (rows carrying `CONDITION`) that satisfy the condition, and the report of how many
    did and how many could not be decided; ``keep_unknown`` leaves the unknown ones in, with `CONDITION` for the caller
    to count by group. The report goes into the table's metadata (`CONDITION_META`)."""
    state = table.column(CONDITION)
    unknown = state.null_count
    satisfied = pc.sum(state).as_py() or 0
    report = {"clauses": condition.as_list(), "satisfied": int(satisfied), "unknown": int(unknown), "unit": "records"}
    keep = pc.coalesce(state, _TRUE) if keep_unknown else pc.coalesce(state, _FALSE)
    table = table.filter(keep)
    if not keep_unknown:
        table = table.drop_columns([CONDITION])
    meta = dict(table.schema.metadata or {})
    meta[CONDITION_META] = json.dumps(report, ensure_ascii=False).encode()
    return table.replace_schema_metadata(meta), report


def condition_report(table: pa.Table) -> dict[str, Any] | None:
    """What a result says of the condition it was read under: ``{"clauses", "satisfied", "unknown", "unit"}``, where
    ``unknown`` is how many records (or, of ``count_events``, events) the condition could not decide; None when the
    result was read under none."""
    raw = (table.schema.metadata or {}).get(CONDITION_META)
    return json.loads(raw) if raw else None
