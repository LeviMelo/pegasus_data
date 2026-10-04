"""Context fields: IBGE's municipal statistics as a place × year layer.

A field is a property of a place and a year that is not a health event: GDP,
the weight of the public sector, agriculture. They are declared in
``curation/fields.yml`` by IBGE's own table and variable, read from IBGE's
aggregates API, and kept in ``<lake>/fields/<name>/`` one row per municipality
and year. Only totals are stored; a rate is computed at use over POPSVS.

IBGE's markers become a status: ``-`` is a true zero, while ``..`` (not
applicable), ``...`` (not available) and ``X`` (suppressed) are null with
their reason.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pyarrow as pa

API = "https://servicodados.ibge.gov.br/api/v3/agregados/{table}/periodos/{period}/variaveis/{variable}?localidades=N6[all]"
_MARKERS = {"-": ("0", "zero"), "..": (None, "not_applicable"), "...": (None, "not_available"),
            "X": (None, "suppressed")}

__all__ = ["build_fields", "declared_fields", "load_field"]


def declared_fields(root: Path | None = None) -> dict[str, dict[str, Any]]:
    from .config import curation_root
    from .ontology import _read_yaml

    base = root or curation_root()
    return dict((_read_yaml(base / "fields.yml") or {}).get("fields") or {})


def _years(text: str) -> list[int]:
    """``2002-2023`` (a span) or ``2010, 2022`` (census years)."""
    out: list[int] = []
    for part in str(text).split(","):
        lo, _, hi = part.strip().partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def _classification(spec: dict[str, Any]) -> str:
    """IBGE's ``classificacao`` parameter: ``59[1023]|2[6794]``; omitted ones are its Total."""
    chosen = spec.get("classification") or {}
    return "|".join(f"{k}[{v}]" for k, v in chosen.items())


def _fetch(table: int, variable: int, year: int, classification: str = "",
           timeout: float = 180.0) -> list[dict[str, Any]]:
    url = API.format(table=table, period=year, variable=variable)
    if classification:
        url += f"&classificacao={classification}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read()
    if body[:2] == bytes((0x1F, 0x8B)):
        # IBGE sends gzip without Content-Encoding, as its meshes endpoint does
        # (DATA_SOURCES §6.3).
        import gzip

        body = gzip.decompress(body)
    data = json.loads(body.decode("utf-8"))
    if not data:
        return []
    return data[0]["resultados"][0]["series"]


def build_fields(settings: Any, names: list[str] | None = None, years: list[int] | None = None) -> dict[str, Any]:
    """Read each declared field from IBGE and write it to ``<lake>/fields/<name>/``."""
    import pyarrow.parquet as pq

    report: dict[str, Any] = {}
    for name, spec in declared_fields().items():
        if names and name not in names:
            continue
        if spec.get("source") == "inmet":
            report[name] = _build_climate(settings, name, years)
            continue
        if spec.get("source") == "s2id":
            report[name] = _build_disasters(settings, name, years)
            continue
        if spec.get("source") == "ans":
            report[name] = _build_ans(settings, name, spec, years)
            continue
        if spec.get("source") == "inep":
            report[name] = _build_inep(settings, name, spec, years)
            continue
        wanted = [y for y in _years(spec["years"]) if not years or y in years]
        written = 0
        statuses: dict[str, int] = {}
        for year in wanted:
            chosen = _classification(spec)
            series = _fetch(int(spec["table"]), int(spec["variable"]), year, chosen)
            code7, values, status = [], [], []
            for item in series:
                raw = str(item["serie"].get(str(year), "")).strip()
                value, state = _MARKERS.get(raw, (raw, "value"))
                code7.append(item["localidade"]["id"])
                values.append(float(value) if value else None)
                status.append(state)
                statuses[state] = statuses.get(state, 0) + 1
            if not code7:
                continue
            table = pa.table({
                "municipality": pa.array([c[:6] for c in code7], pa.string()),
                "municipality7": pa.array(code7, pa.string()),
                "value": pa.array(values, pa.float64()),
                "status": pa.array(status, pa.string()),
                "unit": pa.array([str(spec["unit"])] * len(code7), pa.string()),
                "source": pa.array([f"IBGE agregados {spec['table']} v{spec['variable']}"
                                    + (f" c{chosen}" if chosen else "")] * len(code7), pa.string()),
            })
            target = Path(settings.lake_dir) / "fields" / name / f"year={year}"
            target.mkdir(parents=True, exist_ok=True)
            pq.write_table(table, target / "part.parquet", compression="zstd")
            written += table.num_rows
        report[name] = {"years": len(wanted), "rows": written, "statuses": statuses}
    return report


