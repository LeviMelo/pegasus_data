"""Which years, states and resolutions each dataset is published at, and where."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..catalog.store import CatalogStore
from ..config import Settings
from ..persist.lake import Lake, LakePartition, listed_partitions, record_source
from .model import Geography, Period


@contextmanager
def shared_catalog(settings: Settings) -> Iterator[CatalogStore]:
    """The process's read-only connection to the catalog of ``settings`` (a fresh one starts from the shipped seed,
    ADR-0067), released on exit."""
    store = CatalogStore.shared(settings.catalog_path)
    try:
        yield store
    finally:
        store.close()


@dataclass(frozen=True, slots=True)
class _Coverage:
    resolution: str
    physical_uf: bool
    source_strategy: str
    lake_years: tuple[int, ...]
    fetch_years: tuple[int, ...]
    year_resolutions: tuple[tuple[int, str], ...]
    #: ``geography="BR"`` on a dataset published only per state: the states
    #: that stand for the nation. Empty when a national file exists (SIM's
    #: DOBR, SINASC's DNBR) or BR was not asked.
    national_ufs: tuple[str, ...] = ()
    #: No state asked of a dataset published nationally AND per state in some years: for each such year the one reading
    #: of it, ``("BR",)`` (the national file; the state files are the same records). Years not listed read every file.
    year_geography: tuple[tuple[int, tuple[str, ...]], ...] = ()
    #: Years the catalog calls lake-complete whose listed partition files are not on disk: read from the source instead.
    missing_lake_years: tuple[int, ...] = ()
    #: The files the ``lake_years`` are read from: the catalog's listed partitions, one reading of each year (the
    #: national file or the states', never both), every one on disk. What the plan hands to ``load``.
    lake_partitions: tuple[LakePartition, ...] = ()
    #: ``record source -> YYYYMM`` for the ``lake_partitions`` built from one publication of a month (`sole_competence`): the
    #: competence of records that do not store it.
    lake_competence: tuple[tuple[str, int], ...] = ()
    #: Lake years published by month, with the months asked that no publication is filed for: ``(year, (month, ...))``.
    unpublished: tuple[tuple[int, tuple[int, ...]], ...] = ()


#: A geography code that is not a state: a national file, or a publication with no state axis.
_NOT_A_STATE = frozenset({"", "BR", "NA"})


def national_or_states(items: Iterable[Any], geo_of: Callable[[Any], object]) -> list[Any]:
    """The items of ONE year that are a single reading of the dataset when no state was asked.

    DATASUS publishes SIM and SINASC both as a national file (``DOBR2019``) and as one file per state (``DOAC2019`` ..
    ``DOTO2019``): the same records twice. With no state asked every file was selected, and ``plan("SIM.DO",
    period=2019)`` planned 206 MiB (the national file is 103) and a query returned every death twice. The national
    file is the dataset's reading, as ``geography="BR"`` gives it; the state files are read only when the year has
    no national one. Items with no state axis (documentation rows, ``NA`` partitions) are always kept.
    """
    items = list(items)
    geos = [str(geo_of(item) or "").upper() for item in items]
    has_national = any(g == "BR" for g in geos)
    has_states = any(g not in _NOT_A_STATE for g in geos)
    if not (has_national and has_states):
        return items
    return [item for item, g in zip(items, geos, strict=True) if g in _NOT_A_STATE]


def one_reading(parts: Iterable[LakePartition]) -> list[LakePartition]:
    """The partitions one reading of each year opens when no state was asked (:func:`national_or_states`, per year)."""
    by_year: dict[int, list[LakePartition]] = {}
    for part in parts:
        by_year.setdefault(part.year, []).append(part)
    return [part for items in by_year.values() for part in national_or_states(items, lambda p: p.uf)]


def _filed(publications: Iterable[dict[str, Any]]) -> dict[tuple[str, str], int]:
    """``(family, source id) -> normalized_date`` of each publication: how a lake partition's ``sources`` are dated."""
    out: dict[tuple[str, str], int] = {}
    for row in publications:
        family, path, member = str(row.get("family_id") or ""), str(row.get("path") or ""), str(row.get("member") or "")
        out[(family, f"{path}!{member}" if member else path)] = int(row.get("normalized_date") or 0)
    return out


