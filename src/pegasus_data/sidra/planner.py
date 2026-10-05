"""From what a person wants to the requests SIDRA will serve.

A `Selection` names a table, variables, periods, a territorial level with a scope, and the categories
wanted of each classification. `plan()` checks it against the registry (a bad table, variable,
category or level is an error before any request) and cuts it into `Chunk`s that respect the limits
measured on 2026-10-04 (DATA_SOURCES, "SIDRA's limits"):

1. at most about 50,000 values per request, counted as localities × variables × periods × the
   categories chosen of each classification. A classification left out is fixed at its Total by the
   server and multiplies nothing. The ceiling used is 48,000;
2. explicit ``localidades`` and ``classificacao`` lists fail with HTTP 500 once their text passes about
   4.1 KB, so each is held under 3,500 characters, and a whole state or region is named by a selector
   (``N6[N3[27]]``) instead of a list of its municipalities;
3. a URL of about 8 KB gets an HTML page with status 200, so a URL is held under 6,000 characters.

Cuts are made in this order: states (several small ones share a request), then the dimension with the
most categories (classifications, periods, variables), then, only for an explicit list, municipalities.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .client import BASE
from .registry import Registry

VALUE_CEILING = 48_000
LIST_TEXT_CEILING = 3_500
URL_CEILING = 6_000
ALL = "all"

__all__ = ["ALL", "Chunk", "PlanError", "Selection", "plan", "validate"]


class PlanError(ValueError):
    """The selection cannot be asked of SIDRA as written."""


@dataclass(slots=True)
class Selection:
    """What to fetch.

    ``classifications`` maps a classification id to ``"all"`` (every category, Totals included), a list
    of category ids, or ``"total"``/absent (fixed at the Total by the server, costing nothing).
    ``scope`` is ``"all"`` (every locality of the level), a list of 2-digit state codes (level N6 only)
    or a list of locality ids.
    """

    table: int
    variables: Sequence[int]
    periods: Sequence[str]
    level: str = "N6"
    scope: str | Sequence[str] = ALL
    classifications: dict[int, str | Sequence[int]] = field(default_factory=dict)
    states: bool = False           # scope lists 2-digit state codes rather than locality ids


@dataclass(frozen=True, slots=True)
class Chunk:
    """One request."""

    table: int
    variables: tuple[int, ...]
    periods: tuple[str, ...]
    localities: str                                   # the ``localidades`` parameter
    classification: str                               # the ``classificacao`` parameter ('' = all Totals)
    values: int                                       # the estimated number of values

    @property
    def url(self) -> str:
        url = (f"{BASE}/{self.table}/periodos/{'|'.join(self.periods)}/variaveis/"
               f"{'|'.join(map(str, self.variables))}?localidades={self.localities}")
        return url + (f"&classificacao={self.classification}" if self.classification else "")


@dataclass(slots=True)
class _Unit:
    """A piece of the selection being cut: lists per dimension and the locality side."""

    variables: list[int]
    periods: list[str]
    cats: dict[int, list[int]]                        # explicit categories per classification
    all_cats: set[int]                                # classifications requested as 'all' and not yet cut
    states: list[str] | None                          # N6 by state
    ids: list[str] | None                             # explicit localities
    n_localities: int

    def values(self, sizes: dict[int, int]) -> int:
        n = self.n_localities * len(self.variables) * len(self.periods)
        for cid in self.cats:
            n *= len(self.cats[cid]) if cid not in self.all_cats else sizes[cid]
        return n


def validate(selection: Selection, registry: Registry) -> dict[str, Any]:
    """Check a selection against the registry; return the table's facts the plan needs."""
    tab = registry.tab(selection.table)
    if tab is None or tab["metadata_sha256"] is None:
        raise PlanError(f"table {selection.table} is not in the registry; run `pegasus-data sidra scan` or `sidra show`")
    known_vars = {v["id"] for v in registry.variables(selection.table)}
    missing = [v for v in selection.variables if v not in known_vars]
    if missing:
        raise PlanError(f"table {selection.table} has no variable(s) {missing}; it has {sorted(known_vars)}")
    if selection.level not in tab["levels"]:
        raise PlanError(f"table {selection.table} is not published at {selection.level}; levels: {tab['levels']}")
    classes = {c["id"]: c for c in registry.classifications(selection.table)}
    sizes: dict[int, int] = {}
    for cid, chosen in selection.classifications.items():
        if cid not in classes:
            raise PlanError(f"table {selection.table} has no classification {cid}; it has {sorted(classes)}")
        known = {c["id"] for c in registry.categories(selection.table, cid)}
        if isinstance(chosen, str):
            if chosen not in (ALL, "total"):
                raise PlanError(f"classification {cid}: {chosen!r} is not 'all', 'total' or a list of categories")
        else:
            bad = [c for c in chosen if c not in known]
            if bad:
                raise PlanError(f"classification {cid} of table {selection.table} has no categories {bad[:8]}")
        sizes[cid] = classes[cid]["n_categories"]
    return {"tab": tab, "sizes": sizes, "classes": classes}


def _class_text(cats: dict[int, list[int]], all_cats: set[int]) -> str:
    return "|".join(f"{cid}[{ALL if cid in all_cats else ','.join(map(str, ids))}]" for cid, ids in cats.items())


def _state_selector(states: Sequence[str]) -> str:
    return f"N6[N3[{','.join(states)}]]"


def _locality_text(unit: _Unit, level: str) -> str:
    if unit.states is not None:
        return _state_selector(unit.states)
    if unit.ids is not None:
        return f"{level}[{','.join(unit.ids)}]"
    return f"{level}[{ALL}]"


