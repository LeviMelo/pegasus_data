"""The versions DATASUS overwrote, kept as deltas against their successors in the lake (ADR-0234).

DATASUS rewrites a preliminary or current-year file under the same name (ADR-0141), so the lake's partition of it is
the version last built, and every earlier version exists only if it was kept. A kept version is its difference from the
version that replaced it, matched record by record:

* **removed**: its rows the successor does not hold, whole, in the lake's form (``<id>.removed.parquet``);
* **kept**: the rows both hold, as runs ``(old_start, offset, length)`` of ``_row`` (``<id>.kept.parquet``): row
  ``old_start + i`` of the version is row ``old_start + offset + i`` of the successor. Delta-encoded: DATASUS reorders
  a rewritten file (dengue 2026: 231,311 runs for 445,411 rows kept), and consecutive runs have near offsets.

Rows are matched by their record identity: the content key over the record's own fields (`normalize.engine.
record_key_sql`), exact duplicates numbered in file order, as `linkage.identity.RECORD_ID_SQL` numbers them. A row the
successor added is a row of the successor no run names. Storage is the churn: a file that changed nothing but ten rows
is ten rows and a run or two, and a version read back gives every row in its own order with its own ``_row``.

Each delta names its successor's digest, so a version is read by following successors to the version the lake holds
(`read_version`): the lake's rows of the source, then each delta applied from the newest back. No blob, no network.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ..catalog.store import CatalogStore, utcnow
from .lake import RowGroups, _safe, parquet_writer

#: Under the lake root, beside the systems: `<lake>/versions/<system>/<family>/<source>/<sha>.{removed,kept}.parquet`.
VERSIONS_DIR = "versions"

_RUNS = pa.schema([("old_start", pa.int64()), ("offset", pa.int64()), ("length", pa.int64())])


class VersionUnavailable(LookupError):
    """The version asked is neither the lake's nor reachable through kept deltas."""


# ------------------------------------------------------------------ the lake's rows of one source


def partitions_holding(catalog: CatalogStore, source_id: str) -> list[dict[str, Any]]:
    """The ``lake_partitions`` rows whose recorded sources name ``source_id`` (every family, part file and year)."""
    needle = json.dumps(source_id)
    return [dict(r) for r in catalog.query(
        "SELECT * FROM lake_partitions WHERE instr(source_paths, ?) > 0", (needle,))
        if source_id in json.loads(r["source_paths"] or "[]")]


def file_digests(path: Path) -> dict[str, str]:
    """``{source id: digest}`` of one partition file, from its two provenance columns. Empty for a file that has
    none: an intake unit (ADR-0162) names its source in `_SOURCE_PATH` and keeps no digest, and is held by path."""
    if not {"_source_path", "_blob_sha256"} <= set(pq.read_schema(path).names):
        return {}
    table = pq.read_table(path, columns=["_source_path", "_blob_sha256"])
    if not table.num_rows:
        return {}
    # a file's row groups can carry differing dictionaries, which Arrow will not group over: decode them first
    table = pa.table({name: table.column(name).cast(pa.string()) for name in table.column_names})
    pairs = table.group_by(["_source_path", "_blob_sha256"]).aggregate([])
    out: dict[str, str] = {}
    for source, sha in zip(pairs.column(0).to_pylist(), pairs.column(1).to_pylist(), strict=True):
        if source in out and out[source] != sha:
            raise ValueError(f"{path}: source {source} carries two digests ({out[source]}, {sha})")
        out[str(source)] = str(sha)
    return out


