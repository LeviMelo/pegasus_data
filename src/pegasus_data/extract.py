"""Filtered extracts: the records of a dataset whose code columns hold declared codes, read file by file, kept in the
dataset's one extract store (ADR-0236).

Some datasets are larger than the lake can hold (SIA-PA 2010-2025 is about 190 GB of DBC files, SIA-BI 156 GB), while a
study needs a few procedures of them. An extract streams the dataset's published files one at a time: fetch, decode,
keep the records any of whose ``filters`` (column -> code prefixes) matches, whole, write them, and release the file's
blob unless a snapshot keeps it. Peak disk is one file; the extract is each filter's complete records, never a sample.

What the home holds of a file is one holding (`persist.held`): the lake's partition, whole, or the store's rows of a
predicate, the union of every filter extracted from the file. A new filter reads only the files whose predicate does
not already imply it and stores only the rows it adds (``new AND NOT held``), so overlapping filters never store a row
twice and a filter already held downloads nothing. A file the lake holds whole is never extracted: it holds every
record any filter keeps, and `absorb` drops the store's rows of it once the lake has it. A file the server republishes
is read again, alone.

A query whose row filter a file's holding covers reads that file from the home instead of downloading it
(`held_files`, `held_rows`): every record that can match the query is held, so the query's own filter, applied after,
gives what the file would have given. Each file's holding is written to ``holdings.sqlite`` as its rows land, and a
file that failed is recorded beside it, so a short extract is visibly short.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .persist.held import ExtractStore, FileHolding, Predicate, lake_whole

__all__ = ["absorb", "absorb_landed", "build_extract", "extract_table", "held_files", "held_rows", "migrate_extracts"]


def _filters(filters: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    from ._query_engine.request import normalise_prefix

    return {str(c).upper(): sorted({normalise_prefix(x) for x in codes}) for c, codes in sorted(filters.items())}


def _family_prefix(dataset: str) -> str:
    from ._request import parse_dataset

    system, series = parse_dataset(dataset)
    return f"{system}_{series}_" if series else f"{system}_"


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

    store = CatalogStore.shared(settings.catalog_path)
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


#: files fetched at once, each over its own FTP connection (the fetcher's tested limit is 8): the server gives about
#: 0.5 MB/s a connection (2026-10-11); decoding waits for memory in pegasus_data's admission control, and a worker
#: hands back only its file's kept records
EXTRACT_WORKERS = 6
# worker processes for an extract's files (0: threads, the default). Measured on the SIH-SP 0415* extract
# (2026-11-24): threads 48.7 files/min at 4.4 MB/s, eight processes 50.0 files/min at 5.6 MB/s. A download-bound run
# gains nothing (DATASUS gives about 6 MB/s in total, evaluation 2026-11-21) and processes cost about 300 MB each.
# Processes pay where decoding is the limit: files already held raw.
EXTRACT_PROCESSES = 0


def _read_file(job: tuple) -> tuple[dict[str, Any], Any, int, int, str | None]:
    """One file fetched, decoded and filtered in a worker (a process: module-level, picklable): only the rows it adds
    to the store travel back, those ``add`` keeps and ``held`` (JSON of the file's held predicate, or None) does not.
    Returns (file, those rows or the exception, rows decoded, bytes downloaded, the digest read)."""
    dataset, f, add, held, settings = job
    from .retrieve import fetch
    try:
        # the filters go into the read: rows that cannot match are dropped raw, before they are normalised and
        # hashed (SIH-SP: 1.3% of 1.6 billion rows kept, and the rest had cost two thirds of the extract's time)
        table, report = fetch(dataset, labels=False, provenance=True, only_paths=[f["path"]], report=True,
                              max_bytes=None, settings=settings, on_missing_column="null_fill",
                              rows=add, rows_join="any")
    except Exception as exc:  # noqa: BLE001 - a file that does not open is a recorded gap, not an absence
        return f, exc, 0, 0, None
    mask = Predicate.of(add).mask(table)          # a layout without a column holds none of its records
    if held is not None:
        mask = pc.and_(mask, pc.invert(Predicate.from_json(held).mask(table)))
    sha = None
    if "_blob_sha256" in table.column_names and table.num_rows:
        found = pc.unique(pc.cast(table.column("_blob_sha256"), pa.string())).to_pylist()
        sha = str(found[0]) if len(found) == 1 else None
    if sha is None:
        sha = _fetched_digest(settings, f["path"])
    # the file's own records, counted before the read's row filter dropped the ones that cannot match
    return (f, table.filter(mask), int(getattr(report, "rows_decoded", 0) or table.num_rows),
            int(getattr(report, "bytes_downloaded", 0) or 0), sha)


def _fetched_digest(settings: Any, path: str) -> str | None:
    """The digest of the latest fetch of ``path`` (a file none of whose rows were kept carries none)."""
    from .catalog.store import CatalogStore

    store = CatalogStore.shared(settings.catalog_path)
    try:
        rows = store.query("SELECT sha256 FROM fetches WHERE source_path = ? ORDER BY fetched_at DESC, id DESC LIMIT 1",
                           (path,))
        return str(rows[0]["sha256"]) if rows else None
    finally:
        store.close()


def _whole(settings: Any, dataset: str, paths: Sequence[str] | None = None) -> dict[str, tuple[str, list[Path]]]:
    """The files the lake holds whole at their listed version (`holdings.lake_whole`)."""
    from .catalog.store import CatalogStore

    store = CatalogStore.shared(settings.catalog_path)
    try:
        return lake_whole(store, settings.lake_dir, _family_prefix(dataset), paths)
    finally:
        store.close()


def _stale(settings: Any, holdings: Mapping[str, FileHolding]) -> set[str]:
    from .catalog.store import CatalogStore
    from .persist.held import stale

    store = CatalogStore.shared(settings.catalog_path)
    try:
        return stale(store, {p: h.sha256 for p, h in holdings.items() if h.sha256})
    finally:
        store.close()


def build_extract(dataset: str, years: Sequence[int], filters: dict[str, Sequence[str]], *,
                  ufs: Sequence[str] | None = None, root: str | Path | None = None, settings: Any = None,
                  log: Callable[[str], None] = print, workers: int = EXTRACT_WORKERS,
                  processes: int | None = None) -> dict[str, Any]:
    """`_build_extract` under the store's lock: one builder of a dataset at a time. Two would each read the files the
    store lacks and each write a file's rows twice (a study's store step beside the long SIA-PA extract, 2026-10-12).
    A second caller does not wait for hours: it returns the holdings as they stand."""
    from filelock import FileLock, Timeout

    from .config import load_settings

    settings = settings or load_settings(root=Path(root) if root else None)
    store = ExtractStore(settings.lake_dir, dataset)
    store.root.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(store.root / ".build.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        log(f"extract {dataset}: another process is building it; read as it stands")
        return _manifest(settings, dataset, _filters(filters), years, ufs)
    try:
        return _build_extract(dataset, years, filters, ufs=ufs, settings=settings, log=log, workers=workers,
                              processes=processes)
    finally:
        lock.release()


def _build_extract(dataset: str, years: Sequence[int], filters: dict[str, Sequence[str]], *,
                   ufs: Sequence[str] | None, settings: Any, log: Callable[[str], None], workers: int,
                   processes: int | None) -> dict[str, Any]:
    """Hold the records of ``dataset`` in ``years`` that any of ``filters`` (column -> code prefixes) matches, file by
    file (module docstring), ``workers`` files at a time. A file the lake holds whole, or whose held predicate implies
    the filters at the listed version, is not read; any other is read for what it lacks. An interrupted build resumes.
    Returns the manifest (`_manifest`). ``ufs`` reads only those states' files."""
    from .concurrency import Pace, adaptive_map

    filt = _filters(filters)
    new = Predicate.of(filt)
    store = ExtractStore(settings.lake_dir, dataset)
    files = _files(settings, dataset, years, ufs)
    _check_filter_columns(settings, dataset, files, filt, log)
    listed = {f["path"] for f in files}
    whole = _whole(settings, dataset, sorted(listed))
    holdings = store.holdings()
    void = _stale(settings, {p: h for p, h in holdings.items() if p in listed})
    jobs = []
    for f in files:
        if f["path"] in whole:
            continue
        h = holdings.get(f["path"])
        if h is not None and f["path"] not in void:
            if new.implies(h.predicate):
                continue
            jobs.append((f, new.beyond(h.predicate), h.predicate, False))
        else:
            # never read, or republished since: the listed version is read for all its holding keeps, and replaces it
            jobs.append((f, new.union(h.predicate) if h is not None else new, None, True))
    log(f"extract {dataset} {filt}: {len(files)} files in {sorted(set(map(int, years)))}, {len(whole)} held whole by the "
        f"lake, {len(files) - len(whole) - len(jobs)} by the store, {len(jobs)} to read")
    t0 = time.time()
    pace = Pace()
    by_path = {f["path"]: (add, replace) for f, add, _held, replace in jobs}

    def results():
        # worker processes where decoding is the limit (EXTRACT_PROCESSES)
        procs = processes if processes is not None else EXTRACT_PROCESSES
        args = [(dataset, f, add.filters(), held.to_json() if held is not None else None, settings)
                for f, add, held, _replace in jobs]
        if procs:
            return adaptive_map(_read_file, args, start=min(max(1, workers), procs), cap=procs,
                                measure=lambda out: out[3], pace=pace, processes=True)
        return adaptive_map(_read_file, args, start=max(1, workers), measure=lambda out: out[3], pace=pace)

    added = 0
    for i, (f, kept, rows, _downloaded, sha) in enumerate(results()):
        add, replace = by_path[f["path"]]
        if isinstance(kept, Exception):
            store.fail(f["path"], add, f"{type(kept).__name__}: {kept}")
            log(f"extract {dataset}: {f['path']} failed: {type(kept).__name__}: {kept}")
            continue
        store.add(path=f["path"], year=int(f["year"]), uf=str(f["geo_code"]), period=str(f["normalized_date"]),
                  sha256=sha, predicate=add, rows=rows, table=kept, replace=replace)
        added += kept.num_rows
        _release(settings, [f["path"]])
        if (i + 1) % 25 == 0 or i + 1 == len(jobs):
            log(f"extract {dataset}: {i + 1}/{len(jobs)} files, {added:,} rows added, {time.time() - t0:.0f} s")
    out = _manifest(settings, dataset, filt, years, ufs)
    out["pace"] = pace.as_dict()
    return out


