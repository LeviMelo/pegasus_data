"""Event types: what a dataset's rows become when they are counted as events.

A record is not always the event (DESIGN §3.3 of PegaSUS; handoff 2026-10-04
§3): an SIH AIH is a billing document, a SINAN row a notification. Each
dataset in ``curation/datasets/*.yml`` declares, under ``event_types:``:

* ``kind``: death, foetal death, birth, hospitalisation, notification, case;
* ``classifiers``: the code columns that partition the events, one
  ``primary`` and any ``alternative`` (different families of fields over the
  same events, never independent of each other);
* ``status``: which rows count (a column and the codes that count, read
  from that dataset's own form or layout, never guessed);
* ``consolidation``: the key whose distinct values are the events (SIH's
  long-stay continuation AIHs share their principal's ``N_AIH``);
* ``weight``: the column whose value is the number of events a row stands for
  (SIA's production rows are quantities of a procedure: PA's consolidated BPA
  holds up to 95,404 on one row), with its evidence; or a ``grid`` of columns,
  each the events of one (sex, age band), where the row is a group of people
  the form counts (SINAN-SDTA's foodborne outbreak, OQ-76);
* ``evidence``: where the rule comes from.

:func:`count_events` applies status, consolidation and weight to a query, so a
count of hospitalisations is one rule wherever it is asked.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc


@dataclass(frozen=True, slots=True)
class Classifier:
    column: str
    role: str            # primary | alternative
    structure: str | None = None   # the code structure it lives in (ICD10, SIGTAP...)


#: The columns a weight grid's events carry in place of a record's sex and age: sex 1 male / 2 female (None unknown),
#: age the lower edge of the grid's band in years (None unknown). Not filed by DATASUS; `grid_events` makes them.
GRID_SEX, GRID_AGE = "grid_sex", "grid_age_band"


@dataclass(frozen=True, slots=True)
class GridCell:
    column: str
    sex: int | None       # 1 male, 2 female, None the form's "ignorado"
    age: int | None       # the band's lower edge in years, None the form's "ignorada"


@dataclass(frozen=True, slots=True)
class EventType:
    dataset: str          # the datasets-file key (SIHSUS_RD)
    system: str
    series: str
    name: str
    kind: str
    grain: str | None
    classifiers: tuple[Classifier, ...] = ()
    status_column: str | None = None
    status_values: tuple[str, ...] = ()
    #: Codes that do NOT count; every other row counts, a blank one included
    #: (a SINAN notification still under investigation is a probable case).
    status_excluded: tuple[str, ...] = ()
    consolidation_key: tuple[str, ...] = ()
    weight: str | None = None
    #: A weight grid: each cell's column holds the events of one (sex, age band); ``bands`` are the bands' lower
    #: edges (the last open); ``grid_total`` the row's total, whose events beyond the grid's are of unknown sex and age;
    #: ``grid_margin`` the form's own sum of the grid, which solves a single blank cell.
    grid: tuple[GridCell, ...] = ()
    bands: tuple[int, ...] = ()
    grid_total: str | None = None
    grid_margin: str | None = None
    marks: tuple[str, ...] = ()
    evidence: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset, "system": self.system, "series": self.series, "name": self.name,
            "kind": self.kind, "grain": self.grain,
            "classifiers": [{"column": c.column, "role": c.role, "structure": c.structure} for c in self.classifiers],
            "status": ({"column": self.status_column, "values": list(self.status_values),
                        "excluded": list(self.status_excluded)} if self.status_column else None),
            "consolidation": {"key": list(self.consolidation_key)} if self.consolidation_key else None,
            "weight": self.weight,
            "grid": ({"cells": [{"column": c.column, "sex": c.sex, "age": c.age} for c in self.grid],
                      "bands": list(self.bands), "total": self.grid_total, "margin": self.grid_margin,
                      "sex": GRID_SEX, "age": GRID_AGE}
                     if self.grid else None),
            "marks": list(self.marks), "evidence": self.evidence, "note": self.note,
        }


KINDS = frozenset({"death", "foetal_death", "birth", "hospitalisation", "notification", "case", "probable_case",
                   "authorisation", "procedure"})


@lru_cache(maxsize=1)
def load_event_types() -> dict[str, tuple[EventType, ...]]:
    """``SYSTEM-SERIES`` -> its declared event types, validated."""
    from ..config import curation_root
    from .curation import read_yaml

    out: dict[str, list[EventType]] = {}
    for path in sorted((curation_root() / "datasets").glob("*.yml")):
        doc = read_yaml(path)
        # a file's shared event types hold for every dataset in it that does not declare one of the same name
        # (SINAN's notification: every agravo carries the notification block, so a row is a notification in all 58)
        shared = (doc.get("shared") or {}).get("event_types") or ()
        for key, body in (doc.get("datasets") or {}).items():
            body = body or {}
            own = list(body.get("event_types") or ())
            names = {str(s.get("name")) for s in own}
            # `event_types: []` declares that the dataset has none, the shared ones included (SINAN's ESPO
            # records animal epizootics and NTRA survey batches, not notified people)
            inherited = [] if "event_types" in body and not own else [s for s in shared if str(s.get("name")) not in names]
            for spec in own + inherited:
                event = _event(str(key).upper(), body, spec, path.name)
                out.setdefault(f"{event.system}-{event.series}", []).append(event)
    return {k: tuple(v) for k, v in out.items()}


def _event(key: str, body: dict[str, Any], spec: dict[str, Any], where: str) -> EventType:
    name = str(spec.get("name") or "")
    kind = str(spec.get("kind") or "")
    if kind not in KINDS:
        raise ValueError(f"{where}: {key}.{name}: kind {kind!r} not in {sorted(KINDS)}")
    classifiers = tuple(
        Classifier(str(c["column"]).upper(), str(c.get("role", "alternative")), c.get("structure"))
        for c in spec.get("classifiers") or ()
    )
    primaries = [c for c in classifiers if c.role == "primary"]
    if len(primaries) > 1 or any(c.role not in ("primary", "alternative") for c in classifiers):
        raise ValueError(f"{where}: {key}.{name}: one primary classifier at most, the others alternative")
    status = spec.get("status") or {}
    if status and bool(status.get("values")) == bool(status.get("exclude")):
        raise ValueError(f"{where}: {key}.{name}: a status lists either the codes that count or those that do not")
    if status and not status.get("evidence") and not spec.get("evidence"):
        raise ValueError(f"{where}: {key}.{name}: a status rule needs its evidence")
    weight = spec.get("weight") or {}
    if weight and not ((weight.get("column") or weight.get("grid")) and weight.get("evidence")):
        raise ValueError(f"{where}: {key}.{name}: a weight names its column or its grid, and its evidence")
    if weight and spec.get("consolidation"):
        raise ValueError(f"{where}: {key}.{name}: a weighted row is many events; consolidating it to one is a contradiction")
    grid, bands, total, margin = _grid(weight.get("grid"), f"{where}: {key}.{name}")
    return EventType(
        dataset=key, system=_canonical_system(str(body.get("system") or "")), series=str(body.get("series") or "").upper(),
        name=name, kind=kind, grain=spec.get("grain") or body.get("what_one_row_is"), classifiers=classifiers,
        status_column=str(status["column"]).upper() if status.get("column") else None,
        status_values=tuple(str(v) for v in status.get("values") or ()),
        status_excluded=tuple(str(v) for v in status.get("exclude") or ()),
        consolidation_key=tuple(str(c).upper() for c in (spec.get("consolidation") or {}).get("key") or ()),
        weight=str(weight["column"]).upper() if weight.get("column") else None, grid=grid, bands=bands, grid_total=total, grid_margin=margin,
        marks=tuple(str(m).upper() for m in spec.get("marks") or ()),
        evidence=spec.get("evidence") or status.get("evidence"), note=spec.get("note"),
    )


def _grid(spec: dict[str, Any] | None, where: str) -> tuple[tuple[GridCell, ...], tuple[int, ...], str | None, str | None]:
    """A weight grid's cells, validated: every cell a distinct (sex, band) in its own column, every band one of
    ``bands``."""
    if not spec:
        return (), (), None, None
    bands = tuple(int(b) for b in spec.get("bands") or ())
    if not bands or bands[0] != 0 or list(bands) != sorted(set(bands)):
        raise ValueError(f"{where}: a grid's bands are increasing lower edges from 0")
    sexes = {"male": 1, "female": 2, None: None}
    cells = []
    for c in spec.get("cells") or ():
        if c.get("sex") not in sexes or (c.get("age") is not None and int(c["age"]) not in bands):
            raise ValueError(f"{where}: grid cell {c}: sex male, female or null; age one of the bands {bands} or null")
        cells.append(GridCell(str(c["column"]).upper(), sexes[c.get("sex")], None if c.get("age") is None else int(c["age"])))
    if not cells or len({(c.sex, c.age) for c in cells}) != len(cells) or len({c.column for c in cells}) != len(cells):
        raise ValueError(f"{where}: a grid's cells are distinct (sex, band) pairs in distinct columns")
    total, margin = (str(spec[k]).upper() if spec.get(k) else None for k in ("total", "margin"))
    return tuple(cells), bands, total, margin


def _canonical_system(name: str) -> str:
    """The system as the catalog files it: the ontology's ``SIA`` is crawled as ``SIASUS``, so a
    dataset declared as ``SIA.AQ`` has the same key as a request for ``SIASUS.AQ``."""
    from .._request import SYSTEM_ALIASES, _load_aliases

    _load_aliases()
    return SYSTEM_ALIASES.get(name.upper(), name.upper())


def _key(dataset: str) -> str:
    from .._request import parse_dataset

    system, series = parse_dataset(dataset)
    return f"{system}-{series or system}".upper()


def event_types(dataset: str) -> list[dict[str, Any]]:
    """The event types a dataset's rows become (``pegasus-data events <dataset>``)."""
    declared = load_event_types()
    key = _key(dataset)
    if key not in declared:
        raise KeyError(f"no event types declared for {dataset!r} ({key}); declared: {sorted(declared)}")
    return [e.as_dict() for e in declared[key]]