def in_months(
    parts: Iterable[LakePartition], publications: Iterable[dict[str, Any]], months: Sequence[int],
) -> list[LakePartition]:
    """The ``parts`` that can hold a record of the publications filed for ``months``; a part built only from
    publications of other months is not read.

    A publication is dated by its file (``file_facts.normalized_date``), and a lake partition says which publications it
    was built from (``sources``). An intake source (ADR-0162) lands one part file per monthly unit inside the year's
    partition, so a month's query opens that month's file and not the year's twelve; a DATASUS partition holds a year of
    months, lists them all as sources and stays whenever one of them is asked. A part is kept unless it has sources and
    every one of them is a publication of a known month outside ``months``: a source the catalog does not know, or an
    annual one (month 0), keeps it, so a doubt reads more, never fewer records. The records of a kept part are still
    filtered by their own competence when they carry it (`filters._filter_source_period`).
    """
    filed = _filed(publications)
    wanted = set(months)
    kept = []
    for part in parts:
        dates = [filed.get((part.family_id, source)) for source in part.sources]
        if dates and all(date is not None and date % 100 not in (0, *wanted) for date in dates):
            continue
        kept.append(part)
    return kept


def sole_competence(parts: Iterable[LakePartition], publications: Iterable[dict[str, Any]]) -> dict[str, int]:
    """``record source -> YYYYMM`` for the parts built from ONE publication of a month: every record of such a part has
    that publication's competence, whether or not the part stored it (an intake part does not, `filters._with_competence`).

    A part built from several publications (a DATASUS state-year) cannot say which a record came from and carries the
    competence itself. A source that two parts date differently (the records of one monthly file dated in another year are
    a publication of that year, at year resolution) is left out: its records have no competence, and a month's query
    refuses them rather than guess."""
    singles = [part for part in parts if len(part.sources) == 1]
    if not singles:
        return {}
    filed = _filed(publications)
    found: dict[str, int | None] = {}
    for part in singles:
        (source,) = part.sources
        date = filed.get((part.family_id, source), 0)
        key = record_source(source)
        found[key] = date if date % 100 and found.get(key, date) == date else None
    return {key: date for key, date in found.items() if date}


def compile_capability_payload() -> dict[str, Any]:
    """Compile source-publication metadata from maintainer curation."""
    from ..config import curation_root
    from ..semantics.curation import read_yaml

    datasets: dict[str, dict[str, Any]] = {}
    for path in sorted((curation_root() / "datasets").glob("*.yml")):
        for body in (read_yaml(path, missing_ok=True).get("datasets") or {}).values():
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


#: ``file states -> the parsed shipped declaration``: the resource is checked (`ResourceManager.ensure` hashes it) and
#: parsed once per state of the files it comes from, not once per query.
_CAPABILITY_PAYLOADS: dict[tuple, dict[str, Any]] = {}


def _stat(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _compiled_capability(
    settings: Settings, system: str, series: str | None
) -> dict[str, Any] | None:
    """Return a shipped, reviewed capability declaration; never infer semantics."""
    from .._resources import ResourceManager

    manager = ResourceManager(settings)
    key = (
        str(manager.local_dir),
        _stat(manager.local_dir / "publication_coverage.json"), _stat(manager.local_dir / "manifest.json"),
        _stat(manager.bundled_dir / "publication_coverage.json"), _stat(manager.bundled_dir / "manifest.json"),
    )
    payload = _CAPABILITY_PAYLOADS.get(key)
    if payload is None:
        resource = manager.ensure("publication_coverage")
        payload = json.loads(Path(resource.path).read_text(encoding="utf-8"))
        if len(_CAPABILITY_PAYLOADS) > 16:
            _CAPABILITY_PAYLOADS.clear()
        _CAPABILITY_PAYLOADS[key] = payload
    for body in payload.get("datasets", {}).values():
        systems = {str(value).upper() for value in body.get("observed_systems", ())}
        series_names = {str(value).upper() for value in body.get("observed_series", ())}
        if system.upper() in systems and (series is None or series.upper() in series_names):
            return body
    return None


def _publication_rows(
    store: CatalogStore, family_ids: Sequence[str], years: Sequence[int] = ()
) -> list[dict[str, Any]]:
    """The dataset's publications (one row per family member), of ``years`` when given, once per catalog state.

    A year's rows are all this planning needs of it: the query had no year in its WHERE and loaded every year's
    publications (18,991 rows for SIH-RD, 2.5 s for a national ten-year plan) to look at a few. They are kept by year,
    so a query for other years of the dataset reads only the years it has not seen, and a store holds a year's rows
    once however the queries group them.
    """
    if not family_ids:
        return []
    ids = tuple(family_ids)

    def read(wanted: Sequence[int]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            year_clause = f" AND fa.year IN ({','.join('?' for _ in wanted)})" if wanted else ""
            out.extend(
                dict(row)
                for row in store.query(
                    f"SELECT ff.family_id, ff.path, ff.member, fa.geo_code, fa.year, "
                    f"fa.normalized_date, fa.logical_id, fa.container_format, files.size, "
                    f"families.schema_signature "
                    f"FROM family_files ff LEFT JOIN file_facts fa ON fa.path=ff.path "
                    f"LEFT JOIN files ON files.path=ff.path "
                    f"JOIN families ON families.family_id=ff.family_id "
                    f"WHERE ff.family_id IN ({marks}){year_clause}",
                    (*chunk, *wanted),
                )
            )
        return out

    if not years:
        return [dict(row) for row in store.memo(("publications", ids), lambda: read(()))]
    wanted = sorted({int(y) for y in years})
    # the dict is part of the remembered value: it is dropped with it when the catalog changes, and filled year by year
    by_year: dict[int, list[dict[str, Any]]] = store.memo(("publications_by_year", ids), dict)
    with store._lock:
        missing = [y for y in wanted if y not in by_year]
        if missing:
            found = read(missing)
            for year in missing:
                by_year[year] = []
            for row in found:
                by_year.setdefault(int(row["year"]), []).append(row)
        return [dict(row) for y in wanted for row in by_year[y]]


def _publication_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("family_id") or ""),
        str(row.get("logical_id") or row.get("path") or ""),
        str(row.get("member") or ""),
    )


