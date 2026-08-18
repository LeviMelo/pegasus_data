"""The uniform reader contract every decoder in this package returns.

``(field_metadata[], RecordBatch iterator)``, Arrow-native, as specified in §6.2
of the architecture brief. ``field_metadata`` carries physical type, width and
declared decimals *where the container declares them* — DBF does, CSV does not —
because that declared metadata is real signal for the semantic layer and must not
be thrown away on the way to Arrow.

One deliberate choice: fixed-width containers (DBF, and therefore DBC) are
decoded to **strings**, not to parsed numbers. Type canonicalisation belongs to
L6 where the ledger can say which sentinel means missing in which field; doing it
here would destroy the raw byte pattern that the distributional detectors in L4
need to tell an age code from a diagnosis code (D5).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pyarrow as pa


@dataclass(slots=True)
class FieldMeta:
    """What the container itself declares about a column."""

    name: str
    physical_type: str | None = None   # DBF type letter, arrow type name, 'csv', ...
    width: int | None = None
    decimals: int | None = None
    order: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "physical_type": self.physical_type,
            "width": self.width,
            "decimals": self.decimals,
            "order": self.order,
        }


@dataclass(slots=True)
class DecodedTable:
    """A tabular payload recovered from one physical source.

    ``member`` is non-empty when the payload came from inside an archive; one
    archive can yield many DecodedTables, each a distinct logical dataset (this
    is exactly the APAC ``.exe`` case — seven schemas in one file).
    """

    path: str
    reader: str
    fields: list[FieldMeta]
    batches: Callable[[], Iterator[pa.RecordBatch]]
    member: str = ""
    row_count: int | None = None
    container: str = ""
    role: str = "data"
    warnings: list[str] = field(default_factory=list)

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    @property
    def source_id(self) -> str:
        return f"{self.path}!{self.member}" if self.member else self.path

    def schema(self) -> pa.Schema:
        for batch in self.batches():
            return batch.schema
        return pa.schema([pa.field(f.name, pa.string()) for f in self.fields])

    def to_table(self, *, row_limit: int | None = None) -> pa.Table:
        collected: list[pa.RecordBatch] = []
        seen = 0
        for batch in self.batches():
            if row_limit is not None and seen + batch.num_rows > row_limit:
                batch = batch.slice(0, row_limit - seen)
            collected.append(batch)
            seen += batch.num_rows
            if row_limit is not None and seen >= row_limit:
                break
        if not collected:
            return pa.table({f.name: pa.array([], type=pa.string()) for f in self.fields})
        return pa.Table.from_batches(collected)


class DecodeError(Exception):
    """A reader could not make a table out of this payload."""


class UnsupportedContainer(DecodeError):
    """The container is recognised but this build cannot open it (missing optional dep)."""


def batches_from_table(table: pa.Table, *, batch_size: int = 65_536) -> Callable[[], Iterator[pa.RecordBatch]]:
    """Adapt an already-materialised Arrow table to the streaming contract."""

    def _iter() -> Iterator[pa.RecordBatch]:
        yield from table.to_batches(max_chunksize=batch_size)

    return _iter


def fields_from_schema(schema: pa.Schema, physical_prefix: str = "") -> list[FieldMeta]:
    return [
        FieldMeta(
            name=schema.field(i).name,
            physical_type=f"{physical_prefix}{schema.field(i).type}" if physical_prefix else str(schema.field(i).type),
            order=i,
        )
        for i in range(len(schema))
    ]
