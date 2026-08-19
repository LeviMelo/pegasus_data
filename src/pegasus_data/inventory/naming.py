"""Filename grammar for the DATASUS tree (§5.2).

The classic convention is ``PREFIX + GEO + DATE``: ``RDAL2401.dbc`` is the SIH
reduced file for Alagoas, competência 2024-01.

Two hazards get explicit handling.

**Date ambiguity.** ``DOAL2001`` is SIM for the *year* 2001; ``RDAL2001`` is SIH
for the *competência* 2020-01. This is undecidable from one filename and
decidable from the directory it sits in, so the convention is inferred once per
directory and then applied to that directory's members —
:func:`infer_date_convention`. Where a directory genuinely cannot be decided, the
year is left NULL and an open question is recorded. Guessing here would silently
shift a whole series by nineteen years.

**The "descriptive" ``Dados_Abertos`` subtree.** The brief flagged 82 families as
``DADOS_ABERTOS_UNPARSED_*`` and inferred that the subtree needs its own naming
module. Measured: it mostly does *not*. The filenames are classic
(``DENGBR20.csv.zip`` = prefix ``DENG``, geo ``BR``, year 20); what defeated the
prior parser was the **composite suffix** ``.csv.zip`` / ``.json.zip`` /
``.xml.zip``, which its ``strip_composite_suffix`` only handled for ``.gz``. So
these are not a new grammar — they are the same SINAN series republished in three
containers, i.e. more D3, and they collapse into single families once parsed.
A genuinely descriptive tail does exist (``apac_atd.duck.zip``,
``siasus_pa_ac.duck``) and gets its own grammar below.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath

from ..config import UF_CODES

__all__ = [
    "ParsedName",
    "parse_filename",
    "strip_container_suffixes",
    "infer_date_convention",
    "infer_two_digit_epoch",
    "apply_convention",
    "system_from_path",
    "role_from_path",
]

#: Suffix stacks DATASUS actually uses. Order matters: longest first.
_COMPOSITE_SUFFIXES = (
    ".duck.zip", ".csv.zip", ".json.zip", ".xml.zip", ".dbf.zip", ".dbc.zip",
    ".parquet.zip", ".csv.gz", ".json.gz", ".xml.gz", ".dbf.gz", ".dbc.gz",
    ".tar.gz",
)

_CLASSIC = re.compile(r"^(?P<prefix>[A-Z]{1,8}?)(?P<geo>[A-Z]{2})(?P<date>\d{2,6})$")
_CLASSIC_SEP = re.compile(r"^(?P<prefix>[A-Z]{1,10})[_\-](?P<geo>[A-Z]{2})[_\-]?(?P<date>\d{2,6})$")
_NO_GEO = re.compile(r"^(?P<prefix>[A-Z][A-Z_]{1,11}?)(?P<date>\d{2,6})$")
_DESCRIPTIVE_UF = re.compile(r"^(?P<prefix>[a-z0-9_]+?)_(?P<geo>[a-z]{2})$")

_CURRENT_YEAR = datetime.now(UTC).year


@dataclass(slots=True)
class ParsedName:
    """What a filename claims about itself, before directory context is applied."""

    filename: str
    stem: str
    extension: str | None
    container_format: str | None
    series_prefix: str | None = None
    geo_code: str | None = None
    date_code: str | None = None
    grammar: str = "unparsed"

    # Filled in by apply_convention once the directory's convention is known.
    date_format: str | None = None
    normalized_date: int | None = None
    year: int | None = None

    @property
    def ambiguous_date(self) -> bool:
        """True when a 4-digit code could be either ``YYMM`` or ``YYYY``."""
        return bool(self.date_code) and len(self.date_code or "") == 4


def strip_container_suffixes(filename: str) -> tuple[str, str | None, str | None]:
    """Split ``DENGBR20.csv.zip`` into ``('DENGBR20', '.csv.zip', 'zip')``.

    Returns ``(stem, full_suffix, outermost_container)``. The outermost container
    is what a reader must open first; the inner suffix is a hint about what it
    will find, and neither is allowed to exclude the file (D1).
    """
    lower = filename.lower()
    for composite in _COMPOSITE_SUFFIXES:
        if lower.endswith(composite):
            return filename[: -len(composite)], composite, composite.rsplit(".", 1)[-1]
    suffix = PurePosixPath(lower).suffix
    if suffix:
        return filename[: -len(suffix)], suffix, suffix.lstrip(".")
    return filename, None, None


def parse_filename(filename: str) -> ParsedName:
    """Apply the grammars in order of specificity; never force a bad match."""
    stem, extension, container = strip_container_suffixes(filename)
    parsed = ParsedName(filename=filename, stem=stem, extension=extension, container_format=container)
    upper = stem.upper()

    for grammar, pattern in (("classic", _CLASSIC), ("classic_sep", _CLASSIC_SEP)):
        m = pattern.match(upper)
        if m and m.group("geo") in UF_CODES:
            parsed.series_prefix = m.group("prefix") or None
            parsed.geo_code = m.group("geo")
            parsed.date_code = m.group("date")
            parsed.grammar = grammar
            return parsed

    m = _NO_GEO.match(upper)
    if m:
        # Guard against swallowing a UF that happens to precede the digits, e.g.
        # a two-letter tail that is a real geo token.
        prefix = m.group("prefix")
        if len(prefix) >= 2 and prefix[-2:] in UF_CODES:
            parsed.series_prefix = prefix[:-2] or None
            parsed.geo_code = prefix[-2:]
        else:
            parsed.series_prefix = prefix or None
        parsed.date_code = m.group("date")
        parsed.grammar = "classic_no_geo" if parsed.geo_code is None else "classic"
        return parsed

    m = _DESCRIPTIVE_UF.match(stem.lower())
    if m and m.group("geo").upper() in UF_CODES:
        parsed.series_prefix = m.group("prefix").upper()
        parsed.geo_code = m.group("geo").upper()
        parsed.grammar = "descriptive_uf"
        return parsed

    if re.fullmatch(r"[A-Za-z0-9_\-]+", stem):
        parsed.series_prefix = stem.upper()
        parsed.grammar = "descriptive"
        return parsed

    return parsed


# ------------------------------------------------------------ date conventions


def infer_date_convention(date_codes: list[str], *, group_keys: list[tuple[str, str]] | None = None) -> str:
    """Decide whether a directory's 4-digit codes mean ``YYMM`` or ``YYYY``.

    ``group_keys`` pairs each code with its ``(prefix, geo)`` so the rule the
    brief states can actually be applied: a monthly convention yields many
    distinct tails sharing a leading pair; an annual convention yields one.

    Returns ``'monthly'``, ``'annual'``, ``'explicit'`` (6-digit ``YYYYMM``), or
    ``'ambiguous'``. Ambiguous is a real answer, and callers must not paper over
    it with a default.
    """
    four = [c for c in date_codes if len(c) == 4]
    six = [c for c in date_codes if len(c) == 6]
    two = [c for c in date_codes if len(c) == 2]
    if six and not four:
        return "explicit"
    if two and not four and not six:
        return "annual"
    if not four:
        return "ambiguous" if date_codes else "none"

    tails = [int(c[2:]) for c in four]
    leads = [c[:2] for c in four]

    # 1. A tail outside 01..12 cannot be a month — but one outlier must not
    #    redefine the directory. `SIHSUS/200801_/Dados` holds 22,807 monthly
    #    files and a single annual bundle, `RDAC2017.zip`, whose tail is 17.
    #    Reading "any outlier ⇒ annual" flipped all 22,807 to annual and dated
    #    `CHBR1901.dbc` to the year 1901 instead of 2019-01. The convention is
    #    the dominant pattern; the outliers are the anomaly, and they are left
    #    undated rather than forced into the majority reading.
    month_like = sum(1 for t in tails if 1 <= t <= 12) / len(tails)
    if month_like < 0.98:
        return "annual"

    # 2. A leading pair that is not a plausible century marker cannot be a year
    #    prefix, so the directory is monthly (e.g. '2401' -> 2024-01).
    if any(lead not in {"19", "20"} for lead in leads):
        return "monthly"

    # 3. All codes look like both. Multiplicity decides: annual series carry one
    #    file per (series, geo, year); monthly carry up to twelve.
    if group_keys is not None and len(group_keys) == len(four):
        per_group: dict[tuple[str, str, str], set[int]] = defaultdict(set)
        for (prefix, geo), code in zip(group_keys, four, strict=True):
            per_group[(prefix, geo, code[:2])].add(int(code[2:]))
        if any(len(v) > 1 for v in per_group.values()):
            return "monthly"
        return "annual"

    distinct_tails_per_lead: dict[str, set[int]] = defaultdict(set)
    for lead, tail in zip(leads, tails, strict=True):
        distinct_tails_per_lead[lead].add(tail)
    if any(len(v) > 1 for v in distinct_tails_per_lead.values()):
        return "monthly"
    return "ambiguous"


def _year_from_two_digits(value: int, epoch: str = "pivot") -> int:
    """Expand a two-digit year under the directory's inferred epoch."""
    if epoch == "century_2000":
        return 2000 + value
    if epoch == "century_1900":
        return 1900 + value
    # Default pivot: DATASUS series start in 1979, so ≤ 40 is this century.
    return 2000 + value if value <= 40 else 1900 + value


