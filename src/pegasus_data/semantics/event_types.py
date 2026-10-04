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
* ``evidence``: where the rule comes from.

:func:`count_events` applies status and consolidation to a query, so a count
of hospitalisations is one rule wherever it is asked.
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
            "marks": list(self.marks), "evidence": self.evidence, "note": self.note,
        }


KINDS = frozenset({"death", "foetal_death", "birth", "hospitalisation", "notification", "case", "probable_case"})


@lru_cache(maxsize=1)
def load_event_types() -> dict[str, tuple[EventType, ...]]:
    """``SYSTEM-SERIES`` -> its declared event types, validated."""
    from ..config import curation_root
    from .curation import read_yaml

    out: dict[str, list[EventType]] = {}
    for path in sorted((curation_root() / "datasets").glob("*.yml")):
        for key, body in (read_yaml(path).get("datasets") or {}).items():
            body = body or {}
            for spec in body.get("event_types") or ():
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
    return EventType(
        dataset=key, system=str(body.get("system") or "").upper(), series=str(body.get("series") or "").upper(),
        name=name, kind=kind, grain=spec.get("grain") or body.get("what_one_row_is"), classifiers=classifiers,
        status_column=str(status["column"]).upper() if status.get("column") else None,
        status_values=tuple(str(v) for v in status.get("values") or ()),
        status_excluded=tuple(str(v) for v in status.get("exclude") or ()),
        consolidation_key=tuple(str(c).upper() for c in (spec.get("consolidation") or {}).get("key") or ()),
        marks=tuple(str(m).upper() for m in spec.get("marks") or ()),
        evidence=spec.get("evidence") or status.get("evidence"), note=spec.get("note"),
    )


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


def count_events(
    dataset: str, name: str, *, period: object, geography: object = "BR", by: list[str] | None = None,
    **query_kwargs: Any,
) -> pa.Table:
    """Counts of one event type, optionally grouped by columns of the record."""
    from .._query_engine.executor import query

    event = event_type(dataset, name)
    columns = {c for c in (event.status_column, *event.consolidation_key, *(by or [])) if c}
    table = query(dataset, period=period, geography=geography, select=sorted(columns) or None,
                  present="codes", **query_kwargs)
    events = events_of(table, event)
    if not by:
        return pa.table({"events": [events.num_rows]})
    return events.group_by(by).aggregate([([], "count_all")]).rename_columns([*by, "events"])


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
