"""Compiled and local publication/query capability resolution."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from .model import Geography


@dataclass(frozen=True, slots=True)
class _Axis:
    name: str
    fields: tuple[str, ...]
    encoding: str
    code_system: str | None = None


@dataclass(frozen=True, slots=True)
class _Capabilities:
    resolution: str
    physical_uf: bool
    source_strategy: str
    row_geography: str | None
    row_time: str | None
    lake_years: tuple[int, ...]
    fetch_years: tuple[int, ...]
    year_resolutions: tuple[tuple[int, str], ...]
    time_axis: str | None
    geography_axis: str | None


def _compiled_capability(system: str, series: str | None) -> dict[str, Any] | None:
    """Return a shipped, reviewed capability declaration; never infer semantics."""
    from importlib.resources import files

    resource = files("pegasus_data.resources").joinpath("query_capabilities.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    for body in payload.get("datasets", {}).values():
        systems = {str(value).upper() for value in body.get("observed_systems", ())}
        series_names = {str(value).upper() for value in body.get("observed_series", ())}
        if system.upper() in systems and (series is None or series.upper() in series_names):
            return body
    return None


def _axis(body: dict[str, Any] | None, kind: str, requested: str | None) -> _Axis | None:
    if not body:
        return None
    name = requested or body.get(f"default_{kind}")
    declaration = (body.get(kind) or {}).get(name)
    if not declaration:
        choices = ", ".join(sorted((body.get(kind) or {}).keys())) or "none"
        raise ValueError(f"unknown {kind}_by={name!r}; declared choices: {choices}")
    return _Axis(
        str(name),
        tuple(str(value).upper() for value in declaration.get("fields", ())),
        str(declaration.get("encoding") or "code"),
        declaration.get("code_system"),
    )


def _publication_rows(store: Any, family_ids: Sequence[str]) -> list[dict[str, Any]]:
    if not family_ids:
        return []
    marks = ",".join("?" for _ in family_ids)
    return [
        dict(row)
        for row in store.query(
            f"SELECT ff.family_id, ff.path, ff.member, fa.geo_code, fa.year, "
            f"fa.normalized_date, fa.logical_id, fa.container_format, files.size "
            f"FROM family_files ff LEFT JOIN file_facts fa ON fa.path=ff.path "
            f"LEFT JOIN files ON files.path=ff.path WHERE ff.family_id IN ({marks})",
            tuple(family_ids),
        )
    ]


def _covered_sources(store: Any, family_ids: Sequence[str], year: int, uf: str | None) -> set[str]:
    if not family_ids:
        return set()
    marks = ",".join("?" for _ in family_ids)
    params: list[Any] = [*family_ids, year]
    clause = f"family_id IN ({marks}) AND year=?"
    if uf:
        clause += " AND uf=?"
        params.append(uf)
    paths: set[str] = set()
    for row in store.query(f"SELECT source_paths FROM lake_partitions WHERE {clause}", params):
        try:
            paths.update(str(value) for value in json.loads(row["source_paths"] or "[]"))
        except (TypeError, json.JSONDecodeError):
            continue
    return paths


def _source_identities(store: Any, paths: set[str]) -> set[str]:
    """Resolve physical source paths back to representation-independent identities."""
    if not paths:
        return set()
    marks = ",".join("?" for _ in paths)
    identities: set[str] = set()
    known: set[str] = set()
    for row in store.query(
        f"SELECT path, logical_id FROM file_facts WHERE path IN ({marks})",
        tuple(sorted(paths)),
    ):
        known.add(str(row["path"]))
        identities.add(str(row["logical_id"] or row["path"]))
    identities.update(paths - known)
    return identities


def _capabilities(
    settings: Settings,
    system: str,
    series: str | None,
    *,
    years: Sequence[int],
    geography: Geography | None,
    time_by: str | None,
    geography_by: str | None,
) -> _Capabilities:
    """Compile declared axes with publication-by-publication local coverage."""
    from ..retrieve import _families

    declaration = _compiled_capability(system, series)
    time_axis = _axis(declaration, "time", time_by)
    geography_axis = _axis(declaration, "geography", geography_by)
    declared_physical_uf = bool((declaration or {}).get("physical_geography") == "uf")
    if not settings.catalog_path.is_file():
        from importlib.resources import files

        import pyarrow.dataset as ds

        default_resolution = str((declaration or {}).get("publication_resolution") or "unknown")
        resource_root = files("pegasus_data.resources")
        observed_systems = list((declaration or {}).get("observed_systems") or [system])
        observed_series = list((declaration or {}).get("observed_series") or ([series] if series else []))
        family_filter = ds.field("system").isin(observed_systems)
        if observed_series:
            family_filter &= ds.field("series").isin(observed_series)
        family_table = ds.dataset(
            str(resource_root.joinpath("families.parquet")), format="parquet"
        ).to_table(columns=["signature", "time_min", "time_max"], filter=family_filter)
        signatures = {
            str(signature)
            for signature, lo, hi in zip(
                family_table["signature"].to_pylist(),
                family_table["time_min"].to_pylist(),
                family_table["time_max"].to_pylist(),
                strict=True,
            )
            if not years or any(
                (lo is None or int(lo) <= year) and (hi is None or year <= int(hi))
                for year in years
            )
        }
        fields_by_signature: dict[str, set[str]] = {str(value): set() for value in signatures}
        if signatures:
            presence = ds.dataset(
                str(resource_root.joinpath("schema_presence.parquet")), format="parquet"
            ).to_table(
                columns=["signature", "field"],
                filter=ds.field("signature").isin(sorted(signatures)),
            )
            for signature, field_name in zip(
                presence["signature"].to_pylist(), presence["field"].to_pylist(), strict=True
            ):
                fields_by_signature[str(signature)].add(str(field_name).upper())
        row_time = (
            "+".join(time_axis.fields)
            if time_axis and fields_by_signature and all(
                set(time_axis.fields) <= fields for fields in fields_by_signature.values()
            ) else None
        )
        row_geo = (
            "+".join(geography_axis.fields)
            if geography_axis and fields_by_signature and all(
                set(geography_axis.fields) <= fields for fields in fields_by_signature.values()
            ) else None
        )
        tree_filter = ds.field("system").isin(observed_systems)
        if observed_series:
            tree_filter &= ds.field("series").isin(observed_series)
        if years:
            tree_filter &= ds.field("year").isin(list(years))
        tree = ds.dataset(
            str(resource_root.joinpath("tree.parquet")), format="parquet"
        ).to_table(columns=["year", "yyyymm", "uf"], filter=tree_filter)
        by_year: dict[int, set[int]] = {}
        for year, yyyymm in zip(tree["year"].to_pylist(), tree["yyyymm"].to_pylist(), strict=True):
            if year is not None:
                by_year.setdefault(int(year), set()).add(int(yyyymm or 0) % 100)
        requested_years = tuple(years) or tuple(sorted(by_year))
        resolutions = tuple(
            (
                year,
                "mixed" if 0 in by_year.get(year, set()) and any(by_year.get(year, set()))
                else "month" if any(by_year.get(year, set()))
                else "year" if year in by_year else default_resolution,
            )
            for year in requested_years
        )
        unique = {value for _, value in resolutions}
        overall = next(iter(unique)) if len(unique) == 1 else "mixed"
        return _Capabilities(
            overall, declared_physical_uf, "fetch", row_geo,
            row_time, (), requested_years,
            resolutions,
            time_axis.name if time_axis else None, geography_axis.name if geography_axis else None,
        )

    from ..catalog.store import Catalog
    from ..representations import choose_representations

    store = Catalog(settings.catalog_path, read_only=True)
    try:
        families = _families(store, system, series)
        ids = [str(item["family_id"]) for item in families]
        fields_by_family: dict[str, set[str]] = {family_id: set() for family_id in ids}
        if ids:
            marks = ",".join("?" for _ in ids)
            for row in store.query(
                f"SELECT f.family_id, sp.field_name FROM families f JOIN schema_presence sp "
                f"ON sp.schema_signature=f.schema_signature WHERE f.family_id IN ({marks})",
                tuple(ids),
            ):
                fields_by_family[str(row["family_id"])].add(str(row["field_name"]).upper())
        row_time = (
            "+".join(time_axis.fields)
            if time_axis and fields_by_family and all(
                set(time_axis.fields) <= fields for fields in fields_by_family.values()
            )
            else None
        )
        if not ids:
            # An empty runtime catalog carries no contradictory schema evidence;
            # the shipped declaration remains the bootstrap capability.
            row_time = "+".join(time_axis.fields) if time_axis else None
            row_geo = "+".join(geography_axis.fields) if geography_axis else None
        row_geo = (
            "+".join(geography_axis.fields)
            if geography_axis and fields_by_family and all(
                set(geography_axis.fields) <= fields for fields in fields_by_family.values()
            )
            else None
        )
        publications = _publication_rows(store, ids)
        requested_years = tuple(years) or tuple(
            sorted({int(row["year"]) for row in publications if row.get("year")})
        )
        relevant = [row for row in publications if not requested_years or row.get("year") in requested_years]
        relevant_families = {
            str(row["family_id"]) for row in relevant if row.get("family_id")
        }
        if relevant_families and time_axis and not all(
            set(time_axis.fields) <= fields_by_family.get(family_id, set())
            for family_id in relevant_families
        ):
            row_time = None
        if relevant_families and geography_axis and not all(
            set(geography_axis.fields) <= fields_by_family.get(family_id, set())
            for family_id in relevant_families
        ):
            row_geo = None
        observed_geo = [str(row.get("geo_code") or "") for row in relevant]
        physical_uf = declared_physical_uf and (
            not observed_geo or all(value not in {"", "BR"} for value in observed_geo)
        )
        if physical_uf and geography and geography.uf:
            relevant = [row for row in relevant if str(row.get("geo_code") or "").upper() == geography.uf]

        lake_years: list[int] = []
        fetch_years: list[int] = []
        resolutions: list[tuple[int, str]] = []
        any_partition = bool(
            store.query(
                "SELECT 1 FROM lake_partitions WHERE family_id IN ("
                + (",".join("?" for _ in ids) or "NULL") + ") LIMIT 1",
                tuple(ids),
            )
        ) if ids else False
        for year in requested_years:
            candidates = [row for row in relevant if int(row.get("year") or 0) == year]
            selected = list(choose_representations(store, candidates).selected) if candidates else []
            month_marks = {int(row.get("normalized_date") or 0) % 100 for row in selected}
            resolution = (
                "mixed" if 0 in month_marks and any(month_marks) else
                "month" if any(month_marks) else
                "year" if selected else "unknown"
            )
            resolutions.append((year, resolution))
            partitions = store.query(
                "SELECT 1 FROM lake_partitions WHERE year=? AND family_id IN ("
                + (",".join("?" for _ in ids) or "NULL") + ") LIMIT 1",
                (year, *ids),
            ) if ids else []
            if selected:
                expected = {
                    str(row.get("logical_id") or row["path"]) for row in selected
                }
                covered = _covered_sources(
                    store, ids, year,
                    geography.uf if physical_uf and geography and geography.uf else None,
                )
                complete = expected <= _source_identities(store, covered)
            else:
                # An inventory-free fixture/catalog cannot prove an expected
                # publication is missing. A real inventory takes the strict path above.
                complete = bool(partitions) or (not publications and any_partition)
            (lake_years if complete else fetch_years).append(year)

        unique_resolutions = {value for _, value in resolutions if value != "unknown"}
        overall = next(iter(unique_resolutions)) if len(unique_resolutions) == 1 else (
            "mixed" if unique_resolutions else str((declaration or {}).get("publication_resolution") or "unknown")
        )
        strategy = "hybrid" if lake_years and fetch_years else "lake" if lake_years else "fetch"
        return _Capabilities(
            overall, physical_uf, strategy, row_geo, row_time,
            tuple(lake_years), tuple(fetch_years), tuple(resolutions),
            time_axis.name if time_axis else None, geography_axis.name if geography_axis else None,
        )
    finally:
        store.close()
