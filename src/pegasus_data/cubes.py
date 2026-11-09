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
from .normalize.time import competencia_column, parse_month, year_column, year_of, years_of

__all__ = ["STATUSES", "cube", "cube_sources"]

#: The one status vocabulary of every cube (SIDRA's markers, and what a roll-up adds).
STATUSES = ("value", "zero", "not_applicable", "not_available", "suppressed", "empty", "unknown_symbol", "incomplete")
#: The statuses that carry a number.
NUMBERED = ("value", "zero")
#: A bound of a `where` on a typed number, and its comparison (the intake's `where` grammar).
BOUNDS = {"above": "greater", "below": "less", "at_least": "greater_equal", "at_most": "less_equal"}
#: A records cube's measure written ``<transform>:<column>``: `count` the rows holding a number, `sumsq` the squares'
#: sum, `sumlog` / `sumsqlog` the sum of the logs and of their squares (positive numbers), `countpos` how many are positive,
#: `min` / `max` the least and greatest number (an extreme: merged by min or max, never summed).
_TRANSFORMS = ("count", "sumsq", "sumlog", "sumsqlog", "countpos", "min", "max")
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
    (``month`` or ``year``; a climate cube also ``day`` or ``epi_week``, `cptec`'s); its ``where`` is the record's own codes ({column: [codes]}) and ``condition`` clauses on roles
    (`pegasus_data.conditions`). ``records:<dataset>/rows`` counts the records of a dataset that is no event source (a
    water sample, a sale, a dose row), sums its numeric column ``measure`` or, with ``measure="distinct:<column>"``, counts
    the column's distinct values per cell (establishments, teams, persons). ``where`` also takes ``{column: {"not":
    [...]}}`` and a two-column code ``{"A+B": [...]}``. ``periods`` are years, or months (``"2023-12"``) to read those
    months only. ``derived`` names strata made from the record (a records cube): ``{"FAIXA_ETARIA": {"age": "IDADE_anos",
    "bands": [0, 1, 5, ...]}}`` bands the years `query` derives by the system's declared age, ``{"PESO_FAIXA":
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
    if set(options) - ({"grain"} if kind == "climate" else set()) and kind != "records":
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
                   settings=settings, **options)   # a climate cube takes ``grain`` only


def cube_sources() -> dict[str, str]:
    """The adapters a cube can come from, with what their ids name."""
    return {"sidra": "<table>/<variable>: any table of IBGE's SIDRA registry",
            "series": "<name>/<measure>: a series stitched across census tables (curation/sidra/series.yml)",
            "records": "<dataset>/<event type>: the events of any record dataset by place, period and its columns",
            "population": "<series>: a population series (curation/populations.yml: POPSVS, POPTCU, CENSO...)",
            "climate": "<measure> (BR-DWGD by year), inmet/<measure> (INMET's stations by month or year, the station a stratum) "
                       "or cptec/<variable>[@area] (CPTEC's daily grids by day, epi week, month or year): sums and the days, "
                       "months or readings they rest on",
            "modelled": "<product>[@<version>]/<estimate>: a modelled product on its declared axes, with its bounds"}


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


def _bad_month(period: object) -> int:
    raise ValueError(f"periods are years, months or days, got {period!r}")