def _source_identities(
    selected: Sequence[dict[str, Any]], publications: Sequence[dict[str, Any]], covered: set[tuple[str, str]]
) -> set[tuple[str, str, str]]:
    """The ``selected`` publications (family/logical/member) the lake was built from.

    A publication counts when a file of it that is NOT another edition of the selected one is a source of a partition:
    the selected file itself, another format of the same records, a mirror. A partition built from an older edition
    (SIH-RD 2014-2016, republished corrected) shares the logical identity with the edition now selected and had been
    taken for it, so the corrected records were not served until a rebuild.

    Legacy path-only provenance can prove a loose source but deliberately cannot prove which members of a
    multi-member archive contributed.
    """
    from ..decode.base import logical_source_id
    from ..representations import other_edition

    def built(row: dict[str, Any]) -> bool:
        family = str(row.get("family_id") or "")
        path = str(row.get("path") or "")
        member = str(row.get("member") or "")
        return (family, logical_source_id(path, member)) in covered or (not member and (family, path) in covered)

    by_identity: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in publications:
        by_identity.setdefault(_publication_identity(row), []).append(row)
    return {
        _publication_identity(row)
        for row in selected
        if any(built(other) and not other_edition(other, row) for other in by_identity.get(_publication_identity(row), ()))
    }


def _republished_since_build(store: CatalogStore, parts: Sequence[LakePartition]) -> set[str]:
    """The sources of ``parts`` the server now lists as another version than the one their partition was built from.

    A partition is matched to its publications by path (`_source_identities`), so a file DATASUS republishes at the same
    path (SIH-RD RDES2510-2512 on 2026-10-16, AIHs added) left the partition built on 2026-10-15 counted as covering it,
    and a query read the old records. The version a build read is the latest fetch of the path made by the time the
    partition was written; the server's version now is the catalog's listing. They differ when the size does, or the
    time does other than as the server's two clocks (`listing.same_instant`). A source no fetch dates (a partition from
    before fetch rows were kept) cannot be judged and is taken as built from the current version."""
    from ..discovery.listing import same_instant

    paths = sorted({p.relative_path for p in parts})
    if not paths:
        return set()
    out: set[str] = set()
    for start in range(0, len(paths), 400):
        chunk = paths[start:start + 400]
        marks = ",".join("?" for _ in chunk)
        rows = store.query(
            f"""
            SELECT s.value AS path, fi.size AS listed_size, fi.modified AS listed_mtime,
                   (SELECT f.remote_size FROM fetches f WHERE f.source_path = s.value AND f.fetched_at <= lp.written_at
                     ORDER BY f.fetched_at DESC, f.id DESC LIMIT 1) AS built_size,
                   (SELECT f.byte_size FROM fetches f WHERE f.source_path = s.value AND f.fetched_at <= lp.written_at
                     ORDER BY f.fetched_at DESC, f.id DESC LIMIT 1) AS built_bytes,
                   (SELECT f.remote_modified FROM fetches f WHERE f.source_path = s.value AND f.fetched_at <= lp.written_at
                     ORDER BY f.fetched_at DESC, f.id DESC LIMIT 1) AS built_mtime
              FROM lake_partitions lp, json_each(lp.source_paths) s
              JOIN files fi ON fi.path = s.value
             WHERE lp.relative_path IN ({marks}) AND fi.gone_at IS NULL
            """,
            tuple(chunk),
        )
        for row in rows:
            size = row["built_size"] if row["built_size"] is not None else row["built_bytes"]
            if size is None:
                continue
            listed = row["listed_size"]
            if listed is not None and int(listed) != int(size) or row["built_mtime"] and row["listed_mtime"] and not same_instant(str(row["built_mtime"]), str(row["listed_mtime"])):
                out.add(str(row["path"]))
    return out


