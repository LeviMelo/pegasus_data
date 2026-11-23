"""Filtered extracts: every record of a dataset whose code columns hold declared codes, read file by file.

Some datasets are larger than the lake can hold (SIA-PA 2010-2025 is about 190 GB of DBC files, SIA-BI 156 GB; the disk
has under 180 GB free), while a study needs a few procedures of them (toxoplasma serology). An extract streams the
dataset's published files one at a time: fetch, decode, keep the records any of whose ``filters`` (column -> code
prefixes) matches, whole, write them, and release the file's blob unless a snapshot keeps it. Several
filters are one pass (SIA-PA's serology procedures and its records coded B58 on PA_CIDPRI). Peak disk is one file; the
extract is each filter's complete records, never a sample.

An extract reads the published files through ``fetch`` (``only_paths``), one at a time, never the lake or ``query()``: its
point is a dataset the lake cannot hold, and the planner's lake/fetch choice has nothing to choose.

An extract lives apart from the lake (``<lake>/extracts/<dataset>/<digest>/``): a query for other codes must never read
a filtered table as if it were the dataset. A query whose row filter an extract's filters cover reads the files the
extract holds from it, file by file, instead of downloading them again (`held_files`, `held_rows`): every record that
can match the query was kept, so the query's own filter, applied after, gives what the file would have given. Its manifest names the filters, every file read with the rows read and
kept, and the files that failed, so a short extract is visibly short.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .persist.kept import write_json_atomic, write_parquet_atomic

__all__ = ["build_extract", "extract_dir", "extract_table", "held_files", "held_rows"]


def _filters(filters: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    from ._query_engine.request import normalise_prefix

    return {str(c).upper(): sorted({normalise_prefix(x) for x in codes}) for c, codes in sorted(filters.items())}


def extract_dir(settings: Any, dataset: str, filters: Mapping[str, Sequence[str]]) -> Path:
    """Where the extract of ``dataset`` by ``filters`` (column -> code prefixes) is kept."""
    from ._request import parse_dataset

    system, series = parse_dataset(dataset)
    digest = hashlib.sha256(json.dumps(_filters(filters)).encode()).hexdigest()[:12]
    return Path(settings.lake_dir) / "extracts" / f"{system}-{series or system}" / digest


def _files(settings: Any, dataset: str, years: Sequence[int], ufs: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """The dataset's published data files of ``years`` (the catalog's file facts): path, state, year, period; one
    representation per publication, chosen as a query chooses it (`choose_representations`). Listing every copy made
    the extract read a publication twice where DATASUS mirrors it, and fail where an older copy cannot be read:
    SIA-PA Paraná 2024-08..2025-06 sits in ``/SIASUS/teste/`` (September 2025 trial copies) beside ``200801_/Dados``,
    and the trial copies, never a query's choice, failed and kept 2024 and 2025 unheld (toxoplasmosis study,
    2026-11-05)."""
    from ._request import parse_dataset
    from .catalog.store import CatalogStore
    from .representations import choose_representations

    system, series = parse_dataset(dataset)
    store = CatalogStore(settings.catalog_path)
    try:
        marks = ",".join("?" for _ in years)
        rows = store.query(
            f"""SELECT ff.path, ff.geo_code, ff.year, ff.normalized_date, ff.logical_id, ff.container_format,
                       f.size, fm.member, fm.family_id, fam.schema_signature
                  FROM file_facts ff JOIN files f ON f.path = ff.path
                  LEFT JOIN family_files fm ON fm.path = ff.path
                  LEFT JOIN families fam ON fam.family_id = fm.family_id
                WHERE ff.system = ? AND ff.series_prefix = ? AND ff.role = 'data' AND f.gone_at IS NULL
                AND ff.year IN ({marks}) ORDER BY ff.year, ff.normalized_date, ff.geo_code""",
            [system, series or system, *map(int, years)])
        file_rows = [dict(r) for r in rows if not ufs or r["geo_code"] in set(ufs)]
        chosen = {str(r["path"]) for r in choose_representations(store, file_rows, on_conflict="all").selected}
        keep = ("path", "geo_code", "year", "normalized_date")
        seen: set[str] = set()
        out = []
        for r in file_rows:
            if r["path"] in chosen and r["path"] not in seen:
                seen.add(r["path"])
                out.append({k: r[k] for k in keep})
        return out
    finally:
        store.close()


def _census_fields(settings: Any, files: Sequence[dict[str, Any]]) -> dict[int, frozenset[str] | None]:
    """``year -> the upper-cased fields the header census lists for that year's files`` (a file's own header where the
    per-file census read it, else its family's schema); ``None`` for a year in which any file has no census, which
    proves nothing about a column."""
    from ._query_engine.readplan import schema_presence
    from .catalog.store import CatalogStore

    store = CatalogStore(settings.catalog_path, read_only=True)
    try:
        signature: dict[str, str | None] = {}
        paths = [f["path"] for f in files]
        for start in range(0, len(paths), 500):
            chunk = paths[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            for row in store.query(
                f"""SELECT fm.path AS path, COALESCE(fs.schema_signature, fam.schema_signature) AS sig
                    FROM family_files fm JOIN families fam ON fam.family_id = fm.family_id
                    LEFT JOIN file_schemas fs ON fs.path = fm.path WHERE fm.path IN ({marks})""", chunk):
                signature[row["path"]] = row["sig"]
        presence = schema_presence(store, [{"schema_signature": s} for s in {s for s in signature.values() if s}])
    finally:
        store.close()
    fields: dict[int, set[str] | None] = {}
    for f in files:
        year, sig = int(f["year"]), signature.get(f["path"])
        listed = presence.get(str(sig)) if sig else None
        if year in fields and fields[year] is None:
            continue
        fields[year] = ({n.upper() for n in listed} | (fields.get(year) or set())) if listed else None
    return {y: (frozenset(v) if v is not None else None) for y, v in fields.items()}


def _check_filter_columns(settings: Any, dataset: str, files: Sequence[dict[str, Any]], filt: dict[str, list[str]],
                          log: Callable[[str], None]) -> None:
    """Fail before the first fetch when a filter column is in no file's header: `_match` reads a layout without the
    column as holding none of its records, so a misspelt column fetched and decoded every file (hours of a 190 GB
    dataset) and recorded the extract complete with zero rows. A column some years' layouts lack is reported, not
    refused: those years' files hold none of its records. Silent where the census does not cover the files."""
    import difflib

    if not files:
        return
    census = _census_fields(settings, files)
    known = {y: f for y, f in census.items() if f is not None}
    for column in filt:
        carriers = [y for y, f in known.items() if column in f]
        if carriers or len(known) < len(census):
            if (lacking := sorted(set(known) - set(carriers))):
                log(f"extract {dataset}: {column} is not in the layout of {lacking}: those years' files hold none of its records")
            continue
        every = sorted(set().union(*known.values())) if known else []
        near = difflib.get_close_matches(column, every, n=5, cutoff=0.6)
        raise ValueError(
            f"extract {dataset}: filter column {column!r} is in no file's header of {sorted(known)} (the header census "
            f"lists {len(every)} fields); closest: {', '.join(near) or 'none'}. Nothing was fetched.")


