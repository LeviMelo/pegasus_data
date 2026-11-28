"""A spreadsheet read as the text its cells show: the one reader of a sheet (ADR-0243).

A workbook from a public body is a table wrapped in a report: a title, a date, sometimes a total, then the header,
the rows, then notes. What a caller needs is the same every time: the sheet that holds the table, its header found by
what its first cell says (never by a row number, which moves between editions), the rows under it as text, and the
cells above it (where a sheet prints its own total).

Every cell is the text the sheet shows: a whole number filed as a float (xlrd reads 4717 as 4717.0) loses its ``.0``,
an empty cell is None. Typing is the caller's, by its declaration: a code such as ``00015`` must not become 15.

Before this module the package read spreadsheets in six places, each with its own idea of where the header is
(ARCHITECTURE §5). `intake` and `sources.ibge_dtb` read through here; the four older source modules are to follow.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, NamedTuple

__all__ = ["SheetTable", "cell_text", "read_table", "sheets"]


class SheetTable(NamedTuple):
    """A table found in a workbook: the sheet it is on, its column names, its rows, and every cell of the sheet (for a
    total printed above the header)."""

    sheet: Any
    names: list[str]
    rows: list[list[str | None]]
    cells: list[list[str | None]]
    header_row: int


def cell_text(value: Any) -> str | None:
    """A cell as the text it shows: a whole number filed as a float without its ``.0``, an empty cell as None."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def sheets(source: str | Path | Any, sheet: Any = None) -> dict[Any, list[list[str | None]]]:
    """Every sheet of a workbook (or the one named, by name or index) as rows of text cells. ``source`` is a path or an
    open binary file; ``.xls``, ``.xlsx`` and ``.ods`` are read by the engine pandas picks for each."""
    import io

    import pandas as pd

    # an old .xls (OLE2) goes to xlrd, which prints its remarks on a damaged file to standard output unless given
    # somewhere else to write them: a command's JSON must stay JSON
    if isinstance(source, (str, Path)):
        with open(source, "rb") as handle:
            magic = handle.read(8)
    else:
        magic = source.read(8)
        source.seek(0)
    quiet = {"engine_kwargs": {"logfile": io.StringIO()}} if magic == bytes.fromhex("d0cf11e0a1b11ae1") else {}
    grids = pd.read_excel(source, sheet_name=sheet, header=None, dtype=object, **quiet)
    grids = grids if isinstance(grids, dict) else {sheet: grids}
    return {name: [[cell_text(v) for v in row] for row in grid.itertuples(index=False, name=None)]
            for name, grid in grids.items()}


def read_table(source: str | Path | Any, *, header: str = ".", sheet: Any = None, names: list[str] | None = None,
               stop: str | None = None, label: str = "") -> SheetTable:
    """The one table of a workbook.

    ``header`` is a regex the header row's first cell matches; the table is on the one sheet that has such a row (a
    workbook that opens on a glossary is no obstacle), or on ``sheet`` when it is named. ``names`` are the columns in
    order, where the header's own words are long or change between editions: their number must equal the header's
    cells. ``stop`` is a regex on a row's first cell that ends the table (the notes under it). Repeated header rows and
    empty rows are dropped. None or several sheets with a header, or a count of names that disagrees with the header:
    an error saying what was found, never a guess."""
    pattern = re.compile(header, re.I)
    label = label or (Path(source).name if isinstance(source, (str, Path)) else "the workbook")

    def header_of(cells: list[list[str | None]]) -> int | None:
        return next((i for i, row in enumerate(cells) if row and row[0] and pattern.search(row[0])), None)

    grids = sheets(source, sheet)
    found = {name: cells for name, cells in grids.items() if header_of(cells) is not None}
    if len(found) != 1:
        raise ValueError(f"{label}: expected one sheet with a row whose first cell matches {header!r}, "
                         f"found {sorted(map(str, found))} of {sorted(map(str, grids))}")
    name, cells = next(iter(found.items()))
    head = header_of(cells)
    assert head is not None
    top = cells[head]
    width = max(i for i, c in enumerate(top) if c is not None) + 1
    columns = [str(n).upper() for n in names or []] or [str(c).upper() for c in top[:width]]
    if len(columns) != width:
        raise ValueError(f"{label}: {len(columns)} names declared, the header has {width} cells: {top[:width]}")
    end = re.compile(stop, re.I) if stop else None
    rows: list[list[str | None]] = []
    for row in cells[head + 1:]:
        row = (row + [None] * width)[:width]
        if row[0] and end and end.search(row[0]):
            break
        if all(c is None for c in row) or row == top[:width]:
            continue
        rows.append(row)
    return SheetTable(name, columns, rows, cells, head)