def _manifest(settings: Any, dataset: str, filt: Mapping[str, Sequence[str]], years: Sequence[int],
              ufs: Sequence[str] | None) -> dict[str, Any]:
    """What the home holds of the files of ``years`` (and ``ufs``) for ``filt``, in the manifest form `build_extract`
    returned before the store: ``files`` (path -> entry: year, state, period, and where it is held: ``"store": "lake"``
    with its digest, or ``"extract"`` with the file's rows, the store's rows of it and its held predicate), ``failed``
    (path -> why) and ``unheld`` (the paths held neither way)."""
    files = _files(settings, dataset, years, ufs)
    paths = [f["path"] for f in files]
    whole = _whole(settings, dataset, paths)
    store = ExtractStore(settings.lake_dir, dataset)
    holdings = store.holdings()
    void = _stale(settings, {p: h for p, h in holdings.items() if p in set(paths)})
    pred = Predicate.of(filt)
    failures = store.failures()
    out: dict[str, Any] = {"dataset": dataset, "filters": dict(filt), "files": {}, "failed": {}, "unheld": []}
    for f in files:
        p = f["path"]
        if p in whole:
            out["files"][p] = {"year": int(f["year"]), "uf": f["geo_code"], "period": f["normalized_date"],
                               "store": "lake", "sha256": whole[p][0], "files": [str(x) for x in whole[p][1]]}
        elif p in holdings and p not in void and pred.implies(holdings[p].predicate):
            out["files"][p] = {**holdings[p].entry(), "store": "extract"}
        elif p in failures:
            out["failed"][p] = failures[p]
        else:
            out["unheld"].append(p)
    return out


