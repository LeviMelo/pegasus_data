"""The cube: one measure observed over place × period × strata, the one space × time object (docs/plans/cubes.md).

A cube is named by where it comes from, never curated by hand: ``sidra:5938/37`` is IBGE's table 5938, variable 37,
as soon as the SIDRA registry knows the table; ``series:households_sewer/numerator`` is a measure of a series stitched
across census tables (`sidra.series`). Its rows are long facts in one shape, whatever the adapter:

    place int64 · period str · <one column per stratum kept> · value float64 · status str · unit str · source str

* ``place`` is the place's code at the cube's level: a municipality's IBGE 7 digits, a state's 2, the country 0. The
  level is in the schema metadata (``pegasus.place_level``), with ``pegasus.period_grain`` and the manifest.
* ``period`` is the period's start as text at the grain: ``2021``, ``2021-03``, ``2021-03-15``, ``2021-W09``.
* ``status`` is one vocabulary: ``value``; ``zero`` (an absolute zero); ``not_applicable``, ``not_available``,
  ``suppressed`` (no value, with the source's reason); ``unknown_symbol``; ``incomplete`` (a roll-up missing a part,
  so no value rather than a short sum). A value is never invented for a cell the source did not give.
* A stratum column holds the source's code (a SIDRA category id); its ``<stratum>_label`` the source's words, joined
  at read, never stored apart from the code.

What may be summed is the source's statement, not a guess: SIDRA's ``summarização`` says along which of period and
territory a variable adds up. A roll-up the source does not allow is refused (`AggregationRefused`), and a roll-up over a
part without a value is ``incomplete``, never a partial total.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa

from .measures import AggregationRefused

__all__ = ["STATUSES", "cube", "cube_sources"]

#: The one status vocabulary of every cube (SIDRA's markers, and what a roll-up adds).
STATUSES = ("value", "zero", "not_applicable", "not_available", "suppressed", "empty", "unknown_symbol", "incomplete")
#: The statuses that carry a number.
NUMBERED = ("value", "zero")
#: Place levels and SIDRA's territorial level for each.
LEVELS = {"municipality": "N6", "uf": "N3", "country": "N1"}


def cube(source: str, *, place: str = "municipality", by: Sequence[str] = (), where: Mapping[str, Sequence[Any]] | None = None,
         periods: Sequence[str | int] | None = None, labels: bool = True, settings: Any = None,
         at: str | None = None, time: str | None = None, grain: str | None = None, condition: object = None,
         measure: str | None = None) -> pa.Table:
    """The cube ``source`` at ``place`` level (``municipality``, ``uf``, ``country``), keeping the strata named in ``by``
    and the categories named in ``where``; every other stratum is the source's Total. ``periods`` restricts the periods.

    ``source`` is ``<adapter>:<id>``: ``sidra:<table>/<variable>``, ``series:<name>/<measure>`` or
    ``records:<dataset>/<event type>`` (`cube_sources`). A records cube also takes ``at`` (whose place: one of the
    dataset's geography bindings, its default when left out), ``time`` (which date: one of its time bindings) and ``grain``
    (``month`` or ``year``); its ``where`` is the record's own codes ({column: [codes]}) and ``condition`` clauses on roles
    (`pegasus_data.conditions`). ``records:<dataset>/rows`` counts the records of a dataset that is no event source (a
    water sample, a sale, a dose row), or sums its numeric column ``measure``. The facts must be held or fetchable; a cube
    of nothing raises, never returns an empty table that could pass for an empty result.
    """
    from .config import load_settings

    if place not in LEVELS:
        raise ValueError(f"place must be one of {sorted(LEVELS)}, got {place!r}")
    kind, _, ident = source.partition(":")
    adapter = _ADAPTERS.get(kind)
    if adapter is None or not ident:
        raise ValueError(f"a cube is <adapter>:<id> with adapter one of {sorted(_ADAPTERS)}, got {source!r}")
    options = {k: v for k, v in (("at", at), ("time", time), ("grain", grain), ("condition", condition),
                                 ("measure", measure)) if v is not None}
    if options and kind != "records":
        raise ValueError(f"{sorted(options)} apply to records cubes only")
    settings = settings or load_settings()
    if kind == "records":
        # A records cube reads many records; it is kept by the request and the version of what it was read from.
        request = {"place": place, "by": list(by), "where": dict(where or {}), "periods": [str(p) for p in periods or []],
                   **dict(options)}
        return _cached(settings, f"records-{ident.replace('/', '-')}", request,
                       lambda: adapter(ident, place=place, by=list(by), where=dict(where or {}), periods=periods,
                                       labels=labels, settings=settings, **options),
                       stamp=lambda digest: _records_stamp(settings, ident.partition("/")[0], digest))
    return adapter(ident, place=place, by=list(by), where=dict(where or {}), periods=periods, labels=labels,
                   settings=settings, **options)


def cube_sources() -> dict[str, str]:
    """The adapters a cube can come from, with what their ids name."""
    return {"sidra": "<table>/<variable>: any table of IBGE's SIDRA registry",
            "series": "<name>/<measure>: a series stitched across census tables (curation/sidra/series.yml)",
            "records": "<dataset>/<event type>: the events of any record dataset by place, period and its columns",
            "population": "<series>: a population series (curation/populations.yml: POPSVS, POPTCU, CENSO...)"}


# ---------------------------------------------------------------------------------------------------------- SIDRA


def _sidra(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]], periods: Sequence[str | int] | None,
           labels: bool, settings: Any) -> pa.Table:
    import pyarrow.compute as pc

    from .sidra import Sidra

    table_id, variable_id = _two_ints(ident, "sidra:<table>/<variable>")
    sidra = Sidra(settings=settings)
    registry = sidra.registry
    variable = next((v for v in registry.variables(table_id) if v["id"] == variable_id), None)
    if variable is None:
        raise KeyError(f"SIDRA table {table_id} has no variable {variable_id} in the registry")
    summarisation = set(_json_list(registry.db.execute(
        "SELECT summarisation FROM variable WHERE tab = ? AND id = ?", (table_id, variable_id)).fetchone()[0]))
    wanted_periods = [str(p) for p in periods] if periods else None
    level = LEVELS[place]
    # The published level when IBGE gives it; a finer level summed only where IBGE says the variable sums over territory.
    facts = _facts_or_none(sidra, table_id, variable_id, wanted_periods, level)
    rolled = False
    if facts is None and place != "municipality":
        if "nivelTerritorial" not in summarisation:
            raise AggregationRefused(
                f"sidra:{table_id}/{variable_id} ({variable['name']}) is not summed over territory by IBGE "
                f"(summarização {sorted(summarisation)}), and the {level} level is not held")
        facts = _facts_or_none(sidra, table_id, variable_id, wanted_periods, "N6")
        rolled = True
    if facts is None:
        raise LookupError(f"sidra:{table_id}/{variable_id}: no facts held at {level}; fetch them first "
                          f"(pegasus-data sidra fetch {table_id} -v {variable_id})")

    keep: list[str] = []
    for c in registry.classifications(table_id):
        name = f"c{c['id']}"
        if name in by:
            keep.append(name)
            if name in where:
                facts = facts.filter(pc.is_in(facts.column(name), pa.array([int(x) for x in where[name]], pa.int64())))
            continue
        chosen = [int(x) for x in where.get(name, [])]
        if not chosen:
            total = registry.total_category(table_id, c["id"])
            if total is None:
                raise LookupError(f"sidra:{table_id}: classification {c['id']} ({c['name']}) has no Total; "
                                  f"keep it with by=['{name}'] or name its categories in where")
            chosen = [total]
        elif len(chosen) > 1 and not _summarises(registry, table_id, c["id"]):
            raise AggregationRefused(f"sidra:{table_id}: IBGE does not sum the categories of classification {c['id']} "
                                     f"({c['name']}); keep it with by=['{name}']")
        facts = facts.filter(pc.is_in(facts.column(name), pa.array(chosen, pa.int64())))
    unknown = set(by) - set(keep)
    if unknown:
        held = ["c" + str(c["id"]) for c in registry.classifications(table_id)]
        raise KeyError(f"sidra:{table_id}: no classification {sorted(unknown)}; it has {held}")

    out = pa.table({
        "place": pc.cast(facts.column("locality"), pa.int64()),
        "period": facts.column("period"),
        **{k: facts.column(k) for k in keep},
        "value": facts.column("value"),
        "status": facts.column("status"),
    })
    collapsed = [c for c in (f"c{x['id']}" for x in registry.classifications(table_id)) if c not in keep]
    if collapsed and any(len(where.get(c, [])) > 1 for c in collapsed):
        out = _sum(out, ["place", "period", *keep])
    if rolled:
        out = _roll_place(out, place, keep)
    n = out.num_rows
    out = out.append_column("unit", pa.array([variable["unit"]] * n, pa.string()))
    source_label = f"IBGE agregados {table_id} v{variable_id}"
    out = out.append_column("source", pa.array([source_label] * n, pa.string()))
    if labels and keep:
        out = _label_strata(out, keep, lambda name: {int(c["id"]): c["name"] for c in registry.categories(table_id, int(name[1:]))})
    return _with_manifest(out, {
        "source": f"sidra:{table_id}/{variable_id}", "name": variable["name"], "unit": variable["unit"],
        "kind": variable["kind"], "additive_over": sorted(summarisation), "place_level": place,
        "period_grain": _grain(out.column("period").to_pylist()), "strata": keep, "rolled_up_from": "N6" if rolled else None,
    })


def _summarises(registry: Any, table: int, class_id: int) -> bool:
    row = registry.db.execute("SELECT summarises FROM classification WHERE tab = ? AND id = ?", (table, class_id)).fetchone()
    return bool(row and row[0])


def _facts_or_none(sidra: Any, table: int, variable: int, periods: list[str] | None, level: str) -> pa.Table | None:
    try:
        facts = sidra.facts(table, variables=[variable], periods=periods, level=level, light=True)
    except (FileNotFoundError, LookupError, ValueError):
        return None
    return facts if facts.num_rows else None


# ------------------------------------------------------------------------------------------------------- series


def _series(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]], periods: Sequence[str | int] | None,
            labels: bool, settings: Any) -> pa.Table:
    import pyarrow.compute as pc

    from .sidra import Sidra
    from .sidra.series import declared_series, series_values

    name, _, measure = ident.partition("/")
    if name not in declared_series():
        raise KeyError(f"no series {name!r}; declared: {sorted(declared_series())}")
    if by:
        raise ValueError("a series cube is served at its declared measure; name categories of its axes in where")
    if place != "municipality":
        raise AggregationRefused("a stitched series is held at municipalities; roll it up with the series' own rules")
    values = _cached(settings, f"series-{name}-{measure or 'value'}", where,
                     lambda: series_values(Sidra(settings=settings), name, measure or "value",
                                           {k: list(v) for k, v in where.items()} or None))
    if periods:
        values = values.filter(pc.is_in(values.column("period"), pa.array([str(p) for p in periods])))
    spec = declared_series()[name]
    out = pa.table({
        "place": pc.cast(values.column("locality"), pa.int64()),
        "period": values.column("period"),
        "value": values.column("value"),
        "status": values.column("status"),
        "unit": pa.array([str(spec.get("unit") or "")] * values.num_rows, pa.string()),
        "source": pa.array([f"IBGE agregados {t} v{v} (series {name})" for t, v in
                            zip(values.column("table").to_pylist(), values.column("variable").to_pylist(), strict=True)],
                           pa.string()),
    })
    return _with_manifest(out, {"source": f"series:{ident}", "name": name, "measure": measure or "value",
                                "place_level": place, "period_grain": _grain(out.column("period").to_pylist()),
                                "strata": [], "where": {k: list(v) for k, v in where.items()}})


def _cached(settings: Any, key: str, where: Mapping[str, Any], build: Any, stamp: Any = None) -> pa.Table:
    """A built cube kept under ``<lake>/cubes/`` beside the fingerprint of what it was built from: by default SIDRA's
    fact parts (names, sizes, times); ``stamp`` adds another source's (a records cube's lake partitions and files). The
    curation and this module's own code are always in it, so an edited declaration or a changed adapter makes the cube
    stale and it is built again. A stitched series is seconds to build, a records cube minutes; both are read often."""
    import hashlib

    import pyarrow.parquet as pq

    from .semantics.epoch import curation_epoch
    from .sidra.store import facts_dir

    folder = Path(settings.lake_dir) / "cubes"
    # The request (the series, its measure, its filter) names the file; the facts' fingerprint is its version.
    key = f"{key}-{hashlib.blake2b(json.dumps(where, sort_keys=True, default=str).encode(), digest_size=6).hexdigest()}"
    digest = hashlib.blake2b(digest_size=12)
    digest.update(curation_epoch()[1].encode())
    digest.update(Path(__file__).read_bytes())
    if stamp is not None:
        stamp(digest)
    else:
        base = facts_dir(Path(settings.lake_dir))
        for part in sorted(base.glob("table=*/req-*.parquet")) if base.exists() else ():
            stat = part.stat()
            digest.update(f"{part.parent.name}/{part.name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    target = folder / f"{key}-{digest.hexdigest()}.parquet"
    if target.exists():
        return pq.read_table(target)
    table = build()
    folder.mkdir(parents=True, exist_ok=True)
    for stale in folder.glob(f"{key}-*.parquet"):
        stale.unlink(missing_ok=True)
    tmp = target.with_name(f"_{target.name}.tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(target)
    return table


# ------------------------------------------------------------------------------------------------------ records


def _records(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]], periods: Sequence[str | int] | None,
             labels: bool, settings: Any, at: str | None = None, time: str | None = None, grain: str | None = None,
             condition: object = None, measure: str | None = None) -> pa.Table:
    """Events of one type of a record dataset, counted by the event type's own rules (status, duplicates, consolidation,
    weights: `semantics.event_types`), by place, period and the columns in ``by``. The place and the date are the dataset's
    declared bindings; a municipality is its IBGE 7 digits, and an event whose place no IBGE municipality has, or that has
    no date, is counted in the manifest (``unplaced_events``), never dropped silently. A (place, period) with no event has
    no row: not observed, never zero."""
    import pyarrow.compute as pc

    from ._aggregate import _competencia_column
    from .geography import place_municipalities
    from .semantics.curation import semantics_for
    from .semantics.event_types import count_events

    dataset, _, event = ident.partition("/")
    if not event:
        raise ValueError("a records cube is records:<dataset>/<event type>")
    if not periods:
        raise ValueError("a records cube names its periods (years): it reads the records of those publications")
    semantics = semantics_for(dataset)
    if semantics is None:
        raise LookupError(f"{dataset}: no curated place and time bindings (semantic_axes) to place and date its events")
    geography = semantics.geography_bindings()
    times = semantics.time_bindings()
    at = at or semantics.default_geography() or "residence"
    time = time or semantics.default_time()
    if at not in geography or time not in times:
        raise KeyError(f"{dataset}: place binding {at!r} of {sorted(geography)}, time binding {time!r} of {sorted(times)}")
    place_column = str(geography[at]["fields"][0])
    time_fields = [str(f) for f in times[time]["fields"]]
    encoding = str(times[time].get("encoding") or "")
    grain = grain or "month"
    if grain not in ("month", "year"):
        raise ValueError("a records cube's grain is month or year")
    # `where` is the record's own codes ({column: [codes]}, read by the query) or a prefix ({column: {prefix: [...]}}, kept
    # after counting): SISAGUA's monthly control keeps the CAMPO rows that are counts ("Número de...", "N de...").
    exact = {k: [str(x) for x in v] for k, v in where.items() if not isinstance(v, Mapping)}
    prefixes = {k: [str(x) for x in v["prefix"]] for k, v in where.items() if isinstance(v, Mapping) and "prefix" in v}
    unknown_forms = set(where) - set(exact) - set(prefixes)
    if unknown_forms:
        raise ValueError(f"where takes codes or {{prefix: [...]}}; not understood for {sorted(unknown_forms)}")
    group = list(dict.fromkeys([place_column, *time_fields, *by, *prefixes]))
    extra = {"rows": exact} if exact else {}
    years = sorted({int(str(p)[:4]) for p in periods})
    # Only the years the source publishes are read, in runs of consecutive years; a year asked for that has no
    # publication is said in the manifest, never fetched and failed (FA-HUM's file has no case in 2012).
    from ._explore import explore

    published = {int(r["year"]) for r in explore(dataset).as_dict()["rows"] if r.get("year")}
    unpublished = [y for y in years if y not in published]
    runs: list[list[int]] = []
    for y in (y for y in years if y in published):
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    if not runs:
        raise LookupError(f"{dataset} publishes none of the years {years}")
    def count(span: Any) -> pa.Table:
        if event != "rows":
            if measure:
                raise ValueError("an event type counts events; a measure is summed over a dataset's rows (records:<dataset>/rows)")
            return count_events(dataset, event, period=span, geography="BR", by=group, condition=condition, **extra)
        if condition is not None:
            raise ValueError("a condition on roles applies to an event type's records")
        from ._query_engine import query

        table = query(dataset, period=span, geography="BR", select=list(dict.fromkeys([*group, *([measure] if measure else [])])),
                      present="codes", **extra)
        if measure:
            table = table.set_column(table.schema.get_field_index(measure), measure,
                                     pc.cast(table.column(measure), pa.float64(), safe=False))
            return table.group_by(group).aggregate([(measure, "sum")]).rename_columns([*group, "events"])
        return table.group_by(group).aggregate([(place_column, "count")]).rename_columns([*group, "events"])

    parts = [count(run[0] if len(run) == 1 else (run[0], run[-1])) for run in runs]
    counts = pa.concat_tables(parts, promote_options="permissive") if len(parts) > 1 else parts[0]
    for column, starts in prefixes.items():
        text = pc.cast(counts.column(column), pa.string())
        hit = pc.starts_with(text, starts[0])
        for start in starts[1:]:
            hit = pc.or_kleene(hit, pc.starts_with(text, start))
        hit = pc.fill_null(hit, False)
        counts = counts.filter(hit)
    competencia = _competencia_column(counts, time_fields, encoding)
    year = pc.utf8_slice_codeunits(competencia, 0, 4)
    period = year if grain == "year" else pc.binary_join_element_wise(
        year, pc.utf8_slice_codeunits(competencia, 4, 6), "-")
    places = pa.array(place_municipalities(counts.column(place_column).to_pylist()), pa.int64())
    events = pc.cast(counts.column("events"), pa.float64())
    wanted = pc.is_in(pc.cast(year, pa.int64()), pa.array(years, pa.int64()))   # a span's years not asked for are left out
    keep = pc.fill_null(pc.and_(pc.and_(pc.is_valid(places), pc.is_valid(period)), wanted), False)
    unplaced = float(pc.sum(pc.filter(events, pc.invert(keep))).as_py() or 0)
    facts = pa.table({"place": pc.filter(places, keep), "period": pc.filter(period, keep),
                      **{k: pc.filter(counts.column(k), keep) for k in by}, "value": pc.filter(events, keep)})
    if place == "uf":
        facts = facts.set_column(0, "place", pc.cast(pc.divide(facts.column("place"), 100000), pa.int64()))
    elif place == "country":
        facts = facts.set_column(0, "place", pc.multiply(facts.column("place"), 0))
    keys = ["place", "period", *by]
    facts = facts.group_by(keys).aggregate([("value", "sum")]).rename_columns([*keys, "value"]).select([*keys, "value"])
    n = facts.num_rows
    unit_name = measure or ("records" if event == "rows" else "events")
    facts = (facts.append_column("status", pa.array(["value"] * n, pa.string()))
             .append_column("unit", pa.array([unit_name] * n, pa.string()))
             .append_column("source", pa.array([f"{dataset} {event}"] * n, pa.string())))
    unkeyed = (counts.schema.metadata or {}).get(b"UNKEYED")
    return _with_manifest(facts, {
        "source": f"records:{ident}", "dataset": dataset, "event": event, "at": at, "time": time,
        "place_level": place, "period_grain": grain, "strata": by, "where": where, "periods": [str(p) for p in periods],
        "unplaced_events": unplaced, "events": float(pc.sum(events).as_py() or 0), "not_published": unpublished,
        "unkeyed": unkeyed.decode() if unkeyed else None,
    })


# --------------------------------------------------------------------------------------------------- population


def _population(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]],
                periods: Sequence[str | int] | None, labels: bool, settings: Any) -> pa.Table:
    """A population series (`load_population`) as a cube: persons by municipality and year, by the series' own axes
    (``sex``, ``age``...) when named in ``by``. A series refuses an axis it does not publish (`load_population`), and a
    year it does not hold. Counts of persons add up over places and strata, never over years (a stock)."""
    import pyarrow.compute as pc

    from .api import load_population
    from .geography import place_municipalities

    years = [int(str(p)[:4]) for p in periods] if periods else None
    table = load_population(series=ident, years=years, by=tuple(by), settings=settings)
    for column, codes in where.items():
        table = table.filter(pc.is_in(pc.cast(table.column(column), pa.string()), pa.array([str(c) for c in codes])))
    places = pa.array(place_municipalities(table.column("municipality").to_pylist()), pa.int64())
    keep = pc.is_valid(places)
    unplaced = float(pc.sum(pc.filter(table.column("population"), pc.invert(keep))).as_py() or 0)
    facts = pa.table({"place": pc.filter(places, keep),
                      "period": pc.cast(pc.filter(table.column("year"), keep), pa.string()),
                      **{k: pc.filter(table.column(k), keep) for k in by},
                      "value": pc.cast(pc.filter(table.column("population"), keep), pa.float64())})
    if place == "uf":
        facts = facts.set_column(0, "place", pc.cast(pc.divide(facts.column("place"), 100000), pa.int64()))
    elif place == "country":
        facts = facts.set_column(0, "place", pc.multiply(facts.column("place"), 0))
    keys = ["place", "period", *by]
    facts = facts.group_by(keys).aggregate([("value", "sum")]).rename_columns([*keys, "value"]).select([*keys, "value"])
    n = facts.num_rows
    facts = (facts.append_column("status", pa.array(["value"] * n, pa.string()))
             .append_column("unit", pa.array(["persons"] * n, pa.string()))
             .append_column("source", pa.array([f"population {ident}"] * n, pa.string())))
    series = json.loads((table.schema.metadata or {}).get(b"pegasus.series", b"{}"))
    return _with_manifest(facts, {"source": f"population:{ident}", "series": series, "place_level": place,
                                  "period_grain": "year", "strata": by, "additive_over": ["territory", "strata"],
                                  "stock": True, "unplaced_persons": unplaced})


def _records_stamp(settings: Any, dataset: str, digest: Any) -> None:
    """What a records cube was read from: the dataset's lake partitions and its published files, as the catalog lists
    them (path, size, time). A unit landed again, a file republished or a partition rebuilt changes it."""
    from .catalog.store import CatalogStore
    from .semantics.curation import semantics_for

    semantics = semantics_for(dataset)
    system, series = (str(semantics.system or "").upper(), str(semantics.series or "").upper()) if semantics else ("", "")
    store = CatalogStore(settings.catalog_path, read_only=True)
    try:
        for row in store.query(
            "SELECT lp.relative_path, lp.byte_size, lp.written_at FROM lake_partitions lp JOIN families f"
            " ON f.family_id = lp.family_id WHERE f.system = ? AND f.series = ?"
            " ORDER BY lp.relative_path", (system, series)):
            digest.update(f"{row[0]}:{row[1]}:{row[2]}".encode())
        for row in store.query(
            "SELECT f.path, f.size, f.modified FROM file_facts ff JOIN files f ON f.path = ff.path"
            " WHERE ff.system = ? AND ff.series_prefix = ? AND f.gone_at IS NULL"
            " ORDER BY f.path", (system, series)):
            digest.update(f"{row[0]}:{row[1]}:{row[2]}".encode())
    finally:
        store.close()


# ------------------------------------------------------------------------------------------------------ algebra


def _sum(table: pa.Table, keys: list[str]) -> pa.Table:
    """Sum ``value`` over the rows sharing ``keys``; a group with any part without a number is ``incomplete`` (no value)."""
    import pyarrow.compute as pc

    numbered = pc.is_in(table.column("status"), pa.array(list(NUMBERED)))
    marked = table.append_column("_missing", pc.cast(pc.invert(numbered), pa.int64()))
    grouped = marked.group_by(keys).aggregate([("value", "sum"), ("_missing", "sum")])
    missing = grouped.column("_missing_sum")
    complete = pc.equal(missing, 0)
    value = pc.if_else(complete, grouped.column("value_sum"), pa.scalar(None, pa.float64()))
    zero = pc.and_(complete, pc.equal(grouped.column("value_sum"), 0))
    status = pc.if_else(complete, pc.if_else(zero, "zero", "value"), "incomplete")
    return pa.table({**{k: grouped.column(k) for k in keys}, "value": value, "status": status})


def _roll_place(table: pa.Table, level: str, strata: list[str]) -> pa.Table:
    """Municipalities pushed forward to their state or the country (a total map: every IBGE code has its state)."""
    import pyarrow.compute as pc

    codes = table.column("place")
    target = pc.cast(pc.divide(codes, 100000), pa.int64()) if level == "uf" else pc.multiply(codes, 0)
    return _sum(table.set_column(0, "place", target), ["place", "period", *strata])


def _label_strata(table: pa.Table, strata: list[str], names: Any) -> pa.Table:
    for stratum in strata:
        mapping = names(stratum)
        table = table.append_column(f"{stratum}_label", pa.array(
            [mapping.get(x) for x in table.column(stratum).to_pylist()], pa.string()))
    return table


def _with_manifest(table: pa.Table, manifest: dict[str, Any]) -> pa.Table:
    meta = dict(table.schema.metadata or {})
    meta[b"pegasus.cube"] = json.dumps(manifest, default=str).encode()
    meta[b"pegasus.place_level"] = str(manifest.get("place_level")).encode()
    meta[b"pegasus.period_grain"] = str(manifest.get("period_grain")).encode()
    return table.replace_schema_metadata(meta)


def _grain(periods: list[Any]) -> str:
    sample = next((str(p) for p in periods if p), "")
    if "-W" in sample:
        return "epi_week"
    return {4: "year", 6: "month", 7: "month", 8: "day", 10: "day"}.get(len(sample), "period")


def _two_ints(ident: str, form: str) -> tuple[int, int]:
    head, _, tail = ident.partition("/")
    if not head.isdigit() or not tail.isdigit():
        raise ValueError(f"expected {form}, got {ident!r}")
    return int(head), int(tail)


def _json_list(text: Any) -> list[Any]:
    try:
        return list(json.loads(text or "[]"))
    except ValueError:
        return []


_ADAPTERS = {"sidra": _sidra, "series": _series, "records": _records, "population": _population}


def cube_manifest(table: pa.Table) -> dict[str, Any]:
    """The manifest a cube carries in its schema."""
    return json.loads((table.schema.metadata or {}).get(b"pegasus.cube", b"{}"))
