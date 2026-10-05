"""``pegasus-data sidra``: search IBGE's SIDRA catalog, inspect a table, plan and fetch a selection."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ._common import JsonOpt, RootOpt, _emit, _settings, app, console

sidra_app = typer.Typer(help="IBGE SIDRA: search the catalog, inspect a table, fetch a planned selection.", no_args_is_help=True)
app.add_typer(sidra_app, name="sidra", rich_help_panel="SOURCES")


def _session(root: Path | None):
    from ..sidra import Sidra

    return Sidra(_settings(root).root)


def _parse_classifications(items: list[str] | None) -> dict[int, object]:
    """``86=all`` · ``2=4,5`` · ``287=total``: classification id = all | total | category ids."""
    out: dict[int, object] = {}
    for item in items or []:
        cid, _, rest = item.partition("=")
        out[int(cid)] = rest if rest in ("all", "total") else [int(x) for x in rest.split(",")]
    return out


def _selection(s, table: int, variables: str | None, periods: str, level: str, scope: str, classification: list[str] | None):
    scope_value: object = "all" if scope == "all" else scope.split(",")
    return s.selection(
        table, variables=[int(v) for v in variables.split(",")] if variables else None,
        periods=periods if periods in ("all", "latest") else periods.split(","),
        level=level, scope=scope_value, states=scope != "all" and level == "N6" and all(len(x) == 2 for x in scope.split(",")),
        classifications=_parse_classifications(classification))


@sidra_app.command("scan")
def scan(
    everything: Annotated[bool, typer.Option("--all", help="Read every table's metadata (default: the curated and municipal ones)")] = False,
    limit: Annotated[int | None, typer.Option("--limit", help="Stop after this many tables (for a trial)")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Build the registry from IBGE's metadata (resumable; a table takes 1-2 s, the municipal ones are 4,448)."""
    from ..sidra.registry import load_compendium_file

    settings = _settings(root)
    s = _session(root)
    s.registry.scan_catalog(s.client)
    load_compendium_file(s.registry, settings.curation_dir)        # the curated tables are read first
    order = s.registry.scan_order(s.client, everything=everything)
    result = s.registry.scan_metadata(s.client, order[:limit] if limit else order, log=console.print)
    result["compendium_tables"] = load_compendium_file(s.registry, settings.curation_dir)     # now with their variables
    result.update(s.registry.scan_summary())
    _emit(result, as_json, "SIDRA registry")


