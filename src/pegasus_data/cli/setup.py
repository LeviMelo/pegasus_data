"""Setup: where the data home is, configuration, shipped resources, monitoring."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ._common import (
    JsonOpt,
    RootOpt,
    _emit,
    _parse_years,
    _pipeline,
    _settings,
    _writer,
    app,
    console,
)

config_app = typer.Typer(
    name="config",
    help="Where the data goes. Show it, write it down, or clear it.",
    no_args_is_help=True,
)


app.add_typer(config_app, rich_help_panel="SETUP")


resources_app = typer.Typer(
    name="resources",
    help="Inspect bundled semantic resources and optional local registries.",
    no_args_is_help=True,
)


app.add_typer(resources_app, rich_help_panel="SETUP")


@resources_app.command("status")
def resources_status(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Show code-independent resource versions, checksums, sizes and availability."""
    from .._resources import ResourceManager

    _emit(ResourceManager(_settings(root)).status().as_dict(), as_json, "runtime resources")


@resources_app.command("ensure")
def resources_ensure(
    name: Annotated[str, typer.Argument(help="Resource name, e.g. CNES")],
    period: Annotated[str | None, typer.Option("--period")] = None,
    policy: Annotated[str, typer.Option("--policy", help="local | auto | remote")] = "local",
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Require a resource locally; never start an unbounded download implicitly."""
    from .._resources import ResourceManager

    try:
        record = ResourceManager(_writer(root)).ensure(name, period=period, policy=policy)
    except FileNotFoundError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=2) from exc
    _emit({"resource": record.name, "path": record.path, "bytes": record.bytes}, as_json)


@resources_app.command("build")
def resources_build(
    name: Annotated[str, typer.Argument(help="Optional registry name, currently CNES")],
    years: Annotated[
        str | None,
        typer.Option(
            "--years",
            help="Verified complete source years (required for cnes_names), e.g. 2022-2024",
        ),
    ] = None,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Explicitly build a local registry.

    CNES history is a bounded acquisition/materialization operation. cnes_names
    is currently a maintainer compilation from local documentary evidence and
    requires explicit verified-complete source years.
    """
    from .._resources import ResourceManager

    result = ResourceManager(_writer(root)).build(name, years=_parse_years(years))
    _emit(result, as_json, f"built {name}")


registries_app = typer.Typer(
    name="registries",
    help="The name registries (establishments, teams) that labels are read from.",
    no_args_is_help=True,
)


app.add_typer(registries_app, rich_help_panel="SETUP")


@registries_app.command("build")
def registries_build(
    system: Annotated[
        str, typer.Argument(help="The registry's owner: CNES (establishment, team and CNPJ names) or SIASUS (INE_EQUIPE)")
    ] = "CNES",
    refresh: Annotated[bool, typer.Option("--refresh", help="Read the kit again even if its registry is built")] = False,
    root: RootOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """Download a system's TabWin kit once and build its name registries (ADR-0176).

    The one place a registry is downloaded: reads (`load`, `query`, labels) never fetch, and say this command when a
    registry is missing. The kit is 6 MB (SIH) to 127 MB (CNES).
    """
    from .. import registry

    counts = registry.build(system.upper(), refresh=refresh, settings=_writer(root))
    if not counts:
        console.print(f"[yellow]{system.upper()}: no TabWin kit in the catalog, or none with a registry table[/yellow]")
        raise typer.Exit(code=2)
    _emit(counts, as_json, f"{system.upper()} registry tables (rows)")


def _placement_rows(root: Path | None = None) -> list[dict[str, object]]:
    from ..locate import PLACEMENT_KEYS

    settings = _settings(root)
    places = settings.places()
    rows: list[dict[str, object]] = []
    for key, (env_name, what) in PLACEMENT_KEYS.items():
        path = places.get(key)
        rows.append(
            {
                "key": key,
                "path": str(path) if path else "",
                "decided by": settings.origins.get(key, "derived"),
                "env": env_name,
                "holds": what,
                "exists": bool(path and Path(path).exists()),
            }
        )
    return rows


@app.command(name="where", rich_help_panel="SETUP")
def where(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """Where this installation reads and writes, and which layer decided each path.

    The question behind every "my data disappeared": five layers can set a path
    — an explicit --root, an environment variable, a project config file, the
    per-user one, the built-in default — and working out which is winning by
    elimination is miserable.
    """
    rows = _placement_rows(root)
    if as_json:
        _emit(rows, True, "where")
        return
    table = Table(title="where the data goes", box=None)
    for column in ("key", "path", "decided by", "exists"):
        table.add_column(column)
    for row in rows:
        mark = "[green]yes[/green]" if row["exists"] else "[dim]not yet[/dim]"
        table.add_row(str(row["key"]), str(row["path"]), str(row["decided by"]), mark)
    console.print(table)

    from ..locate import config_search_path

    files = Table(title="config files, in precedence order", box=None)
    for column in ("scope", "path", "read"):
        files.add_column(column)
    for scope, path, exists in config_search_path():
        files.add_row(scope, str(path), "[green]yes[/green]" if exists else "[dim]absent[/dim]")
    console.print(files)


@app.command(name="adopt", rich_help_panel="SETUP")
def adopt_home(
    other: Annotated[Path, typer.Argument(help="Another data home (a folder holding _catalog/)")],
    root: RootOpt = None,
    apply: Annotated[bool, typer.Option("--apply", help="Move the files; without it, only the plan is shown")] = False,
    remove: Annotated[bool, typer.Option("--remove", help="With --apply: delete the other home once adopted")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Move another data home's downloads and registries into this one, so one machine keeps one home.

    Blobs this home lacks move with their fetch history (each digest checked first). Registry files absent here also
    move. The other home's lake and semantic tables are listed but not taken: this home recomputes them from the
    downloads with the current code. ``--remove`` then deletes the other home, so no copy outlives its adoption.
    Crawl the adopted prefixes afterwards, so the listing is as new as the fetches.
    """
    from ..adopt import adopt

    plan = adopt((_writer if apply else _settings)(root), other, apply=apply, remove=remove)
    _emit(plan.summary(), as_json, "adopt")
    if not apply and not as_json:
        console.print("[dim]Nothing was moved. Run again with --apply to move it.[/dim]")


@config_app.command("show")
def config_show(root: RootOpt = None, as_json: JsonOpt = False) -> None:
    """What every placement key resolves to, and what each one holds."""
    rows = _placement_rows(root)
    if as_json:
        _emit(rows, True, "config")
        return
    table = Table(box=None)
    for column in ("key", "path", "decided by", "holds"):
        table.add_column(column)
    for row in rows:
        table.add_row(str(row["key"]), str(row["path"]), str(row["decided by"]), str(row["holds"]))
    console.print(table)


@config_app.command("set")
def config_set(
    root: Annotated[Path | None, typer.Option("--root", help="Everything, unless overridden below")] = None,
    blobs: Annotated[Path | None, typer.Option("--blobs", help="Download cache (large, rebuildable)")] = None,
    lake: Annotated[Path | None, typer.Option("--lake", help="The Parquet lake you query")] = None,
    work: Annotated[Path | None, typer.Option("--work", help="Scratch space for decoding")] = None,
    catalog: Annotated[Path | None, typer.Option("--catalog", help="The SQLite catalog (small, wants to be fast)")] = None,
    curation: Annotated[Path | None, typer.Option("--curation", help="Curated YAML; defaults to the packaged copy")] = None,
    user: Annotated[bool, typer.Option("--user", help="Write the per-user file instead of a project one")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Write placement into a config file, so you say it once.

    Project scope by default — a `pegasus-data.toml` beside you, which is what
    you want when a dataset belongs to a project. `--user` writes the per-user
    file instead, for "all my DATASUS data lives on D:".

    Nothing is moved. Setting a path tells future commands where to look; if you
    are relocating existing data, move it yourself first — this package will not
    quietly relocate gigabytes on your behalf.
    """
    from ..locate import CONFIG_FILENAMES, read_config_file, user_config_path, write_config_file

    wanted = {
        "root": root, "blobs": blobs, "lake": lake,
        "work": work, "catalog": catalog, "curation": curation,
    }
    chosen = {k: str(Path(v).expanduser().resolve()) for k, v in wanted.items() if v is not None}
    if not chosen:
        raise typer.BadParameter("give at least one of --root/--blobs/--lake/--work/--catalog/--curation")

    target = user_config_path() if user else Path.cwd() / CONFIG_FILENAMES[0]
    merged = {**read_config_file(target), **chosen}
    write_config_file(target, merged)
    _emit({"wrote": str(target), **chosen}, as_json, "config set")
    if not as_json:
        console.print(
            "[dim]Nothing was moved. Run `pegasus-data where` to confirm what is now in effect.[/dim]"
        )


@config_app.command("unset")
def config_unset(
    keys: Annotated[list[str], typer.Argument(help="Keys to remove, e.g. blobs lake")],
    user: Annotated[bool, typer.Option("--user", help="Edit the per-user file")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Remove keys from a config file, falling back to the layer beneath."""
    from ..locate import (
        CONFIG_FILENAMES,
        PLACEMENT_KEYS,
        find_project_config,
        read_config_file,
        user_config_path,
        write_config_file,
    )

    unknown = [k for k in keys if k not in PLACEMENT_KEYS]
    if unknown:
        raise typer.BadParameter(f"unknown key(s): {', '.join(unknown)}")
    target = user_config_path() if user else (find_project_config() or Path.cwd() / CONFIG_FILENAMES[0])
    if not target.is_file():
        raise typer.BadParameter(f"no config file at {target}")
    values = read_config_file(target)
    removed = [k for k in keys if k in values]
    for key in removed:
        values.pop(key)
    write_config_file(target, values)
    _emit({"file": str(target), "removed": removed or "nothing"}, as_json, "config unset")


@config_app.command("path")
def config_path(as_json: JsonOpt = False) -> None:
    """Which config files are consulted, in precedence order."""
    from ..locate import config_search_path

    rows = [
        {"scope": scope, "path": str(path), "exists": exists}
        for scope, path, exists in config_search_path()
    ]
    _emit(rows, as_json, "config path")


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
