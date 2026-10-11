"""Filtered extracts: every record of a dataset whose code columns hold declared codes, read file by file.

Some datasets are larger than the lake can hold (SIA-PA 2010-2025 is about 190 GB of DBC files, SIA-BI 156 GB; the disk
has under 180 GB free), while a study needs a few procedures of them (toxoplasma serology). An extract streams the
dataset's published files one at a time: fetch, decode, keep the records any of whose ``filters`` (column -> code
prefixes) matches, whole, write them, and release the file's blob unless a snapshot keeps it. Several
filters are one pass (SIA-PA's serology procedures and its records coded B58 on PA_CIDPRI). Peak disk is one file; the
extract is each filter's complete records, never a sample.

An extract lives apart from the lake (``<lake>/extracts/<dataset>/<digest>/``): a query for other codes must never read
a filtered table as if it were the dataset. Its manifest names the filters, every file read with the rows read and
kept, and the files that failed, so a short extract is visibly short.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

__all__ = ["build_extract", "extract_dir", "extract_table"]


def _norm(code: str) -> str:
    return str(code).replace(".", "").strip().upper()


def _filters(filters: dict[str, Sequence[str]]) -> dict[str, list[str]]:
    return {str(c).upper(): sorted({_norm(x) for x in codes}) for c, codes in sorted(filters.items())}


def extract_dir(settings: Any, dataset: str, filters: dict[str, Sequence[str]]) -> Path:
    """Where the extract of ``dataset`` by ``filters`` (column -> code prefixes) is kept."""
    from ._request import parse_dataset

    system, series = parse_dataset(dataset)
    digest = hashlib.sha256(json.dumps(_filters(filters)).encode()).hexdigest()[:12]
    return Path(settings.lake_dir) / "extracts" / f"{system}-{series or system}" / digest


def _files(settings: Any, dataset: str, years: Sequence[int], ufs: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """The dataset's published data files of ``years`` (the catalog's file facts): path, state, year, period."""
    from ._request import parse_dataset
    from .catalog.store import CatalogStore

    system, series = parse_dataset(dataset)
    store = CatalogStore(settings.catalog_path)
    try:
        marks = ",".join("?" for _ in years)
        rows = store.query(
            f"""SELECT ff.path, ff.geo_code, ff.year, ff.normalized_date FROM file_facts ff JOIN files f ON f.path = ff.path
                WHERE ff.system = ? AND ff.series_prefix = ? AND ff.role = 'data' AND f.gone_at IS NULL
                AND ff.year IN ({marks}) ORDER BY ff.year, ff.normalized_date, ff.geo_code""",
            [system, series or system, *map(int, years)])
        return [dict(r) for r in rows if not ufs or r["geo_code"] in set(ufs)]
    finally:
        store.close()


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


def _match(table: pa.Table, column: str, prefixes: Sequence[str]) -> pa.Array | None:
    """The rows whose ``column`` starts with one of ``prefixes`` (None: the table has no such column)."""
    col = next((c for c in table.column_names if c.upper() == column), None)
    if col is None:
        return None
    text = pc.utf8_upper(pc.cast(table.column(col), pa.string()))
    mask = None
    for p in prefixes:
        hit = pc.fill_null(pc.starts_with(text, p), False)
        mask = hit if mask is None else pc.or_(mask, hit)
    return mask


#: files fetched at once, each over its own FTP connection (the fetcher's tested limit is 8): the server gives about
#: 0.5 MB/s a connection (2026-10-11); decoding waits for memory in pegasus_data's admission control, and a worker
#: hands back only its file's kept records
EXTRACT_WORKERS = 6


def build_extract(dataset: str, years: Sequence[int], filters: dict[str, Sequence[str]], *,
                  ufs: Sequence[str] | None = None, root: str | Path | None = None, settings: Any = None,
                  log: Callable[[str], None] = print, workers: int = EXTRACT_WORKERS) -> dict[str, Any]:
    """Extract the records of ``dataset`` in ``years`` that any of ``filters`` (column -> code prefixes) matches, file
    by file (module docstring), ``workers`` files at a time. A file already in the manifest is not read again, so an
    interrupted extract resumes. Returns the manifest. ``ufs`` reads only those states' files (an extract that is not
    whole says so when read)."""
    from concurrent.futures import ThreadPoolExecutor

    from .config import load_settings
    from .retrieve import fetch

    settings = settings or load_settings(root=Path(root) if root else None)
    filt = _filters(filters)
    target = extract_dir(settings, dataset, filt)
    target.mkdir(parents=True, exist_ok=True)
    mpath = target / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {
        "dataset": dataset, "filters": filt, "files": {}, "failed": {}}
    files = _files(settings, dataset, years, ufs)
    todo = [f for f in files if f["path"] not in manifest["files"]]
    log(f"extract {dataset} {filt}: {len(files)} files in {sorted(set(map(int, years)))}, {len(todo)} to read")
    t0 = time.time()

    def read(f: dict[str, Any]) -> tuple[dict[str, Any], Any, int, Any]:
        """One file fetched, decoded and filtered in the worker: only its kept records wait for their turn."""
        try:
            table, report = fetch(dataset, labels=False, provenance=True, _only_paths=[f["path"]], report=True,
                                  max_bytes=None, settings=settings, on_missing_column="null_fill")
        except Exception as exc:  # noqa: BLE001 - a file that does not open is a recorded gap, not an absence
            return f, exc, 0, None
        mask = None
        for column, prefixes in filt.items():
            hit = _match(table, column, prefixes)          # a layout without the column holds none of its records
            if hit is not None:
                mask = hit if mask is None else pc.or_(mask, hit)
        return f, (table.filter(mask) if mask is not None else table.slice(0, 0)), table.num_rows, report

    pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="extract")

    def results():
        # at most ``workers`` files in flight, taken in order: a slow month never lets decoded ones pile up behind it
        from collections import deque

        window: deque = deque()
        for f in todo:
            window.append(pool.submit(read, f))
            if len(window) >= max(1, workers):
                yield window.popleft().result()
        while window:
            yield window.popleft().result()

    for i, (f, kept, rows, report) in enumerate(results()):
        if isinstance(kept, Exception):
            manifest["failed"][f["path"]] = f"{type(kept).__name__}: {kept}"[:300]
            log(f"extract {dataset}: {f['path']} failed: {type(kept).__name__}: {kept}")
            continue
        if kept.num_rows:
            part = target / f"year={int(f['year'])}" / f"{f['geo_code']}_{f['normalized_date']}.parquet"
            part.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(kept, part, compression="zstd")
        manifest["files"][f["path"]] = {"year": int(f["year"]), "uf": f["geo_code"], "period": f["normalized_date"],
                                        "rows": rows, "kept": kept.num_rows,
                                        "downloaded": int(getattr(report, "bytes_downloaded", 0) or 0)}
        _release(settings, [f["path"]])
        if (i + 1) % 25 == 0 or i + 1 == len(todo):
            mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
            done = sum(v["rows"] for v in manifest["files"].values())
            log(f"extract {dataset}: {i + 1}/{len(todo)} files, {done:,} rows read, "
                f"{sum(v['kept'] for v in manifest['files'].values()):,} kept, {time.time() - t0:.0f} s")
    pool.shutdown()
    mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def extract_table(dataset: str, column: str, codes: Sequence[str], years: Sequence[int] | None = None, *,
                  root: str | Path | None = None, settings: Any = None) -> tuple[pa.Table, dict[str, Any]]:
    """The records of ``dataset`` whose ``column`` starts with one of ``codes``, for ``years``, from an extract with a
    filter on ``column`` whose prefixes cover every asked code; with its manifest. LookupError when no extract covers
    them or a year is not read whole (a failed file, or a file of the year not yet read)."""
    from ._request import parse_dataset
    from .config import load_settings

    settings = settings or load_settings(root=Path(root) if root else None)
    asked = sorted({_norm(c) for c in codes})
    column = column.upper()
    system, series = parse_dataset(dataset)
    base = Path(settings.lake_dir) / "extracts" / f"{system}-{series or system}"
    for d in sorted(base.iterdir()) if base.exists() else []:
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8")) if (d / "manifest.json").exists() else None
        held = ((m or {}).get("filters") or {}).get(column)
        if not held or not all(any(a.startswith(p) for p in held) for a in asked):
            continue
        read = {int(v["year"]) for v in m["files"].values()}
        want = sorted(set(map(int, years))) if years else sorted(read)
        unread = [f["path"] for f in _files(settings, dataset, want) if f["path"] not in m["files"]]
        if unread or m["failed"]:
            raise LookupError(f"{dataset} {column} {asked}: the extract does not hold {want} whole "
                              f"({len(unread)} files unread, {len(m['failed'])} failed)")
        parts = [p for y in want for p in sorted((d / f"year={y}").glob("*.parquet"))]
        table = pa.concat_tables([pq.read_table(p) for p in parts], promote_options="default") if parts else pa.table({})
        if table.num_rows:
            mask = _match(table, column, asked)
            table = table.filter(mask) if mask is not None else table.slice(0, 0)
        return table, m
    raise LookupError(f"{dataset}: no extract with a filter on {column} covers {asked}")
