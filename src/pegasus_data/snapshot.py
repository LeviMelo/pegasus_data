"""Snapshots: the versions of files DATASUS rewrites in place (ADR-0141).

A preliminary or current-year file is overwritten under the same name, so the
server keeps one state and the history exists only if someone fetched each state
while it was current. ``snapshot()`` is that someone:

1. list again the directories of the declared series (``curation/snapshots.yml``)
   with the crawler, over one connection;
2. judge each declared file against its latest version by the listed size and
   modification time, and fetch only the ones that differ, over one connection,
   from DATASUS alone (never the mirror, which can lag);
3. record each version in ``snapshot_versions`` and build it into the lake: its
   partition takes the new version and keeps the one it replaces as a delta
   (`persist.versions`, ADR-0234); the download is then released. The lake is the
   only stored form of every version.

``versions()`` lists what was kept of a path. ``digests_as_of()`` answers which
version a date saw, and is what ``query(..., as_of=)`` reads, from the lake.
"""

from __future__ import annotations

import re
import shutil
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from .acquire.cache import BlobStore
from .acquire.fetcher import MIRROR_HOST, MIRROR_PREFIX, Fetcher
from .catalog.store import CatalogStore, utcnow
from .config import Settings, curation_root, load_settings
from .discovery.crawler import Crawler
from .discovery.ftp_client import FtpClient
from .discovery.listing import normalize_path
from .normalize.time import add_months, compose

#: Free RAM a run needs before it opens a connection (the machine is shared).
MIN_AVAILABLE_RAM = 4 * 2**30
#: Free disk to leave after the run's downloads.
MIN_FREE_DISK = 10 * 2**30
#: One run refuses to take more new bytes than this unless told otherwise.
DEFAULT_MAX_BYTES = 5 * 2**30


class SnapshotRefused(RuntimeError):
    """The run was not started: memory, disk or the byte budget said no."""


@dataclass(slots=True)
class SeriesReport:
    declared: int = 0
    unchanged: int = 0
    adopted: int = 0
    to_fetch: int = 0
    fetched: int = 0
    failed: int = 0
    bytes_fetched: int = 0
    bytes_to_fetch: int = 0


@dataclass(slots=True)
class SnapshotReport:
    run_id: str
    started_at: str
    dry_run: bool = False
    finished_at: str = ""
    series: dict[str, SeriesReport] = field(default_factory=dict)
    directories_listed: int = 0
    #: ``listing`` (LIST of each directory) or ``stat`` (MDTM and SIZE per file).
    observed_by: str = ""
    listing_failures: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    seconds: float = 0.0
    #: Bytes this run pulled from DATASUS (zero when nothing changed).
    bytes_downloaded: int = 0
    #: The whole kept history: versions named by ``snapshot_versions``.
    versions_total: int = 0
    #: What is stored of them: the downloads not yet landed, and the deltas in the lake.
    store_bytes: int = 0
    delta_bytes: int = 0
    #: The build of this run's versions into the lake (`build.land`): partitions, versions kept, downloads released.
    landed: dict[str, Any] = field(default_factory=dict)
    disk_free: int = 0

    def totals(self) -> SeriesReport:
        out = SeriesReport()
        for item in self.series.values():
            for name in out.__slots__:
                setattr(out, name, getattr(out, name) + getattr(item, name))
        return out

    def as_dict(self) -> dict[str, Any]:
        totals = self.totals()
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "dry_run": self.dry_run,
            "seconds": round(self.seconds, 1),
            "observed_by": self.observed_by,
            "directories_listed": self.directories_listed,
            "declared_files": totals.declared,
            "unchanged": totals.unchanged,
            "adopted_from_cache": totals.adopted,
            "to_fetch" if self.dry_run else "fetched": totals.to_fetch if self.dry_run else totals.fetched,
            "failed": totals.failed,
            "bytes_to_fetch" if self.dry_run else "bytes_downloaded": (
                totals.bytes_to_fetch if self.dry_run else self.bytes_downloaded
            ),
            "versions_kept": self.versions_total,
            "store_bytes": self.store_bytes,
            "delta_bytes": self.delta_bytes,
            "landed": self.landed,
            "disk_free": self.disk_free,
            "listing_failures": self.listing_failures,
            "errors": self.errors,
            "series": {name: {k: getattr(v, k) for k in v.__slots__} for name, v in self.series.items()},
        }


