"""Reference code tables as first-class, version-scoped lake citizens.

Why these are not materialised as ``<field>_label`` columns
-----------------------------------------------------------

For a small closed codelist — ``SEXO`` has three categories, ``IDENT`` three —
writing the label beside the code is cheap and unambiguous, and §7.1 step 3 is
right to ask for it.

For a large hierarchical classification it is the wrong shape, for three reasons
that have nothing to do with footprint:

1. **It fixes a granularity choice invisibly.** ``E11`` and ``E119`` are distinct
   rows in the CID-10 table. Materialising one label makes whichever codelist won
   a coverage ranking into *the* answer, and the analyst inherits that choice
   without being told a choice was made. Chapter, block and category are all
   legitimate levels and the consumer must pick.

2. **It freezes a time-varying assertion.** The 1992–1997 kit's CID-10 has 14,197
   rows; the current one has 14,253, and they disagree about labels in between.
   ``dictionary.valid_from``/``valid_to`` exist precisely to keep both true. A
   string baked into a 2019 row throws that scoping away and cannot be corrected
   without rewriting the lake.

3. **The published wording is dated and abbreviated.** ``DESCR`` is a 50-character
   field: ``N39.0`` reads "Infecc do trato urinario de localiz NE", and ICD-10's
   pt-BR wording for several endocrine codes is clinically obsolete. Freezing it
   into every row presents a lossy legacy string as the meaning of the code.

So the code tables are written to ``lake/reference/<table>/window=.../`` and
joined on demand, at the granularity and vintage the consumer chooses. Nothing is
lost: meaning is still fully recoverable, which is what P1 requires, and
``describe()`` still resolves it — it just names the table and the window rather
than pretending one string is the answer.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as pads
import pyarrow.parquet as pq

from ..catalog.store import Catalog

_SAFE = re.compile(r"[^A-Za-z0-9_.=-]+")

#: Tables that are hierarchical classifications rather than closed codelists.
#: A field bound to one of these gets a join, not a materialised label column.
HIERARCHICAL_TABLES: frozenset[str] = frozenset(
    {"CID10", "CID9", "TPROC", "TPROC10", "EMUSO", "EMUSO10", "MUNICBR", "MUNIDB", "CBO", "TCBO"}
)

#: Above this many distinct labels a codelist is treated as a classification even
#: if it is not named above — the distinction is size and hierarchy, not identity.
LARGE_CODELIST_LABELS = 200


@dataclass(slots=True)
class ReferenceTable:
    table_id: str
    valid_from: str | None
    valid_to: str | None
    rows: int
    relative_path: str
    source_ref: str
    code_widths: tuple[int, ...] = ()

    @property
    def mixed_widths(self) -> bool:
        """Two code widths in one table means two classifications merged."""
        return len(self.code_widths) > 1

    @property
    def window(self) -> str:
        if self.valid_from and self.valid_to:
            return f"{self.valid_from}-{self.valid_to}"
        return "current"


def is_hierarchical(catalog: Catalog, codelist: str) -> bool:
    """Whether a codelist should be joined rather than flattened into labels."""
    name = codelist.upper()
    if any(name.startswith(prefix) for prefix in HIERARCHICAL_TABLES):
        return True
    labels = catalog.scalar(
        "SELECT COUNT(DISTINCT value_label) FROM dictionary WHERE value_group = ?", (codelist,)
    )
    return int(labels or 0) > LARGE_CODELIST_LABELS


def write_reference_tables(
    catalog: Catalog, lake_root: str | Path, *, compression: str = "zstd"
) -> list[ReferenceTable]:
    """Materialise every code table, scoped by the validity window it came from."""
    root = Path(lake_root) / "reference"
    root.mkdir(parents=True, exist_ok=True)

    written: list[ReferenceTable] = []

    # One ordered scan, grouped as it streams. Querying per (table, window) meant
    # ~500 separate scans of a 3.4-million-row table, which is quadratic in the
    # number of codelists and dominated the stage.
    cursor = catalog.execute(
        """
        SELECT value_group, valid_from, valid_to, value_raw, value_label, source, source_ref, confidence
          FROM dictionary
         WHERE value_group IS NOT NULL
         ORDER BY value_group, valid_from, value_raw
        """
    )

    current_key: tuple[str, str | None, str | None] | None = None
    batch: list[tuple[object, ...]] = []

    def _flush() -> None:
        if current_key is None or len(batch) < 2:
            return
        table_id, valid_from, valid_to = current_key
        table = pa.table(
            {
                "code": pa.array([str(e[0]) for e in batch], type=pa.string()),
                "label": pa.array([e[1] for e in batch], type=pa.string()),
                "source": pa.array([e[2] for e in batch], type=pa.string()),
                "source_ref": pa.array([e[3] for e in batch], type=pa.string()),
                "confidence": pa.array([float(e[4] or 0) for e in batch], type=pa.float32()),
                # Code width separates classifications that a kit ships merged.
                # `CBO` in the current SIH kit holds 3,000 three-digit CBO-1994
                # codes and 2,813 six-digit CBO-2002 codes in one file; joining
                # without the width would let a 1994 code label 2002 data.
                "code_width": pa.array([len(str(e[0])) for e in batch], type=pa.int8()),
                "valid_from": pa.array([valid_from] * len(batch), type=pa.string()),
                "valid_to": pa.array([valid_to] * len(batch), type=pa.string()),
            }
        )
        window = str(valid_from or "current")
        # The partition key is `window`, not `valid_from`: a hive key of the same
        # name as a data column shadows it, and the string "current" would come
        # back where the real NULL belongs.
        directory = root / _SAFE.sub("_", table_id) / f"window={_SAFE.sub('_', window)}"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "part-00000.parquet"
        pq.write_table(table, target, compression=compression, use_dictionary=True)
        written.append(
            ReferenceTable(
                table_id=table_id,
                valid_from=valid_from,
                valid_to=valid_to,
                rows=table.num_rows,
                relative_path=str(target.relative_to(Path(lake_root))).replace("\\", "/"),
                source_ref=str(batch[0][3]),
                code_widths=tuple(sorted({len(str(e[0])) for e in batch})),
            )
        )

    for row in cursor:
        key = (str(row[0]), row[1], row[2])
        if key != current_key:
            _flush()
            current_key = key
            batch = []
        batch.append((row[3], row[4], row[5], row[6], row[7]))
    _flush()
    return written


def flag_mixed_width_tables(catalog: Catalog, tables: Sequence[ReferenceTable]) -> int:
    """Record any reference table that merges two code widths.

    Not a defect in the ingestion — it is what the kit ships — but a hazard the
    consumer has to know about, because the two widths are different
    classifications with overlapping numeric ranges.
    """
    flagged = 0
    for t in tables:
        if not t.mixed_widths:
            continue
        flagged += 1
        catalog.note_question(
            f"reference.mixed_code_widths:{t.table_id}",
            area="semantics",
            question=(
                f"Reference table {t.table_id} ({t.window}) mixes code widths {list(t.code_widths)}, "
                f"which means it merges more than one classification vintage in a single file. "
                f"Joining on code alone can label data from one vintage with the other's meanings."
            ),
            verification_procedure=(
                "Filter the reference table by `code_width` matching the width actually observed "
                "in the column being decoded, and confirm against the record layout's declared "
                "width for that field."
            ),
            blocking=f"safe decoding of fields bound to {t.table_id}",
        )
    return flagged


def read_reference_table(
    lake_root: str | Path,
    table_id: str,
    *,
    valid_from: str | None = None,
    year: int | None = None,
    code_width: int | None = None,
) -> pa.Table:
    """Load one reference table, optionally the vintage covering a given year.

    Asking for a ``year`` picks the window that contains it, which is the whole
    point of keeping the windows apart: a 1995 admission decodes against the
    1992–1997 table, not against today's.
    """
    base = Path(lake_root) / "reference" / _SAFE.sub("_", table_id)
    if not base.exists():
        raise FileNotFoundError(
            f"no reference table {table_id!r} in the lake; run `pegasus-data reference`"
        )
    dataset = pads.dataset(base, format="parquet", partitioning="hive")
    table = dataset.to_table()
    if code_width is not None and "code_width" in table.schema.names:
        table = table.filter(
            pa.array([w == code_width for w in table.column("code_width").to_pylist()])
        )
    if valid_from is not None:
        mask = [v == valid_from for v in table.column("valid_from").to_pylist()]
        return table.filter(pa.array(mask))
    if year is not None:
        competencia = year * 100
        dated: list[bool] = []
        current: list[bool] = []
        for start, end in zip(
            table.column("valid_from").to_pylist(), table.column("valid_to").to_pylist(), strict=True
        ):
            if start is None or not str(start).isdigit():
                dated.append(False)
                current.append(True)  # the open-ended table published today
                continue
            lo = int(start)
            hi = int(end) if end and str(end).isdigit() else 999912
            dated.append(lo <= competencia + 12 and competencia <= hi)
            current.append(False)
        # A window that explicitly covers the year wins; otherwise the current
        # table stands in, and the caller can see which it got from `valid_from`.
        matched = table.filter(pa.array(dated))
        if matched.num_rows:
            return matched
        fallback = table.filter(pa.array(current))
        return fallback if fallback.num_rows else table
    return table


def register_reference_tables(catalog: Catalog, tables: Sequence[ReferenceTable]) -> int:
    catalog.executemany(
        """
        INSERT INTO lake_datasets (dataset, system, series, family_ids, description)
        VALUES (?, NULL, NULL, NULL, ?)
        ON CONFLICT(dataset) DO UPDATE SET description=excluded.description
        """,
        [
            (
                f"ref_{t.table_id.lower()}",
                f"reference table {t.table_id}, {t.rows} codes, window {t.window}, from {t.source_ref}",
            )
            for t in tables
        ],
    )
    return len(tables)


def available_tables(lake_root: str | Path) -> list[dict[str, object]]:
    root = Path(lake_root) / "reference"
    if not root.exists():
        return []
    out: list[dict[str, object]] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        windows = sorted(
            w.name.split("=", 1)[-1] for w in directory.iterdir() if w.is_dir()
        )
        out.append({"table": directory.name, "windows": windows})
    return out