def _cached(settings: Any, key: str, where: Mapping[str, Any], build: Any, stamp: Any = None) -> pa.Table:
    """A built cube kept under ``<lake>/cubes/`` beside the fingerprint of what it was built from: by default SIDRA's
    fact parts (names, sizes, times); ``stamp`` adds another source's (a records cube's lake partitions and files). The
    curation and this module's own code are always in it, so an edited declaration or a changed adapter makes the cube
    stale and it is built again. A stitched series is seconds to build, a records cube minutes; both are read often."""

    import pyarrow.parquet as pq

    from .semantics.epoch import curation_epoch
    from .sidra.store import fact_parts

    folder = Path(settings.lake_dir) / "cubes"
    # The request (the series, its measure, its filter) names the file; the facts' fingerprint is its version.
    key = f"{key}-{hashlib.blake2b(json.dumps(where, sort_keys=True, default=str).encode(), digest_size=6).hexdigest()}"
    digest = hashlib.blake2b(digest_size=12)
    digest.update(curation_epoch()[1].encode())
    digest.update(_code_fingerprint())
    if stamp is not None:
        stamp(digest)
    else:
        for part in fact_parts(Path(settings.lake_dir)):
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
    no date, is counted in the manifest (``unplaced_events``), never dropped silently. An event whose code names its state
    and no municipality (DATASUS's "Município ignorado - <UF>": `geography.place_states`) is in no municipality's cell
    and counts in its state's and the country's. A (place, period) with no event has
    no row: not observed, never zero."""
    import pyarrow.compute as pc

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
    # a binding whose values are states (`code_system: uf`, SIES's SES-SP) is read at state level, never below
    states = places_bound[at].get("code_system") == "uf"
    state_prefix = str(places_bound[at].get("prefix") or "")
    if states and place == "municipality":
        raise ValueError(f"{dataset}: its place {at!r} is a state; read it at place='uf'")
    time_fields = [str(f) for f in times[time]["fields"]]
    encoding = str(times[time].get("encoding") or "")
    # a binding inherited from the system names the system's columns; a dataset of another layout (SIM-DOR's MUNIRES and
    # DATAOBITO under SIM's CODMUNRES and DTOBITO) would place and date nothing. The dataset's roles say which columns it
    # has: a bound column they do not declare is refused (the intake's landed binding names columns it makes itself).
    from .semantics.column_roles import declared_columns

    try:
        held = {c.column.upper() for c in declared_columns(dataset)}
    except KeyError:
        held = set()
    if held:
        unheld = [f for binding, fields in ((at, [place_column]), (time, time_fields)) if binding != "landed"
                  for f in fields if f.upper() not in held]
        if unheld:
            raise LookupError(f"{dataset}: its bindings {at!r}/{time!r} name {unheld}, columns its roles do not declare; "
                              "declare the dataset's own semantic_axes")
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
    # ``count:<column>``: the rows where the column holds a number (a mean's denominator: a blank stay is unknown, not 0)
    # The other moments of a number are sums of a transform of it: ``sumsq:<column>`` (x squared), and for a positive
    # number ``sumlog:`` / ``sumsqlog:`` (its log, its log squared) and ``countpos:`` (how many are positive): a
    # variance and a log-normal's likelihood are these sums, merged by addition (`measures.MOMENTS`, `LOGMOMENTS`).
    transform, _, argument = (measure or "").partition(":")
    if transform not in _TRANSFORMS:
        transform, argument = "", ""
    numbered = argument if transform == "count" else None
    summed = None if distinct or transform else measure
    extreme = transform if transform in ("min", "max") else None
    moment = transform if transform in _TRANSFORMS and transform not in ("count", "min", "max") else None
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
    years = sorted(set(years_of(periods)))
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
    spans: list[Any] = ([m for m in months if year_of(m) in published] if months
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
                from .normalize.types import to_number

                number = to_number(table.column(columns[0]))
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
    cell = list(dict.fromkeys([place_column, "__uf", *time_fields, *by]))

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
        if states:
            from .geography import uf_codes_by_sigla

            by_abbreviation = {abbr: int(code) for abbr, code in uf_codes_by_sigla().items()}
            mapped = pa.array([by_abbreviation.get(str(v).strip().removeprefix(state_prefix)) if v else None
                               for v in codes.dictionary.to_pylist()], pa.int64())
            state = mapped
        else:
            from .geography import place_states

            mapped = pa.array(place_municipalities(codes.dictionary.to_pylist()), pa.int64())
            # the state of each code: its municipality's, or the one a state-only code names
            state = pa.array(place_states(codes.dictionary.to_pylist()), pa.int64())
        table = table.set_column(table.schema.get_field_index(place_column), place_column, pc.take(mapped, codes.indices))
        return table.append_column("__uf", pc.take(state, codes.indices))

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
        extra_columns = [*parts_summed, *([distinct] if distinct else []), *([numbered] if numbered else []),
                         *([argument] if moment or extreme else [])]
        table = banded(placed(kept(query(dataset, period=span, geography=publications,
                                         select=list(dict.fromkeys([*group, *extra_columns])), present="codes", **extra))))
        if summed:
            # one number reader (`normalize.types.to_number`); several columns sum row-wise, a part
            # with no number contributing nothing and a row where no part holds one staying null (missing is not zero)
            from .normalize.types import to_number

            values = [to_number(table.column(part)) for part in parts_summed]
            total = values[0]
            for value in values[1:]:
                total = pc.if_else(pc.or_(pc.is_valid(total), pc.is_valid(value)),
                                   pc.add(pc.fill_null(total, 0.0), pc.fill_null(value, 0.0)),
                                   pa.scalar(None, pa.float64()))
            table = table.append_column("__sum", total)
            return table.group_by(cell).aggregate([("__sum", "sum")]).rename_columns([*cell, "events"])
        if extreme:
            from .normalize.types import to_number

            return table.append_column("__x", to_number(table.column(argument))).group_by(cell).aggregate(
                [("__x", extreme)]).rename_columns([*cell, "events"])
        if moment:
            from .normalize.types import to_number

            number = to_number(table.column(argument))
            if moment == "sumsq":
                term = pc.multiply(number, number)
            else:
                # a number that is not positive has no logarithm: left out of the state, as a blank is, never clipped
                positive = pc.fill_null(pc.greater(number, 0.0), False)
                log = pc.ln(pc.if_else(positive, number, pa.scalar(1.0, pa.float64())))
                term = (pc.cast(positive, pa.float64()) if moment == "countpos" else
                        pc.if_else(positive, log if moment == "sumlog" else pc.multiply(log, log),
                                   pa.scalar(None, pa.float64())))
            return table.append_column("__m", term).group_by(cell).aggregate([("__m", "sum")]).rename_columns(
                [*cell, "events"])
        if numbered:
            from .normalize.types import to_number

            table = table.append_column("__n", pc.cast(pc.is_valid(to_number(table.column(numbered))), pa.float64()))
            return table.group_by(cell).aggregate([("__n", "sum")]).rename_columns([*cell, "events"])
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
    century = str(times[time].get("century") or "")
    competencia = competencia_column(counts, time_fields, encoding, century)
    # a period of no month (ANS's file year) leaves the column all null, of no type: it is text that holds nothing
    competencia = pa.nulls(counts.num_rows, pa.string()) if competencia is None else pc.cast(competencia, pa.string())
    year = pc.utf8_slice_codeunits(competencia, 0, 4)
    period = year if grain == "year" else pc.binary_join_element_wise(
        year, pc.utf8_slice_codeunits(competencia, 4, 6), "-")
    # An event whose year is recorded and month is not (a year and a month held apart, a binding that is a year alone:
    # SISAGUA's register by NU_ANO, or a date filed as its year alone: SIM-DO 2000's 496 deaths dated "2000") is kept at
    # the finest period known, its year: it counts in every year's total and is never placed in a month (FA's 13
    # month-less events).
    filed_year = year_column(counts, time_fields, encoding, century)
    if filed_year is not None:
        known = pc.is_valid(filed_year)
        missing = pc.is_null(competencia)
        year = pc.if_else(pc.and_(missing, known), filed_year, year)
        period = pc.if_else(pc.and_(missing, known), filed_year, period)
    places = pc.cast(counts.column(place_column), pa.int64())          # placed before grouping (`placed`)
    if place in ("uf", "country"):
        # at a state or the country an event is placed by its state, which a state-only code names too
        places = pc.cast(counts.column("__uf"), pa.int64())
    events = pc.cast(counts.column("events"), pa.float64())
    # a span's years (or months) not asked for are left out
    wanted = (pc.is_in(pc.binary_join_element_wise(year, pc.utf8_slice_codeunits(competencia, 4, 6), "-"), pa.array(months))
              if months else pc.is_in(pc.cast(year, pa.int64()), pa.array(years, pa.int64())))
    keep = pc.fill_null(pc.and_(pc.and_(pc.is_valid(places), pc.is_valid(period)), wanted), False)
    # an extreme's cells are least or greatest numbers: no count of what was not placed is made from them
    unplaced = None if extreme else float(pc.sum(pc.filter(events, pc.invert(keep))).as_py() or 0)
    # the unplaced of a wanted, dated period whose code still names a state ("Município ignorado - <UF>"), per state: what a
    # sum of the municipalities of a state lacks against the state
    in_state = pc.fill_null(pc.and_(pc.and_(pc.invert(keep), pc.is_valid(counts.column("__uf"))),
                                    pc.and_(pc.is_valid(period), wanted)), False)
    if extreme:
        in_state = pc.and_(in_state, pa.scalar(False))
    by_state = (pa.table({"uf": pc.filter(counts.column("__uf"), in_state), "n": pc.filter(events, in_state)})
                .group_by("uf").aggregate([("n", "sum")]))
    unplaced_by_state = {str(u): float(n) for u, n in zip(by_state["uf"].to_pylist(), by_state["n_sum"].to_pylist(),
                                                          strict=True) if n}
    facts = pa.table({"place": pc.filter(places, keep), "period": pc.filter(period, keep),
                      **{k: pc.filter(counts.column(k), keep) for k in by}, "value": pc.filter(events, keep)})
    if place == "country":
        facts = facts.set_column(0, "place", pc.multiply(facts.column("place"), 0))
    keys = ["place", "period", *by]
    facts = (facts.group_by(keys).aggregate([("value", extreme or "sum")]).rename_columns([*keys, "value"])
             .select([*keys, "value"]))
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
        "unplaced_events": unplaced, "unplaced_by_state": unplaced_by_state,
        "events": None if extreme else float(pc.sum(events).as_py() or 0), "not_published": unpublished,
        "additive": not extreme,
        "unkeyed": unkeyed.decode() if unkeyed else None,
    })


# --------------------------------------------------------------------------------------------------- population


def _population(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]],
                periods: Sequence[str | int] | None, labels: bool, settings: Any) -> pa.Table:
    """A population series (`load_population`) as a cube: persons by place and year, by the series' own axes (``sex``,
    ``age``...) when named in ``by``. A series refuses an axis it does not publish (`load_population`), and a year it does
    not hold. Counts of persons add up over places and strata, never over years (a stock).

    Places follow the one placing rule: a municipality by `place_municipalities`, a state by `place_states`. A series filed
    by state (``ufcod``: the projections) has no municipality place, and refuses one. The persons no place takes are
    named in the manifest (``unplaced_persons``, ``unplaced_codes``, ``unplaced_years``), never dropped silently."""
    import pyarrow.compute as pc

    from .api import load_population
    from .config import UF_NUMERIC
    from .geography import place_municipalities, place_states

    years = years_of(periods) if periods else None
    table = load_population(series=ident, years=years, by=tuple(by), settings=settings)
    for column, codes in where.items():
        table = table.filter(pc.is_in(pc.cast(table.column(column), pa.string()), pa.array([str(c) for c in codes])))
    names = set(table.schema.names)
    if "municipality" in names:
        raw = table.column("municipality").to_pylist()
        codes = place_municipalities(raw) if place == "municipality" else place_states(raw)
    else:
        state = next((c for c in ("ufcod", "uf") if c in names), None)
        if state is None or place == "municipality":
            raise ValueError(f"population:{ident} is filed by {state or 'no place'}; it has no municipality place")
        raw = table.column(state).to_pylist()
        codes = [int(c) if c is not None and str(c).strip().removesuffix(".0") in UF_NUMERIC else None
                 for c in (None if r is None else str(r).strip().removesuffix(".0") for r in raw)]
    places = pa.array(codes, pa.int64())
    keep = pc.is_valid(places)
    lost = pc.invert(keep)
    unplaced = float(pc.sum(pc.filter(table.column("population"), lost)).as_py() or 0)
    unplaced_codes = sorted({str(r) for r, c in zip(raw, codes, strict=True) if c is None})
    unplaced_years = sorted({int(y) for y in pc.unique(pc.filter(table.column("year"), lost)).to_pylist()})
    facts = pa.table({"place": pc.filter(places, keep),
                      "period": pc.cast(pc.filter(table.column("year"), keep), pa.string()),
                      **{k: pc.filter(table.column(k), keep) for k in by},
                      "value": pc.cast(pc.filter(table.column("population"), keep), pa.float64())})
    if place == "country":
        facts = facts.set_column(0, "place", pc.multiply(facts.column("place"), 0))
    keys = ["place", "period", *by]
    facts = facts.group_by(keys).aggregate([("value", "sum")]).rename_columns([*keys, "value"]).select([*keys, "value"])
    if not facts.num_rows:
        raise ValueError(f"population:{ident} places no persons at {place} for {periods or 'any year'}")
    n = facts.num_rows
    facts = (facts.append_column("status", pa.array(["value"] * n, pa.string()))
             .append_column("unit", pa.array(["persons"] * n, pa.string()))
             .append_column("source", pa.array([f"population {ident}"] * n, pa.string())))
    series = json.loads((table.schema.metadata or {}).get(b"pegasus.series", b"{}"))
    return _with_manifest(facts, {"source": f"population:{ident}", "series": series, "place_level": place,
                                  "period_grain": "year", "strata": by, "additive_over": ["territory", "strata"],
                                  "stock": True, "unplaced_persons": unplaced, "unplaced_codes": unplaced_codes,
                                  "unplaced_years": unplaced_years})


def _climate(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]],
             periods: Sequence[str | int] | None, labels: bool, settings: Any, grain: str | None = None) -> pa.Table:
    """The climate family, one adapter whose id names the source: ``climate:<measure>`` (or ``climate:brdwgd/<measure>``)
    BR-DWGD's municipal climate by year, ``climate:inmet/<measure>`` INMET's stations by month or year, and
    ``climate:cptec/<variable>[@area]`` CPTEC's daily grids by day, epi week, month or year. Each is sums and the days,
    months or readings they rest on, never a finished mean; a place is never summed (a temperature is no part of its
    state's), so the cube is municipal."""
    source, _, rest = ident.partition("/")
    if source == "inmet":
        return _climate_inmet(rest, place=place, by=by, where=where, periods=periods, settings=settings, grain=grain)
    if source == "cptec":
        return _climate_cptec(rest, place=place, by=by, where=where, periods=periods, settings=settings, grain=grain)
    if grain not in (None, "year"):
        raise ValueError("BR-DWGD's climate cube is by year")
    return _climate_brdwgd(rest if source == "brdwgd" else ident, place=place, by=by, where=where, periods=periods,
                           settings=settings)


def _climate_brdwgd(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]],
                    periods: Sequence[str | int] | None, settings: Any) -> pa.Table:
    """A measure of BR-DWGD's municipal climate (one of `sources.brdwgd.MEASURES`) by municipality
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
    years = sorted(set(years_of(periods))) if periods else None
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


#: INMET's stored station-month columns: a measure's sum or extreme, the readings it rests on, and how months combine.
INMET_MEASURES = {
    "precipitation_mm": ("precipitation_mm_sum", "precipitation_readings", "sum", "mm"),
    "temperature_c": ("temperature_c_sum", "temperature_readings", "sum", "°C summed over readings"),
    "temperature_c_max": ("temperature_c_max", "temperature_readings", "max", "°C"),
    "temperature_c_min": ("temperature_c_min", "temperature_readings", "min", "°C"),
}


def _climate_inmet(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]],
                   periods: Sequence[str | int] | None, settings: Any, grain: str | None) -> pa.Table:
    """A measure of INMET's stations (``climate:inmet/<measure>``, one of `INMET_MEASURES`) by month or year, from the
    station-month base the build keeps (the field ``climate``: sums, readings and extremes). A station is no
    municipality: the cube's place is the municipality the station stands in (`inmet`'s placement) and the station
    (``station``) is a stratum that is never summed, because two stations of one municipality are two observations of
    two sites, not parts of one total. So ``station`` is named in ``by`` or fixed in ``where``. ``readings`` is what a
    value rests on (hours, or days for a conventional station), ``network`` the station's; a year adds the months'
    sums, takes the extreme of their extremes, and is ``incomplete`` below twelve months with a value. The value is the
    source's, with no completeness rule applied: whether a month is complete enough is the reader's (``readings``;
    `inmet.station_months` is the 90% rule the climate validation uses)."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    if ident not in INMET_MEASURES:
        raise KeyError(f"climate:inmet/<measure> is one of {sorted(INMET_MEASURES)}, got {ident!r}")
    if place != "municipality":
        raise ValueError("a station climate cube is municipal: its station is a stratum, never summed")
    if set(by) - {"station"} or set(where) - {"station"}:
        raise KeyError(f"climate:inmet has one stratum, station; got {sorted({*by, *where} - {'station'})}")
    if "station" not in by and "station" not in where:
        raise ValueError("climate:inmet is not additive over stations: name station in by, or fix it in where")
    grain = grain or "month"
    if grain not in ("month", "year"):
        raise ValueError("climate:inmet is by month or year")
    column, readings, law, unit = INMET_MEASURES[ident]
    directory = Path(settings.lake_dir) / "fields" / "climate"
    if not directory.is_dir():
        raise LookupError("INMET's station base is not built: run `pegasus-data fields --name climate`")
    dataset = ds.dataset(directory, format="parquet", partitioning="hive")
    expression = None
    if periods:
        years = sorted(set(years_of(periods)))
        expression = ds.field("year").isin(years)
    if "station" in where:
        clause = ds.field("station_id").isin([str(c) for c in where["station"]])
        expression = clause if expression is None else expression & clause
    table = dataset.to_table(columns=["station_id", "network", "municipality7", "year", "month", column, readings],
                             filter=expression)
    table = table.filter(pc.is_valid(table.column(column)))
    if periods:
        wanted = {str(p) for p in periods}
        keys = pc.binary_join_element_wise(pc.cast(table.column("year"), pa.string()),
                                           pc.utf8_lpad(pc.cast(table.column("month"), pa.string()), 2, "0"), "-")
        table = table.filter(pc.or_(pc.is_in(keys, pa.array(sorted(wanted))),
                                    pc.is_in(pc.cast(table.column("year"), pa.string()), pa.array(sorted(wanted)))))
    table = table.append_column("months", pa.array([1] * table.num_rows, pa.int64()))
    if grain == "year":
        grouped = table.group_by(["municipality7", "station_id", "network", "year"]).aggregate(
            [(column, law), (readings, "sum"), ("months", "sum")])
        table = pa.table({"municipality7": grouped.column("municipality7"), "station_id": grouped.column("station_id"),
                          "network": grouped.column("network"), "year": grouped.column("year"), "month": pa.nulls(
                              grouped.num_rows, pa.int64()), column: grouped.column(f"{column}_{law}"),
                          readings: grouped.column(f"{readings}_sum"), "months": grouped.column("months_sum")})
    period = (pc.cast(table.column("year"), pa.string()) if grain == "year" else pc.binary_join_element_wise(
        pc.cast(table.column("year"), pa.string()), pc.utf8_lpad(pc.cast(table.column("month"), pa.string()), 2, "0"), "-"))
    n = table.num_rows
    status = (pc.if_else(pc.greater_equal(table.column("months"), 12), "value", "incomplete") if grain == "year"
              else pa.array(["value"] * n, pa.string()))
    facts = pa.table({"place": pc.cast(table.column("municipality7"), pa.int64()), "period": period,
                      "station": table.column("station_id"), "value": pc.cast(table.column(column), pa.float64()),
                      "status": status, "unit": pa.array([unit] * n, pa.string()),
                      "source": pa.array(["INMET stations (Zenodo 14925215)"] * n, pa.string()),
                      "readings": table.column(readings), "network": table.column("network"),
                      **({"months": table.column("months")} if grain == "year" else {})})
    facts = facts.sort_by([("place", "ascending"), ("station", "ascending"), ("period", "ascending")])
    return _with_manifest(facts, {"source": f"climate:inmet/{ident}", "place_level": "municipality", "period_grain": grain,
                                  "strata": ["station"], "additive_over": ["months"] if law == "sum" else [],
                                  "extreme_over": ["months"] if law != "sum" else [], "denominator": "readings"})