# ------------------------------------------------------------------ declaration


def declared_series(only: Sequence[str] | None = None) -> dict[str, dict[str, Any]]:
    """``curation/snapshots.yml``, optionally narrowed to the named series."""
    from .semantics.curation import read_yaml

    series = dict((read_yaml(curation_root() / "snapshots.yml", missing_ok=True) or {}).get("snapshots") or {})
    if only:
        unknown = [name for name in only if name not in series]
        if unknown:
            raise ValueError(f"no declared snapshot series {unknown}; declared: {sorted(series)}")
        series = {name: series[name] for name in only}
    return series


def _competence_floor(months: int, today: date) -> int:
    """The oldest competence (YYYYMM) kept: ``months`` back from ``today``."""
    return add_months(cast(int, compose(today.year, today.month)), -months)


def _keeps(spec: Mapping[str, Any], filename: str, today: date) -> bool:
    """Does a series keep this filename (pattern, states, competence window)?"""
    if not spec.get("pattern"):
        return True
    match = re.compile(str(spec["pattern"]), re.I).match(filename)
    if not match:
        return False
    groups = match.groupdict()
    ufs = {str(u).upper() for u in spec.get("ufs") or ()}
    if ufs and str(groups.get("uf") or "").upper() not in ufs:
        return False
    if spec.get("months") and groups.get("yy") and groups.get("mm"):
        floor = _competence_floor(int(spec["months"]), today)
        filed = compose(2000 + int(groups["yy"]), groups["mm"])
        if filed is not None and filed < floor:       # a name whose month is no month is not dated: kept
            return False
    return True


def _declared_files(
    catalog: CatalogStore, spec: Mapping[str, Any], base: str, today: date
) -> list[tuple[str, int | None, str]]:
    """(path, size, modified) of the files a series keeps, from the observed state."""
    out: list[tuple[str, int | None, str]] = []
    for directory in spec["directories"]:
        rows = catalog.query(
            "SELECT path, filename, size, modified FROM files WHERE directory = ? AND gone_at IS NULL",
            (f"{base.rstrip('/')}/{directory.strip('/')}",),
        )
        out += [
            (str(r["path"]), r["size"], str(r["modified"] or ""))
            for r in rows if _keeps(spec, str(r["filename"]), today)
        ]
    return sorted(out)


def _mirror_names(directory: str, host: str, prefix: str) -> set[str]:
    """Filenames the S3 mirror holds under a directory (names only: its dates are its own)."""
    from .transport import get_text

    names: set[str] = set()
    key = directory[len(prefix):].strip("/") + "/"
    marker = ""
    while True:
        text = get_text(f"https://{host}/", params={"prefix": key, "marker": marker, "delimiter": "/"}, timeout=60)
        keys = re.findall(r"<Key>([^<]+)</Key>", text)
        names |= {k[len(key):] for k in keys if "/" not in k[len(key):]}
        if "<IsTruncated>true</IsTruncated>" not in text or not keys:
            return names
        marker = keys[-1]


def _extension(name: str) -> str | None:
    return name.rsplit(".", 1)[1].lower() if "." in name else None


def _observe_by_stat(
    catalog: CatalogStore, resolved: Settings, series: Mapping[str, Mapping[str, Any]], base: str, today: date,
    say: Callable[[str], None],
) -> int:
    """The state of the declared files from FTP's control channel alone.

    For when the data channel (every directory listing and every transfer) does
    not answer, as from 2026-10-03 (ADR-0122). MDTM and SIZE still do, so the
    names come from the catalog and the mirror's key list and the DATASUS server
    itself is asked for each one's time and size; a name it does not know is not
    on DATASUS and is dropped.
    """
    client = FtpClient(resolved.host, timeout=resolved.timeout, max_retries=resolved.max_retries,
                       backoff_base=resolved.backoff_base).connect()
    asked = 0
    try:
        for spec in series.values():
            for directory in spec["directories"]:
                full = f"{base}/{directory.strip('/')}"
                known = {
                    str(r["filename"]): (r["size"], r["modified"])
                    for r in catalog.query(
                        "SELECT filename, size, modified FROM files WHERE directory = ? AND gone_at IS NULL", (full,))
                }
                try:
                    names = set(known) | _mirror_names(full, MIRROR_HOST, MIRROR_PREFIX)
                except Exception as exc:  # noqa: BLE001 - the catalog's names still stand
                    say(f"mirror key list unavailable for {full}: {exc}")
                    names = set(known)
                rows = []
                for name in sorted(n for n in names if _keeps(spec, n, today)):
                    path = normalize_path(f"{full}/{name}")
                    modified = client.modified_time(path)
                    asked += 1
                    if modified is None:
                        continue  # not on DATASUS (a mirror-only name) or unanswered
                    before = known.get(name)
                    size = before[0] if before and before[1] == modified and before[0] is not None else client.size(path)
                    rows.append({
                        "path": path, "directory": full, "filename": name, "extension": _extension(name),
                        "size": size, "modified": modified, "listing_method": "stat", "change_signal": "mtime",
                    })
                catalog.upsert_files(rows)
    finally:
        client.close()
    return asked


