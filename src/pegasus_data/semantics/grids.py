"""A variable spread over columns: a grid of named axes (ADR-0158).

Some forms put one variable in many columns, each column a cell of its axes: SINAN-SDTA counts an outbreak's ill by
sex × age band (NU_1_M_NU … NU_IG_IGN), CNES-ST flags each attendance type × payer (AP01CV01 … AP07CV07). The code
lives in the column's name. A role file declares such a family under ``grids:``:

    grids:
      attendance:
        value: flag
        evidence: ...
        axes:
          attendance: {'01': INTERNACAO, '02': ATENDIMENTO AMBULATORIAL, ...}
          payer: {'01': SUS, ...}
        cells:
          AP01CV01: {attendance: '01', payer: '01'}

Every cell is a declared column, every axis value one of its axis's codes, every cell a distinct combination.
`grid_table` reads a grid long: one row per (record, cell), the axes' codes as columns, the cell's raw value as
``value``. An event that counts people from a grid names it in its weight (`event_types`, ADR-0156).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .epoch import curated


@dataclass(frozen=True, slots=True)
class ColumnGrid:
    dataset: str
    name: str
    value: str                                   # what a cell holds: count, flag
    axes: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]   # (axis, ((code, label), ...)), in declared order
    cells: tuple[tuple[str, tuple[str, ...]], ...]              # (column, one code per axis)
    evidence: str | None = None

    def axis_codes(self, axis: str) -> dict[str, str]:
        return dict(next(codes for a, codes in self.axes if a == axis))

    def as_dict(self) -> dict[str, Any]:
        names = [a for a, _ in self.axes]
        return {"dataset": self.dataset, "name": self.name, "value": self.value, "evidence": self.evidence,
                "axes": {a: dict(codes) for a, codes in self.axes},
                "cells": {col: dict(zip(names, codes, strict=True)) for col, codes in self.cells}}


@curated
def load_grids() -> dict[str, dict[str, ColumnGrid]]:
    """Every role file's grids, validated against its columns."""
    from .column_roles import load_column_roles, roles_dir
    from .curation import read_yaml

    declared = load_column_roles()
    out: dict[str, dict[str, ColumnGrid]] = {}
    folder = roles_dir()
    for path in sorted(folder.glob("*.yml")) if folder.exists() else ():
        if path.name.endswith(".draft.yml"):
            continue
        body = read_yaml(path, shared=True)
        if not body.get("grids"):
            continue
        dataset = str(body.get("dataset") or path.stem).upper()
        columns = {c.column for c in declared.get(dataset, ())}
        for name, spec in body["grids"].items():
            out.setdefault(dataset, {})[str(name)] = _grid(dataset, str(name), spec or {}, columns, path.name)
    return out


def _grid(dataset: str, name: str, spec: dict[str, Any], columns: set[str], where: str) -> ColumnGrid:
    def bad(message: str) -> ValueError:
        return ValueError(f"{where}: grid {name}: {message}")

    axes = tuple((str(a), tuple((str(c), str(lab)) for c, lab in (codes or {}).items()))
                 for a, codes in (spec.get("axes") or {}).items())
    if not axes or any(not codes for _, codes in axes):
        raise bad("a grid names its axes, each with its codes")
    names = [a for a, _ in axes]
    known = {a: {c for c, _ in codes} for a, codes in axes}
    cells, seen = [], set()
    for column, at in (spec.get("cells") or {}).items():
        column = str(column).upper()
        if column not in columns:
            raise bad(f"cell {column} is not a declared column of {dataset}")
        if set(at or {}) != set(names):
            raise bad(f"cell {column} gives {sorted(at or {})}, not one code per axis {names}")
        codes = tuple(str(at[a]) for a in names)
        if any(c not in known[a] for a, c in zip(names, codes, strict=True)):
            raise bad(f"cell {column}: {dict(zip(names, codes, strict=True))} uses a code its axis does not list")
        if codes in seen:
            raise bad(f"cell {column} repeats {dict(zip(names, codes, strict=True))}")
        seen.add(codes)
        cells.append((column, codes))
    if not cells:
        raise bad("a grid has cells")
    return ColumnGrid(dataset, name, str(spec.get("value") or "count"), axes, tuple(cells), spec.get("evidence"))


def _key(dataset: str) -> str:
    from .column_roles import roles

    return str(roles(dataset)[0]["dataset"]) if roles(dataset) else dataset.upper().replace(".", "-")


def grid(dataset: str, name: str) -> ColumnGrid:
    found = load_grids().get(_key(dataset), {})
    if name not in found:
        raise KeyError(f"{dataset!r} declares no grid {name!r}; it declares {sorted(found)}")
    return found[name]


def grids(dataset: str) -> list[dict[str, Any]]:
    """The grids a dataset's role file declares (``pegasus-data grids <dataset>``)."""
    return [g.as_dict() for g in load_grids().get(_key(dataset), {}).values()]


def melt(table: pa.Table, g: ColumnGrid, keep: list[str] | None = None) -> pa.Table:
    """``table``'s grid columns read long: one row per (record, cell), the axes' codes, the cell's raw ``value``."""
    keep = list(keep or [])
    names = [a for a, _ in g.axes]
    missing = [c for c, _ in g.cells if c not in table.column_names]
    if missing:
        raise KeyError(f"grid {g.name}: columns {missing[:5]} are not in the table")
    n = table.num_rows
    parts = [pa.table({**{k: table.column(k) for k in keep},
                       **{a: pa.repeat(pa.scalar(c, pa.string()), n) for a, c in zip(names, codes, strict=True)},
                       "value": pc.cast(table.column(column), pa.string())})
             for column, codes in g.cells]
    return pa.concat_tables(parts)


def grid_table(dataset: str, name: str, *, period: object, geography: object = "BR", keep: list[str] | None = None,
               **query_kwargs: Any) -> pa.Table:
    """A grid read long from the records of ``period`` and ``geography``: ``keep`` columns, the axes, ``value``."""
    from .._query_engine.executor import query

    g = grid(dataset, name)
    table = query(dataset, period=period, geography=geography, select=list(dict.fromkeys([*(keep or []), *(c for c, _ in g.cells)])),
                  present="codes", **query_kwargs)
    return melt(table, g, keep)
