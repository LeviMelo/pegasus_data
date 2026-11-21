"""What a file suffix means, declared once.

The tree's suffix knowledge used to live in six hand lists (the file role of
`inventory.naming`, the member roles of `decode.archives`, the reader hints of
`decode.registry`, the header-readable suffixes of `inventory.schemas`, the
untyped-listing hints of `discovery.listing`, the container ranks of
`inventory.families`). Each answered a different question about the same
suffixes and could drift from the others (audit #16, 2026-11-21). They are
fields of one record here; the sites derive their sets from it.

A suffix is a hint that orders work, never a filter (D1): an unlisted suffix
gets the full reader ladder, and a file whose suffix says "documentation" is
still probed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Suffix:
    #: What the file is for, by suffix alone (`inventory.naming.role_from_path`): "dictionary", "documentation",
    #: "auxiliary" (software and pointers) or None (no verdict from the suffix: the path decides).
    role: str | None = None
    #: The role of an archive member (`decode.archives`): data, lookup, def, cnv, doc, binary; none = "unknown".
    member_role: str | None = None
    #: Reader names to try first, in order; ("skip",) = never probe. None = the full ladder.
    readers: tuple[str, ...] | None = None
    #: Typed as a file, not a directory, from an NLST name alone (no per-entry CWD probe).
    listed: bool = False
    #: How the header is read by a ranged fetch: "dbf" (prefix), "csv" (first line), "archive" (small zips whole).
    header: str | None = None


def _s(**kw: object) -> Suffix:
    return Suffix(**kw)  # type: ignore[arg-type]


SUFFIXES: dict[str, Suffix] = {
    ".dbc": _s(member_role="data", readers=("dbc", "dbf", "archive"), listed=True, header="dbf"),
    ".dbf": _s(member_role="lookup", readers=("dbf", "dbc", "archive"), listed=True, header="dbf"),
    ".csv": _s(member_role="data", readers=("csv", "json", "xml", "archive"), listed=True, header="csv"),
    ".txt": _s(role="documentation", member_role="data", readers=("csv", "json", "xml"), listed=True),
    ".json": _s(member_role="data", readers=("json", "csv"), listed=True),
    ".xml": _s(member_role="data", readers=("xml", "csv"), listed=True),
    ".parquet": _s(member_role="data", readers=("parquet",), listed=True),
    ".xls": _s(member_role="data", readers=("xlsx", "csv"), listed=True),
    ".xlsx": _s(member_role="data", readers=("xlsx", "csv"), listed=True),
    ".duck": _s(member_role="data", readers=("duckdb", "archive"), listed=True),
    ".zip": _s(readers=("archive",), listed=True, header="archive"),
    ".gz": _s(readers=("archive",), listed=True),
    ".rar": _s(readers=("archive",), listed=True),
    ".7z": _s(readers=("archive",), listed=True),
    ".tar": _s(readers=("archive",), listed=True),
    ".bz2": _s(listed=True),
    ".exe": _s(member_role="binary", readers=("archive",), listed=True),
    ".def": _s(role="dictionary", member_role="def", readers=("semantic",), listed=True),
    ".cnv": _s(role="dictionary", member_role="cnv", readers=("semantic",), listed=True),
    ".pdf": _s(role="documentation", member_role="doc", readers=("document",), listed=True),
    ".hlp": _s(role="documentation", member_role="doc", readers=("document",), listed=True),
    ".cnt": _s(role="documentation", member_role="doc", readers=("document",), listed=True),
    ".doc": _s(role="documentation", member_role="doc", listed=True),
    ".docx": _s(role="documentation", member_role="doc", listed=True),
    ".htm": _s(role="documentation", member_role="doc", listed=True),
    ".html": _s(role="documentation", member_role="doc", listed=True),
    ".rtf": _s(role="documentation", member_role="doc"),
    ".dll": _s(role="auxiliary", member_role="binary", readers=("skip",), listed=True),
    ".ini": _s(role="auxiliary", member_role="binary"),
    ".bat": _s(role="auxiliary", member_role="binary"),
    ".url": _s(role="auxiliary"),
    ".msi": _s(role="auxiliary"),
}

#: Suffixes of two parts that name a compressed payload: the archive reader goes first.
COMPOSITE_SUFFIXES: tuple[str, ...] = (".duck.zip", ".csv.gz", ".json.gz", ".xml.gz", ".dbf.gz", ".dbc.gz", ".tar.gz")


def suffixes_where(**field: object) -> tuple[str, ...]:
    """The suffixes whose record has every given field value (`suffixes_where(role="documentation")`)."""
    return tuple(s for s, rec in SUFFIXES.items() if all(getattr(rec, k) == v for k, v in field.items()))


def header_kind(suffix: str) -> str | None:
    rec = SUFFIXES.get(suffix)
    return rec.header if rec else None


#: Container formats (what a probe or the suffix says a file is): decode cost, cheapest first (a Parquet footer is a
#: map and its row groups are independently decodable; a `.dbc` is inflated from byte zero, §7.2), and the reader that
#: opens it (None: no single reader, the probe ladder decides).
CONTAINERS: dict[str, tuple[int, str | None]] = {
    "parquet": (0, "parquet"),
    "duckdb": (1, "duckdb"),
    "csv": (2, "csv"),
    "json": (3, "json"),
    "xml": (4, "xml"),
    "dbf": (5, "dbf"),
    "xlsx": (6, "xlsx"),
    "dbc": (7, "dbc"),
    "zip": (8, "archive"),
    "gzip": (9, "archive"),
    "lha_sfx": (10, "archive"),
    "rar": (11, "archive"),
    "7z": (12, "archive"),
    "unknown": (99, None),
}