def held_files(settings: Any, dataset: str, filters: Mapping[str, Sequence[str]] | None = None,
               join: str = "all", paths: Sequence[str] | None = None) -> dict[str, tuple[Path | None, dict[str, Any]]]:
    """The published files of ``dataset`` the home holds every record of that row filter ``filters`` (column -> code
    prefixes, combined by ``join``: "all" or "any") can keep: path -> (the store's directory, or None for the lake; the
    entry). A file the lake holds whole at its listed version is held for any filter, and for none; a file of the
    store when its predicate covers the filter (`Predicate.covers`) at its listed version. ``paths``: only these."""
    out: dict[str, tuple[Path | None, dict[str, Any]]] = {
        p: (None, {"store": "lake", "sha256": sha, "files": [str(x) for x in parts]})
        for p, (sha, parts) in _whole(settings, dataset, paths).items()}
    asked = {c: v for c, v in (filters or {}).items() if v}
    if not asked:
        return out
    store = ExtractStore(settings.lake_dir, dataset)
    only = set(paths) if paths is not None else None
    holdings = {p: h for p, h in store.holdings().items() if p not in out and h.predicate.covers(asked, join)
                and (only is None or p in only)}
    void = _stale(settings, holdings)
    for p, h in holdings.items():
        if p not in void:
            out[p] = (store.root, {**h.entry(), "store": "extract"})
    return out


