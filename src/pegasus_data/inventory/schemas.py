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
    read_table_header,
)
from ..inventory.families import schema_signature

#: Extensions whose header this can read directly. Everything else — archives,
#: CSV, XML, JSON — needs a different route and is reported as such rather than
#: silently skipped.
HEADER_READABLE = (".dbc", ".dbf")

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
    catalog: Catalog, *, systems: Sequence[str] | None = None, only_missing: bool = True
) -> list[dict[str, object]]:
    """One representative file per stratum, cheapest first.

    Cheapest by byte size, which for a header read is nearly irrelevant — but it
    costs nothing to prefer the small one and it keeps the choice aligned with
    how the profile stage samples.
    """
    clauses = ["f.gone_at IS NULL", "ff.role = 'data'"]
    params: list[object] = []
    if systems:
        clauses.append(f"ff.system IN ({','.join('?' * len(systems))})")
        params.extend(s.upper() for s in systems)
    if only_missing:
        clauses.append("s.schema_signature IS NULL")
    where = " AND ".join(clauses)
    return [
        dict(r)
        for r in catalog.query(
            f"""
            SELECT s.stratum_id, s.system, s.series, s.year,
                   ff.path AS path, f.size AS size, f.extension AS extension
              FROM strata s
              JOIN stratum_members m ON m.stratum_id = s.stratum_id
              JOIN file_facts ff     ON ff.path = m.path
              JOIN files f           ON f.path = m.path
             WHERE {where}
             GROUP BY s.stratum_id
             HAVING f.size = MIN(f.size)
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
           SET schema_signature = COALESCE(schema_signature, ?),
               field_count      = COALESCE(field_count, ?),
               sample_status    = CASE WHEN sample_status = 'pending' THEN 'header' ELSE sample_status END
         WHERE stratum_id = ?
        """,
        (signature, len(header.fields), stratum_id),
    )
    return signature


def run_census(
    catalog: Catalog,
    fetch_prefix: Callable[[str, int], bytes],
    targets: Sequence[dict[str, object]],
    *,
    on_item: Callable[[str], None] | None = None,
) -> SchemaCensus:
    """Read one header per target, widening the request only when asked to."""
    census = SchemaCensus()
    for target in targets:
        path = str(target["path"])
        census.examined += 1
        if on_item:
            on_item(path)
        extension = str(target.get("extension") or "").lower()
        if extension not in HEADER_READABLE:
            census.not_header_readable += 1
            continue
        try:
            data = fetch_prefix(path, FIRST_PREFIX)
            census.bytes_fetched += len(data)
            try:
                header = read_table_header(data)
            except HeaderUnreadable:
                # The file said its header is longer than we asked for. Ask again
                # for exactly what it said, once — not a doubling loop, because
                # the header states its own length and a second failure means the
                # bytes are not a header at all.
                needed = min(DEFAULT_PREFIX_BYTES, max(FIRST_PREFIX * 8, 1))
                data = fetch_prefix(path, needed)
                census.bytes_fetched += len(data)
                census.widened += 1
                header = read_table_header(data)
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