def _has_publications(store: CatalogStore, family_ids: Sequence[str]) -> bool:
    """Does the catalog hold any publication of these families (an inventory-free fixture holds none)?"""
    if not family_ids:
        return False
    ids = tuple(family_ids)

    def load() -> bool:
        return any(
            store.query(
                f"SELECT 1 FROM family_files WHERE family_id IN ({','.join('?' for _ in ids[start:start + 500])}) LIMIT 1",
                ids[start:start + 500],
            )
            for start in range(0, len(ids), 500)
        )

    return store.memo(("has_publications", ids), load)


def _catalog_coverage(
    store: CatalogStore, settings: Settings, system: str, series: str | None, years: tuple[int, ...],
    ufs_asked: tuple[str, ...], period: Period | None = None,
) -> _Coverage:
    """The part of the coverage the catalog decides, with the lake files each lake year rests on.

    Pure in the catalog state, so remembered until it changes; whether those files are still on disk is not a
    catalog fact and is checked by :func:`_coverage` on every call. A ``period`` given in months narrows the files of
    a year to those built from the publications of its months (:func:`in_months`), and names the months of a monthly
    year that no publication is filed for (``unpublished``); when none of the months asked is filed in any year there is
    nothing to read, and :class:`NothingPublished` says so, where the year was read whole and came back empty.
    """
    from ..representations import choose_representations
    from .readplan import resolve_family

    declaration = _compiled_capability(settings, system, series)
    declared_physical_uf = bool((declaration or {}).get("physical_geography") == "uf")
    families = resolve_family(store, system, series, None)
    ids = [str(item["family_id"]) for item in families]
    # every year's publications are only needed to say whether the dataset is cut by state when no year is asked
    publications = _publication_rows(store, ids, years)
    requested_years = tuple(years) or tuple(
        sorted({int(row["year"]) for row in publications if row.get("year")})
    )
    relevant = [row for row in publications if not requested_years or row.get("year") in requested_years]
    observed_geo = [str(row.get("geo_code") or "") for row in relevant]
    # ANY UF-coded publication proves the axis. The old test demanded the
    # partition be EXCLUSIVELY per-UF, and SIM's tree is not: DO{UF}2022
    # for all 27 states coexists with a consolidated DOBR file and a few
    # geo-less documentation rows, so the axis was erased by the company
    # it keeps. When a UF is requested, the filter below already excludes
    # the BR consolidated, so no row is double-counted.
    # Whether a dataset is cut by state is a fact about its filenames, and
    # the catalog has them: any publication carrying a real UF proves the
    # axis. Requiring a curated declaration as well left all but five
    # datasets (CNES.EP, CNES.EQ, CIH.CR …) refusing `geography=` although
    # they are published per state (the all-dataset sweep, 2026-09-28).
    # A year with no publication at all says nothing about the axis: the dataset's other years do, so a UF asked
    # of SIA-SAD in 2023 (published 2012-2018) ends in NothingPublished, not in "UF is not a partition".
    axis_geo = observed_geo or [str(row.get("geo_code") or "") for row in _publication_rows(store, ids)]
    measured_uf = any(value not in {"", "BR"} for value in axis_geo)
    physical_uf = measured_uf or (declared_physical_uf and not observed_geo)
    wanted_ufs = set(ufs_asked) if physical_uf and ufs_asked else set()
    national_ufs: tuple[str, ...] = ()
    if wanted_ufs == {"BR"} and not any(value.upper() == "BR" for value in observed_geo):
        # The nation, for a dataset DATASUS publishes only per state, is
        # every state. `geography="BR"` on SIH-RD raised NothingPublished
        # (2026-09-30) although all 27 states were there.
        national_ufs = tuple(sorted({value.upper() for value in observed_geo if value not in {"", "BR"}}))
        wanted_ufs = set(national_ufs)
    if wanted_ufs:
        relevant = [row for row in relevant if str(row.get("geo_code") or "").upper() in wanted_ufs]

    parts = [part for family_parts in listed_partitions(store, ids).values() for part in family_parts]
    has_publications = _has_publications(store, ids)
    lake_years: list[int] = []
    fetch_years: list[int] = []
    resolutions: list[tuple[int, str]] = []
    year_geography: list[tuple[int, tuple[str, ...]]] = []
    lake_partitions: list[LakePartition] = []
    published_rows: list[dict[str, Any]] = []
    unpublished: list[tuple[int, tuple[int, ...]]] = []
    published: dict[int, tuple[int, ...]] = {}
    nothing_filed: set[int] = set()
    any_partition = bool(parts)
    for year in requested_years:
        candidates = [row for row in relevant if int(row.get("year") or 0) == year]
        ufs_year = tuple(sorted(wanted_ufs))
        if not wanted_ufs:
            # no state asked: one reading of the year (a national file beside its state files is the same records)
            reading = national_or_states(candidates, lambda row: row.get("geo_code"))
            if len(reading) < len(candidates):
                candidates, ufs_year = reading, ("BR",)
                year_geography.append((year, ufs_year))
        selected = list(choose_representations(store, candidates).selected) if candidates else []
        month_marks = {int(row.get("normalized_date") or 0) % 100 for row in selected}
        resolution = (
            "mixed" if 0 in month_marks and any(month_marks) else
            "month" if any(month_marks) else
            "year" if selected else "unknown"
        )
        resolutions.append((year, resolution))
        year_parts = Lake.narrow(parts, ufs_year or None, [year])
        if not ufs_year:
            year_parts = one_reading(year_parts)        # no reading decided from the publications: the lake's own
        if selected:
            expected = {_publication_identity(row) for row in selected}
            # a partition built from a version the server has since replaced covers nothing: the year is read from the
            # current files (and the next build rewrites the partition)
            stale = _republished_since_build(store, year_parts)
            covered = {(p.family_id, source) for p in year_parts for source in p.sources if source not in stale}
            complete = expected <= _source_identities(selected, candidates, covered)
        else:
            # An inventory-free fixture/catalog cannot prove an expected
            # publication is missing. A real inventory takes the strict path above.
            complete = bool(year_parts) or (not has_publications and any_partition)
        (lake_years if complete else fetch_years).append(year)
        if complete:
            asked_months = period.months_in(year) if period is not None else ()
            read = in_months(year_parts, candidates, asked_months) if asked_months else year_parts
            if asked_months and resolution == "month":
                filed = {int(row.get("normalized_date") or 0) % 100 for row in candidates}
                if absent := tuple(month for month in asked_months if month not in filed):
                    unpublished.append((year, absent))
                    published[year] = tuple(sorted(filed))
                    if not read:
                        nothing_filed.add(year)
                elif not read:
                    read = year_parts           # every month is filed and no file was found for it: read more, never fewer
            lake_partitions.extend(read)
            published_rows.extend(candidates)

    if nothing_filed:
        # a year none of whose months asked is filed has nothing to read (its table would be empty and read as "no
        # records in those months"): the plan says so (`unpublished`), and when no year is left to read, the request fails
        lake_years = [year for year in lake_years if year not in nothing_filed]
        if not lake_years and not fetch_years:
            from .._request import NothingPublished

            said = "; ".join(
                f"{', '.join(f'{year}-{month:02d}' for month in absent)} (filed in {year}: "
                f"{', '.join(f'{month:02d}' for month in published[year] if month) or 'none by month'})"
                for year, absent in unpublished
            )
            raise NothingPublished(f"{system}-{series or ''} files no publication for {said}")

    unique_resolutions = {value for _, value in resolutions if value != "unknown"}
    overall = next(iter(unique_resolutions)) if len(unique_resolutions) == 1 else (
        "mixed" if unique_resolutions else str((declaration or {}).get("publication_resolution") or "unknown")
    )
    strategy = "hybrid" if lake_years and fetch_years else "lake" if lake_years else "fetch"
    coverage = _Coverage(
        overall, physical_uf, strategy,
        tuple(lake_years), tuple(fetch_years), tuple(resolutions), national_ufs, tuple(year_geography),
        lake_partitions=tuple(lake_partitions),
        lake_competence=tuple(sorted(sole_competence(lake_partitions, published_rows).items())),
        unpublished=tuple(unpublished),
    )
    return coverage