def where_held(rows: Mapping[str, Sequence[str]] | None, join: str, files: Sequence[str | Path]) -> Any:
    """A row filter as a scan predicate over lake partition ``files``, on the columns they hold: under "all" a column
    no file holds keeps no row; under "any" it keeps none of its own. None: no filter. The read's finishing filter is
    applied after it all the same."""
    from ._query_engine.request import rows_expression

    asked = {str(c).upper(): v for c, v in (rows or {}).items() if v}
    if not asked:
        return None
    names: set[str] = set()
    for f in files:
        names |= {n.upper() for n in pq.read_schema(f).names}
    present = {c: v for c, v in asked.items() if c in names}
    if not present or (join == "all" and len(present) < len(asked)):
        return pc.scalar(False)
    return rows_expression(present, join)


def lake_rows(path: str, entry: Mapping[str, Any], where: Any = None, record_key: bool = True) -> pa.Table:
    """The lake's rows of the published file ``path`` (a `held_files` entry of the lake) in the form a read of the file
    gives: what the build adds dropped, the record key computed (`retrieve._version_outcome`). ``where``: a scan
    predicate pushed into the read (`where_held`)."""
    from .persist.versions import source_rows

    return _read_form(source_rows([Path(x) for x in entry["files"]], path, str(entry["sha256"]), where=where),
                      record_key)


def _read_form(table: pa.Table, record_key: bool = True) -> pa.Table:
    from .normalize.engine import record_keys

    table = table.drop_columns([c for c in ("_competencia", "_source_resolution", "_record_key")
                                if c in table.column_names])
    if not table.num_rows or not record_key:
        return table
    return pa.Table.from_batches([b.append_column("_record_key", record_keys(b))
                                  for b in table.to_batches(max_chunksize=131_072)])


