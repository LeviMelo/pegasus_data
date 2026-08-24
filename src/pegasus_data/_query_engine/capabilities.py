"""Compiled and local publication/query capability resolution."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from .model import Geography


@dataclass(frozen=True, slots=True)
class _Capabilities:
    resolution: str
    physical_uf: bool
    source_strategy: str
    lake_years: tuple[int, ...]
    fetch_years: tuple[int, ...]
    year_resolutions: tuple[tuple[int, str], ...]


def compile_capability_payload() -> dict[str, Any]:
    """Compile source-publication metadata from maintainer curation."""
    from ..ontology import CURATION, _read_yaml

    datasets: dict[str, dict[str, Any]] = {}
    for path in sorted((CURATION / "datasets").glob("*.yml")):
        for body in (_read_yaml(path).get("datasets") or {}).values():
            publication = body.get("source_publication") or {}
            code = str(publication.get("dataset") or "")
            if not code:
                continue
            compiled = {
                "observed_systems": list(publication.get("observed_systems") or ()),
                "observed_series": list(publication.get("observed_series") or ()),
                "publication_resolution": str(
                    publication.get("temporal_resolution") or "unknown"
                ),
            }
            if publication.get("physical_geography"):
                compiled["physical_geography"] = str(
                    publication["physical_geography"]
                )
            if code in datasets:
                raise ValueError(
                    f"duplicate source-publication capability declaration for {code} "
                    f"(encountered again in {path.name})"
                )
            datasets[code] = compiled
    return {"schema_version": 2, "datasets": datasets}


def _compiled_capability(
    settings: Settings, system: str, series: str | None
) -> dict[str, Any] | None:
    """Return a shipped, reviewed capability declaration; never infer semantics."""
    from .._resources import ResourceManager

    resource = ResourceManager(settings).ensure("query_capabilities")
    payload = json.loads(Path(resource.path).read_text(encoding="utf-8"))
    for body in payload.get("datasets", {}).values():
        systems = {str(value).upper() for value in body.get("observed_systems", ())}
        series_names = {str(value).upper() for value in body.get("observed_series", ())}
        if system.upper() in systems and (series is None or series.upper() in series_names):
            return body
    return None


def _publication_rows(store: Any, family_ids: Sequence[str]) -> list[dict[str, Any]]:
    if not family_ids:
        return []
    marks = ",".join("?" for _ in family_ids)
    return [
        dict(row)
        for row in store.query(
            f"SELECT ff.family_id, ff.path, ff.member, fa.geo_code, fa.year, "
            f"fa.normalized_date, fa.logical_id, fa.container_format, files.size, "
            f"families.schema_signature "
            f"FROM family_files ff LEFT JOIN file_facts fa ON fa.path=ff.path "
            f"LEFT JOIN files ON files.path=ff.path "
            f"JOIN families ON families.family_id=ff.family_id "
            f"WHERE ff.family_id IN ({marks})",
            tuple(family_ids),
        )
    ]


def _covered_sources(
    store: Any, family_ids: Sequence[str], year: int, uf: str | None
) -> set[tuple[str, str]]:
    if not family_ids:
        return set()
    marks = ",".join("?" for _ in family_ids)
    params: list[Any] = [*family_ids, year]
    clause = f"family_id IN ({marks}) AND year=?"
    if uf:
        clause += " AND uf=?"
        params.append(uf)
    paths: set[tuple[str, str]] = set()
    for row in store.query(
        f"SELECT family_id, source_paths FROM lake_partitions WHERE {clause}", params
    ):
        try:
            paths.update(
                (str(row["family_id"]), str(value))
                for value in json.loads(row["source_paths"] or "[]")
            )
        except (TypeError, json.JSONDecodeError):
            continue
    return paths


def _publication_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("family_id") or ""),
        str(row.get("logical_id") or row.get("path") or ""),
        str(row.get("member") or ""),
    )


def _source_identities(
    publications: Sequence[dict[str, Any]], covered: set[tuple[str, str]]
) -> set[tuple[str, str, str]]:
    """Resolve lake provenance to family/logical/member source units.

    Legacy path-only provenance can prove a loose source but deliberately cannot
    prove which members of a multi-member archive contributed.
    """
    from ..decode.base import logical_source_id

    identities: set[tuple[str, str, str]] = set()
    for row in publications:
        family = str(row.get("family_id") or "")
        path = str(row.get("path") or "")
        member = str(row.get("member") or "")
        source_id = logical_source_id(path, member)
        if (family, source_id) in covered or (
            not member and (family, path) in covered
        ):
            identities.add(_publication_identity(row))
    return identities


def _capabilities(
    settings: Settings,
    system: str,
    series: str | None,
    *,
    years: Sequence[int],
    geography: Geography | None,
) -> _Capabilities:
    """Resolve source-publication capabilities and exact local coverage."""
    from ..retrieve import _families

    declaration = _compiled_capability(settings, system, series)
    declared_physical_uf = bool((declaration or {}).get("physical_geography") == "uf")
    if not settings.catalog_path.is_file():
        from importlib.resources import files

        import pyarrow.dataset as ds

        default_resolution = str((declaration or {}).get("publication_resolution") or "unknown")
        resource_root = files("pegasus_data.resources")
        observed_systems = list((declaration or {}).get("observed_systems") or [system])
        observed_series = list((declaration or {}).get("observed_series") or ([series] if series else []))
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
            overall, declared_physical_uf, "fetch", (), requested_years,
            resolutions,
        )

    from ..catalog.store import Catalog
    from ..representations import choose_representations

    store = Catalog(settings.catalog_path, read_only=True)
    try:
        families = _families(store, system, series)
        ids = [str(item["family_id"]) for item in families]
        publications = _publication_rows(store, ids)
        requested_years = tuple(years) or tuple(
            sorted({int(row["year"]) for row in publications if row.get("year")})
        )
        relevant = [row for row in publications if not requested_years or row.get("year") in requested_years]
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
                expected = {_publication_identity(row) for row in selected}
                covered = _covered_sources(
                    store, ids, year,
                    geography.uf if physical_uf and geography and geography.uf else None,
                )
                complete = expected <= _source_identities(publications, covered)
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
            overall, physical_uf, strategy,
            tuple(lake_years), tuple(fetch_years), tuple(resolutions),
        )
    finally:
        store.close()
