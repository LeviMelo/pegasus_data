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
from ..ontology import dataset_key
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
    from ..semantics.curation import read_yaml
    from ..semantics.relations import RelationType, SemanticRelation, adjudicate

    body = read_yaml(decision, missing_ok=True)
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
            dataset, uf=uf or None, years=year, max_levels=max_levels, settings=_settings(root),
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
    for note in result.notes:
        console.print(f"[yellow]note[/yellow] {note}")
    if result.skipped:
        left_out = _Table(title=f"{len(result.skipped)} fields left out", show_edge=False)
        left_out.add_column("field")
        left_out.add_column("why")
        for name, why in result.skipped:
            left_out.add_row(name, why)
        console.print(left_out)


@app.command(rich_help_panel="UNDERSTAND")
def search(
    query: Annotated[str, typer.Argument(help="Words to look for, e.g. 'raça' or 'Parda'")],
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="dataset | variable | field | product | role | event | link | aggregate | operation | sidra | code"),
    ] = None,
    system: Annotated[str | None, typer.Option("--system", "-s", help="One system, e.g. SIHSUS")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 25,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Find anything pegasus_data holds or can do: datasets, columns, context fields, roles, events, links,
    aggregates, functions and commands, SIDRA tables and code labels, each with the call that gets it.

    "Which column is about race", "is there rainfall by municipality" and "which code means Parda" are the same
    question to ask here. Every word must match; accents are folded. Reads the home's map (`compendium`), rebuilt
    when what it describes has changed.
    """
    from .._search import search as _search

    hits = _search(query, kind=kind, system=system, limit=limit, root=root)
    if not hits:
        console.print(f"[yellow]nothing matches {query!r}[/yellow]")
        return
    _emit(hits, as_json, f"search: {query}")


@app.command(name="compendium", rich_help_panel="UNDERSTAND")
def compendium_cmd(
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the .sqlite (default: the home's own map)")] = None,
    system: SystemsOpt = None,
    codes: Annotated[str, typer.Option("--codes", help="none | internal | bound | all")] = "none",
    max_codes: Annotated[int, typer.Option("--max-codes", help="Codelists larger than this count as external under --codes internal")] = 1000,
    values: Annotated[bool, typer.Option("--values/--no-values", help="Include observed value frequencies")] = False,
    files: Annotated[bool, typer.Option("--files/--no-files", help="Include the raw file listing")] = False,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Write the map of everything pegasus_data holds and can do, as one SQLite file.

    Which systems and datasets exist, their years and states on the server and in the lake, every column with its
    meaning, the codelist a query labels it with and how often it is filled; the context fields, roles, event types,
    links, aggregates, SIDRA tables, and every function and command. Code meanings and value frequencies are opt-in
    because they are what makes such a file large. Without --out it refreshes the home's own map, which `search` reads.
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


@app.command(name="manual", rich_help_panel="UNDERSTAND")
def manual_cmd(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Write the manual: the home's map as text files to grep and read (`<home>/manual/`, `INDEX.md` first).

    One page per dataset, per dataset's columns and roles, per link, and pages for the context fields, products,
    operations and SIDRA tables, generated from the map (rebuilt first when stale). The map's background rebuild
    writes it too."""
    from .._manual import manual_dir, write_manual
    from ..config import load_settings

    counts = write_manual(root=root)
    where = manual_dir(load_settings(root=root))
    if as_json:
        _emit({"manual": str(where), **counts}, True)
        return
    console.print(f"manual written to {where}: " + ", ".join(f"{v} {k}" for k, v in counts.items()))


@app.command(name="roles", rich_help_panel="UNDERSTAND")
def roles_cmd(
    dataset: Annotated[str, typer.Argument(help="A dataset: SIM-DO, SINASC-DN, SIH-RD, CIHA, SINAN-DENG ...")],
    as_json: JsonOpt = False,
) -> None:
    """What each column of a dataset states: entity.property, value kind, model role, and the unit of a measure."""
    from ..semantics.column_roles import roles as _roles

    rows = _roles(dataset)
    if as_json:
        _emit(rows, True)
        return
    table = Table(title=f"roles of {dataset}")
    for header in ("column", "role", "kind", "model", "unit", "domain", "name"):
        table.add_column(header)
    for row in rows:
        mark = "" if row["reviewed"] else " (draft)"
        unit = (row["unit"] + (f" of {row['unit_of']}" if row.get("unit_of") else "")) if row["unit"] else (
            "unknown" if row.get("unit_unknown") else "")
        table.add_row(row["column"], row["role"] + mark, row["kind"], row["model"], unit, str(row["fact_domain"] or ""),
                      str(row["name"] or ""))
    console.print(table)


@app.command(name="events", rich_help_panel="UNDERSTAND")
def events_cmd(
    dataset: Annotated[str, typer.Argument(help="A dataset: SIH-RD, SIM-DO, SINASC-DN, CIHA, SINAN-DENG ...")],
    as_json: JsonOpt = False,
) -> None:
    """The event types a dataset's rows become: classifiers, which rows count, how rows consolidate."""
    from ..semantics.event_types import event_types as _event_types

    rows = _event_types(dataset)
    if as_json:
        _emit(rows, True)
        return
    for row in rows:
        classifiers = ", ".join(f"{c['column']} ({c['role']})" for c in row["classifiers"]) or "none"
        status = row["status"]
        console.print(f"[bold]{row['name']}[/bold] ({row['kind']}): {row['grain'] or ''}")
        console.print(f"  classifiers: {classifiers}")
        if status:
            console.print(f"  counts rows with {status['column']} in {status['values']}")
        cons = row["consolidation"] or {}
        if cons.get("key"):
            console.print(f"  one event per distinct {cons['key']}")
        if cons.get("chain"):
            # a stay chains its AIHs (continuations, transfers) per person; there is no single key to name
            chain = cons["chain"]
            console.print(f"  one event per chain of rows of one person {chain.get('person')}, from {chain.get('start')} "
                          f"to {chain.get('end')}, continued by {chain.get('reason')} in {chain.get('continues')} "
                          f"(transfer {chain.get('transfer')}) within {chain.get('gap_days')} day(s)")
        if row["evidence"]:
            console.print(f"  evidence: {row['evidence']}")


@app.command(name="holdings", rich_help_panel="UNDERSTAND")
def holdings_cmd(
    check: Annotated[bool, typer.Option("--check", help="Exit 1 when any store holds variables nothing describes")] = False,
    show: Annotated[int, typer.Option("--show", help="Undescribed variables listed per store")] = 8,
    as_json: JsonOpt = False,
) -> None:
    """Every store of the home against what describes it, variable by variable: what is held and nothing describes."""
    from .._holdings import holdings

    rows = [h.as_dict() for h in holdings()]
    bad = [r for r in rows if r["defect"]]
    if as_json:
        _emit(bad if check else rows, True)
    else:
        console.print(f"{len(rows)} stores; {len(bad)} with defects; "
                      f"{sum(len(r['undescribed']) for r in bad)} variables held and undescribed")
        for r in sorted(bad, key=lambda r: -len(r["undescribed"])):
            opaque = f", {len(r['opaque_files'])} opaque files" if r["opaque_files"] else ""
            console.print(f"[bold]{r['store']}[/bold] ({r['describer'] or 'no describer'}): "
                          f"{len(r['undescribed'])} of {r['held'] or 0} undescribed{opaque}")
            if r["undescribed"][:show]:
                console.print("  " + ", ".join(r["undescribed"][:show]) + (" ..." if len(r["undescribed"]) > show else ""))
    if check and bad:
        raise typer.Exit(1)


@app.command(name="structure", rich_help_panel="UNDERSTAND")
def structure_cmd(
    name: Annotated[str | None, typer.Argument(help="ICD10, SIGTAP, CBO2002, CNAE20, CID-BR-10, ICSAP-GROUPS ...; none lists them")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Write the structure as .csv or .parquet")] = None,
    as_json: JsonOpt = False,
) -> None:
    """A code structure as data: a tree's nodes and parents, or a list's member codes."""
    from ..semantics.code_structures import code_structure, code_structures

    if name is None:
        _emit(code_structures(), as_json, "code structures")
        return
    table = code_structure(name)
    if out is not None:
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        (pq.write_table if out.suffix == ".parquet" else pacsv.write_csv)(table, out)
        console.print(f"wrote {out} ({table.num_rows:,} rows)")
        return
    _emit({"rows": table.num_rows, "columns": table.column_names, "first": table.slice(0, 5).to_pylist()},
          as_json, f"structure {name}")


@app.command(name="garbage-codes", rich_help_panel="UNDERSTAND")
def garbage_codes_cmd(
    edition: Annotated[str, typer.Argument(help="GBD2019 (default: the later list, levels where its appendix gives them) or GBD2017 (every code with its level)")] = "GBD2019",
    out: Annotated[Path | None, typer.Option("--out", help="Write the table as .csv or .parquet")] = None,
    as_json: JsonOpt = False,
) -> None:
    """The ICD-10 garbage codes of a published list with their GBD level (1 to 4) and package."""
    import json

    from ..semantics.code_structures import GARBAGE_METADATA, garbage_codes

    table = garbage_codes(edition)
    if out is not None:
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        (pq.write_table if out.suffix == ".parquet" else pacsv.write_csv)(table, out)
        console.print(f"wrote {out} ({table.num_rows:,} rows)")
        return
    meta = json.loads(table.schema.metadata[GARBAGE_METADATA])
    _emit({"rows": table.num_rows, "codes": meta["codes"], "study": meta["study"], "source": meta["source"], "licence": meta["licence"],
           "first": table.slice(0, 5).to_pylist()}, as_json, f"garbage codes {meta['edition']}")


@app.command(name="price-index", rich_help_panel="SOURCES")
def price_index_cmd(
    grain: Annotated[str, typer.Option("--grain", help="month (the monthly index number) or year (the mean of the year's twelve)")] = "month",
    reference: Annotated[str | None, typer.Option("--reference", help="A month (2025-12) or, with --grain year, a year: adds `factor`, nominal reais x factor = reais of that month")] = None,
    years: Annotated[str | None, typer.Option("--years", help="Rows to keep, e.g. 2014-2025")] = None,
    refresh: Annotated[bool, typer.Option("--refresh", help="Re-read the source first (IBGE's list of months; the BCB series), for those published since")] = False,
    index: Annotated[str, typer.Option("--index", help="IPCA (default), INPC (IBGE, SIDRA), IGP-M or IGP-DI (FGV, via BCB SGS 189/190)")] = "IPCA",
    out: Annotated[Path | None, typer.Option("--out", help="Write the table as .csv or .parquet")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """IPCA or INPC (IBGE, December 1993 = 100), IGP-M or IGP-DI (FGV, via the Banco Central SGS), to deflate the nominal reais of SIH and SIA; fetches the series once."""
    from ..sidra.prices import price_index

    table = price_index(_settings(root).root, grain=grain, reference=reference, refresh=refresh,
                        years=_parse_years(years) if years else None, index=index)
    if out is not None:
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        (pq.write_table if out.suffix == ".parquet" else pacsv.write_csv)(table, out)
        console.print(f"wrote {out} ({table.num_rows:,} rows)")
        return
    _emit(table.slice(max(0, table.num_rows - 12)).to_pylist(), as_json, f"price index ({table.num_rows} {grain}s; the last 12)")


@app.command(name="cep-points", rich_help_panel="SOURCES")
def cep_points_cmd(
    municipality: Annotated[list[str] | None, typer.Option("--municipality", "-m", help="Municipality code, six digits (DATASUS) or seven (IBGE); repeat for several")] = None,
    uf: Annotated[list[str] | None, typer.Option("--uf", help="State (AL or 27); repeat for several")] = None,
    cep: Annotated[list[str] | None, typer.Option("--cep", help="Eight-digit CEP, exact; repeat for several")] = None,
    tracts: Annotated[bool, typer.Option("--tracts/--no-tracts", help="Keep each CEP's census tracts (parquet output only)")] = False,
    limit: Annotated[int, typer.Option("--limit", help="Rows shown (the whole table goes to --out)")] = 20,
    out: Annotated[Path | None, typer.Option("--out", help="Write the table as .csv or .parquet")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Where each CEP lies, from the Census's CNEFE 2022: one row per CEP and municipality (built by `pegasus-data cnefe`).

    The median position of the CEP's addresses, the distance from it within which half and nine tenths of them lie, their
    count (IBGE's TOT_END), private households, coordinate levels and census tracts. A CEP that is the only one of its
    municipality (`municipality_ceps` 1) places nobody inside it.
    """
    from ..sources.ibge_cnefe import CnefeNotBuilt, cep_points

    if tracts and out is not None and out.suffix != ".parquet":
        raise typer.BadParameter("tracts are a list per CEP: write a .parquet", param_hint="--tracts")
    try:
        table = cep_points(municipality=municipality, uf=uf, cep=cep, tracts=tracts, settings=_settings(root))
    except (CnefeNotBuilt, LookupError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if out is not None:
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        (pq.write_table if out.suffix == ".parquet" else pacsv.write_csv)(table, out)
        console.print(f"wrote {out} ({table.num_rows:,} rows)")
        return
    shown = ["cep", "municipality7", "n_addresses", "lat", "lon", "radius_p50_m", "radius_p90_m", "municipality_ceps"]
    rows = table.select(shown).slice(0, limit).to_pylist()
    for row in rows:
        row.update({k: round(row[k], 1) for k in ("radius_p50_m", "radius_p90_m") if row[k] is not None})
    _emit(rows, as_json, f"{table.num_rows:,} CEP rows (the first {len(rows)})")


@app.command(name="graph", rich_help_panel="UNDERSTAND")
def graph_cmd(
    kind: Annotated[str, typer.Argument(help="contiguity, population_distance, regic_network, regic_health_basic, "
                                             "regic_health_high, a mobility layer built by `mobility` (commute_work_2010, commute_study_2010, "
                                             "road_links_2016, waterway_links_2016, air_passengers), or a dataset for care flows (SIH-RD, CIHA, SIM-DO, SINASC-DN, SINAN-DENG, ...: "
                                             "one whose roles declare a residence and a place of the event)")],
    period: Annotated[str | None, typer.Option("--period", help="Care flows: the years counted; a mobility layer: the vintages "
                       "kept (years, or YYYYMM for air_passengers; a range A-B)")] = None,
    geo: Annotated[str, typer.Option("--geo", help="Care flows: the publications read")] = "BR",
    by: Annotated[str | None, typer.Option("--by", help="Care flows: a classifier, e.g. DIAG_PRINC or COMPLEX")] = None,
    level: Annotated[str | None, typer.Option("--level", help="Care flows: the classifier's tree level, e.g. chapter")] = None,
    to: Annotated[str, typer.Option("--to", help="Care flows: end at the 'municipality' or at the 'establishment' (CNES)")] = "municipality",
    measure: Annotated[list[str] | None, typer.Option("--measure", help="Care flows: a quantity of the event by its role, "
                       "e.g. admission.length_of_stay; each edge carries its count and sum (repeat for several)")] = None,
    derive: Annotated[str | None, typer.Option("--derive", help="Care flows: profile (self-sufficiency), catchments (dominant flow), "
                                                                "communities (Leiden) or regions (communities against health regions)")] = None,
    resolution: Annotated[float, typer.Option("--resolution", help="Communities: Leiden resolution (larger = more communities)")] = 1.0,
    against: Annotated[str, typer.Option("--against", help="Regions: the classification compared with")] = "health_region_current",
    out: Annotated[Path | None, typer.Option("--out", help="Write the edge list (or derived table) as .csv or .parquet")] = None,
    root: RootOpt = None,
) -> None:
    """A proximity graph between municipalities, as an edge list (from, to, weight, kind, vintage)."""
    from ..measures import AggregationRefused
    from ..proximity import care_flows, flows, graph_kinds, proximity_graph

    if kind.lower() not in graph_kinds(root) and dataset_key(kind) in flows():
        if period is None:
            raise typer.BadParameter("care flows need --period")
        try:
            table = care_flows(kind, period=period, geography=geo, by=by, level=level, destination=to,
                               measure=measure or None, settings=_settings(root))
        except (AggregationRefused, ValueError) as refused:
            raise typer.BadParameter(str(refused)) from refused
        if derive:
            from .. import careflow

            if derive == "profile":
                table = careflow.care_flow_profile(table)
            elif derive == "catchments":
                table = careflow.care_flow_catchments(table)
            elif derive in ("communities", "regions"):
                communities = careflow.care_flow_communities(table, resolution=resolution)
                if derive == "regions":
                    result = careflow.compare_flow_regions(table, communities, against=against)
                    _emit({"summary": result["summary"], "regions": result["regions"].num_rows}, False,
                          f"graph {kind} regions vs {against}")
                    table = result["regions"]
                    if out is None:
                        return
                else:
                    table = communities
            else:
                raise typer.BadParameter("--derive is profile, catchments, communities or regions")
    else:
        vintage = None
        if period:
            first, _, last = period.partition("-")
            vintage = list(range(int(first), int(last or first) + 1))
        table = proximity_graph(kind, vintage=vintage, root=root)
    if out is not None:
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        (pq.write_table if out.suffix == ".parquet" else pacsv.write_csv)(table, out)
        console.print(f"wrote {out} ({table.num_rows:,} rows)")
        meta = {k.decode(): v.decode() for k, v in (table.schema.metadata or {}).items()}
        if "events" in meta:
            console.print(f"events {int(meta['events']):,}; unplaced {meta['unplaced']}; unresolved {meta['unresolved']}")
        for role, m in json.loads(meta.get("measures", "{}")).items():
            console.print(f"{role} ({m['unit'] or 'no declared unit'}): {m['n']:,} events with a value, {m['missing']:,} not recorded, "
                          f"{m['outside_domain']:,} outside the domain; sum {m['sum']}; columns {', '.join(m['columns'])}")
        return
    _emit({"rows": table.num_rows, "metadata": {k.decode(): v.decode() for k, v in (table.schema.metadata or {}).items()},
           "first": table.slice(0, 5).to_pylist()}, False, f"graph {kind}")


@app.command(name="climate", rich_help_panel="EXTRACT")
def climate_cmd(
    variable: Annotated[list[str] | None, typer.Option("--variable", help="precipitation, tmax, tmin or tmed (repeat); default all")] = None,
    start: Annotated[str | None, typer.Option("--start", help="First day, YYYY-MM-DD")] = None,
    end: Annotated[str | None, typer.Option("--end", help="Last day, YYYY-MM-DD")] = None,
    municipality: Annotated[list[str] | None, typer.Option("--municipality", help="IBGE code, 6 or 7 digits (repeat)")] = None,
    uf: Annotated[list[str] | None, typer.Option("--uf", help="IBGE state code, 2 digits (repeat)")] = None,
    weight: Annotated[str, typer.Option("--weight", help="population (where people live) or area")] = "population",
    as_of: Annotated[str | None, typer.Option("--as-of", help="The values as published on or before this date or instant (UTC)")] = None,
    weekly: Annotated[bool, typer.Option("--weekly", help="Sums and day counts by epidemiological week")] = False,
    out: Annotated[Path | None, typer.Option("--out", help="Write .csv or .parquet")] = None,
    root: RootOpt = None,
) -> None:
    """Daily municipal weather from CPTEC's MERGE and SAMeT (ADR-0204), by population or by area, by day or epidemiological week."""
    from ..sources import cptec

    names = variable or list(cptec.PRODUCTS)
    reader = cptec.weekly if weekly else cptec.daily
    table = reader(names, start=start, end=end, municipality=municipality, uf=uf, weight=weight, as_of=as_of,
                   settings=_settings(root))
    if out is not None:
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        (pq.write_table if out.suffix == ".parquet" else pacsv.write_csv)(table, out)
        console.print(f"wrote {out} ({table.num_rows:,} rows)")
        return
    _emit({"rows": table.num_rows, "first": table.slice(0, 5).to_pylist()}, False, "climate")


@app.command(name="grade-cells", rich_help_panel="EXTRACT")
def grade_cells_cmd(
    municipality: Annotated[list[str] | None, typer.Option("--municipality", help="IBGE code, 6 or 7 digits (repeat)")] = None,
    uf: Annotated[list[str] | None, typer.Option("--uf", help="IBGE state code, 2 digits (repeat)")] = None,
    resolution: Annotated[int | None, typer.Option("--resolution", help="Sum into the grade's coarser cells: 1000, 5000, 10000, 50000, 100000 or 500000 m")] = None,
    populated: Annotated[bool, typer.Option("--populated", help="Only cells with people")] = False,
    out: Annotated[Path | None, typer.Option("--out", help="Write .csv, .parquet or .gpkg (with the squares)")] = None,
    root: RootOpt = None,
) -> None:
    """IBGE's Grade Estatística 2022: people and households per cell and municipality (ADR-0203)."""
    from ..sources import ibge_grade

    table = ibge_grade.cells(municipality=municipality, uf=uf, resolution=resolution, populated=populated,
                             root=_settings(root).root)
    if out is not None:
        if out.suffix == ".gpkg":
            ibge_grade.geometry(table).to_file(out, driver="GPKG")
        else:
            import pyarrow.csv as pacsv
            import pyarrow.parquet as pq

            (pq.write_table if out.suffix == ".parquet" else pacsv.write_csv)(table, out)
        console.print(f"wrote {out} ({table.num_rows:,} rows)")
        return
    import pyarrow.compute as pc

    _emit({"rows": table.num_rows, "population": round(pc.sum(table.column("population")).as_py() or 0),
           "households": round(pc.sum(table.column("households")).as_py() or 0), "first": table.slice(0, 3).to_pylist()},
          False, "grade-cells")


@app.command(name="info", rich_help_panel="UNDERSTAND")
def info_cmd(
    target: Annotated[str | None, typer.Argument(help="System, dataset or variable: SIH, SIH-RD, SIH.RD")] = None,
    field: Annotated[str | None, typer.Option("--field", help="A column within the target")] = None,
    everything: Annotated[bool, typer.Option("--all", help="With no target: the whole overview, every dataset on a line")] = False,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """What a system, dataset or variable IS — identity, evidence and coverage. With no target, the manual's index (a
    page: what kinds of things this install holds and where to read on, `pegasus-data manual`); ``--all`` the whole
    overview (every dataset, context field, link, aggregate and operation, with the call for each; about 17,000 tokens).

    ``explore`` says what is out there to fetch and ``dictionary`` says what a
    column means. This says what a thing *is*, at any level of the ontology.
    """
    from .._info import info as _info

    if target is None and field is None and not everything and not as_json:
        from .._manual import manual_dir, write_manual
        from ..config import load_settings

        index = manual_dir(load_settings(root=root)) / "INDEX.md"
        if not index.is_file():
            write_manual(root=root)
        typer.echo(index.read_text(encoding="utf-8") + f"\n(the manual: {index.parent}; `pegasus-data info --all` "
                   "prints the whole overview)")
        return
    answer = _info(target, field_name=field, root=root)
    if as_json:
        _emit(answer.as_dict(), True)
        return
    if answer.kind == "overview":
        typer.echo(str(answer))  # plain: the map's overview is read whole, by people and agents, unwrapped
        return
    console.print(str(answer))


@app.command(name="facts", rich_help_panel="UNDERSTAND")
def facts_cmd(
    dataset: Annotated[str, typer.Argument(help="A dataset: SIH-RD, SIM-DO, SINASC-DN, CIHA, SINAN-DENG ...")],
    as_json: JsonOpt = False,
) -> None:
    """What the curation documents of a dataset, with its sources: what a row is, its dates and places, the events it
    becomes and what the source says of them. Offline, from the shipped curation (a methods section quotes it)."""
    from .._info import dataset_facts

    facts = dataset_facts(dataset)
    if as_json:
        _emit(facts, True)
        return
    for key in ("what_one_row_is", "unit_of_analysis", "known_biases", "use", "why_no_event_type"):
        if facts[key]:
            console.print(f"[bold]{key}[/bold]: {facts[key]}")
    for gotcha in facts["gotchas"]:
        console.print(f"  - {gotcha}")
    for axis in ("time", "geography"):
        console.print(f"[bold]{axis}[/bold]: default {facts[axis]['default']}; "
                      + "; ".join(f"{name} = {'+'.join(spec['fields'])}" for name, spec in facts[axis]["axes"].items()))
    for event in facts["events"]:
        console.print(f"[bold]event {event['name']}[/bold] ({event['kind']}): {event['grain'] or ''}")
    for document in facts["documents"]:
        console.print(f"  source: {document}")
    if not facts["documented"]:
        console.print(f"[yellow]the curation declares nothing of {dataset!r}[/yellow]")


@app.command(name="publications", rich_help_panel="EXPLORE")
def publications_cmd(
    dataset: Annotated[str, typer.Argument(help="A dataset: SIH-RD, SIM-DO, SINASC-DN ...")],
    years: Annotated[str | None, typer.Option("--years", help="A year, or a span: 2014..2023")] = None,
    uf: Annotated[str | None, typer.Option("--uf", help="States (comma separated); the national file is always kept")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Write the table as .csv or .parquet")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Which published files the lake holds a dataset's records from, one row each: the server's size and date, the
    digest decoded, when and from where it was fetched, the rows, preliminary or final; and the files the catalog lists
    that the lake does not hold, with the reason."""
    from .._explore import publications

    span: object = None
    if years:
        low, _, high = years.partition("..")
        span = range(int(low), int(high or low) + 1)
    table = publications(dataset, span, ufs=uf.split(",") if uf else None, root=root)  # type: ignore[arg-type]
    if out is not None:
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq

        (pq.write_table if out.suffix == ".parquet" else pacsv.write_csv)(table, out)
        console.print(f"wrote {out} ({table.num_rows:,} files)")
        return
    held = sum(1 for held in table.column("in_lake").to_pylist() if held)
    _emit({"files": table.num_rows, "in_lake": held, "not_in_lake": table.num_rows - held,
           "rows_decoded": sum(r or 0 for r in table.column("rows_decoded").to_pylist()),
           "first": table.slice(0, 3).to_pylist()}, as_json, f"publications {dataset}")


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
        store = CatalogStore.shared(settings.catalog_path)
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
    codes: Annotated[
        str | None, typer.Option("--codes", help="Codes of a cohort link: ICD-10 prefixes (I21,I22), or SIGTAP procedure prefixes with --match procedure (0403070171)")
    ] = None,
    match: Annotated[
        str, typer.Option("--match", help="principal | any | procedure: the codes on the principal diagnosis, on every diagnosis, or on the procedure performed")
    ] = "principal",
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Link records about the same person across two datasets (ADR-0107, ADR-0110).

    'pegasus-data link sih_deaths_to_sim --period 2022 --geo RR'. Prints every
    pass with its negative control (the same join with a birth date shifted by
    a week: its pairs are coincidences), the held-out validations and the
    verdict. A linkage that is not viable exits 1 unless --allow-not-viable.

    A cohort link is run per codes: 'pegasus-data link sih_admissions_to_sim
    --period 2018..2022 --geo AL --codes I21,I22' (the admissions of a
    diagnosis to the death certificate of any cause; its report holds the
    false-match rate at each follow-up horizon).
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
                          codes=[c.strip() for c in codes.split(",")] if codes else None, match=match,
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
    left: Annotated[str, typer.Argument(help="A dataset with linkage roles (compare: in curation/roles/<dataset>.yml), e.g. SINASC-DN")],
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
    as_of: Annotated[
        str | None,
        typer.Option("--as-of", help="Read each file as `pegasus-data snapshot` kept it on this date (2026-09-30); no network"),
    ] = None,
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
                return_report=True, as_of=as_of,
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
    store = CatalogStore.shared(settings.catalog_path)
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
            help="Materialise a <field>_label column per small closed codelist. Off by default: a "
            "stored label is today's meaning on every historical row, and the query path joins "
            "labels at read time by validity window. Changing it makes every partition stale.",
        ),
    ] = False,
    rebuild: Annotated[
        bool,
        typer.Option(
            "--rebuild",
            help="Write every selected partition again. By default a partition whose "
            "source files and normalisation plan are unchanged, and whose Parquet is "
            "still on disk, is left alone.",
        ),
    ] = False,
    keep_downloads: Annotated[
        bool | None,
        typer.Option(
            "--keep-downloads/--release-downloads",
            help="Keep each downloaded file beside the partitions built from it. By default (Settings.keep_downloads) "
            "a file whose records a verified partition holds is deleted after the build; a rebuild fetches it again.",
        ),
    ] = None,
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
                release=None if keep_downloads is None else not keep_downloads,
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