def infer_two_digit_epoch(codes: list[str]) -> str:
    """Choose how a directory's two-digit years expand.

    ``IBGE/projpop`` holds ``PROJUF00 … PROJUF70``: population *projections*
    running to 2070, where the default pivot would read ``70`` as 1970 and
    scatter a contiguous series across a century. The discriminator is
    contiguity — the correct reading is the one whose expanded years form the
    tightest span, since a real series is contiguous and a mis-read one is not.
    """
    values = sorted({int(c) for c in codes if len(c) == 2 and c.isdigit()})
    if not values:
        return "pivot"
    candidates = {
        "pivot": [_year_from_two_digits(v, "pivot") for v in values],
        "century_2000": [2000 + v for v in values],
        "century_1900": [1900 + v for v in values],
    }
    best = "pivot"
    best_span = None
    for name, years in candidates.items():
        span = max(years) - min(years)
        # A reading that puts data implausibly far out is not a candidate at all.
        if max(years) > _CURRENT_YEAR + 60 or min(years) < 1900:
            continue
        if best_span is None or span < best_span:
            best, best_span = name, span
    return best


def apply_convention(parsed: ParsedName, convention: str, *, epoch: str = "pivot") -> ParsedName:
    """Resolve a parsed name's date under the directory's inferred convention."""
    code = parsed.date_code
    if not code:
        return parsed
    if len(code) == 6:
        parsed.date_format = "YYYYMM"
        parsed.normalized_date = int(code)
        parsed.year = int(code[:4])
        return parsed
    if len(code) == 2:
        parsed.date_format = "YY"
        parsed.year = _year_from_two_digits(int(code), epoch)
        parsed.normalized_date = parsed.year * 100
        return parsed
    if len(code) == 4:
        if convention == "monthly":
            month = int(code[2:])
            if 1 <= month <= 12:
                year = _year_from_two_digits(
                    int(code[:2]), epoch if epoch != "century_2000" else "pivot"
                )
                parsed.date_format = "YYMM"
                parsed.year = year
                parsed.normalized_date = year * 100 + month
                return parsed
            # A file in a monthly directory whose tail is not a month is the
            # outlier the convention was inferred *around* — usually an annual
            # bundle. Forcing it into the majority reading would invent a date,
            # so it stays undated and visible.
            parsed.date_format = "ambiguous"
            parsed.year = None
            parsed.normalized_date = None
            return parsed
        if convention == "annual":
            year = int(code)
            if 1900 <= year <= _CURRENT_YEAR + 3:
                parsed.date_format = "YYYY"
                parsed.year = year
                parsed.normalized_date = year * 100
                return parsed
            # A 4-digit code in an 'annual' directory that is not a plausible
            # year is a contradiction; leave it undecided rather than invent one.
        parsed.date_format = "ambiguous"
        parsed.year = None
        parsed.normalized_date = None
    return parsed