def _climate_cptec(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]],
                   periods: Sequence[str | int] | None, settings: Any, grain: str | None) -> pa.Table:
    """A variable of CPTEC's daily grids (``climate:cptec/<variable>``, or ``<variable>@area`` for the area-weighted
    municipal mean; the default weighs by the people of the grade) summed over the days of each period, at ``grain`` (``day``,
    ``epi_week`` by the Ministry's rule, ``month`` (default) or ``year``). The value is the sum of the daily values (the
    period's rain; a temperature's mean is ``value / days``), ``days`` the days held, ``coverage`` their mean share of
    weight read at its own grid cell, and a period with fewer days than it has is ``incomplete`` (value kept). The latest
    vintage of each day is read. A scan of the daily files is aggregated inside the read (`cptec.period_sums`), so the
    periods are named: a national day table is never held."""
    import calendar
    import datetime as dt
    import functools

    import pyarrow.compute as pc

    from .sources import cptec

    variable, _, weight = ident.partition("@")
    weight = weight or "population"
    if variable not in cptec.PRODUCTS:
        raise KeyError(f"climate:cptec/<variable> is one of {sorted(cptec.PRODUCTS)}, got {variable!r}")
    if by or where:
        raise ValueError("a climate cube has no strata")
    if place != "municipality":
        raise ValueError("a climate cube is municipal: a temperature is not summed over places")
    if not periods:
        raise ValueError("climate:cptec reads daily files: name the periods (years, months or days)")
    grain = grain or "month"
    spans = []
    for p in (str(p) for p in periods):
        if len(p) == 4 and p.isdigit():
            spans.append((dt.date(int(p), 1, 1), dt.date(int(p), 12, 31)))
        elif len(p) == 7:
            y, m = divmod(parse_month(p) or _bad_month(p), 100)
            spans.append((dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])))
        elif len(p) == 10:
            spans.append((dt.date.fromisoformat(p),) * 2)
        else:
            raise ValueError(f"periods are years, months or days, got {p!r}")
    table = cptec.period_sums(variable, grain, start=min(s[0] for s in spans), end=max(s[1] for s in spans), weight=weight,
                              settings=settings)
    first, last = table.column("first_day"), table.column("last_day")
    inside = [pc.and_(pc.greater_equal(last, pa.scalar(a, pa.date32())), pc.less_equal(first, pa.scalar(b, pa.date32())))
              for a, b in spans]
    table = table.filter(functools.reduce(pc.or_, inside))
    periods_out = table.column("period").to_pylist()
    expected = pa.array([_period_days(p) for p in periods_out], pa.int64())
    n = table.num_rows
    product = cptec.PRODUCTS[variable]
    stamp = pc.strftime(table.column("published"), format="%Y-%m-%d")
    source = pc.binary_join_element_wise(pa.array([f"CPTEC {product.product} ({weight}), vintage "] * n, pa.string()), stamp, "")
    facts = pa.table({"place": pc.cast(table.column("municipality7"), pa.int64()), "period": table.column("period"),
                      "value": pc.cast(table.column("value"), pa.float64()),
                      "status": pc.if_else(pc.equal(table.column("days"), expected), "value", "incomplete"),
                      "unit": pa.array(["mm" if variable == "precipitation" else "°C summed over days"] * n, pa.string()),
                      "source": source, "days": table.column("days"),
                      "coverage": pc.cast(table.column("coverage"), pa.float64())})
    return _with_manifest(facts, {"source": f"climate:cptec/{ident}", "place_level": "municipality", "period_grain": grain,
                                  "strata": [], "additive_over": ["days"], "denominator": "days", "weight": weight,
                                  "product": product.product, "reference": product.reference})


