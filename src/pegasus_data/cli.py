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
from .config import Settings, load_settings
from .pipeline import Pipeline
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


@app.command()
def crawl(
    root: RootOpt = None,
    host: Annotated[str | None, typer.Option("--host")] = None,
    base_path: Annotated[str | None, typer.Option("--base-path")] = None,
    connections: Annotated[int | None, typer.Option("--connections", "-c")] = None,
    resume: Annotated[bool, typer.Option("--resume", help="Skip directories already listed; retry open gaps")] = False,
    prefix: Annotated[list[str] | None, typer.Option("--prefix", help="Crawl only these subtrees")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Walk the FTP tree, recording files, metadata and unreachable paths."""
    pipeline = _pipeline(root, host=host, base_path=base_path, connections=connections)
    try:
        with console.status("crawling…"):
            result = pipeline.crawl(resume=resume, prefixes=prefix)
        _emit(result.counts, as_json, "crawl")
        files = pipeline.catalog.count("files")
        with_size = pipeline.catalog.count("files", "size IS NOT NULL")
        console.print(f"[green]{files}[/green] files known, [green]{with_size}[/green] carrying size and mtime")
    finally:
        pipeline.close()


@app.command()
def inventory(root: RootOpt = None, system: SystemsOpt = None, as_json: JsonOpt = False) -> None:
    """Parse filenames, infer per-directory date conventions, build strata. No network."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.inventory(systems=system)
        _emit(result.counts, as_json, "inventory")
    finally:
        pipeline.close()


@app.command()
def sample(root: RootOpt = None, system: SystemsOpt = None, limit: Annotated[int | None, typer.Option("--limit")] = None, as_json: JsonOpt = False) -> None:
    """Choose one file per schema stratum."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.sample(systems=system, limit=limit)
        _emit(result.counts, as_json, "sample")
    finally:
        pipeline.close()


@app.command()
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


@app.command()
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


@app.command()
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


@app.command()
def families(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Build schema-signature families, representations, drift and rename candidates."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.families()
        _emit(result.counts, as_json, "families")
    finally:
        pipeline.close()


@app.command()
def ledger(root: RootOpt = None, system: SystemsOpt = None, as_json: JsonOpt = False) -> None:
    """Build the metadata ledger, including dictionary_coverage per field."""
    pipeline = _pipeline(root)
    try:
        result = pipeline.ledger(systems=system)
        _emit(result.counts, as_json, "ledger")
    finally:
        pipeline.close()


@app.command()
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


@app.command()
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


@app.command()
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


@app.command()
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


@app.command()
def report(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Coverage, dictionary_coverage, and the open questions."""
    settings = _settings(root)
    from .catalog.store import Catalog as Store
    from .inventory.strata import coverage_by_system
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


@app.command()
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


@app.command()
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


@app.command()
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


@app.command(name="all")
def run_everything(
    root: RootOpt = None,
    system: SystemsOpt = None,
    prefix: Annotated[list[str] | None, typer.Option("--prefix")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Cap strata profiled and files per family")] = None,
    resume: Annotated[bool, typer.Option("--resume")] = False,
) -> None:
    """crawl → inventory → semantics → profile → families → ledger → build."""
    pipeline = _pipeline(root)
    try:
        stages = [
            ("crawl", lambda: pipeline.crawl(resume=resume, prefixes=prefix)),
            ("inventory", lambda: pipeline.inventory(systems=system)),
            ("semantics", lambda: pipeline.semantics(systems=system)),
            ("profile", lambda: pipeline.profile(systems=system, limit=limit)),
            ("families", pipeline.families),
            ("ledger", lambda: pipeline.ledger(systems=system)),
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