def event_type(dataset: str, name: str) -> EventType:
    for event in load_event_types().get(_key(dataset), ()):
        if event.name == name:
            return event
    raise KeyError(f"{dataset!r} declares no event type {name!r}")


def events_of(table: pa.Table, event: EventType) -> pa.Table:
    """The rows of ``table`` that are events of this type, one per event.

    Status first (which rows count), then consolidation: one row per distinct
    key, the first in file order. Exact string matching: a status code is
    matched at the width the dataset files it.
    """
    if event.status_column:
        if event.status_column not in table.column_names:
            raise KeyError(f"{event.name}: status column {event.status_column} is not in the table")
        values = pc.utf8_trim_whitespace(pc.cast(table.column(event.status_column), pa.string()))
        if event.status_values:
            table = table.filter(pc.is_in(values, value_set=pa.array(event.status_values, pa.string())))
        else:
            dropped = pc.fill_null(pc.is_in(values, value_set=pa.array(event.status_excluded, pa.string())), False)
            table = table.filter(pc.invert(dropped))
    if event.consolidation_key:
        missing = [c for c in event.consolidation_key if c not in table.column_names]
        if missing:
            raise KeyError(f"{event.name}: consolidation key {missing} is not in the table")
        indexed = table.append_column("__i", pa.array(range(table.num_rows), pa.int64()))
        first = indexed.group_by(list(event.consolidation_key), use_threads=False).aggregate([("__i", "min")])
        keep = pc.sort_indices(first.column("__i_min"))
        table = table.take(pc.take(first.column("__i_min"), keep))
    return table