# ------------------------------------------------------------- path semantics


def logical_identity(
    parsed: ParsedName, *, system: str | None, path: str | None = None
) -> str:
    """A file's identity, derived from its **name** rather than its location.

    ``SIHSUS|RD|AL|2401`` names the SIH reduced AIH file for Alagoas, competência
    2024-01, wherever on the tree it happens to live. Strata and families are
    keyed on identity, so a directory rename moves a file without re-deriving
    thirty-five years of lineage under fresh identifiers.

    A name that does not parse still gets a stable identity from the filename
    itself — location-independent, which is the property that matters — rather
    than falling back to the path and reintroducing the very coupling this
    exists to remove.

    **This is a many-to-one grouping key, not a unique one.** The container suffix
    is deliberately excluded, so ``RDAC2401.dbc``, ``RDAC2401.dbf`` and a
    ``.csv`` republication of the same competência all return
    ``SIHSUS|RD|AC|2401``. That is the point — they are three representations of
    one publication, and grouping them is what lets the reader pick a container
    without changing what data they asked for. It also means anything treating a
    logical_id as a primary key is wrong: ``path`` is the unique key, and a join
    on logical_id returns a set. See ``test_logical_id_is_many_to_one``.
    """
    if parsed.series_prefix:
        return "|".join(
            [
                (system or "UNKNOWN").upper(),
                parsed.series_prefix.upper(),
                (parsed.geo_code or "").upper(),
                parsed.date_code or "",
            ]
        )
    return f"{(system or 'UNKNOWN').upper()}|~{parsed.filename.upper()}"


