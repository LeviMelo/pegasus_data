"""The maintainer pipeline: crawl to build, and catalog maintenance (RUNBOOK §5)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..build import Builder
from ..catalog.store import CatalogStore, _declared_columns, _schema_sql
from ..pipeline import Pipeline, StageResult
from ._common import (
    JsonOpt,
    RootOpt,
    SystemsOpt,
    _emit,
    _fmt,
    _parse_years,
    _pipeline,
    _writer,
    app,
    console,
)


@app.command(rich_help_panel="PIPELINE")
def geography(
    out: Annotated[str | None, typer.Option("--out", help="Where to write the pack (default: the package's resources)")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Compile the supramunicipal membership pack from its three authorities.

    DATASUS's TabWin tables in the label pack (health regions per system and the
    rest of the health-service geography), IBGE's Localidades API (territorial
    identity), TabNet's current territorial tables (health macroregion, the
    current health regions), IPEA's comparable areas and IBGE's population arrangements. Maintainer step; the result ships as
    ``resources/geography.parquet``, with the points pack and the proximity graphs rebuilt from the Grade Estatística
    (`pegasus-data grade` first; ADR-0203).
    """
    from importlib.resources import files

    from ..geography import GEOGRAPHY_PACK_NAME, build_geography_pack
    from ..sources.ibge_localidades import fetch_municipalities

    settings = _writer(root)
    target = Path(out) if out else Path(str(files("pegasus_data.resources") / GEOGRAPHY_PACK_NAME))
    with console.status("compiling geography…"):
        result = build_geography_pack(
            target, ibge=fetch_municipalities(), tabnet_cache=settings.root / "registries" / "tabnet",
            ipea_cache=settings.root / "registries" / "ipea_amc", arranjos_cache=settings.root / "registries" / "ibge_arranjos",
        )
        from ..geography import POINTS_PACK_NAME, build_municipality_points, mesh_file, point_sources
        from ..proximity import build_proximity_graphs

        sources = point_sources(settings.root / "registries" / "ibge_points")
        maxima = mesh_file("municipality", "maxima", settings.root)
        result["points"] = build_municipality_points(
            target.with_name(POINTS_PACK_NAME), localities=sources["localities.gpkg"], mesh=maxima, grade_root=settings.root)
        result["proximity"] = build_proximity_graphs(target.parent, mesh=maxima, grade_root=settings.root)
    _emit(result, as_json, "geography")