def event_weights(table: pa.Table, event: EventType) -> pa.Array:
    """The number of events each row of ``table`` stands for: 1, or its ``weight`` column as an integer.

    A weight that is not a non-negative integer raises: a row whose quantity is unknown is not zero events, and a
    sum that silently skipped it would look like a count."""
    if event.weight is None:
        return pa.repeat(pa.scalar(1, pa.int64()), table.num_rows)
    if event.weight not in table.column_names:
        raise KeyError(f"{event.name}: weight column {event.weight} is not in the table")
    text = pc.utf8_trim_whitespace(pc.cast(table.column(event.weight), pa.string()))
    numeric = pc.match_substring_regex(text, r"^\d+$")
    bad = table.num_rows - pc.sum(pc.fill_null(numeric, False)).as_py() if table.num_rows else 0
    if bad:
        raise ValueError(f"{event.name}: {bad} of {table.num_rows} rows carry no quantity in {event.weight}")
    return pc.cast(text, pa.int64())


def _integers(table: pa.Table, column: str, event: EventType) -> pa.Array:
    """A count column as integers, blank as null; any other text raises (an unknown quantity is not zero events)."""
    if column not in table.column_names:
        raise KeyError(f"{event.name}: grid column {column} is not in the table")
    text = pc.utf8_trim_whitespace(pc.cast(table.column(column), pa.string()))
    blank = pc.fill_null(pc.equal(text, ""), True)
    whole = pc.fill_null(pc.match_substring_regex(text, r"^\d+$"), False)
    bad = pc.sum(pc.and_(pc.invert(blank), pc.invert(whole))).as_py()
    if bad:
        raise ValueError(f"{event.name}: {bad} rows carry a count in {column} that is not a whole number")
    return pc.cast(pc.if_else(blank, pa.scalar(None, pa.string()), text), pa.int64())