def _data_channel_up(resolved: Settings, directory: str) -> bool:
    """Does one directory listing answer within 20 seconds?"""
    client = FtpClient(resolved.host, timeout=20, max_retries=1)
    try:
        client.connect()
        client.list_directory(directory, ladder=("list",))
        return True
    except Exception:  # noqa: BLE001 - any failure here means the listing path is not usable
        return False
    finally:
        client.close()


def _mirror_matches(
    queue: list[tuple[str, str, int | None, str]], resolved: Settings, report: SnapshotReport
) -> list[tuple[str, str, int | None, str]]:
    """The queued files whose mirror copy is the state DATASUS reports.

    The mirror stores each file's original FTP modification time (``x-amz-meta-mtime``).
    A copy is taken as the DATASUS version only when its size and that time both
    equal what the DATASUS server answered; otherwise the mirror holds another
    state and the file waits for a run that can see it.
    """
    import httpx

    from .discovery.https_client import HttpsClient

    kept: list[tuple[str, str, int | None, str]] = []
    with HttpsClient(MIRROR_HOST, timeout=resolved.timeout, strip_prefix=MIRROR_PREFIX) as mirror:
        for name, path, size, modified in queue:
            part = report.series[name]
            try:
                url = mirror.url(path) or ""
                head = mirror._client.head(url)
                head.raise_for_status()
                length = int(head.headers.get("content-length", -1))
                stamp = head.headers.get("x-amz-meta-mtime")
                theirs = datetime.fromtimestamp(int(stamp), UTC).isoformat() if stamp else None
            except (httpx.HTTPError, ValueError) as exc:
                part.failed += 1
                report.errors.append((path, f"mirror HEAD: {exc}"))
                continue
            if length != size or theirs != modified:
                part.failed += 1
                report.errors.append((
                    path, f"mirror holds another state (size {length}, time {theirs}); DATASUS: {size}, {modified}"))
                continue
            kept.append((name, path, size, modified))
    return kept


# ------------------------------------------------------------------- the run


