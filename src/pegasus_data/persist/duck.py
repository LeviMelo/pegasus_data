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
from typing import Any

import duckdb
import pyarrow as pa

from ..catalog.store import CatalogStore

_SAFE_NAME = re.compile(r"[^a-z0-9_]+")


def dataset_name(system: str, series: str | None) -> str:
    base = f"{system}_{series}" if series else system
    return _SAFE_NAME.sub("_", base.lower()).strip("_")


class DuckLake:
    """A DuckDB connection with views registered over the Parquet lake."""

    def __init__(
        self,
        lake_root: str | Path,
        catalog: CatalogStore | None = None,
        *,
        database: str = ":memory:",
        read_only: bool = False,
    ) -> None:
        self.lake_root = Path(lake_root)
        self.catalog = catalog
        self._owned_catalog: Any = None
        self.conn = duckdb.connect(database, read_only=read_only)
        self.conn.execute("SET enable_progress_bar = false")

    def close(self) -> None:
        self.conn.close()
        # `open_lake()` attaches the CatalogStore it opened here. Without this the
        # DuckDB connection closed and the catalog connection did not, leaving
        # it with no reachable owner — one leaked per open_lake() call.
        owned = getattr(self, "_owned_catalog", None)
        if owned is not None:
            owned.close()
            self._owned_catalog = None

    def __enter__(self) -> DuckLake:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- registration

    def register_family(self, system: str, family_id: str, view: str | None = None,
                        files: Sequence[str] | None = None) -> str | None:
        """A view over one family. ``files`` (lake-relative paths) are the partitions to read, as `query()` chooses them
        (`register_all`); without them, every file under the family's directory."""
        base = self.lake_root / system / family_id
        if not base.exists():
            return None
        name = view or _SAFE_NAME.sub("_", family_id.lower())
        if files is not None:
            paths = [str(self.lake_root / f).replace("\\", "/") for f in files]
            if not paths:
                return None
            source = "[" + ", ".join(f"'{q}'" for q in paths) + "]"
        else:
            source = "'" + str(base / "**" / "*.parquet").replace("\\", "/") + "'"
        # The partition keys from the path, not by DuckDB's Hive detection: DuckDB matches names case-insensitively, and
        # a file's own field of a key's name (SINAN's national dengue files carry `UF`) read as the partition's value,
        # "BR". A key a file's field already names is `partition_<key>`. The record key is not here: the lake computes
        # it per file (`Lake._read_derived`), and over files of different columns a view would hash a missing one as null.
        import pyarrow.parquet as pq

        first = (self.lake_root / files[0]) if files else next(base.rglob("*.parquet"), None)
        taken = {f.lower() for f in (pq.read_schema(first).names if first is not None else [])}
        keys = []
        for key in ("schema_signature", "uf", "year"):
            value = "regexp_extract(filename, '" + key + r"=([^/\\]+)', 1)"
            keys.append(f"{f'CAST({value} AS INTEGER)' if key == 'year' else value} AS "
                        f"{f'partition_{key}' if key in taken else key}")
        self.conn.execute(
            f'CREATE OR REPLACE VIEW "{name}" AS SELECT * EXCLUDE (filename), {", ".join(keys)} '
            f"FROM read_parquet({source}, hive_partitioning = false, union_by_name = true, filename = true)"
        )
        return name

    def register_all(self) -> list[str]:
        """Register one view per family plus one union view per ``(system, series)``."""
        if self.catalog is None:
            return self._register_from_disk()
        registered: list[str] = []
        by_series: dict[tuple[str, str | None], list[str]] = {}
        # The files `query()` reads, never a walk of the directories: the partitions the catalog lists (a superseded
        # family's are delisted, `persist.lake._delist_superseded`), and of a year held as a national file and as its
        # state files, the national one (`one_reading`). The views globbed each family's directory, a second reading
        # beside the query engine's, and study scripts that globbed the lake the same way mixed SIH's rejected AIHs (RJ)
        # into RD cohorts (2026-11-22).
        from .._query_engine.coverage import declared_widths, one_reading
        from .lake import listed_partitions

        rows = [dict(r) for r in self.catalog.query("SELECT family_id, system, series FROM families")]
        groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault((row["system"], row["series"]), []).append(row)
        listed = listed_partitions(self.catalog, sorted({str(r["family_id"]) for r in rows}))
        widths = declared_widths(self.catalog)
        held: dict[tuple[str, str | None], set[tuple[int, str]]] = {}
        for (system, series), members in groups.items():
            chosen = one_reading([p for m in members for p in listed.get(str(m["family_id"]), ())], widths)
            held[(system, series)] = {(int(p.year), str(p.uf)) for p in chosen if p.year is not None}
            files: dict[str, list[str]] = {}
            for part in sorted(chosen, key=lambda p: (p.uf, p.year, p.relative_path)):
                files.setdefault(part.family_id, []).append(part.relative_path)
            for row in members:
                name = self.register_family(system, row["family_id"], files=files.get(str(row["family_id"]), []))
                if name:
                    registered.append(name)
                    by_series.setdefault((system, series), []).append(name)

        dataset_rows: list[tuple[object, ...]] = []
        holding_rows: list[tuple[str, int, str]] = []
        for (system, series), views in by_series.items():
            name = dataset_name(system, series)
            if not name or not views:
                continue
            union = " UNION ALL BY NAME ".join(f'SELECT * FROM "{v}"' for v in views)
            self.conn.execute(f'CREATE OR REPLACE VIEW "{name}" AS {union}')
            registered.append(name)
            hy: dict[int, set[str]] = {}
            for y, uf in held.get((system, series), ()):
                hy.setdefault(y, set()).add(uf)
            holding_rows.extend((name, y, uf) for y, ufs in hy.items() for uf in ufs)
            # what the view holds, said where a reader looks: a view of three states' 2023 SIH-SP read as the country
            # (t08, 2026-11-24). `lake_holdings` lists every (dataset, year, uf) a view reads.
            partial = sorted(y for y, ufs in hy.items() if len(ufs) < 27 and not ({"BR", "00"} & ufs))
            dataset_rows.append(
                (
                    name, system, series, ",".join(views),
                    f"{system} {series or ''}".strip() + f" — {len(views)} schema generation(s)"
                    + (f"; partial: {', '.join(f'{y} ({len(hy[y])} states)' for y in partial)}" if partial else ""),
                )
            )
        self.conn.execute("CREATE OR REPLACE TEMP TABLE lake_holdings(dataset VARCHAR, year INTEGER, uf VARCHAR)")
        if holding_rows:
            self.conn.executemany("INSERT INTO lake_holdings VALUES (?, ?, ?)", holding_rows)
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
        for system_dir in sorted(p for p in self.lake_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
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
        return self.conn.execute(statement, list(params or [])).to_arrow_table()

    def tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT table_name FROM information_schema.tables ORDER BY table_name"
        ).fetchall()
        return [str(r[0]) for r in rows]

    def describe_dataset(self, name: str) -> list[dict[str, object]]:
        rows = self.conn.execute(f'DESCRIBE "{name}"').fetchall()
        return [{"column": r[0], "type": r[1]} for r in rows]