def grid_events(table: pa.Table, event: EventType, keep: list[str] | None = None) -> pa.Table:
    """A grid event's rows as events by (sex, age band): one row per (record, cell), ``events`` the cell's count,
    and one per record for the events of its total beyond its grid's, of unknown sex and age.

    The grid is what the form counted by sex and age; its total may hold more people (SINAN-SDTA: the grid counts the
    ill who were interviewed, field 28, and NU_TOT all the ill, field 29). A blank cell is never zero: a single blank
    is solved from the grid's margin (the form's own sum of the grid) when that leaves it a whole number, and any
    other blank holds no one in the grid, so its people, if any, are among the total's of unknown sex and age. A row
    with no cell filled has no grid; a row with neither grid nor total is ``unquantified`` (a group, not zero
    people). Where the grid exceeds the total, the grid counts: its people were counted one by one."""
    keep = list(keep or [])
    n = table.num_rows
    counts = [_integers(table, c.column, event) for c in event.grid]
    n_filled = pa.repeat(pa.scalar(0, pa.int64()), n)
    grid_sum = pa.repeat(pa.scalar(0, pa.int64()), n)
    for a in counts:
        n_filled = pc.add(n_filled, pc.cast(pc.is_valid(a), pa.int64()))
        grid_sum = pc.add(grid_sum, pc.fill_null(a, 0))
    if event.grid_margin:
        margin = _integers(table, event.grid_margin, event)
        solved = pc.subtract(margin, grid_sum)
        solvable = pc.fill_null(pc.and_(pc.equal(n_filled, len(event.grid) - 1), pc.greater_equal(solved, 0)), False)
        counts = [pc.if_else(pc.and_(solvable, pc.is_null(a)), solved, a) for a in counts]
        grid_sum = pc.if_else(solvable, margin, grid_sum)
        n_filled = pc.if_else(solvable, pa.scalar(len(event.grid), pa.int64()), n_filled)
    total = _integers(table, event.grid_total, event) if event.grid_total else pa.nulls(n, pa.int64())
    beyond = pc.max_element_wise(pc.subtract(pc.fill_null(total, 0), grid_sum), pa.scalar(0, pa.int64()))
    unquantified = pc.cast(pc.and_(pc.equal(n_filled, 0), pc.is_null(total)), pa.int64())
    zero = pa.repeat(pa.scalar(0, pa.int64()), n)
    parts = [pa.table({**{k: table.column(k) for k in keep},
                       GRID_SEX: pa.repeat(pa.scalar(c.sex, pa.int8()), n), GRID_AGE: pa.repeat(pa.scalar(c.age, pa.int16()), n),
                       "events": pc.fill_null(a, 0), "unquantified": zero})
             for c, a in zip(event.grid, counts, strict=True)]
    parts.append(pa.table({**{k: table.column(k) for k in keep},
                           GRID_SEX: pa.nulls(n, pa.int8()), GRID_AGE: pa.nulls(n, pa.int16()),
                           "events": beyond, "unquantified": unquantified}))
    long = pa.concat_tables(parts)
    return long.filter(pc.or_(pc.greater(long.column("events"), 0), pc.greater(long.column("unquantified"), 0)))


