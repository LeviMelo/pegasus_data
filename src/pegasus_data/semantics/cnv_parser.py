"""TabNet ``.CNV`` parser — the officially pactuated code→category maps (D7).

Grammar, learned empirically from the 79 uncompressed files under
``PNI/AUXILIARES/`` and the 177 members of ``TAB_SIH_199201-199712.zip``::

    <n_categories> <code_width>
    <seq:right-aligned><spaces><label:padded><spaces><match-expression>

For example ``SEXO.CNV``::

    3 1
          3  Ignorado                                           0-9
          1  Masculino                                          1
          2  Feminino                                           2,3

and ``CID10CAP.CNV``::

    23 3
        001  I.   Algumas doenças infecciosas e parasitárias    A00-B99

The match expression is a single code, a comma-separated list, a range, or any
mixture; **ranges and lists are both expanded** into individual dictionary rows.

Two properties that a naive reading gets wrong:

* **Last match wins.** ``SEXO.CNV`` lists ``Ignorado → 0-9`` *first*, covering
  the whole domain, then overrides it with ``Masculino → 1`` and
  ``Feminino → 2,3``. Reading first-match-wins would label every record
  "Ignorado". The catch-all-then-specialise idiom recurs throughout
  (``IDADE18.CNV`` opens with ``Ign → 000-999``), so resolution order is load
  bearing and is recorded per entry.
* **Alphanumeric ranges need a universe.** ``A00-B99`` cannot be enumerated
  without knowing which codes exist. Where a universe is supplied (the
  14,197-row ``CID10.DBF`` from the same kit) the range is expanded against it;
  where it is not, the range is preserved as a *rule* with its expression intact
  rather than being dropped or guessed at.
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..textenc import best_effort_decode

__all__ = ["CnvCategory", "CnvFile", "parse_cnv", "parse_cnv_bytes", "expand_expression"]

_TOKEN = re.compile(r"\S+")
#: The bare header: a category count and a code width, nothing else.
_HEADER = re.compile(r"^\s*(\d+)\s+(\d+)\s*$")
#: The header WITH a title, which is the commoner form and was being missed.
#: ``NHE.cnv`` opens with the count, a sentence describing the table, and then
#: the width; because the bare pattern did not match, line 1 was parsed as a
#: category and its title became a dictionary "code" —
#: ``'26/08/210 pelo GT-SINAN/MS nova definição 190 NHE. ; Patch 4.2'``.
#: Guarded on both numbers being plausible so a data row cannot impersonate it:
#: a code width above 30 is not a width, and the title must not be empty (that
#: is the bare form, already handled above).
_HEADER_TITLED = re.compile(r"^\s*(\d+)\s+(\S.*?)\s+(\d+)\s*$")
#: The header with a trailing TabNet flag: ``326 7 L``. Three of the four files
#: that were emitting prose codes opened with this form, and because neither the
#: bare nor the titled pattern matched, the header line itself was parsed as a
#: category and the file lost its declared count AND its code width — so nothing
#: downstream could zero-pad or validate.
_HEADER_FLAGGED = re.compile(r"^\s*(\d+)\s+(\d+)\s+([A-Za-z])\s*$")
#: TabNet's comment marker. ``Mun_A_F_P.cnv`` opens with two of these before its
#: real header, so header detection has to look past them rather than at line 1,
#: and they must not survive into the body as categories.
_COMMENT = re.compile(r"^\s*;")
#: Widths beyond this are not code widths; the longest real one on the tree is
#: the 10-character SIGTAP procedure code.
_MAX_CODE_WIDTH = 30


@dataclass(slots=True)
class CnvCategory:
    """One category line: its sequence, its label, and what it matches."""

    order: int          # position in the file; higher wins on overlap
    sequence: str       # the category number TabNet uses
    label: str
    expression: str
    line_no: int
    codes: list[str] = field(default_factory=list)
    unexpanded: list[str] = field(default_factory=list)

    @property
    def fully_expanded(self) -> bool:
        return not self.unexpanded


@dataclass(slots=True)
class CnvFile:
    """A parsed ``.CNV``, with enough provenance to cite any single mapping."""

    name: str
    source_ref: str
    declared_categories: int | None
    code_width: int | None
    categories: list[CnvCategory] = field(default_factory=list)
    encoding: str = "cp850"
    warnings: list[str] = field(default_factory=list)

    @property
    def category_count(self) -> int:
        return len(self.categories)

    def mapping(self) -> dict[str, tuple[str, CnvCategory]]:
        """Resolve overlaps with last-match-wins and return ``code → (label, category)``."""
        out: dict[str, tuple[str, CnvCategory]] = {}
        for category in self.categories:  # already in file order
            for code in category.codes:
                out[code] = (category.label, category)
        return out

    def rules(self) -> list[tuple[str, CnvCategory]]:
        """Expressions that could not be enumerated, kept verbatim."""
        return [(expr, c) for c in self.categories for expr in c.unexpanded]


def _expression_column(lines: list[str]) -> int | None:
    """Find the column where the match expression starts.

    Measured across the SIH kit's 177 CNV members, the column is 60 in the large
    majority of files but 64–66 in others, so it is inferred per file rather than
    hard-coded. Lines whose label overflows that column fall back to token
    splitting and are flagged.
    """
    starts: Counter[int] = Counter()
    for line in lines:
        tokens = list(_TOKEN.finditer(line))
        if len(tokens) >= 2:
            starts[tokens[-1].start()] += 1
    if not starts:
        return None
    column, hits = starts.most_common(1)[0]
    # Only trust a column that most lines agree on; otherwise parse by tokens.
    return column if hits >= max(2, 0.6 * sum(starts.values())) else None


def _plausible_header(count: str, width: str) -> bool:
    """Do these two numbers look like a category count and a code width?

    A width is written ``6``; a code is zero-padded to that width, ``000001``,
    so a leading zero is the strongest signal that this is data rather than a
    header. A one-category file barely exists, and a data row's first token is
    a sequence number starting at 1.
    """
    if len(width) > 1 and width.startswith("0"):
        return False
    if not (0 < int(width) <= _MAX_CODE_WIDTH):
        return False
    return int(count) >= 2


def _first_expression(text: str) -> tuple[str, str] | None:
    """The leading token of ``text`` if it is a match expression, plus the rest.

    Used when the text past the expression column is not a clean expression.
    ``medico02.CNV`` line 11 reads ``... MÉDICO DE FAMÍLIA   XXXXXX      vascular``
    — the code is ``XXXXXX``, exactly as on its neighbours, and ``vascular`` is
    a fragment that does not belong to the line at all. Taking the LAST token,
    as this used to, chose ``vascular``: a word, stored as a code, bound to a
    column, and matched against real records.
    """
    tokens = list(_TOKEN.finditer(text))
    if not tokens:
        return None
    head = tokens[0].group()
    if not _is_expression(head):
        return None
    return head, text[tokens[0].end():].strip()


def _is_titled_header(match: re.Match[str]) -> bool:
    """Is this first line a ``<count> <title> <width>`` header, or a data row?

    They are genuinely ambiguous — ``  1 Hospital A   000001`` fits the same
    shape — so three properties separate them, and all three must hold:

    * **The width has no leading zero.** A width is written ``6``; a code is
      zero-padded to that width, ``000001``. This is the strongest of the three.
    * **The count is at least two.** A one-category ``.CNV`` barely exists, and a
      data row's first token is the sequence number, which starts at 1.
    * **The title contains a space.** Headers describe the table in a phrase;
      a data row's label may be a single word.

    Refusing a genuine one-category titled header costs one spurious category.
    Accepting a data row costs a whole row of real decoding, so the asymmetry
    justifies erring this way.
    """
    count, title, width = match.group(1), match.group(2), match.group(3)
    if not _plausible_header(count, width):
        return False
    return " " in title.strip()


def parse_cnv_bytes(
    data: bytes,
    *,
    name: str,
    source_ref: str,
    universe: frozenset[str] | None = None,
    max_expansion: int = 50_000,
) -> CnvFile:
    text, encoding = best_effort_decode(data)
    raw_lines = text.splitlines()
    if not raw_lines:
        return CnvFile(name, source_ref, None, None, encoding=encoding, warnings=["empty file"])

    declared: int | None = None
    width: int | None = None

    # The header is the first line that is neither blank nor a comment. Looking
    # only at line 1 meant a file that opens with a comment lost its header
    # entirely, and with it the code width every downstream expansion needs.
    first = 0
    while first < len(raw_lines) and (
        not raw_lines[first].strip() or _COMMENT.match(raw_lines[first])
    ):
        first += 1
    body_start = first

    if first < len(raw_lines):
        line0 = raw_lines[first]
        header = _HEADER.match(line0)
        flagged = _HEADER_FLAGGED.match(line0)
        titled = _HEADER_TITLED.match(line0)
        if header:
            declared = int(header.group(1))
            width = int(header.group(2))
            body_start = first + 1
        elif flagged and _plausible_header(flagged.group(1), flagged.group(2)):
            declared = int(flagged.group(1))
            width = int(flagged.group(2))
            body_start = first + 1
        elif titled and _is_titled_header(titled):
            declared = int(titled.group(1))
            width = int(titled.group(3))
            body_start = first + 1

    # Keep the true line number with each line: comments are dropped from the
    # body, so position in the list no longer tracks position in the file, and
    # every warning here cites a line a human is expected to go and read.
    body = [
        (n, ln)
        for n, ln in enumerate(raw_lines[body_start:], start=body_start + 1)
        if ln.strip() and not _COMMENT.match(ln)
    ]

    expr_col = _expression_column([ln for _, ln in body])
    out = CnvFile(name, source_ref, declared, width, encoding=encoding)

    for offset, (line_no, line) in enumerate(body):
        tokens = list(_TOKEN.finditer(line))
        if not tokens:
            continue
        sequence = tokens[0].group()
        if len(tokens) == 1:
            out.warnings.append(f"line {line_no}: no match expression")
            continue
        if expr_col is not None and len(line) > expr_col and line[expr_col - 1 : expr_col] in (" ", ""):
            # Collapse the column padding: a .CNV is a fixed-width layout, so the
            # run of spaces inside 'JI-PARANÁ               A' is alignment, not
            # part of the name.
            label = " ".join(line[tokens[0].end() : expr_col].split())
            expression = line[expr_col:].strip()
            if not expression:
                label = " ".join(t.group() for t in tokens[1:-1]).strip()
                expression = tokens[-1].group()
            elif not _is_expression(expression):
                # The expression column is inferred from the file as a whole, so
                # a line whose label runs long pushes real text past it and the
                # split captures prose as the code. `medico02.CNV` line 11 became
                # code `'XXXXXX                       vascular'` labelled
                # `'MÉDICO DE FAMÍLIA'`, and that codelist decodes CNES.CBOUNICO
                # — so the wrong thing was being matched against real records.
                #
                # A TabNet match expression is a code, a range or a comma list.
                # It never contains free internal whitespace, which makes this
                # detectable rather than a matter of taste: fall back to the
                # token split, and say so.
                lead = _first_expression(expression)
                if lead is not None:
                    # The column split was right and the line carries trailing
                    # junk. Keep the aligned code and the label the column gave,
                    # and record what was discarded rather than dropping it
                    # silently — it is evidence the source file is damaged.
                    expression, discarded = lead
                    out.warnings.append(
                        f"line {line_no}: text after the match expression "
                        f"{expression!r} is not part of it ({discarded[:40]!r}); "
                        "discarded"
                    )
                else:
                    out.warnings.append(
                        f"line {line_no}: text past the expression column "
                        f"is not a match expression ({expression[:40]!r}); "
                        "re-split on tokens"
                    )
                    label = " ".join(t.group() for t in tokens[1:-1]).strip()
                    expression = tokens[-1].group()
        else:
            label = " ".join(t.group() for t in tokens[1:-1]).strip()
            expression = tokens[-1].group()
            if expr_col is not None:
                out.warnings.append(f"line {line_no}: label overflows expression column")
        codes, unexpanded = expand_expression(
            expression, width=width, universe=universe, max_expansion=max_expansion
        )
        out.categories.append(
            CnvCategory(
                order=offset,
                sequence=sequence,
                label=label,
                expression=expression,
                line_no=line_no,
                codes=codes,
                unexpanded=unexpanded,
            )
        )

    if declared is not None and declared != len(out.categories):
        out.warnings.append(
            f"header declares {declared} categories, {len(out.categories)} parsed"
        )
    return out


def parse_cnv(path: str | Path, **kwargs: object) -> CnvFile:
    p = Path(path)
    return parse_cnv_bytes(p.read_bytes(), name=p.name, source_ref=str(p), **kwargs)  # type: ignore[arg-type]


# ------------------------------------------------------------------ expansion

#: Whitespace that legitimately sits inside an expression: around a range dash
#: and around the commas of a list. Anything else means the split was wrong.
_EXPRESSION_GLUE = re.compile(r"\s*([-,])\s*")


def _is_expression(text: str) -> bool:
    """Could this be a TabNet match expression at all?

    Codes, ranges (``1-5``, ``A00-B99``) and comma lists. Never free prose, so a
    residual space after collapsing the range and list separators means the text
    is a label that overran the expression column.
    """
    return " " not in _EXPRESSION_GLUE.sub(r"\1", text.strip())


_NUMERIC_RANGE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
_ALNUM_RANGE = re.compile(r"^([A-Za-z0-9.]+)\s*-\s*([A-Za-z0-9.]+)$")


def expand_expression(
    expression: str,
    *,
    width: int | None = None,
    universe: frozenset[str] | None = None,
    max_expansion: int = 50_000,
) -> tuple[list[str], list[str]]:
    """Turn a match expression into concrete codes.

    Returns ``(codes, unexpanded)``. Anything that lands in ``unexpanded`` is a
    finding to be recorded as a rule, never an entry to be dropped.
    """
    codes: list[str] = []
    unexpanded: list[str] = []
    for part in (p.strip() for p in expression.split(",")):
        if not part:
            continue
        numeric = _NUMERIC_RANGE.match(part)
        if numeric:
            lo_raw, hi_raw = numeric.group(1), numeric.group(2)
            lo, hi = int(lo_raw), int(hi_raw)
            if hi < lo:
                unexpanded.append(part)
                continue
            if hi - lo + 1 > max_expansion:
                unexpanded.append(part)
                continue
            # Pad to the header's declared code width, which is how TabNet matches.
            # The unpadded form is deliberately *not* also emitted: adding '0' as
            # an alias for '000000' would let a stray single digit pick up a
            # municipality's label.
            pad = max(len(lo_raw), len(hi_raw), width or 0)
            codes.extend(str(v).zfill(pad) for v in range(lo, hi + 1))
            continue
        alnum = _ALNUM_RANGE.match(part)
        if alnum:
            lo_s, hi_s = alnum.group(1).upper(), alnum.group(2).upper()
            if universe:
                span = _expand_against_universe(lo_s, hi_s, universe)
                if span:
                    codes.extend(span)
                    continue
            unexpanded.append(part)
            continue
        codes.append(part)
        if width and part.isdigit() and len(part) < width:
            codes.append(part.zfill(width))
    # Preserve first-seen order while removing duplicates.
    return list(dict.fromkeys(codes)), unexpanded


@lru_cache(maxsize=8)
def _sorted_universe(universe: frozenset[str]) -> tuple[str, ...]:
    return tuple(sorted(universe))


def _expand_against_universe(lo: str, hi: str, universe: frozenset[str]) -> list[str]:
    """Members of a known code universe lying between two endpoints.

    Comparison is on the endpoint's own width, which is how TabNet matches: the
    range ``A00-B99`` covers every code whose first three characters sort within
    those bounds, so ``A001`` and ``B991`` are both inside it.

    Bisected rather than scanned. The per-chapter CID files carry thousands of
    ranges each and there are dozens of them in a kit; scanning the 14,197-code
    universe per range turned dictionary ingestion into roughly a billion string
    comparisons. Truncation preserves sort order — ``a <= b`` implies
    ``a[:n] <= b[:n]`` — so the matching codes are always one contiguous slice.
    """
    ordered = _sorted_universe(universe)
    n = max(len(lo), len(hi))
    start = bisect_left(ordered, lo, key=lambda c: c[:n].ljust(n))
    stop = bisect_right(ordered, hi, key=lambda c: c[:n].ljust(n))
    return list(ordered[start:stop])
