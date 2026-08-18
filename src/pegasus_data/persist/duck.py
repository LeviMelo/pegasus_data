"""DuckDB views over the lake, so a consumer writes SQL and nothing else.

The point of §7.3's closing sentence: someone should be able to query ``sih_rd``
without knowing anything about partitioning, schema signatures, or the fact that
the same records were published in four containers.

Dataset names are derived from ``(system, series)`` and registered in
``lake_datasets``. Where a series has several schema generations, the view unions
them **by name** with the union of their columns, and a column absent from a
generation is NULL *in that generation only* — which is visible and honest,
unlike a silently dropped column. ``describe_dataset`` reports exactly which
generations carry which column so a consumer can see it before writing a filter.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pyarrow as pa

from ..catalog.store import Catalog

_SAFE_NAME = re.compile(r"[^a-z0-9_]+")


def dataset_name(system: str, series: str | None) -> str:
    base = f"{system}_{series}" if series else system
    return _SAFE_NAME.sub("_", base.lower()).strip("_")


class DuckLake:
    """A DuckDB connection with views registered over the Parquet lake."""

    def __init__(
        self,
        lake_root: str | Path,
        catalog: Catalog | None = None,
        *,
        database: str = ":memory:",
        read_only: bool = False,
    ) -> None:
        self.lake_root = Path(lake_root)
        self.catalog = catalog
        self.conn = duckdb.connect(database, read_only=read_only)
        self.conn.execute("SET enable_progress_bar = false")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> DuckLake:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- registration

    def register_family(self, system: str, family_id: str, view: str | None = None) -> str | None:
        base = self.lake_root / system / family_id
        if not base.exists():
            return None
        name = view or _SAFE_NAME.sub("_", family_id.lower())
        glob = str(base / "**" / "*.parquet").replace("\\", "/")
        self.conn.execute(
            f'CREATE OR REPLACE VIEW "{name}" AS '
            f"SELECT * FROM read_parquet('{glob}', hive_partitioning = true, union_by_name = true)"
        )
        return name

    def register_all(self) -> list[str]:
        """Register one view per family plus one union view per ``(system, series)``."""
        if self.catalog is None:
            return self._register_from_disk()
        registered: list[str] = []
        by_series: dict[tuple[str, str | None], list[str]] = {}
        for row in self.catalog.query("SELECT family_id, system, series FROM families"):
            name = self.register_family(row["system"], row["family_id"])
            if name:
                registered.append(name)
                by_series.setdefault((row["system"], row["series"]), []).append(name)

        dataset_rows: list[tuple[object, ...]] = []
        for (system, series), views in by_series.items():
            name = dataset_name(system, series)
            if not name or not views:
                continue
            union = " UNION ALL BY NAME ".join(f'SELECT * FROM "{v}"' for v in views)
            self.conn.execute(f'CREATE OR REPLACE VIEW "{name}" AS {union}')
            registered.append(name)
            dataset_rows.append(
                (
                    name, system, series, ",".join(views),
                    f"{system} {series or ''}".strip() + f" — {len(views)} schema generation(s)",
                )
            )
        # Registering views is a read-only act as far as the lake is concerned;
        # recording the dataset names is a convenience. A caller holding the
        # catalog read-only (`verify`, `describe`) still gets its views.
        if not self.catalog.read_only:
            self.catalog.executemany(
                """
                INSERT INTO lake_datasets (dataset, system, series, family_ids, description)
                VALUES (?,?,?,?,?)
                ON CONFLICT(dataset) DO UPDATE SET
                    system=excluded.system, series=excluded.series,
                    family_ids=excluded.family_ids, description=excluded.description
                """,
                dataset_rows,
            )
        return registered

    def _register_from_disk(self) -> list[str]:
        registered: list[str] = []
        for system_dir in sorted(p for p in self.lake_root.iterdir() if p.is_dir()):
            for family_dir in sorted(p for p in system_dir.iterdir() if p.is_dir()):
                name = self.register_family(system_dir.name, family_dir.name)
                if name:
                    registered.append(name)
        return registered

    # -------------------------------------------------------------------- use

    def sql(self, statement: str, params: Sequence[object] | None = None) -> duckdb.DuckDBPyRelation:
        """Run SQL and return DuckDB's own relation, for chaining."""
        return self.conn.sql(statement, params=list(params or []))

    def query(self, statement: str, params: Sequence[object] | None = None) -> pa.Table:
        """Run SQL and return a materialised Arrow table."""
        return self.conn.execute(statement, list(params or [])).fetch_arrow_table()

    def tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT table_name FROM information_schema.tables ORDER BY table_name"
        ).fetchall()
        return [str(r[0]) for r in rows]

    def describe_dataset(self, name: str) -> list[dict[str, object]]:
        rows = self.conn.execute(f'DESCRIBE "{name}"').fetchall()
        return [{"column": r[0], "type": r[1]} for r in rows]
