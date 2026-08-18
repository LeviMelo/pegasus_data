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
_HEADER = re.compile(r"^\s*(\d+)\s+(\d+)\s*$")


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
    body_start = 0
    header = _HEADER.match(raw_lines[0])
    if header:
        declared = int(header.group(1))
        width = int(header.group(2))
        body_start = 1
    body = [ln for ln in raw_lines[body_start:] if ln.strip()]

    expr_col = _expression_column(body)
    out = CnvFile(name, source_ref, declared, width, encoding=encoding)

    for offset, line in enumerate(body):
        tokens = list(_TOKEN.finditer(line))
        if not tokens:
            continue
        sequence = tokens[0].group()
        if len(tokens) == 1:
            out.warnings.append(f"line {offset + body_start + 1}: no match expression")
            continue
        if expr_col is not None and len(line) > expr_col and line[expr_col - 1 : expr_col] in (" ", ""):
            label = line[tokens[0].end() : expr_col].strip()
            expression = line[expr_col:].strip()
            if not expression:
                label = " ".join(t.group() for t in tokens[1:-1]).strip()
                expression = tokens[-1].group()
        else:
            label = " ".join(t.group() for t in tokens[1:-1]).strip()
            expression = tokens[-1].group()
            if expr_col is not None:
                out.warnings.append(f"line {offset + body_start + 1}: label overflows expression column")
        codes, unexpanded = expand_expression(
            expression, width=width, universe=universe, max_expansion=max_expansion
        )
        out.categories.append(
            CnvCategory(
                order=offset,
                sequence=sequence,
                label=label,
                expression=expression,
                line_no=offset + body_start + 1,
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