def _lake_tables(entries: Mapping[str, Mapping[str, Any]], rows: Mapping[str, Sequence[str]],
                 join: str = "all") -> dict[str, pa.Table]:
    """`lake_rows` of many files, each set of partition files read once for all the files it holds."""
    from .persist.versions import sources_rows

    groups: dict[tuple[str, ...], dict[str, str]] = {}
    for path, entry in entries.items():
        groups.setdefault(tuple(sorted(entry["files"])), {})[path] = str(entry["sha256"])
    out: dict[str, pa.Table] = {}
    for files, digests in groups.items():
        table = sources_rows([Path(f) for f in files], digests, where_held(rows, join, files))
        if not table.num_rows:
            continue
        source = pc.cast(table.column("_source_path"), pa.string())
        for path in digests:
            own = table.filter(pc.equal(source, path))
            if own.num_rows:
                out[path] = _read_form(own)
    return out


def held_rows(directory: Path | None, path: str, entry: Mapping[str, Any],
              rows: Mapping[str, Sequence[str]] | None = None, join: str = "all",
              record_key: bool = True) -> pa.Table | None:
    """The held records of the published file ``path``, from a `held_files` item (None: it holds none). ``rows``: the
    row filter, pushed into a read of the lake (the store's rows of a file are few and come whole). ``record_key``:
    the lake's rows with their key computed (the store's carry it)."""
    if entry.get("store") == "lake" or directory is None:
        table = lake_rows(path, entry, where_held(rows, join, entry["files"]), record_key=record_key)
        return table if table.num_rows else None
    store = ExtractStore(directory.parent.parent, directory.name.replace("-", ".", 1))
    holding = store.holdings(path).get(path)
    return store.read(holding) if holding is not None else None


def extract_table(dataset: str, column: str, codes: Sequence[str], years: Sequence[int] | None = None, *,
                  ufs: Sequence[str] | None = None, root: str | Path | None = None,
                  settings: Any = None) -> tuple[pa.Table, dict[str, Any]]:
    """The records of ``dataset`` whose ``column`` starts with one of ``codes``, for ``years``, from what the home holds:
    the store's rows where a file's predicate implies the codes, the lake's where it holds the file whole; with the
    manifest (`_manifest`). LookupError when a file of a year is held neither way (failed, or not read). ``years``
    None: the years the store holds the codes of. ``ufs``: only those states, as `build_extract` takes them (the
    manifest says so, ``served_ufs``)."""
    from .config import load_settings

    settings = settings or load_settings(root=Path(root) if root else None)
    filt = _filters({column: codes})
    asked = filt[column.upper()]
    store = ExtractStore(settings.lake_dir, dataset)
    pred = Predicate.of(filt)
    holdings = store.holdings()
    if years is None:
        years = sorted({h.year for h in holdings.values() if pred.implies(h.predicate)})
        if not years:
            raise LookupError(f"{dataset}: no extract with a filter on {column.upper()} covers {asked}")
    manifest = _manifest(settings, dataset, filt, years, ufs)
    if manifest["failed"] or manifest["unheld"]:
        raise LookupError(f"{dataset} {column.upper()} {asked}: {list(years)} not held whole ("
                          f"{len(manifest['unheld'])} files held neither by the lake nor by the extract store, "
                          f"{len(manifest['failed'])} failed)")
    from .persist.held import with_year

    entries = manifest["files"]
    lake = _lake_tables({p: e for p, e in entries.items() if e["store"] == "lake"}, filt)
    pieces = []
    # in the order the extract folders gave: by year, then state, then period
    for path, entry in sorted(entries.items(), key=lambda kv: (kv[1]["year"], kv[1]["uf"], str(kv[1]["period"]), kv[0])):
        t = with_year(lake[path], entry["year"]) if path in lake else (
            store.read(holdings[path]) if entry["store"] == "extract" else None)
        if t is not None and t.num_rows:
            pieces.append(t)
    table = pa.concat_tables(pieces, promote_options="default") if pieces else pa.table({})
    if table.num_rows:
        table = table.filter(pred.mask(table))
    if ufs:
        manifest = {**manifest, "served_ufs": sorted(set(ufs))}
    return table, manifest


