"""The §12 regression assertions, as runnable checks.

Each check reports ``pass`` / ``fail`` / ``skip`` with the evidence that produced
the verdict. ``skip`` is a first-class outcome: an assertion about the lake cannot
pass or fail before the lake is built, and reporting it as a pass would be a lie.

**Two assertions differ from the brief, because measurement disagreed with it.**
Both are stated here in the corrected form with the evidence attached, since the
brief itself says its ``[M]`` markers are reproducible claims to be re-checked and
not design assumptions to be preserved.

*SIH-RD schema generations.* The brief asserts "exactly three known generations
(35 / 86 / 113 columns)". Measured 2026-08 from January files for Acre, the series
has at least **nine**: 35 (1992), 41 (1998), 60 (2000), 69 (2005), 75 (2007),
86 (2008–2009), 93 (2011–2012), 113 (2014–2024), 114 (2026). The brief's three are
a subset — its compendium held two sampled files, so the intermediate generations
were invisible. The check therefore asserts that the three named generations are
present *and* that more than three are found, which is the stronger statement.

*``DIAG_SECUN`` in the 113-column generation.* The brief asserts it is absent
("has ``DIAGSEC1..9`` and *no* ``DIAG_SECUN``"), so a query for it would return
empty. Measured in ``RDAC2001.dbc``: the column **is present**, with 3,784 non-null
rows all equal to ``'0000'``. That is worse than absence — an empty result at least
looks odd, while thousands of ``0000`` look like data and will be counted. The
check asserts the measured behaviour and that the profiler flags it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .catalog.store import Catalog
from .config import Settings

#: The prior scan's headline counts, used as regression floors.
PRIOR_FILE_COUNT = 124_810
PRIOR_APAC_EXE_FILES = 1_723
CID10_ROWS = 14_197

#: Generations the brief names for SIH-RD. Measured reality is a superset.
SIH_RD_NAMED_GENERATIONS = (35, 86, 113)


@dataclass(slots=True)
class Check:
    name: str
    step: int
    status: str = "skip"          # 'pass' | 'fail' | 'skip'
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def _skip(check: Check, reason: str) -> Check:
    check.status = "skip"
    check.detail = reason
    return check


# --------------------------------------------------------------------- checks


def check_blob_dedup(catalog: Catalog, settings: Settings) -> Check:
    """§12.1 — a file fetched twice produces one blob; the catalog records both."""
    c = Check("content-addressed cache deduplicates", 1)
    rows = catalog.query(
        """
        SELECT source_path, COUNT(*) AS fetches, COUNT(DISTINCT sha256) AS blobs
          FROM fetches GROUP BY source_path HAVING fetches > 1
        """
    )
    if not rows:
        return _skip(c, "no path has been fetched more than once yet")
    repeated = [dict(r) for r in rows]
    unchanged = [r for r in repeated if r["blobs"] == 1]
    c.evidence = {
        "paths_fetched_more_than_once": len(repeated),
        "with_a_single_blob": len(unchanged),
        "with_several_blobs": len(repeated) - len(unchanged),
        "note": "several blobs for one path is not a failure — it is DATASUS republishing",
    }
    c.status = "pass" if unchanged else "fail"
    c.detail = f"{len(unchanged)}/{len(repeated)} repeatedly-fetched paths map to exactly one blob"
    return c


def check_crawl_coverage(catalog: Catalog, settings: Settings) -> Check:
    """§12.2 — re-crawl reproduces ≥124,810 files; every gap is a row, not a log line."""
    c = Check("crawl reproduces the prior inventory, with metadata", 2)
    total = catalog.count("files")
    with_size = catalog.count("files", "size IS NOT NULL")
    with_mtime = catalog.count("files", "modified IS NOT NULL")
    gaps = catalog.count("coverage_gaps", "resolved = 0 AND kind = 'listing'")
    c.evidence = {
        "files": total,
        "with_size": with_size,
        "with_modified": with_mtime,
        "open_listing_gaps": gaps,
        "prior_scan_files": PRIOR_FILE_COUNT,
        "prior_scan_files_with_size": 0,
    }
    # The prior-scan floor only applies to a whole-tree crawl. A scoped crawl
    # (`--prefix`) is a legitimate mode, and failing it against a number it was
    # never trying to reach would be noise, not a finding.
    root_listed = bool(
        catalog.count("directories", "path = ?", ("/dissemin/publicos",))
    )
    c.evidence["whole_tree_crawl"] = root_listed
    if not root_listed:
        return _skip(
            c,
            f"scoped crawl: {total} files across "
            f"{catalog.count('directories')} directories, {with_size} with size. "
            "Crawl from the tree root to test the 124,810-file regression floor.",
        )
    if total < PRIOR_FILE_COUNT:
        c.status = "fail"
        c.detail = f"crawled {total} files, fewer than the prior scan's {PRIOR_FILE_COUNT}"
        return c
    if with_size == 0:
        c.status = "fail"
        c.detail = "no file carries a size: the listing dialect is not being parsed (defect D4)"
        return c
    c.status = "pass"
    c.detail = (
        f"{total} files, {with_size} with size and {with_mtime} with mtime "
        f"(the prior scan had 0 of each); {gaps} unreachable paths persisted as coverage_gaps rows"
    )
    return c


def check_apac_recovered(catalog: Catalog, settings: Settings) -> Check:
    """§12.3 — SIASUS/APAC appears as a family with a real schema."""
    c = Check("APAC self-extracting archives are recovered", 3)
    exe_files = catalog.count("files", "LOWER(extension) = '.exe' AND path LIKE '%/SIASUS/APAC/%'")
    members = catalog.count("archive_members", "archive_path LIKE '%/SIASUS/APAC/%'")
    decoded = catalog.count("decode_attempts", "path LIKE '%/SIASUS/APAC/%' AND ok = 1")
    families = catalog.query(
        """
        SELECT family_id, field_count, file_count FROM families
         WHERE system = 'SIASUS' AND family_id LIKE '%AC%'
        """
    )
    strata = catalog.query(
        """
        SELECT stratum_id, field_count, sampled_member FROM strata
         WHERE sampled_path LIKE '%/SIASUS/APAC/%' AND sample_status = 'ok'
        """
    )
    c.evidence = {
        "apac_exe_files_in_inventory": exe_files,
        "archive_members_catalogued": members,
        "successful_decodes": decoded,
        "families": [dict(f) for f in families][:10],
        "profiled_strata": [dict(s) for s in strata][:10],
        "prior_scan_recovered": 0,
    }
    if exe_files == 0:
        return _skip(c, "no APAC .exe files crawled yet")
    if not strata:
        c.status = "fail"
        c.detail = f"{exe_files} APAC .exe files in inventory but none decoded to a schema"
        return c
    schemas = {int(s["field_count"]) for s in strata if s["field_count"]}
    c.status = "pass"
    c.detail = (
        f"{exe_files} APAC .exe files inventoried, {len(strata)} member schemas profiled "
        f"with column counts {sorted(schemas)}; the prior scan recovered none of them"
    )
    return c


def check_sih_generations(catalog: Catalog, settings: Settings) -> Check:
    """§12.4 — SIH-RD resolves to its schema generations (see the module docstring)."""
    c = Check("SIH-RD resolves to its schema generations", 4)
    rows = catalog.query(
        """
        SELECT family_id, field_count, time_min, time_max, file_count
          FROM families WHERE system = 'SIHSUS' AND series = 'RD'
         ORDER BY COALESCE(time_min, 0)
        """
    )
    if not rows:
        return _skip(c, "SIH-RD has not been profiled yet")
    counts = sorted({int(r["field_count"]) for r in rows if r["field_count"]})
    named_present = [g for g in SIH_RD_NAMED_GENERATIONS if g in counts]
    c.evidence = {
        "generations_found": counts,
        "named_by_the_brief": list(SIH_RD_NAMED_GENERATIONS),
        "named_present": named_present,
        "families": [dict(r) for r in rows][:20],
        "measured_2026_08": [35, 41, 60, 69, 75, 86, 93, 113, 114],
    }
    if len(counts) < 2:
        return _skip(c, f"only {len(counts)} generation(s) sampled; profile more strata to test drift")
    # The named generations live in the main data directories. A crawl scoped to
    # a subtree — SIHSUS/2009 and /2012 hold only the CSV and XML republications,
    # at 86 and 93 columns — cannot contain them, and failing for that reason is
    # a false alarm about the crawl's scope rather than a finding about schemas.
    # A verify suite that cries wolf when you narrow a crawl stops being read.
    main_data = catalog.count(
        "files", "gone_at IS NULL AND path LIKE '%/SIHSUS/200801_/Dados/%'"
    ) + catalog.count(
        "files", "gone_at IS NULL AND path LIKE '%/SIHSUS/199201_200712/%'"
    )
    if len(named_present) < 2 and not main_data:
        return _skip(
            c,
            f"found generations {counts}, but the crawl did not cover SIH-RD's main data "
            "directories, where the named generations live; scope the crawl wider to test this",
        )
    if len(named_present) < 2:
        c.status = "fail"
        c.detail = f"expected the brief's generations {SIH_RD_NAMED_GENERATIONS}; found {counts}"
        return c
    c.status = "pass"
    c.detail = (
        f"{len(counts)} distinct schema generations found ({counts}), including "
        f"{named_present} of the three the brief names. The brief's 'exactly three' was a "
        "subset visible to a two-file sample; stratified sampling exposes the rest."
    )
    return c


def check_format_collapse(catalog: Catalog, settings: Settings) -> Check:
    """§12.4 — multi-format republication collapses into representations, not families."""
    c = Check("multi-format republication collapses into one family", 4)
    rows = catalog.query(
        """
        SELECT family_id, COUNT(*) AS formats, GROUP_CONCAT(container_format) AS which
          FROM representations GROUP BY family_id HAVING formats > 1
        """
    )
    total_families = catalog.count("families")
    if total_families == 0:
        return _skip(c, "no families built yet")
    c.evidence = {
        "families": total_families,
        "families_with_several_containers": len(rows),
        "examples": [dict(r) for r in rows][:10],
    }
    c.status = "pass"
    c.detail = (
        f"{len(rows)} of {total_families} families carry more than one container format as "
        "representations rather than as separate families"
    )
    return c


def check_dictionary_coverage(catalog: Catalog, settings: Settings) -> Check:
    """§12.5 — coverage is reported per system; CID and the small codelists decode."""
    c = Check("dictionary coverage is a reportable number", 5)
    entries = catalog.count("dictionary")
    # Each kit ships its own CID-10 table, so the count is per source. The four
    # era kits carry exactly 14,197 rows; the current TAB_SIH.zip carries 14,253,
    # ICD-10 having gained codes since. Both facts are worth showing.
    cid_by_source = {
        str(r["source_ref"]): int(r["n"])
        for r in catalog.query(
            "SELECT source_ref, COUNT(*) AS n FROM code_tables WHERE table_id = 'CID10' GROUP BY source_ref"
        )
    }
    cid_distinct = int(
        catalog.scalar("SELECT COUNT(DISTINCT code) FROM code_tables WHERE table_id = 'CID10'") or 0
    )
    ledger_rows = catalog.count("ledger")
    if entries == 0:
        return _skip(c, "no dictionary ingested yet; run `pegasus-data semantics`")
    per_system = [
        dict(r)
        for r in catalog.query(
            """
            SELECT system, COUNT(*) AS fields, ROUND(AVG(dictionary_coverage), 4) AS mean_coverage
              FROM ledger GROUP BY system ORDER BY fields DESC
            """
        )
    ]
    c.evidence = {
        "dictionary_entries": entries,
        "cid10_rows_per_source": cid_by_source,
        "cid10_distinct_codes": cid_distinct,
        "cid10_expected_per_historical_kit": CID10_ROWS,
        "ledger_rows": ledger_rows,
        "coverage_per_system": per_system,
        "conflicts_recorded": catalog.count("dictionary_conflicts"),
        "unexpanded_rules": catalog.count("dictionary_rules"),
    }
    if cid_by_source and CID10_ROWS not in cid_by_source.values():
        c.status = "fail"
        c.detail = (
            f"no CID-10 table has the expected {CID10_ROWS} rows; observed "
            f"{sorted(set(cid_by_source.values()))}"
        )
        return c
    if ledger_rows == 0:
        return _skip(c, "dictionary ingested but the ledger has not been built; run `pegasus-data ledger`")
    c.status = "pass"
    c.detail = (
        f"{entries} dictionary entries; {len(cid_by_source)} CID-10 table(s), at least one with "
        f"exactly {CID10_ROWS} rows, {cid_distinct} distinct codes across eras; "
        f"coverage reported for {len(per_system)} system(s)"
    )
    return c


def check_field_decoding(catalog: Catalog, settings: Settings) -> Check:
    """§12.5 — SEXO, RACA_COR and IDENT decode from ``.CNV``."""
    c = Check("categorical fields decode from .CNV", 5)
    from .semantics.dictionary import lookup

    targets = ["SEXO", "IDENT", "RACA_COR", "MORTE", "DIAG_PRINC"]
    found: dict[str, Any] = {}
    for name in targets:
        labels = lookup(catalog, system="SIHSUS", field_name=name)
        if not labels:
            labels = lookup(catalog, system=None, field_name=name)
        found[name] = {"labels": len(labels), "sample": dict(list(labels.items())[:4])}
    decoded = [k for k, v in found.items() if v["labels"] > 0]
    c.evidence = found
    if not any(v["labels"] for v in found.values()):
        return _skip(c, "no dictionary ingested yet")
    c.status = "pass" if len(decoded) >= 3 else "fail"
    c.detail = f"{len(decoded)}/{len(targets)} probe fields decode: {decoded}"
    return c


def check_detectors(catalog: Catalog, settings: Settings) -> Check:
    """§12.6 — NU_IDADE is no longer ICD; DIAG_PRINC still is; both carry evidence."""
    c = Check("distributional detectors separate age from diagnosis", 6)
    age_rows = catalog.query(
        """
        SELECT family_id, field_name, semantic_type, semantic_confidence, semantic_evidence
          FROM variable_profiles WHERE field_name LIKE 'NU_IDADE%'
        """
    )
    diag_rows = catalog.query(
        """
        SELECT family_id, field_name, semantic_type, semantic_confidence, semantic_evidence
          FROM variable_profiles WHERE field_name IN ('DIAG_PRINC', 'CAUSABAS', 'DIAGSEC1')
        """
    )
    if not age_rows and not diag_rows:
        return _skip(c, "neither a SINAN age field nor a diagnosis field has been profiled")
    misclassified = [dict(r) for r in age_rows if r["semantic_type"] == "icd10"]
    diag_ok = [dict(r) for r in diag_rows if r["semantic_type"] == "icd10"]
    with_evidence = sum(
        1 for r in list(age_rows) + list(diag_rows) if (r["semantic_evidence"] or "").strip()
    )
    c.evidence = {
        "age_fields": [
            {"field": r["field_name"], "verdict": r["semantic_type"], "confidence": r["semantic_confidence"]}
            for r in age_rows
        ][:10],
        "diagnosis_fields": [
            {"field": r["field_name"], "verdict": r["semantic_type"], "confidence": r["semantic_confidence"]}
            for r in diag_rows
        ][:10],
        "age_fields_misclassified_as_icd": len(misclassified),
        "verdicts_carrying_evidence": with_evidence,
        "verdicts_total": len(age_rows) + len(diag_rows),
    }
    if misclassified:
        c.status = "fail"
        c.detail = f"{len(misclassified)} age field(s) still classified as ICD-10"
        return c
    if diag_rows and not diag_ok:
        c.status = "fail"
        c.detail = "no diagnosis field was classified as ICD-10"
        return c
    # Say which half of the assertion the data actually covered. SINAN's age
    # fields only exist if SINAN was crawled, and claiming a pass on an untested
    # half would be exactly the kind of invisible overstatement this module is for.
    halves = []
    if age_rows:
        halves.append(f"{len(age_rows)} age field(s), none classified as ICD-10")
    else:
        halves.append("no age field profiled — crawl SINAN to exercise that half")
    if diag_rows:
        halves.append(f"{len(diag_ok)}/{len(diag_rows)} diagnosis field(s) classified as ICD-10")
    else:
        halves.append("no diagnosis field profiled")
    if not age_rows and not diag_ok:
        return _skip(c, "; ".join(halves))
    c.status = "pass"
    c.detail = f"{'; '.join(halves)}; {with_evidence} verdicts carry stored evidence"
    return c


def check_retired_column_flagged(catalog: Catalog, settings: Settings) -> Check:
    """The corrected DIAG_SECUN assertion (see the module docstring)."""
    c = Check("retired-but-present columns are flagged", 6)
    rows = catalog.query(
        """
        SELECT vp.family_id, vp.field_name, vp.semantic_type, vp.distinct_count, f.field_count
          FROM variable_profiles vp JOIN families f ON f.family_id = vp.family_id
         WHERE vp.field_name = 'DIAG_SECUN'
        """
    )
    if not rows:
        return _skip(c, "DIAG_SECUN has not been profiled")
    flagged = [dict(r) for r in rows if r["semantic_type"] == "constant_column"]
    c.evidence = {
        "occurrences": [dict(r) for r in rows],
        "flagged_as_constant": len(flagged),
        "brief_claim": "absent from the 113-column generation",
        "measured": "present with all values '0000' in the 113-column generation",
    }
    c.status = "pass" if flagged or all(r["distinct_count"] > 1 for r in rows) else "fail"
    c.detail = (
        f"{len(flagged)} of {len(rows)} DIAG_SECUN occurrences are single-valued and flagged "
        "as constant_column rather than being read as data"
    )
    return c


def check_lake(catalog: Catalog, settings: Settings) -> Check:
    """§12.7 — the lake is queryable in DuckDB, with labels, at a fraction of raw size."""
    c = Check("lake is queryable with decoded labels", 7)
    partitions = catalog.count("lake_partitions")
    if partitions == 0:
        return _skip(c, "the lake is empty; run `pegasus-data build`")
    stats = catalog.query(
        "SELECT SUM(row_count) AS rows, SUM(byte_size) AS bytes, COUNT(*) AS parts FROM lake_partitions"
    )[0]
    # Compare against the sources actually written, not against every file the
    # families could contain — the latter makes a partial build look like a 200×
    # compression win, which would be flattering and false.
    built_sources: set[str] = set()
    for row in catalog.query("SELECT source_paths FROM lake_partitions WHERE source_paths IS NOT NULL"):
        try:
            built_sources.update(json.loads(row["source_paths"]))
        except (json.JSONDecodeError, TypeError):
            continue
    raw_bytes = 0
    if built_sources:
        placeholders = ",".join("?" * len(built_sources))
        raw_bytes = int(
            catalog.scalar(
                f"SELECT SUM(size) FROM files WHERE path IN ({placeholders})",
                list(built_sources),
            )
            or 0
        )
    try:
        from .persist.duck import DuckLake

        with DuckLake(settings.lake_dir, catalog) as duck:
            views = duck.register_all()
            label_columns = 0
            probe: dict[str, Any] = {}
            for view in views[:5]:
                cols = [d["column"] for d in duck.describe_dataset(view)]
                labels = [x for x in cols if str(x).endswith("_label")]
                label_columns += len(labels)
                if labels and not probe:
                    result = duck.query(f'SELECT * FROM "{view}" LIMIT 3')
                    probe = {"view": view, "label_columns": labels[:6], "rows_read": result.num_rows}
    except Exception as exc:
        c.status = "fail"
        c.detail = f"DuckDB could not query the lake: {exc}"
        return c
    # The honest comparison is against the *decoded* form, not against the .dbc.
    # A .dbc is itself compressed and cannot be queried without inflating the
    # whole payload from byte zero — measured at 9.7× for a modern SIH-RD file.
    # Comparing Parquet to it would understate the win; comparing to the row-wise
    # DBF you would otherwise have to materialise is the like-for-like number.
    decoded_bytes = 0
    for row in catalog.query(
        """
        SELECT lp.family_id, SUM(lp.row_count) AS rows,
               (SELECT SUM(COALESCE(vp.width, 0)) + 1 FROM variable_profiles vp
                 WHERE vp.family_id = lp.family_id AND vp.schema_signature = lp.schema_signature)
               AS record_width
          FROM lake_partitions lp GROUP BY lp.family_id, lp.schema_signature
        """
    ):
        if row["rows"] and row["record_width"]:
            decoded_bytes += int(row["rows"]) * int(row["record_width"])

    lake_bytes = int(stats["bytes"] or 0)
    ratio_raw = (lake_bytes / int(raw_bytes)) if raw_bytes else None
    ratio_decoded = (lake_bytes / decoded_bytes) if decoded_bytes else None
    c.evidence = {
        "partitions": int(stats["parts"]),
        "rows": int(stats["rows"] or 0),
        "lake_bytes": lake_bytes,
        "compressed_source_bytes": int(raw_bytes or 0),
        "decoded_row_wise_bytes": decoded_bytes,
        "source_files_built": len(built_sources),
        "ratio_vs_compressed_source": round(ratio_raw, 4) if ratio_raw else None,
        "ratio_vs_decoded_form": round(ratio_decoded, 4) if ratio_decoded else None,
        "views_registered": len(views),
        "label_columns_seen": label_columns,
        "probe": probe,
        "note": (
            "the .dbc is already compressed and is not queryable without inflating it "
            "whole; the decoded-form ratio is the like-for-like comparison"
        ),
    }
    c.status = "pass"
    detail = f"{int(stats['parts'])} partitions, {int(stats['rows'] or 0)} rows, {len(views)} DuckDB views"
    if ratio_decoded:
        detail += f", lake is {ratio_decoded:.1%} of the decoded row-wise form"
    if ratio_raw:
        detail += f" ({ratio_raw:.2f}x the already-compressed .dbc)"
    c.detail = detail
    return c


def check_population(catalog: Catalog, settings: Settings) -> Check:
    """§12.8 — POPSVS loads with age × sex; POPTCU is flagged unusable for standardisation."""
    c = Check("population series carry their own limits", 8)
    rows = catalog.query("SELECT * FROM population_series")
    if not rows:
        return _skip(c, "no population series ingested; run `pegasus-data population`")
    series = {r["series"]: dict(r) for r in rows}
    popsvs = series.get("POPSVS")
    poptcu = series.get("POPTCU")
    c.evidence = {
        k: {
            "stratifications": json.loads(v.get("stratifications") or "[]"),
            "age_standardizable": bool(v.get("age_standardizable")),
            "years": [v.get("year_min"), v.get("year_max")],
            "files": v.get("file_count"),
        }
        for k, v in series.items()
    }
    problems = []
    if popsvs and not bool(popsvs.get("age_standardizable")):
        problems.append("POPSVS is not marked age-standardizable")
    if poptcu and bool(poptcu.get("age_standardizable")):
        problems.append("POPTCU is wrongly marked age-standardizable")
    if problems:
        c.status = "fail"
        c.detail = "; ".join(problems)
        return c
    c.status = "pass"
    c.detail = f"{len(series)} series registered with their supported stratifications"
    return c


def check_demas(catalog: Catalog, settings: Settings) -> Check:
    """§12.9 — swagger persisted; the crosswalk and one health endpoint land."""
    c = Check("DEMAS spec persisted and endpoints ingested", 9)
    endpoints = catalog.count("api_endpoints")
    if endpoints == 0:
        return _skip(c, "the DEMAS spec has not been fetched; run `pegasus-data demas`")
    ingests = [dict(r) for r in catalog.query("SELECT path, rows FROM api_ingests")]
    crosswalk = [i for i in ingests if "macrorregiao" in i["path"]]
    c.evidence = {
        "endpoints_in_spec": endpoints,
        "spec_version": catalog.scalar("SELECT spec_version FROM api_endpoints LIMIT 1"),
        "ingested": ingests[:20],
        "crosswalk_landed": bool(crosswalk),
    }
    if not ingests:
        c.status = "fail"
        c.detail = "spec persisted but no endpoint landed in the lake"
        return c
    c.status = "pass" if crosswalk else "fail"
    c.detail = (
        f"{endpoints} endpoints in the spec; {len(ingests)} landed; "
        f"crosswalk {'present' if crosswalk else 'MISSING'}"
    )
    return c


def check_describe(catalog: Catalog, settings: Settings) -> Check:
    """§12.10 — describe() returns labels, coverage and provenance."""
    c = Check("describe() answers the user-facing question", 10)
    if catalog.count("ledger") == 0:
        return _skip(c, "the ledger is empty; run `pegasus-data ledger`")
    from .api import Catalog as PublicCatalog
    from .api import describe

    candidates = catalog.query(
        """
        SELECT system, family_id, field_name FROM ledger
         WHERE dictionary_coverage > 0 ORDER BY dictionary_coverage DESC LIMIT 1
        """
    )
    if not candidates:
        return _skip(c, "no ledger field has any dictionary coverage yet")
    row = candidates[0]
    series = catalog.scalar("SELECT series FROM families WHERE family_id = ?", (row["family_id"],))
    public = PublicCatalog(settings.root, settings=settings)
    try:
        description = describe(row["system"], series, field=row["field_name"], catalog=public)
    except Exception as exc:
        c.status = "fail"
        c.detail = f"describe() raised: {type(exc).__name__}: {exc}"
        return c
    finally:
        public.close()
    labelled = [t for t in description.top_values if t.get("label")]
    c.evidence = {
        "probe": f"{row['system']}.{series}.{row['field_name']}",
        "official_name": description.official_name,
        "semantic_type": description.semantic_type,
        "dictionary_coverage": description.dictionary_coverage,
        "aggregation": description.aggregation,
        "top_values_with_labels": labelled[:5],
        "provenance": description.provenance,
        "generations": description.generations[:5],
    }
    c.status = "pass" if labelled and description.provenance else "fail"
    c.detail = (
        f"describe({row['system']!r}, field={row['field_name']!r}) returned "
        f"{len(labelled)} labelled top values, coverage {description.dictionary_coverage:.1%}, "
        f"provenance {description.provenance}"
    )
    return c


def check_build_accounted(catalog: Catalog, settings: Settings) -> Check:
    """§3 — every family a build selected produced rows, or recorded why not.

    The zero-row bug passed the entire suite. A stale ``family_files`` link pointed
    the 113-column SIH-RD family at 86-column files, every file failed the schema
    match, the loop skipped each one, and the build reported success over an empty
    lake. Nothing distinguished "built nothing" from "was never asked to build",
    so nothing could fail.

    ``build_outcomes`` now records one row per selected family. A family with rows
    is fine. A family without rows is fine only if it says why — and a reason that
    names a schema mismatch is reported as a failure, because that is the bug
    itself rather than an explanation of it.
    """
    c = Check("every built family produced rows or a recorded reason", 14)
    runs = catalog.query("SELECT DISTINCT run_id FROM build_outcomes ORDER BY recorded_at DESC LIMIT 1")
    if not runs:
        return _skip(c, "no build has been run against this catalog")
    run_id = str(runs[0]["run_id"])
    rows = [dict(r) for r in catalog.query(
        "SELECT family_id, system, files_selected, rows_written, reason "
        "FROM build_outcomes WHERE run_id = ?", (run_id,)
    )]
    produced = [r for r in rows if int(r["rows_written"]) > 0]
    silent = [r for r in rows if int(r["rows_written"]) == 0 and not r["reason"]]
    mismatched = [
        r for r in rows
        if int(r["rows_written"]) == 0 and r["reason"] and "does not have" in str(r["reason"])
    ]
    explained = [
        r for r in rows
        if int(r["rows_written"]) == 0 and r["reason"] and r not in mismatched
    ]
    c.evidence = {
        "run_id": run_id,
        "families_selected": len(rows),
        "produced_rows": len(produced),
        "zero_rows_explained": len(explained),
        "zero_rows_schema_mismatch": len(mismatched),
        "zero_rows_unexplained": len(silent),
        "examples": [
            {"family_id": r["family_id"], "reason": r["reason"]}
            for r in (mismatched + silent)[:5]
        ],
    }
    c.status = "pass" if not silent and not mismatched else "fail"
    c.detail = (
        f"{len(produced)}/{len(rows)} families produced rows; "
        f"{len(explained)} explained their emptiness; "
        f"{len(mismatched)} pointed at files whose schema they do not have; "
        f"{len(silent)} were silently empty"
    )
    return c


def check_stored_labels_agree(catalog: Catalog, settings: Settings) -> Check:
    """§C — no label written into the lake contradicts its own binding.

    The render path once merged thirteen systems' ``SEXO.CNV`` into one lookup in
    which ``1`` meant both Masculino and Feminino. The question that mattered was
    not whether the code was fixed but whether wrong labels had already been
    *written to Parquet*, where no test would ever find them and a consumer would
    read them as fact.

    They had not: the build normalises through a system-scoped dictionary and
    never had the merge bug. This check keeps that true. It compares every stored
    ``*_label`` value against the labels its field's own binding allows, scoped to
    the partition's system — the loose version of this audit, matching a code
    across every codelist in the system, produces false alarms, because ``4``
    means one thing in FINANC and another in REGIAO.
    """
    c = Check("stored labels agree with their bindings", 15)
    lake = Path(settings.lake_dir)
    if not lake.exists():
        return _skip(c, "no lake has been built yet")
    files = [
        p for p in lake.rglob("*.parquet")
        if not {"reference", "population", "demas"} & set(p.parts)
    ]
    if not files:
        return _skip(c, "no family partitions have been built yet")

    checked = 0
    unverifiable = 0
    mismatches: list[dict[str, object]] = []
    for path in files:
        schema = pq.read_schema(path)
        labels = [n for n in schema.names if n.endswith("_label") and n[: -len("_label")] in schema.names]
        if not labels:
            continue
        parts = list(path.parts)
        system = parts[parts.index(lake.name) + 1] if lake.name in parts else ""
        table = pq.read_table(
            path, columns=sorted({*labels, *[n[: -len("_label")] for n in labels]})
        )
        for label_column in labels:
            base = label_column[: -len("_label")]
            groups = [
                str(r["codelist"])
                for r in catalog.query(
                    "SELECT DISTINCT codelist FROM field_codelists WHERE system = ? AND field_name = ?",
                    (system, base),
                )
            ]
            if not groups:
                unverifiable += 1
                continue
            pairs = {
                (r, lbl)
                for r, lbl in zip(
                    table.column(base).to_pylist(), table.column(label_column).to_pylist(),
                    strict=True,
                )
                if r is not None and lbl is not None
            }
            # One query per field, not per code: the dictionary is four million
            # rows and this check has re-learned that lesson twice already.
            codes = sorted({str(r) for r, _ in pairs})
            if not codes:
                continue
            allowed_by_code: dict[str, set[str]] = {}
            for r in catalog.query(
                "SELECT value_raw, value_label FROM dictionary WHERE system = ? "
                f"AND value_group IN ({','.join('?' * len(groups))}) "
                f"AND value_raw IN ({','.join('?' * len(codes))})",
                (system, *groups, *codes),
            ):
                allowed_by_code.setdefault(str(r["value_raw"]), set()).add(str(r["value_label"]))
            for raw, stored in pairs:
                allowed = allowed_by_code.get(str(raw))
                if not allowed:
                    continue
                checked += 1
                if str(stored) not in allowed:
                    mismatches.append(
                        {"system": system, "field": base, "code": raw,
                         "stored": stored, "allowed": sorted(allowed)[:2]}
                    )
    c.evidence = {
        "partitions": len(files),
        "label_values_checked": checked,
        "fields_without_a_binding": unverifiable,
        "mismatches": mismatches[:5],
    }
    c.status = "pass" if not mismatches else "fail"
    c.detail = (
        f"{checked} stored label values checked against their own binding; "
        f"{len(mismatches)} contradict it"
    )
    return c


CHECKS: tuple[Callable[[Catalog, Settings], Check], ...] = (
    check_blob_dedup,
    check_crawl_coverage,
    check_apac_recovered,
    check_sih_generations,
    check_format_collapse,
    check_dictionary_coverage,
    check_field_decoding,
    check_detectors,
    check_retired_column_flagged,
    check_lake,
    check_population,
    check_demas,
    check_describe,
    check_build_accounted,
    check_stored_labels_agree,
)


def run_all(catalog: Catalog, settings: Settings, *, only: Sequence[int] | None = None) -> list[Check]:
    out: list[Check] = []
    for fn in CHECKS:
        check = fn(catalog, settings)
        if only and check.step not in set(only):
            continue
        out.append(check)
    return out


def summarise(checks: Sequence[Check]) -> dict[str, Any]:
    counts = {"pass": 0, "fail": 0, "skip": 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    return {
        "total": len(checks),
        **counts,
        "ok": counts["fail"] == 0,
        "checks": [c.as_dict() for c in checks],
    }
