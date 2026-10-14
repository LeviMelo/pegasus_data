"""Shared pieces of the command line: the app, its options and helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ..config import Settings, load_settings
from ..pipeline import Pipeline

app = typer.Typer(
    name="pegasus-data",
    help="A queryable, self-describing data lake over Brazil's DATASUS public health data.",
    no_args_is_help=True,
    add_completion=False,
)


console = Console()
err = Console(stderr=True)


RootOpt = Annotated[
    Path | None,
    typer.Option(
        "--root",
        help="Data home for this command. Persist it with `pegasus-data config set --root`; "
        "see `pegasus-data where` for what is in effect and why.",
    ),
]


SystemsOpt = Annotated[list[str] | None, typer.Option("--system", "-s", help="Limit to these information systems")]


JsonOpt = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON instead of a table")]


def _settings(root: Path | None, **overrides: object) -> Settings:
    return load_settings(root=root, **overrides)


def _writer(root: Path | None, **overrides: object) -> Settings:
    """The settings of a command that WRITES: it says where, on stderr (so ``--json`` stays clean), and warns when the
    root named on the command line displaced a place that an environment variable or a config file had set (ADR-0175, ADR-0188)."""
    settings = _settings(root, **overrides)
    where = settings.places()
    err.print(f"[dim]writes under {where['root']} (lake {where['lake']}, catalog {where['catalog']}, blobs {where['blobs']}, work {where['work']})[/dim]", soft_wrap=True)
    for key, how in settings.origins.items():
        if "not used" in how:
            err.print(f"[yellow]{key} follows the root given here; {how.split('not used: ', 1)[1].rstrip(')')}[/yellow]", soft_wrap=True)
    return settings


def _pipeline(root: Path | None, **overrides: object) -> Pipeline:
    return Pipeline(_writer(root, **overrides))


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
