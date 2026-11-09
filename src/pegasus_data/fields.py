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

Every declared field has a ``label``, its short name for a list (sentence case, about six words), beside ``what``, its
sentence; two fields that differ say how in their labels (`unlabelled_fields`, `shared_labels`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pyarrow as pa

from .semantics.epoch import curated

__all__ = ["build_fields", "declared_fields", "field_rate", "load_field", "shared_labels", "unlabelled_fields"]


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


def unlabelled_fields() -> list[str]:
    """The declared fields with no ``label`` (the short name a list shows; ``what`` is the sentence). The list a reviewer
    closes, never a default."""
    return sorted(n for n, spec in declared_fields().items() if not str(spec.get("label") or "").strip())


def shared_labels() -> dict[str, list[str]]:
    """The labels two or more declared fields carry, folded as names are matched (case, hyphens and spaces do not tell
    two labels apart), each with its fields: fields that differ (SUS or all, jobs or persons) say how. Empty when none."""
    from .textenc import fold

    declared = declared_fields()
    seen: dict[str, list[str]] = {}
    for name, spec in declared.items():
        if str(spec.get("label") or "").strip():
            seen.setdefault(fold(spec["label"]), []).append(name)
    return {declared[names[0]]["label"]: names for names in seen.values() if len(names) > 1}


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
    # A CNES field that is a records cube is built as one (cached by its register's fingerprint, ADR-0217); only the
    # professionals' fields still need `sources.cnes`'s own pass over the PF files.
    for name in [n for n, sp in chosen_cnes.items() if cnes_cube(n, sp) is not None]:
        table = load_field(name, years=years, settings=settings)
        report[name] = {"rows": table.num_rows, "cube": True}
        chosen_cnes.pop(name)
    if chosen_cnes:
        report.update(_build_cnes(settings, chosen_cnes, years))
    if "climate" in declared and (not names or "climate" in names):
        report.update(_build_climate(settings, years))
    chosen_brdwgd = {n: sp for n, sp in declared.items() if sp.get("source") == "brdwgd" and (not names or n in names)}
    if chosen_brdwgd:
        report.update(_build_climate_brdwgd(settings, chosen_brdwgd, years))
    chosen_intake: dict[str, list[str]] = {}
    from .intake import declared_sources

    sources = declared_sources()
    for name, spec in declared.items():
        if spec.get("source") != "intake" or (names and name not in names):
            continue
        if not names and (sources.get(spec["intake"], {}).get("origin") or {}).get("on_request"):
            # Too large to land whole (SI-PNI's doses): built only when named, with its years.
            report[name] = {"skipped": f"source {spec['intake']} is declared on request: name the field and its years"}
            continue
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
    """Fetch what a series field reads into SIDRA's fact store; the field is the cube ``series:<name>/<measure>`` and is
    served from the store by `load_field` (ADR-0217), never copied."""
    from .sidra.series import fetch_series

    fetch_series(sidra, spec["series"], log=lambda _m: None)
    return _cube_report(name, spec, years, settings)


def _build_sidra(settings: Any, sidra: Any, name: str, spec: dict[str, Any], years: list[int] | None) -> dict[str, Any]:
    """Fetch an IBGE aggregate (table, variable, the categories named) into SIDRA's fact store; the field is the cube
    ``sidra:<table>/<variable>`` and is served from the store by `load_field` (ADR-0217), never copied."""
    wanted = [y for y in _years(spec["years"]) if not years or y in years]
    selection = sidra.selection(
        int(spec["table"]), variables=[int(spec["variable"])], periods=[str(y) for y in wanted],
        classifications={int(k): [int(v)] for k, v in (spec.get("classification") or {}).items()})
    report = sidra.fetch(selection, log=lambda _m: None)
    if report["shortfalls"]:                      # a request that returned fewer cells than it asked for: never a quiet gap
        raise RuntimeError(f"field {name!r}: SIDRA returned fewer values than planned: {report['shortfalls'][:2]}")
    return _cube_report(name, spec, years, settings)


def cube_of(spec: dict[str, Any]) -> tuple[str, dict[str, list[Any]]] | None:
    """The cube a SIDRA or series field is (source, where), or None for a field that is still built apart."""
    if spec.get("table"):
        return (f"sidra:{spec['table']}/{spec['variable']}",
                {f"c{k}": [v] for k, v in (spec.get("classification") or {}).items()})
    if spec.get("series"):
        return f"series:{spec['series']}/{spec.get('measure', 'value')}", dict(spec.get("where") or {})
    return None


def _field_from_cube(name: str, spec: dict[str, Any], years: list[int] | None, settings: Any) -> pa.Table:
    """A SIDRA or series field read from its cube, in the field's columns (municipality, municipality7, value, status,
    unit, source, year): what `load_field` returned when the field was a stored copy, value for value (evaluation
    2026-11-08-the-one-map: 26 fields, 0 differences)."""
    import pyarrow.compute as pc

    from .cubes import cube

    source, where = cube_of(spec) or ("", {})
    declared = [str(y) for y in _years(spec["years"])]
    # Only the declared years are asked of the cube; a year the field does not have is no row, as the stored copy gave.
    periods = [str(y) for y in years if str(y) in declared] if years else declared
    if not periods:
        return pa.table({"municipality": pa.array([], pa.string()), "municipality7": pa.array([], pa.string()),
                         "value": pa.array([], pa.float64()), "status": pa.array([], pa.string()),
                         "unit": pa.array([], pa.string()), "source": pa.array([], pa.string()),
                         "year": pa.array([], pa.int32())})
    table = cube(source, where=where, periods=periods, labels=False, settings=settings)
    table = table.filter(pc.is_in(table.column("period"), pa.array(declared)))
    code7 = pc.cast(table.column("place"), pa.string())
    unit = str(spec["unit"])
    return pa.table({
        "municipality": pc.utf8_slice_codeunits(code7, 0, 6),
        "municipality7": code7,
        "value": table.column("value"),
        "status": table.column("status"),
        "unit": pa.array([unit] * table.num_rows, pa.string()),
        "source": table.column("source") if spec.get("series") else pa.array(
            [_sidra_source(spec)] * table.num_rows, pa.string()),
        "year": pc.cast(table.column("period"), pa.int32()),
    })


def intake_cube(name: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    """The records cube an intake field is, or None for one still built apart: a count or a sum, with its `where` and
    `by`, over a landed dataset placed by municipality code with place and time bindings (curated, or read from its
    roles). Shares (`outcome`), unpivoted margins and row registers are not yet cubes; neither is a field whose dataset
    holds no landed records, whose stored copy is then the only form of its data (ANS's beneficiaries)."""
    from .intake import _strata, declared_sources
    from .semantics.curation import semantics_for

    if spec.get("source") != "intake":
        return None
    source = declared_sources().get(str(spec.get("intake")))
    fs = ((source or {}).get("fields") or {}).get(name) if source else None
    if not fs or fs.get("unpivot") or fs.get("rows"):
        return None
    if (source.get("place") or {}).get("type") != "municipality":
        return None
    dataset = f"{source['system']}-{source['series']}"
    if semantics_for(dataset) is None or not _landed(source):
        return None
    from .semantics.event_types import event_types

    try:
        events = [e["name"] for e in event_types(dataset)]
    except KeyError:
        events = []
    measure = fs["measure"]["sum"] if isinstance(fs.get("measure"), dict) else None
    cube_source = f"records:{dataset}/{events[0] if events else 'rows'}"
    where = dict(fs.get("where") or {})
    support = None
    if fs.get("outcome"):
        # a share's numerator: its population's records with the outcome, a row (0 where none) wherever the population has one
        if fs.get("by"):
            return None
        support = {"source": cube_source, "where": dict(where)}
        where = {**where, **fs["outcome"]}
    return {"source": cube_source, "dataset": dataset, "support": support,
            "where": where, "strata": _strata(fs),
            "measure": str(measure).upper() if measure else None,
            "grain": (source.get("period") or {}).get("grain") or "year",
            "citation": str(source.get("citation") or source.get("what") or "")}


def _landed(source: dict[str, Any]) -> bool:
    from .catalog.store import CatalogStore
    from .config import load_settings

    store = CatalogStore(load_settings().catalog_path, read_only=True)
    try:
        return bool(store.query("SELECT 1 FROM families WHERE system = ? AND series = ? AND schema_source = 'intake' LIMIT 1",
                                (str(source["system"]).upper(), str(source["series"]).upper())))
    finally:
        store.close()


def _field_from_records(name: str, spec: dict[str, Any], plan: dict[str, Any], years: list[int] | None,
                        settings: Any) -> pa.Table:
    """An intake field read from its records cube, in the field's columns: (municipality, [month], its strata, value,
    municipality7, status, unit, source, year), as `intake._derive` wrote them (evaluation 2026-11-09-the-cube-stage-1).
    An event source's events follow its event type (SRAG's notifications filed in two yearly files count once)."""
    import pyarrow.compute as pc

    from ._explore import explore
    from .cubes import cube

    # a field that names no years is read on the years its dataset publishes (SRAG's notifications)
    declared = (_years(spec["years"]) if str(spec.get("years") or "").strip()
                else sorted({int(r["year"]) for r in explore(plan["dataset"]).as_dict()["rows"] if r.get("year")}))
    periods = [y for y in (years or declared) if y in declared]
    columns = [c for c, _ in plan["strata"]]
    if periods:
        table = cube(plan["source"], periods=periods, grain=plan["grain"], by=columns, where=plan["where"],
                     measure=plan["measure"], support=plan.get("support"), settings=settings)
    else:
        table = pa.table({"place": pa.array([], pa.int64()), "period": pa.array([], pa.string()),
                          **{c: pa.array([], pa.string()) for c in columns}, "value": pa.array([], pa.float64())})
    code7 = pc.cast(table.column("place"), pa.string())
    period = table.column("period")
    n = table.num_rows
    out: dict[str, Any] = {"municipality": pc.utf8_slice_codeunits(code7, 0, 6)}
    if plan["grain"] == "month":
        # a period kept at its year (its month not recorded) has no month, as the field had it
        month = pc.utf8_slice_codeunits(period, 5, 7)
        out["month"] = pc.cast(pc.if_else(pc.equal(month, ""), pa.scalar(None, pa.string()), month), pa.int32())
    for column, alias in plan["strata"]:
        out[alias] = pc.cast(table.column(column), pa.string())
    out.update({
        "value": pc.cast(table.column("value"), pa.float64()),
        "municipality7": code7,
        "status": pa.array(["ok"] * n, pa.string()),
        "unit": pa.array([str(spec.get("unit") or "")] * n, pa.string()),
        "source": pa.array([plan["citation"]] * n, pa.string()),
        "year": pc.cast(pc.utf8_slice_codeunits(period, 0, 4), pa.int32()),
    })
    return pa.table(out)


def cnes_cube(name: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    """The records cube a CNES supply field is: a December's register read by the one reader (its files adopted from
    the mirror, `adopt.adopt_copies`), the field's groups as code lists on the register's own columns, its stock counted
    (establishments and teams as distinct codes) or summed (beds, equipment). The support is December's ST register: a
    municipality with no establishment in it has no value (``no_cnes_record``), one with establishments and none of the
    field's is a true 0. A field of professionals (PF) is not yet a cube: its files are not held."""
    from .sources.cnes import NOT_DEACTIVATED, groups

    if spec.get("source") != "cnes" or spec.get("family") == "professionals":
        return None
    g = groups()
    family = spec["family"]
    where: dict[str, Any] = {}
    if family == "facilities":
        listed = [c for codes in g["facility_groups"].values() for c in codes]
        group = spec["group"]
        where["TP_UNID"] = {"not": listed} if group == "other" else list(g["facility_groups"][group])
        where["VINC_SUS"] = ["1"] if spec["sector"] == "sus" else {"not": ["1"]}
        dataset, measure = "CNES-ST", "distinct:CNES"
    elif family == "beds":
        if spec["kind"] in ("icu", "neonatal_icu"):
            where["CODLEITO"] = list(g[f"{spec['kind']}_bed_codes"])
        dataset, measure = "CNES-LT", {"all": "QT_EXIST", "sus": "QT_SUS", "nonsus": "QT_NSUS"}[spec["sector"]]
    elif family == "equipment":
        where["TIPEQUIP+CODEQUIP"] = list(g["equipment"][spec["equipment"]])
        if spec["sector"] == "sus":
            where["IND_SUS"] = ["1"]
        dataset, measure = "CNES-EQ", "QT_EXIST"
    elif family == "teams":
        where["TIPO_EQP"] = list(g["team_groups"][spec["group"]])
        where["DT_DESAT"] = list(NOT_DEACTIVATED)
        dataset, measure = "CNES-EP", "distinct:IDEQUIPE"
    else:
        return None
    return {"source": f"records:{dataset}/rows", "dataset": dataset, "where": where, "measure": measure,
            "support": "records:CNES-ST/rows"}


def _field_from_cnes(name: str, spec: dict[str, Any], plan: dict[str, Any], years: list[int] | None,
                     settings: Any) -> pa.Table:
    """A CNES field from its cube, in the field's columns, one row per IBGE municipality and year: the value inside the
    register's support (``ok``), else a null (``no_cnes_record``), as `_build_cnes` wrote them."""
    from .cubes import cube
    from .geography import municipalities

    declared = _years(spec["years"])
    wanted = [y for y in (years or declared) if y in declared]
    universe = municipalities()
    keys = sorted(universe)
    columns: dict[str, list[Any]] = {k: [] for k in ("municipality", "municipality7", "value", "status", "unit", "source", "year")}
    for year in wanted:
        table = cube(plan["source"], periods=[f"{year}-12"], grain="month", where=plan["where"], measure=plan["measure"],
                     support=plan["support"], settings=settings)
        found = {str(r["place"]): r["value"] for r in table.select(["place", "value"]).to_pylist()}
        label = f"{plan['dataset']} {year}-12"
        for six in keys:
            code7 = str(universe[six]["code7"])
            held = code7 in found
            columns["municipality"].append(six)
            columns["municipality7"].append(code7)
            columns["value"].append(float(found[code7]) if held else None)
            columns["status"].append("ok" if held else "no_cnes_record")
            columns["unit"].append(str(spec["unit"]))
            columns["source"].append(label)
            columns["year"].append(year)
    return pa.table({"municipality": pa.array(columns["municipality"], pa.string()),
                     "municipality7": pa.array(columns["municipality7"], pa.string()),
                     "value": pa.array(columns["value"], pa.float64()),
                     "status": pa.array(columns["status"], pa.string()),
                     "unit": pa.array(columns["unit"], pa.string()),
                     "source": pa.array(columns["source"], pa.string()),
                     "year": pa.array(columns["year"], pa.int32())})


def _sidra_source(spec: dict[str, Any]) -> str:
    chosen = _classification(spec)
    return f"IBGE agregados {spec['table']} v{spec['variable']}" + (f" c{chosen}" if chosen else "")


def _cube_report(name: str, spec: dict[str, Any], years: list[int] | None, settings: Any) -> dict[str, Any]:
    table = _field_from_cube(name, spec, years, settings)
    statuses: dict[str, int] = {}
    for state in table.column("status").to_pylist():
        statuses[state] = statuses.get(state, 0) + 1
    return {"years": len(set(table.column("year").to_pylist())), "rows": table.num_rows, "statuses": statuses}


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
    """One field as (municipality, year, value, status, unit), from the lake. A field declared ``grain: month`` also has a
    ``month`` (1-12) and one row per municipality and month that has records: a year is the sum of its months (``law: sum``),
    a municipality-month without records has no row (missing, never 0)."""
    import pyarrow.dataset as ds

    from .config import load_settings

    if name not in declared_fields():
        raise KeyError(f"unknown field {name!r}; declared: {sorted(declared_fields())}")
    settings = settings or load_settings()
    spec = declared_fields()[name]
    wanted = [years] if isinstance(years, int) else years
    if cube_of(spec) is not None:                 # a SIDRA or series field is its cube, read from the fact store
        return _field_from_cube(name, spec, wanted, settings)
    plan = intake_cube(name, spec)
    if plan is not None:                          # an intake count or sum is its records cube (ADR-0217)
        return _field_from_records(name, spec, plan, wanted, settings)
    plan = cnes_cube(name, spec)
    if plan is not None:                          # a CNES supply field is its records cube over December's register
        return _field_from_cnes(name, spec, plan, wanted, settings)
    directory = Path(settings.lake_dir) / "fields" / name
    if not directory.exists():
        raise FileNotFoundError(f"field {name!r} is not in the lake; run `pegasus-data fields --name {name}`")
    dataset = ds.dataset(directory, format="parquet", partitioning="hive")
    wanted = [years] if isinstance(years, int) else years
    expression = ds.field("year").isin(wanted) if wanted else None
    return dataset.to_table(filter=expression)
