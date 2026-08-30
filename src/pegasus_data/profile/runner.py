"""L4 — profile a decoded table into the catalog.

Streams every RecordBatch through one :class:`FieldAccumulator` per column, then
classifies each field from its whole distribution and writes the verdict together
with the statistics that produced it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from ..catalog.store import Catalog
from ..decode.base import DecodedTable
from ..inventory.families import schema_signature
from .accumulators import FieldAccumulator, FieldStats
from .detectors import ReferenceSets, SemanticVerdict, classify


@dataclass(slots=True)
class TableProfile:
    path: str
    member: str
    reader: str
    schema_signature: str
    field_names: list[str]
    rows_profiled: int
    stats: dict[str, FieldStats]
    verdicts: dict[str, SemanticVerdict]

    @property
    def field_count(self) -> int:
        return len(self.field_names)


def profile_table(
    table: DecodedTable,
    *,
    refs: ReferenceSets | None = None,
    row_limit: int | None = None,
    max_distinct: int = 50_000,
    top_values: int = 200,
) -> TableProfile:
    accumulators = {
        f.name: FieldAccumulator(f, max_distinct=max_distinct, top_values=top_values)
        for f in table.fields
    }
    rows = 0
    for batch in table.batches():
        if row_limit is not None and rows >= row_limit:
            break
        if row_limit is not None and rows + batch.num_rows > row_limit:
            batch = batch.slice(0, row_limit - rows)
        for name in batch.schema.names:
            acc = accumulators.get(name)
            if acc is not None:
                acc.add_array(batch.column(name))
        rows += batch.num_rows

    stats = {name: acc.stats() for name, acc in accumulators.items()}
    verdicts = {name: classify(s, refs=refs, name=name) for name, s in stats.items()}
    names = table.field_names
    return TableProfile(
        path=table.path,
        member=table.member,
        reader=table.reader,
        schema_signature=schema_signature(names),
        field_names=names,
        rows_profiled=rows,
        stats=stats,
        verdicts=verdicts,
    )


def persist_profile(
    catalog: Catalog,
    profile: TableProfile,
    *,
    family_id: str,
    top_values_kept: int = 200,
) -> None:
    """Write variable profiles, value frequencies and schema presence."""
    catalog.executemany(
        """
        INSERT INTO schemas (schema_signature, field_count, fields_json, first_seen)
        VALUES (?,?,?, datetime('now'))
        ON CONFLICT(schema_signature) DO NOTHING
        """,
        [(profile.schema_signature, profile.field_count, json.dumps(profile.field_names))],
    )
    catalog.executemany(
        """
        INSERT INTO schema_presence (schema_signature, field_name, field_order)
        VALUES (?,?,?)
        ON CONFLICT(schema_signature, field_name) DO UPDATE SET field_order=excluded.field_order
        """,
        [(profile.schema_signature, name, i) for i, name in enumerate(profile.field_names)],
    )

    var_rows: list[tuple[object, ...]] = []
    freq_rows: list[tuple[object, ...]] = []
    for order, name in enumerate(profile.field_names):
        s = profile.stats.get(name)
        v = profile.verdicts.get(name)
        if s is None or v is None:
            continue
        var_rows.append(
            (
                family_id, name, profile.schema_signature,
                f"{profile.path}!{profile.member}" if profile.member else profile.path,
                order, s.physical_type, s.width, s.decimals,
                s.non_null, s.nulls, s.distinct_count, int(s.distinct_truncated),
                v.semantic_type, v.confidence, v.evidence_json(),
                json.dumps(s.as_dict(), default=str),
            )
        )
        total = s.non_null or 1
        for rank, (value, count) in enumerate(s.top_values[:top_values_kept], start=1):
            freq_rows.append(
                (family_id, name, profile.schema_signature, value, count, count / total, rank)
            )

    catalog.executemany(
        """
        INSERT INTO variable_profiles (family_id, field_name, schema_signature, source_path,
            field_order, physical_type, width, decimals, non_null, nulls, distinct_count,
            distinct_truncated, semantic_type, semantic_confidence, semantic_evidence, stats_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(family_id, field_name, schema_signature) DO UPDATE SET
            source_path=excluded.source_path, field_order=excluded.field_order,
            physical_type=excluded.physical_type, width=excluded.width, decimals=excluded.decimals,
            non_null=excluded.non_null, nulls=excluded.nulls,
            distinct_count=excluded.distinct_count, distinct_truncated=excluded.distinct_truncated,
            semantic_type=excluded.semantic_type, semantic_confidence=excluded.semantic_confidence,
            semantic_evidence=excluded.semantic_evidence, stats_json=excluded.stats_json
        """,
        var_rows,
    )
    catalog.execute(
        "DELETE FROM value_frequencies WHERE family_id=? AND schema_signature=?",
        (family_id, profile.schema_signature),
    )
    catalog.executemany(
        """
        INSERT INTO value_frequencies (family_id, field_name, schema_signature, value, count, percent, rank)
        VALUES (?,?,?,?,?,?,?)
        """,
        freq_rows,
    )


def record_stratum_schema(
    catalog: Catalog,
    stratum_id: str,
    *,
    schema_sig: str,
    field_count: int,
    sampled_member: str = "",
    status: str = "ok",
    error: str | None = None,
) -> None:
    # Through write(), which owns the lock -- see persist_reconciliation.
    with catalog.write() as conn:
        conn.execute(
            """
            UPDATE strata
               SET schema_signature=?, field_count=?, sampled_member=?, sample_status=?, sample_error=?
             WHERE stratum_id=?
            """,
            (schema_sig, field_count, sampled_member, status, error, stratum_id),
        )


def record_decode_attempts(
    catalog: Catalog, path: str, attempts: Sequence[tuple[str, bool, str | None]], member: str = ""
) -> None:
    catalog.executemany(
        """
        INSERT INTO decode_attempts (path, member, reader, ok, error, attempted_at)
        VALUES (?,?,?,?,?, datetime('now'))
        ON CONFLICT(path, member, reader) DO UPDATE SET
            ok=excluded.ok, error=excluded.error, attempted_at=excluded.attempted_at
        """,
        [(path, member, reader, int(ok), error) for reader, ok, error in attempts],
    )
