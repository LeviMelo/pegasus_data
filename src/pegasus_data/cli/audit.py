"""Audits: verification, quality and coverage reports."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ..catalog.store import CatalogStore
from ..verify import run_all, summarise
from ._common import (
    JsonOpt,
    RootOpt,
    SystemsOpt,
    _emit,
    _fmt,
    _settings,
    app,
    console,
)


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
    from ..semantics.icd import flag_suspect_bindings, measure_icd_columns, persist_token_rules

    settings = _settings(root)
    store = CatalogStore(settings.catalog_path, read_only=not write)
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


@app.command(rich_help_panel="AUDIT")
def meaning(
    root: RootOpt = None,
    system: SystemsOpt = None,
    out: Annotated[Path | None, typer.Option("--out", help="Write every (family, field) row here (.csv or .parquet)")] = None,
    as_json: JsonOpt = False,
) -> None:
    """How much is described and translatable, field by field (ADR-0085).

    Every field of every family: is it described from a source, and does a
    table decode every code observed in real samples? The standard is total;
    this is the distance to it.
    """
    import pyarrow as pa

    from ..catalog.store import CatalogStore
    from ..semantics.coverage import as_records, measure, summarise

    settings = _settings(root)
    store = CatalogStore.shared(settings.catalog_path)
    try:
        rows = measure(store, system)
    finally:
        store.close()
    _emit(summarise(rows), as_json, "coverage (distinct fields per system, at their worst family)")
    if out:
        from ..api import write_table

        write_table(pa.Table.from_pylist(as_records(rows)), out, out.suffix.lstrip(".") or "csv")
        console.print(f"[green]wrote[/green] {out}  ({len(rows):,} family-field rows)")


@app.command(rich_help_panel="AUDIT")
def findings(
    root: RootOpt = None,
    open_only: Annotated[bool, typer.Option("--open", help="Only unresolved questions")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Everything measured that contradicted an assumption, resolved and open."""
    settings = _settings(root)
    store = CatalogStore(settings.catalog_path, read_only=settings.catalog_path.exists())
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


@app.command(rich_help_panel="AUDIT")
def report(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Coverage, dictionary_coverage, and the open questions."""
    settings = _settings(root)
    from ..catalog.store import CatalogStore as Store
    from ..inventory.strata import coverage_by_system
    from ..inventory.systems import low_trust_prefixes
    from ..semantics.dictionary import conflicts_report
    from ..semantics.ledger import coverage_report
    from ..semantics.reference import reference_summary

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
    from ..catalog.store import CatalogStore as Store

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


@app.command(rich_help_panel="AUDIT")
def verify(
    root: RootOpt = None,
    step: Annotated[list[int] | None, typer.Option("--step", help="Only these §12 steps")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Run the §12 regression assertions."""
    settings = _settings(root)
    from ..catalog.store import CatalogStore as Store

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
