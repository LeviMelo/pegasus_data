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

import hashlib
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
#: A bound of a `where` on a typed number, and its comparison (the intake's grammar: `intake._derive`'s conditions).
BOUNDS = {"above": "greater", "below": "less", "at_least": "greater_equal", "at_most": "less_equal"}
#: Place levels and SIDRA's territorial level for each.
LEVELS = {"municipality": "N6", "uf": "N3", "country": "N1"}


def cube(source: str, *, place: str = "municipality", by: Sequence[str] = (), where: Mapping[str, Sequence[Any]] | None = None,
         periods: Sequence[str | int] | None = None, labels: bool = True, settings: Any = None,
         at: str | None = None, time: str | None = None, grain: str | None = None, condition: object = None,
         measure: str | None = None, support: Any = None, geography: str | None = None,
         derived: Mapping[str, Mapping[str, Any]] | None = None) -> pa.Table:
    """The cube ``source`` at ``place`` level (``municipality``, ``uf``, ``country``), keeping the strata named in ``by``
    and the categories named in ``where``; every other stratum is the source's Total. ``periods`` restricts the periods.

    ``source`` is ``<adapter>:<id>``: ``sidra:<table>/<variable>``, ``series:<name>/<measure>`` or
    ``records:<dataset>/<event type>`` (`cube_sources`). A records cube also takes ``at`` (whose place: one of the
    dataset's geography bindings, its default when left out), ``time`` (which date: one of its time bindings) and ``grain``
    (``month`` or ``year``); its ``where`` is the record's own codes ({column: [codes]}) and ``condition`` clauses on roles
    (`pegasus_data.conditions`). ``records:<dataset>/rows`` counts the records of a dataset that is no event source (a
    water sample, a sale, a dose row), sums its numeric column ``measure`` or, with ``measure="distinct:<column>"``, counts
    the column's distinct values per cell (establishments, teams, persons). ``where`` also takes ``{column: {"not":
    [...]}}`` and a two-column code ``{"A+B": [...]}``. ``periods`` are years, or months (``"2023-12"``) to read those
    months only. ``derived`` names strata made from the record (a records cube): ``{"FAIXA_ETARIA": {"age": "IDADE_anos",
    "bands": [0, 1, 5, ...]}}`` bands the age the dataset's variables declare (`_age.resolve_age`), ``{"PESO_FAIXA":
    {"field": "PESO", "bands": [...]}}`` bands a number; a value not decodable is its own level (``ZIG``). Each named in
    ``by``. ``support`` names a records cube (``records:CNES-ST/rows``) whose places are the ones the source could
    have recorded: inside it a cell with no record is 0 (``zero``), outside it there is no row. The facts must be held or
    fetchable; a cube of nothing raises, never returns an empty table that could pass for an empty result.
    """
    from .config import load_settings

    if place not in LEVELS:
        raise ValueError(f"place must be one of {sorted(LEVELS)}, got {place!r}")
    kind, _, ident = source.partition(":")
    adapter = _ADAPTERS.get(kind)
    if adapter is None or not ident:
        raise ValueError(f"a cube is <adapter>:<id> with adapter one of {sorted(_ADAPTERS)}, got {source!r}")
    options = {k: v for k, v in (("at", at), ("time", time), ("grain", grain), ("condition", condition),
                                 ("measure", measure), ("support", support), ("geography", geography),
                                 ("derived", {k: dict(v) for k, v in derived.items()} if derived else None)) if v is not None}
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
            "population": "<series>: a population series (curation/populations.yml: POPSVS, POPTCU, CENSO...)",
            "climate": "<measure>: BR-DWGD's municipal climate by year (sums and their months held, sources.brdwgd)"}


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
    digest.update(_code_fingerprint())
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
             condition: object = None, measure: str | None = None, support: Any = None,
             geography: str | None = None, derived: Mapping[str, Mapping[str, Any]] | None = None) -> pa.Table:
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
    places_bound = semantics.geography_bindings()
    times = semantics.time_bindings()
    at = at or semantics.default_geography() or "residence"
    time = time or semantics.default_time()
    if at not in places_bound or time not in times:
        raise KeyError(f"{dataset}: place binding {at!r} of {sorted(places_bound)}, time binding {time!r} of {sorted(times)}")
    place_column = str(places_bound[at]["fields"][0])
    time_fields = [str(f) for f in times[time]["fields"]]
    encoding = str(times[time].get("encoding") or "")
    grain = grain or "month"
    if grain not in ("month", "year"):
        raise ValueError("a records cube's grain is month or year")
    # `where` is the record's own codes ({column: [codes]}, read by the query) or a prefix ({column: {prefix: [...]}}, kept
    # after counting): SISAGUA's monthly control keeps the CAMPO rows that are counts ("Número de...", "N de...").
    # A code list on a plain column is read by the query; a prefix, an exclusion or a code made of two columns
    # ("TIPEQUIP+CODEQUIP": CNES's equipment key) is applied after counting, on columns kept for it.
    # a list holding the blank code ("" : CNES's DT_DESAT of a team still active) is applied after, a null read as blank
    exact = {k: [str(x) for x in v] for k, v in where.items()
             if not isinstance(v, Mapping) and "+" not in k and "" not in [str(x) for x in v]}
    after = {k: v for k, v in where.items() if k not in exact}
    for k, v in after.items():
        if isinstance(v, Mapping) and not set(v) <= {"prefix", "not", *BOUNDS}:
            raise ValueError(f"where takes codes, {{prefix: [...]}}, {{not: [...]}} or bounds {sorted(BOUNDS)}; "
                             f"not understood for {k!r}")
    filter_columns = [c for k in after for c in k.split("+")]
    distinct = measure.split(":", 1)[1] if measure and measure.startswith("distinct:") else None
    summed = None if distinct else measure
    # a derived stratum is read from its input columns and made after counting by them (`_derived_dimensions`)
    bands = _derived_dimensions(dataset, derived or {})
    missing = [b for b in bands if b not in by]
    if missing:
        raise ValueError(f"derived strata {missing} are not named in by")
    inputs = [c for d in bands.values() for c in (d.fields if hasattr(d, "form") else (d.field_name,))]
    group = list(dict.fromkeys([place_column, *time_fields, *(b for b in by if b not in bands), *inputs, *filter_columns]))
    extra = {"rows": exact} if exact else {}
    months = sorted({str(p) for p in periods if len(str(p)) == 7 and str(p)[4] == "-"})
    # `geography` selects the publications read (a state's files), never the records: a test reads the least it needs
    publications = geography or "BR"
    years = sorted({int(str(p)[:4]) for p in periods})
    # Only the years the source publishes are read; a year asked for that has no publication is said in the manifest,
    # never fetched and failed (FA-HUM's file has no case in 2012). Events are read in runs of consecutive years, since an
    # event type removes a record filed in two years' publications (SRAG's) only within one read; a dataset's rows have no
    # identity across files and are read one year at a time (SNGPC's national sales of 2014-2021 read at once ran out of
    # memory).
    from ._explore import explore

    published = {int(r["year"]) for r in explore(dataset).as_dict()["rows"] if r.get("year")}
    unpublished = [y for y in years if y not in published]
    readable = [y for y in years if y in published]
    if not readable:
        raise LookupError(f"{dataset} publishes none of the years {years}")
    runs: list[list[int]] = []
    for y in readable:
        if runs and y == runs[-1][-1] + 1 and event != "rows":
            runs[-1].append(y)
        else:
            runs.append([y])
    spans: list[Any] = ([m for m in months if int(m[:4]) in published] if months
                        else [run[0] if len(run) == 1 else (run[0], run[-1]) for run in runs])

    def kept(table: pa.Table) -> pa.Table:
        """`where`'s prefixes, exclusions, bounds and two-column codes, applied to a table that holds their columns."""
        for key, rule in after.items():
            columns = key.split("+")
            text = pc.fill_null(pc.utf8_trim_whitespace(pc.cast(table.column(columns[0]), pa.string())), "")
            for column in columns[1:]:
                text = pc.binary_join_element_wise(
                    text, pc.fill_null(pc.utf8_trim_whitespace(pc.cast(table.column(column), pa.string())), ""), "")
            if isinstance(rule, Mapping) and set(rule) & set(BOUNDS):
                # the typed value against a bound (a potability limit: turbidity above 5 uT); a value not a number fails
                number = pc.cast(table.column(columns[0]), pa.float64(), safe=False)
                hit = None
                for bound, op in BOUNDS.items():
                    if bound in rule:
                        test = getattr(pc, op)(number, float(rule[bound]))
                        hit = test if hit is None else pc.and_kleene(hit, test)
            elif isinstance(rule, Mapping) and "prefix" in rule:
                starts = [str(x) for x in rule["prefix"]]
                hit = pc.starts_with(text, starts[0])
                for start in starts[1:]:
                    hit = pc.or_kleene(hit, pc.starts_with(text, start))
            elif isinstance(rule, Mapping):
                # an exclusion of a value not recorded is unknown, never kept: a facility with no SUS link recorded is
                # neither SUS nor non-SUS (as the CNES fields counted it)
                recorded = pc.is_valid(table.column(columns[0]))
                hit = pc.and_(recorded, pc.invert(pc.is_in(text, pa.array([str(x) for x in rule["not"]]))))
            else:
                hit = pc.is_in(text, pa.array([str(x) for x in rule]))
            table = table.filter(pc.fill_null(hit, False))
        return table

    # the cell's own keys: a column a filter reads is not one of them (a physician under two CBO codes is one person)
    cell = list(dict.fromkeys([place_column, *time_fields, *by]))

    def banded(table: pa.Table) -> pa.Table:
        """The derived strata of ``table``'s input columns (`_age.band_column`, `NumericBandDimension.column`)."""
        from ._age import band_column, years_column

        for name, dim in bands.items():
            column = band_column(dim, years_column(dim, table)) if hasattr(dim, "form") else dim.column(table)
            table = table.append_column(name, column)
        return table

    def placed(table: pa.Table) -> pa.Table:
        """The place column as the municipality it places (`geography.place_municipalities`), before any grouping: a
        distinct count is of its municipality, never summed over the codes that place there (the Federal District's PF
        files code its administrative regions to 2016, and a physician of two regions is one physician of Brasília)."""
        codes = pc.dictionary_encode(pc.cast(table.column(place_column), pa.string())).combine_chunks()
        mapped = pa.array(place_municipalities(codes.dictionary.to_pylist()), pa.int64())
        return table.set_column(table.schema.get_field_index(place_column), place_column, pc.take(mapped, codes.indices))

    def count(span: Any) -> pa.Table:
        if event != "rows":
            if measure:
                raise ValueError("an event type counts events; a measure is summed over a dataset's rows (records:<dataset>/rows)")
            # events are counted by the filters' columns too, then filtered and summed over them (events add up)
            counted = banded(placed(kept(count_events(dataset, event, period=span, geography=publications, by=group,
                                                      condition=condition, **extra))))
            return counted.group_by(cell).aggregate([("events", "sum")]).rename_columns([*cell, "events"])
        if condition is not None:
            raise ValueError("a condition on roles applies to an event type's records")
        from ._query_engine import query

        # a sum of several columns ("HORA_AMB+HORAHOSP+HORAOUTR": a professional's weekly hours), a missing part as 0
        parts_summed = summed.split("+") if summed else []
        extra_columns = [*parts_summed, *([distinct] if distinct else [])]
        table = banded(placed(kept(query(dataset, period=span, geography=publications,
                                         select=list(dict.fromkeys([*group, *extra_columns])), present="codes", **extra))))
        if summed:
            total = None
            for part in parts_summed:
                value = pc.cast(table.column(part), pa.float64(), safe=False)
                value = pc.fill_null(value, 0.0) if len(parts_summed) > 1 else value
                total = value if total is None else pc.add(total, value)
            table = table.append_column("__sum", total)
            return table.group_by(cell).aggregate([("__sum", "sum")]).rename_columns([*cell, "events"])
        if distinct:
            # one row per distinct value in its cell (an establishment listed twice in a month is one), then counted
            values = pc.utf8_trim_whitespace(pc.cast(table.column(distinct), pa.string()))
            table = table.set_column(table.schema.get_field_index(distinct), distinct, values).filter(
                pc.fill_null(pc.not_equal(values, ""), False))
            table = table.group_by([*cell, distinct]).aggregate([])
            return table.group_by(cell).aggregate([(distinct, "count")]).rename_columns([*cell, "events"])
        # every row, its place unplaced included (a count of the place column skips nulls: the unplaced vanished)
        return table.group_by(cell).aggregate([(place_column, "count", pc.CountOptions(mode="all"))]).rename_columns(
            [*cell, "events"])

    parts = [count(span) for span in spans]
    counts = pa.concat_tables(parts, promote_options="permissive") if len(parts) > 1 else parts[0]
    competencia = _competencia_column(counts, time_fields, encoding)
    # a period of no month (ANS's file year) leaves the column all null, of no type: it is text that holds nothing
    competencia = pa.nulls(counts.num_rows, pa.string()) if competencia is None else pc.cast(competencia, pa.string())
    year = pc.utf8_slice_codeunits(competencia, 0, 4)
    period = year if grain == "year" else pc.binary_join_element_wise(
        year, pc.utf8_slice_codeunits(competencia, 4, 6), "-")
    # An event whose year is recorded and month is not (a year and a month held apart, or a binding that is a year
    # alone: SISAGUA's register by NU_ANO) is kept at the finest period known, its year: it counts in every year's total
    # and is never placed in a month (FA's 13 month-less events).
    if (len(time_fields) >= 2 or encoding == "year") and time_fields[0] in counts.column_names:
        filed_year = pc.utf8_trim_whitespace(pc.cast(counts.column(time_fields[0]), pa.string()))
        known = pc.fill_null(pc.match_substring_regex(filed_year, r"^(19|20|21)\d\d$"), False)
        missing = pc.is_null(competencia)
        year = pc.if_else(pc.and_(missing, known), filed_year, year)
        period = pc.if_else(pc.and_(missing, known), filed_year, period)
    places = pc.cast(counts.column(place_column), pa.int64())          # placed before grouping (`placed`)
    events = pc.cast(counts.column("events"), pa.float64())
    # a span's years (or months) not asked for are left out
    wanted = (pc.is_in(pc.binary_join_element_wise(year, pc.utf8_slice_codeunits(competencia, 4, 6), "-"), pa.array(months))
              if months else pc.is_in(pc.cast(year, pa.int64()), pa.array(years, pa.int64())))
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
    statuses = ["value"] * facts.num_rows
    if support:
        # the places the source could have recorded, per period: inside, a cell with no record is a true 0
        if by:
            raise ValueError("a support fills (place, period) cells; name no strata with it")
        frame = (cube(support["source"], where=support.get("where"), place=place, periods=periods, grain=grain,
                      geography=geography, settings=settings) if isinstance(support, Mapping)
                 else cube(support, place=place, periods=periods, grain=grain, geography=geography, settings=settings))
        held = {(r["place"], r["period"]) for r in facts.select(["place", "period"]).to_pylist()}
        missing = sorted({(r["place"], r["period"]) for r in frame.select(["place", "period"]).to_pylist()} - held)
        if missing:
            facts = pa.concat_tables([facts, pa.table({
                "place": pa.array([m[0] for m in missing], pa.int64()), "period": pa.array([m[1] for m in missing]),
                "value": pa.array([0.0] * len(missing), pa.float64())})])
        statuses = statuses + ["zero"] * len(missing)
    n = facts.num_rows
    unit_name = measure or ("records" if event == "rows" else "events")
    facts = (facts.append_column("status", pa.array(statuses, pa.string()))
             .append_column("unit", pa.array([unit_name] * n, pa.string()))
             .append_column("source", pa.array([f"{dataset} {event}"] * n, pa.string())))
    unkeyed = (counts.schema.metadata or {}).get(b"UNKEYED")
    return _with_manifest(facts, {
        "source": f"records:{ident}", "dataset": dataset, "event": event, "at": at, "time": time,
        "place_level": place, "period_grain": grain, "strata": by, "where": where, "periods": [str(p) for p in periods],
        "measure": measure, "support": support, "publications": publications,
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


def _climate(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]],
             periods: Sequence[str | int] | None, labels: bool, settings: Any) -> pa.Table:
    """A measure of BR-DWGD's municipal climate (``climate:<measure>``, one of `sources.brdwgd.MEASURES`) by municipality
    and year, from the municipality-month base the build keeps (``climate_monthly``): the sums a mean is made of, and
    their denominators (``temperature_months``, ``precipitation_months``: months held, fractional), by
    `brdwgd.municipality_years`. A year whose variable holds fewer than twelve months is ``incomplete``, its value kept.
    Sums add over months, never over places (a municipality's temperature is no part of its state's); the cube is
    municipal."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    from .sources import brdwgd

    if ident not in brdwgd.MEASURES:
        raise KeyError(f"climate:<measure> is one of {sorted(brdwgd.MEASURES)}, got {ident!r}")
    if by or where:
        raise ValueError("a climate cube has no strata")
    if place != "municipality":
        raise ValueError("a climate cube is municipal: a temperature is not summed over places")
    base_dir = Path(settings.lake_dir) / "fields" / "climate_monthly"
    if not base_dir.is_dir():
        raise LookupError("BR-DWGD's municipal base is not built: run `pegasus-data fields --name climate_monthly`")
    years = sorted({int(str(p)[:4]) for p in periods}) if periods else None
    base = ds.dataset(base_dir, format="parquet", partitioning="hive")
    months = base.to_table(filter=ds.field("year").isin(years) if years else None)
    months = months.set_column(months.schema.get_field_index("year"), "year", pc.cast(months.column("year"), pa.int32()))
    annual = brdwgd.municipality_years(months)
    annual = annual.filter(pc.is_valid(annual.column(ident)))
    held = annual.column(f"{brdwgd.MEASURES[ident]}_months")
    n = annual.num_rows
    facts = pa.table({"place": pc.cast(annual.column("municipality7"), pa.int64()),
                      "period": pc.cast(annual.column("year"), pa.string()),
                      "value": pc.cast(annual.column(ident), pa.float64()),
                      "status": pc.if_else(pc.greater_equal(held, 12 - 1e-9), "value", "incomplete"),
                      "unit": pa.array([ident] * n, pa.string()),
                      "source": annual.column("product"),
                      "months": pc.cast(held, pa.float64())})
    return _with_manifest(facts, {"source": f"climate:{ident}", "place_level": "municipality", "period_grain": "year",
                                  "strata": [], "additive_over": ["months"],
                                  "denominator": f"climate:{brdwgd.MEASURES[ident]}_months"})


def _derived_dimensions(dataset: str, derived: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Each derived stratum's dimension: an age band (``age``: the derived variable whose declaration gives the age's
    form, resolved from the system's variables, `_age.resolve_age`; or a ``form`` given in place) or a numeric band
    (``field``)."""
    from ._age import parse_age, parse_band_dimensions, resolve_age

    out: dict[str, Any] = {}
    for name, body in derived.items():
        body = dict(body)
        if "field" in body:
            out[name] = parse_band_dimensions({name: body})[0]
        elif "age" in body:
            age = parse_age({"of": body["age"], **({"bands": body["bands"]} if body.get("bands") else {})}, name=name)
            out[name] = resolve_age(age, _variable_docs(dataset))
        else:
            out[name] = parse_age(body, name=name)
    return out


