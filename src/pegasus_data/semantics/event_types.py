"""Event types: what a dataset's rows become when they are counted as events.

A record is not always the event (DESIGN §3.3 of PegaSUS; handoff 2026-10-04
§3): an SIH AIH is a billing document, a SINAN row a notification. Each
dataset in ``curation/datasets/*.yml`` declares, under ``event_types:``:

* ``kind``: death, foetal death, birth, hospitalisation, notification, case;
* ``classifiers``: the code columns that partition the events, one
  ``primary`` and any ``alternative`` (different families of fields over the
  same events, never independent of each other); ``role`` is required. An alternative that
  ``recodes`` the primary is a second coding of the SAME attribute (SIM's original underlying cause beside the
  underlying cause, same ICD-10 structure): it corroborates or compares and is never a further dimension, since
  counting by it counts the same events again; one that does not is another attribute of the same events, a facet
  (SIH's procedure beside its diagnosis) that partitions them differently;
* ``status``: which rows count (a column and the codes that count, read
  from that dataset's own form or layout, never guessed);
* ``consolidation``: the key whose distinct values are the events (SIH's
  long-stay continuation AIHs share their principal's ``N_AIH``);
* ``weight``: the column whose value is the number of events a row stands for
  (SIA's production rows are quantities of a procedure: PA's consolidated BPA
  holds up to 95,404 on one row), with its evidence; or a ``grid`` of columns,
  each the events of one (sex, age band), where the row is a group of people
  the form counts (SINAN-SDTA's foodborne outbreak, OQ-76);
* ``duplicates``: rows identical in every column but the listed entry metadata (``except``: a notification number,
  an entry or transfer date) are one record entered again; and rows the source itself flags as duplicates
  (``flag: {column, codes}``: SINAN's NDUPLIC_N 2, "não contar"; a form without the flag flags none). With its
  evidence; dropped before anything else. A file's ``shared: duplicates:`` holds for each of its event types;
* ``persons: false``: the row is a group, not a person (a foodborne outbreak): its events have no sex or age, and
  are exposed by the whole population of their place;
* ``evidence``: where the rule comes from;
* ``source_notes``: what the SOURCE itself says about the event, so every consumer inherits it and a report states
  its limits with their citation (ADR-0160): ``source`` (required, the document), and any of ``definition`` (how the
  source defines the event), ``valid_from`` / ``valid_to`` (years its data are valid), ``final_after_years`` (a
  notification year's national database is frozen that many years later), ``known_errors`` and ``limitations``
  (lists of statements the source makes), ``form`` (the notification form used). Unknown keys raise.
* ``exposure``: the event's own denominator when it is other events, not residents: ``events`` (one or more
  ``DATASET:event`` whose counts by place and year are summed: live births for a congenital or gestational condition,
  live births and foetal deaths for the foetal death rate), ``per`` (the scale the source reports: 1000) and
  ``evidence`` (required: the indicator's definition and who uses it). Consumers read the event per those events.

:func:`count_events` applies status, consolidation and weight to a query, so a
count of hospitalisations is one rule wherever it is asked.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
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
    #: The primary column this one re-codes (a second coding of the same attribute, same structure); None: a facet
    recodes: str | None = None


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
    #: Duplicate entries: rows equal on every column but these (entry metadata) are one record (``None``: no rule)
    duplicates_except: tuple[str, ...] | None = None
    #: The source's own duplicate flag: (column, codes that mean "do not count")
    duplicates_flag: tuple[str, tuple[str, ...]] | None = None
    weight: str | None = None
    #: A weight grid: each cell's column holds the events of one (sex, age band); ``bands`` are the bands' lower
    #: edges (the last open); ``grid_total`` the row's total, whose events beyond the grid's are of unknown sex and age;
    #: ``grid_margin`` the form's own sum of the grid, which solves a single blank cell.
    grid: tuple[GridCell, ...] = ()
    bands: tuple[int, ...] = ()
    grid_total: str | None = None
    grid_margin: str | None = None
    marks: tuple[str, ...] = ()
    #: False when the row is a group (an outbreak), not a person: no sex or age, the whole population exposed
    persons: bool = True
    evidence: str | None = None
    note: str | None = None
    #: The source's own definitions, validity window, finality rule and acknowledged errors, with their citation
    source_notes: dict[str, Any] | None = None
    #: The denominator events (``events``: DATASET:event, summed), the reporting scale and the evidence for them
    exposure: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset, "system": self.system, "series": self.series, "name": self.name,
            "kind": self.kind, "grain": self.grain,
            "classifiers": [{"column": c.column, "role": c.role, "structure": c.structure, "recodes": c.recodes}
                           for c in self.classifiers],
            "status": ({"column": self.status_column, "values": list(self.status_values),
                        "excluded": list(self.status_excluded)} if self.status_column else None),
            "consolidation": {"key": list(self.consolidation_key)} if self.consolidation_key else None,
            **({"duplicates": {**({"except": list(self.duplicates_except)} if self.duplicates_except is not None else {}),
                                **({"flag": {"column": self.duplicates_flag[0], "codes": list(self.duplicates_flag[1])}}
                                   if self.duplicates_flag else {})}}
               if self.duplicates_except is not None or self.duplicates_flag else {}),
            "weight": self.weight,
            "grid": ({"cells": [{"column": c.column, "sex": c.sex, "age": c.age} for c in self.grid],
                      "bands": list(self.bands), "total": self.grid_total, "margin": self.grid_margin,
                      "sex": GRID_SEX, "age": GRID_AGE}
                     if self.grid else None),
            "marks": list(self.marks), "evidence": self.evidence, "note": self.note,
            "source_notes": self.source_notes,
            "exposure": self.exposure,
            **({} if self.persons else {"persons": False}),
        }


KINDS = frozenset({"death", "foetal_death", "birth", "hospitalisation", "notification", "case", "probable_case", "outbreak",
                   "authorisation", "procedure"})


@lru_cache(maxsize=1)
def load_event_types() -> dict[str, tuple[EventType, ...]]:
    """``SYSTEM-SERIES`` -> its declared event types, validated."""
    from ..config import curation_root
    from .curation import read_yaml

    out: dict[str, list[EventType]] = {}
    for path in sorted((curation_root() / "datasets").glob("*.yml")):
        doc = read_yaml(path, shared=True)
        # a file's shared event types hold for every dataset in it that does not declare one of the same name
        # (SINAN's notification: every agravo carries the notification block, so a row is a notification in all 58)
        shared = (doc.get("shared") or {}).get("event_types") or ()
        shared_dups = (doc.get("shared") or {}).get("duplicates")
        for key, body in (doc.get("datasets") or {}).items():
            body = body or {}
            own = list(body.get("event_types") or ())
            names = {str(s.get("name")) for s in own}
            # `event_types: []` declares that the dataset has none, the shared ones included (SINAN's ESPO
            # records animal epizootics and NTRA survey batches, not notified people)
            # `shared_event_types: false` declares that none of them hold beside its own (SDTA's row is an outbreak: its
            # `case` and `outbreak` events, never SINAN's person notification)
            inherited = ([] if ("event_types" in body and not own) or body.get("shared_event_types") is False
                         else [s for s in shared if str(s.get("name")) not in names])
            for spec in own + inherited:
                if shared_dups and "duplicates" not in spec:
                    spec = {**spec, "duplicates": shared_dups}
                event = _event(str(key).upper(), body, spec, path.name)
                out.setdefault(f"{event.system}-{event.series}", []).append(event)
    return {k: tuple(v) for k, v in out.items()}


def _event(key: str, body: dict[str, Any], spec: dict[str, Any], where: str) -> EventType:
    name = str(spec.get("name") or "")
    kind = str(spec.get("kind") or "")
    if kind not in KINDS:
        raise ValueError(f"{where}: {key}.{name}: kind {kind!r} not in {sorted(KINDS)}")
    classifiers = _classifiers(spec.get("classifiers"), f"{where}: {key}.{name}")
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
    system, series = _canonical_system(str(body.get("system") or "")), str(body.get("series") or "").upper()
    grid, bands, total, margin = _grid(weight if weight.get("grid") else None, f"{system}-{series}",
                                       f"{where}: {key}.{name}")
    return EventType(
        dataset=key, system=_canonical_system(str(body.get("system") or "")), series=str(body.get("series") or "").upper(),
        name=name, kind=kind, grain=spec.get("grain") or body.get("what_one_row_is"), classifiers=classifiers,
        status_column=str(status["column"]).upper() if status.get("column") else None,
        status_values=tuple(str(v) for v in status.get("values") or ()),
        status_excluded=tuple(str(v) for v in status.get("exclude") or ()),
        consolidation_key=tuple(str(c).upper() for c in (spec.get("consolidation") or {}).get("key") or ()),
        duplicates_except=_duplicates(spec.get("duplicates"), f"{where}: {key}.{name}"),
        duplicates_flag=_duplicate_flag(spec.get("duplicates"), f"{where}: {key}.{name}"),
        weight=str(weight["column"]).upper() if weight.get("column") else None, grid=grid, bands=bands, grid_total=total, grid_margin=margin,
        marks=tuple(str(m).upper() for m in spec.get("marks") or ()), persons=bool(spec.get("persons", True)),
        evidence=spec.get("evidence") or status.get("evidence"), note=spec.get("note"),
        source_notes=_source_notes(spec.get("source_notes"), f"{where}: {key}.{name}"),
        exposure=_exposure(spec.get("exposure"), f"{where}: {key}.{name}"),
    )


def _classifiers(specs: list[dict[str, Any]] | None, where: str) -> tuple[Classifier, ...]:
    """The declared classifiers, validated: every one names its ``role``; one primary at most; ``recodes`` names the
    primary column it re-codes, in the same code structure."""
    classifiers = []
    for c in specs or ():
        if "role" not in c:
            raise ValueError(f"{where}: classifier {c.get('column')!r} names no role (primary or alternative)")
        recodes = str(c["recodes"]).upper() if c.get("recodes") else None
        classifiers.append(Classifier(str(c["column"]).upper(), str(c["role"]), c.get("structure"), recodes))
    primaries = [c for c in classifiers if c.role == "primary"]
    if len(primaries) > 1 or any(c.role not in ("primary", "alternative") for c in classifiers):
        raise ValueError(f"{where}: one primary classifier at most, the others alternative")
    for c in classifiers:
        if c.recodes is None:
            continue
        if c.role != "alternative":
            raise ValueError(f"{where}: {c.column} recodes {c.recodes}, so it is an alternative classifier")
        if not primaries or primaries[0].column != c.recodes:
            raise ValueError(f"{where}: {c.column} recodes {c.recodes}, which is not this event's primary classifier")
        if not c.structure or c.structure != primaries[0].structure:
            raise ValueError(f"{where}: {c.column} recodes {c.recodes} and must be in its code structure "
                             f"({primaries[0].structure!r}), not {c.structure!r}")
    return tuple(classifiers)


def _exposure(spec: dict[str, Any] | None, where: str) -> dict[str, Any] | None:
    """A declared ``exposure`` block, validated: ``events`` a non-empty list of ``DATASET:event``, ``per`` a positive
    number, ``evidence`` required; unknown keys raise."""
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise ValueError(f"{where}: exposure is a mapping")
    unknown = sorted(set(spec) - {"events", "per", "evidence"})
    if unknown:
        raise ValueError(f"{where}: exposure has unknown keys {unknown}")
    events = spec.get("events")
    if isinstance(events, str):
        events = [events]
    if not events or not all(isinstance(e, str) and e.count(":") == 1 and all(e.split(":")) for e in events):
        raise ValueError(f"{where}: exposure.events is a list of DATASET:event")
    if not str(spec.get("evidence") or "").strip():
        raise ValueError(f"{where}: exposure needs its evidence (the indicator's definition and who uses it)")
    per = spec.get("per", 1)
    if isinstance(per, bool) or not isinstance(per, (int, float)) or per <= 0:
        raise ValueError(f"{where}: exposure.per is a positive number")
    return {"events": [e.strip() for e in events], "per": per, "evidence": " ".join(str(spec["evidence"]).split())}


_NOTE_TEXT = ("definition", "form")
_NOTE_LISTS = ("known_errors", "limitations")
_NOTE_YEARS = ("valid_from", "valid_to", "final_after_years")


def _source_notes(spec: dict[str, Any] | None, where: str) -> dict[str, Any] | None:
    """A declared ``source_notes`` block, validated: a citation is required, every key is known, years are integers,
    texts and lists of texts are non-empty, and the validity window is ordered."""
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise ValueError(f"{where}: source_notes is a mapping")
    unknown = sorted(set(spec) - {"source", *_NOTE_TEXT, *_NOTE_LISTS, *_NOTE_YEARS})
    if unknown:
        raise ValueError(f"{where}: source_notes has unknown keys {unknown}")
    if not str(spec.get("source") or "").strip():
        raise ValueError(f"{where}: source_notes needs its source (the document that states it)")
    if len(spec) < 2:
        raise ValueError(f"{where}: source_notes states nothing beside its source")
    out: dict[str, Any] = {"source": str(spec["source"]).strip()}
    for k in _NOTE_TEXT:
        if k in spec:
            if not isinstance(spec[k], str) or not spec[k].strip():
                raise ValueError(f"{where}: source_notes.{k} is a non-empty text")
            out[k] = " ".join(spec[k].split())
    for k in _NOTE_LISTS:
        if k in spec:
            items = spec[k]
            if not isinstance(items, list) or not items or not all(isinstance(i, str) and i.strip() for i in items):
                raise ValueError(f"{where}: source_notes.{k} is a non-empty list of texts")
            out[k] = [" ".join(i.split()) for i in items]
    for k in _NOTE_YEARS:
        if k in spec:
            v = spec[k]
            if isinstance(v, bool) or not isinstance(v, int) or v < (1 if k == "final_after_years" else 1900):
                raise ValueError(f"{where}: source_notes.{k} is a year (or, for final_after_years, a number of years)")
            out[k] = v
    if "valid_from" in out and "valid_to" in out and out["valid_from"] > out["valid_to"]:
        raise ValueError(f"{where}: source_notes.valid_from is after valid_to")
    return out


def _grid(spec: dict[str, Any] | None, dataset: str,
          where: str) -> tuple[tuple[GridCell, ...], tuple[int, ...], str | None, str | None]:
    """A weight grid's cells: the role file's grid ``spec["grid"]`` (`grids`, ADR-0158), its ``sex`` axis read through
    the codes the weight names male and female (any other code: unknown), its ``age`` axis codes the bands' lower edges
    in years but for those the weight names ``unknown``. The bands start at 0 and every cell is a distinct (sex, band)."""
    if not spec:
        return (), (), None, None
    from .grids import load_grids

    g = load_grids().get(dataset, {}).get(str(spec["grid"]))
    if g is None:
        raise ValueError(f"{where}: no grid {spec['grid']!r} in the roles of {dataset}")
    sx, ag = spec.get("sex") or {}, spec.get("age") or {}
    axes = [a for a, _ in g.axes]
    if sorted(axes) != sorted([sx.get("axis"), ag.get("axis")]):
        raise ValueError(f"{where}: the weight reads the grid's axes {axes} as its sex and age")
    sex_of = {str(sx.get("male")): 1, str(sx.get("female")): 2}
    unknown_age = {str(u) for u in ag.get("unknown") or ()}
    try:
        bands = tuple(sorted(int(c) for c in g.axis_codes(ag["axis"]) if c not in unknown_age))
    except ValueError as exc:
        raise ValueError(f"{where}: an age code that is not a band's lower edge must be named unknown") from exc
    if not bands or bands[0] != 0:
        raise ValueError(f"{where}: a grid's bands are lower edges from 0")
    i_sex, i_age = axes.index(sx["axis"]), axes.index(ag["axis"])
    cells = tuple(GridCell(column, sex_of.get(codes[i_sex]), None if codes[i_age] in unknown_age else int(codes[i_age]))
                  for column, codes in g.cells)
    total, margin = (str(spec[k]).upper() if spec.get(k) else None for k in ("total", "margin"))
    return cells, bands, total, margin


def _duplicates(spec: dict[str, Any] | None, where: str) -> tuple[str, ...] | None:
    """A duplicates rule's entry-metadata columns (None: rows are not compared), with its evidence required."""
    if spec is None:
        return None
    if not spec.get("evidence"):
        raise ValueError(f"{where}: a duplicates rule needs its evidence")
    if "except" not in spec:
        return None
    return tuple(str(c).upper() for c in spec.get("except") or ())