def _release(settings: Any, paths: Sequence[str]) -> int:
    """Delete the blobs fetched for ``paths``, files this extract has read and kept the matching records of, unless a
    snapshot keeps them or they were also fetched for another path nothing holds (`BlobStore.prune_verified`, the
    rule a lake build's release follows too); returns the bytes freed."""
    from .acquire.cache import BlobStore
    from .catalog.store import CatalogStore

    store = CatalogStore(settings.catalog_path)
    try:
        return BlobStore(settings.blobs_dir, store).prune_verified(Path(settings.lake_dir), paths=paths,
                                                                   held=paths)["bytes"]
    finally:
        store.close()


def _part_path(target: Path, year: int, geo_code: str, period: str) -> Path:
    """Where a file's kept rows land in an extract: the extract's layout, written and read only here."""
    return target / f"year={int(year)}" / f"{geo_code}_{period}.parquet"


def _year_parts(extract_dir: Path, year: int) -> list[Path]:
    return sorted((extract_dir / f"year={year}").glob("*.parquet"))


def _match(table: pa.Table, column: str, prefixes: Sequence[str]) -> pa.Array | None:
    """The rows whose ``column`` starts with one of ``prefixes`` (None: the table has no such column)."""
    from ._query_engine.request import prefix_match

    col = next((c for c in table.column_names if c.upper() == column), None)
    if col is None:
        return None
    return pc.fill_null(prefix_match(pc.cast(table.column(col), pa.string()), prefixes), False)