def _coverage(
    settings: Settings,
    store: CatalogStore,
    system: str,
    series: str | None,
    *,
    years: Sequence[int],
    geography: Geography | None,
    period: Period | None = None,
) -> _Coverage:
    """Resolve source-publication capabilities and exact local coverage.

    The catalog's answer is remembered until the catalog changes; the lake's files are looked at every time. A year the
    catalog lists as lake-complete whose partition files are gone (a pruned or moved lake, a rebuild caught between
    its two renames) is not lake-complete: it falls back to the source, and the plan says so.
    """
    ufs_asked = tuple(geography.ufs) if geography else ()
    months = period if period is not None and period.precision == "month" else None
    coverage = store.memo(
        ("coverage", system, series, tuple(years), ufs_asked, months),
        lambda: _catalog_coverage(store, settings, system, series, tuple(years), ufs_asked, months),
    )
    lake_dir = Path(settings.lake_dir)
    gone = tuple(sorted({p.year for p in coverage.lake_partitions if not (lake_dir / p.relative_path).is_file()}))
    if not gone:
        return coverage
    lake_years = tuple(y for y in coverage.lake_years if y not in gone)
    fetch_years = tuple(sorted({*coverage.fetch_years, *gone}))
    strategy = "hybrid" if lake_years and fetch_years else "lake" if lake_years else "fetch"
    from dataclasses import replace

    return replace(coverage, source_strategy=strategy, lake_years=lake_years, fetch_years=fetch_years,
                   missing_lake_years=gone,
                   lake_partitions=tuple(p for p in coverage.lake_partitions if p.year not in gone))