def snapshot(
    settings: Settings | None = None,
    *,
    only: Sequence[str] | None = None,
    dry_run: bool = False,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
    root: str | Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> SnapshotReport:
    """List the declared series again and keep every changed file as a version.

    ``dry_run`` lists (which refreshes the catalog's view of those directories)
    and reports what would be fetched, in files and bytes, without fetching.
    Raises :class:`SnapshotRefused` before any download when free memory is
    under 4 GiB, the run would leave under 10 GiB of disk, or the new bytes
    exceed ``max_bytes`` (``None`` for no limit).
    """
    import time

    import psutil

    started = time.monotonic()
    resolved = settings or load_settings(root=Path(root) if root else None)
    resolved.ensure_dirs()
    series = declared_series(only)
    catalog = CatalogStore(resolved.catalog_path)
    blobs = BlobStore(resolved.blobs_dir, catalog)
    report = SnapshotReport(run_id=uuid.uuid4().hex[:12], started_at=utcnow(), dry_run=dry_run)
    say = on_progress or (lambda _msg: None)
    try:
        base = resolved.base_path.rstrip("/")
        directories = list(dict.fromkeys(
            f"{base}/{d.strip('/')}" for spec in series.values() for d in spec["directories"]
        ))
        today = datetime.now(UTC).date()
        failed_dirs: set[str] = set()
        if _data_channel_up(resolved, directories[0]):
            say(f"listing {len(directories)} directories")
            Crawler(
                catalog, host=resolved.host, connections=1, timeout=resolved.timeout,
                max_retries=resolved.max_retries, backoff_base=resolved.backoff_base,
            ).crawl(base, only_prefixes=directories)
            report.observed_by = "listing"
            failed_dirs = {
                d for d in directories
                for gap in catalog.open_gaps("listing") if str(gap["path"]).startswith(d)
            }
        else:
            say("FTP data channel does not answer; asking DATASUS for each declared file's time and size")
            _observe_by_stat(catalog, resolved, series, base, today, say)
            report.observed_by = "stat"
        report.directories_listed = len(directories)
        report.listing_failures = sorted(failed_dirs)

        now = utcnow()
        #: the versions this run recorded, built into the lake at the end
        recorded: list[str] = []
        queue: list[tuple[str, str, int | None, str]] = []  # (series, path, size, modified)
        unchanged: list[tuple[str, str, str]] = []
        for name, spec in series.items():
            part = report.series.setdefault(name, SeriesReport())
            if any(f"{base}/{d.strip('/')}" in failed_dirs for d in spec["directories"]):
                report.errors.append((name, "listing failed; no file judged from a stale listing"))
                continue
            for path, size, modified in _declared_files(catalog, spec, base, today):
                part.declared += 1
                latest = _latest(catalog, path)
                if latest is not None and latest["modified"] == modified and (
                    size is None or latest["size"] is None or int(latest["size"]) == int(size)
                ):
                    part.unchanged += 1
                    unchanged.append((latest["sha256"], path, latest["modified"]))
                    continue
                digest = _already_fetched(catalog, blobs, path, size, modified)
                if digest:
                    _record_version(catalog, report.run_id, path, digest, size, modified, "adopted")
                    recorded.append(path)
                    part.adopted += 1
                    continue
                queue.append((name, path, size, modified))
                part.to_fetch += 1
                part.bytes_to_fetch += int(size or 0)
        if unchanged:
            with catalog.write() as conn:
                conn.executemany(
                    "UPDATE snapshot_versions SET last_observed_at = ?, observations = observations + 1, run_id = ? "
                    "WHERE sha256 = ? AND path = ? AND modified = ?",
                    [(now, report.run_id, sha, path, mod) for sha, path, mod in unchanged],
                )

        need = sum(int(size or 0) for _n, _p, size, _m in queue)
        if queue and not dry_run:
            available = psutil.virtual_memory().available
            if available < MIN_AVAILABLE_RAM:
                raise SnapshotRefused(
                    f"{available / 2**30:.1f} GiB of RAM available, {MIN_AVAILABLE_RAM / 2**30:.0f} GiB needed")
            free = shutil.disk_usage(resolved.blobs_dir).free
            if free - need < MIN_FREE_DISK:
                raise SnapshotRefused(
                    f"{need / 2**20:.0f} MiB to fetch would leave {(free - need) / 2**30:.1f} GiB free, "
                    f"under {MIN_FREE_DISK / 2**30:.0f} GiB")
            if max_bytes is not None and need > max_bytes:
                raise SnapshotRefused(
                    f"{need / 2**30:.2f} GiB to fetch is over max_bytes={max_bytes / 2**30:.2f} GiB; "
                    "narrow --only or raise the limit")
            say(f"fetching {len(queue)} files, {need / 2**20:.0f} MiB")
            fetcher = Fetcher(
                catalog, blobs, host=resolved.host, concurrency=1, timeout=resolved.timeout,
                max_retries=resolved.max_retries, backoff_base=resolved.backoff_base,
                stall_timeout=resolved.stall_timeout, heartbeat_interval=resolved.heartbeat_interval,
                mirror=report.observed_by == "stat",
            )
            if report.observed_by == "stat":
                # DATASUS cannot transfer; the mirror carries the bytes, but only
                # a copy that matches DATASUS's own size and time is the version.
                fetcher.mirror_first = True
                queue = _mirror_matches(queue, resolved, report)
            meta = {path: (name, size, modified) for name, path, size, modified in queue}

            def _kept(result: Any) -> None:
                name, size, modified = meta[result.path]
                part = report.series[name]
                if result.error or not result.sha256:
                    part.failed += 1
                    report.errors.append((result.path, result.error or "not fetched"))
                    return
                part.fetched += 1
                part.bytes_fetched += result.byte_size
                report.bytes_downloaded += result.byte_size
                served = catalog.query(
                    "SELECT serving_method FROM fetches WHERE source_path = ? AND sha256 = ? ORDER BY id DESC LIMIT 1",
                    (result.path, result.sha256))
                _record_version(catalog, report.run_id, result.path, result.sha256, size, modified,
                                str(served[0]["serving_method"]) if served else "")
                recorded.append(result.path)

            fetcher.fetch_many([p for _n, p, _s, _m in queue], force=True, on_result=_kept)
            for marker, reason in (fetcher.last_stats.diagnostics if fetcher.last_stats else ()):
                report.errors.append((marker, reason))
        elif queue:
            say(f"{len(queue)} files, {need / 2**20:.0f} MiB would be fetched")
        if recorded and not dry_run:
            say(f"building {len(recorded)} versions into the lake")
            report.landed = _land(resolved, recorded)

        report.versions_total = int(catalog.scalar("SELECT COUNT(*) FROM snapshot_versions") or 0)
        report.store_bytes = sum(
            blobs.path_for(str(r["sha256"])).stat().st_size
            for r in catalog.query("SELECT DISTINCT sha256 FROM snapshot_versions") if blobs.has(str(r["sha256"])))
        report.delta_bytes = int(catalog.scalar("SELECT COALESCE(SUM(byte_size), 0) FROM lake_versions") or 0)
        report.disk_free = shutil.disk_usage(resolved.blobs_dir).free
        report.finished_at = utcnow()
        report.seconds = time.monotonic() - started
        catalog.log_event(
            "snapshot",
            f"{'dry run' if dry_run else 'run'}: {report.totals().fetched} fetched, "
            f"{report.bytes_downloaded} bytes, {report.totals().unchanged} unchanged",
            run_id=report.run_id, detail=report.as_dict(),
        )
        return report
    finally:
        catalog.close()


def _land(resolved: Settings, paths: Sequence[str]) -> dict[str, Any]:
    """This run's versions built into the lake and their downloads released (`build.land`)."""
    from .build import land
    from .pipeline import Pipeline

    pipeline = Pipeline(resolved)
    try:
        counts = land(pipeline, paths, release=True)
    finally:
        pipeline.close()
    keep = ("partitions", "partitions_reused", "files_carried", "versions_kept", "rows", "released", "errors")
    return {k: counts[k] for k in keep if k in counts}


def _latest(catalog: CatalogStore, path: str) -> Any:
    rows = catalog.query(
        "SELECT sha256, modified, size FROM snapshot_versions WHERE path = ? "
        "ORDER BY first_observed_at DESC, rowid DESC LIMIT 1",
        (path,),
    )
    return rows[0] if rows else None


def _already_fetched(
    catalog: CatalogStore, blobs: BlobStore, path: str, size: int | None, modified: str
) -> str | None:
    """A blob an earlier read fetched from DATASUS at exactly this size and time.

    Taken as the version without a second download. A copy the mirror served is
    not adopted: the mirror's file can be an older or newer state.
    """
    if size is None or not modified:
        return None
    rows = catalog.query(
        "SELECT sha256 FROM fetches WHERE source_path = ? AND remote_size = ? AND remote_modified = ? "
        "AND serving_method LIKE 'ftp%' ORDER BY id DESC LIMIT 1",
        (path, int(size), modified),
    )
    return str(rows[0]["sha256"]) if rows and blobs.has(str(rows[0]["sha256"])) else None


def _record_version(
    catalog: CatalogStore, run_id: str, path: str, digest: str, size: int | None, modified: str, serving: str
) -> None:
    now = utcnow()
    with catalog.write() as conn:
        conn.execute(
            """
            INSERT INTO snapshot_versions (path, sha256, modified, size, first_observed_at,
                                           last_observed_at, observations, run_id, serving_method)
            VALUES (?,?,?,?,?,?,1,?,?)
            ON CONFLICT(path, sha256, modified) DO UPDATE SET
                last_observed_at = excluded.last_observed_at,
                observations = snapshot_versions.observations + 1,
                run_id = excluded.run_id
            """,
            (path, digest, modified or "", size, now, now, run_id, serving),
        )


# ------------------------------------------------------------------- reading


def versions(
    path: str, *, settings: Settings | None = None, root: str | Path | None = None
) -> list[dict[str, Any]]:
    """The known versions of the files whose path contains ``path``, oldest first: the ones a snapshot observed and
    the ones kept as deltas, each with where it is stored (``stored``): ``lake`` (the partition holds it), ``delta``
    (kept against its successor, ADR-0234), ``download`` (a blob not yet landed) or ``lost``."""
    from .persist.versions import current_digest

    resolved = settings or load_settings(root=Path(root) if root else None)
    catalog = CatalogStore(resolved.catalog_path, read_only=True)
    try:
        blobs = BlobStore(resolved.blobs_dir)
        found: dict[tuple[str, str], dict[str, Any]] = {}
        for r in catalog.query(
            "SELECT path, modified, size, sha256, first_observed_at, last_observed_at, observations, "
            "serving_method FROM snapshot_versions WHERE path LIKE ?", (f"%{path}%",),
        ):
            found[(str(r["path"]), str(r["sha256"]))] = dict(r)
        deltas = {}
        for r in catalog.query(
            "SELECT path, modified, size, sha256, rows, rows_removed, rows_added, byte_size AS delta_bytes "
            "FROM lake_versions WHERE path LIKE ? AND source_id = path", (f"%{path}%",),
        ):
            key = (str(r["path"]), str(r["sha256"]))
            deltas[key] = dict(r)
            found.setdefault(key, {"path": r["path"], "modified": r["modified"], "size": r["size"],
                                   "sha256": r["sha256"]})
        held = {p: current_digest(catalog, resolved.lake_dir, p)[0] for p in {k[0] for k in found}}
        out = []
        for (p, sha), row in found.items():
            stored = ("lake" if held.get(p) == sha else "delta" if (p, sha) in deltas
                      else "download" if blobs.has(sha) else "lost")
            out.append({**row, **{k: v for k, v in deltas.get((p, sha), {}).items() if k.startswith(("rows", "delta"))},
                        "stored": stored})
        return sorted(out, key=lambda r: (r["path"], str(r.get("modified") or r.get("first_observed_at") or "")))
    finally:
        catalog.close()


def as_of_cutoff(as_of: str | date | datetime) -> datetime:
    """A date means the end of that day (UTC); a datetime without zone is UTC."""
    if isinstance(as_of, datetime):
        return as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
    if isinstance(as_of, date):
        return datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC) + timedelta(days=1) - timedelta(seconds=1)
    text = str(as_of).strip()
    if len(text) <= 10:
        return as_of_cutoff(date.fromisoformat(text))
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def digests_as_of(
    catalog: CatalogStore, paths: Iterable[str], as_of: str | date | datetime, *, lake_root: str | Path | None = None,
) -> tuple[dict[str, str], list[str]]:
    """``({path: sha256}, [paths with no version by then])`` for a date.

    The versions of a path are the ones a snapshot observed, the ones kept as deltas (`lake_versions`, ADR-0234) and,
    given ``lake_root``, the one the lake holds, each at the server modification time listed for it (the time a
    snapshot first saw it, where the server gave none). The version a date saw is the latest on or before it. A state
    that was overwritten before anything read it is not in the history, so a path whose every known version is newer
    than the date is reported missing rather than answered with a later state.
    """
    from .persist.versions import current_digest, listing_of

    cutoff = as_of_cutoff(as_of)
    found: dict[str, str] = {}
    missing: list[str] = []
    for path in dict.fromkeys(paths):
        candidates = [(str(r["modified"] or r["first_observed_at"]), str(r["sha256"])) for r in catalog.query(
            "SELECT sha256, modified, first_observed_at FROM snapshot_versions WHERE path = ?", (path,))]
        candidates += [(str(r["modified"]), str(r["sha256"])) for r in catalog.query(
            "SELECT sha256, modified FROM lake_versions WHERE path = ? AND source_id = path AND modified <> ''",
            (path,))]
        if lake_root is not None:
            held, _files = current_digest(catalog, lake_root, path)
            modified = listing_of(catalog, path, held)[1] if held else ""
            if held and modified:
                candidates.append((modified, held))
        best: tuple[datetime, str] | None = None
        for when, sha in candidates:
            stamp = datetime.fromisoformat(when)
            stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
            if stamp <= cutoff and (best is None or stamp >= best[0]):
                best = (stamp, sha)
        if best is None:
            missing.append(path)
        else:
            found[path] = best[1]
    return found, missing