def _period_days(period: str) -> int:
    """The days a period of the climate cubes holds (``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``, ``YYYY-Www``)."""
    import calendar

    if "-W" in period:
        return 7
    if len(period) == 4:
        return 366 if calendar.isleap(int(period)) else 365
    if len(period) == 7:
        return calendar.monthrange(*divmod(parse_month(period) or _bad_month(period), 100))[1]
    return 1


def _modelled(ident: str, *, place: str, by: list[str], where: dict[str, Sequence[Any]],
              periods: Sequence[str | int] | None, labels: bool, settings: Any) -> pa.Table:
    """An estimate of a modelled product as a cube (``modelled:<product>/<estimate>``, the latest version, or
    ``<product>@<version>/<estimate>``), on the axes its manifest declares (``place``, ``period``, ``strata``), its
    uncertainty carried as columns named by their suffix (``lo``, ``hi``, ``lo95``, ``hi95``). Never summed implicitly:
    every declared stratum is named in ``by`` or fixed in ``where``, except for an estimate the manifest declares
    ``additive``, whose point value sums over the strata left out (its bounds then do not: they are null). A place that
    is an area of several municipalities ("A+B") is no municipality and is counted, not placed; a product whose places
    are states is read at ``place="uf"``."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    from .geography import uf_codes_by_sigla
    from .modelled import read_modelled

    name, _, estimate = ident.partition("/")
    product, _, version = name.partition("@")
    _, manifest = read_modelled(product, version or None, settings=settings)
    folder = settings.modelled_dir / product / manifest["version"]
    if not manifest.get("place"):
        raise LookupError(f"modelled:{product} {manifest['version']}: its manifest declares no axes")
    if estimate not in manifest["estimates"]:
        raise KeyError(f"modelled:{product}: estimates are {sorted(manifest['estimates'])}, got {estimate!r}")
    strata, place_column, period_column = list(manifest["strata"]), manifest["place"], manifest["period"]
    unknown = [b for b in [*by, *where] if b not in strata]
    if unknown:
        raise KeyError(f"modelled:{product}: strata are {strata}, got {unknown}")
    additive = estimate in (manifest.get("additive") or [])
    left_out = [c for c in strata if c not in by and c not in where]
    if left_out and not additive:
        raise ValueError(f"modelled:{product}/{estimate} is not additive: name {left_out} in by or fix them in where")
    bounds = {c.removeprefix(f"{estimate}_"): c for c in manifest["estimates"][estimate]}
    states = place_column == "uf"
    if states != (place == "uf"):
        raise ValueError(f"modelled:{product}'s places are {'states' if states else 'municipalities'}; "
                         f"read it at place={'uf' if states else 'municipality'}")
    dataset = ds.dataset(folder / "estimates.parquet")
    expression = None
    if periods and period_column:
        years = years_of(periods)
        kind = dataset.schema.field(period_column).type
        expression = ds.field(period_column).isin(years if pa.types.is_integer(kind) else [str(p) for p in periods])
    for column, codes in where.items():
        kind = dataset.schema.field(column).type
        values = [int(c) for c in codes] if pa.types.is_integer(kind) else [str(c) for c in codes]
        clause = ds.field(column).isin(values)
        expression = clause if expression is None else expression & clause
    columns = list(dict.fromkeys([place_column, *([period_column] if period_column else []), *by, estimate,
                                  *bounds.values()]))
    table = dataset.to_table(columns=columns, filter=expression)
    raw = pc.cast(table.column(place_column), pa.string())
    if states:
        codes = {abbr: int(code) for abbr, code in uf_codes_by_sigla().items()}
        places = pa.array([int(v) if v and v.isdigit() else codes.get(v) for v in raw.to_pylist()], pa.int64())
    else:
        sole = pc.match_substring_regex(raw, r"^\d{6,7}$")
        places = pa.array(place_municipalities_of(raw, sole), pa.int64())
    keep = pc.is_valid(places)
    areas = int(pc.sum(pc.invert(keep)).as_py() or 0)
    period = (pc.cast(table.column(period_column), pa.string()) if period_column
              else pa.array([""] * table.num_rows, pa.string()))
    facts = pa.table({"place": places, "period": period, **{b: pc.cast(table.column(b), pa.string()) for b in by},
                      "value": pc.cast(table.column(estimate), pa.float64()),
                      **{k: pc.cast(table.column(c), pa.float64()) for k, c in bounds.items()}}).filter(keep)
    keys = ["place", "period", *by]
    if left_out:
        # an additive estimate summed over the strata left out; its bounds are not sums of bounds
        facts = facts.group_by(keys).aggregate([("value", "sum")]).rename_columns([*keys, "value"])
        for k in bounds:
            facts = facts.append_column(k, pa.nulls(facts.num_rows, pa.float64()))
    n = facts.num_rows
    facts = (facts.append_column("status", pa.array(["value"] * n, pa.string()))
             .append_column("unit", pa.array([estimate] * n, pa.string()))
             .append_column("source", pa.array([f"modelled {product} {manifest['version']}"] * n, pa.string())))
    return _with_manifest(facts, {"source": f"modelled:{product}/{estimate}", "version": manifest["version"],
                                  "tier": "modelled", "place_level": place, "strata": by, "summed_over": left_out,
                                  "additive": additive, "areas_not_municipalities": areas, "bounds": sorted(bounds),
                                  "model": manifest.get("model"), "validation": manifest.get("validation")})


def place_municipalities_of(raw: Any, sole: Any) -> list[int | None]:
    """A modelled product's places as municipalities (`geography.place_municipalities`); an area ("A+B") is none."""
    from .geography import place_municipalities

    values = raw.to_pylist()
    flags = sole.to_pylist()
    placed = place_municipalities([v if f else None for v, f in zip(values, flags, strict=True)])
    return placed


