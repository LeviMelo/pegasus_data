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

__all__ = ["axis_map", "build_series", "check_axes", "declared_series", "fetch_series", "series_report", "series_values", "validate_series"]


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


def _sum_over(table: pa.Table, keys: list[str]) -> pa.Table:
    """Sum ``value`` over the rows that share ``keys``. A part with no figure makes the sum missing (never the sum of
    what was left): its status is that of the first missing part. Every other column is constant within a group."""
    others = [c for c in table.column_names if c not in keys and c not in ("value", "status")]
    work = table.append_column("_miss", pc.is_null(table.column("value")))
    work = work.append_column("_why", pc.if_else(pc.is_null(table.column("value")), table.column("status"), pa.scalar(None, pa.string())))
    grouped = work.group_by(keys, use_threads=False).aggregate(
        [("value", "sum"), ("_miss", "any"), ("_why", "min"), *[(c, "min") for c in others]])
    value = pc.if_else(grouped.column("_miss_any"), pa.scalar(None, pa.float64()), grouped.column("value_sum"))
    status = pc.if_else(grouped.column("_miss_any"), grouped.column("_why_min"),
                        pc.if_else(pc.equal(grouped.column("value_sum"), 0.0), pa.scalar("zero"), pa.scalar("value")))
    out = {k: grouped.column(k) for k in keys}
    out.update({c: grouped.column(f"{c}_min") for c in others})
    out.update(value=value, status=status)
    return pa.table(out).select([c for c in table.column_names if c in out])


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
        part = pa.table(cols)
        many_to_one = any(len(set(m.values())) < len(m) for _, m in dims.values())          # e.g. five income classes -> one band
        if source.get("sum") or many_to_one:
            part = _sum_over(part, ["locality", "level", "period", *axes_all])
        parts.append(part)
    out = pa.concat_tables(parts, promote_options="permissive")
    if len(sources) == 1:                                      # nothing to arbitrate between: no claim competes
        return out.append_column("selected", pa.array([True] * out.num_rows, pa.bool_()))
    # a claim with no figure never outranks one with a figure: rank by priority, with the unvalued ones last
    rank = pc.if_else(pc.is_valid(out.column("value")), out.column("priority"), pc.add(out.column("priority"), 1000))
    ranked = out.append_column("_row", pa.array(range(out.num_rows), pa.int64())).append_column("_rank", rank)
    for axis in axes_all:                      # a join never matches null keys: a measure without that axis (a total) is keyed by ""
        ranked = ranked.append_column(f"_k_{axis}", pc.fill_null(ranked.column(axis), ""))
    joint = ["locality", "level", "period", "measure", *[f"_k_{a}" for a in axes_all]]
    best = ranked.group_by(joint, use_threads=False).aggregate([("_rank", "min")])
    joined = ranked.join(best, keys=joint, join_type="left outer", use_threads=False)
    joined = joined.append_column("selected", pc.equal(joined.column("_rank"), joined.column("_rank_min"))).sort_by("_row")
    joined = joined.drop_columns([f"_k_{a}" for a in axes_all])
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


def series_values(sidra: Sidra, name: str, measure: str = "value", where: dict[str, list[str]] | None = None) -> pa.Table:
    """One number per place and period from a series, for a field: the ``selected`` claim of ``measure``, restricted to
    the categories in ``where`` (axis -> canonical codes) and summed over them. A series with axes needs ``where``:
    which categories to take is the caller's statement, never a default."""
    table = build_series(sidra, name)
    table = table.filter(pc.and_(table.column("selected"), pc.equal(table.column("measure"), measure)))
    if table.num_rows == 0:
        raise LookupError(f"series {name!r} has no measure {measure!r}")
    axes = [a for a in declared_axes() if a in table.column_names and pc.any(pc.is_valid(table.column(a))).as_py()]
    if axes and not where:
        raise ValueError(f"series {name!r} carries {axes}: name the categories wanted (`where`)")
    for axis, codes in (where or {}).items():
        table = table.filter(pc.is_in(table.column(axis), pa.array([str(c) for c in codes], pa.string())))
        if table.num_rows == 0:
            raise LookupError(f"series {name!r}: no rows for {axis} in {codes}")
    table = table.drop_columns([a for a in declared_axes() if a in table.column_names])
    keys = ["locality", "level", "period"]
    return _sum_over(table, keys).select(["locality", "period", "value", "status", "unit", "table", "variable"])


def series_report(sidra: Sidra, name: str) -> dict[str, Any]:
    """What a series declares (comparability, gaps) and what it holds: per period and measure, the places with a
    figure and the places without one, by IBGE's reason. A gap is counted here, never discovered downstream."""
    spec = declared_series()[name]
    table = build_series(sidra, name)
    table = table.filter(table.column("selected"))
    coverage = []
    pairs = sorted({(r["period"], r["measure"]) for r in table.select(["period", "measure"]).to_pylist()})
    for period, measure in pairs:
        part = table.filter(pc.and_(pc.equal(table.column("period"), period), pc.equal(table.column("measure"), measure)))
        missing = part.filter(pc.is_null(part.column("value")))
        reasons: dict[str, int] = {}
        for status in missing.column("status").to_pylist():
            reasons[status] = reasons.get(status, 0) + 1
        coverage.append({"period": period, "measure": measure, "rows": part.num_rows, "with_value": part.num_rows - missing.num_rows,
                         "missing": reasons, "total": pc.sum(part.column("value")).as_py()})
    return {"series": name, "comparability": spec.get("comparability"), "gaps": spec.get("gaps"), "coverage": coverage}
