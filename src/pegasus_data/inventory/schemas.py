"""A **census** of every schema on the tree, read from headers alone.

The profile stage answers "what is in this column" and needs the payload to do
it: value distributions, semantic detection, sentinel discovery. That is
expensive — the cheapest member of each of the 4,228 strata still totals 183 GiB
— and so profiling has always been a *sample*.

This answers the narrower question "**what columns does this file have**", which
is what a schema catalogue actually needs, and answers it for everything. A DBF
declares its whole schema in a header of a few hundred bytes, and a ``.dbc``
stores that header uncompressed ahead of its compressed payload, so a ranged
fetch of the first few KB settles it. The census costs about 17 MB instead of
183 GiB.

The two are complements, not rivals. The census tells you that SIH-RD has
thirteen schema generations and exactly which columns each one has; the sample
tells you what `DIAG_PRINC` contains. Recording the census separately from
``variable_profiles`` keeps that distinction honest — nothing here should ever be
mistaken for having read the data.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog, utcnow
from ..decode.header import (
    DEFAULT_PREFIX_BYTES,
    HeaderUnreadable,
    TableHeader,
    read_csv_header,
    read_table_header,
)
from ..inventory.families import schema_signature

#: Extensions whose header this can read directly. Everything else — archives,
#: CSV, XML, JSON — needs a different route and is reported as such rather than
#: silently skipped.
HEADER_READABLE = (".dbc", ".dbf")

#: Delimited exports, whose first line names the columns. Same prefix trick,
#: different parser — and worth having, because DATASUS republishes whole
#: systems as CSV under Dados_Abertos where no DBF exists at all.
CSV_READABLE = (".csv",)

#: A small archive is read whole and its first data member's header parsed. A
#: zip keeps its directory at the END, so no prefix reaches a member; below
#: this size fetching it all is still cheap. IBGE's 120 census and population
#: strata are zips of a few KB to a few MB (OQ-54, 2026-09-28).
SMALL_ARCHIVE_BYTES = 20_000_000
ARCHIVE_READABLE = (".zip",)
#: A Parquet file declares its schema in a footer at the END: the last bytes
#: hold the footer's length and the magic "PAR1". SIPNI's 1.2 GB exports are
#: censused from their last 256 KB (ADR-0077).
PARQUET_TAIL = 256 * 1024

#: First ask. Covers every header measured on this tree (the widest, a
#: 113-column SIH-RD file, needs about 3.7 KB) with room to spare.
FIRST_PREFIX = 8192


@dataclass(slots=True)
class SchemaCensus:
    examined: int = 0
    read: int = 0
    unreadable: int = 0
    widened: int = 0
    not_header_readable: int = 0
    bytes_fetched: int = 0
    signatures: set[str] = field(default_factory=set)
    errors: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "examined": self.examined,
            "schemas_read": self.read,
            "unreadable": self.unreadable,
            "prefix_widened": self.widened,
            "not_header_readable": self.not_header_readable,
            "distinct_signatures": len(self.signatures),
            "bytes_fetched": self.bytes_fetched,
            "megabytes_fetched": round(self.bytes_fetched / 2**20, 2),
            "errors": self.errors[:10],
        }


def census_targets(
    catalog: Catalog,
    *,
    systems: Sequence[str] | None = None,
    only_missing: bool = True,
    stratum_ids: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """The stratum's own recorded sample, one file per stratum.

    The sample is chosen once, by :meth:`Stratum.sample_path` (a header the
    census can read first, then the cheapest), and recorded in
    ``strata.sampled_path``. This used to re-pick with its own SQL ("smallest
    file"), a second selection beside the first that sampled SIH-RD's .xml
    republications and left four years with no family (2026-09-28).

    ``stratum_ids`` narrows the census to a named set. Without it, answering
    ``fetch("CNES-ST", uf="AC", years=2023)`` on a fresh catalog censused **271
    strata across all thirteen CNES datasets** — hundreds of sequential requests
    to a high-latency legacy server, to learn about twelve files.
    """
    clauses = ["f.gone_at IS NULL", "s.sampled_path IS NOT NULL"]
    params: list[object] = []
    if systems:
        clauses.append(f"s.system IN ({','.join('?' * len(systems))})")
        params.extend(str(x).upper() for x in systems)
    if stratum_ids:
        clauses.append(f"s.stratum_id IN ({','.join('?' * len(stratum_ids))})")
        params.extend(stratum_ids)
    if only_missing:
        # Missing, or republished since it was read: DATASUS rewrote all of
        # SIA-PA on 2026-09-17 with one more column, and a signature read in
        # August described files that no longer existed (ADR-0078).
        clauses.append(
            "(s.schema_signature IS NULL OR f.modified > COALESCE(s.censused_at, f.first_seen))"
        )
    where = " AND ".join(clauses)
    return [
        dict(r)
        for r in catalog.query(
            f"""
            SELECT s.stratum_id, s.system, s.series, s.year, s.sampled_member AS member,
                   s.sampled_path AS path, f.size AS size, f.extension AS extension
              FROM strata s
              JOIN files f ON f.path = s.sampled_path
             WHERE {where}
             ORDER BY s.system, s.series, s.year
            """,
            params,
        )
    ]


def persist_header(
    catalog: Catalog, *, stratum_id: str, path: str, header: TableHeader
) -> str:
    """Record the schema, keyed by the same signature the families stage uses.

    Sharing ``schema_signature`` is the point: a census entry and a profiled
    sample of the same shape land on the same family, so the census fills in the
    generations sampling never reached without creating a parallel universe of
    schema identifiers.
    """
    signature = schema_signature(header.field_names)
    catalog.executemany(
        """
        INSERT INTO schemas (schema_signature, field_count, fields_json, first_seen)
        VALUES (?,?,?, datetime('now'))
        ON CONFLICT(schema_signature) DO NOTHING
        """,
        [(signature, len(header.fields), json.dumps(header.field_names))],
    )
    catalog.executemany(
        """
        INSERT INTO schema_presence (schema_signature, field_name, field_order)
        VALUES (?,?,?)
        ON CONFLICT(schema_signature, field_name) DO UPDATE SET field_order=excluded.field_order
        """,
        [(signature, f.name, i) for i, f in enumerate(header.fields)],
    )
    catalog.executemany(
        """
        INSERT INTO schema_header_facts
            (schema_signature, path, field_name, field_order, type_code, width, decimals,
             declared_records, record_length, widths_consistent, read_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(schema_signature, field_name) DO UPDATE SET
            type_code=excluded.type_code, width=excluded.width, decimals=excluded.decimals,
            declared_records=excluded.declared_records, record_length=excluded.record_length,
            widths_consistent=excluded.widths_consistent, read_at=excluded.read_at
        """,
        [
            (
                signature, path, f.name, i, f.type_code, f.width, f.decimals,
                header.declared_records, header.record_length,
                int(header.consistent), utcnow(),
            )
            for i, f in enumerate(header.fields)
        ],
    )
    catalog.execute(
        """
        UPDATE strata
           SET schema_signature = ?,
               field_count      = ?,
               censused_at      = ?,
               sample_status    = CASE WHEN sample_status = 'pending' THEN 'header' ELSE sample_status END
         WHERE stratum_id = ?
        """,
        (signature, len(header.fields), utcnow(), stratum_id),
    )
    return signature


def run_census(
    catalog: Catalog,
    fetch_prefix: Callable[[str, int], bytes],
    targets: Sequence[dict[str, object]],
    *,
    on_item: Callable[[str], None] | None = None,
    fetch_range: Callable[[str, int, int], bytes] | None = None,
) -> SchemaCensus:
    """Read one header per target, widening the request only when asked to."""
    census = SchemaCensus()
    archive_cache: dict[str, bytes] = {}
    for target in targets:
        path = str(target["path"])
        census.examined += 1
        if on_item:
            on_item(path)
        extension = str(target.get("extension") or "").lower()
        if extension == ".parquet" and fetch_range is not None and int(target.get("size") or 0) > 8:
            size = int(target.get("size") or 0)
            try:
                tail_size = min(size, PARQUET_TAIL)
                tail = fetch_range(path, size - tail_size, tail_size)
                census.bytes_fetched += len(tail)
                footer = int.from_bytes(tail[-8:-4], "little") + 8
                if footer > len(tail) and footer <= size:
                    # A wide or many-row-group file: ask again for exactly the footer.
                    tail = fetch_range(path, size - footer, footer)
                    census.bytes_fetched += len(tail)
                header = _parquet_header(tail, size)
            except Exception as exc:  # noqa: BLE001 - one bad file is not the census
                census.unreadable += 1
                census.errors.append((path, f"{type(exc).__name__}: {exc}"))
                continue
            signature = persist_header(catalog, stratum_id=str(target["stratum_id"]), path=path, header=header)
            census.signatures.add(signature)
            census.read += 1
            continue
        if extension == ".exe" and int(target.get("size") or 0) <= SMALL_ARCHIVE_BYTES:
            try:
                data = archive_cache.get(path) or fetch_prefix(path, int(target.get("size") or SMALL_ARCHIVE_BYTES))
                if path not in archive_cache:
                    census.bytes_fetched += len(data)
                    archive_cache[path] = data
                header, member = _header_in_lha(catalog, path, data, target)
            except Exception as exc:  # noqa: BLE001 - one bad archive is not the census
                census.unreadable += 1
                census.errors.append((path, f"{type(exc).__name__}: {exc}"))
                continue
            signature = persist_header(catalog, stratum_id=str(target["stratum_id"]), path=path, header=header)
            catalog.execute("UPDATE strata SET sampled_member = ? WHERE stratum_id = ?",
                            (member, str(target["stratum_id"])))
            census.signatures.add(signature)
            census.read += 1
            continue
        if extension in ARCHIVE_READABLE and int(target.get("size") or 0) <= SMALL_ARCHIVE_BYTES:
            try:
                data = fetch_prefix(path, int(target.get("size") or SMALL_ARCHIVE_BYTES))
                census.bytes_fetched += len(data)
                header = _header_in_archive(data)
            except Exception as exc:  # noqa: BLE001 - one bad archive is not the census
                census.unreadable += 1
                census.errors.append((path, f"{type(exc).__name__}: {exc}"))
                continue
            signature = persist_header(catalog, stratum_id=str(target["stratum_id"]), path=path, header=header)
            census.signatures.add(signature)
            census.read += 1
            continue
        if extension not in HEADER_READABLE and extension not in CSV_READABLE:
            census.not_header_readable += 1
            continue
        reader = read_csv_header if extension in CSV_READABLE else read_table_header
        try:
            data = fetch_prefix(path, FIRST_PREFIX)
            census.bytes_fetched += len(data)
            try:
                header = reader(data)
            except HeaderUnreadable:
                # The file said its header is longer than we asked for. Ask again
                # for exactly what it said, once — not a doubling loop, because
                # the header states its own length and a second failure means the
                # bytes are not a header at all.
                needed = min(DEFAULT_PREFIX_BYTES, max(FIRST_PREFIX * 8, 1))
                data = fetch_prefix(path, needed)
                census.bytes_fetched += len(data)
                census.widened += 1
                header = reader(data)
        except HeaderUnreadable as exc:
            census.unreadable += 1
            census.errors.append((path, str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 - one bad file is not the census
            census.unreadable += 1
            census.errors.append((path, f"{type(exc).__name__}: {exc}"))
            continue
        signature = persist_header(
            catalog, stratum_id=str(target["stratum_id"]), path=path, header=header
        )
        census.signatures.add(signature)
        census.read += 1
    return census


def census_summary(catalog: Catalog) -> list[dict[str, object]]:
    """Schema generations per (system, series), from the census plus the samples."""
    return [
        dict(r)
        for r in catalog.query(
            """
            SELECT system, series,
                   COUNT(*)                              AS strata,
                   COUNT(DISTINCT schema_signature)      AS generations,
                   MIN(field_count)                      AS min_fields,
                   MAX(field_count)                      AS max_fields,
                   MIN(year)                             AS year_min,
                   MAX(year)                             AS year_max
              FROM strata
             WHERE schema_signature IS NOT NULL AND schema_signature <> ''
             GROUP BY system, series
             ORDER BY generations DESC, strata DESC
            """
        )
    ]


def _header_in_archive(data: bytes) -> TableHeader:
    """The header of the first DBF, DBC or CSV member of a zip held in memory."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = sorted(
            (m for m in archive.infolist() if not m.is_dir()),
            key=lambda m: (m.filename.lower().endswith(".csv"), m.filename),
        )
        for member in members:
            name = member.filename.lower()
            if name.endswith((".dbf", ".dbc")):
                with archive.open(member) as handle:
                    return read_table_header(handle.read(64 * 1024))
            if name.endswith(".csv"):
                with archive.open(member) as handle:
                    return read_csv_header(handle.read(64 * 1024))
            if name.endswith(".parquet"):
                body = archive.read(member)
                return _parquet_header(body, len(body))
    raise HeaderUnreadable("no DBF, DBC, CSV or Parquet member in the archive")


def _parquet_header(tail: bytes, size: int) -> TableHeader:
    """Column names from a Parquet footer held in memory.

    The reader is handed a file of the true size in which only the tail is
    present; reading the schema touches nothing else.
    """
    import io
    import struct

    import pyarrow.parquet as pq

    from ..decode.header import HeaderField

    if tail[-4:] != b"PAR1":
        raise HeaderUnreadable("not a Parquet file: no PAR1 magic at the end")
    footer_len = struct.unpack("<I", tail[-8:-4])[0]
    if footer_len + 8 > len(tail):
        raise HeaderUnreadable(f"Parquet footer is {footer_len} bytes; the tail read holds {len(tail)}")
    base = size - len(tail)

    class _Tail(io.RawIOBase):
        def __init__(self) -> None:
            self.pos = 0

        def readable(self) -> bool:
            return True

        def seekable(self) -> bool:
            return True

        def seek(self, offset: int, whence: int = 0) -> int:
            self.pos = offset if whence == 0 else (self.pos + offset if whence == 1 else size + offset)
            return self.pos

        def tell(self) -> int:
            return self.pos

        def readinto(self, buffer) -> int:  # type: ignore[no-untyped-def]
            # Bytes before the tail are never interpreted (the footer is whole
            # in the tail); a buffered reader's speculative prefetch gets zeros.
            if self.pos < base:
                gap = min(len(buffer), base - self.pos)
                buffer[:gap] = bytes(gap)
                self.pos += gap
                return gap
            chunk = tail[self.pos - base : self.pos - base + len(buffer)]
            buffer[: len(chunk)] = chunk
            self.pos += len(chunk)
            return len(chunk)

    schema = pq.read_schema(io.BufferedReader(_Tail()))
    fields = [HeaderField(name=name, type_code="P", width=0, decimals=0) for name in schema.names]
    return TableHeader(fields=fields, declared_records=0, header_length=0, record_length=0, version=0)


def _header_in_lha(catalog: Catalog, path: str, data: bytes, target: dict[str, object]) -> tuple[TableHeader, str]:
    """Open an LHA self-extracting archive; record every member; read one.

    The member read is the stratum's own: the one named in ``sampled_member``
    (a member stratum from inventory's expansion), else the one whose kind is
    the stratum's series, else the first DBF (ADR-0077).
    """
    from ..decode.lha import LhaArchive
    from .naming import member_kind

    archive = LhaArchive(data)
    names = [m.name for m in archive.members]
    catalog.executemany(
        "INSERT OR IGNORE INTO archive_members (archive_path, member, member_size, member_role, container) "
        "VALUES (?,?,?,?, 'lha_sfx')",
        [(path, m.name, m.original_size, "data" if m.name.lower().endswith((".dbf", ".dbc")) else "binary")
         for m in archive.members],
    )
    wanted = str(target.get("member") or "")
    if not wanted:
        series = str(target.get("series") or "")
        own = [n for n in names if member_kind(path, n, series) == series.upper()]
        dbfs = [n for n in names if n.lower().endswith((".dbf", ".dbc"))]
        wanted = (own or dbfs or [""])[0]
    if wanted not in names:
        raise HeaderUnreadable(f"member {wanted!r} not in the archive ({len(names)} members)")
    return read_table_header(archive.read(wanted)[: 64 * 1024]), wanted

