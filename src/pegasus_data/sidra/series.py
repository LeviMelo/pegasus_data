"""Series stitched across tables and census vintages, from the stored facts.

``curation/sidra/series.yml`` declares a series as sources: a table, a variable, periods, the axes it
carries (``dims``) and a priority. ``curation/sidra/axes.yml`` says what each source's categories mean in
a common vocabulary (sex, race/colour, the single year of age), so tables that name the same thing with
different category ids (sex is 4/5 in one table and 92956/92957 in another) land in one column.

Where two sources claim the same cell, both rows are kept and ``selected`` marks the one that the series'
rule prefers (the lowest priority number): a conflict between sources is recorded, never resolved silently.
A source's own marks (``status``) travel with its values: a missing figure is a null with a reason.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .session import Sidra

__all__ = ["axis_map", "build_series", "check_axes", "declared_series", "fetch_series", "validate_series"]


def _curation(name: str) -> dict[str, Any]:
    import yaml

    from ..config import curation_root

    return yaml.safe_load((Path(curation_root()) / "sidra" / name).read_text("utf-8")) or {}


def declared_series() -> dict[str, dict[str, Any]]:
    return dict(_curation("series.yml").get("series") or {})


def declared_axes() -> dict[str, dict[str, Any]]:
    return dict(_curation("axes.yml").get("axes") or {})


def axis_map(sidra: Sidra, table: int, axis: str, class_id: int) -> dict[int, Any]:
    """Category id → canonical code for ``axis`` as carried by ``class_id`` in ``table``.

    An axis is either a ``map`` (category id → code, curated and checked against IBGE's names by
    `check_axes`) or a ``rule``: ``single_year_age`` reads the category names ("Menos de 1 ano" is 0,
    "n ano(s)" is n, "100 anos ou mais" is 100) and leaves groups and months out.
    """
    sidra.ensure(table)
    spec = declared_axes()[axis]
    if spec.get("rule") == "single_year_age":
        out: dict[int, Any] = {}
        for cat in sidra.registry.categories(table, class_id):
            name = cat["name"].strip()
            if name == "Menos de 1 ano":
                out[cat["id"]] = 0
            elif name == "100 anos ou mais":
                out[cat["id"]] = 100
            elif m := re.fullmatch(r"(\d+) anos?", name):
                out[cat["id"]] = int(m.group(1))
        if sorted(out.values()) != list(range(101)):
            raise ValueError(f"table {table}, classification {class_id}: single years of age are not exactly 0..100")
        return out
    codes = (spec.get("classifications") or {}).get(class_id)
    if codes is None:
        raise KeyError(f"axis {axis!r} has no map for classification {class_id} (table {table}); add it to curation/sidra/axes.yml")
    known = {c["id"] for c in sidra.registry.categories(table, class_id, synthetic=True)}
    return {int(k): v for k, v in codes.items() if int(k) in known}


def _periods(sidra: Sidra, source: dict[str, Any]) -> list[str]:
    known = sidra.periods(source["table"])
    wanted = source.get("periods", "all")
    if wanted == "all":
        return known
    chosen = [str(p) for p in wanted]
    missing = [p for p in chosen if p not in known]
    if missing:
        raise ValueError(f"series source {source['id']}: table {source['table']} has no period(s) {missing}")
    return chosen


def _dim_picks(sidra: Sidra, source: dict[str, Any]) -> tuple[dict[int, list[int]], dict[str, tuple[int, dict[int, Any]]]]:
    picks: dict[int, list[int]] = {}
    dims: dict[str, tuple[int, dict[int, Any]]] = {}
    for axis, class_id in (source.get("dims") or {}).items():
        mapping = axis_map(sidra, source["table"], axis, int(class_id))
        picks[int(class_id)] = [i for i, code in mapping.items() if code != "total"] if source.get("drop_totals", True) else list(mapping)
        dims[axis] = (int(class_id), mapping)
    for class_id, cats in (source.get("picks") or {}).items():
        picks[int(class_id)] = [int(c) for c in cats]
    return picks, dims


def _sources(name: str, only: list[str] | None) -> list[dict[str, Any]]:
    sources = declared_series()[name]["sources"]
    chosen = [s for s in sources if not only or s["id"] in only]
    if only and len(chosen) != len(set(only)):
        raise KeyError(f"series {name!r} has no source(s) {sorted(set(only) - {s['id'] for s in sources})}")
    return chosen


def fetch_series(sidra: Sidra, name: str, log=print, only: list[str] | None = None) -> list[dict[str, Any]]:
    """Plan and fetch every source of a series, or just those named in ``only`` (resumable)."""
    reports = []
    for source in _sources(name, only):
        picks, _ = _dim_picks(sidra, source)
        selection = sidra.selection(source["table"], variables=[int(source["variable"])], periods=_periods(sidra, source),
                                    level=source.get("level", "N6"), classifications=picks)
        reports.append({"source": source["id"], **sidra.fetch(selection, log=log)})
        if source.get("dims"):
            # the table's own totals, to check the cells against (validate_series)
            totals = sidra.selection(source["table"], variables=[int(source["variable"])], periods=_periods(sidra, source),
                                     level=source.get("level", "N6"))
            reports.append({"source": f"{source['id']}:totals", **sidra.fetch(totals, log=log)})
    return reports


def build_series(sidra: Sidra, name: str, only: list[str] | None = None) -> pa.Table:
    """The series as one long table: locality, level, period, canonical axes, measure (numerator or denominator,
    where a series has both), value, status, unit, source, role, priority, selected. Built from stored facts only."""
    sources = _sources(name, only)
    parts: list[pa.Table] = []
    axes_all = sorted({a for s in sources for a in (s.get("dims") or {})})
    for source in sources:
        table, variable = int(source["table"]), int(source["variable"])
        picks, dims = _dim_picks(sidra, source)
        facts = sidra.slice(table, variables=[variable], periods=_periods(sidra, source), picks=picks, level=source.get("level", "N6"))
        cols: dict[str, Any] = {"locality": facts.column("locality"), "level": facts.column("level"), "period": facts.column("period")}
        for axis in axes_all:
            if axis in dims:
                class_id, mapping = dims[axis]
                ids = pa.array(list(mapping), pa.int64())
                values = pa.array(list(mapping.values()))
                cols[axis] = pc.take(values, pc.index_in(facts.column(f"c{class_id}"), ids))
            else:
                cols[axis] = pa.nulls(facts.num_rows, pa.string())
        n = facts.num_rows
        unit = next((v["unit"] for v in sidra.registry.variables(table) if v["id"] == variable), None)
        cols.update(measure=pa.array([source.get("measure", "value")] * n, pa.string()), value=facts.column("value"), status=facts.column("status"),
                    unit=pa.array([unit] * n, pa.string()), source=pa.array([source["id"]] * n, pa.string()),
                    table=pa.array([table] * n, pa.int32()), variable=pa.array([variable] * n, pa.int32()),
                    role=pa.array([source.get("role")] * n, pa.string()), priority=pa.array([int(source.get("priority", 1))] * n, pa.int32()))
        parts.append(pa.table(cols))
    out = pa.concat_tables(parts, promote_options="permissive")
    if len(sources) == 1:                                      # nothing to arbitrate between: no claim competes
        return out.append_column("selected", pa.array([True] * out.num_rows, pa.bool_()))
    keys = ["locality", "level", "period", "measure", *axes_all]
    # a claim with no figure never outranks one with a figure: rank by priority, with the unvalued ones last
    rank = pc.if_else(pc.is_valid(out.column("value")), out.column("priority"), pc.add(out.column("priority"), 1000))
    ranked = out.append_column("_row", pa.array(range(out.num_rows), pa.int64())).append_column("_rank", rank)
    best = ranked.group_by(keys, use_threads=False).aggregate([("_rank", "min")])
    joined = ranked.join(best, keys=keys, join_type="left outer", use_threads=False)
    joined = joined.append_column("selected", pc.equal(joined.column("_rank"), joined.column("_rank_min"))).sort_by("_row")
    return joined.drop_columns(["_row", "_rank", "_rank_min"])


def validate_series(sidra: Sidra, name: str, only: list[str] | None = None) -> list[dict[str, Any]]:
    """For each source that carries axes: do its cells add up to the table's own Total, municipality by
    municipality and period by period? A mismatch is reported with examples; a null cell is skipped, and
    the municipalities whose total is itself null are counted apart."""
    out = []
    for source in _sources(name, only):
        if not source.get("dims"):
            continue
        table, variable = int(source["table"]), int(source["variable"])
        periods = _periods(sidra, source)
        picks, _ = _dim_picks(sidra, source)
        cells = sidra.slice(table, variables=[variable], periods=periods, picks=picks, level=source.get("level", "N6"))
        totals = sidra.slice(table, variables=[variable], periods=periods, level=source.get("level", "N6"))
        sums = cells.group_by(["locality", "period"]).aggregate([("value", "sum"), ("value", "count_distinct")])
        published = {(r["locality"], r["period"]): r["value"] for r in totals.select(["locality", "period", "value"]).to_pylist()}
        mismatched, no_total, checked = [], 0, 0
        for r in sums.to_pylist():
            total = published.get((r["locality"], r["period"]))
            if total is None:
                no_total += 1
                continue
            checked += 1
            if r["value_sum"] is not None and abs(r["value_sum"] - total) > 1e-6:
                mismatched.append((r["locality"], r["period"], r["value_sum"], total))
        residual: dict[str, float] = {}
        for _, period, cells_sum, total in mismatched:
            residual[period] = residual.get(period, 0.0) + (total - cells_sum)
        out.append({"source": source["id"], "checked": checked, "mismatched": len(mismatched), "total_missing": no_total,
                    "residual_by_period": residual,                      # total minus the cells: persons in no listed category
                    "cells_above_total": sum(1 for m in mismatched if m[2] > m[3]), "examples": mismatched[:3]})
    return out


def check_axes(sidra: Sidra) -> list[dict[str, str]]:
    """Every curated axis map entry against IBGE's category name, wherever the registry has the category."""
    problems = []
    for axis, spec in declared_axes().items():
        patterns = {code: re.compile(p) for code, p in (spec.get("names") or {}).items()}
        for class_id, mapping in (spec.get("classifications") or {}).items():
            for cat, code in mapping.items():
                rows = sidra.registry.db.execute("SELECT DISTINCT name, synthetic FROM category WHERE class_id = ? AND id = ?", (class_id, cat)).fetchall()
                for name, synthetic in rows:
                    if synthetic and code == "total":                  # IBGE's implicit total (id 0) has no name to match
                        continue
                    if code not in patterns or not patterns[code].search(name):
                        problems.append({"axis": axis, "classification": str(class_id), "category": str(cat), "maps_to": str(code), "ibge_name": name})
    return problems