def absorb(dataset: str, paths: Sequence[str] | None = None, *, settings: Any = None, verify: bool = True,
           dry_run: bool = False, log: Callable[[str], None] = print) -> dict[str, Any]:
    """Drop the store's rows of the files the lake now holds whole at the same digest (``paths``: only those). With
    ``verify``, a file's rows are dropped only when the lake's rows of it that its held predicate keeps are the
    store's: the same ``_row`` set. Returns what was (``dry_run``: would be) dropped and what was kept apart, why."""
    from .config import load_settings

    settings = settings or load_settings()
    store = ExtractStore(settings.lake_dir, dataset)
    holdings = store.holdings()
    if paths is not None:
        holdings = {p: h for p, h in holdings.items() if p in set(paths)}
    whole = _whole(settings, dataset, sorted(holdings))
    out: dict[str, Any] = {"dropped": 0, "rows": 0, "bytes": 0, "kept_apart": {}}
    candidates = []
    for p, h in sorted(holdings.items()):
        if p not in whole:
            continue
        if h.sha256 and h.sha256 != whole[p][0]:
            out["kept_apart"][p] = f"the store holds version {h.sha256[:12]}, the lake {whole[p][0][:12]}"
            continue
        candidates.append((p, h))
    lake = _lake_row_ids(whole, [(p, h.predicate) for p, h in candidates]) if verify else {}
    for p, h in candidates:
        if verify:
            mine = store.read(h)
            a = sorted(mine.column("_row").to_pylist()) if mine is not None else []
            if lake.get((p, h.predicate)) != a:
                out["kept_apart"][p] = f"the lake's rows for {h.predicate} are not the store's {h.kept}"
                continue
        out["dropped"] += 1
        out["rows"] += h.kept
        out["bytes"] += h.bytes if dry_run else store.drop(p)
    if out["dropped"] or out["kept_apart"]:
        log(f"absorb {dataset}: {out['dropped']} files ({out['rows']:,} rows, {out['bytes'] / 1e6:.0f} MB) "
            f"{'would be ' if dry_run else ''}dropped, the lake holds them whole; {len(out['kept_apart'])} kept apart")
    return out


def absorb_landed(settings: Any, paths: Sequence[str], log: Callable[[str], None] = print) -> dict[str, Any]:
    """`absorb` the files a lake build just wrote, in every dataset's store that holds any of them."""
    base = Path(settings.lake_dir) / "extracts"
    out = {}
    wanted = set(paths)
    for d in sorted(base.iterdir()) if base.exists() else []:
        store = ExtractStore(settings.lake_dir, d.name)
        if store.exists() and (mine := sorted(wanted & set(store.holdings()))):
            out[d.name] = absorb(d.name, mine, settings=settings, log=log)
    return out


def _lake_row_ids(whole: Mapping[str, tuple[str, list[Path]]],
                  wanted: Sequence[tuple[str, Predicate]]) -> dict[tuple[str, Predicate], list[int]]:
    """``(path, predicate) -> the sorted ``_row`` of the lake's rows of the file that the predicate keeps``, for files
    the lake holds whole (``whole``, `_whole`): each partition read once, for every file of it and their predicates,
    on the provenance and the predicates' columns only."""
    import pyarrow.dataset as pads

    from ._query_engine.request import rows_expression

    groups: dict[tuple[str, ...], list[tuple[str, Predicate]]] = {}
    for path, pred in wanted:
        groups.setdefault(tuple(sorted(str(f) for f in whole[path][1])), []).append((path, pred))
    out: dict[tuple[str, Predicate], list[int]] = {}
    for files, items in groups.items():
        union = Predicate(frozenset())
        for _p, pred in items:
            union = union.union(pred)
        paths = sorted({p for p, _pr in items})
        cols = sorted({c for c, _ in union.atoms or ()})
        pieces = []
        for f in files:
            names = {x.upper(): x for x in pq.read_schema(f).names}
            present = {c: v for c, v in union.filters().items() if c in names}
            test = pads.field("_source_path").isin(paths)
            if union.atoms is not None:
                test = test & (rows_expression(present, "any") if present else pc.scalar(False))
            pieces.append(pads.dataset(f, format="parquet").to_table(
                columns=["_source_path", "_row", *[names[c] for c in cols if c in names]], filter=test))
        lake = pa.concat_tables(pieces, promote_options="permissive")
        source = pc.cast(lake.column("_source_path"), pa.string())
        for path, pred in items:
            own = lake.filter(pc.equal(source, path))
            out[(path, pred)] = sorted(own.filter(pred.mask(own)).column("_row").to_pylist()) if own.num_rows else []
    return out