def _build_ans(settings: Any, name: str, spec: dict[str, Any], years: list[int] | None) -> dict[str, Any]:
    """ANS beneficiaries of each year's December file (``sources.ans``)."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from .sources.ans import beneficiaries

    cache = Path(settings.root) / "registries" / "ans"
    written: dict[str, Any] = {}
    for year in [y for y in _years(spec["years"]) if not years or y in years]:
        table = beneficiaries(year, 12, cache)
        n = table.num_rows
        table = table.rename_columns(["municipality", "sex", "age_band", "coverage", "value", "file_uf"])
        table = table.append_column("year", pa.array([year] * n, pa.int32()))
        table = table.append_column("month", pa.array([12] * n, pa.int32()))
        table = table.append_column("unit", pa.array([str(spec["unit"])] * n, pa.string()))
        table = table.append_column("source", pa.array([f"ANS PDA-024 {year}-12"] * n, pa.string()))
        target = Path(settings.lake_dir) / "fields" / name / f"year={year}"
        target.mkdir(parents=True, exist_ok=True)
        pq.write_table(table.drop_columns(["year"]), target / "part.parquet", compression="zstd")
        medical = table.filter(pc.equal(table.column("coverage"), "Médico-hospitalar"))
        written[str(year)] = {"rows": n, "medical_hospital": pc.sum(medical.column("value")).as_py()}
    return written


def _build_inep(settings: Any, name: str, spec: dict[str, Any], years: list[int] | None) -> dict[str, Any]:
    """INEP school-census enrolment margins per municipality (``sources.inep``)."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from .sources.inep import enrolments

    cache = Path(settings.root) / "registries" / "inep"
    written: dict[str, Any] = {}
    for year in [y for y in _years(spec["years"]) if not years or y in years]:
        table = enrolments(year, cache)
        n = table.num_rows
        table = table.append_column("municipality", pc.utf8_slice_codeunits(table.column("municipality7"), 0, 6))
        table = table.append_column("unit", pa.array([str(spec["unit"])] * n, pa.string()))
        table = table.append_column("source", pa.array([f"INEP microdados_ed_basica_{year}"] * n, pa.string()))
        target = Path(settings.lake_dir) / "fields" / name / f"year={year}"
        target.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, target / "part.parquet", compression="zstd")
        total = table.filter(pc.equal(table.column("margin"), "total"))
        written[str(year)] = {"rows": n, "enrolments": pc.sum(total.column("value")).as_py()}
    return written


def _build_climate(settings: Any, name: str, years: list[int] | None) -> dict[str, Any]:
    """Station-month climate placed in the municipality each station stands in (``sources.inmet``)."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from .sources.inmet import monthly, stations

    cache = Path(settings.root) / "registries" / "inmet"
    placed = {s["station_id"]: s for s in stations(cache) if s["municipality7"]}
    table = monthly(cache, years)
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
        target = Path(settings.lake_dir) / "fields" / name / f"year={year}"
        target.mkdir(parents=True, exist_ok=True)
        pq.write_table(part, target / "part.parquet", compression="zstd")
        written += part.num_rows
    return {"rows": written, "stations_placed": len(placed), "station_months_unplaced": unplaced}


def _build_disasters(settings: Any, name: str, years: list[int] | None) -> dict[str, Any]:
    """S2iD's recorded disasters, one row per municipal event (``sources.s2id``)."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from .sources.s2id import events

    table = events(Path(settings.root) / "registries" / "s2id")
    undated = int(pc.sum(pc.is_null(table.column("year"))).as_py() or 0)
    table = table.filter(pc.is_valid(table.column("year")))
    written = 0
    for year in sorted(set(table.column("year").to_pylist())):
        if years and year not in years:
            continue
        part = table.filter(pc.equal(table.column("year"), year)).drop_columns(["year"])
        target = Path(settings.lake_dir) / "fields" / name / f"year={int(year)}"
        target.mkdir(parents=True, exist_ok=True)
        pq.write_table(part, target / "part.parquet", compression="zstd")
        written += part.num_rows
    return {"rows": written, "undated": undated}


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