def _fill(items: list[Any], values: int, ceiling: int) -> list[list[Any]]:
    """Cut ``items`` (which together cost ``values``) into pieces that each fill the ceiling, the last taking the
    remainder: ceil(values / ceiling) requests, not the more that equal pieces cost. At least two pieces, so a
    unit cut for the length of its text, not its values, still gets smaller."""
    per = max(1, min(int(ceiling // (values / len(items))), math.ceil(len(items) / 2)))
    return [items[i:i + per] for i in range(0, len(items), per)]


def plan(selection: Selection, registry: Registry, *, per_state: dict[str, int] | None = None,
         locality_total: int | None = None, ceiling: int = VALUE_CEILING) -> list[Chunk]:
    """Cut ``selection`` into requests. ``per_state`` is the number of N6 localities of the table in each
    state (from its ``/localidades/N6``); ``locality_total`` the count at the level otherwise."""
    facts = validate(selection, registry)
    sizes: dict[int, int] = facts["sizes"]
    cats: dict[int, list[int]] = {}
    all_cats: set[int] = set()
    for cid, chosen in selection.classifications.items():
        if isinstance(chosen, str):
            if chosen == ALL:
                cats[cid] = [c["id"] for c in registry.categories(selection.table, cid)]
                all_cats.add(cid)
            continue                                       # "total": left out, fixed at the Total by the server
        cats[cid] = list(chosen)

    base: dict[str, Any] = {"variables": list(selection.variables), "periods": list(selection.periods), "cats": cats, "all_cats": all_cats}
    units: list[_Unit] = []
    scope = selection.scope
    if selection.level == "N6" and (scope == ALL or selection.states):
        if per_state is None:
            raise PlanError("planning N6 by state needs the table's municipalities per state (`/localidades/N6`)")
        wanted = sorted(per_state) if scope == ALL else sorted(map(str, scope))
        missing = [s for s in wanted if s not in per_state]
        if missing:
            raise PlanError(f"table {selection.table} has no municipalities in state(s) {missing}")
        # states are packed into a request while the values stay under the ceiling
        group: list[str] = []
        count = 0
        per_row = max(1, _Unit(**base, states=None, ids=None, n_localities=1).values(sizes))
        for s in wanted:
            if group and (count + per_state[s]) * per_row > ceiling:
                units.append(_Unit(**base, states=group, ids=None, n_localities=count))
                group, count = [], 0
            group.append(s)
            count += per_state[s]
        units.append(_Unit(**base, states=group, ids=None, n_localities=count))
    elif scope == ALL:
        n = locality_total if locality_total is not None else 1
        units.append(_Unit(**base, states=None, ids=None, n_localities=n))
    else:
        ids = [str(i) for i in scope]
        units.append(_Unit(**base, states=None, ids=ids, n_localities=len(ids)))

    chunks: list[Chunk] = []
    pending = list(units)
    while pending:
        unit = pending.pop(0)
        values = unit.values(sizes)
        class_text = _class_text(unit.cats, unit.all_cats)
        loc_text = _locality_text(unit, selection.level)
        text_ok = (len(class_text) <= LIST_TEXT_CEILING and
                   (unit.ids is None or len(loc_text) <= LIST_TEXT_CEILING))
        url_ok = len(Chunk(selection.table, tuple(unit.variables), tuple(unit.periods), loc_text, class_text, values).url) <= URL_CEILING
        if values <= ceiling and text_ok and url_ok:
            chunks.append(Chunk(selection.table, tuple(unit.variables), tuple(unit.periods), loc_text, class_text, values))
            continue
        pending = _cut(unit, sizes, values, ceiling) + pending
    return chunks


def _cut(unit: _Unit, sizes: dict[int, int], values: int, ceiling: int) -> list[_Unit]:
    """Split a unit that is over a limit along its widest dimension that can still be cut."""
    def with_(**change: Any) -> _Unit:
        data = {"variables": unit.variables, "periods": unit.periods, "cats": unit.cats, "all_cats": unit.all_cats,
                "states": unit.states, "ids": unit.ids, "n_localities": unit.n_localities, **change}
        return _Unit(**data)

    if unit.states is not None and len(unit.states) > 1:                   # states first
        pieces = _fill(unit.states, values, ceiling)
        return [with_(states=p, n_localities=math.ceil(unit.n_localities * len(p) / len(unit.states))) for p in pieces]
    candidates: list[tuple[int, str, Any]] = []
    for cid, ids in unit.cats.items():
        n = sizes[cid] if cid in unit.all_cats else len(ids)
        if len(ids) > 1:
            candidates.append((n, "class", cid))
    if len(unit.periods) > 1:
        candidates.append((len(unit.periods), "periods", None))
    if len(unit.variables) > 1:
        candidates.append((len(unit.variables), "variables", None))
    if candidates:
        _, kind, cid = max(candidates, key=lambda c: c[0])
        if kind == "class":
            pieces = _fill(unit.cats[cid], values, ceiling)
            out = []
            for p in pieces:
                cats = dict(unit.cats)
                cats[cid] = p
                out.append(with_(cats=cats, all_cats=unit.all_cats - {cid}))
            return out
        if kind == "periods":
            return [with_(periods=p) for p in _fill(unit.periods, values, ceiling)]
        return [with_(variables=p) for p in _fill(unit.variables, values, ceiling)]
    if unit.ids is not None and len(unit.ids) > 1:
        return [with_(ids=p, n_localities=len(p)) for p in _fill(unit.ids, values, ceiling)]
    if unit.states is not None and unit.states:
        # a single state still too large with nothing else to cut: only its municipalities remain
        raise PlanError(f"state {unit.states[0]} alone exceeds the ceiling with every other dimension at one value "
                        f"({values} values); name its municipalities explicitly")
    raise PlanError(f"cannot cut a request of {values} values below the ceiling {ceiling}")
