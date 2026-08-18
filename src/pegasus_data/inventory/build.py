"""L1 — turn crawled paths into parsed facts, directory conventions, and strata.

Pure computation over the catalog: no network. Runs in seconds over 125k rows and
is idempotent, so it can be re-run after every crawl.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from ..catalog.store import Catalog
from .naming import (
    ParsedName,
    apply_convention,
    infer_date_convention,
    infer_two_digit_epoch,
    parse_filename,
    role_from_path,
    system_from_path,
)
from .strata import build_strata, persist_strata, prune_orphan_strata


def build_inventory(
    catalog: Catalog, *, base_path: str = "/dissemin/publicos", systems: Sequence[str] | None = None
) -> dict[str, int]:
    """Parse every known file, infer per-directory date conventions, persist facts."""
    where = ""
    params: list[object] = []
    if systems:
        clauses = " OR ".join("path LIKE ?" for _ in systems)
        where = f"WHERE {clauses}"
        params = [f"{base_path}/{s}/%" for s in systems]
    rows = catalog.query(f"SELECT path, directory, filename FROM files {where}", params)

    parsed_by_path: dict[str, ParsedName] = {}
    by_directory: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        parsed = parse_filename(row["filename"])
        parsed_by_path[row["path"]] = parsed
        by_directory[row["directory"]].append(row["path"])

    # ---- per-directory convention (§5.2: never decide the date format per file)
    conventions: dict[str, str] = {}
    epochs: dict[str, str] = {}
    ambiguous_dirs: list[str] = []
    for directory, paths in by_directory.items():
        codes: list[str] = []
        keys: list[tuple[str, str]] = []
        for p in paths:
            parsed = parsed_by_path[p]
            if parsed.date_code:
                codes.append(parsed.date_code)
                keys.append((parsed.series_prefix or "", parsed.geo_code or ""))
        convention = infer_date_convention(codes, group_keys=keys) if codes else "none"
        conventions[directory] = convention
        epochs[directory] = infer_two_digit_epoch(codes) if codes else "pivot"
        if convention == "ambiguous":
            ambiguous_dirs.append(directory)

    facts: list[tuple[object, ...]] = []
    for path, parsed in parsed_by_path.items():
        directory = path.rsplit("/", 1)[0]
        convention = conventions.get(directory, "none")
        resolved = apply_convention(parsed, convention, epoch=epochs.get(directory, "pivot"))
        facts.append(
            (
                path,
                system_from_path(path, base_path),
                resolved.series_prefix,
                resolved.geo_code,
                resolved.date_code,
                resolved.date_format,
                resolved.normalized_date,
                resolved.year,
                resolved.grammar,
                resolved.container_format,
                role_from_path(path),
            )
        )

    catalog.executemany(
        """
        INSERT INTO file_facts (path, system, series_prefix, geo_code, date_code, date_format,
                                normalized_date, year, grammar, container_format, role)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
            system=excluded.system, series_prefix=excluded.series_prefix,
            geo_code=excluded.geo_code, date_code=excluded.date_code,
            date_format=excluded.date_format, normalized_date=excluded.normalized_date,
            year=excluded.year, grammar=excluded.grammar,
            container_format=excluded.container_format, role=excluded.role
        """,
        facts,
    )
    catalog.executemany(
        "UPDATE directories SET date_convention=? WHERE path=?",
        [(conv, d) for d, conv in conventions.items()],
    )

    # An undecidable directory is a real open question, not a silent default.
    for directory in ambiguous_dirs:
        catalog.note_question(
            f"naming.ambiguous_date_convention:{directory}",
            area="inventory",
            question=(
                f"Directory {directory} holds 4-digit date codes that parse equally well as "
                "YYMM (competência) and YYYY (year); its members' years are recorded as NULL."
            ),
            verification_procedure=(
                "Decode one member and compare an internal date field (e.g. DT_INTER, DTOBITO, "
                "ANO_CMPT) against both readings; or check whether a sibling directory of the "
                "same series carries an unambiguous code."
            ),
            blocking="stratification of this directory's files",
        )

    strata_rows = [
        {
            "path": f[0], "system": f[1], "series_prefix": f[2], "year": f[7],
        }
        for f in facts
        if f[10] == "data"
    ]
    strata = build_strata(strata_rows)
    # Strata are derived from file facts, so a re-inventory that changes a year
    # produces new stratum ids and orphans the old ones. Leaving them behind is
    # not harmless: a stratum dated 1901 by the bug this replaced kept dragging
    # `families.time_min` back to 1901 long after the facts were corrected.
    pruned = prune_orphan_strata(catalog, {s.stratum_id for s in strata}, systems=systems)
    persist_strata(catalog, strata)

    return {
        "strata_pruned": pruned,
        "files_parsed": len(facts),
        "directories": len(conventions),
        "ambiguous_directories": len(ambiguous_dirs),
        "strata": len(strata),
        "unparsed": sum(1 for f in facts if f[8] == "unparsed"),
    }


def inventory_summary(catalog: Catalog) -> list[dict[str, object]]:
    rows = catalog.query(
        """
        SELECT system,
               COUNT(*)                                              AS files,
               SUM(CASE WHEN role='data' THEN 1 ELSE 0 END)          AS data_files,
               SUM(CASE WHEN role='dictionary' THEN 1 ELSE 0 END)    AS dictionary_files,
               SUM(CASE WHEN role='documentation' THEN 1 ELSE 0 END) AS doc_files,
               SUM(CASE WHEN grammar='unparsed' THEN 1 ELSE 0 END)   AS unparsed,
               COUNT(DISTINCT series_prefix)                         AS series,
               MIN(year) AS year_min, MAX(year) AS year_max
          FROM file_facts
         GROUP BY system
         ORDER BY files DESC
        """
    )
    return [dict(r) for r in rows]