@app.command(rich_help_panel="PIPELINE")
def grade(
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Build IBGE's Grade Estatística 2022 (people and households on 200 m / 1 km cells) with each cell's municipalities,
    into registries/ibge_grade/ (ADR-0203). Checked against the totals IBGE publishes for it."""
    from ..sources import ibge_grade

    settings = _writer(root)
    with console.status("building the Grade Estatística…") as status:
        result = ibge_grade.build(settings.root, log=lambda m: status.update(m))
    _emit(result, as_json, "grade")


@app.command(rich_help_panel="PIPELINE")
def tracts(
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Read IBGE's Census 2022 tract tables (identity and counts; residents by sex and age band, a suppressed count null)
    into registries/ibge_tracts/, and measure what suppression leaves out (ADR-0203)."""
    from ..sources import ibge_tracts

    settings = _writer(root)
    with console.status("reading the tract tables…"):
        result = ibge_tracts.build(settings.root)
    _emit(result, as_json, "tracts")


@app.command(rich_help_panel="PIPELINE")
def mobility(
    layer: Annotated[list[str] | None, typer.Option("--layer", help="census_commuting, ibge_links or anac_air (repeat); default all")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Build the mobility layers between municipalities into registries/mobility/ (ADR-0211), read by `graph KIND`
    and `proximity_graph(kind)`: Census 2010 commuting, IBGE coach and boat links 2016, ANAC air passengers by month."""
    import importlib

    from ..proximity import MOBILITY_LAYERS

    settings = _writer(root)
    modules = layer or sorted({module for module, _ in MOBILITY_LAYERS.values()})
    result = {}
    for module in modules:
        with console.status(f"building {module}…") as status:
            result[module] = importlib.import_module(f"pegasus_data.sources.{module}").build(
                settings.root, log=lambda m: status.update(m))
    _emit(result, as_json, "mobility")


@app.command(name="climate-update", rich_help_panel="PIPELINE")
def climate_update(
    variable: Annotated[list[str] | None, typer.Option("--variable", help="precipitation, tmax, tmin or tmed (repeat); default all")] = None,
    start: Annotated[str | None, typer.Option("--start", help="First day, YYYY-MM-DD (default 2000-01-01)")] = None,
    end: Annotated[str | None, typer.Option("--end", help="Last day, YYYY-MM-DD (default today)")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Read CPTEC's daily MERGE precipitation and SAMeT temperatures into municipal means by population and by area,
    keeping every vintage (ADR-0204): files not yet held, or listed with another time than the one held, are read. Run it
    daily to keep SAMeT's provisional days."""
    import datetime as dt

    from ..sources import cptec

    settings = _writer(root)
    with console.status("reading CPTEC…") as status:
        result = cptec.update(settings, variable or None, start=dt.date.fromisoformat(start) if start else None,
                              end=dt.date.fromisoformat(end) if end else None, log=lambda m: status.update(m))
    _emit(result, as_json, "climate-update")


@app.command(rich_help_panel="PIPELINE")
def fields(
    name: Annotated[list[str] | None, typer.Option("--name", help="A declared field (curation/fields.yml); default all")] = None,
    years: Annotated[str | None, typer.Option("--years", help="e.g. 2019-2021")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Read IBGE's municipal statistics (curation/fields.yml) into lake/fields/."""
    from ..fields import build_fields

    with console.status("reading IBGE…"):
        result = build_fields(_writer(root), names=name, years=_parse_years(years))
    _emit(result, as_json, "fields")


@app.command(name="intake-periods", rich_help_panel="MAINTENANCE")
def intake_periods(
    source: Annotated[str | None, typer.Option("--source", help="One declared source (curation/intake.yml); default every file source")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Count the publications that would be dated differently; change nothing")] = False,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Date the catalog's publications of the declared file sources by their units' periods (a source declared by
    `months` files one publication per month), landing nothing: for units registered before a month was one of their facts."""
    from ..intake import register_periods

    _emit(register_periods(_writer(root), source, dry_run=dry_run), as_json, "intake-periods")


@app.command(rich_help_panel="PIPELINE")
def cnefe(
    uf: Annotated[list[str] | None, typer.Option("--uf", help="Only these UFs (abbreviation or IBGE code); default all 27")] = None,
    force: Annotated[bool, typer.Option("--force", help="Download and land again what is already landed")] = False,
    keep_raw: Annotated[bool | None, typer.Option("--keep-raw/--delete-raw", help="Keep or delete each UF's zip once its records are "
                                                  "landed and counted (default: delete only when the free disk is short)")] = None,
    check: Annotated[bool, typer.Option("--check/--no-check", help="Compare with IBGE's own aggregate by CEP at the end")] = True,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Land IBGE's CNEFE 2022 (the Census's georeferenced addresses) and derive the per-CEP table that `cep-points` reads.

    Downloads the per-UF zips (3.9 GB in all), lands every record under lake/cnefe_2022/uf=<UF>/, counts the rows against the
    file's own lines, derives lake/cnefe_2022_cep/ (the addresses, private households, median position, spread, coordinate
    levels and census tracts of each CEP and municipality) and checks the counts against IBGE's aggregate by CEP.
    Idempotent: a landed UF is skipped.
    """
    from ..sources.ibge_cnefe import build_cnefe

    result = build_cnefe(uf, _writer(root), keep_raw=keep_raw, force=force, check=check, log=lambda text: console.print(text, markup=False, highlight=False))
    _emit({**result, "ufs": {k: {"records": v["rows"], "cep_rows": v["ceps"]["rows"], "skipped": v.get("skipped", False)}
                             for k, v in result["ufs"].items()}}, as_json, "cnefe")
    if result["failed"]:
        raise typer.Exit(code=1)


@app.command(rich_help_panel="PIPELINE")
def extract(
    dataset: Annotated[str, typer.Argument(help="e.g. SIASUS-PA")],
    years: Annotated[str, typer.Option("--years", help="e.g. 2010-2025")],
    filters: Annotated[list[str], typer.Option("--filter", help="COLUMN=CODE,CODE (prefixes); repeat for several columns")],
    uf: Annotated[list[str] | None, typer.Option("--uf", help="only these states' files (the extract is then not whole)")] = None,
    workers: Annotated[int, typer.Option("--workers", help="files fetched at once")] = 6,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Keep the records of a dataset that the filters match, reading its files one by one (extract.py): for a dataset
    larger than the lake can hold."""
    from ..extract import build_extract

    parsed: dict[str, list[str]] = {}
    for f in filters:
        column, _, codes = f.partition("=")
        wanted = [c.strip() for c in codes.split(",") if c.strip()]
        if not column.strip() or not wanted:
            # a filter without a column or without a code matches nothing: every file would be fetched and kept as zero rows
            raise typer.BadParameter(f"{f!r} is not COLUMN=CODE[,CODE...]", param_hint="--filter")
        parsed.setdefault(column.strip(), []).extend(wanted)
    try:
        result = build_extract(dataset, _parse_years(years), parsed, ufs=uf, settings=_writer(root), log=console.print,
                               workers=workers)
    except ValueError as exc:      # a filter column in no file's header, refused before any fetch
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _emit({k: v for k, v in result.items() if k != "files"} | {"files_read": len(result["files"]),
          "kept": sum(v["kept"] for v in result["files"].values())}, as_json, "extract")


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
    from ..semantics.curation import CurationError, coverage_by_rung, load_curation

    settings = _writer(root)
    store = CatalogStore(settings.catalog_path)
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
    from ..sources.community import ingest as ingest_community

    settings = _writer(root)
    store = CatalogStore(settings.catalog_path)
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
    from ..sources.sigtap import SigtapUnavailable, ingest

    settings = _writer(root)
    store = CatalogStore(settings.catalog_path)
    try:
        with console.status("fetching SIGTAP…"):
            result = ingest(store, competencias=competencia, latest=latest)
        _emit(result, as_json, "sigtap")
    except SigtapUnavailable as exc:
        console.print(f"[red]SIGTAP unavailable: {exc}[/red]")
        raise typer.Exit(code=1) from exc
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
    from ..inventory.systems import adjudicate_prefix

    settings = _writer(root)
    store = CatalogStore(settings.catalog_path)
    try:
        _emit(adjudicate_prefix(store, prefix, system), as_json, "prefix adjudicated")
        console.print("[yellow]Re-run 'pegasus-data inventory' to re-derive the affected strata.[/yellow]")
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        store.close()


@app.command(name="prune", rich_help_panel="MAINTENANCE")
def prune(
    root: RootOpt = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Count what would go, delete nothing")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Delete downloaded files whose lake partitions are verified; refetched only if a rebuild needs them.

    The catalog keeps each file's checksum, size and path. The original DATASUS
    bytes cannot be regenerated from the lake; a refetch reproduces them. Kits,
    registries and files no partition was built from are kept.
    """
    from ..acquire.cache import BlobStore

    settings = _writer(root)
    catalog = CatalogStore(settings.catalog_path)
    try:
        result = BlobStore(settings.blobs_dir, catalog).prune_verified(settings.lake_dir, dry_run=dry_run)
        _emit(result, as_json, "prune (dry run)" if dry_run else "prune")
    finally:
        catalog.close()


@app.command(name="reencode-modelled", rich_help_panel="MAINTENANCE")
def reencode_modelled(
    product: Annotated[str, typer.Argument(help="Modelled product, e.g. population_account")],
    versions: Annotated[list[str] | None, typer.Argument(help="Versions to rewrite; all with a file when omitted")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Rewrite modelled versions with the current encoding (floats in BYTE_STREAM_SPLIT), value for value."""
    from ..modelled import reencode

    settings = _writer(root)
    base = Path(settings.lake_dir) / "modelled" / product
    names = versions or sorted(p.name for p in base.iterdir() if (p / "estimates.parquet").is_file())
    for name in names:
        _emit(reencode(product, name, settings=settings), as_json, f"reencode {name}")


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
    settings = _writer(root)
    catalog = CatalogStore(settings.catalog_path, strict_schema=False)
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


@app.command(name="download", rich_help_panel="PIPELINE")
def download(
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
    force: Annotated[bool, typer.Option(
        "--force", help="Re-read kits whose bytes and parsing code are unchanged since their last ingest")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Ingest TAB kits, parse .DEF/.CNV, build the dictionary. This is P1."""
    pipeline = _pipeline(root)
    try:
        with console.status("ingesting dictionaries…"):
            result = pipeline.semantics(systems=system, limit=limit, pdfs=pdfs, force=force)
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
    all_files: Annotated[bool, typer.Option("--all-files", help="Read EVERY dbc/dbf header, incrementally (ADR-0081)")] = False,
    workers: Annotated[int, typer.Option("--workers", help="FTP connections for --all-files")] = 8,
    whole_up_to_gb: Annotated[float, typer.Option(
        "--whole-up-to-gb", help="Fetch zipped DuckDB exports up to this size whole to describe them")] = 0.0,
    as_json: JsonOpt = False,
) -> None:
    """Census every stratum's columns by reading file headers, not payloads.

    A DBF declares its whole schema in a few hundred bytes, and a .dbc keeps that
    header uncompressed ahead of its compressed payload — so a ranged fetch
    settles what columns a file has for about 17 MB across the entire tree, where
    decoding one file per stratum would be 183 GiB.
    """
    pipeline = _pipeline(root)
    if all_files:
        try:
            def _tick(done: int, total: int) -> None:
                if done % 2000 == 0 or done == total:
                    print(f"[file census] {done}/{total}", flush=True)

            result = pipeline.file_schemas(systems=system, limit=limit, workers=workers, on_item=_tick)
            _emit(result.counts, as_json, "per-file schema census")
        finally:
            pipeline.close()
        return
    try:
        result = pipeline.schemas(systems=system, limit=limit, only_missing=not all_strata,
                                  whole_file_limit=int(whole_up_to_gb * 2**30) or None)
        _emit(result.counts, as_json, "schema census")
        if not as_json:
            from ..inventory.schemas import census_summary

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
def bindings(
    root: RootOpt = None,
    system: SystemsOpt = None,
    per_family: Annotated[int, typer.Option("--per-family", help="Files sampled per family, from distinct states")] = 2,
    as_json: JsonOpt = False,
) -> None:
    """Decide, once per family and field, which codelist labels each column.

    Samples real files from every family, weighs every bound codelist against
    the observed codes (per-state partitions collapsed, rollups excluded) and
    stores the decision in `label_bindings`, which ships in the seed. Run after
    `families` and `curate`, before `scripts/build_resources.py` (ADR-0072).
    """
    from ..semantics.label_bindings import compile_bindings

    settings = _writer(root)
    counts = compile_bindings(
        settings, systems=system, per_family=per_family,
        on_progress=None if as_json else (lambda line: console.print(f"[dim]{line}[/dim]")),
    )
    _emit(counts, as_json, "label bindings")
    if counts.get("failed") and not counts.get("families"):
        # Every sampled family failed: nothing was compiled, and a zero exit
        # let a maintainer chain carry on as if it had been (2026-09-29).
        console.print("[red]no family compiled; every sample failed[/red]")
        raise typer.Exit(code=1)


@app.command(rich_help_panel="PIPELINE")
def ledger(root: RootOpt = None, system: SystemsOpt = None, as_json: JsonOpt = False) -> None:
    """Build the metadata ledger, including dictionary_coverage per field."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.ledger(systems=system)
        _emit(result.counts, as_json, "ledger")
    finally:
        pipeline.close()


@app.command(name="aggregate-build", rich_help_panel="MAINTENANCE")
def aggregate_build_cmd(
    name: Annotated[str, typer.Argument(help="Aggregate name, e.g. sih_rd_municipality_month")],
    root: RootOpt = None,
    years: Annotated[str | None, typer.Option("--years", help="e.g. 2022 or 2020-2023")] = None,
    uf: Annotated[list[str] | None, typer.Option("--uf", help="Limit the build to these states")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Materialise an aggregate's base cuboid. A maintainer step, not a user one.

    Rows come from the ordinary retrieval path, so this costs what a fetch of
    the same span costs — once. Everything served from the artifact afterwards
    is arithmetic on a few thousand rows.
    """
    from .._aggregate import build_aggregate

    settings = _writer(root)
    wanted = _parse_years(years)
    if not wanted:
        console.print("[red]--years is required; an unbounded build would "
                      "download the whole publication history[/red]")
        raise typer.Exit(code=1)
    with console.status(f"building {name}…"):
        report = build_aggregate(name, years=wanted, uf=uf, settings=settings)
    _emit(report.as_dict(), as_json, f"aggregate-build {name}")
    for warning in report.warnings:
        console.print(f"[yellow]{warning}[/yellow]")


@app.command(name="labelpack", rich_help_panel="MAINTENANCE")
def labelpack_cmd(
    root: RootOpt = None,
    out: Annotated[Path, typer.Option("--out", help="Where to write the pack")] = Path(
        "src/pegasus_data/resources/labels.parquet"
    ),
    carry_from: Annotated[
        Path | None,
        typer.Option("--carry-from", help="Pack whose windows the catalog lacks are kept (default: the shipped one)"),
    ] = None,
    as_json: JsonOpt = False,
) -> None:
    """Rebuild the label pack the package ships.

    A maintainer step, not a user one: it reads the local catalog's dictionary
    and distils it into the file that lets `fetch(labels=True)` translate on a
    fresh install with no network. Run it after `semantics`.
    """
    from ..labelpack import build_label_pack

    pipeline = _pipeline(root)
    try:
        report = build_label_pack(pipeline.catalog, out, carry_from=carry_from)
        counts = dict(report.counts)
        _emit(counts, as_json, "label pack")
        if report.held_back and not as_json:
            console.print(
                f"[dim]held back {len(report.held_back)} entity registries; "
                f"reach them with fetch(\"CNES-ST\") and the CNES join key[/dim]"
            )
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
        from ..persist.reference import (
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
    as_json: JsonOpt = False,
) -> None:
    """Persist the DEMAS OpenAPI document and set the endpoints curation/intake.yml declares against it. The API's tables
    are read by their intake declarations, not here."""
    pipeline = _pipeline(root)
    try:
        builder = Builder(pipeline)
        with console.status("reading the DEMAS OpenAPI document…"):
            result = builder.demas()
        _emit(result.counts, as_json, "demas")
        for note in result.notes[:10]:
            console.print(f"[yellow]note[/yellow] {note}")
    finally:
        pipeline.close()


def _optional(pipeline: Pipeline, stage: str) -> StageResult:
    """Run a network-dependent source, reporting failure instead of raising.

    SIGTAP lives on a different host and the community source on GitHub; either
    can be unreachable behind a firewall or on a bad day. Neither is worth
    ending a multi-hour run for, and a stage that says why it produced nothing
    is honest in a way a crashed pipeline is not.
    """
    try:
        if stage == "sigtap":
            from ..sources.sigtap import ingest as run

            return StageResult(stage, counts=run(pipeline.catalog))
        from ..sources.community import ingest as run_community

        return StageResult(stage, counts=run_community(pipeline.catalog))
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        pipeline.catalog.log_event(
            stage, "optional source unavailable", level="warn", detail=f"{type(exc).__name__}: {exc}"
        )
        return StageResult(stage, counts={"skipped": True, "reason": f"{type(exc).__name__}: {exc}"})


def _write_reference(pipeline: Pipeline) -> StageResult:
    from ..persist.reference import (
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
    from ..semantics.curation import load_curation

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


@app.command(rich_help_panel="PIPELINE")
def snapshot(
    root: RootOpt = None,
    only: Annotated[list[str] | None, typer.Option("--only", help="Declared series to run (curation/snapshots.yml); default all")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="List and report what would be fetched, fetch nothing")] = False,
    max_gb: Annotated[float, typer.Option("--max-gb", help="Refuse a run that would fetch more new GiB than this")] = 5.0,
    versions: Annotated[str | None, typer.Option("--versions", help="List the kept versions of paths containing this text, and fetch nothing")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Keep the preliminary and current-year files DATASUS rewrites in place.

    Lists the declared series again, fetches only files whose listed size or
    modification time changed since their last kept version, and stores each
    version beside the others (ADR-0141). Nothing is deleted. Schedule it daily
    (RUNBOOK §8). Read a past state with query(..., as_of="2026-09-30").
    """
    from .. import snapshot as snap

    settings = _writer(root)
    if versions is not None:
        _emit(snap.versions(versions, settings=settings), as_json, "versions")
        return
    try:
        report = snap.snapshot(
            settings, only=only, dry_run=dry_run, max_bytes=int(max_gb * 2**30),
            on_progress=lambda message: console.print(message),
        )
    except snap.SnapshotRefused as exc:
        console.print(f"[red]refused:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _emit(report.as_dict(), as_json, "snapshot")
    if report.errors or report.listing_failures:
        raise typer.Exit(code=1)