def migrate_extracts(dataset: str, *, settings: Any = None, apply: bool = False, remove: bool = False,
                     folders: Sequence[str] | None = None, verify: bool = True,
                     log: Callable[[str], None] = print) -> dict[str, Any]:
    """Fold the per-filter extract folders of ``dataset`` (``<store>/<digest>/manifest.json``, before ADR-0236) into
    its store. Each legacy file entry is a holding of its folder's filters at the digest its rows carry:
    - a file the lake holds whole at that digest is absorbed: with ``verify``, only when the lake's rows of it that
      the folder's filters keep are the folder's, the same ``_row`` set (one scan of each partition for all files);
    - any other adds to the store only the rows its holding lacks (``legacy AND NOT held``), its predicate widened;
    - a failed or unrecorded file adds nothing.
    Without ``apply`` nothing is written and the plan is returned (folders, files and rows each way). ``apply``
    writes the carried rows to the store and deletes nothing; ``remove`` (with ``apply``) then deletes each folder all
    of whose files were absorbed or carried, none mismatched. ``folders``: only these digests."""
    import shutil

    from .config import load_settings

    settings = settings or load_settings()
    store = ExtractStore(settings.lake_dir, dataset)
    legacy = sorted(d for d in store.root.iterdir() if (d / "manifest.json").is_file()
                    and (folders is None or d.name in folders)) if store.root.exists() else []
    whole = _whole(settings, dataset)
    plan: dict[str, Any] = {"folders": {}, "absorbed": 0, "carried": 0, "carried_rows": 0, "absorbed_rows": 0,
                            "mismatch": {}}

    def part_rows(d: Path, path: str, entry: Mapping[str, Any], columns: Sequence[str] | None = None) -> pa.Table | None:
        if not int(entry.get("kept") or 0):
            return None
        rows = pq.read_table(d / f"year={int(entry['year'])}" / f"{entry['uf']}_{entry['period']}.parquet",
                             columns=list(columns) if columns else None)
        source = pc.cast(rows.column("_source_path"), pa.string())
        return rows.filter(pc.fill_null(pc.or_(pc.equal(source, path), pc.starts_with(source, path + "!")), False))

    # 1. sort every file of every folder: absorbed by the lake (to verify) or carried into the store
    absorb_: list[tuple[str, str, Predicate, list[int]]] = []     # folder, path, predicate, the folder's _row set
    carry: list[tuple[Path, str, dict[str, Any], Predicate]] = []
    manifests = {}
    for d in legacy:
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        manifests[d.name] = m
        pred = Predicate.of(m.get("filters") or {})
        failed = set(m.get("failed") or ())
        plan["folders"][d.name] = {"filters": str(pred), "files": len(m.get("files") or {}), "failed": len(failed),
                                   "bytes": sum(p.stat().st_size for p in d.rglob("*.parquet")),
                                   "absorbed": 0, "absorbed_rows": 0, "carried": 0, "carried_rows": 0}
        for path, entry in sorted((m.get("files") or {}).items()):
            if path in failed:
                continue
            if path in whole:
                ids = part_rows(d, path, entry, ["_source_path", "_row", "_blob_sha256"])
                shas = set(pc.cast(ids.column("_blob_sha256"), pa.string()).to_pylist()) if ids is not None else set()
                if shas <= {whole[path][0]}:
                    absorb_.append((d.name, path, pred, sorted(ids.column("_row").to_pylist()) if ids else []))
                    continue
            carry.append((d, path, entry, pred))

    # 2. verify the absorbed: each lake partition read once, for every file and folder it holds
    lake = _lake_row_ids(whole, [(p, pred) for _f, p, pred, _r in absorb_]) if verify else {}
    for folder, path, pred, mine in absorb_:
        if verify and lake[(path, pred)] != mine:
            plan["mismatch"][path] = (f"{folder}: the lake holds {len(lake[(path, pred)])} rows for {pred}, "
                                      f"the extract {len(mine)}")
            continue
        plan["folders"][folder]["absorbed"] += 1
        plan["folders"][folder]["absorbed_rows"] += len(mine)

    # 3. carry the rest: each file adds the rows its holding lacks
    held: dict[str, Predicate] = {p: h.predicate for p, h in store.holdings().items()}
    versions: dict[str, str | None] = {p: h.sha256 for p, h in store.holdings().items()}
    for d, path, entry, pred in carry:
        mine = held.get(path)
        row = plan["folders"][d.name]
        add = part_rows(d, path, entry)
        if (add.num_rows if add is not None else 0) != int(entry.get("kept") or 0):
            # the folder lost rows of this file: its part was named by state and period, and the files DATASUS splits
            # (SIA-PA's PASP2301a, b, c) wrote one part over another. Not carried: the file is read again.
            plan.setdefault("short", {})[path] = (f"{d.name}: {entry.get('kept')} rows recorded, "
                                                  f"{add.num_rows if add is not None else 0} in its part")
            continue
        sha = None
        if add is not None and add.num_rows:
            shas = pc.unique(pc.cast(add.column("_blob_sha256"), pa.string())).to_pylist()
            sha = shas[0] if len(shas) == 1 else None
        if sha and versions.get(path) and versions[path] != sha:
            plan["mismatch"][path] = f"{d.name}: version {sha[:12]}, another folder's {str(versions[path])[:12]}"
            continue
        row["carried"] += 1
        if mine is not None and pred.implies(mine):
            continue
        if add is not None and mine is not None:
            add = add.filter(pc.invert(mine.mask(add)))
        row["carried_rows"] += add.num_rows if add is not None else 0
        held[path] = mine.union(pred) if mine is not None else pred
        versions[path] = versions.get(path) or sha
        if apply:
            store.add(path=path, year=int(entry["year"]), uf=str(entry["uf"]), period=str(entry["period"]),
                      sha256=sha or _fetched_digest(settings, path), predicate=pred,
                      rows=int(entry.get("rows") or 0), table=add)

    for name, row in plan["folders"].items():
        plan["absorbed"] += row["absorbed"]
        plan["absorbed_rows"] += row["absorbed_rows"]
        plan["carried"] += row["carried"]
        plan["carried_rows"] += row["carried_rows"]
        clean = not any(v.startswith(f"{name}:") for v in plan["mismatch"].values())
        done = row["absorbed"] + row["carried"] == row["files"] - row["failed"]
        log(f"migrate {dataset} {name} ({row['filters']}): {row['files']} files, {row['absorbed']} absorbed by the lake "
            f"({row['absorbed_rows']:,} rows), {row['carried']} carried ({row['carried_rows']:,} rows added), "
            f"{row['bytes'] / 1e6:.0f} MB{'' if clean else ', MISMATCHED'}")
        if apply and remove and clean and done:
            shutil.rmtree(store.root / name)
            row["removed"] = True
    return plan