@sidra_app.command("search")
def search(
    terms: Annotated[str, typer.Argument(help="Words in a table's name, research, subject, variables or classifications")],
    level: Annotated[str | None, typer.Option("--level", help="Territorial level, e.g. N6 (municipality), N3 (state)")] = None,
    research: Annotated[str | None, typer.Option("--research", help="Part of the research's name, e.g. 'Saúde'")] = None,
    curated: Annotated[bool, typer.Option("--curated", help="Only the author's compendium tables")] = False,
    limit: Annotated[int, typer.Option("--limit")] = 30,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Find tables in the registry."""
    found = _session(root).registry.search(terms, level=level, research=research, compendium_only=curated, limit=limit)
    rows = found if as_json else [{"table": r["id"], "name": r["name"][:72], "research": (r["research"] or "")[:24],
                                   "periods": f"{r['first_period']}-{r['last_period']}", "N6": "yes" if r["has_n6"] else "",
                                   "tier": r["tier"] or ""} for r in found]
    _emit(rows, as_json, f"{len(rows)} tables")


@sidra_app.command("show")
def show(
    table: Annotated[int, typer.Argument(help="SIDRA table (agregado) number")],
    classification: Annotated[int | None, typer.Option("--classification", "-c", help="List this classification's categories")] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """What a table holds: variables, units, classifications, periods, territorial levels."""
    s = _session(root)
    if classification is not None:
        _emit(s.registry.categories(table, classification), as_json, f"table {table}, classification {classification}")
        return
    info = s.describe(table)
    info["periods"] = s.periods(table)
    _emit({k: v for k, v in info.items() if k not in ("variables", "classifications")}, as_json, f"table {table}")
    _emit(info["variables"], as_json, "variables")
    _emit(info["classifications"], as_json, "classifications")


@sidra_app.command("survey")
def survey_(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Tables per research: how many, how many scanned, reaching N6 and N3, curated, and the periods spanned."""
    from ..sidra.survey import survey

    _emit(survey(_session(root).registry), as_json, "SIDRA by research")


@sidra_app.command("families")
def families(research: Annotated[str, typer.Option("--research")] = "Censo Demográfico", root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Tables that ask the same question in different periods (same classifications and variables): series across vintages."""
    from ..sidra.survey import vintage_families

    _emit(vintage_families(_session(root).registry, research), as_json, f"vintage families of {research}")


@sidra_app.command("rank")
def rank_(
    level: Annotated[str, typer.Option("--level")] = "N6",
    topic: Annotated[list[str] | None, typer.Option("--topic", help="curation/sidra/topics.yml; default all")] = None,
    curated: Annotated[bool, typer.Option("--curated", help="Include the compendium's tables")] = False,
    limit: Annotated[int, typer.Option("--limit")] = 40, root: RootOpt = None, as_json: JsonOpt = False,
) -> None:
    """A reading list: scanned tables at a level, scored on topic, time span and how many localities they cover
    (the count is fetched from IBGE for the best candidates)."""
    from ..sidra.survey import rank

    s = _session(root)
    _emit(rank(s.registry, level=level, topics=topic, outside_compendium=not curated, limit=limit, client=s.client), as_json, "reading list")


_Table = Annotated[int, typer.Argument(help="SIDRA table number")]
_Vars = Annotated[str | None, typer.Option("--variables", "-v", help="Variable ids, comma-separated (default: the compendium's kept ones, else all)")]
_Per = Annotated[str, typer.Option("--periods", "-p", help="'all', 'latest' or ids, comma-separated")]
_Lvl = Annotated[str, typer.Option("--level", help="N6 municipality, N3 state, N2 region, N1 Brazil")]
_Scope = Annotated[str, typer.Option("--scope", help="'all', 2-digit state codes (N6), or locality ids, comma-separated")]
_Cls = Annotated[list[str] | None, typer.Option("--class", "-c", help="classification=all|total|ids, e.g. 86=all  2=4,5  (omitted = Total)")]


@sidra_app.command("plan")
def plan(table: _Table, variables: _Vars = None, periods: _Per = "latest", level: _Lvl = "N6", scope: _Scope = "all",
         classification: _Cls = None, root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """The requests a selection needs under SIDRA's limits; nothing is fetched."""
    s = _session(root)
    chunks = s.plan(_selection(s, table, variables, periods, level, scope, classification))
    rows = [{"values": c.values, "localities": c.localities[:60], "periods": "|".join(c.periods), "variables": "|".join(map(str, c.variables)),
             "classificacao": c.classification[:80], "url_chars": len(c.url)} for c in chunks]
    _emit({"requests": len(chunks), "values": sum(c.values for c in chunks), "largest": max(c.values for c in chunks)}, as_json, "plan")
    if not as_json and len(rows) <= 40:
        _emit(rows, False, "requests")


@sidra_app.command("fetch")
def fetch(table: _Table, variables: _Vars = None, periods: _Per = "latest", level: _Lvl = "N6", scope: _Scope = "all",
          classification: _Cls = None, root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Fetch a selection into the lake (resumable; every response is cached with its provenance)."""
    s = _session(root)
    _emit(s.fetch(_selection(s, table, variables, periods, level, scope, classification), log=console.print), as_json, "fetch")


@sidra_app.command("facts")
def facts(table: _Table, periods: Annotated[str | None, typer.Option("--periods", "-p")] = None,
          out: Annotated[Path | None, typer.Option("--out", help=".csv or .parquet; default: print a sample")] = None,
          head: Annotated[int, typer.Option("--head")] = 12, root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """The stored facts of a table with labels, units and Total flags joined on."""
    s = _session(root)
    table_ = s.labelled(table, periods=periods.split(",") if periods else None)
    if out is None:
        _emit(table_.slice(0, head).to_pylist(), as_json, f"{table_.num_rows} facts")
    elif out.suffix == ".parquet":
        import pyarrow.parquet as pq

        pq.write_table(table_, out)
    else:
        import pyarrow.csv as pcsv

        pcsv.write_csv(table_, out)
    if out is not None:
        _emit({"rows": table_.num_rows, "out": str(out)}, as_json, "written")


@sidra_app.command("rebuild")
def rebuild(table: _Table, root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Re-derive a table's stored facts from the cached responses (no request is made)."""
    _emit({"table": table, "parts_rewritten": _session(root).rebuild(table)}, as_json, "rebuild")


@sidra_app.command("check")
def check(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Where the curated compendium and IBGE's metadata disagree."""
    from ..sidra.registry import compendium_disagreements
    from ..sidra.series import check_axes

    s = _session(root)
    _emit(compendium_disagreements(s.registry), as_json, "compendium vs IBGE metadata")
    _emit(check_axes(s) or {"axes": "every curated category matches IBGE's name"}, as_json, "axes (curation/sidra/axes.yml) vs IBGE names")


@sidra_app.command("series")
def series(name: Annotated[str | None, typer.Argument(help="A stitched series (curation/sidra/series.yml); omit to list")] = None,
           fetch_: Annotated[bool, typer.Option("--fetch", help="Fetch the series' sources first (resumable)")] = False,
           validate: Annotated[bool, typer.Option("--validate", help="Check its cells against the tables' own totals")] = False,
           report: Annotated[bool, typer.Option("--report", help="Its comparability and gaps, and the places with a figure per census")] = False,
           out: Annotated[Path | None, typer.Option("--out")] = None, root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """A stitched series from the stored facts; where sources overlap both claims are kept, one `selected`."""
    from ..sidra.series import build_series, declared_series, fetch_series, series_report, validate_series

    if name is None:
        _emit([{"series": k, "what": " ".join(v.get("what", "").split())[:110]} for k, v in declared_series().items()], as_json, "series")
        return
    s = _session(root)
    if fetch_:
        _emit(fetch_series(s, name, log=console.print), as_json, "fetched")
    if validate:
        _emit(validate_series(s, name), as_json, "cells against the tables' own totals")
        return
    if report:
        _emit(series_report(s, name), as_json, f"series {name}")
        return
    table_ = build_series(s, name)
    if out is None:
        _emit(table_.slice(0, 12).to_pylist(), as_json, f"{table_.num_rows} rows")
    else:
        import pyarrow.parquet as pq

        pq.write_table(table_, out)
        _emit({"rows": table_.num_rows, "out": str(out)}, as_json, "written")


@sidra_app.command("curated")
def curated(
    group: Annotated[str | None, typer.Option("--group", help="demography, education, housing_sanitation, income_labour, ...")] = None,
    tier: Annotated[str | None, typer.Option("--tier", help="T1_CORE, T2_CONTEXT, T3_OPTIONAL, T4_LOW_PRIORITY")] = None,
    table: Annotated[list[int] | None, typer.Option("--table", "-t")] = None,
    fetch_: Annotated[bool, typer.Option("--fetch", help="Fetch them (resumable); without it, only the cost is shown")] = False,
    max_values: Annotated[int, typer.Option("--max-values", help="Skip a table that would need more values than this")] = 30_000_000,
    root: RootOpt = None, as_json: JsonOpt = False,
) -> None:
    """The author's compendium tables: what each would cost under SIDRA's limits, and, with --fetch, fetch them."""
    s = _session(root)
    rows = []
    for t in s.curated(group=group, tier=tier, tables=table):
        row: dict[str, object] = {"table": t, "name": (s.registry.tab(t) or {}).get("name", "")[:50]}
        try:
            selection = s.curated_selection(t)
            row.update(s.estimate(selection))
            if fetch_ and row["values"] <= max_values:    # type: ignore[operator]
                report = s.fetch(selection, log=lambda _m: None)
                row.update(fetched=report["fetched"], rows=report["rows"], shortfalls=len(report["shortfalls"]))
            elif fetch_:
                row["skipped"] = f"over {max_values} values"
        except Exception as exc:  # noqa: BLE001 - reported per table, the others go on
            row["error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
        rows.append(row)
    _emit(rows, as_json, "curated tables")


@sidra_app.command("rollup")
def rollup(name: Annotated[str, typer.Argument(help="A stitched series of counts")],
           start: Annotated[int, typer.Option("--start", help="1980, 1991 or 2000: comparable areas for start-2010")] = 2000,
           nonexistent: Annotated[bool, typer.Option("--nonexistent", help="Take `...` cells as municipalities not yet created (a vintage before the creations)")] = False,
           out: Annotated[Path | None, typer.Option("--out")] = None, root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """A series of counts summed over IPEA's minimum comparable areas, so municipal creations do not break it."""
    from ..sidra.lineage import roll_up

    s = _session(root)
    table_ = roll_up(s, s.series(name), start, nonexistent=nonexistent)
    if out is None:
        _emit(table_.slice(0, 12).to_pylist(), as_json, f"{table_.num_rows} areas × periods")
    else:
        import pyarrow.parquet as pq

        pq.write_table(table_, out)
        _emit({"rows": table_.num_rows, "out": str(out)}, as_json, "written")