def partition_digests(lake_root: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """``{source id: digest}`` of a partition's files: the catalog's record where the build wrote one, else the files'."""
    out: dict[str, str] = {}
    for row in rows:
        recorded = row.get("source_digests")
        found = json.loads(recorded) if recorded else file_digests(lake_root / str(row["relative_path"]))
        out.update({str(k): str(v) for k, v in found.items()})
    return out


def source_rows(files: Sequence[Path], source_id: str, sha: str | None = None) -> pa.Table:
    """The rows of one source in partition files (no partition columns), in ``_row`` order, each typed column's text
    as filed given back whole (`raw_text`, ADR-0232): a file's renders are its own, so rows taken out of it carry no
    render metadata and are compared and kept by their whole text. A split partition's files can differ by a column:
    read file by file and promoted."""
    import pyarrow.dataset as ds

    from ..raw_text import META_KEY, quote, renders_of, restored

    pieces = []
    for file in files:
        dataset = ds.dataset(str(file), format="parquet")
        test = ds.field("_source_path") == source_id
        if sha is not None:
            test = test & (ds.field("_blob_sha256") == sha)
        table = dataset.to_table(filter=test)
        renders = renders_of(pq.read_schema(file).metadata)
        if renders:
            table = restored(table, renders, quote)
        meta = {k: v for k, v in (table.schema.metadata or {}).items() if k != META_KEY}
        table = table.replace_schema_metadata(meta or None)
        if table.num_rows:
            pieces.append(table)
    if not pieces:
        return pa.table({})
    table = pieces[0] if len(pieces) == 1 else pa.concat_tables(pieces, promote_options="permissive")
    return table.sort_by("_row")


# ------------------------------------------------------------------ the difference of two versions


def _duck(duckdb: Any) -> Any:
    """A DuckDB connection held to 1.5 GB, spilling to this process's own directory (`Settings.duckdb_spill`): the
    machine is shared and pages when a join takes its default 80% of memory."""
    from ..config import load_settings

    con = duckdb.connect()
    spill = load_settings().duckdb_spill().as_posix()
    con.execute(f"SET memory_limit = '1500MB'; SET threads = 4; SET temp_directory = '{spill}'; "
                "SET preserve_insertion_order = false")
    return con


def _matched(old: pa.Table, new: pa.Table) -> pa.Table:
    """``(old_row, new_row)`` of the rows two versions share, matched by content key and duplicate number."""
    import duckdb

    from ..normalize.engine import key_fields, record_key_sql

    fields = key_fields(set(old.column_names) | set(new.column_names))

    def keyed(table: pa.Table) -> pa.Table:
        cols = {"_row": table.column("_row")}
        for name in fields:
            cols[name] = table.column(name) if name in table.column_names else pa.nulls(table.num_rows, pa.string())
        return pa.table(cols)

    con = _duck(duckdb)
    try:
        con.register("o", keyed(old))
        con.register("n", keyed(new))
        key = record_key_sql(fields)
        return con.execute(f"""
            WITH od AS (SELECT _row, k, row_number() OVER (PARTITION BY k ORDER BY _row) AS d
                        FROM (SELECT _row, {key} AS k FROM o)),
                 nd AS (SELECT _row, k, row_number() OVER (PARTITION BY k ORDER BY _row) AS d
                        FROM (SELECT _row, {key} AS k FROM n))
            SELECT od._row AS old_row, nd._row AS new_row FROM od JOIN nd USING (k, d) ORDER BY old_row
        """).to_arrow_table()
    finally:
        con.close()


def _runs(pairs: pa.Table) -> pa.Table:
    """Matched rows as runs where both sides count up together."""
    import duckdb

    con = _duck(duckdb)
    try:
        con.register("p", pairs)
        return con.execute("""
            WITH s AS (SELECT old_row, new_row,
                              CASE WHEN old_row - lag(old_row) OVER w = 1
                                    AND new_row - lag(new_row) OVER w = 1 THEN 0 ELSE 1 END AS edge
                       FROM p WINDOW w AS (ORDER BY old_row)),
                 r AS (SELECT old_row, new_row, sum(edge) OVER (ORDER BY old_row) AS run FROM s)
            SELECT min(old_row)::BIGINT AS old_start, (min(new_row) - min(old_row))::BIGINT AS offset,
                   count(*)::BIGINT AS length
            FROM r GROUP BY run ORDER BY old_start
        """).to_arrow_table().cast(_RUNS)
    finally:
        con.close()


def _write(path: Path, table: pa.Table, *, runs: bool = False) -> int:
    """A delta file: removed rows in the lake's encoding; runs as three delta-encoded integer columns (2.3 times
    smaller than dictionary-encoded on dengue 2026's 231,311 runs)."""
    from .kept import ENCODING, ZSTD_LEVEL
    from .staging import staged_file

    if runs:
        table = table.replace_schema_metadata({b"pegasus.encoding": f"{ENCODING}-delta".encode()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with staged_file(path) as staged:
        writer = (pq.ParquetWriter(staged, table.schema, compression="zstd", compression_level=ZSTD_LEVEL,
                                   use_dictionary=False, column_encoding=dict.fromkeys(table.schema.names,
                                                                                       "DELTA_BINARY_PACKED"))
                  if runs else parquet_writer(staged, table.schema))
        try:
            groups = RowGroups(writer)
            for batch in table.to_batches():
                groups.write(batch)
            groups.flush()
        finally:
            writer.close()
    return path.stat().st_size


def listing_of(catalog: CatalogStore, path: str, sha: str) -> tuple[int | None, str]:
    """The listed size and server time of one version of a path: a snapshot's observation, else the fetch's."""
    rows = catalog.query("SELECT size, modified FROM snapshot_versions WHERE path = ? AND sha256 = ? "
                         "ORDER BY first_observed_at DESC LIMIT 1", (path, sha))
    if rows:
        return rows[0]["size"], str(rows[0]["modified"] or "")
    rows = catalog.query("SELECT remote_size, remote_modified FROM fetches WHERE source_path = ? AND sha256 = ? "
                         "ORDER BY id DESC LIMIT 1", (path, sha))
    return (rows[0]["remote_size"], str(rows[0]["remote_modified"] or "")) if rows else (None, "")


def write_delta(
    catalog: CatalogStore, lake_root: str | Path, *, system: str, family_id: str, schema_signature: str,
    source_id: str, path: str, old_sha: str, old: pa.Table, new_sha: str, new: pa.Table,
) -> dict[str, Any]:
    """Keep version ``old_sha`` of ``source_id`` as its difference from ``new_sha``; one row of ``lake_versions``.
    ``old`` and ``new`` are the source's rows of each version in the lake's form."""
    if old_sha == new_sha:
        raise ValueError(f"{source_id}: a version is not its own successor")
    for name, table in (("old", old), ("new", new)):
        rows = table.column("_row")
        if pc.count_distinct(rows).as_py() != table.num_rows:
            raise ValueError(f"{source_id}: the {name} version's _row is not unique")
    pairs = _matched(old, new)
    runs = _runs(pairs)
    removed = old.filter(pc.invert(pc.is_in(old.column("_row"), value_set=pairs.column("old_row"))))
    base = Path(lake_root) / VERSIONS_DIR / _safe(system) / _safe(family_id) / _safe(source_id)
    removed_path, kept_path = base / f"{old_sha}.removed.parquet", base / f"{old_sha}.kept.parquet"
    # a version that removed nothing has no removed file: an empty one is its schema, 11 KB for SIH-RD's 113 columns
    size = (_write(removed_path, removed) if removed.num_rows else 0) + _write(kept_path, runs, runs=True)
    listed_size, modified = listing_of(catalog, path, old_sha)
    record = {
        "source_id": source_id, "path": path, "sha256": old_sha, "size": listed_size, "modified": modified,
        "successor_sha256": new_sha, "superseded_at": utcnow(), "system": system, "family_id": family_id,
        "schema_signature": schema_signature,
        "removed_path": removed_path.relative_to(lake_root).as_posix() if removed.num_rows else "",
        "kept_path": kept_path.relative_to(lake_root).as_posix(),
        "rows": old.num_rows, "rows_removed": removed.num_rows, "rows_added": new.num_rows - pairs.num_rows,
        "byte_size": size,
    }
    names = list(record)
    with catalog.write() as conn:
        conn.execute(
            f"INSERT INTO lake_versions ({', '.join(names)}) VALUES ({', '.join('?' * len(names))}) "
            "ON CONFLICT(source_id, sha256) DO UPDATE SET "
            + ", ".join(f"{n} = excluded.{n}" for n in names if n not in ("source_id", "sha256")),
            [record[n] for n in names])
    return record


# ------------------------------------------------------------------ reading a version back


def current_digest(catalog: CatalogStore, lake_root: str | Path, source_id: str) -> tuple[str | None, list[Path]]:
    """The digest the lake holds a source at, and the partition files holding it."""
    rows = partitions_holding(catalog, source_id)
    files = [Path(lake_root) / str(r["relative_path"]) for r in rows]
    held = partition_digests(Path(lake_root), rows).get(source_id)
    return held, files


def _apply(current: pa.Table, kept: pa.Table, removed: pa.Table, sha: str) -> pa.Table:
    """The version before ``current``: its runs of ``current``'s rows renumbered, and its removed rows."""
    import numpy as np

    starts_old = kept.column("old_start").to_numpy()
    starts_new = starts_old + kept.column("offset").to_numpy()
    lengths = kept.column("length").to_numpy()
    if len(lengths):
        offsets = np.repeat(np.cumsum(lengths) - lengths, lengths)
        within = np.arange(int(lengths.sum()), dtype=np.int64) - offsets
        new_rows = np.repeat(starts_new, lengths) + within
        old_rows = np.repeat(starts_old, lengths) + within
    else:
        new_rows = old_rows = np.zeros(0, dtype=np.int64)
    positions = pc.index_in(pa.array(new_rows), value_set=current.column("_row"))
    if positions.null_count:
        raise VersionUnavailable(f"{positions.null_count} rows a delta keeps are not in its successor")
    carried = current.take(positions)
    index = carried.schema.get_field_index("_row")
    carried = carried.set_column(index, carried.schema.field(index), pa.array(old_rows, pa.int64()))
    sha_field = carried.schema.field("_blob_sha256")
    stamp = pa.DictionaryArray.from_arrays(pa.array(np.zeros(carried.num_rows, np.int32)), pa.array([sha]))
    carried = carried.set_column(carried.schema.get_field_index("_blob_sha256"), sha_field,
                                 stamp.cast(sha_field.type))
    out = pa.concat_tables([carried, removed], promote_options="permissive") if removed.num_rows else carried
    return out.sort_by("_row")


def read_version(catalog: CatalogStore, lake_root: str | Path, source_id: str, sha: str) -> pa.Table:
    """The rows of ``source_id`` as version ``sha`` held them, in the lake's form and the version's row order: the
    lake's rows when it holds that version, else the lake's rows with each delta from the lake's version back to it
    applied. Raises :class:`VersionUnavailable` when no chain of kept deltas leads there."""
    root = Path(lake_root)
    held, files = current_digest(catalog, root, source_id)
    if held is None:
        raise VersionUnavailable(f"{source_id}: the lake holds no version of it")
    rows = {str(r["sha256"]): dict(r) for r in catalog.query(
        "SELECT * FROM lake_versions WHERE source_id = ?", (source_id,))}
    chain: list[dict[str, Any]] = []
    step = sha
    while step != held:
        row = rows.get(step)
        if row is None or len(chain) > len(rows):
            raise VersionUnavailable(f"{source_id}: no kept delta leads from version {sha[:12]} to the lake's "
                                     f"{held[:12]}")
        chain.append(row)
        step = str(row["successor_sha256"])
    table = source_rows(files, source_id, held)
    for row in reversed(chain):
        removed = pq.read_table(root / row["removed_path"]) if row["removed_path"] else pa.table({})
        table = _apply(table, pq.read_table(root / row["kept_path"]), removed, str(row["sha256"]))
    return table


def record_partition_digests(catalog: CatalogStore, lake_root: str | Path) -> int:
    """Fill ``lake_partitions.source_digests`` for the partitions written before it existed, from their files'
    ``_blob_sha256``; returns the partitions recorded. A partition with a file missing is left for its rebuild."""
    root = Path(lake_root)
    groups: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    for row in catalog.query("SELECT * FROM lake_partitions WHERE source_digests IS NULL"):
        groups.setdefault((row["family_id"], row["schema_signature"], row["uf"], row["year"]), []).append(dict(row))
    done = 0
    for key, rows in groups.items():
        if not all((root / str(r["relative_path"])).is_file() for r in rows):
            continue
        digests = json.dumps(dict(sorted(partition_digests(root, rows).items())))
        catalog.execute("UPDATE lake_partitions SET source_digests = ? WHERE family_id = ? AND schema_signature = ? "
                        "AND uf = ? AND year = ?", (digests, *key))
        done += 1
    return done


def held_versions(catalog: CatalogStore) -> set[tuple[str, str]]:
    """``(source id, digest)`` of every version kept as a delta."""
    return {(str(r["source_id"]), str(r["sha256"])) for r in catalog.query("SELECT source_id, sha256 FROM lake_versions")}


__all__ = ["VERSIONS_DIR", "VersionUnavailable", "current_digest", "file_digests", "held_versions",
           "listing_of", "partition_digests", "partitions_holding", "read_version", "record_partition_digests",
           "source_rows", "write_delta"]