def _variable_docs(dataset: str) -> dict[str, Any]:
    """The curated variables of ``dataset``'s system, read from `curation/variables/<system>/` (not the catalog: a
    declaration is read where it is written)."""
    from ._request import parse_dataset
    from .config import curation_root
    from .semantics.curation import parse_variable_file, read_yaml

    system, _series = parse_dataset(dataset)
    out: dict[str, Any] = {}
    for path in sorted((curation_root() / "variables" / system.lower()).glob("*.yml")):
        for doc in parse_variable_file(path, read_yaml(path) or {}):
            out[f"{path.stem}:{doc.field_name}"] = doc
    return out


_CODE: dict[str, Any] = {}


def _code_fingerprint() -> bytes:
    """The package's source, as a cube's version: a cube computes through the period reader, the age decoder, the event
    counter, the placing rule, the query engine and more, and a list of them goes stale (an edit to the period reader,
    outside the list, once served a stale empty cube). Every module counts, so a cached cube is never one computed by
    code that no longer exists; memoised in the process by the files' sizes and times."""
    root = Path(__file__).parent
    files = sorted(root.rglob("*.py"))
    stat = tuple((str(f), f.stat().st_size, f.stat().st_mtime_ns) for f in files)
    if _CODE.get("stat") != stat:
        digest = hashlib.blake2b(digest_size=16)
        for f in files:
            digest.update(str(f.relative_to(root)).encode())
            digest.update(f.read_bytes())
        _CODE.update(stat=stat, digest=digest.digest())
    return _CODE["digest"]


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


_ADAPTERS = {"sidra": _sidra, "series": _series, "records": _records, "population": _population, "climate": _climate}


def cube_manifest(table: pa.Table) -> dict[str, Any]:
    """The manifest a cube carries in its schema."""
    return json.loads((table.schema.metadata or {}).get(b"pegasus.cube", b"{}"))
