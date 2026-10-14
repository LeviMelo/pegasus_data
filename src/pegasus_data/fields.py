"""Context fields: IBGE's municipal statistics as a place × year layer.

A field is a property of a place and a year that is not a health event: GDP,
the weight of the public sector, agriculture. They are declared in
``curation/fields.yml`` by IBGE's own table and variable, read through the
general SIDRA interface (`pegasus_data.sidra`), and kept in ``<lake>/fields/<name>/`` one row per municipality
and year. Only totals are stored; a rate is computed at use over POPSVS.

IBGE's markers become a status: ``-`` is a true zero, while ``..`` (not
applicable), ``...`` (not available) and ``X`` (suppressed) are null with
their reason.

A field declared with ``series:`` is one measure of a series stitched across the censuses
(``curation/sidra/series.yml``): the same concept in 2000, 2010 and 2022 where IBGE's tables allow it, with the
series' own statement of comparability and gaps. A share is a numerator field over a denominator field.

A field declared in ``curation/intake.yml`` (`pegasus_data.intake`, ADR-0162) comes from a source that is not on the FTP and
is read, reduced and served by that one mechanism: the DEMAS API and the Portal de Dados Abertos' files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pyarrow as pa

from .semantics.epoch import curated

__all__ = ["build_fields", "declared_fields", "field_rate", "load_field"]


def write_parquet_atomic(table: pa.Table, target: Path, **options: Any) -> None:
    """Write ``target`` whole or not at all: to a hidden file beside it (a dataset scan ignores a leading ``_``), then
    renamed over it. A second process finding the file never reads half of it, and a crash leaves no truncated file for
    a cache to trust forever."""
    import pyarrow.parquet as pq

    target = Path(target)
    tmp = target.with_name(f"_{target.name}.{os.getpid()}.tmp")
    try:
        pq.write_table(table, tmp, **options)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


@curated(rooted=True)
def declared_fields(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """The declared fields (``fields.yml`` and the intake sources'), once per curation epoch. Shared: not to be edited."""
    from .config import curation_root
    from .intake import intake_fields
    from .ontology import _read_yaml

    base = root or curation_root()
    return {**dict((_read_yaml(base / "fields.yml") or {}).get("fields") or {}), **intake_fields(base)}


def _years(text: str) -> list[int]:
    """``2002-2023`` (a span) or ``2010, 2022`` (census years)."""
    out: list[int] = []
    for part in str(text).split(","):
        lo, _, hi = part.strip().partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def _classification(spec: dict[str, Any]) -> str:
    """IBGE's ``classificacao`` parameter as the source string: ``59[1023]|2[6794]``; omitted ones are its Total."""
    chosen = spec.get("classification") or {}
    return "|".join(f"{k}[{v}]" for k, v in chosen.items())


def build_fields(settings: Any, names: list[str] | None = None, years: list[int] | None = None) -> dict[str, Any]:
    """Read each declared field from its source and write it to ``<lake>/fields/<name>/``."""
    report: dict[str, Any] = {}
    sidra = None
    declared = declared_fields()
    chosen_cnes = {n: sp for n, sp in declared.items() if sp.get("source") == "cnes" and (not names or n in names)}
    if chosen_cnes:
        report.update(_build_cnes(settings, chosen_cnes, years))
    if "climate" in declared and (not names or "climate" in names):
        report.update(_build_climate(settings, years))
    chosen_brdwgd = {n: sp for n, sp in declared.items() if sp.get("source") == "brdwgd" and (not names or n in names)}
    if chosen_brdwgd:
        report.update(_build_climate_brdwgd(settings, chosen_brdwgd, years))
    chosen_intake: dict[str, list[str]] = {}
    for name, spec in declared.items():
        if spec.get("source") == "intake" and (not names or name in names):
            chosen_intake.setdefault(spec["intake"], []).append(name)
    if chosen_intake:
        from .intake import build_source

        for source, fields in chosen_intake.items():
            result = build_source(settings, source, fields, years)
            report.update({f: result[f] for f in fields})
            report[f"intake:{source}"] = {k: v for k, v in result.items() if k not in fields}
    for name, spec in declared.items():
        if names and name not in names:
            continue
        if spec.get("source") in ("cnes", "intake", "inmet", "brdwgd"):
            continue
        if sidra is None:
            from .sidra import Sidra

            sidra = Sidra(settings=settings)
        build = _build_series_field if spec.get("series") else _build_sidra
        report[name] = build(settings, sidra, name, spec, years)
    return report


def _build_series_field(settings: Any, sidra: Any, name: str, spec: dict[str, Any], years: list[int] | None) -> dict[str, Any]:
    """One measure of a stitched series as a place × year field.

    ``measure`` is the series' ``numerator``/``denominator``/``value``; ``where`` names the categories of an axis the
    field takes and sums (``{income_band: [le_half, none]}``). The claim the series ``selected`` is the one kept; a
    figure that is missing for a municipality stays a null with IBGE's reason.
    """
    import pyarrow.compute as pc

    from .sidra.series import series_values

    wanted = [y for y in _years(spec["years"]) if not years or y in years]
    values = series_values(sidra, spec["series"], spec.get("measure", "value"), spec.get("where"))
    written = 0
    statuses: dict[str, int] = {}
    for year in wanted:
        part = values.filter(pc.equal(values.column("period"), str(year)))
        if part.num_rows == 0:
            continue
        code7 = part.column("locality").to_pylist()
        n = len(code7)
        source = [f"IBGE agregados {t} v{v} (series {spec['series']})" for t, v in zip(part.column("table").to_pylist(), part.column("variable").to_pylist(), strict=True)]
        table = pa.table({
            "municipality": pa.array([c[:6] for c in code7], pa.string()),
            "municipality7": pa.array(code7, pa.string()),
            "value": part.column("value"),
            "status": part.column("status"),
            "unit": pa.array([str(spec["unit"])] * n, pa.string()),
            "source": pa.array(source, pa.string()),
        })
        for state in part.column("status").to_pylist():
            statuses[state] = statuses.get(state, 0) + 1
        target = Path(settings.lake_dir) / "fields" / name / f"year={year}"
        target.mkdir(parents=True, exist_ok=True)
        write_parquet_atomic(table, target / "part.parquet", compression="zstd")
        written += n
    return {"years": len(wanted), "rows": written, "statuses": statuses}


def _build_sidra(settings: Any, sidra: Any, name: str, spec: dict[str, Any], years: list[int] | None) -> dict[str, Any]:
    """An IBGE aggregate (table, variable, one category of some classifications) as a place × year field.

    The request is planned, fetched and cached by `pegasus_data.sidra`; this keeps the municipality, the
    value and IBGE's marker as a status (``-`` a true zero; ``..``, ``...`` and ``X`` null with their reason).
    """
    import pyarrow.compute as pc

    wanted = [y for y in _years(spec["years"]) if not years or y in years]
    chosen = _classification(spec)
    selection = sidra.selection(
        int(spec["table"]), variables=[int(spec["variable"])], periods=[str(y) for y in wanted],
        classifications={int(k): [int(v)] for k, v in (spec.get("classification") or {}).items()})
    report = sidra.fetch(selection, log=lambda _m: None)
    if report["shortfalls"]:                      # a request that returned fewer cells than it asked for: never a quiet gap
        raise RuntimeError(f"field {name!r}: SIDRA returned fewer values than planned: {report['shortfalls'][:2]}")
    facts = sidra.slice(int(spec["table"]), variables=[int(spec["variable"])], periods=selection.periods,
                        picks={int(k): [int(v)] for k, v in (spec.get("classification") or {}).items()})
    source = f"IBGE agregados {spec['table']} v{spec['variable']}" + (f" c{chosen}" if chosen else "")
    written = 0
    statuses: dict[str, int] = {}
    for year in wanted:
        part = facts.filter(pc.equal(facts.column("period"), str(year)))
        if part.num_rows == 0:
            continue
        code7 = part.column("locality").to_pylist()
        n = len(code7)
        table = pa.table({
            "municipality": pa.array([c[:6] for c in code7], pa.string()),
            "municipality7": pa.array(code7, pa.string()),
            "value": part.column("value"),
            "status": part.column("status"),
            "unit": pa.array([str(spec["unit"])] * n, pa.string()),
            "source": pa.array([source] * n, pa.string()),
        })
        for state in part.column("status").to_pylist():
            statuses[state] = statuses.get(state, 0) + 1
        target = Path(settings.lake_dir) / "fields" / name / f"year={year}"
        target.mkdir(parents=True, exist_ok=True)
        write_parquet_atomic(table, target / "part.parquet", compression="zstd")
        written += n
    return {"years": len(wanted), "rows": written, "statuses": statuses}


def _build_cnes(settings: Any, specs: dict[str, dict[str, Any]], years: list[int] | None) -> dict[str, Any]:
    """The CNES supply fields (``sources.cnes``): every selected field of a December from one pass over its files.

    Rows exist for every IBGE municipality (the current 5,570). One in the year's ST register carries its value, a
    true 0 included (``ok``); one that has no establishment in the register is a null with ``no_cnes_record``.
    Codes the register holds that are not an IBGE municipality are *unallocated*: summed and reported per field.
    """

    from .geography import municipalities
    from .sources import cnes

    cache = Path(settings.root) / "registries" / "CNES"
    universe = municipalities()
    code7 = {c6: row["code7"] for c6, row in universe.items()}
    wanted = sorted({y for sp in specs.values() for y in _years(sp["years"]) if not years or y in years})
    report: dict[str, Any] = {name: {"years": {}} for name in specs}
    for year in wanted:
        tables = cnes.year_tables(year, cache)
        in_register = cnes.register(tables)
        for name, spec in specs.items():
            if year not in _years(spec["years"]):
                continue
            found = cnes.values(spec, tables)
            keys = sorted(code7)
            n = len(keys)
            value = [found.get(k, 0.0) if k in in_register else None for k in keys]
            table = pa.table({
                "municipality": pa.array(keys, pa.string()),
                "municipality7": pa.array([code7[k] for k in keys], pa.string()),
                "value": pa.array(value, pa.float64()),
                "status": pa.array(["ok" if k in in_register else "no_cnes_record" for k in keys], pa.string()),
                "unit": pa.array([str(spec["unit"])] * n, pa.string()),
                "source": pa.array([f"CNES-{'ST' if spec['family'] == 'facilities' else {'beds': 'LT', 'equipment': 'EQ', 'teams': 'EP', 'professionals': 'PF'}[spec['family']]} {year}-12"] * n, pa.string()),
            })
            target = Path(settings.lake_dir) / "fields" / name / f"year={year}"
            target.mkdir(parents=True, exist_ok=True)
            write_parquet_atomic(table, target / "part.parquet", compression="zstd")
            unallocated = {k: v for k, v in found.items() if k not in code7}
            report[name]["years"][str(year)] = {
                "total": sum(v for k, v in found.items() if k in code7), "unallocated": sum(unallocated.values()),
                "unallocated_codes": dict(sorted(unallocated.items(), key=lambda kv: -kv[1])[:5]),
                "no_cnes_record": n - sum(1 for k in keys if k in in_register)}
    return report


def field_rate(name: str, *, per: float = 1000.0, years: list[int] | int | None = None, settings: Any = None) -> pa.Table:
    """A sum field over the resident population: (municipality, year, numerator, population, rate per ``per``).

    The population is the municipal total of ``population-account-2`` (reference date 1 August), summed over sex
    and age; a ratio of sums, so any group of municipalities lifts it by summing numerator and population. A
    population-account place that merges municipalities (a post-2010 creation inside its parent's area) has no
    separate figure: its members are left without a rate and counted in ``rate_missing`` below, not given a share.
    """
    import pyarrow.compute as pc

    from .config import load_settings
    from .modelled import read_modelled

    settings = settings or load_settings()
    field = load_field(name, years=years, settings=settings).filter(pc.field("status") == "ok")
    wanted = sorted(set(field.column("year").to_pylist()))
    account, _ = read_modelled("population_account", "population-account-2", settings=settings)
    account = account.filter(pc.and_(pc.equal(account.column("place_kind"), "municipality"), pc.is_in(account.column("year"), value_set=pa.array(wanted, account.column("year").type))))
    total = account.group_by(["place", "year"]).aggregate([("population", "sum")])
    single = pc.invert(pc.match_substring(total.column("place"), "+"))
    total = total.filter(single)
    population = {(p[:6], int(y)): v for p, y, v in zip(total.column("place").to_pylist(), total.column("year").to_pylist(),
                                                      total.column("population_sum").to_pylist(), strict=True)}
    municipality = field.column("municipality").to_pylist()
    year = [int(y) for y in field.column("year").to_pylist()]
    numerator = field.column("value").to_pylist()
    denominator = [population.get((m, y)) for m, y in zip(municipality, year, strict=True)]
    rate = [None if d is None or n is None or d <= 0 else n / d * per for n, d in zip(numerator, denominator, strict=True)]
    return pa.table({"municipality": municipality, "year": year, "numerator": numerator, "population": denominator,
                     "rate": rate, "per": [per] * len(rate)})


def _build_climate(settings: Any, years: list[int] | None) -> dict[str, Any]:
    """INMET's stations (``sources.inmet``): the station-month sums, counts and extremes placed in the municipality
    each station stands in (the field ``climate``). Observations kept to validate the BR-DWGD climate fields
    (`_build_climate_brdwgd`), not their source."""
    import pyarrow.compute as pc

    from .geography import mesh_file
    from .sources import inmet

    cache = Path(settings.root) / "registries" / "inmet"
    mesh = mesh_file("municipality", "maxima", settings.root)
    placed = {s["station_id"]: s for s in inmet.stations(cache, mesh) if s["municipality7"]}
    table = inmet.monthly(cache, years)
    ids = table.column("station_id").to_pylist()
    code7 = [placed[i]["municipality7"] if i in placed else None for i in ids]
    table = table.append_column("municipality7", pa.array(code7, pa.string()))
    # Where the station's position came from, how it was placed, and the
    # municipality INMET itself registers it in, so an analysis can keep only
    # positions it trusts and see where the two disagree (sources/inmet.py).
    for key in ("coordinates_from", "placed_by", "inmet_municipality7"):
        table = table.append_column(key, pa.array([placed[i][key] if i in placed else None for i in ids], pa.string()))
    table = table.append_column("municipality", pc.utf8_slice_codeunits(table.column("municipality7"), 0, 6))
    unplaced = int(pc.sum(pc.is_null(table.column("municipality7"))).as_py() or 0)
    table = table.filter(pc.is_valid(table.column("municipality7")))
    written = 0
    for year in sorted(set(table.column("year").to_pylist())):
        part = table.filter(pc.equal(table.column("year"), year)).drop_columns(["year"])
        target = Path(settings.lake_dir) / "fields" / "climate" / f"year={year}"
        target.mkdir(parents=True, exist_ok=True)
        write_parquet_atomic(part, target / "part.parquet", compression="zstd")
        written += part.num_rows
    return {"climate": {"rows": written, "stations_placed": len(placed), "station_months_unplaced": unplaced}}


def _build_climate_brdwgd(settings: Any, specs: dict[str, dict[str, Any]], years: list[int] | None) -> dict[str, Any]:
    """BR-DWGD's municipal zonal statistics (``sources.brdwgd``, ADR-0178): the base ``climate_monthly`` and the fields read
    from it, one value per municipality and year.

    A field with a ``measure`` is one column of `brdwgd.municipality_years`: a sum with its denominator declared in
    ``over`` (the mean is the ratio, formed at use). Its ``status`` is ``ok`` when all twelve months are held and
    ``partial_year`` otherwise (the value is kept), its ``source`` names the release of that row and ``months`` what it
    rests on. A municipality the release does not hold has no row, and is named in the report.
    """
    import pyarrow.compute as pc

    from .geography import municipalities
    from .sources import brdwgd

    months, release = brdwgd.municipality_months(Path(settings.root) / "registries" / "brdwgd")
    expected = {row["code7"] for row in municipalities().values()}
    held = set(months.column("municipality7").unique().to_pylist())
    months = months.filter(pc.is_in(months.column("municipality7"), value_set=pa.array(sorted(expected), pa.string())))
    if years:
        months = months.filter(pc.is_in(months.column("year"), value_set=pa.array(years, pa.int32())))
    report: dict[str, Any] = {"release": f"BR-DWGD v{release['version']}, Zenodo {release['record']}, {release['published']}"
                                         + (" (kept: Zenodo could not be asked)" if release.get("offline") else ""),
                              "municipalities_without_series": sorted(expected - held)}
    if "climate_monthly" in specs:
        base = months.append_column("municipality", pc.utf8_slice_codeunits(months.column("municipality7"), 0, 6))
        report["climate_monthly"] = {"rows": _write_by_year(base, "climate_monthly", settings, prune=not years),
                                     "years": f"{pc.min(months.column('year')).as_py()}-{pc.max(months.column('year')).as_py()}"}
    derived = {name: spec for name, spec in specs.items() if spec.get("measure")}
    if derived:
        annual = brdwgd.municipality_years(months)
        for name, spec in derived.items():
            variable = brdwgd.MEASURES[spec["measure"]]
            kept = annual.filter(pc.is_valid(annual.column(spec["measure"])))
            n = kept.num_rows
            held_months = kept.column(f"{variable}_months")
            status = pc.if_else(pc.greater_equal(held_months, 12 - 1e-9), "ok", "partial_year")
            out = pa.table({
                "municipality": kept.column("municipality"), "municipality7": kept.column("municipality7"),
                "value": kept.column(spec["measure"]), "status": status,
                "unit": pa.array([str(spec["unit"])] * n, pa.string()), "source": kept.column("product"),
                "months": held_months, "year": kept.column("year")})
            _write_by_year(out, name, settings, prune=not years)
            report[name] = {"rows": n, "ok": int(pc.sum(pc.equal(status, "ok")).as_py() or 0),
                            "partial_year": int(pc.sum(pc.equal(status, "partial_year")).as_py() or 0)}
    return report


def _write_by_year(table: pa.Table, name: str, settings: Any, prune: bool = False) -> int:
    """``table`` split by its ``year`` column into ``<lake>/fields/<name>/year=<year>/part.parquet`` (the column itself is
    the partition and is dropped); the rows written. With ``prune`` the years of the field that ``table`` does not hold
    are removed: a whole-period build replaces the field, it does not leave another source's years beside its own."""
    import shutil

    import pyarrow.compute as pc

    years = sorted(set(table.column("year").to_pylist()))
    for year in years:
        part = table.filter(pc.equal(table.column("year"), year)).drop_columns(["year"])
        target = Path(settings.lake_dir) / "fields" / name / f"year={int(year)}"
        target.mkdir(parents=True, exist_ok=True)
        write_parquet_atomic(part, target / "part.parquet", compression="zstd")
    if prune:
        keep = {f"year={int(y)}" for y in years}
        for stale in (Path(settings.lake_dir) / "fields" / name).glob("year=*"):
            if stale.name not in keep:
                shutil.rmtree(stale)
    return table.num_rows


def load_field(name: str, *, years: list[int] | int | None = None, settings: Any = None) -> pa.Table:
    """One field as (municipality, year, value, status, unit), from the lake."""
    import pyarrow.dataset as ds

    from .config import load_settings

    if name not in declared_fields():
        raise KeyError(f"unknown field {name!r}; declared: {sorted(declared_fields())}")
    settings = settings or load_settings()
    directory = Path(settings.lake_dir) / "fields" / name
    if not directory.exists():
        raise FileNotFoundError(f"field {name!r} is not in the lake; run `pegasus-data fields --name {name}`")
    dataset = ds.dataset(directory, format="parquet", partitioning="hive")
    wanted = [years] if isinstance(years, int) else years
    expression = ds.field("year").isin(wanted) if wanted else None
    return dataset.to_table(filter=expression)