def _duplicate_flag(spec: dict[str, Any] | None, where: str) -> tuple[str, tuple[str, ...]] | None:
    """The source's duplicate flag of a duplicates rule: (column, codes that mean "do not count")."""
    flag = (spec or {}).get("flag")
    if not flag:
        return None
    if not (flag.get("column") and flag.get("codes")):
        raise ValueError(f"{where}: a duplicate flag names its column and its codes")
    return str(flag["column"]).upper(), tuple(str(c) for c in flag["codes"])


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


#: Schema-metadata key `events_of` sets on its result: how many rows had no consolidation key (kept as events of
#: their own), as text. Absent when none.
UNKEYED = b"pegasus.unkeyed"


def events_of(table: pa.Table, event: EventType, *, flag_absent_ok: bool = False) -> pa.Table:
    """The rows of ``table`` that are events of this type, one per event.

    Duplicate entries first (a declared ``duplicates`` rule: rows equal on every column but entry metadata are one
    record, the first in file order kept; the table must then carry every column; the source's own flag drops the
    rows it marks, and its column must be in the table: ``flag_absent_ok`` is for the reader that found the form
    without it, `read_events`, never a forgotten projection), then status (which rows count), then consolidation: one
    row per distinct key, the first in file order. A row with no key (null or blank in any key column) identifies no
    event to join and is kept as an event of its own; their number is the result's `UNKEYED` metadata. Exact string
    matching: a status code is matched at the width the dataset files it.
    """
    if event.duplicates_flag:
        column, codes = event.duplicates_flag
        if column in table.column_names:
            flagged = pc.is_in(pc.utf8_trim_whitespace(pc.cast(table.column(column), pa.string())),
                               value_set=pa.array(list(codes), pa.string()))
            table = table.filter(pc.invert(pc.fill_null(flagged, False)))
        elif not flag_absent_ok:
            raise KeyError(f"{event.name}: the source's duplicate flag {column} is not in the table; select it, or the "
                           f"duplicates it marks are counted")
    if event.duplicates_except is not None and table.num_rows:
        key = [c for c in table.column_names if not c.startswith("_") and c not in event.duplicates_except]
        indexed = table.append_column("__i", pa.array(range(table.num_rows), pa.int64()))
        strings = pa.table({c: pc.cast(indexed.column(c), pa.string()) for c in key}).append_column("__i", indexed.column("__i"))
        first = strings.group_by(key, use_threads=False).aggregate([("__i", "min")])
        table = table.take(pc.take(first.column("__i_min"), pc.sort_indices(first.column("__i_min"))))
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
        unkeyed = pa.repeat(pa.scalar(False), table.num_rows)
        for c in event.consolidation_key:
            text = pc.utf8_trim_whitespace(pc.cast(table.column(c), pa.string()))
            unkeyed = pc.or_(unkeyed, pc.fill_null(pc.equal(text, ""), True))
        if isinstance(unkeyed, pa.ChunkedArray):
            unkeyed = unkeyed.combine_chunks()
        position = pa.array(range(table.num_rows), pa.int64())
        first = table.filter(pc.invert(unkeyed)).append_column("__i", pc.filter(position, pc.invert(unkeyed))).group_by(
            list(event.consolidation_key), use_threads=False).aggregate([("__i", "min")]).column("__i_min")
        keep = pa.concat_arrays([*first.chunks, pc.filter(position, unkeyed)])
        table = table.take(pc.take(keep, pc.sort_indices(keep)))
        n_unkeyed = pc.sum(unkeyed).as_py() or 0
        if n_unkeyed:
            table = table.replace_schema_metadata({**(table.schema.metadata or {}), UNKEYED: str(n_unkeyed).encode()})
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
    """A count column as integers, blank and its role's missing codes as null (SDTA's NU_TOT 0: an outbreak has two
    or more ill); any other text raises (an unknown quantity is not zero events)."""
    from .column_roles import load_column_roles

    if column not in table.column_names:
        raise KeyError(f"{event.name}: grid column {column} is not in the table")
    role = next((r for r in load_column_roles().get(f"{event.system}-{event.series}", ()) if r.column == column), None)
    text = pc.utf8_trim_whitespace(pc.cast(table.column(column), pa.string()))
    blank = pc.fill_null(pc.equal(text, ""), True)
    if role is not None and role.missing:
        blank = pc.or_(blank, pc.fill_null(pc.is_in(text, value_set=pa.array(list(role.missing), pa.string())), False))
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
    people), and so is a row whose grid holds no one and has no total. The total is the count where it is recorded
    (the Ministry's published totals are its sums); a grid that exceeds a recorded total cannot be the same people, so
    that row's total is of unknown sex and age, and a grid with no total counts its own people."""
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
    over = pc.fill_null(pc.greater(grid_sum, total), False)            # the grid contradicts the total: not allocated
    counts = [pc.if_else(over, pa.scalar(None, pa.int64()), a) for a in counts]
    grid_sum = pc.if_else(over, pa.scalar(0, pa.int64()), grid_sum)
    beyond = pc.max_element_wise(pc.subtract(pc.fill_null(total, 0), grid_sum), pa.scalar(0, pa.int64()))
    unquantified = pc.cast(pc.and_(pc.equal(grid_sum, 0), pc.is_null(total)), pa.int64())
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


def read_events(dataset: str, event: EventType, columns: Iterable[str] = (), *, records: pa.Table | None = None,
                **query_kwargs: Any) -> pa.Table:
    """The events of one type read from ``dataset`` (``period``, ``geography``, ... as `query`), or from ``records``
    already read (an extract's, `pegasus_data.extract`): the one place that assembles an event type's reading.

    It selects ``columns`` and what the rule itself reads (status, consolidation key, weight, grid, and the source's
    duplicate flag, which a form or a year may lack: then it reads without it and the flag marks none; any other missing
    column raises), or every column when the duplicates rule compares whole rows. The result is `events_of`'s, and
    for an event that is not a grid, carries ``__w``: the number of events each row stands for (`event_weights`).
    ``records`` are taken as they come: a duplicate flag they lack raises, as a forgotten projection would."""
    flag = event.duplicates_flag[0] if event.duplicates_flag else None
    if records is not None:
        table = records
    else:
        from .._query_engine.executor import query

        needed = {c for c in (*columns, event.status_column, *event.consolidation_key, event.weight, event.grid_total,
                              event.grid_margin, *(c.column for c in event.grid)) if c}
        select = None if event.duplicates_except is not None else (sorted(needed) or None)
        if select is None or flag is None:
            table = query(dataset, select=select, present="codes", **query_kwargs)
        else:
            try:
                table = query(dataset, select=sorted({*select, flag}), present="codes", **query_kwargs)
            except Exception as exc:
                if f"'{flag}' is not present" not in str(exc):
                    raise
                table = query(dataset, select=select, present="codes", **query_kwargs)
    events = events_of(table, event, flag_absent_ok=records is None)
    if event.grid:
        return events
    return events.append_column("__w", event_weights(events, event))


def count_events(
    dataset: str, name: str, *, period: object, geography: object = "BR", by: list[str] | None = None,
    records: pa.Table | None = None, **query_kwargs: Any,
) -> pa.Table:
    """Counts of one event type, optionally grouped by columns of the record; a weighted event sums its weight.
    ``records``: the event type's records already read (an extract's, `pegasus_data.extract`), counted in place of a
    query of ``period`` and ``geography``.

    A grid event's ``by`` may name `GRID_SEX` and `GRID_AGE`, and its result has a column ``unquantified``: the rows
    whose grid and total are both blank, a group whose people were not counted (`grid_events`).

    The result's metadata `UNKEYED` is the number of rows that had no consolidation key and were counted as events of
    their own; a warning says so."""
    event = event_type(dataset, name)
    if event.grid:
        record_by = [c for c in by or [] if c not in (GRID_SEX, GRID_AGE)]
        events = read_events(dataset, event, record_by, records=records, period=period, geography=geography,
                             **query_kwargs)
        long = grid_events(events, event, record_by)
        if not by:
            out = pa.table({"events": [pc.sum(long.column("events")).as_py() or 0],
                            "unquantified": [pc.sum(long.column("unquantified")).as_py() or 0]})
        else:
            out = long.group_by(list(by)).aggregate([("events", "sum"), ("unquantified", "sum")]).rename_columns(
                [*by, "events", "unquantified"])
        return out
    events = read_events(dataset, event, by or (), records=records, period=period, geography=geography, **query_kwargs)
    if not by:
        out = pa.table({"events": [pc.sum(events.column("__w")).as_py() or 0]})
    else:
        out = events.group_by(by).aggregate([("__w", "sum")]).rename_columns([*by, "events"])
    unkeyed = int((events.schema.metadata or {}).get(UNKEYED, b"0"))
    if unkeyed:
        warnings.warn(f"{dataset} {name}: {unkeyed} rows have no {'/'.join(event.consolidation_key)}; each is counted "
                      f"as an event of its own, as consolidating them into one would lose events", stacklevel=2)
        out = out.replace_schema_metadata({UNKEYED: str(unkeyed).encode()})
    return out


def field_overlap(
    dataset: str, name: str, a: dict[str, list[str]], b: dict[str, list[str]], *,
    period: object, geography: object = "BR", **query_kwargs: Any,
) -> dict[str, Any]:
    """How much two fields over one event type share, measured from records.

    A field is the events whose columns carry a code starting with one of the
    listed prefixes: ``{"CAUSABAS": ["I21"]}`` or, for "any mention",
    ``{"LINHAA": ["I21"], "LINHAB": ["I21"], ...}``. The overlap is the shared
    events over the smaller field's events (DESIGN §3.5): two fields above 0.05
    are never tested against each other as if independent. The events are read as `count_events` reads
    them (`read_events`): the source's duplicates dropped, the status applied, a weighted row counted
    for its quantity.
    """
    event = event_type(dataset, name)
    table = read_events(dataset, event, {*a, *b}, period=period, geography=geography, **query_kwargs)
    weights = table.column("__w") if "__w" in table.column_names else pa.repeat(pa.scalar(1, pa.int64()), table.num_rows)

    def members(predicate: dict[str, list[str]]) -> pa.Array:
        hit = pa.array([False] * table.num_rows)
        for column, prefixes in predicate.items():
            values = pc.utf8_upper(pc.cast(table.column(column), pa.string()))
            for prefix in prefixes:
                hit = pc.or_(hit, pc.fill_null(pc.starts_with(values, str(prefix).upper()), False))
        return hit

    def total(mask: pa.Array) -> int:
        return pc.sum(pc.if_else(mask, weights, 0)).as_py() or 0

    in_a, in_b = members(a), members(b)
    n_a, n_b, shared = total(in_a), total(in_b), total(pc.and_(in_a, in_b))
    smaller = min(n_a, n_b)
    return {"events": pc.sum(weights).as_py() or 0, "a": n_a, "b": n_b, "shared": shared,
            "overlap": (shared / smaller) if smaller else None}
