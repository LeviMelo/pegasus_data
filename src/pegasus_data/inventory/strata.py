"""Schema strata — the unit of sampling (D2).

The prior scan characterised each *family* from a single file, so
``schema_drift.drift_flag = False`` across all 233 families was absence of
measurement, not evidence of stability. The worked case in the brief: family
``SIHSUS_RD_cc57a5d875`` spans 1992-01 → 2026-05 across 12,101 files and was
described from ``RDAC9201.dbc`` — Acre, January 1992, 35 columns. The
113-column modern schema was invisible.

The fix is to sample by **stratum**, keyed ``(system, series, year)``. A DATASUS
schema is the serialisation of a national paper form, so it varies with time and
system — not with state, and not with month. One file per stratum is therefore
sufficient *and* necessary: fewer misses generations, more buys nothing.

Sampling within a stratum is deterministic (sorted by path) so a re-run picks the
same file and results are reproducible.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog


@dataclass(slots=True)
class Stratum:
    system: str
    series: str | None
    year: int | None
    paths: list[str] = field(default_factory=list)

    @property
    def stratum_id(self) -> str:
        seed = f"{self.system}|{self.series or ''}|{self.year if self.year is not None else ''}"
        return f"{self.system}_{self.series or 'NA'}_{self.year if self.year is not None else 'NA'}_" + hashlib.sha256(
            seed.encode()
        ).hexdigest()[:8]

    @property
    def file_count(self) -> int:
        return len(self.paths)

    def sample_path(self) -> str | None:
        """Deterministic pick: the smallest path in sort order.

        Deliberately *not* "the earliest" — that is what produced the 1992 Acre
        sample. Within a stratum every file shares a year, so any member is
        equally representative and reproducibility is what matters.
        """
        return min(self.paths) if self.paths else None


def build_strata(rows: Iterable[dict[str, object]]) -> list[Stratum]:
    """Group parsed file facts into ``(system, series, year)`` strata.

    Files whose year could not be decided (an ambiguous directory convention)
    still get a stratum with ``year = None`` rather than being dropped — an
    undated file is a coverage question, not a non-file.
    """
    groups: dict[tuple[str, str | None, int | None], Stratum] = {}
    for row in rows:
        system = str(row.get("system") or "UNKNOWN")
        series = row.get("series_prefix")
        year = row.get("year")
        key = (system, str(series) if series else None, int(year) if year is not None else None)
        stratum = groups.get(key)
        if stratum is None:
            stratum = Stratum(system=key[0], series=key[1], year=key[2])
            groups[key] = stratum
        stratum.paths.append(str(row["path"]))
    for stratum in groups.values():
        stratum.paths.sort()
    return sorted(groups.values(), key=lambda s: (s.system, s.series or "", s.year or 0))


def persist_strata(catalog: Catalog, strata: Sequence[Stratum]) -> int:
    catalog.executemany(
        """
        INSERT INTO strata (stratum_id, system, series, year, file_count, sampled_path, sample_status)
        VALUES (?,?,?,?,?,?, 'pending')
        ON CONFLICT(stratum_id) DO UPDATE SET
            file_count=excluded.file_count,
            sampled_path=COALESCE(strata.sampled_path, excluded.sampled_path)
        """,
        [
            (s.stratum_id, s.system, s.series, s.year, s.file_count, s.sample_path())
            for s in strata
        ],
    )
    members: list[tuple[str, str]] = []
    for s in strata:
        members.extend((s.stratum_id, p) for p in s.paths)
    catalog.executemany(
        "INSERT OR IGNORE INTO stratum_members (stratum_id, path) VALUES (?,?)", members
    )
    return len(strata)


def sample_plan(catalog: Catalog, *, systems: Sequence[str] | None = None, only_pending: bool = True) -> list[dict[str, object]]:
    """The list of files to fetch and profile: one per stratum."""
    clauses = ["sampled_path IS NOT NULL"]
    params: list[object] = []
    if only_pending:
        clauses.append("sample_status = 'pending'")
    if systems:
        clauses.append(f"system IN ({','.join('?' * len(systems))})")
        params.extend(systems)
    rows = catalog.query(
        f"SELECT stratum_id, system, series, year, file_count, sampled_path, sampled_member "
        f"FROM strata WHERE {' AND '.join(clauses)} ORDER BY system, series, year",
        params,
    )
    return [dict(r) for r in rows]


def coverage_by_system(catalog: Catalog) -> list[dict[str, object]]:
    rows = catalog.query(
        """
        SELECT system,
               COUNT(*)                                        AS strata,
               SUM(CASE WHEN sample_status='ok' THEN 1 ELSE 0 END)     AS sampled,
               SUM(CASE WHEN sample_status='failed' THEN 1 ELSE 0 END) AS failed,
               SUM(file_count)                                  AS files,
               MIN(year)                                        AS year_min,
               MAX(year)                                        AS year_max,
               COUNT(DISTINCT schema_signature)                 AS schema_generations
          FROM strata
         GROUP BY system
         ORDER BY files DESC
        """
    )
    return [dict(r) for r in rows]


def merge_strata_by_signature(catalog: Catalog) -> dict[str, list[str]]:
    """Group strata that share a field signature — the raw material for families."""
    out: dict[str, list[str]] = defaultdict(list)
    for row in catalog.query(
        "SELECT stratum_id, schema_signature FROM strata WHERE schema_signature IS NOT NULL"
    ):
        out[row["schema_signature"]].append(row["stratum_id"])
    return dict(out)
