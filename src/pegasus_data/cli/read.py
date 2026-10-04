"""Reading data: query, explore, describe, link, and the semantic layer's questions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ..build import Builder
from ..catalog.store import CatalogStore
from ..config import load_settings
from ._common import (
    JsonOpt,
    RootOpt,
    SystemsOpt,
    _emit,
    _parse_years,
    _pipeline,
    _settings,
    app,
    console,
)

adjudicate_app = typer.Typer(
    name="adjudicate",
    help="Inspect evidence for unresolved semantics and apply reviewed decisions.",
    no_args_is_help=True,
)


app.add_typer(adjudicate_app, rich_help_panel="UNDERSTAND")


@adjudicate_app.command("show")
def adjudicate_show(
    key: str, root: RootOpt = None, as_json: JsonOpt = False
) -> None:
    from ..semantics.relations import adjudication_evidence

    store = CatalogStore(_settings(root).catalog_path)
    try:
        _emit(adjudication_evidence(store, key), as_json, key)
    finally:
        store.close()


@adjudicate_app.command("export")
def adjudicate_export(key: str, out: Path, root: RootOpt = None) -> None:
    """Write a compact JSON evidence package suitable for human/AI review."""
    from ..semantics.relations import adjudication_evidence

    store = CatalogStore(_settings(root).catalog_path)
    try:
        payload = adjudication_evidence(store, key)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    finally:
        store.close()
    console.print(f"[green]wrote[/green] {out}")


@adjudicate_app.command("apply")
def adjudicate_apply(
    key: str,
    decision: Annotated[Path, typer.Option("--decision", help="Reviewed YAML decision")],
    by: Annotated[str, typer.Option("--by", help="Reviewer identity")],
    root: RootOpt = None,
) -> None:
    from ..ontology import _read_yaml
    from ..semantics.relations import RelationType, SemanticRelation, adjudicate

    body = _read_yaml(decision)
    relation = SemanticRelation(
        system=str(body["system"]).upper(),
        dataset=str(body.get("dataset", "")).upper(),
        field_name=str(body["field"]).upper(),
        relation_type=RelationType(str(body["relation"])),
        target_type=str(body["target_type"]),
        target_name=str(body.get("target_name", "")),
        artifact=str(body["artifact"]),
        source_namespace=body.get("source_namespace"),
        target_namespace=body.get("target_namespace"),
        evidence=json.dumps(body.get("evidence", []), ensure_ascii=False),
    )
    store = CatalogStore(_settings(root).catalog_path)
    try:
        adjudicate(store, key, relation, by=by)
    finally:
        store.close()
    console.print(f"[green]adjudicated[/green] {key}")


@app.command("aggregate-suggest", rich_help_panel="UNDERSTAND")
def aggregate_suggest(
    dataset: Annotated[str, typer.Argument(help="e.g. SIH-RD, SIM-DO, SINAN-DENG")],
    uf: Annotated[str | None, typer.Option("--uf", help="State to measure; omit --uf for one-file-a-year datasets")] = "PE",
    year: Annotated[int, typer.Option("--year")] = 2022,
    max_levels: Annotated[int, typer.Option("--max-levels")] = 40,
    root: RootOpt = None,
) -> None:
    """Rank a dataset's fields as dimension candidates, with the cost measured.

    Cardinality is MEASURED on one real state-year, meaning comes from
    curation, and the cost column counts the distinct key combinations each
    dimension would add. The output is evidence for writing a spec, not a
    spec: a dimension stays an analytical claim.
    """
    from ..suggest import suggest

    with console.status("measuring…"):
        result = suggest(
            dataset, uf=uf or None, years=year, max_levels=max_levels,
        )
    console.print(
        f"[bold]{result.dataset}[/bold] · {result.rows:,} rows measured · "
        f"base municipality×month = {result.base_cells:,} cells"
    )
    from rich.table import Table as _Table

    table = _Table(show_edge=False)
    for column in ("field", "levels", "nulls", "coded", "cells if added", "meaning"):
        table.add_column(column)
    for c in result.candidates:
        table.add_row(
            c.field_name,
            str(c.distinct),
            f"{c.null_share:.0%}",
            c.code_system or "—",
            f"{c.cumulative_cells:,}",
            (c.translated_name or c.description or "")[:46],
        )
    console.print(table)
    console.print(
        f"[dim]{len(result.skipped)} fields skipped "
        "(axes, identifiers, constants, or too many levels — band those)[/dim]"
    )


@app.command(rich_help_panel="UNDERSTAND")
def search(
    query: Annotated[str, typer.Argument(help="Words to look for, e.g. 'raça' or 'Parda'")],
    kind: Annotated[
        str | None, typer.Option("--kind", help="variable | dataset | code")
    ] = None,
    system: Annotated[str | None, typer.Option("--system", "-s", help="One system, e.g. SIHSUS")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 25,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Search variable names, descriptions, datasets and every code label.

    "Which column is about race" and "which code means Parda" are the same
    question to ask here. Accents are folded, so both spellings find it. Reads
    the catalog and the shipped label pack; no dictionary build is needed.
    """
    from .._search import search as _search

    hits = _search(query, kind=kind, system=system, limit=limit, root=root)
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
    from .._compendium import compendium as _compendium

    report = _compendium(
        out, systems=system, codes=codes, max_codes=max_codes,  # type: ignore[arg-type]
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
    from .._info import info as _info

    answer = _info(target, field_name=field, root=root)
    if as_json:
        _emit(answer.as_dict(), True)
        return
    console.print(str(answer))


@app.command()
def workbook(
    artifact: Annotated[str, typer.Argument(help="A built aggregate artifact, e.g. sih_rd_municipality_month")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Workbook path (default: <artifact>.xlsx here)")] = None,
    root: RootOpt = None,
) -> None:
    """Write a built artifact as an Excel workbook: national, monthly, UF,
    municipality and per-dimension sheets, each its own aggregation."""
    from ..workbook import build

    settings = load_settings(root=Path(root) if root else None)
    target = out or Path(f"{artifact}.xlsx")
    path = build(artifact, target, settings=settings)
    console.print(f"{path} ({path.stat().st_size / 1_048_576:.1f} MB)")


@app.command(name="aggregate", rich_help_panel="EXTRACT")
def aggregate_cmd(
    name: Annotated[str, typer.Argument(help="Aggregate name")],
    root: RootOpt = None,
    by: Annotated[list[str] | None, typer.Option("--by", help="Level per axis, e.g. --by health_region --by year")] = None,
    measure: Annotated[list[str] | None, typer.Option("--measure", "-m")] = None,
    year: Annotated[str | None, typer.Option("--year")] = None,
    uf: Annotated[str | None, typer.Option("--uf")] = None,
    system: Annotated[str | None, typer.Option("--system", help="Whose regionalisation to roll up through")] = None,
    out: Annotated[Path | None, typer.Option("--out")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "csv",
    as_json: JsonOpt = False,
) -> None:
    """Serve cells from a built aggregate. An axis you do not name is totalled."""
    from .._aggregate import aggregate as _aggregate

    where: dict[str, object] = {}
    if year:
        where["year"] = [y.strip() for y in year.split(",") if y.strip()]
    if uf:
        where["uf"] = uf
    table, report = _aggregate(
        name, measures=measure or None, by=by or None, where=where or None,
        system=system, settings=_settings(root), return_report=True,
    )
    if out:
        from ..api import write_table

        write_table(table, out, fmt)
        console.print(f"[green]wrote[/green] {out}  ({table.num_rows:,} cells)")
    _emit(report.as_dict(), as_json, f"aggregate {name}")
    for warning in report.warnings:
        console.print(f"[yellow]{warning}[/yellow]")


@app.command(rich_help_panel="EXPLORE")
def systems(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """What information systems are in the lake, and how much of each."""
    from ..api import Catalog as PublicCatalog

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
    store = CatalogStore(settings.catalog_path, read_only=settings.catalog_path.exists())
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
    from ..api import Catalog as PublicCatalog

    settings = _settings(root)
    public = PublicCatalog(settings.root, settings=settings)
    try:
        _emit(public.coverage(system, series), as_json, f"coverage {system}")
    finally:
        public.close()


@app.command(rich_help_panel="EXPLORE")
def explore(
    target: Annotated[str | None, typer.Argument(help="System or dataset, e.g. SIHSUS or SIH-RD")] = None,
    root: RootOpt = None,
    year: Annotated[int | None, typer.Option("--year", help="List the files for this year")] = None,
    uf: Annotated[str | None, typer.Option("--uf", help="Limit to one state")] = None,
    everything: Annotated[
        bool, typer.Option("--all-roles", help="Include dictionary and documentation files")
    ] = False,
    as_json: JsonOpt = False,
) -> None:
    """What DATASUS has — answered from the map, without downloading anything.

    No argument lists the information systems. A system lists its series. A
    dataset gives coverage by year. Adding --year lists the files themselves,
    with sizes, which is what you want before committing to a download.

    Works on a fresh install with no crawl and no network: the catalog starts
    from the seed the package ships (ADR-0067). `crawl` brings it up to date,
    and the result names the crawl date behind it.
    """
    from .._explore import explore as explore_tree

    try:
        result = explore_tree(
            target, year=year, uf=uf, role=None if everything else "data", root=root,
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
    present: Annotated[str | None, typer.Option("--present", help="readable | analysis | labels | codes (ADR-0084)")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Label DATASUS data you already have. No download, no lake.

    For the extract someone mailed you, or pulled from TabNet, or fetched with
    R's microdatasus. --system is required: SEXO=3 is Feminino in SIHSUS and
    undefined in SINASC, so labelling without it would be guessing.
    """
    from .._translate import TranslationImpossible
    from .._translate import translate as translate_table

    try:
        with console.status(f"labelling {path.name}…"):
            table, result = translate_table(
                path, system=system, year=year, profile="audit", root=root, report=True
            )
        from ..catalog.store import CatalogStore
        from ..presentation import documented_names
        from ..presentation import present as apply_presentation

        settings = _settings(root)
        store = CatalogStore(settings.catalog_path, read_only=True)
        try:
            table = apply_presentation(
                table, present or settings.presentation, names=documented_names(store, system.upper())  # type: ignore[arg-type]
            )
        finally:
            store.close()
    except TranslationImpossible as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    target = out or path.with_name(f"{path.stem}_labelled.{fmt}")
    from ..api import write_table

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


@app.command(name="link", rich_help_panel="EXTRACT")
def link_cmd(
    spec: Annotated[str | None, typer.Argument(help="A link spec from curation/links.yml; omit to list them")] = None,
    period: Annotated[str | None, typer.Option("--period", "-p", help="2022, 2022-01, or 2020..2022")] = None,
    geography: Annotated[str | None, typer.Option("--geo", "-g", help="AC, or AC,RR, or BR")] = None,
    right_geography: Annotated[
        str | None, typer.Option("--right-geo", help="Read the right side over another scope, e.g. BR (ADR-0120)")
    ] = None,
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write the pairs (parquet or csv)")] = None,
    method: Annotated[
        str, typer.Option("--method", "-m", help="deterministic (exact passes) | probabilistic (ADR-0111)")
    ] = "deterministic",
    allow_not_viable: Annotated[
        bool, typer.Option("--allow-not-viable", help="Return the pairs of a linkage that fails its verdict")
    ] = False,
    allow_partial: Annotated[
        bool, typer.Option("--allow-partial", help="Accept a side short of a file that will not download or open")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Recompute even when a stored run of this spec and scope exists")
    ] = False,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Link records about the same person across two datasets (ADR-0107, ADR-0110).

    'pegasus-data link sih_deaths_to_sim --period 2022 --geo RR'. Prints every
    pass with its negative control (the same join with a birth date shifted by
    a week: its pairs are coincidences), the held-out validations and the
    verdict. A linkage that is not viable exits 1 unless --allow-not-viable.
    """
    from ..linkage.engine import LinkNotViable, link, load_links
    from ..retrieve import DatasetUnknown, NothingPublished

    specs = load_links()
    if not spec:
        _emit({name: s.description for name, s in specs.items()}, as_json, "link specs")
        return
    if not period or not geography:
        console.print("[red]--period and --geo are required[/red]")
        raise typer.Exit(code=2)
    span: object = tuple(part.strip() for part in period.split("..")) if ".." in period else period.strip()
    geo: object = [g.strip() for g in geography.split(",")] if "," in geography else geography.strip()
    try:
        with console.status(f"linking {spec}…"):
            result = link(spec, period=span, geography=geo, right_geography=right_geography, method=method,
                          allow_not_viable=allow_not_viable, allow_partial=allow_partial, refresh=refresh,
                          settings=_settings(root))
    except LinkNotViable as exc:
        _emit(exc.result.summary(), as_json, f"link {spec}: NOT VIABLE")
        raise typer.Exit(code=1) from exc
    except (KeyError, DatasetUnknown, NothingPublished, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    summary = result.summary()
    summary.pop("models", None) if not as_json else None
    _emit(summary, as_json, f"link {spec} ({method})")
    if out:
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        if out.suffix.lower() == ".csv":
            pacsv.write_csv(result.pairs, out)
        else:
            pq.write_table(result.pairs, out)
        console.print(f"[green]wrote[/green] {out}  ({result.pairs.num_rows:,} pairs)")


@app.command(name="link-discover", rich_help_panel="EXTRACT")
def link_discover_cmd(
    left: Annotated[str, typer.Argument(help="A dataset with roles (curation/roles.yml), e.g. SINASC-DN")],
    right: Annotated[str, typer.Argument(help="The other dataset, e.g. SIH-RD")],
    period: Annotated[str, typer.Option("--period", "-p", help="2022, or 2020..2022")],
    geography: Annotated[str, typer.Option("--geo", "-g", help="AC, or AC,RR, or BR")],
    top: Annotated[int, typer.Option("--top", help="How many keys to show")] = 10,
    allow_partial: Annotated[
        bool, typer.Option("--allow-partial", help="Accept a side short of a file that will not download or open")
    ] = False,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Measure which fields carry people shared by two datasets (ADR-0119).

    'pegasus-data link-discover SINASC-DN SIH-RD --period 2022 --geo RR'. Every
    key built from type-compatible roles is counted against a placebo (left
    dates shifted a week); keys are ranked by the pairs they isolate beyond
    chance.
    """
    from ..linkage.discover import discover_links
    from ..retrieve import DatasetUnknown, NothingPublished

    span: object = tuple(part.strip() for part in period.split("..")) if ".." in period else period.strip()
    geo: object = [g.strip() for g in geography.split(",")] if "," in geography else geography.strip()
    try:
        with console.status(f"discovering {left} ~ {right}…"):
            results = discover_links(left, right, period=span, geography=geo, allow_partial=allow_partial,
                                     settings=_settings(root))
    except (KeyError, DatasetUnknown, NothingPublished, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _emit([r.summary() for r in results[:top]], as_json, f"link discovery {left} ~ {right}")


@app.command(name="link-entities", rich_help_panel="EXTRACT")
def link_entities_cmd(
    period: Annotated[str, typer.Option("--period", "-p", help="The scope of stored links, e.g. 2022")],
    geography: Annotated[str, typer.Option("--geo", "-g", help="The scope of stored links, e.g. BR")],
    method: Annotated[str, typer.Option("--method", "-m", help="probabilistic | deterministic")] = "probabilistic",
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Merge the stored links of a scope into persons (docs/plans/linkage-theory.md §3.3).

    'pegasus-data link-entities --period 2022 --geo BR'. Reports persons by
    number of records, and per link how many of its pairs were merged, were
    already one person through other links, or were refused because the merge
    would give one person two birth records or two deaths.
    """
    from ..linkage.entities import build_entities

    try:
        with console.status("merging links into persons…"):
            entities = build_entities(period=period, geography=geography, method=method, settings=_settings(root))
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _emit(entities.summary(), as_json, f"entities {geography} {period}")


@app.command(name="query", rich_help_panel="EXTRACT")
def query_cmd(
    dataset: Annotated[str, typer.Argument(help="Dataset: SIH.RD, SIM.DO, SINASC.DN (SIH-RD works too)")],
    period: Annotated[
        str | None, typer.Option("--period", "-p", help="2023, 2023-01, or a range 2020..2023 / 2022-01..2022-06")
    ] = None,
    geography: Annotated[
        str | None, typer.Option("--geo", "-g", help="State(s) whose publications to read: AL, or AL,SE")
    ] = None,
    select: Annotated[list[str] | None, typer.Option("--select", "-c", help="Columns to keep (labels follow)")] = None,
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write the table here instead of summarising")] = None,
    fmt: Annotated[str | None, typer.Option("--format", help="csv | parquet | xlsx (default: from --out)")] = None,
    present: Annotated[
        str | None,
        typer.Option("--present", help="readable (default) | analysis | labels | codes  (ADR-0084)"),
    ] = None,
    values: Annotated[
        str | None, typer.Option("--values", help='Value template, e.g. "{label} ({code})" or "{code} - {label}"')
    ] = None,
    names: Annotated[
        str | None, typer.Option("--names", help='Header template, e.g. "{name} ({code})" or "{code}"')
    ] = None,
    language: Annotated[str | None, typer.Option("--language", help="pt | en: which documented name heads a column")] = None,
    dictionary_out: Annotated[
        Path | None,
        typer.Option("--dictionary", help="Also write the table's data dictionary (.md, .csv, .json or .parquet)"),
    ] = None,
    allow_unbounded: Annotated[
        bool, typer.Option("--allow-unbounded", help="Permit a query with no --period (every year on the server)")
    ] = False,
    allow_partial: Annotated[
        bool, typer.Option("--allow-partial", help="Accept a short table when a source file will not download or open")
    ] = False,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Get a dataset, labelled: the command-line form of query() (ADR-0073).

    'pegasus-data query SIH.RD --period 2023-01 --geo AL --out sih.csv'. Reads a
    lake you built where it covers the request and the FTP server otherwise;
    every coded value reads "Masculino (1)" under "Sexo do paciente (SEXO)" unless
    --present or the templates say otherwise. `plan` first, to see what it will
    read: 'pegasus-data query SIH.RD --period 2023 --geo AL' without --out
    prints the plan and a summary.
    """
    from .._query_engine import plan as plan_query
    from .._query_engine import query as run_query
    from ..retrieve import DatasetUnknown, NothingPublished

    settings = _settings(root)
    span: object = None
    if period:
        span = tuple(part.strip() for part in period.split("..")) if ".." in period else period.strip()
    try:
        console.print(plan_query(dataset, period=span, geography=geography, settings=settings,
                                 allow_unbounded=allow_unbounded).explain())
        with console.status(f"querying {dataset}…"):
            # The canonical form first: the dictionary is written from it, and
            # the presentation is applied to it once, below.
            table, report = run_query(
                dataset, period=span, geography=geography, select=select, present="analysis",
                allow_unbounded=allow_unbounded, allow_partial=allow_partial, settings=settings,
                return_report=True,
            )
    except (DatasetUnknown, NothingPublished, ValueError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    labelled = sum(1 for c in table.column_names if c.endswith("_label"))
    from .._dictionary import describe_table
    from ..catalog.store import CatalogStore
    from ..presentation import documented_names
    from ..presentation import present as apply_presentation
    from ..retrieve import parse_dataset

    system = parse_dataset(dataset)[0]
    store = CatalogStore(settings.catalog_path, read_only=True)
    try:
        if dictionary_out:
            _, book = describe_table(store, system, table, dataset=dataset)
            book.write(dictionary_out)
            console.print(f"[green]wrote[/green] {dictionary_out}  ({len(book)} columns described)")
        overrides = {k: v for k, v in {"values": values, "names": names, "language": language}.items() if v}
        spec: object = {"preset": present, **overrides} if present else (overrides or None)
        if spec is None:
            spec = settings.presentation
        elif isinstance(spec, dict) and "preset" not in spec:
            spec = {"preset": settings.presentation if isinstance(settings.presentation, str) else "readable", **spec}
        table = apply_presentation(table, spec, names=documented_names(store, system))  # type: ignore[arg-type]
    finally:
        store.close()
    if out:
        from ..api import write_table

        chosen = fmt or (out.suffix.lstrip(".").lower() or "csv")
        write_table(table, out, chosen)
        console.print(f"[green]wrote[/green] {out}  ({table.num_rows:,} rows, {table.num_columns} columns)")
    summary = {
        "rows": table.num_rows,
        "columns": table.num_columns,
        "labelled": labelled,
        "strategy": report.source_strategy,
        "warnings": len(report.warnings),
    }
    _emit(summary, as_json, f"query {dataset}")
    for warning in report.warnings[:10]:
        console.print(f"[yellow]{warning}[/yellow]")


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
    rebuild: Annotated[
        bool,
        typer.Option(
            "--rebuild",
            help="Write every selected partition again. By default a partition whose "
            "source files and normalisation plan are unchanged, and whose Parquet is "
            "still on disk, is left alone.",
        ),
    ] = False,
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
                rebuild=rebuild,
            )
        _emit(result.counts, as_json, "build")
        if result.counts.get("errors"):
            # A file that would not fetch or decode is a gap, not an empty
            # success: say so in the exit status too.
            raise typer.Exit(code=1)
    finally:
        pipeline.close()


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
    from ..catalog.store import CatalogStore as Store
    from ..semantics.gaps import distinct_field_gaps, find_gaps, persist_gaps, summarise_gaps

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
    from ..api import Catalog as PublicCatalog
    from ..api import describe as describe_field

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