#: files fetched at once, each over its own FTP connection (the fetcher's tested limit is 8): the server gives about
#: 0.5 MB/s a connection (2026-10-11); decoding waits for memory in pegasus_data's admission control, and a worker
#: hands back only its file's kept records
EXTRACT_WORKERS = 6


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """The manifest written whole or not at all (a temporary file replaced): rewritten in place every few files, a
    reader caught it half written and took the extract for absent (PegaSUS's tests, 2026-10-12)."""
    write_json_atomic(manifest, path, indent=1)


def _read_manifest(path: Path) -> dict[str, Any] | None:
    """A manifest, read again when caught mid-write by a builder of the older, in-place kind; None when absent."""
    import time

    for _ in range(5):
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            time.sleep(0.2)
    return None


def build_extract(dataset: str, years: Sequence[int], filters: dict[str, Sequence[str]], *,
                  ufs: Sequence[str] | None = None, root: str | Path | None = None, settings: Any = None,
                  log: Callable[[str], None] = print, workers: int = EXTRACT_WORKERS) -> dict[str, Any]:
    """`_build_extract` under the extract's own lock: one builder at a time. Two would each read the files the manifest
    lacks and each write the manifest as it saw it, losing entries and writing a file's records twice (a study's
    store step beside the long SIA-PA extract, 2026-10-12). A second caller does not wait for hours: it returns the
    manifest as it stands, and a reader takes only the years held whole."""
    from filelock import FileLock, Timeout

    from .config import load_settings

    settings = settings or load_settings(root=Path(root) if root else None)
    target = extract_dir(settings, dataset, _filters(filters))
    target.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(target / ".build.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        mpath = target / "manifest.json"
        log(f"extract {dataset}: another process is building it; read as it stands")
        return _read_manifest(mpath) or {"dataset": dataset, "filters": _filters(filters), "files": {}, "failed": {}}
    try:
        return _build_extract(dataset, years, filters, ufs=ufs, settings=settings, log=log, workers=workers)
    finally:
        lock.release()


def _build_extract(dataset: str, years: Sequence[int], filters: dict[str, Sequence[str]], *,
                   ufs: Sequence[str] | None = None, root: str | Path | None = None, settings: Any = None,
                   log: Callable[[str], None] = print, workers: int = EXTRACT_WORKERS) -> dict[str, Any]:
    """Extract the records of ``dataset`` in ``years`` that any of ``filters`` (column -> code prefixes) matches, file
    by file (module docstring), ``workers`` files at a time. A file already in the manifest is not read again, so an
    interrupted extract resumes. Returns the manifest. ``ufs`` reads only those states' files (an extract that is not
    whole says so when read)."""
    from .concurrency import Pace, adaptive_map
    from .config import load_settings
    from .retrieve import fetch

    settings = settings or load_settings(root=Path(root) if root else None)
    filt = _filters(filters)
    target = extract_dir(settings, dataset, filt)
    target.mkdir(parents=True, exist_ok=True)
    mpath = target / "manifest.json"
    manifest = _read_manifest(mpath) or {"dataset": dataset, "filters": filt, "files": {}, "failed": {}}
    # a failure is the file's state until it is read: one a later run read (or an older run listed beside its success)
    # no longer counts against its year, or `extract_table` would refuse that year for ever
    manifest["failed"] = {p: why for p, why in (manifest.get("failed") or {}).items() if p not in manifest["files"]}
    files = _files(settings, dataset, years, ufs)
    _check_filter_columns(settings, dataset, files, filt, log)
    todo = [f for f in files if f["path"] not in manifest["files"]]
    log(f"extract {dataset} {filt}: {len(files)} files in {sorted(set(map(int, years)))}, {len(todo)} to read")
    t0 = time.time()

    def read(f: dict[str, Any]) -> tuple[dict[str, Any], Any, int, Any]:
        """One file fetched, decoded and filtered in the worker: only its kept records wait for their turn."""
        try:
            # the filters go into the read: rows that cannot match are dropped raw, before they are normalised and
            # hashed (SIH-SP: 1.3% of 1.6 billion rows kept, and the rest had cost two thirds of the extract's time)
            table, report = fetch(dataset, labels=False, provenance=True, only_paths=[f["path"]], report=True,
                                  max_bytes=None, settings=settings, on_missing_column="null_fill",
                                  rows=filt, rows_join="any")
        except Exception as exc:  # noqa: BLE001 - a file that does not open is a recorded gap, not an absence
            return f, exc, 0, None
        mask = None
        for column, prefixes in filt.items():
            hit = _match(table, column, prefixes)          # a layout without the column holds none of its records
            if hit is not None:
                mask = hit if mask is None else pc.or_(mask, hit)
        # the file's own records, counted before the read's row filter dropped the ones that cannot match
        return f, (table.filter(mask) if mask is not None else table.slice(0, 0)),             int(getattr(report, "rows_decoded", 0) or table.num_rows), report

    # as many files in flight as the total rate keeps rising with (`concurrency.adaptive_map`), starting at ``workers``:
    # a fixed six was short of the line one hour and past it the next (2026-11-21)
    pace = Pace()

    def results():
        return adaptive_map(read, todo, start=max(1, workers),
                            measure=lambda out: getattr(out[3], "bytes_downloaded", 0) or 0, pace=pace)

    for i, (f, kept, rows, report) in enumerate(results()):
        if isinstance(kept, Exception):
            manifest["failed"][f["path"]] = f"{type(kept).__name__}: {kept}"[:300]
            log(f"extract {dataset}: {f['path']} failed: {type(kept).__name__}: {kept}")
            continue
        if kept.num_rows:
            part = _part_path(target, f["year"], f["geo_code"], f["normalized_date"])
            part.parent.mkdir(parents=True, exist_ok=True)
            write_parquet_atomic(kept, part, compression="zstd")
        manifest["files"][f["path"]] = {"year": int(f["year"]), "uf": f["geo_code"], "period": f["normalized_date"],
                                        "rows": rows, "kept": kept.num_rows,
                                        "downloaded": int(getattr(report, "bytes_downloaded", 0) or 0)}
        manifest["failed"].pop(f["path"], None)
        _release(settings, [f["path"]])
        if (i + 1) % 25 == 0 or i + 1 == len(todo):
            _write_manifest(mpath, manifest)
            done = sum(v["rows"] for v in manifest["files"].values())
            log(f"extract {dataset}: {i + 1}/{len(todo)} files, {done:,} rows read, "
                f"{sum(v['kept'] for v in manifest['files'].values()):,} kept, {time.time() - t0:.0f} s")
    manifest["pace"] = pace.as_dict()
    _write_manifest(mpath, manifest)
    return manifest


def held_files(settings: Any, dataset: str, filters: Mapping[str, Sequence[str]],
               join: str = "all") -> dict[str, tuple[Path, dict[str, Any]]]:
    """The published files of ``dataset`` an extract holds every record of that row filter ``filters`` (column -> code
    prefixes, combined by ``join``: "all" or "any") can keep: path -> (extract directory, the manifest's entry).

    An extract kept a record when ANY of its filters matched. Under "all" the query keeps only records that match
    each of its columns, so one column whose prefixes an extract's filter on it covers makes the extract complete
    for the query; under "any" every column of the query must be covered. A file the manifest records as failed,
    or does not record, is not held: it is read from its publication."""
    from ._query_engine.request import normalise_prefix
    from ._request import parse_dataset

    asked = {str(c).upper(): {normalise_prefix(x) for x in v} for c, v in filters.items() if v}
    if not asked:
        return {}
    system, series = parse_dataset(dataset)
    base = Path(settings.lake_dir) / "extracts" / f"{system}-{series or system}"
    out: dict[str, tuple[Path, dict[str, Any]]] = {}
    for d in sorted(base.iterdir()) if base.exists() else []:
        m = _read_manifest(d / "manifest.json")
        if not m:
            continue
        held = {str(c).upper(): list(v) for c, v in (m.get("filters") or {}).items()}
        covered = [c for c, want in asked.items()
                   if c in held and all(any(a.startswith(p) for p in held[c]) for a in want)]
        if not (covered if join == "all" else len(covered) == len(asked)):
            continue
        failed = set(m.get("failed") or ())
        for path, entry in (m.get("files") or {}).items():
            if path not in failed and path not in out:
                out[path] = (d, entry)
    return out


def held_rows(directory: Path, path: str, entry: Mapping[str, Any]) -> pa.Table | None:
    """The kept records of the published file ``path`` in the extract at ``directory`` (None: it kept none)."""
    if not int(entry.get("kept") or 0):
        return None
    part = _part_path(directory, int(entry["year"]), str(entry["uf"]), str(entry["period"]))
    table = pq.read_table(part)
    if "_source_path" in table.column_names:
        # a part is one file's rows; a publication split into members carries the member in its source id
        source = pc.cast(table.column("_source_path"), pa.string())
        mine = pc.or_(pc.equal(source, path), pc.starts_with(source, path + "!"))
        table = table.filter(pc.fill_null(mine, False))
    return table


def extract_table(dataset: str, column: str, codes: Sequence[str], years: Sequence[int] | None = None, *,
                  root: str | Path | None = None, settings: Any = None) -> tuple[pa.Table, dict[str, Any]]:
    """The records of ``dataset`` whose ``column`` starts with one of ``codes``, for ``years``, from an extract with a
    filter on ``column`` whose prefixes cover every asked code; with its manifest. LookupError when no extract covers
    them or a year is not read whole (a failed file, or a file of the year not yet read)."""
    from ._request import parse_dataset
    from .config import load_settings

    settings = settings or load_settings(root=Path(root) if root else None)
    from ._query_engine.request import normalise_prefix

    asked = sorted({normalise_prefix(c) for c in codes})
    column = column.upper()
    system, series = parse_dataset(dataset)
    base = Path(settings.lake_dir) / "extracts" / f"{system}-{series or system}"
    for d in sorted(base.iterdir()) if base.exists() else []:
        m = _read_manifest(d / "manifest.json")
        held = ((m or {}).get("filters") or {}).get(column)
        if not held or not all(any(a.startswith(p) for p in held) for a in asked):
            continue
        assert m is not None  # held is non-empty only when the manifest was read
        read = {int(v["year"]) for v in m["files"].values()}
        want = sorted(set(map(int, years))) if years else sorted(read)
        listed = {f["path"] for f in _files(settings, dataset, want)}
        unread = [p for p in listed if p not in m["files"]]
        # a failure counts against its own year only: one stray file of DATASUS's "teste" folder (2024) had made
        # every year of SIA-PA's extract unheld (2026-10-12)
        failed = [p for p in m["failed"] if p in listed and p not in m["files"]]
        if unread or failed:
            raise LookupError(f"{dataset} {column} {asked}: the extract does not hold {want} whole "
                              f"({len(unread)} files unread, {len(failed)} failed)")
        parts = [p for y in want for p in _year_parts(d, y)]
        table = pa.concat_tables([pq.read_table(p) for p in parts], promote_options="default") if parts else pa.table({})
        if table.num_rows:
            mask = _match(table, column, asked)
            table = table.filter(mask) if mask is not None else table.slice(0, 0)
        return table, m
    raise LookupError(f"{dataset}: no extract with a filter on {column} covers {asked}")
