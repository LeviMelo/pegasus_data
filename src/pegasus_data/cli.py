"""Command surface (§8).

    pegasus-data crawl      [--host] [--base-path] [--connections N] [--resume]
    pegasus-data inventory
    pegasus-data sample
    pegasus-data fetch      [--strata|--family|--system] [--concurrency N]
    pegasus-data profile    [--family|--system]
    pegasus-data semantics
    pegasus-data normalize  [--system] [--uf] [--years]
    pegasus-data build      [--system] [--uf] [--years]
    pegasus-data report
    pegasus-data verify

Every command is resumable and idempotent, and every command writes to the
catalog before returning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .build import Builder
from .catalog.store import Catalog, _declared_columns, _schema_sql
from .config import Settings, load_settings
from .pipeline import Pipeline, StageResult
from .verify import run_all, summarise

app = typer.Typer(
    name="pegasus-data",
    help="A queryable, self-describing data lake over Brazil's DATASUS public health data.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

RootOpt = Annotated[Path | None, typer.Option("--root", help="Data home (default $PEGASUS_DATA_HOME or ./pegasus_data_home)")]
SystemsOpt = Annotated[list[str] | None, typer.Option("--system", "-s", help="Limit to these information systems")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON instead of a table")]


def _settings(root: Path | None, **overrides: object) -> Settings:
    return load_settings(root=root, **overrides)


def _pipeline(root: Path | None, **overrides: object) -> Pipeline:
    return Pipeline(_settings(root, **overrides))


def _emit(payload: object, as_json: bool, title: str = "") -> None:
    if as_json:
        console.print_json(json.dumps(payload, default=str))
        return
    if isinstance(payload, dict):
        table = Table(title=title or None, show_header=False, box=None)
        for key, value in payload.items():
            table.add_row(f"[bold]{key}[/bold]", _fmt(value))
        console.print(table)
        return
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        table = Table(title=title or None)
        for column in payload[0]:
            table.add_column(str(column))
        for row in payload:
            table.add_row(*[_fmt(row.get(c)) for c in payload[0]])
        console.print(table)
        return
    console.print(payload)


def _fmt(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str, ensure_ascii=False)
        return text if len(text) <= 160 else text[:157] + "..."
    return str(value)


# ------------------------------------------------------------------- commands


@app.command(rich_help_panel="MONITOR")
def crawl(
    root: RootOpt = None,
    host: Annotated[str | None, typer.Option("--host")] = None,
    base_path: Annotated[str | None, typer.Option("--base-path")] = None,
    connections: Annotated[int | None, typer.Option("--connections", "-c")] = None,
    resume: Annotated[bool, typer.Option("--resume", help="Skip directories already listed; retry open gaps")] = False,
    prefix: Annotated[list[str] | None, typer.Option("--prefix", help="Crawl only these subtrees")] = None,
    accept_mass_gone: Annotated[bool, typer.Option("--accept-mass-gone", help="Record a crawl that withdraws a large share of the catalog instead of failing on it")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Walk the FTP tree, recording files, metadata and unreachable paths."""
    pipeline = _pipeline(root, host=host, base_path=base_path, connections=connections)
    try:
        with console.status("crawling…"):
            result = pipeline.crawl(resume=resume, prefixes=prefix, accept_mass_gone=accept_mass_gone)
        _emit(result.counts, as_json, "crawl")
        if not as_json:
            rec = result.counts.get("reconciliation", {})
            if isinstance(rec, dict):
                _emit(
                    {k: v for k, v in rec.items() if not k.startswith("example_")},
                    False,
                    "reconciliation against the previous crawl",
                )
                for move in rec.get("example_moves", [])[:5]:
                    console.print(f"  [cyan]moved[/cyan] {move['from']} -> {move['to']}")
                for path in rec.get("example_gone", [])[:5]:
                    console.print(f"  [yellow]gone[/yellow] {path}")
        files = pipeline.catalog.count("files", "gone_at IS NULL")
        with_size = pipeline.catalog.count("files", "size IS NOT NULL AND gone_at IS NULL")
        console.print(f"[green]{files}[/green] files present, [green]{with_size}[/green] carrying size and mtime")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def curate(
    root: RootOpt = None,
    curation: Annotated[Path | None, typer.Option("--curation", help="Directory of curated YAML (defaults to the packaged one)")] = None,
    accept: Annotated[str | None, typer.Option("--accept", help="Resolve an open question by recording a human decision")] = None,
    note: Annotated[str | None, typer.Option("--note", help="Why, for the --accept record")] = None,
    by: Annotated[str | None, typer.Option("--by", help="Who is asserting, for the --accept record")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Load curation/*.yml into the catalog. With --accept, settle an open question.

    This is the door §4 exists to add. Three times the design made a slot for
    human judgement and left no way to write into it; a decision recorded here
    outranks every extracted source, because SOURCE_AUTHORITY['manual'] is 0.
    """
    from .semantics.curation import CurationError, coverage_by_rung, load_curation

    settings = _settings(root)
    store = Catalog(settings.catalog_path)
    try:
        if accept:
            existing = store.query("SELECT key, status FROM open_questions WHERE key = ?", (accept,))
            if not existing:
                console.print(f"[red]no open question with key {accept!r}[/red]")
                console.print("Run 'pegasus-data report' to list them.")
                raise typer.Exit(code=1)
            if not note:
                console.print("[red]--accept needs --note saying why[/red]")
                raise typer.Exit(code=1)
            store.resolve_question(
                accept,
                resolution=note,
                evidence=f"accepted by {by or 'unattributed'} via 'pegasus-data curate --accept'",
            )
            _emit({"key": accept, "status": "resolved", "note": note, "by": by}, as_json, "accepted")
            return

        directory = curation or settings.curation_dir
        result = load_curation(store, Path(directory))
        _emit(result, as_json, "curation loaded")
        if not as_json:
            rungs = coverage_by_rung(store)
            if rungs:
                _emit(rungs, False, "documentation coverage per system, by rung")
    except CurationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        store.close()


@app.command(name="dictionary", rich_help_panel="UNDERSTAND")
def dictionary(
    root: RootOpt = None,
    system: SystemsOpt = None,
    out: Annotated[Path | None, typer.Option("--out", help="Where to write (default docs/dictionary.sqlite)")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Write the whole data dictionary as one queryable SQLite file.

    Systems, variables, code tables, every code and label, schema generations and
    dataset prose — with full-text search over all of it. Generated from the
    catalog and never hand-written, so a variable with no description here means
    no source supplied one; the fix is curation/, not the documentation.

    Read it with `pegasus-data search` and `pegasus-data page`, or open it with
    anything that speaks SQL.
    """
    from .docsgen import write_database

    settings = _settings(root)
    target = out or Path("docs") / "dictionary.sqlite"
    store = Catalog(settings.catalog_path, read_only=settings.catalog_path.exists())
    try:
        with console.status(f"writing {target}…"):
            result = write_database(store, target, systems=system)
        _emit(result, as_json, "dictionary")
    finally:
        store.close()


@app.command(rich_help_panel="UNDERSTAND")
def search(
    query: Annotated[str, typer.Argument(help="Words to look for, e.g. 'raça' or 'Parda'")],
    docs: Annotated[Path | None, typer.Option("--docs", help="Dictionary database")] = None,
    kind: Annotated[
        str | None, typer.Option("--kind", help="variable | codelist | dataset")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 25,
    as_json: JsonOpt = False,
) -> None:
    """Search the dictionary: variable names, descriptions and every code label.

    "Which column is about race" and "which code means Parda" are the same
    question to ask here. Accents are folded, so both spellings find it.
    """
    from .docsgen import search_docs

    path = docs or Path("docs") / "dictionary.sqlite"
    if not path.exists():
        console.print(f"[red]no dictionary at {path}[/red]")
        console.print("Run 'pegasus-data dictionary' to build it.")
        raise typer.Exit(code=1)
    hits = search_docs(path, query, limit=limit, kind=kind)
    if not hits:
        console.print(f"[yellow]nothing matches {query!r}[/yellow]")
        return
    _emit(hits, as_json, f"search: {query}")


@app.command(name="compendium", rich_help_panel="UNDERSTAND")
def compendium_cmd(
    out: Annotated[Path, typer.Option("--out", help="Where to write the .sqlite")] = Path("datasus.sqlite"),
    system: SystemsOpt = None,
    codes: Annotated[str, typer.Option("--codes", help="none | internal | bound | all")] = "none",
    max_codes: Annotated[int, typer.Option("--max-codes", help="Codelists larger than this count as external under --codes internal")] = 1000,
    values: Annotated[bool, typer.Option("--values/--no-values", help="Include observed value frequencies")] = False,
    files: Annotated[bool, typer.Option("--files/--no-files", help="Include the raw file listing")] = False,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Write a portable map of DATASUS: what exists, down to the variable.

    The core answers what a researcher asks before downloading anything — which
    systems, which datasets, which years and states, which columns and what they
    mean. Code meanings and value frequencies are opt-in because they are what
    makes such a file large.
    """
    from .compendium import compendium as _compendium

    report = _compendium(
        out, systems=system, codes=codes, max_codes=max_codes,
        values=values, files=files, root=root,
    )
    if as_json:
        _emit(report.as_dict(), True)
        return
    console.print(str(report))


@app.command(name="info", rich_help_panel="UNDERSTAND")
def info_cmd(
    target: Annotated[str | None, typer.Argument(help="System, dataset or variable: SIH, SIH-RD, SIH.RD")] = None,
    field: Annotated[str | None, typer.Option("--field", help="A column within the target")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """What a system, dataset or variable IS — identity, evidence and coverage.

    ``explore`` says what is out there to fetch and ``dictionary`` says what a
    column means. This says what a thing *is*, at any level of the ontology.
    """
    from ._info import info as _info

    answer = _info(target, field_name=field, root=root)
    if as_json:
        _emit(answer.as_dict(), True)
        return
    console.print(str(answer))


@app.command(name="page", rich_help_panel="UNDERSTAND")
def page(
    system: Annotated[str, typer.Argument(help="Information system, e.g. SIHSUS")],
    field: Annotated[str, typer.Argument(help="Column, e.g. DIAG_PRINC")],
    docs: Annotated[Path | None, typer.Option("--docs", help="Dictionary database")] = None,
) -> None:
    """Print one variable's documentation page, out of the dictionary database."""
    from rich.markdown import Markdown

    from .docsgen import read_page

    path = docs or Path("docs") / "dictionary.sqlite"
    if not path.exists():
        console.print(f"[red]no dictionary at {path}[/red]")
        raise typer.Exit(code=1)
    body = read_page(path, system, field)
    if body is None:
        console.print(f"[yellow]{system}.{field} is not in the dictionary[/yellow]")
        raise typer.Exit(code=1)
    console.print(Markdown(body))


@app.command(rich_help_panel="PIPELINE")
def community(
    root: RootOpt = None,
    system: SystemsOpt = None,
    commit: Annotated[str | None, typer.Option("--commit", help="Pin a microdatasus commit SHA")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Ingest community transcriptions of DATASUS codings (microdatasus, MIT).

    The lowest rung that still counts: below pdf, above inferred, and unable to
    override a .CNV/.DEF by construction. Every entry records the repository and
    commit it came from, because a transcription without a version is a rumour.
    Covers columns DATASUS documents nowhere — CNES most of all.
    """
    from .sources.community import ingest as ingest_community

    settings = _settings(root)
    store = Catalog(settings.catalog_path)
    try:
        with console.status("fetching community codings…"):
            result = ingest_community(store, systems=system, commit=commit)
        _emit(result, as_json, "community codings")
    finally:
        store.close()


@app.command(rich_help_panel="PIPELINE")
def sigtap(
    root: RootOpt = None,
    competencia: Annotated[list[str] | None, typer.Option("--competencia", help="YYYYMM vintages to ingest; default is the newest")] = None,
    latest: Annotated[int, typer.Option("--latest", help="How many of the newest exports to ingest")] = 1,
    as_json: JsonOpt = False,
) -> None:
    """Ingest the SIGTAP Tabela Unificada — procedures, occupations and CID, first-party.

    Supplies what the TabNet kits structurally cannot: procedure attributes, and
    an occupation table at a single code width where the FTP tree's CBO file
    mixes two classifications. Lands at source='sigtap', which outranks a lookup
    DBF and never a .CNV/.DEF.
    """
    from .sources.sigtap import SigtapUnavailable, ingest

    settings = _settings(root)
    store = Catalog(settings.catalog_path)
    try:
        with console.status("fetching SIGTAP…"):
            result = ingest(store, competencias=competencia, latest=latest)
        _emit(result, as_json, "sigtap")
    except SigtapUnavailable as exc:
        console.print(f"[red]SIGTAP unavailable: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        store.close()


@app.command(name="icd-quality", rich_help_panel="AUDIT")
def icd_quality(
    root: RootOpt = None,
    system: SystemsOpt = None,
    write: Annotated[bool, typer.Option("--write", help="Record the inferred token rules into the variable dictionary")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Measure what ICD-classified columns actually contain, and how they pack codes.

    Produces a token rule per column and a quality report: how many values are a
    single valid code, several codes in one cell, malformed, a sentinel, or
    syntactically valid but absent from the CID table for that vintage. Nothing
    is dropped or nulled — malformed values are flagged so a consumer can filter
    on quality instead of discovering it later.
    """
    from .semantics.icd import flag_suspect_bindings, measure_icd_columns, persist_token_rules

    settings = _settings(root)
    store = Catalog(settings.catalog_path, read_only=not write)
    try:
        measured = measure_icd_columns(store, settings.lake_dir, systems=system)
        if not measured:
            console.print("[yellow]no column is bound to CID10 yet[/yellow]")
            return
        _emit([q.as_dict() for q in measured] if as_json else
              [{k: v for k, v in q.as_dict().items() if not k.startswith("examples")}
               for q in measured],
              as_json, "ICD column quality")
        if write:
            console.print(f"[green]{persist_token_rules(store, measured)}[/green] token rules recorded")
            suspect = flag_suspect_bindings(store, measured)
            if suspect:
                console.print(
                    f"[yellow]{suspect}[/yellow] binding(s) flagged as probably wrong "
                    "(near-zero match rate); see open questions"
                )
    finally:
        store.close()


@app.command(name="prefix-adjudicate", rich_help_panel="MAINTENANCE")
def prefix_adjudicate(
    prefix: Annotated[str, typer.Option("--prefix", help="Series prefix to settle, e.g. CM")],
    system: Annotated[str, typer.Option("--system", help="The system it actually belongs to")],
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Settle a held prefix->system contradiction. Re-derives that prefix's strata and families.

    The learned map holds its first answer on purpose, so a reorganisation cannot
    silently move identity. This is how a person overrides it once they have
    decided which of the two readings is true.
    """
    from .inventory.systems import adjudicate_prefix

    settings = _settings(root)
    store = Catalog(settings.catalog_path)
    try:
        _emit(adjudicate_prefix(store, prefix, system), as_json, "prefix adjudicated")
        console.print("[yellow]Re-run 'pegasus-data inventory' to re-derive the affected strata.[/yellow]")
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        store.close()


@app.command(rich_help_panel="MAINTENANCE")
def pack(
    out: Annotated[Path, typer.Option("--out", "-o", help="Bundle file to write")],
    root: RootOpt = None,
    system: SystemsOpt = None,
    everything: Annotated[
        bool,
        typer.Option(
            "--all-codelists",
            help="Pack unbound TabNet axes too (roughly doubles the size)",
        ),
    ] = False,
    max_codelist_rows: Annotated[
        int | None,
        typer.Option(
            "--max-codelist-rows",
            help="Omit codelists larger than this (the geographic roll-ups carry most of the bytes)",
        ),
    ] = None,
    note: Annotated[str, typer.Option("--note", help="Free text recorded in the manifest")] = "",
    as_json: JsonOpt = False,
) -> None:
    """Write a portable semantic bundle: labelling and docs with no DATASUS.

    Codelists, field bindings, curated meanings and the schema catalogue, in one
    file. Restoring it into an empty catalog is enough to translate and describe
    data; only fetching new files still needs the network.
    """
    from .bundle import pack as pack_bundle

    settings = _settings(root)
    catalog = Catalog(settings.catalog_path)
    try:
        with console.status(f"packing {out}…"):
            report = pack_bundle(
                catalog,
                out,
                systems=system,
                bound_only=not everything,
                max_codelist_rows=max_codelist_rows,
                note=note,
            )
        _emit(report.as_dict(), as_json, "pack")
    finally:
        catalog.close()


@app.command(rich_help_panel="MAINTENANCE")
def unpack(
    bundle: Annotated[Path, typer.Argument(help="Bundle file to load")],
    root: RootOpt = None,
    replace: Annotated[
        bool,
        typer.Option(
            "--replace",
            help="Clear the packed tables first; use when the bundle is the source of truth",
        ),
    ] = False,
    as_json: JsonOpt = False,
) -> None:
    """Load a semantic bundle into the catalog.

    Additive by default, because a local crawl read the files first-hand and a
    bundle is a copy of someone else's reading. Follow with 'reference' to
    rebuild the Parquet lookups the view layer joins against.
    """
    from .bundle import BundleError
    from .bundle import unpack as unpack_bundle

    settings = _settings(root)
    catalog = Catalog(settings.catalog_path)
    try:
        _emit(unpack_bundle(catalog, bundle, replace=replace), as_json, "unpack")
        console.print(
            "[yellow]Run 'pegasus-data reference' to rebuild the Parquet lookups.[/yellow]"
        )
    except BundleError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        catalog.close()


@app.command(name="catalog-rebuild", rich_help_panel="MAINTENANCE")
def catalog_rebuild(
    table: Annotated[str, typer.Option("--table", help="Table to recreate from the shipped schema")],
    root: RootOpt = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Recreate a table the catalog cannot migrate into. Drops columns the schema no longer declares.

    The remedy named by CatalogSchemaError. Columns present in both the old table
    and the shipped schema are carried over; anything else is lost with the old
    table, which is why this is a command you run rather than something migration
    does for you.
    """
    settings = _settings(root)
    catalog = Catalog(settings.catalog_path, strict_schema=False)
    try:
        declared = set(_declared_columns(_schema_sql()).get(table, {}))
        existing = [r[1] for r in catalog.query(f"PRAGMA table_info({table})")]
        if not existing:
            console.print(f"[red]catalog has no table named {table!r}[/red]")
            raise typer.Exit(code=1)
        dropping = [c for c in existing if c not in declared]
        rows = catalog.count(table)
        if dropping and not yes:
            console.print(
                f"[yellow]Rebuilding {table} ({rows:,} rows) will DROP these columns "
                f"and their data: {', '.join(dropping)}[/yellow]"
            )
            typer.confirm("Proceed?", abort=True)
        _emit(catalog.rebuild_table(table), as_json, f"catalog-rebuild {table}")
    finally:
        catalog.close()


@app.command(rich_help_panel="PIPELINE")
def inventory(root: RootOpt = None, system: SystemsOpt = None, as_json: JsonOpt = False) -> None:
    """Parse filenames, infer per-directory date conventions, build strata. No network."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.inventory(systems=system)
        _emit(result.counts, as_json, "inventory")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def sample(root: RootOpt = None, system: SystemsOpt = None, limit: Annotated[int | None, typer.Option("--limit")] = None, as_json: JsonOpt = False) -> None:
    """Choose one file per schema stratum."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.sample(systems=system, limit=limit)
        _emit(result.counts, as_json, "sample")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def fetch(
    root: RootOpt = None,
    system: SystemsOpt = None,
    family: Annotated[list[str] | None, typer.Option("--family")] = None,
    concurrency: Annotated[int | None, typer.Option("--concurrency", "-j")] = None,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Fetch files into the content-addressed cache. Nothing is fetched twice."""
    pipeline = _pipeline(root, fetch_concurrency=concurrency)
    try:
        clauses, params = [], []
        if system:
            clauses.append(f"fa.system IN ({','.join('?' * len(system))})")
            params.extend(system)
        if family:
            clauses.append(f"ff.family_id IN ({','.join('?' * len(family))})")
            params.extend(family)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        join = "LEFT JOIN family_files ff ON ff.path = fa.path" if family else ""
        rows = pipeline.catalog.query(
            f"SELECT DISTINCT fa.path FROM file_facts fa {join}{where} ORDER BY fa.path", params
        )
        paths = [r["path"] for r in rows]
        if limit:
            paths = paths[:limit]
        with console.status(f"fetching {len(paths)} files…"):
            stats = pipeline.fetcher.fetch_many(paths)
        _emit(
            {
                "requested": stats.requested,
                "fetched": stats.fetched,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "bytes": stats.bytes_fetched,
                "errors": stats.errors[:5],
            },
            as_json,
            "fetch",
        )
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def semantics(
    root: RootOpt = None,
    system: SystemsOpt = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Cap how many kits to ingest")] = None,
    pdfs: Annotated[
        bool,
        typer.Option(
            "--pdfs/--no-pdfs",
            help="Also harvest the dictionary PDFs. Off by default: most PDFs on the tree "
            "are legislation and technical notes, not layout tables, and an unconstrained "
            "read of them injects noise into the dictionary.",
        ),
    ] = False,
    as_json: JsonOpt = False,
) -> None:
    """Ingest TAB kits, parse .DEF/.CNV, build the dictionary. This is P1."""
    pipeline = _pipeline(root)
    try:
        with console.status("ingesting dictionaries…"):
            result = pipeline.semantics(systems=system, limit=limit, pdfs=pdfs)
        _emit(result.counts, as_json, "semantics")
        for note in result.notes[:10]:
            console.print(f"[yellow]note[/yellow] {note}")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def schemas(
    root: RootOpt = None,
    system: SystemsOpt = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Cap strata examined")] = None,
    all_strata: Annotated[bool, typer.Option("--all", help="Re-read strata that already have a signature")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Census every stratum's columns by reading file headers, not payloads.

    A DBF declares its whole schema in a few hundred bytes, and a .dbc keeps that
    header uncompressed ahead of its compressed payload — so a ranged fetch
    settles what columns a file has for about 17 MB across the entire tree, where
    decoding one file per stratum would be 183 GiB.
    """
    pipeline = _pipeline(root)
    try:
        result = pipeline.schemas(systems=system, limit=limit, only_missing=not all_strata)
        _emit(result.counts, as_json, "schema census")
        if not as_json:
            from .inventory.schemas import census_summary

            rows = census_summary(pipeline.catalog)
            if rows:
                _emit(rows[:20], False, "schema generations per series")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def profile(
    root: RootOpt = None,
    system: SystemsOpt = None,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
    rows: Annotated[int | None, typer.Option("--rows", help="Row cap per sampled file")] = None,
    force: Annotated[bool, typer.Option("--force", help="Re-profile strata already marked ok")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Fetch and profile one file per stratum, classifying every field."""
    pipeline = _pipeline(root)
    try:
        with console.status("profiling…"):
            result = pipeline.profile(systems=system, limit=limit, row_limit=rows, force=force)
        _emit(result.counts, as_json, "profile")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def families(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Build schema-signature families, representations, drift and rename candidates."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.families()
        _emit(result.counts, as_json, "families")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def ledger(root: RootOpt = None, system: SystemsOpt = None, as_json: JsonOpt = False) -> None:
    """Build the metadata ledger, including dictionary_coverage per field."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.ledger(systems=system)
        _emit(result.counts, as_json, "ledger")
    finally:
        pipeline.close()


@app.command(rich_help_panel="EXTRACT")
def normalize(
    root: RootOpt = None,
    system: SystemsOpt = None,
    uf: Annotated[list[str] | None, typer.Option("--uf")] = None,
    years: Annotated[str | None, typer.Option("--years", help="e.g. 2015-2024 or 2019,2020")] = None,
    family: Annotated[list[str] | None, typer.Option("--family")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Max files per family")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Normalise and write the lake (an alias of `build`, kept for §8's surface)."""
    build(root=root, system=system, uf=uf, years=years, family=family, limit=limit, as_json=as_json)


@app.command(rich_help_panel="EXPLORE")
def systems(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """What information systems are in the lake, and how much of each."""
    from .api import Catalog as PublicCatalog

    settings = _settings(root)
    public = PublicCatalog(settings.root, settings=settings)
    try:
        _emit(public.systems(), as_json, "systems")
    finally:
        public.close()


@app.command(rich_help_panel="EXPLORE")
def tree(
    root: RootOpt = None,
    system: SystemsOpt = None,
    depth: Annotated[int, typer.Option("--depth", help="How many path levels to show")] = 3,
    as_json: JsonOpt = False,
) -> None:
    """Show the crawled FTP tree: directories, file counts and the bytes behind them."""
    settings = _settings(root)
    store = Catalog(settings.catalog_path, read_only=settings.catalog_path.exists())
    try:
        base = settings.base_path.rstrip("/")
        rows = store.query(
            """
            SELECT directory, COUNT(*) AS files, SUM(size) AS bytes
              FROM files WHERE gone_at IS NULL GROUP BY directory
            """
        )
        folded: dict[str, dict[str, int]] = {}
        for r in rows:
            rest = str(r["directory"])[len(base):].strip("/")
            key = "/".join(rest.split("/")[:depth]) or "(root)"
            bucket = folded.setdefault(key, {"files": 0, "bytes": 0})
            bucket["files"] += int(r["files"] or 0)
            bucket["bytes"] += int(r["bytes"] or 0)
        if system:
            wanted = {s.upper() for s in system}
            folded = {k: v for k, v in folded.items() if k.split("/")[0].upper() in wanted}
        payload = [
            {"path": k, "files": v["files"], "gib": round(v["bytes"] / 2**30, 2)}
            for k, v in sorted(folded.items(), key=lambda kv: -kv[1]["files"])
        ]
        _emit(payload if as_json else payload[:40], as_json, "tree")
    finally:
        store.close()


@app.command(rich_help_panel="EXPLORE")
def coverage(
    system: Annotated[str, typer.Argument(help="Information system, e.g. SIHSUS")],
    series: Annotated[str | None, typer.Argument(help="Series, e.g. RD")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """What years, states and schema generations exist for one system."""
    from .api import Catalog as PublicCatalog

    settings = _settings(root)
    public = PublicCatalog(settings.root, settings=settings)
    try:
        _emit(public.coverage(system, series), as_json, f"coverage {system}")
    finally:
        public.close()


@app.command(rich_help_panel="AUDIT")
def findings(
    root: RootOpt = None,
    open_only: Annotated[bool, typer.Option("--open", help="Only unresolved questions")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Everything measured that contradicted an assumption, resolved and open."""
    settings = _settings(root)
    store = Catalog(settings.catalog_path, read_only=settings.catalog_path.exists())
    try:
        clause = " WHERE status = 'open'" if open_only else ""
        rows = [
            dict(r)
            for r in store.query(
                f"SELECT key, area, status, question, resolution, blocking "
                f"FROM open_questions{clause} ORDER BY status, area, key"
            )
        ]
        if as_json:
            _emit(rows, True)
            return
        for r in rows:
            marker = "[green]resolved[/green]" if r["status"] == "resolved" else "[yellow]open[/yellow]"
            console.print(f"{marker} [bold]{r['key']}[/bold]  ({r['area']})")
            console.print(f"    {r['question']}")
            if r["resolution"]:
                console.print(f"    [green]->[/green] {r['resolution']}")
            elif r["blocking"]:
                console.print(f"    [yellow]blocks:[/yellow] {r['blocking']}")
            console.print()
        console.print(f"{len(rows)} finding(s)")
    finally:
        store.close()


@app.command(rich_help_panel="EXPLORE")
def explore(
    target: Annotated[str | None, typer.Argument(help="System or dataset, e.g. SIHSUS or SIH-RD")] = None,
    root: RootOpt = None,
    year: Annotated[int | None, typer.Option("--year", help="List the files for this year")] = None,
    uf: Annotated[str | None, typer.Option("--uf", help="Limit to one state")] = None,
    everything: Annotated[
        bool, typer.Option("--all-roles", help="Include dictionary and documentation files")
    ] = False,
    packaged: Annotated[
        bool, typer.Option("--packaged", help="Use the shipped snapshot even if a crawl exists")
    ] = False,
    as_json: JsonOpt = False,
) -> None:
    """What DATASUS has — answered from the map, without downloading anything.

    No argument lists the information systems. A system lists its series. A
    dataset gives coverage by year. Adding --year lists the files themselves,
    with sizes, which is what you want before committing to a download.

    Works on a fresh install with no crawl and no network: the map of all
    207,251 files ships with the package. A local crawl supersedes it, and the
    result always says which one answered.
    """
    from ._explore import explore as explore_tree

    try:
        result = explore_tree(
            target, year=year, uf=uf, role=None if everything else "data",
            source="packaged" if packaged else "auto", root=root,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if as_json:
        _emit(result.as_dict(), True)
        return
    if not result.rows:
        console.print(f"[yellow]nothing matched {target!r}[/yellow]")
        if result.unknown:
            console.print("Known: " + ", ".join(result.unknown[:20]))
        raise typer.Exit(code=1)
    _emit(result.rows, False, f"{target or 'DATASUS'} — {result.level}")
    console.print(
        f"[dim]{result.total_files:,} files, {result.total_bytes / 2**30:.1f} GiB · "
        f"{result.source}"
        + (f", crawled {result.as_of[:10]}" if result.as_of else "")
        + "[/dim]"
    )


@app.command(name="translate", rich_help_panel="EXTRACT")
def translate_file(
    path: Annotated[Path, typer.Argument(help="CSV or Parquet file of DATASUS data")],
    system: Annotated[str, typer.Option("--system", "-s", help="Which system produced it")],
    root: RootOpt = None,
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the labelled table")] = None,
    fmt: Annotated[str, typer.Option("--format", help="csv | parquet | xlsx")] = "csv",
    year: Annotated[int | None, typer.Option("--year", help="Vintage of the codelists to apply")] = None,
    profile: Annotated[str, typer.Option("--profile", help="analysis | codes | audit | report")] = "report",
    as_json: JsonOpt = False,
) -> None:
    """Label DATASUS data you already have. No download, no lake.

    For the extract someone mailed you, or pulled from TabNet, or fetched with
    R's microdatasus. --system is required: SEXO=3 is Feminino in SIHSUS and
    undefined in SINASC, so labelling without it would be guessing.
    """
    from ._translate import TranslationImpossible
    from ._translate import translate as translate_table

    try:
        with console.status(f"labelling {path.name}…"):
            table, result = translate_table(
                path, system=system, year=year, profile=profile, root=root, report=True
            )
    except TranslationImpossible as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    target = out or path.with_name(f"{path.stem}_labelled.{fmt}")
    from .api import write_table

    write_table(table, target, fmt)
    console.print(f"[green]wrote[/green] {target}  ({table.num_rows:,} rows)")
    _emit(
        {
            "labelled": len(getattr(result, "labelled", []) or []),
            "unlabelled": len(getattr(result, "unlabelled", []) or []),
            "warnings": list(getattr(result, "warnings", []) or [])[:8],
        },
        as_json,
        "translate",
    )


@app.command(rich_help_panel="EXTRACT")
def get(
    dataset: Annotated[str, typer.Argument(help="Dataset, e.g. SIH-RD, SIM-DO, SINASC-DN")],
    root: RootOpt = None,
    uf: Annotated[list[str] | None, typer.Option("--uf", help="Limit to these states")] = None,
    years: Annotated[str | None, typer.Option("--years", help="e.g. 2020-2024 or 2021,2023")] = None,
    months: Annotated[str | None, typer.Option("--months", help="e.g. 1,2,3")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Write here instead of summarising")] = None,
    fmt: Annotated[str, typer.Option("--format", help="csv | parquet | xlsx")] = "csv",
    columns: Annotated[list[str] | None, typer.Option("--column", "-c")] = None,
    profile: Annotated[str, typer.Option("--profile", help="analysis | codes | audit | report")] = "report",
    no_labels: Annotated[bool, typer.Option("--no-labels", help="Return codes as filed")] = False,
    max_files: Annotated[int | None, typer.Option("--max-files", help="Stop after this many files")] = None,
    no_discover: Annotated[
        bool, typer.Option("--no-discover", help="Refuse rather than crawl an unknown system")
    ] = False,
    as_json: JsonOpt = False,
) -> None:
    """Download a dataset from DATASUS and hand it back processed. No lake needed.

    The one-call door: 'pegasus-data get SIH-RD --uf AL --years 2023'. Files are
    downloaded on demand, decoded, normalised and labelled. A system the catalog
    has never seen triggers a crawl of that system's directory only, which is
    recorded, so the second call is free.
    """
    from .retrieve import DatasetUnknown, NothingPublished
    from .retrieve import fetch as fetch_dataset

    month_list = [int(m) for m in (months or "").replace(" ", "").split(",") if m]
    settings = _settings(root)
    try:
        with console.status(f"fetching {dataset}…"):
            table, result = fetch_dataset(
                dataset,
                uf=uf,
                years=_parse_years(years),
                months=month_list,
                columns=columns,
                labels=not no_labels,
                profile=profile,
                max_files=max_files,
                discover=not no_discover,
                settings=settings,
                report=True,
            )
    except (DatasetUnknown, NothingPublished) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if out:
        from .api import write_table

        write_table(table, out, fmt)
        console.print(f"[green]wrote[/green] {out}  ({table.num_rows:,} rows)")
    _emit(result.as_dict(), as_json, f"get {dataset}")
    for warning in result.warnings:
        console.print(f"[yellow]{warning}[/yellow]")
    if result.years_missing:
        console.print(
            f"[yellow]no data for {result.years_missing} — "
            "DATASUS publishes nothing for those years in this series[/yellow]"
        )


@app.command(rich_help_panel="EXTRACT")
def export(
    system: Annotated[str, typer.Argument(help="Information system, e.g. SIHSUS")],
    series: Annotated[str | None, typer.Argument(help="Series, e.g. RD")] = None,
    root: RootOpt = None,
    uf: Annotated[list[str] | None, typer.Option("--uf", help="Limit to these states")] = None,
    years: Annotated[str | None, typer.Option("--years", help="e.g. 2020-2024 or 2021,2023")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Output file")] = None,
    fmt: Annotated[str, typer.Option("--format", help="csv | parquet | xlsx")] = "csv",
    profile: Annotated[str, typer.Option("--profile", help="analysis | codes | audit | report")] = "report",
    headers: Annotated[str | None, typer.Option("--headers", help="original | translated | both")] = None,
    values: Annotated[str | None, typer.Option("--values", help="separate | combined")] = None,
) -> None:
    """Write a rendered extract: labels applied, ready to open.

    Same rendering path as load(), so an option means the same thing in a
    notebook and in a file. Defaults to the 'report' profile.
    """
    from .api import Catalog as PublicCatalog
    from .api import export as export_table

    settings = _settings(root)
    public = PublicCatalog(settings.root, settings=settings)
    try:
        target = export_table(
            system, series, path=out, format=fmt, uf=uf, years=_parse_years(years),
            catalog=public, profile=profile, headers=headers, values=values,
        )
        console.print(f"[green]wrote[/green] {target}")
    finally:
        public.close()


@app.command(rich_help_panel="EXTRACT")
def build(
    root: RootOpt = None,
    system: SystemsOpt = None,
    uf: Annotated[list[str] | None, typer.Option("--uf")] = None,
    years: Annotated[str | None, typer.Option("--years", help="e.g. 2015-2024 or 2019,2020")] = None,
    family: Annotated[list[str] | None, typer.Option("--family")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Max files per family")] = None,
    keep_raw: Annotated[bool, typer.Option("--keep-raw/--no-keep-raw")] = True,
    labels: Annotated[
        bool,
        typer.Option(
            "--labels/--no-labels",
            help="Materialise a <field>_label column per decoded field. On by default; "
            "off roughly halves the column count and the footprint, and labels can "
            "still be applied at read time from the dictionary.",
        ),
    ] = True,
    as_json: JsonOpt = False,
) -> None:
    """Normalise families into the partitioned Parquet lake."""
    pipeline = _pipeline(root)
    try:
        builder = Builder(pipeline)
        with console.status("building the lake…"):
            result = builder.build(
                systems=system,
                ufs=uf,
                years=_parse_years(years),
                family_ids=family,
                max_files_per_family=limit,
                keep_raw=keep_raw,
                emit_labels=labels,
            )
        _emit(result.counts, as_json, "build")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def reference(
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Write the code tables to lake/reference/, scoped by validity window.

    Hierarchical classifications (CID-10, procedures, CBO, municipalities) are
    joined from here rather than flattened into a label column per row, so the
    consumer chooses the granularity and the vintage.
    """
    pipeline = _pipeline(root)
    try:
        from .persist.reference import (
            flag_mixed_width_tables,
            flag_unlabelled_codelists,
            register_reference_tables,
            write_reference_tables,
        )

        with console.status("writing reference tables…"):
            written = write_reference_tables(pipeline.catalog, pipeline.settings.lake_dir)
            register_reference_tables(pipeline.catalog, written)
            unlabelled = flag_unlabelled_codelists(pipeline.catalog)
            if unlabelled:
                console.print(
                    f"[yellow]{len(unlabelled)}[/yellow] codelist(s) decode nothing — their "
                    "label column resolved to a blank field; recorded as open questions"
                )
                _emit(unlabelled[:8], False, "codelists with no usable labels")
            mixed = flag_mixed_width_tables(pipeline.catalog, written)
        rows = [
            {
                "table": t.table_id,
                "window": t.window,
                "codes": t.rows,
                "widths": ",".join(map(str, t.code_widths)),
                "path": t.relative_path,
            }
            for t in sorted(written, key=lambda x: -x.rows)[:40]
        ]
        _emit(rows, as_json, f"{len(written)} reference tables")
        if mixed:
            console.print(
                f"[yellow]{mixed}[/yellow] table(s) merge more than one code width — "
                "recorded as open questions; join with code_width= to stay on one vintage"
            )
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def population(
    root: RootOpt = None,
    series: Annotated[list[str] | None, typer.Option("--series")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Ingest the IBGE denominator series into lake/population/."""
    pipeline = _pipeline(root)
    try:
        builder = Builder(pipeline)
        with console.status("ingesting denominators…"):
            result = builder.population(series=series)
        _emit(result.counts, as_json, "population")
        for note in result.notes[:10]:
            console.print(f"[yellow]note[/yellow] {note}")
    finally:
        pipeline.close()


@app.command(rich_help_panel="PIPELINE")
def demas(
    root: RootOpt = None,
    endpoint: Annotated[list[str] | None, typer.Option("--endpoint")] = None,
    pages: Annotated[int, typer.Option("--pages", help="Pages to pull per endpoint")] = 5,
    as_json: JsonOpt = False,
) -> None:
    """Persist the DEMAS OpenAPI document and ingest the priority endpoints."""
    pipeline = _pipeline(root)
    try:
        builder = Builder(pipeline)
        with console.status("querying the DEMAS API…"):
            result = builder.demas(endpoints=endpoint, max_pages=pages)
        _emit(result.counts, as_json, "demas")
        for note in result.notes[:10]:
            console.print(f"[yellow]note[/yellow] {note}")
    finally:
        pipeline.close()


@app.command(rich_help_panel="AUDIT")
def report(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Coverage, dictionary_coverage, and the open questions."""
    settings = _settings(root)
    from .catalog.store import Catalog as Store
    from .inventory.strata import coverage_by_system
    from .inventory.systems import low_trust_prefixes
    from .semantics.dictionary import conflicts_report
    from .semantics.ledger import coverage_report
    from .semantics.reference import reference_summary

    store = Store(settings.catalog_path, read_only=settings.catalog_path.exists())
    try:
        payload = {
            "root": str(settings.root),
            "files": store.count("files"),
            "files_with_metadata": store.count("files", "size IS NOT NULL"),
            "directories": store.count("directories"),
            "open_coverage_gaps": store.count("coverage_gaps", "resolved = 0"),
            "strata": store.count("strata"),
            "strata_profiled": store.count("strata", "sample_status = 'ok'"),
            "families": store.count("families"),
            "schemas": store.count("schemas"),
            "dictionary_entries": store.count("dictionary"),
            "dictionary_conflicts": store.count("dictionary_conflicts"),
            "unexpanded_rules": store.count("dictionary_rules"),
            "codelist_bindings": store.count("field_codelists"),
            "ledger_rows": store.count("ledger"),
            "lake_partitions": store.count("lake_partitions"),
            "lake_rows": store.scalar("SELECT SUM(row_count) FROM lake_partitions") or 0,
            "blobs": store.count("blobs"),
        }
        if as_json:
            payload["coverage_per_system"] = coverage_report(store)
            payload["strata_per_system"] = coverage_by_system(store)
            payload["conflicts"] = conflicts_report(store, limit=50)
            payload["reference_sets"] = reference_summary(store)
            payload["low_trust_prefixes"] = low_trust_prefixes(store)
            payload["open_questions"] = [
                dict(r) for r in store.query("SELECT key, status, area, question, resolution FROM open_questions ORDER BY key")
            ]
            _emit(payload, True)
            return
        _emit(payload, False, "catalog")
        strata = coverage_by_system(store)
        if strata:
            _emit(strata, False, "strata and schema generations per system")
        coverage = coverage_report(store)
        if coverage:
            _emit(coverage, False, "dictionary coverage per system")
        low_trust = low_trust_prefixes(store)
        if low_trust:
            # 2d: the count of low-trust prefixes says nothing on its own. What
            # matters is how many files still fall back to path authority.
            facts = store.count("file_facts")
            covered = sum(int(r["files"]) for r in low_trust)
            console.print(
                f"[yellow]{len(low_trust)}[/yellow] low-trust series prefixes cover "
                f"[yellow]{covered:,}[/yellow] of {facts:,} files "
                f"([yellow]{covered / facts:.2%}[/yellow]) via the path-authoritative fallback"
            )
            _emit(low_trust[:10], False, "low-trust prefixes (largest first)")
        conflicts = conflicts_report(store, limit=10)
        if conflicts:
            # A conflict is a finding, so it belongs in the report rather than
            # only in a table nobody queries (§6.3).
            _emit(conflicts, False, "dictionary conflicts (most recent)")
        questions = [
            dict(r)
            for r in store.query(
                "SELECT key, status, area, blocking FROM open_questions ORDER BY status, key"
            )
        ]
        if questions:
            table = Table(title="open questions")
            table.add_column("key")
            table.add_column("status")
            table.add_column("area")
            table.add_column("blocking")
            for q in questions:
                colour = "green" if q["status"] == "resolved" else "yellow"
                table.add_row(
                    str(q["key"]), f"[{colour}]{q['status']}[/{colour}]", str(q["area"]), _fmt(q["blocking"])
                )
            console.print(table)
    finally:
        store.close()


@app.command(rich_help_panel="AUDIT")
def questions(
    root: RootOpt = None,
    key: Annotated[str | None, typer.Option("--key", help="Show one question's full resolution")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Show the [V] list with resolutions and the evidence behind them."""
    settings = _settings(root)
    from .catalog.store import Catalog as Store

    store = Store(settings.catalog_path, read_only=settings.catalog_path.exists())
    try:
        if key:
            rows = [dict(r) for r in store.query("SELECT * FROM open_questions WHERE key = ?", (key,))]
            if not rows:
                console.print(f"[red]no question with key {key!r}[/red]")
                raise typer.Exit(1)
            _emit(rows[0], as_json, key)
            return
        rows = [
            dict(r)
            for r in store.query(
                "SELECT key, area, status, question, resolution FROM open_questions ORDER BY key"
            )
        ]
        if as_json:
            _emit(rows, True)
            return
        for row in rows:
            colour = "green" if row["status"] == "resolved" else "yellow"
            console.print(f"[bold]{row['key']}[/bold] [{colour}]{row['status']}[/{colour}] ({row['area']})")
            console.print(f"  Q: {row['question']}")
            if row["resolution"]:
                console.print(f"  [green]A:[/green] {row['resolution']}")
            console.print()
    finally:
        store.close()


@app.command(rich_help_panel="UNDERSTAND")
def gaps(
    root: RootOpt = None,
    system: SystemsOpt = None,
    limit: Annotated[int, typer.Option("--limit", help="How many fields to show")] = 30,
    max_coverage: Annotated[float, typer.Option("--max-coverage", help="Treat coverage at or below this as a gap")] = 0.5,
    persist: Annotated[bool, typer.Option("--persist/--no-persist", help="Record the list as open questions")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Which variables still have no dictionary, ranked by observed row mass.

    The complement of `report`'s coverage number: not how much is decoded, but
    exactly what is not, and what it would take to close each one.
    """
    settings = _settings(root)
    from .catalog.store import Catalog as Store
    from .semantics.gaps import distinct_field_gaps, find_gaps, persist_gaps, summarise_gaps

    writable = persist
    store = Store(settings.catalog_path, read_only=not writable and settings.catalog_path.exists())
    try:
        found = find_gaps(store, systems=system, max_coverage=max_coverage)
        summary = summarise_gaps(found)
        by_field = distinct_field_gaps(found)
        if as_json:
            _emit({"summary": summary, "by_field": by_field[:limit]}, True)
        else:
            _emit(summary, False, "undecoded fields")
            table = Table(title=f"top {min(limit, len(by_field))} undecoded variables by observed row mass")
            table.add_column("system")
            table.add_column("field")
            table.add_column("kind")
            table.add_column("rows", justify="right")
            table.add_column("distinct", justify="right")
            table.add_column("years")
            table.add_column("sample values")
            for entry in by_field[:limit]:
                years = entry["years"]
                table.add_row(
                    str(entry["system"]), str(entry["field"]), str(entry["kind"]),
                    f"{int(entry['observed_rows']):,}", str(entry["distinct_observed"]),
                    f"{years[0]}-{years[1]}",
                    ", ".join(map(str, entry["top_values"][:4])),
                )
            console.print(table)
        if persist:
            noted = persist_gaps(store, found)
            console.print(f"[green]{noted}[/green] gaps recorded as open questions")
    finally:
        store.close()


@app.command(rich_help_panel="UNDERSTAND")
def describe(
    system: Annotated[str, typer.Argument(help="e.g. SIHSUS")],
    series: Annotated[str | None, typer.Argument(help="e.g. RD")] = None,
    field: Annotated[str | None, typer.Option("--field", "-f")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """What a variable is and what its values mean — with provenance."""
    from .api import Catalog as PublicCatalog
    from .api import describe as describe_field

    settings = _settings(root)
    catalog = PublicCatalog(settings.root, settings=settings)
    try:
        if field is None:
            _emit(catalog.coverage(system, series), as_json, f"{system} {series or ''}")
            return
        description = describe_field(system, series, field=field, catalog=catalog)
        if as_json:
            _emit(description.as_dict(), True)
            return
        head = {
            "field": description.field_name,
            "official name": description.official_name,
            "semantic type": f"{description.semantic_type} ({description.semantic_confidence:.2f})"
            if description.semantic_confidence is not None
            else description.semantic_type,
            "aggregation": description.aggregation,
            "unit": description.unit,
            "dictionary coverage": f"{description.dictionary_coverage:.1%}",
            "distinct observed": description.distinct_observed,
            "sentinels": description.sentinel_values,
            "provenance": description.provenance,
        }
        _emit(head, False, f"{system} {series or ''} — {field}")
        if description.top_values:
            table = Table(title="top values")
            table.add_column("value")
            table.add_column("label")
            table.add_column("count", justify="right")
            table.add_column("%", justify="right")
            for row in description.top_values[:15]:
                table.add_row(
                    str(row["value"]), str(row.get("label") or "[dim]undecoded[/dim]"),
                    str(row["count"]), f"{row['percent']:.2%}",
                )
            console.print(table)
        if description.rollups:
            _emit(description.rollups[:6], False, "codelists bound to this field")
        if description.generations:
            _emit(description.generations, False, "schema generations")
        for question in description.open_questions:
            console.print(f"[yellow]open question[/yellow] {question}")
    finally:
        catalog.close()


@app.command(rich_help_panel="AUDIT")
def verify(
    root: RootOpt = None,
    step: Annotated[list[int] | None, typer.Option("--step", help="Only these §12 steps")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Run the §12 regression assertions."""
    settings = _settings(root)
    from .catalog.store import Catalog as Store

    store = Store(settings.catalog_path, read_only=settings.catalog_path.exists())
    try:
        checks = run_all(store, settings, only=step)
        payload = summarise(checks)
        if as_json:
            _emit(payload, True)
        else:
            table = Table(title="§12 regression assertions")
            table.add_column("step", justify="right")
            table.add_column("check")
            table.add_column("status")
            table.add_column("detail")
            for c in checks:
                colour = {"pass": "green", "fail": "red", "skip": "yellow"}[c.status]
                table.add_row(str(c.step), c.name, f"[{colour}]{c.status}[/{colour}]", c.detail)
            console.print(table)
            console.print(
                f"[bold]{payload['pass']} passed, {payload['fail']} failed, {payload['skip']} skipped[/bold]"
            )
        if payload["fail"]:
            raise typer.Exit(1)
    finally:
        store.close()


def _optional(pipeline: Pipeline, stage: str) -> StageResult:
    """Run a network-dependent source, reporting failure instead of raising.

    SIGTAP lives on a different host and the community source on GitHub; either
    can be unreachable behind a firewall or on a bad day. Neither is worth
    ending a multi-hour run for, and a stage that says why it produced nothing
    is honest in a way a crashed pipeline is not.
    """
    try:
        if stage == "sigtap":
            from .sources.sigtap import ingest as run

            return StageResult(stage, counts=run(pipeline.catalog))
        from .sources.community import ingest as run_community

        return StageResult(stage, counts=run_community(pipeline.catalog))
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        pipeline.catalog.log_event(
            stage, "optional source unavailable", level="warn", detail=f"{type(exc).__name__}: {exc}"
        )
        return StageResult(stage, counts={"skipped": True, "reason": f"{type(exc).__name__}: {exc}"})


def _write_reference(pipeline: Pipeline) -> StageResult:
    from .persist.reference import (
        flag_unlabelled_codelists,
        register_reference_tables,
        write_reference_tables,
    )

    written = write_reference_tables(pipeline.catalog, pipeline.settings.lake_dir)
    register_reference_tables(pipeline.catalog, written)
    unlabelled = flag_unlabelled_codelists(pipeline.catalog)
    return StageResult(
        "reference",
        counts={"tables": len(written), "codelists_without_labels": len(unlabelled)},
    )


@app.command(name="all", rich_help_panel="PIPELINE")
def run_everything(
    root: RootOpt = None,
    system: SystemsOpt = None,
    prefix: Annotated[list[str] | None, typer.Option("--prefix")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Cap strata profiled and files per family")] = None,
    resume: Annotated[bool, typer.Option("--resume")] = False,
) -> None:
    """Empty directory to queryable lake, in dependency order.

    crawl → inventory → semantics → sigtap → community → curate → reference →
    schemas → profile → families → ledger → build.

    The order is not cosmetic. Every value source lands before ``curate``, so a
    curated assertion can override any of them; ``reference`` comes after
    ``curate``, because it materialises the winners and materialising them
    earlier would freeze the losers into the lake.
    """
    from .semantics.curation import load_curation

    pipeline = _pipeline(root)
    try:
        stages = [
            ("crawl", lambda: pipeline.crawl(resume=resume, prefixes=prefix)),
            ("inventory", lambda: pipeline.inventory(systems=system)),
            ("semantics", lambda: pipeline.semantics(systems=system)),
            # External value sources, each unable to outrank the .CNV/.DEF above
            # it. Both reach the network and both are allowed to fail without
            # taking the run with them — a lake without SIGTAP is smaller, not
            # broken.
            ("sigtap", lambda: _optional(pipeline, "sigtap")),
            ("community", lambda: _optional(pipeline, "community")),
            # Curation lands after every extracted source and before anything
            # materialises: the manual bindings it writes outrank all of them,
            # and the ledger downstream reads the winner.
            (
                "curate",
                lambda: StageResult(
                    "curate", counts=load_curation(pipeline.catalog, pipeline.settings.curation_dir)
                ),
            ),
            # Materialise the code tables. Without this a lake has no
            # lake/reference/, and load() cannot label a single column — which
            # made `all` produce something that read back as raw codes.
            ("reference", lambda: _write_reference(pipeline)),
            # Census first: it is cheap, it covers everything, and it gives the
            # profile stage a schema for strata its sample will never reach.
            ("schemas", lambda: pipeline.schemas(systems=system)),
            ("profile", lambda: pipeline.profile(systems=system, limit=limit)),
            ("families", pipeline.families),
            ("ledger", lambda: pipeline.ledger(systems=system)),
            # The .DEF files name columns nothing else does; harvest before
            # curate, so a hand-written description still outranks them.
            ("def-names", lambda: pipeline.def_names(systems=system)),
            # Needs bindings and profiles both, so it follows the ledger.
            ("measure-bindings", pipeline.measure_bindings),
        ]
        for name, fn in stages:
            with console.status(f"{name}…"):
                result = fn()
            console.print(f"[green]✓[/green] {name}: {_fmt(result.counts)}")
        builder = Builder(pipeline)
        with console.status("build…"):
            result = builder.build(systems=system, max_files_per_family=limit)
        console.print(f"[green]✓[/green] build: {_fmt(result.counts)}")
    finally:
        pipeline.close()


def _parse_years(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, _, hi = part.partition("-")
            out.extend(range(int(lo), int(hi) + 1))
        elif part:
            out.append(int(part))
    return out or None


def _make_console_unicode_safe() -> None:
    """Stop a legacy console codepage from killing the process mid-report.

    Windows consoles still default to cp1252 or cp850, and essentially every
    label this tool prints is Portuguese — ``Doenças``, ``Permanência``,
    ``óbito``. Rich writes them straight to stdout and the encoder raises
    ``UnicodeEncodeError``, losing the whole report over one character. Switching
    the streams to UTF-8 with replacement keeps the output readable and the exit
    code meaningful.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main() -> None:
    _make_console_unicode_safe()
    try:
        app()
    except KeyboardInterrupt:
        console.print("[yellow]interrupted — every stage is resumable, re-run to continue[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
