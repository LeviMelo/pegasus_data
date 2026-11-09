"""Adopt another data home into this one: one machine, one home.

Every process that resolved no root used to make a data home beside its working directory, so one machine's downloads
were spread over homes that did not know of one another: on 2026-10-23 a project's pipeline fetched 11.6 GB of SIH and
SINAN into the repository's home while the per-user home already held most of those years. `adopt` moves what the other
home ACQUIRED into this one:

* **Downloads.** Each blob the other home's fetch history names is moved after its digest is checked, when this home
  lacks it. The fetch rows naming blobs now held here join this catalog's history. The latest fetch of a path is read by
  time (`fetched_at`), so an adopted older copy never shadows a newer one fetched here.
* **Registries.** Each file absent here is moved.

What the other home DERIVED is not adopted: its lake (record partitions, links, fields, aggregates, population
series) and its semantic tables. Each was computed by the code of its day. This home recomputes it from the adopted
downloads with the code of now, so no stale product is read as current. The plan lists these, together with the files
present on both sides and the files that disagree (this home's copy is kept), so the other home can be deleted
knowing what is lost.

The plan is read-only; ``apply=True`` executes it, and ``remove=True`` then deletes the other home, so no copy outlives
its adoption: adopted homes left on disk held 13 GB of duplicates on 2026-10-24 (ADR-0208). Crawl the adopted prefixes
afterwards. A fetch newer than this home's listing is judged against that listing, and a stale listing calls it changed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import stat
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings

__all__ = ["AdoptPlan", "adopt"]


@dataclass
class AdoptPlan:
    """What adopting a home moves and what it leaves, with bytes."""

    other: str
    blobs: list[str] = field(default_factory=list)
    blob_bytes: int = 0
    blobs_held: int = 0
    blobs_corrupt: list[str] = field(default_factory=list)
    fetch_rows: list = field(default_factory=list)
    registries: list[str] = field(default_factory=list)
    registry_bytes: int = 0
    same: int = 0
    differ: list[str] = field(default_factory=list)
    derived: dict[str, int] = field(default_factory=dict)  # lake top directory -> bytes left to be recomputed here
    applied: bool = False
    removed_bytes: int | None = None  # what deleting the adopted home freed; None while it is kept

    def summary(self) -> dict:
        return {"other": self.other, "blobs moved": len(self.blobs), "blob GB": round(self.blob_bytes / 1e9, 2),
                "blobs already here": self.blobs_held, "blobs failing their digest": len(self.blobs_corrupt),
                "fetch rows added": len(self.fetch_rows), "registry files moved": len(self.registries),
                "registry GB": round(self.registry_bytes / 1e9, 2), "registry files identical here": self.same,
                "registry files differing (kept this home's)": self.differ,
                "derived, left to recompute (GB)": {k: round(v / 1e9, 3) for k, v in self.derived.items()},
                "applied": self.applied,
                "removed (GB)": None if self.removed_bytes is None else round(self.removed_bytes / 1e9, 2)}


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1 << 22):
            h.update(block)
    return h.hexdigest()


def _files(base: Path) -> dict[str, int]:
    if not base.is_dir():
        return {}
    return {p.relative_to(base).as_posix(): p.stat().st_size for p in base.rglob("*") if p.is_file()}


def _remove_home(other: Path, here: Path) -> int:
    """Delete an adopted home and return the bytes freed. A junction or symbolic link inside it is removed as a link,
    never followed: a scratch home whose `lake/` links to this home's lake is common. A folder that is, holds or lies
    inside this home is refused."""
    if other == here or other in here.parents or here in other.parents:
        raise ValueError(f"{other} and this home {here} overlap: not removed")
    freed = 0

    def gone(path: Path) -> None:
        nonlocal freed
        st = os.lstat(path)
        if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT or stat.S_ISLNK(st.st_mode):
            try:
                os.rmdir(path)  # a junction or a directory link
            except OSError:
                os.unlink(path)
            return
        if not stat.S_ISDIR(st.st_mode):
            freed += st.st_size
            os.chmod(path, stat.S_IWRITE)
            os.unlink(path)
            return
        with os.scandir(path) as entries:
            children = [Path(e.path) for e in entries]
        for child in children:
            gone(child)
        os.rmdir(path)

    gone(other)
    return freed


def adopt(settings: Settings, other: str | Path, *, apply: bool = False, remove: bool = False) -> AdoptPlan:
    """Plan (and with ``apply``, carry out) moving ``other``'s downloads and registries into the home of ``settings``;
    with ``remove`` as well, delete ``other`` once nothing it acquired is left only there."""
    if remove and not apply:
        raise ValueError("remove deletes the other home after its adoption: it needs apply")
    other = Path(other).resolve()
    if other == Path(settings.root).resolve():
        raise ValueError(f"{other} is this home")
    here_blobs, here_reg = Path(settings.blobs_dir), Path(settings.registries_dir)
    plan = AdoptPlan(str(other))
    theirs = sqlite3.connect(f"file:{(other / '_catalog' / 'catalog.sqlite').as_posix()}?mode=ro", uri=True)
    theirs.row_factory = sqlite3.Row
    ours = sqlite3.connect(str(settings.catalog_path), timeout=300)
    ours.row_factory = sqlite3.Row
    try:
        rows = theirs.execute("SELECT source_path, sha256, byte_size, fetched_at, serving_method, elapsed_ms, "
                              "remote_size, remote_modified FROM fetches").fetchall()
        held: set[str] = set()
        for sha in sorted({r["sha256"] for r in rows}):
            src = other / "blobs" / "sha256" / sha[:2] / sha
            if (here_blobs / "sha256" / sha[:2] / sha).is_file():
                plan.blobs_held += 1
                held.add(sha)
            elif src.is_file():
                if apply and _digest(src) != sha:  # the digest is read when the bytes are about to move
                    plan.blobs_corrupt.append(sha)
                    continue
                plan.blobs.append(sha)
                plan.blob_bytes += src.stat().st_size
                held.add(sha)
        known = {tuple(r) for r in ours.execute("SELECT source_path, sha256, fetched_at FROM fetches")}
        plan.fetch_rows = [r for r in rows if r["sha256"] in held
                           and (r["source_path"], r["sha256"], r["fetched_at"]) not in known]

        ours_reg = _files(here_reg)
        for rel, size in sorted(_files(other / "registries").items()):
            if rel not in ours_reg:
                plan.registries.append(rel)
                plan.registry_bytes += size
            elif ours_reg[rel] == size:
                plan.same += 1
            else:
                plan.differ.append(rel)
        derived: Counter[str] = Counter()
        for rel, size in _files(other / "lake").items():
            derived[rel.split("/", 1)[0]] += size
        plan.derived = dict(derived.most_common())

        if apply:
            for sha in plan.blobs:
                target = here_blobs / "sha256" / sha[:2] / sha
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(other / "blobs" / "sha256" / sha[:2] / sha), str(target))
            for rel in plan.registries:
                target = here_reg / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(other / "registries" / rel), str(target))
            per_blob: dict[str, tuple[int, str, int]] = {}  # adopted fetches, the first of them, bytes
            for f in plan.fetch_rows:
                n, first, size = per_blob.get(f["sha256"], (0, f["fetched_at"], f["byte_size"] or 0))
                per_blob[f["sha256"]] = (n + 1, min(first, f["fetched_at"]), size)
            with ours:
                ours.execute("BEGIN IMMEDIATE")
                ours.executemany(
                    "INSERT INTO blobs (sha256, byte_size, first_fetched_at, fetch_count) VALUES (?,?,?,?) "
                    "ON CONFLICT(sha256) DO UPDATE SET fetch_count = blobs.fetch_count + excluded.fetch_count, "
                    "first_fetched_at = min(blobs.first_fetched_at, excluded.first_fetched_at)",
                    [(sha, size, first, n) for sha, (n, first, size) in per_blob.items()])
                ours.executemany(
                    "INSERT INTO fetches (source_path, sha256, byte_size, fetched_at, serving_method, elapsed_ms, "
                    "remote_size, remote_modified) VALUES (?,?,?,?,?,?,?,?)", [tuple(f) for f in plan.fetch_rows])
            plan.applied = True
    finally:
        theirs.close()
        ours.close()
    if remove:
        if plan.blobs_corrupt:
            raise ValueError(f"{len(plan.blobs_corrupt)} blobs of {other} fail their digest: that home is kept")
        plan.removed_bytes = _remove_home(other, Path(settings.root).resolve())
    return plan


def adopt_copies(settings: Settings, folder: str | Path, ftp_directory: str, *, apply: bool = False) -> dict[str, object]:
    """Adopt loose copies of FTP files into the blob store, so the one reader finds them held and fetches nothing.

    A file of ``folder`` is a copy of ``<ftp_directory>/<its name>`` when the catalog lists that path with the same size;
    it is stored under its own SHA-256 (a copy, ``folder`` untouched) and recorded as a fetch of that path with the
    listing's size and time (``serving_method`` ``local-copy``), so the fetcher's then-and-now comparison holds it current
    until DATASUS republishes it. Bytes are not proven equal by a size: the caller samples files against the server first
    (the CNES mirror: 5 of 5 identical, 2026-11-09). Without ``apply`` nothing is written; the counts say what would be.
    """
    from .acquire.cache import BlobStore, sha256_file
    from .catalog.store import CatalogStore

    base = Path(folder)
    prefix = ftp_directory.rstrip("/") + "/"
    store = CatalogStore(settings.catalog_path, read_only=not apply)
    try:
        listed = {str(r["path"]).rsplit("/", 1)[-1].upper(): (str(r["path"]), int(r["size"] or -1), r["modified"])
                  for r in store.query("SELECT path, size, modified FROM files WHERE path LIKE ? AND gone_at IS NULL",
                                       (prefix + "%",))}
        blobs = BlobStore(settings.blobs_dir, catalog=store if apply else None)
        counts: Counter[str] = Counter()
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            hit = listed.get(path.name.upper())
            if hit is None:
                counts["not listed"] += 1
                continue
            ftp_path, size, modified = hit
            if path.stat().st_size != size:
                counts["size differs"] += 1
                continue
            if not apply:
                counts["would adopt"] += 1
                continue
            digest = sha256_file(path)
            staged = blobs.staging_path(path.name)
            shutil.copyfile(path, staged)
            blobs.adopt(staged, digest, size, source_path=ftp_path, serving_method="local-copy",
                        remote_size=size, remote_modified=modified)
            counts["adopted"] += 1
        return dict(counts)
    finally:
        store.close()