def download_estimate(
    settings: Settings,
    store: CatalogStore,
    system: str,
    series: str | None,
    years: Sequence[int],
    months_by_year: dict[int, tuple[int, ...]],
    ufs: Sequence[str],
    year_ufs: dict[int, tuple[str, ...]] | None = None,
) -> tuple[int | None, int | None]:
    """(bytes the fetch would select, bytes of those already cached).

    From the catalog alone, before anything moves: the publications a fetch of
    these years, months and states would read, one representation each
    (ADR-0076). ``year_ufs``: the files a year reads when it differs from ``ufs`` (the national file beside its state
    files). ``(None, None)`` when the catalog cannot say.
    """
    if not years:
        return 0, 0
    from ..representations import choose_representations
    from ..retrieve import _month_of
    from .readplan import resolve_family

    ids = [str(f["family_id"]) for f in resolve_family(store, system, series, None)]
    if not ids:
        return None, None
    wanted_all = {u.upper() for u in ufs}
    per_year = {y: {u.upper() for u in v} for y, v in (year_ufs or {}).items()}
    rows = []
    for row in _publication_rows(store, ids, years):
        year = row.get("year")
        if year not in set(years):
            continue
        wanted = per_year.get(int(year), wanted_all)
        if wanted and str(row.get("geo_code") or "").upper() not in wanted:
            continue
        months = months_by_year.get(int(year))
        month = _month_of(row.get("normalized_date"))
        if months and month is not None and month not in set(months):
            continue
        rows.append(row)
    selected = list(choose_representations(store, rows, on_conflict="all").selected) if rows else []
    paths = sorted({str(r["path"]) for r in selected})
    total = sum(int(r.get("size") or 0) for r in {str(r["path"]): r for r in selected}.values())
    cached = 0
    if paths:
        # a file is cached while one of its fetched blobs is on disk: the fetch history is append-only, and a blob
        # an extract released after reading (`BlobStore.prune_verified`) had counted as cached, SIA-PA 2016's
        # 6.75 GB "cached" fetched again (2026-10-12). The blob store is not catalog state, so this stays outside the
        # remembered answers.
        marks = ",".join("?" for _ in paths)
        blobs = Path(settings.blobs_dir) / "sha256"
        fetched = store.query(
            f"SELECT DISTINCT f.path, f.size, x.sha256 FROM files f JOIN fetches x ON x.source_path = f.path "
            f"WHERE f.path IN ({marks})", tuple(paths))
        held: dict[str, int] = {}
        for row in fetched:
            digest = str(row["sha256"])
            if (blobs / digest[:2] / digest).exists():
                held[str(row["path"])] = int(row["size"] or 0)
        cached = sum(held.values())
    return total, cached
