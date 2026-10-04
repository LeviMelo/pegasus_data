"""The ``pegasus-data`` command line. `RUNBOOK.md` is its manual.

For a person reading data:

    pegasus-data query SIH.RD --period 2023-01 --geo AL --out sih.csv
    pegasus-data info SIH.RD          pegasus-data explore SIH.RD
    pegasus-data search raça          pegasus-data translate FILE --system SIHSUS

For a maintainer building the shipped snapshot (RUNBOOK §5):

    crawl → inventory → schemas → families → curate → bindings → build_resources

Every command is resumable and idempotent, and writes to the catalog before
returning.
"""

from __future__ import annotations

import sys

from . import audit, pipeline, read, setup  # noqa: F401 - each registers its commands
from ._common import (
    app,
    console,
)


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
