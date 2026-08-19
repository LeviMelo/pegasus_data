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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog


@dataclass(slots=True)
class Stratum:
    system: str
    series: str | None
    year: int | None
    paths: list[str] = field(default_factory=list)
    #: ``path -> byte size``, where the crawl recorded one. Used only to pick the
    #: cheapest representative; an absent size sorts last so it is never
    #: preferred over a file whose cost is known.
    sizes: dict[str, int] = field(default_factory=dict)

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
        """The cheapest representative, then path order to break ties.

        Deliberately *not* "the earliest" — that is what produced the 1992 Acre
        sample. Within a stratum every file shares a system, series and year, so
        every member has the same schema and any of them answers the question the
        sample is asked. Given that, the only thing left to optimise is cost.

        And the cost varies enormously. A stratum can hold RDAC (Acre, tens of
        KB) beside RDSP (São Paulo, tens of MB), or a single BR-wide national
        file; profiling 4,228 strata means 4,228 downloads, and picking by name
        was picking blind. Sorting by size makes the sweep affordable without
        changing a single answer it produces. Ties break on path so the choice
        stays reproducible.
        """
        if not self.paths:
            return None
        return min(self.paths, key=lambda p: (self.sizes.get(p, 1 << 62), p))


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
        key = (system, str(series) if series else None, int(year) if isinstance(year, (int, float, str)) and str(year).strip() else None)
        stratum = groups.get(key)
        if stratum is None:
            stratum = Stratum(system=key[0], series=key[1], year=key[2])
            groups[key] = stratum
        path = str(row["path"])
        stratum.paths.append(path)
        size = row.get("size")
        if size is not None:
            try:
                stratum.sizes[path] = int(size)
            except (TypeError, ValueError):
                pass
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
    # Membership is replaced, not merged. A correction that moves a file between
    # strata leaves it listed in both if the old rows survive, and the stale entry
    # is enough to keep a stratum's sample — and the schema signature derived from
    # it — pointing at a file that no longer belongs to it.
    catalog.executemany(
        "DELETE FROM stratum_members WHERE stratum_id = ?", [(s.stratum_id,) for s in strata]
    )
    members: list[tuple[str, str]] = []
    for s in strata:
        members.extend((s.stratum_id, p) for p in s.paths)
    catalog.executemany(
        "INSERT OR IGNORE INTO stratum_members (stratum_id, path) VALUES (?,?)", members
    )

    # A stratum id is a hash of (system, series, year), so it survives a
    # re-inventory even when the files that belong to it change. When a
    # correction moves files between strata, the recorded sample — and therefore
    # the schema signature derived from it — can end up describing a file the
    # stratum no longer contains. That is how a 2008 stratum came to claim the
    # 113-column signature of a 2014 file. Invalidate any such stratum so the
    # next profile run re-derives it rather than inheriting a stale answer.
    catalog.execute(
        """
        UPDATE strata
           SET sampled_path = NULL, sampled_member = NULL, schema_signature = NULL,
               field_count = NULL, sample_status = 'pending', sample_error = NULL
         WHERE sampled_path IS NOT NULL
           AND NOT EXISTS (
                SELECT 1 FROM stratum_members m
                 WHERE m.stratum_id = strata.stratum_id AND m.path = strata.sampled_path
           )
        """
    )
    # Re-seed the sample for anything just invalidated, and for anything new.
    catalog.executemany(
        "UPDATE strata SET sampled_path = ? WHERE stratum_id = ? AND sampled_path IS NULL",
        [(s.sample_path(), s.stratum_id) for s in strata if s.sample_path()],
    )
    catalog.conn.commit()
    return len(strata)


def sample_plan(catalog: Catalog, *, systems: Sequence[str] | None = None, only_pending: bool = True) -> list[dict[str, object]]:
    """The list of files to fetch and profile: one per stratum."""
    clauses = ["sampled_path IS NOT NULL"]
    params: list[object] = []
    if only_pending:
        # 'header' means the schema census read this stratum's columns from a
        # file header. That is strictly less than profiling — it says nothing
        # about values — so such a stratum is still OUTSTANDING here. Matching
        # only 'pending' let the cheap census silently disable the expensive
        # stage that follows it: `all` runs schemas before profile, so profile
        # would have found nothing to do and reported success.
        clauses.append("sample_status IN ('pending', 'header')")
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


def prune_orphan_strata(
    catalog: Catalog, keep: set[str], *, systems: Sequence[str] | None = None
) -> int:
    """Drop strata that the current file facts no longer produce.

    Strata are derived data, so re-running ``inventory`` must be able to replace
    them, not merely add to them. Anything keyed on a value that has since been
    corrected — a year, a series — yields a different ``stratum_id``, and the
    stale row would otherwise keep feeding families, drift reports and coverage
    numbers that no longer reflect the catalog.
    """
    clause = ""
    params: list[object] = []
    if systems:
        clause = f" WHERE system IN ({','.join('?' * len(systems))})"
        params = list(systems)
    existing = {str(r["stratum_id"]) for r in catalog.query(f"SELECT stratum_id FROM strata{clause}", params)}
    # Archive-member strata are derived during profiling, not here, and their
    # parent is what inventory knows about; keep them if their parent survives.
    orphans = [
        s for s in existing - keep
        if s.split("#", 1)[0] not in keep or "#" not in s
    ]
    if not orphans:
        return 0
    catalog.executemany("DELETE FROM strata WHERE stratum_id = ?", [(s,) for s in orphans])
    catalog.executemany("DELETE FROM stratum_members WHERE stratum_id = ?", [(s,) for s in orphans])
    return len(orphans)