def count_events(
    dataset: str, name: str, *, period: object, geography: object = "BR", by: list[str] | None = None,
    **query_kwargs: Any,
) -> pa.Table:
    """Counts of one event type, optionally grouped by columns of the record; a weighted event sums its weight.

    A grid event's ``by`` may name `GRID_SEX` and `GRID_AGE`, and its result has a column ``unquantified``: the rows
    whose grid and total are both blank, a group whose people were not counted (`grid_events`)."""
    from .._query_engine.executor import query

    event = event_type(dataset, name)
    if event.grid:
        record_by = [c for c in by or [] if c not in (GRID_SEX, GRID_AGE)]
        columns = {c for c in (event.status_column, event.grid_total, event.grid_margin, *(c.column for c in event.grid),
                               *record_by) if c}
        table = query(dataset, period=period, geography=geography, select=sorted(columns), present="codes",
                      **query_kwargs)
        long = grid_events(events_of(table, event), event, record_by)
        if not by:
            return pa.table({"events": [pc.sum(long.column("events")).as_py() or 0],
                             "unquantified": [pc.sum(long.column("unquantified")).as_py() or 0]})
        return long.group_by(list(by)).aggregate([("events", "sum"), ("unquantified", "sum")]).rename_columns(
            [*by, "events", "unquantified"])
    columns = {c for c in (event.status_column, *event.consolidation_key, event.weight, *(by or [])) if c}
    table = query(dataset, period=period, geography=geography, select=sorted(columns) or None,
                  present="codes", **query_kwargs)
    events = events_of(table, event)
    events = events.append_column("__w", event_weights(events, event))
    if not by:
        return pa.table({"events": [pc.sum(events.column("__w")).as_py() or 0]})
    return events.group_by(by).aggregate([("__w", "sum")]).rename_columns([*by, "events"])


def field_overlap(
    dataset: str, name: str, a: dict[str, list[str]], b: dict[str, list[str]], *,
    period: object, geography: object = "BR", **query_kwargs: Any,
) -> dict[str, Any]:
    """How much two fields over one event type share, measured from records.

    A field is the events whose columns carry a code starting with one of the
    listed prefixes: ``{"CAUSABAS": ["I21"]}`` or, for "any mention",
    ``{"LINHAA": ["I21"], "LINHAB": ["I21"], ...}``. The overlap is the shared
    events over the smaller field's events (DESIGN §3.5): two fields above 0.05
    are never tested against each other as if independent.
    """
    from .._query_engine.executor import query

    event = event_type(dataset, name)
    columns = {c for c in (event.status_column, *event.consolidation_key, *a, *b) if c}
    table = events_of(query(dataset, period=period, geography=geography, select=sorted(columns),
                            present="codes", **query_kwargs), event)

    def members(predicate: dict[str, list[str]]) -> pa.Array:
        hit = pa.array([False] * table.num_rows)
        for column, prefixes in predicate.items():
            values = pc.utf8_upper(pc.cast(table.column(column), pa.string()))
            for prefix in prefixes:
                hit = pc.or_(hit, pc.fill_null(pc.starts_with(values, str(prefix).upper()), False))
        return hit

    in_a, in_b = members(a), members(b)
    n_a, n_b = pc.sum(in_a).as_py() or 0, pc.sum(in_b).as_py() or 0
    shared = pc.sum(pc.and_(in_a, in_b)).as_py() or 0
    smaller = min(n_a, n_b)
    return {"events": table.num_rows, "a": n_a, "b": n_b, "shared": shared,
            "overlap": (shared / smaller) if smaller else None}
