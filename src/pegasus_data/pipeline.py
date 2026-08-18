"""Stage orchestration: each stage is independently runnable, resumable, idempotent.

Recommended order::

    crawl → inventory → semantics → sample → profile → families → build

``semantics`` deliberately runs *before* ``profile``: the TAB kits supply the
ICD-10, procedure and municipality universes that the distributional detectors
use to turn a structural guess into a checked membership rate. Running it later
still works — ``profile`` just records lower confidences, and re-running it after
``semantics`` upgrades them.

Every stage writes to the catalog before returning, so an interrupted run resumes
from what the catalog knows rather than from a checkpoint file.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .acquire.cache import BlobStore
from .acquire.fetcher import Fetcher
from .catalog.store import Catalog
from .config import Settings
from .decode.registry import ReaderRegistry
from .discovery.crawler import Crawler
from .discovery.https_client import probe_https_mirror
from .inventory.build import build_inventory
from .inventory.families import (
    build_families,
    family_id_for,
    persist_families,
    schema_signature,
)
from .inventory.strata import sample_plan
from .profile.drift import (
    analyse_drift,
    detect_renames,
    persist_drift,
    persist_renames,
)
from .profile.runner import (
    persist_profile,
    profile_table,
    record_decode_attempts,
    record_stratum_schema,
)
from .semantics.dictionary import (
    bind_by_semantic_type,
    bind_codelists_to_fields,
    corroborate_semantic_bindings,
    entries_from_kit,
    persist_bindings,
    persist_entries,
    persist_rules,
)
from .semantics.ledger import build_ledger, persist_ledger
from .semantics.reference import load_reference_sets
from .semantics.tabkit import find_kits, find_loose_dictionaries, parse_kit, persist_kit

#: The `[V]` list from §14, seeded into ``open_questions`` on first run so that
#: every one is tracked whether or not this run happens to close it.
SEED_QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "key": "V1.https_mirror",
        "area": "discovery",
        "question": "Does an HTTPS mirror serve the same tree, restoring Content-Length and Last-Modified?",
        "verification_procedure": "HEAD/GET the same paths over https and compare payload SHA-256 to the FTP fetch for 20 files across 5 systems.",
        "blocking": "cheap incremental sync (superseded if the IIS MS-DOS LIST dialect is parsed, which it now is)",
    },
    {
        "key": "V2.sfx_exe_payload",
        "area": "decode",
        "question": "What is inside SIASUS/APAC/*.EXE, and does opening it recover the APAC series?",
        "verification_procedure": "Unpack /dissemin/publicos/SIASUS/APAC/2002/acac0202.exe and enumerate members.",
        "blocking": "1,723 files and the only patient-anchored longitudinal trail in public data",
    },
    {
        "key": "V3.cnv_def_grammar",
        "area": "semantics",
        "question": "What are the .CNV and .DEF grammars?",
        "verification_procedure": "Learn from the uncompressed files under PNI/AUXILIARES/, then generalise to kit members.",
        "blocking": "the entire semantic layer (P1)",
    },
    {
        "key": "V4.tab_kit_contents",
        "area": "semantics",
        "question": "What lookup tables exist inside each TAB_*.zip kit?",
        "verification_procedure": "Enumerate the members of every kit and catalogue the DBF lookups.",
        "blocking": "procedure, establishment and ICD tables",
    },
    {
        "key": "V5.sigtap_procedure_table",
        "area": "semantics",
        "question": "Is a procedure code table present inside any kit, or must SIGTAP be sourced separately?",
        "verification_procedure": "Search kit members for a procedure table; if absent, check sigtap.datasus.gov.br.",
        "blocking": "amputation and dialysis signals in the companion research plan",
    },
    {
        "key": "V6.duck_storage_version",
        "area": "decode",
        "question": "Can the installed DuckDB open the .duck databases under Dados_Abertos?",
        "verification_procedure": "Open apac_atd.duck.zip; on failure record the storage version from the file header.",
        "blocking": "11 APAC DuckDB databases plus 66 SIASUS PA backups",
    },
    {
        "key": "V7.projpop",
        "area": "denominators",
        "question": "What are the 71 files under IBGE/projpop, and do they supersede POPSVS for projected age structures?",
        "verification_procedure": "Decode PROJUF*.dbf and inspect its stratifications and year coverage.",
        "blocking": "choice of denominator for projected years",
    },
    {
        "key": "V8.ministry_denominator",
        "area": "denominators",
        "question": "Which population series backs the Ministry's own published rates?",
        "verification_procedure": "Reproduce a published TabNet rate from microdata under each candidate series and see which matches.",
        "blocking": "validation of any rate against a federal publication",
    },
    {
        "key": "V9.demas_granularity",
        "area": "api",
        "question": "What granularity do the BNAFAR/Horus, Previne cadastro and Previne indicator endpoints serve?",
        "verification_procedure": "Read the persisted OpenAPI parameters and fetch one page from each endpoint.",
        "blocking": "the pre-decompensation medication signal",
    },
    {
        "key": "V10.dados_abertos_grammar",
        "area": "inventory",
        "question": "What naming grammar does the Dados_Abertos subtree use?",
        "verification_procedure": "Parse its filenames and measure how many remain unparsed.",
        "blocking": "82 families reported UNPARSED by the prior scan",
    },
    {
        "key": "V11.coverage_gaps",
        "area": "discovery",
        "question": "Do the 32 directories that failed to list in the prior scan resolve on retry?",
        "verification_procedure": "Re-crawl with per-directory method escalation; anything still failing persists as a coverage_gaps row.",
        "blocking": "dictionary and documentation directories, i.e. part of P1",
    },
)


@dataclass(slots=True)
class StageResult:
    stage: str
    ok: bool = True
    counts: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {"stage": self.stage, "ok": self.ok, "counts": self.counts, "notes": self.notes}


class Pipeline:
    """Holds the shared objects every stage needs."""

    def __init__(self, settings: Settings, catalog: Catalog | None = None) -> None:
        self.settings = settings
        settings.ensure_dirs()
        self.catalog = catalog or Catalog(settings.catalog_path)
        self.blobs = BlobStore(settings.blobs_dir, self.catalog)
        self.fetcher = Fetcher(
            self.catalog,
            self.blobs,
            host=settings.host,
            concurrency=settings.fetch_concurrency,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
            backoff_base=settings.backoff_base,
        )
        self.seed_questions()

    def close(self) -> None:
        self.catalog.close()

    def seed_questions(self) -> None:
        for q in SEED_QUESTIONS:
            self.catalog.note_question(
                q["key"],
                area=q["area"],
                question=q["question"],
                verification_procedure=q["verification_procedure"],
                blocking=q["blocking"],
            )

    # ------------------------------------------------------------------ crawl

    def crawl(
        self,
        *,
        resume: bool = False,
        prefixes: Sequence[str] | None = None,
        on_progress: Callable[[object], None] | None = None,
    ) -> StageResult:
        crawler = Crawler(
            self.catalog,
            host=self.settings.host,
            connections=self.settings.connections,
            timeout=self.settings.timeout,
            max_retries=self.settings.max_retries,
            backoff_base=self.settings.backoff_base,
            on_progress=on_progress,  # type: ignore[arg-type]
        )
        stats = crawler.crawl(self.settings.base_path, resume=resume, only_prefixes=prefixes)
        with_meta = self.catalog.count("files", "size IS NOT NULL")
        total = self.catalog.count("files")
        self.catalog.resolve_question(
            "V11.coverage_gaps",
            resolution=(
                f"re-crawl listed {stats.directories} directories; "
                f"{stats.gaps} remain unreachable and are recorded as coverage_gaps rows"
            ),
            evidence=json.dumps(stats.as_dict()),
        )
        if total and with_meta / total > 0.99:
            self.catalog.resolve_question(
                "V1.https_mirror",
                resolution=(
                    "No HTTPS mirror is needed and none is reachable: ftp.datasus.gov.br "
                    "accepts nothing on :80 or :443. The metadata the mirror would have "
                    "restored comes instead from parsing the IIS MS-DOS LIST dialect, which "
                    f"supplies size and mtime for {with_meta}/{total} files, plus SIZE/MDTM per file."
                ),
                evidence=json.dumps({"files_with_size": with_meta, "files_total": total}),
            )
        return StageResult("crawl", counts=stats.as_dict())

    def probe_mirror(self, sample_paths: Sequence[str] | None = None) -> StageResult:
        paths = list(sample_paths or [])
        if not paths:
            rows = self.catalog.query("SELECT path FROM files ORDER BY path LIMIT 20")
            paths = [r["path"] for r in rows]
        verdict = probe_https_mirror(paths)
        self.catalog.resolve_question(
            "V1.https_mirror",
            resolution=verdict.summary(),
            evidence=json.dumps([p.as_dict() for p in verdict.probes]),
        )
        return StageResult("probe_mirror", counts={"available": verdict.available, "host": verdict.host})

    # -------------------------------------------------------------- inventory

    def inventory(self, *, systems: Sequence[str] | None = None) -> StageResult:
        counts = build_inventory(self.catalog, base_path=self.settings.base_path, systems=systems)
        unparsed = self.catalog.count("file_facts", "grammar = 'unparsed'")
        total = self.catalog.count("file_facts")
        dados_abertos_unparsed = self.catalog.count(
            "file_facts", "grammar = 'unparsed' AND path LIKE '%Dados_Abertos%'"
        )
        self.catalog.resolve_question(
            "V10.dados_abertos_grammar",
            resolution=(
                "Dados_Abertos does not need a separate grammar. Its filenames are classic "
                "PREFIX+GEO+DATE (DENGBR20.csv.zip); the prior scan's 82 UNPARSED families "
                "came from composite suffixes (.csv.zip/.json.zip/.xml.zip) that its "
                "suffix-stripper only handled for .gz. A small descriptive tail "
                "(apac_atd.duck.zip, siasus_pa_ac.duck) has its own grammar. "
                f"Unparsed now: {dados_abertos_unparsed} in Dados_Abertos, {unparsed} of {total} overall."
            ),
            evidence=json.dumps({**counts, "unparsed_dados_abertos": dados_abertos_unparsed}),
        )
        return StageResult("inventory", counts=counts)

    # -------------------------------------------------------------- semantics

    def semantics(
        self,
        *,
        systems: Sequence[str] | None = None,
        limit: int | None = None,
        pdfs: bool = True,
    ) -> StageResult:
        kits = find_kits(self.catalog, systems=systems)
        loose = find_loose_dictionaries(self.catalog, systems=systems)
        if limit:
            kits = kits[:limit]
        counts: dict[str, object] = {
            "kits_found": len(kits),
            "loose_dictionaries": len(loose),
            "kits_ingested": 0,
            "dictionary_entries": 0,
            "conflicts": 0,
            "rules": 0,
            "code_table_rows": 0,
            "def_variables": 0,
        }
        notes: list[str] = []

        fetched = self.fetcher.ensure(kits)
        kit_reports: list[dict[str, object]] = []
        for path in kits:
            digest = fetched.get(path)
            if not digest:
                notes.append(f"kit unavailable: {path}")
                continue
            system = _system_of(path, self.settings.base_path)
            try:
                kit = parse_kit(self.blobs.read(digest), kit_path=path, system=system)
            except Exception as exc:
                self.catalog.record_gap(path, kind="decode", methods=("kit",), error=str(exc))
                notes.append(f"kit parse failed: {path}: {exc}")
                continue
            stats = persist_kit(self.catalog, kit, sha256=digest)
            entries, bindings, rules = entries_from_kit(kit)
            merged = persist_entries(self.catalog, entries)
            persist_bindings(self.catalog, bindings)
            rule_count = persist_rules(self.catalog, rules, system=system)
            counts["kits_ingested"] = int(counts["kits_ingested"]) + 1
            counts["dictionary_entries"] = int(counts["dictionary_entries"]) + merged["inserted"]
            counts["conflicts"] = int(counts["conflicts"]) + merged["conflicts"]
            counts["rules"] = int(counts["rules"]) + rule_count
            counts["code_table_rows"] = int(counts["code_table_rows"]) + int(stats["code_table_rows"])
            counts["def_variables"] = int(counts["def_variables"]) + int(stats["def_variables"])
            kit_reports.append({"kit": path, **stats})

        # Loose .DEF/.CNV — the cheapest place to start, and the only place some
        # systems (PNI) publish their dictionaries at all.
        loose_fetched = self.fetcher.ensure(loose)
        loose_defs = 0
        loose_cnvs = 0
        # Accumulate every loose .CNV and merge once. Merging per file meant 78
        # passes over a dictionary that is already millions of rows deep.
        loose_entries = []
        for path, digest in loose_fetched.items():
            system = _system_of(path, self.settings.base_path)
            payload = self.blobs.read(digest)
            if path.lower().endswith(".cnv"):
                from .semantics.cnv_parser import parse_cnv_bytes
                from .semantics.dictionary import entries_from_loose_cnv

                cnv = parse_cnv_bytes(payload, name=PurePosixPath(path).name, source_ref=path)
                loose_entries.extend(entries_from_loose_cnv(cnv, system=system))
                loose_cnvs += 1
            elif path.lower().endswith(".def"):
                from .semantics.def_parser import parse_def_bytes

                parsed = parse_def_bytes(payload, name=PurePosixPath(path).name, source_ref=path)
                self.catalog.executemany(
                    """
                    INSERT INTO def_datasets (def_path, system, data_glob, help_ref, title)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(def_path) DO UPDATE SET data_glob=excluded.data_glob, title=excluded.title
                    """,
                    [(path, system, parsed.data_glob, parsed.help_ref, parsed.title)],
                )
                self.catalog.executemany(
                    """
                    INSERT INTO def_variables (def_path, system, usage, display_name, field_name, category_arg, lookup_ref, line_no)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(def_path, usage, display_name, field_name) DO UPDATE SET
                        category_arg=excluded.category_arg, lookup_ref=excluded.lookup_ref
                    """,
                    [
                        (path, system, v.usage, v.display_name, v.field_name, v.category_arg, v.lookup_ref, v.line_no)
                        for v in parsed.variables
                    ],
                )
                counts["def_variables"] = int(counts["def_variables"]) + len(parsed.variables)
                loose_defs += 1

        if loose_entries:
            merged = persist_entries(self.catalog, loose_entries)
            counts["dictionary_entries"] = int(counts["dictionary_entries"]) + merged["inserted"]
            counts["conflicts"] = int(counts["conflicts"]) + merged["conflicts"]

        counts["loose_cnv_parsed"] = loose_cnvs
        counts["loose_def_parsed"] = loose_defs
        counts["codelists_bound"] = bind_codelists_to_fields(self.catalog)

        if pdfs:
            counts.update(self._harvest_pdfs(systems=systems, notes=notes))

        self._close_semantic_questions(counts, kit_reports)
        return StageResult("semantics", counts=counts, notes=notes)

    def _harvest_pdfs(
        self, *, systems: Sequence[str] | None, notes: list[str]
    ) -> dict[str, object]:
        """Supply-chain source #4: the dictionary PDFs.

        Held at lower confidence and never overriding ``.CNV``/``.DEF`` (§6.3). A
        PDF layout table states intent, not the bytes actually written, and the
        two diverge — so anything harvested here loses every conflict against a
        TabNet source and the disagreement is recorded rather than dropped.
        """
        from .semantics.pdf_harvest import (
            documentation_rows,
            entries_from_harvest,
            harvest_pdf,
            known_field_names,
        )

        rows = self.catalog.query(
            "SELECT path FROM files WHERE LOWER(extension) = '.pdf' ORDER BY path"
        )
        paths = [r["path"] for r in rows]
        if systems:
            wanted = {s.upper() for s in systems}
            paths = [p for p in paths if any(f"/{s}/" in p.upper() for s in wanted)]
        if not paths:
            return {"pdfs_found": 0, "pdfs_harvested": 0, "pdf_entries": 0}

        fetched = self.fetcher.ensure(paths)
        # Only columns this catalog has observed can be informed by a PDF.
        known = known_field_names(self.catalog)
        harvested = 0
        rejected = 0
        documentation: list[tuple[object, ...]] = []
        entries = []
        descriptions = 0
        for path, digest in fetched.items():
            system = _system_of(path, self.settings.base_path)
            try:
                result = harvest_pdf(
                    self.blobs.read(digest), source_ref=path, known_fields=known
                )
            except Exception as exc:
                notes.append(f"pdf harvest failed: {path}: {exc}")
                continue
            if result.warnings:
                notes.extend(f"{path}: {w}" for w in result.warnings[:1])
            if result.is_empty:
                continue
            harvested += 1
            rejected += result.rejected
            descriptions += len(result.field_descriptions)
            documentation.extend(documentation_rows(result, system=system))
            entries.extend(entries_from_harvest(result, system=system))

        # The record layout is the only source that names the column itself, so
        # it lands in its own table rather than in the value dictionary.
        self.catalog.executemany(
            """
            INSERT INTO field_documentation (system, field_name, description, declared_type,
                declared_width, declared_decimals, source, source_ref, confidence)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(system, field_name, source_ref) DO UPDATE SET
                description=excluded.description, declared_type=excluded.declared_type,
                declared_width=excluded.declared_width, declared_decimals=excluded.declared_decimals
            """,
            documentation,
        )
        merged = {"inserted": 0, "conflicts": 0}
        if entries:
            merged = persist_entries(self.catalog, entries)
        return {
            "pdfs_found": len(paths),
            "pdfs_harvested": harvested,
            "pdf_candidates_rejected": rejected,
            "pdf_field_descriptions": descriptions,
            "pdf_entries": merged["inserted"],
            "pdf_conflicts": merged["conflicts"],
            "field_documentation_rows": len(documentation),
        }

    def _close_semantic_questions(
        self, counts: dict[str, object], kit_reports: list[dict[str, object]]
    ) -> None:
        if int(counts.get("kits_ingested", 0)):
            self.catalog.resolve_question(
                "V3.cnv_def_grammar",
                resolution=(
                    ".CNV: header '<n_categories> <code_width>' then fixed-column rows of "
                    "sequence / label / match-expression, where the expression is a code, a "
                    "comma list, a range, or a mixture, and LAST match wins (catch-alls are "
                    "listed first and overridden). .DEF: ';' comment, 'A' data glob, '?' help, "
                    "and variable lines prefixed L/C/S/X (linha/coluna/seleção/all) or I "
                    "(incremento, i.e. officially summable), each 'label,FIELD[,arg[,LOOKUP]]'."
                ),
                evidence=json.dumps(counts),
            )
            self.catalog.resolve_question(
                "V4.tab_kit_contents",
                resolution=f"{counts['kits_ingested']} kits ingested; every member catalogued in archive_members with its role",
                evidence=json.dumps(kit_reports[:20]),
            )
        procedure_rows = self.catalog.count("code_tables", "table_id LIKE 'TPROC%' OR table_id LIKE 'EMUSO%'")
        if procedure_rows:
            self.catalog.resolve_question(
                "V5.sigtap_procedure_table",
                resolution=(
                    f"A procedure code table IS present inside the kits: {procedure_rows} rows across "
                    "TPROC/TPROC10/EMUSO members (code + description + group). These are the "
                    "TabNet procedure tables for the kit's own era, not the full SIGTAP release "
                    "with its attribute tables (validity windows, CBO and CID restrictions, "
                    "financing). Code→description decoding needs nothing further; anything "
                    "depending on procedure *attributes* still requires SIGTAP from "
                    "sigtap.datasus.gov.br."
                ),
                evidence=json.dumps({"procedure_code_rows": procedure_rows}),
            )

    # ----------------------------------------------------------------- sample

    def sample(self, *, systems: Sequence[str] | None = None, limit: int | None = None) -> StageResult:
        plan = sample_plan(self.catalog, systems=systems)
        if limit:
            plan = plan[:limit]
        return StageResult("sample", counts={"strata_to_sample": len(plan)})

    # ---------------------------------------------------------------- profile

    def profile(
        self,
        *,
        systems: Sequence[str] | None = None,
        limit: int | None = None,
        row_limit: int | None = None,
        force: bool = False,
        on_item: Callable[[str, str], None] | None = None,
    ) -> StageResult:
        plan = sample_plan(self.catalog, systems=systems, only_pending=not force)
        if limit:
            plan = plan[:limit]
        refs = load_reference_sets(self.catalog)
        registry = ReaderRegistry(row_limit=row_limit or self.settings.profile_row_limit)
        counts = {
            "strata": len(plan), "profiled": 0, "failed": 0, "tables": 0,
            "families_profiled": 0, "schema_only": 0,
        }
        notes: list[str] = []
        # Families already carrying full statistics — from this run or an earlier
        # one — need only their schema confirmed.
        profiled_families: set[str] = {
            str(r["family_id"]) for r in self.catalog.query("SELECT DISTINCT family_id FROM variable_profiles")
        }

        paths = [str(row["sampled_path"]) for row in plan]
        digests = self.fetcher.ensure(paths)

        for row in plan:
            stratum_id = str(row["stratum_id"])
            path = str(row["sampled_path"])
            if on_item:
                on_item(stratum_id, path)
            digest = digests.get(path)
            if not digest:
                record_stratum_schema(
                    self.catalog, stratum_id, schema_sig="", field_count=0,
                    status="failed", error="fetch failed",
                )
                counts["failed"] += 1
                continue
            outcome = registry.open_bytes(self.blobs.read(digest), path=path)
            record_decode_attempts(
                self.catalog, path, [(a.reader, a.ok, a.error) for a in outcome.attempts]
            )
            for key, question in outcome.open_questions:
                self.catalog.note_question(
                    f"{key}:{path}", area="decode", question=question,
                    verification_procedure="re-run `pegasus-data profile` after resolving the dependency",
                    blocking=path,
                )
            if not outcome.tables:
                record_stratum_schema(
                    self.catalog, stratum_id, schema_sig="", field_count=0, status="failed",
                    error="; ".join(f"{a.reader}: {a.error}" for a in outcome.attempts if not a.ok)[:1000],
                )
                self.catalog.record_gap(path, kind="decode", methods=tuple(a.reader for a in outcome.attempts), error="undecodable")
                counts["failed"] += 1
                continue

            # An archive holding several schemas (an APAC .exe holds seven) makes
            # each member its own stratum, keyed by the member name.
            #
            # A stratum that already names a member profiles *only* that member.
            # Without this, re-profiling re-expands the whole archive and derives
            # seven new member strata from each existing one, which multiplies on
            # every run instead of converging.
            tables = outcome.tables
            claimed_member = str(row.get("sampled_member") or "")
            if claimed_member:
                tables = [t for t in tables if t.member == claimed_member] or tables[:1]
            for index, table in enumerate(tables):
                member_stratum = (
                    stratum_id if (index == 0 or claimed_member) else f"{stratum_id}#{index}"
                )
                # Archive members become their own series so that seven APAC
                # schemas in one .exe do not collapse into one another.
                member_series = (
                    f"{row['series']}:{PurePosixPath(table.member).stem}"
                    if table.member
                    else row["series"]
                )
                # The schema signature comes from the container's declared field
                # list, which every reader exposes without reading a single
                # record. So every stratum's schema is established cheaply, and
                # the expensive part — streaming the rows to build the value
                # distributions — runs once per *family*, not once per stratum.
                # SIH-RD alone has 12,101 files across ~35 strata that share one
                # schema; profiling each in full would re-derive the same
                # statistics dozens of times and overwrite them each round.
                signature = schema_signature(table.field_names)
                family_id = family_id_for(str(row["system"]), member_series, signature)
                if family_id not in profiled_families:
                    profile = profile_table(
                        table,
                        refs=refs,
                        row_limit=row_limit or self.settings.profile_row_limit,
                        max_distinct=self.settings.max_distinct_tracked,
                        top_values=self.settings.top_values_kept,
                    )
                    persist_profile(
                        self.catalog,
                        profile,
                        family_id=family_id,
                        top_values_kept=self.settings.top_values_kept,
                    )
                    profiled_families.add(family_id)
                    counts["families_profiled"] += 1
                else:
                    counts["schema_only"] += 1
                field_count = len(table.field_names)
                if index > 0:
                    self.catalog.executemany(
                        """
                        INSERT INTO strata (stratum_id, system, series, year, file_count, sampled_path, sample_status)
                        VALUES (?,?,?,?,?,?, 'pending')
                        ON CONFLICT(stratum_id) DO NOTHING
                        """,
                        [(member_stratum, row["system"], member_series, row["year"], 1, path)],
                    )
                    self.catalog.executemany(
                        "INSERT OR IGNORE INTO stratum_members (stratum_id, path) VALUES (?,?)",
                        [(member_stratum, path)],
                    )
                if index == 0 and table.member:
                    self.catalog.execute(
                        "UPDATE strata SET series = ? WHERE stratum_id = ?",
                        (member_series, member_stratum),
                    )
                record_stratum_schema(
                    self.catalog, member_stratum,
                    schema_sig=signature,
                    field_count=field_count,
                    sampled_member=table.member,
                    status="ok",
                )
                counts["tables"] += 1
            counts["profiled"] += 1

        self._close_decode_questions()
        return StageResult("profile", counts=counts, notes=notes)

    def _close_decode_questions(self) -> None:
        apac = self.catalog.count(
            "decode_attempts", "path LIKE '%/SIASUS/APAC/%' AND ok = 1"
        )
        if apac:
            members = self.catalog.count("archive_members", "archive_path LIKE '%/SIASUS/APAC/%'")
            self.catalog.resolve_question(
                "V2.sfx_exe_payload",
                resolution=(
                    "SIASUS/APAC/*.EXE are LHA self-extracting archives (stub identifies as "
                    "\"LHA's SFX 2.13S\", payload method -lh5-), NOT zip or rar — zipfile and "
                    "rarfile both reject them. Each holds SEVEN DBF members with distinct "
                    "schemas (AC/PC/PF/OP/CO/EX/UD prefixes: master, chemo, radio, other "
                    "procedures, billed procedures, serology, dialysis unit), so one archive is "
                    "seven logical datasets. Decoded here by a pure-Python -lh5- reader, byte-"
                    "exact against 7-Zip."
                ),
                evidence=json.dumps({"apac_decodes_ok": apac, "archive_members_recorded": members}),
            )
        duck_ok = self.catalog.count("decode_attempts", "reader='duckdb' AND ok=1")
        duck_fail = self.catalog.count("decode_attempts", "reader='duckdb' AND ok=0")
        if duck_ok or duck_fail:
            self.catalog.resolve_question(
                "V6.duck_storage_version",
                resolution=(
                    f"{duck_ok} .duck database(s) opened with the installed DuckDB; "
                    f"{duck_fail} refused. Refusals are recorded as open questions carrying the "
                    "storage version read from the file header, never as skipped files."
                ),
                evidence=json.dumps({"opened": duck_ok, "refused": duck_fail}),
            )

    # --------------------------------------------------------------- families

    def families(self) -> StageResult:
        fams = build_families(self.catalog)
        persist_families(self.catalog, fams)
        reports = analyse_drift(self.catalog)
        persist_drift(self.catalog, reports)
        renames = detect_renames(self.catalog)
        persist_renames(self.catalog, renames)
        status_counts: dict[str, int] = {}
        for r in reports:
            status_counts[r.drift_status] = status_counts.get(r.drift_status, 0) + 1
        return StageResult(
            "families",
            counts={
                "families": len(fams),
                "drift_reports": len(reports),
                "drift_status": status_counts,
                "rename_candidates": len(renames),
            },
        )

    # ----------------------------------------------------------------- ledger

    def ledger(self, *, systems: Sequence[str] | None = None) -> StageResult:
        # Fields the detectors identified get their reference table attached
        # before coverage is computed, so an ICD column is scored against the
        # 14,197-row CID table rather than against whichever chapter list a .DEF
        # happened to name.
        semantic_bindings = bind_by_semantic_type(self.catalog)
        # A detector match only becomes usable for labelling once a record layout
        # independently names the same classification.
        corroborated = corroborate_semantic_bindings(self.catalog)
        entries = build_ledger(self.catalog, systems=systems)
        persist_ledger(self.catalog, entries)
        covered = sum(1 for e in entries if e.dictionary_coverage >= 0.99)
        mean = sum(e.dictionary_coverage for e in entries) / len(entries) if entries else 0.0
        return StageResult(
            "ledger",
            counts={
                "ledger_rows": len(entries),
                "fully_covered_fields": covered,
                "mean_dictionary_coverage": round(mean, 4),
                "semantic_bindings_added": semantic_bindings,
                "semantic_bindings_corroborated": corroborated,
            },
        )


def _system_of(path: str, base_path: str) -> str | None:
    from .inventory.naming import system_from_path

    return system_from_path(path, base_path)


def schema_signature_for(field_names: Sequence[str]) -> str:
    return schema_signature(field_names)