def _derived_dimensions(dataset: str, derived: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Each derived stratum's dimension: the bands of an age (``age``: a column of years, usually the derived variable
    ``IDADE_anos`` that `query` decodes by the system's declared age, `_age`), of a number (``field``), or of an age
    whose form is given in place (``form``)."""
    from ._age import parse_age, parse_band_dimensions

    out: dict[str, Any] = {}
    for name, body in derived.items():
        body = dict(body)
        if "field" in body:
            out[name] = parse_band_dimensions({name: body})[0]
        elif "age" in body:
            out[name] = parse_age({"form": "years", "fields": [body["age"]],
                                   **({"bands": body["bands"]} if body.get("bands") else {})}, name=name)
        else:
            out[name] = parse_age(body, name=name)
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


def manifest(table: pa.Table) -> dict[str, Any]:
    """What a cube is and what its build found (the ``pegasus.cube`` metadata `cube` writes); a table no cube made raises."""
    raw = (table.schema.metadata or {}).get(b"pegasus.cube")
    if raw is None:
        raise ValueError("not a cube: the table carries no pegasus.cube manifest")
    return json.loads(raw)


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


_ADAPTERS = {"sidra": _sidra, "series": _series, "records": _records, "population": _population, "climate": _climate,
             "modelled": _modelled}


