"""Parsers for FTP directory listings.

Measured on ``ftp.datasus.gov.br`` (2026-08): the server is **Microsoft FTP
Service on Windows_NT**. ``FEAT`` advertises ``SIZE``, ``MDTM``, ``AUTH TLS``,
``REST STREAM`` — and *not* ``MLST``/``MLSD``. ``MLSD`` returns
``500 Command not understood``.

``LIST`` returns the IIS MS-DOS dialect::

    05-29-15  04:10PM                18550 acac0201.exe
    02-24-18  07:38AM       <DIR>          199201_200712

which carries **both size and mtime**. The prior scanner only had a Unix-style
``LIST`` regex; every line failed to match, the reader raised, and the crawl fell
all the way back to ``NLST`` — which is why ``size`` and ``modified`` were NULL
for all 124,810 rows (defect D4). The fix is this module: parse both dialects,
and treat an unparsed-but-non-empty listing as a hard error rather than as an
empty directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath

from ..formats import suffixes_where

__all__ = [
    "ListingEntry",
    "same_instant",
    "parse_list_lines",
    "parse_msdos_line",
    "parse_unix_line",
    "normalize_path",
    "join_path",
]

# IIS / MS-DOS dialect: "MM-DD-YY  hh:mmAM  <DIR>|size  name"
_MSDOS_RE = re.compile(
    r"^\s*(?P<month>\d{2})-(?P<day>\d{2})-(?P<year>\d{2,4})\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})(?P<ampm>[AaPp][Mm])?\s+"
    r"(?:(?P<dir><DIR>)|(?P<size>\d+))\s+"
    r"(?P<name>.+?)\s*$"
)

# Unix / ls -l dialect, kept because DATASUS mirrors and test doubles use it.
_UNIX_RE = re.compile(
    r"^(?P<mode>[bcdlps-][rwxsStT-]{9})[\.\+]?\s+\d+\s+\S+\s+\S+\s+"
    r"(?P<size>\d+)\s+(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+"
    r"(?P<timeyear>[\d:]{4,5})\s+(?P<name>.+?)\s*$"
)

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

#: Suffixes that let NLST output be typed without a per-entry CWD probe. This is
#: a *hint for ordering work*, never a filter — see design rule D1.
_FILE_SUFFIX_HINTS = suffixes_where(listed=True)


@dataclass(slots=True)
class ListingEntry:
    """One child of a directory, as the server reported it."""

    name: str
    path: str
    is_dir: bool | None          # None = the listing method could not say
    size: int | None = None
    modified: str | None = None  # ISO-8601
    method: str = ""
    flags: list[str] = field(default_factory=list)

    @property
    def change_signal(self) -> str:
        if self.modified:
            return "mtime"
        if self.size is not None:
            return "size"
        return "content_hash"


#: MSYS/Git-Bash rewrites a leading-slash argument into a Windows path before the
#: process ever sees it, so ``--prefix /dissemin/publicos/IBGE`` arrives as
#: ``/C:/Program Files/Git/dissemin/publicos/IBGE`` and every listing 550s. An FTP
#: path can never contain a drive letter, so stripping one back is unambiguous.
_MSYS_MANGLED = re.compile(r"^/?[A-Za-z]:/.*?(?=/dissemin/)", re.I)


def normalize_path(path: str) -> str:
    """Collapse separators, guarantee a leading slash, undo MSYS path mangling."""
    cleaned = (path or "/").replace("\\", "/")
    cleaned = _MSYS_MANGLED.sub("", cleaned)
    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if len(cleaned) > 1 and cleaned.endswith("/"):
        cleaned = cleaned[:-1]
    return cleaned


def join_path(directory: str, child: str) -> str:
    if child.startswith("/"):
        return normalize_path(child)
    return normalize_path(str(PurePosixPath(normalize_path(directory)) / child))


#: The server answers in two clocks. LIST shows its wall clock and MDTM shows UTC, and the wall clock is UTC-3 for
#: every date, the summer-time months before 2019 included. Measured on 2026-10-24 by comparing MDTM against LIST on
#: 1,290 files in the catalogs and on 6 files live, a 2018-02 file among them. A LIST time is stored as filed:
#: truncated to the minute and labelled +00:00. So one file reads 16:30 by LIST and 19:30:45 by MDTM, and a catalog
#: holds both, because MDTM answers whenever LIST cannot (ADR-0122) and whenever the listing is stale.
LIST_CLOCK_BEHIND_S = 3 * 3600


def same_instant(a: str, b: str) -> bool:
    """Do two recorded modification times name one instant? Either they are equal, or one is the other read through
    the server's other clock: :data:`LIST_CLOCK_BEHIND_S` apart, to within LIST's truncation to the minute."""
    if a == b:
        return True
    try:
        apart = abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds())
    except ValueError:
        return False
    return apart == 0 or abs(apart - LIST_CLOCK_BEHIND_S) < 60


def _iso(year: int, month: int, day: int, hour: int, minute: int) -> str | None:
    try:
        return datetime(year, month, day, hour, minute, tzinfo=UTC).isoformat()
    except ValueError:
        return None


def _this_year() -> int:
    return datetime.now(UTC).year


def parse_msdos_line(line: str, directory: str) -> ListingEntry | None:
    """Parse one IIS MS-DOS listing row. Returns None if the dialect does not match."""
    m = _MSDOS_RE.match(line)
    if not m:
        return None
    name = m.group("name")
    if name in {".", ".."} or not name:
        return None
    raw_year = int(m.group("year"))
    # IIS emits two-digit years. This is a file's modification time, which is never in the future: the century is the
    # latest that does not put it after the current year (no fixed pivot; a data year's two digits are naming's).
    year = raw_year if raw_year > 99 else (2000 + raw_year if 2000 + raw_year <= _this_year() else 1900 + raw_year)
    hour = int(m.group("hour"))
    ampm = (m.group("ampm") or "").upper()
    if ampm == "PM" and hour != 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    modified = _iso(year, int(m.group("month")), int(m.group("day")), hour, int(m.group("minute")))
    is_dir = m.group("dir") is not None
    size = None if is_dir else int(m.group("size"))
    return ListingEntry(
        name=name,
        path=join_path(directory, name),
        is_dir=is_dir,
        size=size,
        modified=modified,
        method="LIST:msdos",
    )


def parse_unix_line(line: str, directory: str) -> ListingEntry | None:
    """Parse one ``ls -l`` listing row. Returns None if the dialect does not match."""
    m = _UNIX_RE.match(line)
    if not m:
        return None
    name = m.group("name")
    if name in {".", ".."} or not name:
        return None
    mode = m.group("mode")
    is_dir = mode.startswith("d")
    flags: list[str] = []
    if mode.startswith("l"):
        # Symlink: "name -> target". Keep the link name, flag it, do not follow.
        name = name.split(" -> ", 1)[0]
        flags.append("symlink")
        is_dir = None
    timeyear = m.group("timeyear")
    now = datetime.now(UTC)
    month = _MONTHS.get(m.group("month"), 0)
    day = int(m.group("day"))
    modified = None
    if month:
        if ":" in timeyear:
            hh, mm = timeyear.split(":")
            year = now.year if (month, day) <= (now.month, now.day) else now.year - 1
            modified = _iso(year, month, day, int(hh), int(mm))
        else:
            modified = _iso(int(timeyear), month, day, 0, 0)
    return ListingEntry(
        name=name,
        path=join_path(directory, name),
        is_dir=is_dir,
        size=int(m.group("size")),
        modified=modified,
        method="LIST:unix",
        flags=flags,
    )


def parse_list_lines(lines: list[str], directory: str) -> list[ListingEntry]:
    """Parse a full ``LIST`` response, auto-detecting the dialect.

    Raises ``ValueError`` when the server sent content we could not understand.
    A directory that genuinely has no children returns an empty list from an
    empty response — those two cases must never be conflated, because conflating
    them is how a whole subtree silently disappears.
    """
    meaningful = [ln for ln in lines if ln.strip() and not ln.lower().startswith("total ")]
    if not meaningful:
        return []
    entries: list[ListingEntry] = []
    unparsed: list[str] = []
    for line in meaningful:
        entry = parse_msdos_line(line, directory) or parse_unix_line(line, directory)
        if entry is None:
            unparsed.append(line)
        else:
            entries.append(entry)
    if not entries:
        raise ValueError(
            f"LIST returned {len(meaningful)} rows in an unrecognised dialect; "
            f"first row: {meaningful[0]!r}"
        )
    if unparsed:
        # Partial understanding is still a coverage problem: surface it.
        for e in entries:
            e.flags.append(f"unparsed_list_rows:{len(unparsed)}")
    return entries


def parse_nlst(children: list[str], directory: str) -> list[ListingEntry]:
    """Type NLST output from suffix hints only; unknowns stay ``is_dir=None``."""
    entries: list[ListingEntry] = []
    for child in children:
        name = PurePosixPath(child).name if "/" in child else child
        if not name or name in {".", ".."}:
            continue
        lower = name.lower()
        hinted = any(lower.endswith(s) for s in _FILE_SUFFIX_HINTS)
        entries.append(
            ListingEntry(
                name=name,
                path=join_path(directory, child),
                is_dir=False if hinted else None,
                method="NLST",
                flags=["nlst_type_from_suffix_hint"] if hinted else ["nlst_untyped"],
            )
        )
    return entries
