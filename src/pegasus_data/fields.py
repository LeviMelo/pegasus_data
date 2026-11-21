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

from pathlib import Path
from typing import Any, cast

import pyarrow as pa

from .persist.kept import write_parquet_atomic
from .semantics.epoch import curated

__all__ = ["build_fields", "declared_fields", "field_rate", "load_field", "shared_labels", "unlabelled_fields"]


@curated(rooted=True)
def declared_fields(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """The declared fields (``fields.yml`` and the intake sources'), once per curation epoch. Shared: not to be edited."""
    from .config import curation_root
    from .semantics.curation import read_yaml
    from .semantics.intake_declarations import intake_fields

    base = root or curation_root()
    return {**dict((read_yaml(base / "fields.yml", missing_ok=True) or {}).get("fields") or {}), **intake_fields(base)}


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
    """Make each declared field readable by `load_field`: fetch or land what its cube or view reads (ADR-0217). Only the
    climate bases (raw observations) are written under ``<lake>/fields/``; every other field is served, never copied."""
    report: dict[str, Any] = {}
    sidra = None
    declared = declared_fields()
    # every CNES field is a records cube over the register the one reader serves (ADR-0217), cached by its fingerprint
    for name in [n for n, sp in declared.items() if sp.get("source") == "cnes" and (not names or n in names)]:
        if cnes_cube(name, declared[name]) is None:
            raise ValueError(f"{name}: a CNES field of no family the cube knows ({declared[name].get('family')!r})")
        table = load_field(name, years=years, settings=settings)
        report[name] = {"rows": table.num_rows, "cube": True}
    if "climate" in declared and (not names or "climate" in names):
        report.update(_build_climate(settings, years))
    chosen_brdwgd = {n: sp for n, sp in declared.items() if sp.get("source") == "brdwgd" and (not names or n in names)}
    if chosen_brdwgd:
        report.update(_build_climate_brdwgd(settings, chosen_brdwgd, years))
    chosen_intake: dict[str, list[str]] = {}
    from .semantics.intake_declarations import declared_sources

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
    `by`, over a landed dataset placed by a municipality's code or name, with place and time bindings (curated, read
    from its roles, or the place and period it was landed by). Shares (`outcome`), unpivoted margins and row registers are not yet cubes; neither is a field whose dataset
    holds no landed records, whose stored copy is then the only form of its data (ANS's beneficiaries)."""
    from .semantics.curation import semantics_for
    from .semantics.intake_declarations import declared_sources
    from .semantics.intake_declarations import strata as _strata

    if spec.get("source") != "intake":
        return None
    source = declared_sources().get(str(spec.get("intake")))
    if not source:
        return None
    fs = (source.get("fields") or {}).get(name)
    if not fs or fs.get("unpivot") or fs.get("rows"):
        return None
    place = source.get("place") or {}
    if place.get("type") not in ("municipality", "municipality_name") and place.get("states") is None:
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
    # the intake lands every column upper-cased: a declaration's names are read as landed (PNI's st_documento)
    where = {"+".join(part.upper() for part in str(k).split("+")): v for k, v in (fs.get("where") or {}).items()}
    support = None
    if fs.get("outcome"):
        # a share's numerator: its population's records with the outcome, a row (0 where none) wherever the population has one
        if fs.get("by"):
            return None
        support = {"source": cube_source, "where": dict(where)}
        where = {**where, **{str(k).upper(): v for k, v in fs["outcome"].items()}}
    return {"source": cube_source, "dataset": dataset, "support": support,
            "where": where, "strata": [(c.upper() if c else c, alias) for c, alias in _strata(fs)],
            "measure": str(measure).upper() if measure else None,
            "grain": (source.get("period") or {}).get("grain") or "year",
            # a source placed by a state's code is read at state level, its field keyed by that code as filed
            "states": ({"as": str(place.get("as") or place["column"]).lower(), "prefix": str(place["states"])}
                       if place.get("states") is not None else None),
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
    municipality7, status, unit, source, year), as the removed `intake._derive` wrote them (evaluation 2026-11-09-the-cube-stage-1).
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
                     measure=plan["measure"], support=plan.get("support"), settings=settings,
                     place="uf" if plan.get("states") else "municipality")
    else:
        table = pa.table({"place": pa.array([], pa.int64()), "period": pa.array([], pa.string()),
                          **{c: pa.array([], pa.string()) for c in columns}, "value": pa.array([], pa.float64())})
    code7 = pc.cast(table.column("place"), pa.string())
    period = table.column("period")
    n = table.num_rows
    states = plan.get("states")
    if states:
        from .config import UF_NUMERIC

        out: dict[str, Any] = {states["as"]: pa.array([f"{states['prefix']}{UF_NUMERIC.get(str(c), '')}"
                                                        for c in code7.to_pylist()], pa.string())}
    else:
        out = {"municipality": pc.utf8_slice_codeunits(code7, 0, 6)}
    if plan["grain"] == "month":
        # a period kept at its year (its month not recorded) has no month, as the field had it
        month = pc.utf8_slice_codeunits(period, 5, 7)
        out["month"] = pc.cast(pc.if_else(pc.equal(month, ""), pa.scalar(None, pa.string()), month), pa.int32())
    for column, alias in plan["strata"]:
        out[alias] = pc.cast(table.column(column), pa.string())
    out.update({
        "value": pc.cast(table.column("value"), pa.float64()),
        **({} if states else {"municipality7": code7}),
        "status": pa.array(["ok"] * n, pa.string()),
        "unit": pa.array([str(spec.get("unit") or "")] * n, pa.string()),
        "source": pa.array([plan["citation"]] * n, pa.string()),
        "year": pc.cast(pc.utf8_slice_codeunits(period, 0, 4), pa.int32()),
    })
    return pa.table(out)