def system_from_path(path: str, base_path: str = "/dissemin/publicos") -> str | None:
    """The information system is the first path element under the base path."""
    parts = [p for p in PurePosixPath(path).parts if p not in {"/", ""}]
    base_parts = [p for p in PurePosixPath(base_path).parts if p not in {"/", ""}]
    if len(parts) > len(base_parts) and parts[: len(base_parts)] == base_parts:
        return parts[len(base_parts)].upper()
    if "publicos" in parts:
        idx = parts.index("publicos")
        if idx + 1 < len(parts):
            return parts[idx + 1].upper()
    return parts[0].upper() if parts else None


#: Directory names that hold the semantic layer. These are a **primary ingestion
#: target** with their own parser stack, not a byproduct to be filtered out (D7).
DICTIONARY_DIR_TOKENS = {
    "auxiliar", "auxiliares", "doc", "docs", "documentacao", "documentação",
    "tab", "tabelas", "dicionario", "dicionarios", "layout", "layouts",
    "versoesantigas",
}
_DICTIONARY_SUFFIXES = {".def", ".cnv"}
_DOC_SUFFIXES = {".pdf", ".doc", ".docx", ".htm", ".html", ".hlp", ".cnt", ".txt", ".rtf"}


def role_from_path(path: str) -> str:
    """Classify what a file is *for*, never what to skip.

    The role steers which parser stack sees the file first. Nothing is excluded
    by role: a ``.pdf`` in a Doc directory still gets probed, because a
    misclassified data file that is never opened is exactly defect D1.
    """
    p = PurePosixPath(path)
    suffix = p.suffix.lower()
    parts_lower = {part.lower() for part in p.parts}
    if suffix in _DICTIONARY_SUFFIXES:
        return "dictionary"
    if suffix in _DOC_SUFFIXES:
        return "documentation"
    name_lower = p.name.lower()
    if name_lower.startswith("tab") and suffix in {".zip", ".rar"}:
        return "dictionary"
    if parts_lower & DICTIONARY_DIR_TOKENS:
        return "auxiliary"
    return "data"