def rows_view(name: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    """A field that is a register of records (``rows:`` in its intake declaration: the field's column -> the record's), as
    a view of the landed records, or None while the source has none landed."""
    from .semantics.intake_declarations import declared_sources

    if spec.get("source") != "intake":
        return None
    source = declared_sources().get(str(spec.get("intake")))
    if not source:
        return None
    fs = (source.get("fields") or {}).get(name)
    if not fs or not fs.get("rows") or not _landed(source):
        return None
    return {"dataset": f"{source['system']}-{source['series']}", "rows": dict(fs["rows"]), "where": dict(fs.get("where") or {})}


def _field_from_rows(register: dict[str, Any], years: list[int] | None, settings: Any) -> pa.Table:
    """A register field read from its records (`query`), each record column under the field's name, with its year."""
    import pyarrow.compute as pc

    from ._query_engine import query

    columns = list(dict.fromkeys([*register["rows"].values(), "year"]))
    period = [str(y) for y in years] if years else None
    table = cast("pa.Table", query(register["dataset"], period=period, geography="BR", select=columns, present="codes",
                  rows={k.upper(): [str(v) for v in vs] for k, vs in register["where"].items()} or None, settings=settings))
    named = {c.upper(): c for c in table.column_names}
    out = {alias: table.column(named[str(col).upper()]) for alias, col in register["rows"].items()}
    out["year"] = pc.cast(table.column(named["YEAR"]), pa.int32())
    return pa.table(out)


def margins_view(name: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    """A field whose margins the source publishes as columns (``unpivot:`` in its intake declaration: a column -> its
    margin and category; INEP's enrolments by sex, race and age band, each summing to the total), as one records cube
    per column over the landed records, or None while the source has none landed."""
    from .semantics.intake_declarations import declared_sources

    if spec.get("source") != "intake":
        return None
    source = declared_sources().get(str(spec.get("intake")))
    if not source:
        return None
    fs = (source.get("fields") or {}).get(name)
    if not fs or not fs.get("unpivot") or not _landed(source):
        return None
    unpivot = fs["unpivot"]
    return {"dataset": f"{source['system']}-{source['series']}", "as": list(unpivot["as"]),
            "columns": {str(c).upper(): list(v) for c, v in unpivot["columns"].items()},
            "citation": str(source.get("citation") or source.get("what") or "")}


def _field_from_margins(name: str, spec: dict[str, Any], margins: dict[str, Any], years: list[int] | None,
                        settings: Any) -> pa.Table:
    """The margins field from its cubes: per column, the municipality sums of that column, keyed by the column's margin
    and category, in the field's columns."""
    import pyarrow.compute as pc

    from .cubes import cube

    declared = _years(spec["years"])
    periods = [y for y in (years or declared) if y in declared]
    first, second = margins["as"]
    parts = []
    for column, (margin, category) in margins["columns"].items():
        table = cube(f"records:{margins['dataset']}/rows", measure=column, periods=periods, grain="year",
                     settings=settings)
        code7 = pc.cast(table.column("place"), pa.string())
        n = table.num_rows
        year = pc.cast(table.column("period"), pa.int32())
        parts.append(pa.table({
            "municipality7": code7, first: pa.array([str(margin)] * n, pa.string()),
            second: pa.array([str(category)] * n, pa.string()), "value": pc.cast(table.column("value"), pa.float64()),
            "municipality": pc.utf8_slice_codeunits(code7, 0, 6),
            "unit": pa.array([str(spec.get("unit") or "")] * n, pa.string()),
            "source": pa.array([margins["citation"]] * n, pa.string()),
            "year": year}))
    return pa.concat_tables(parts)


def _field_from_climate(name: str, spec: dict[str, Any], years: list[int] | None, settings: Any) -> pa.Table:
    """A BR-DWGD annual field from its cube (``climate:<measure>``), in the field's columns: ``ok`` when the year holds
    all twelve months, ``partial_year`` otherwise (the value kept), ``months`` what it rests on, ``source`` the release."""
    import pyarrow.compute as pc

    from .cubes import cube

    table = cube(f"climate:{spec['measure']}", periods=years, settings=settings)
    code7 = pc.cast(table.column("place"), pa.string())
    n = table.num_rows
    return pa.table({"municipality": pc.utf8_slice_codeunits(code7, 0, 6), "municipality7": code7,
                     "value": table.column("value"),
                     "status": pc.if_else(pc.equal(table.column("status"), "value"), "ok", "partial_year"),
                     "unit": pa.array([str(spec["unit"])] * n, pa.string()), "source": table.column("source"),
                     "months": table.column("months"), "year": pc.cast(table.column("period"), pa.int32())})


def cnes_groups() -> dict[str, Any]:
    """The ``cnes:`` block of ``curation/fields.yml``: which codes make each group a CNES field counts."""
    from .config import curation_root
    from .semantics.curation import read_yaml

    return dict((read_yaml(curation_root() / "fields.yml", missing_ok=True) or {}).get("cnes") or {})


def cnes_cube(name: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    """The records cube a CNES supply field is: a December's register read by the one reader (its files adopted from
    the mirror, `adopt.adopt_copies`), the field's groups as code lists on the register's own columns, its stock counted
    (establishments and teams as distinct codes) or summed (beds, equipment). The support is December's ST register: a
    municipality with no establishment in it has no value (``no_cnes_record``), one with establishments and none of the
    field's is a true 0. A field of professionals counts PF's rows (jobs), its distinct CNS_PROF (persons) or sums its three
    weekly hours columns, for the occupations whose CBO has one of the group's prefixes."""
    if spec.get("source") != "cnes":
        return None
    g = cnes_groups()
    recipe = (g.get("families") or {}).get(spec["family"])
    if recipe is None:
        return None
    where: dict[str, Any] = {}
    group = recipe.get("group")
    if group:
        chosen = spec.get(group["select"])
        lists = group["groups"]
        if isinstance(lists, dict):                 # a group named by the field, each its own list (beds' ICU kinds)
            codes = g[lists[chosen]] if chosen in lists else None
        elif group.get("other") and chosen == "other":   # everything the named groups do not list
            codes = {"not": [c for listed in g[lists].values() for c in listed]}
        else:
            codes = g[lists][chosen]
        if codes is not None:
            where[group["column"]] = codes if isinstance(codes, dict) else (
                {"prefix": list(codes)} if group.get("prefix") else list(codes))
        elif not group.get("optional"):
            raise KeyError(f"{name}: no group {chosen!r} in {group['groups']}")
    sector = recipe.get("sector")
    if sector:
        chosen = spec.get("sector")
        if sector.get("only_measure"):
            if spec.get("measure") == sector["only_measure"]:
                where[sector["column"]] = list(sector["sus"])
        elif chosen == "sus":
            where[sector["column"]] = list(sector["sus"])
        elif chosen == "nonsus":
            where[sector["column"]] = {"not": list(sector["sus"])}
    for column, listed in (recipe.get("fixed") or {}).items():
        where[column] = list(g[listed])
    measure = recipe["measure"]
    if isinstance(measure, dict):
        measure = measure[spec[recipe["measure_by"]]]
    dataset = recipe["dataset"]
    return {"source": f"records:{dataset}/rows", "dataset": dataset, "where": where, "measure": measure,
            "support": f"records:{g.get('support', 'CNES-ST')}/rows", "month": int(g["register_month"])}


def _field_from_cnes(name: str, spec: dict[str, Any], plan: dict[str, Any], years: list[int] | None,
                     settings: Any) -> pa.Table:
    """A CNES field from its cube, in the field's columns, one row per IBGE municipality and year: the value inside the
    register's support (``ok``), else a null (``no_cnes_record``), the statuses its stored copies carried."""
    from .cubes import cube
    from .geography import municipalities

    declared = _years(spec["years"])
    wanted = [y for y in (years or declared) if y in declared]
    universe = municipalities()
    keys = sorted(universe)
    columns: dict[str, list[Any]] = {k: [] for k in ("municipality", "municipality7", "value", "status", "unit", "source", "year")}
    for year in wanted:
        table = cube(plan["source"], periods=[f"{year}-{plan['month']:02d}"], grain="month", where=plan["where"], measure=plan["measure"],
                     support=plan["support"], settings=settings)
        found = {str(r["place"]): r["value"] for r in table.select(["place", "value"]).to_pylist()}
        label = f"{plan['dataset']} {year}-{plan['month']:02d}"
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


def field_rate(name: str, *, per: float = 1000.0, years: list[int] | int | None = None, settings: Any = None) -> pa.Table:
    """A sum field over the resident population: (municipality, year, numerator, population, rate per ``per``).

    The population is the municipal total of the population account (its current version, reference date 1 August),
    summed over sex and age (`cube("modelled:population_account/population")`, all races together); a ratio of sums,
    so any group of municipalities lifts it by summing numerator and population. A municipality the account does not
    hold in a year has no rate, never a share of another's.
    """
    import pyarrow.compute as pc

    from .config import load_settings
    from .cubes import cube

    settings = settings or load_settings()
    field = load_field(name, years=years, settings=settings).filter(pc.field("status") == "ok")
    wanted = sorted(set(field.column("year").to_pylist()))
    total = cube("modelled:population_account/population", place="municipality", periods=wanted,
                 where={"race": ["total"]}, settings=settings)
    from .geography import place_six

    population: dict[tuple[str | None, int], Any] = {(str(p)[:6], int(y)): v for p, y, v in zip(total.column("place").to_pylist(),
                                                              total.column("period").to_pylist(),
                                                              total.column("value").to_pylist(), strict=True)}
    municipality = field.column("municipality").to_pylist()
    distinct = sorted({m for m in municipality if m is not None})
    placed = dict(zip(distinct, place_six(distinct), strict=True))
    year = [int(y) for y in field.column("year").to_pylist()]
    numerator = field.column("value").to_pylist()
    denominator = [population.get((placed.get(m), y)) for m, y in zip(municipality, year, strict=True)]
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

    cache = settings.registry_dir("inmet")
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
    """BR-DWGD's municipal zonal statistics (``sources.brdwgd``, ADR-0178): the base ``climate_monthly`` is written, and
    each field with a ``measure`` is a view of its cube over it (``climate:<measure>``, `_field_from_climate`): a sum with
    its denominator declared in ``over`` (the mean is the ratio, formed at use), ``ok`` when all twelve months are held
    and ``partial_year`` otherwise. A municipality the release does not hold has no row, and is named in the report.
    """
    import pyarrow.compute as pc

    from .geography import municipalities
    from .sources import brdwgd

    months, release = brdwgd.municipality_months(settings.registry_dir("brdwgd"))
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
    # the annual sums are views of their climate cube over that base (ADR-0217), not copies
    for name in (n for n, spec in specs.items() if spec.get("measure")):
        table = load_field(name, years=years, settings=settings)
        report[name] = {"rows": table.num_rows, "cube": True,
                        "ok": int(pc.sum(pc.equal(table.column("status"), "ok")).as_py() or 0),
                        "partial_year": int(pc.sum(pc.equal(table.column("status"), "partial_year")).as_py() or 0)}
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
    if spec.get("source") == "brdwgd" and spec.get("measure"):   # an annual climate sum is its climate cube
        return _field_from_climate(name, spec, wanted, settings)
    register = rows_view(name, spec)
    if register is not None:                      # a register (S2iD's events) is its landed records, renamed
        return _field_from_rows(register, wanted, settings)
    margins = margins_view(name, spec)
    if margins is not None:                       # margins published as columns (INEP's) are one cube per column
        return _field_from_margins(name, spec, margins, wanted, settings)
    directory = Path(settings.lake_dir) / "fields" / name
    if not directory.exists():
        raise FileNotFoundError(f"field {name!r} is not in the lake; run `pegasus-data fields --name {name}`")
    dataset = ds.dataset(directory, format="parquet", partitioning="hive")
    wanted = [years] if isinstance(years, int) else years
    expression = ds.field("year").isin(wanted) if wanted else None
    return dataset.to_table(filter=expression)
