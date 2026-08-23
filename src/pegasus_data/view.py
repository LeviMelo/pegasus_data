"""Rendering: turning stored codes into something a person can read (§5).

The governing goal is that a user should never see an untranslated internal code
and should never need an external table to understand what they are looking at.
Everything here serves that.

Storage and view are separate concerns, and keeping them separate is what makes
every option below a parameter instead of a build variant. The lake stores raw
codes, companion columns and provenance — written once, machine-facing, stable.
This module applies every presentation decision at **read** time, from the
version-scoped reference tables. Nobody rebuilds a lake to change how a column
is displayed, and nobody has to choose a rendering before they know the question.

The axis that decides rendering is ``code_system`` from the curated variable
dictionary (§4), not a heuristic:

* ``internal`` — DATASUS-invented, meaningless outside the system, joins to
  nothing. The label **replaces** the code. Nobody wants ``1`` in a finished
  output, and ``SEXO = 1`` is not a fact about the world.
* ``external`` — a canonical identifier in its own right: ICD-10, CBO, IBGE
  município, CNES, SIGTAP. The code **and** the label. The code is a join key
  and must survive; the label is still needed to read the row.
* ``none`` — dates, money, counts, free text. The value as typed.

The previous rule keyed on whether a codelist was hierarchical or large. That
correlated with the right answer for the wrong reason — ICD is hierarchical
*and* external, so the heuristic worked until it met an internal hierarchy — and
it stated the policy as a threshold in the source rather than as a field a user
can read.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.compute as pc

from .catalog.store import Catalog
from .persist.reference import read_reference_table
from .semantics.curation import VariableDoc, load_variable_docs

RenderMode = Literal["code", "label", "both", "combined"]

#: How a combined value reads: ``1 – Masculino``. An en dash, because a hyphen
#: is already inside plenty of codes.
COMBINED_SEP = " – "

#: Multi-valued columns join with this. Wide enough to survive a label that has
#: commas in it, which ICD labels routinely do.
TOKEN_JOIN = " | "


class LabelUnavailable(RuntimeError):
    """A label was requested for a field that cannot produce one.

    Raised rather than returning the codes unlabelled. Silently handing back
    unlabelled data when labels were asked for is the failure §5.5 exists to
    close: the caller believes it read one thing and actually read another, and
    nothing in the result says so.
    """


@dataclass(frozen=True, slots=True)
class RenderProfile:
    """What a profile decides, before any per-column override is applied."""

    name: str
    internal: RenderMode = "label"
    external: RenderMode = "both"
    companions: bool = True
    derived: bool = True
    headers: Literal["original", "translated", "both"] = "original"
    values: Literal["separate", "combined"] = "separate"


PROFILES: dict[str, RenderProfile] = {
    # The default. Labels everywhere, codes kept where they are join keys.
    "analysis": RenderProfile("analysis"),
    # Nothing rendered: the lake as stored, for a pipeline stage that will do its
    # own joining and wants no surprises.
    "codes": RenderProfile(
        "codes", internal="code", external="code", companions=False, derived=False
    ),
    # Everything visible at once, including the internal codes the analysis
    # profile hides, so a disagreement can be traced back to what was stored.
    "audit": RenderProfile("audit", internal="both", external="both"),
    # For a document someone reads. Translated headers and combined values are
    # both hostile to machines and are why this is not the default.
    "report": RenderProfile("report", headers="translated", values="combined"),
}


@dataclass(slots=True)
class RenderReport:
    """What rendering actually did, so the caller need not infer it."""

    labelled: list[str] = field(default_factory=list)
    unlabelled: list[str] = field(default_factory=list)
    #: Codelists whose labels came from another system's copy because the
    #: requested system ships none. Machine-readable, so a strict analytical
    #: profile can reject them rather than parsing prose.
    borrowed: list[str] = field(default_factory=list)
    #: ``table_id -> "current" | "unresolved"``. The requested vintage did not
    #: exist, so either today's table stood in or nothing did. A historical
    #: label rendered from today's table is not wrong the way a borrowed
    #: system's is, but it is not what was asked for — and the caller could
    #: previously only detect it by reading `valid_from` off the reference
    #: table and knowing what to compare it against.
    fallback_vintage: dict[str, str] = field(default_factory=dict)
    #: ``column -> share`` where a bound codelist decoded only part of the
    #: observed codes. Already in `warnings` as prose; here as a number, so a
    #: threshold can be applied instead of a regex.
    partial_codelist_match: dict[str, float] = field(default_factory=dict)
    #: Columns labelled through a rolled-up parent codelist rather than an
    #: exact-width match.
    rollup_used: list[str] = field(default_factory=list)
    #: ``column -> codelist`` — which reference table actually produced the
    #: labels. `labelled` says THAT a column was decoded and this says BY WHAT,
    #: which is a different question and the one that catches a wrong answer:
    #: CODMUNRES was in `labelled` for months while CIRAC was quietly naming
    #: health regions where municipalities were asked for. Only a caller who
    #: could see the table name could see the defect.
    codelist_used: dict[str, str] = field(default_factory=dict)
    #: ``rendered name -> DATASUS name``, when a profile translated the headers.
    #: The `report` profile does, and it is the CLI's default, so anything built
    #: from the rendered table afterwards — the data dictionary — would look up
    #: "Mother's age" in curation, find nothing, and describe nothing.
    renamed_headers: dict[str, str] = field(default_factory=dict)
    #: Unlabelled columns holding one value in every row, with that value —
    #: ``CID_MORTE`` is ``'0000'`` 59,835 times in SIH-RD/AC/2023. These are ALSO
    #: in ``unlabelled``, so nothing a caller checks today is lost; this names
    #: the subset that is dead data rather than a labelling defect, which is
    #: what lets a reader subtract the noise instead of skimming past all of it.
    #: It is a finding in its own right: the column carries nothing in this
    #: slice, which is worth knowing before an analysis is built on it.
    constant: dict[str, str] = field(default_factory=dict)
    derived_added: list[str] = field(default_factory=list)
    companions_dropped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tokens_unmatched: dict[str, int] = field(default_factory=dict)
    structural_absence: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "labelled": self.labelled,
            "unlabelled": self.unlabelled,
            "constant": self.constant,
            "borrowed": self.borrowed,
            "fallback_vintage": self.fallback_vintage,
            "partial_codelist_match": self.partial_codelist_match,
            "rollup_used": self.rollup_used,
            "codelist_used": self.codelist_used,
            "derived_added": self.derived_added,
            "companions_dropped": self.companions_dropped,
            "warnings": self.warnings,
            "tokens_unmatched": self.tokens_unmatched,
            "structural_absence": self.structural_absence,
        }


# --------------------------------------------------------------- column kinds

#: Suffixes normalisation writes for *companion* columns — genuinely new
#: information derived from a value, as opposed to a label, which adds none.
#: ``MUNIC_RES_uf`` is not readable off ``MUNIC_RES`` unless you know the IBGE
#: prefix scheme; ``SEXO_label`` tells you nothing ``SEXO`` did not already say.
COMPANION_SUFFIXES: tuple[str, ...] = (
    "_ibge7", "_ibge6", "_uf", "_region", "_epi_week", "_epi_year",
    "_iso", "_raw", "_valid", "_checkdigit_ok",
)

LABEL_SUFFIX = "_label"


def column_kind(name: str, base_columns: frozenset[str]) -> str:
    """``raw`` · ``label`` · ``companion``, decided by suffix against the raws."""
    if name.endswith(LABEL_SUFFIX) and name[: -len(LABEL_SUFFIX)] in base_columns:
        return "label"
    for suffix in COMPANION_SUFFIXES:
        if name.endswith(suffix) and name[: -len(suffix)] in base_columns:
            return "companion"
    return "raw"


# ------------------------------------------------------------------ labelling


def _lookup_map(
    lake_root: Path,
    codelist: str,
    *,
    system: str | None,
    year: int | None,
    competencia: int | None = None,
    code_width: int | None,
) -> dict[str, str]:
    """``code -> label`` for one codelist at one vintage.

    Reads the *version-scoped* table: a 1995 admission decodes against the
    1992–1997 vintage, not against today's. Materialising the labels into the
    lake would have frozen one vintage's wording forever, which is why they are
    joined here instead.
    """
    table = read_reference_table(
        lake_root,
        codelist,
        system=system,
        year=year,
        competencia=competencia,
        code_width=code_width,
    )
    codes = table.column("code").to_pylist()
    labels = table.column("label").to_pylist()
    # Last write wins, matching .CNV semantics, where a later line deliberately
    # overrides an earlier one. A blank label is dropped rather than stored: an
    # empty string is not a translation, and offering one turns a labelled column
    # into a column of nothing while still reporting that it was labelled. This
    # is how CADMUN behaved — a DBF lookup that picked OBSERV as its label
    # column, which is blank for 5,517 of its 5,579 rows.
    return {
        str(c): str(lbl)
        for c, lbl in zip(codes, labels, strict=True)
        if c is not None and lbl is not None and str(lbl).strip()
    }


def _single_lookup(
    lake_root: Path,
    codelist: str,
    system: str | None,
    year: int | None,
    code_width: int | None,
    competencia: int | None = None,
) -> dict[str, str] | None:
    """One codelist's ``code -> label``, or ``None`` if it is not materialised.

    Separate from :func:`_lookup_map` only so a missing table is a *candidate
    that loses* rather than an exception the chooser has to catch per call.
    """
    try:
        return _lookup_map(
            lake_root,
            codelist,
            system=system,
            year=year,
            competencia=competencia,
            code_width=code_width,
        )
    except (FileNotFoundError, OSError):
        return None


def _contradictions(
    lake_root: Path,
    codelist: str,
    *,
    system: str | None,
    year: int | None,
    competencia: int | None = None,
    code_width: int | None,
) -> dict[str, set[str]]:
    """Codes the table maps to more than one label.

    Last-write-wins is correct *within* a ``.CNV``, where a later line
    deliberately supersedes an earlier one. It is not correct across files that
    disagree: the merged ``SEXO`` table contains both ``1 -> Masculino`` and
    ``1 -> Feminino``, because different systems encoded sex differently and the
    kit ships both. Silently taking whichever sorted last would label half the
    hospital admissions in Brazil with the wrong sex, and nothing in the output
    would show it.
    """
    table = read_reference_table(
        lake_root,
        codelist,
        system=system,
        year=year,
        competencia=competencia,
        code_width=code_width,
    )
    seen: dict[str, set[str]] = {}
    for code, label in zip(
        table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True
    ):
        if code is None or label is None:
            continue
        seen.setdefault(str(code), set()).add(str(label))
    return {code: labels for code, labels in seen.items() if len(labels) > 1}


def _widths(lookup: Mapping[str, str]) -> set[int]:
    return {len(code) for code in lookup}


def _bindings(store: Catalog, system: str, family_id: str | None) -> dict[str, list[str]]:
    """``field -> codelists``, best authority first.

    **One table per field unless a curated entry names more.** A ``.DEF`` binds a
    column to every tabulation axis that mentions it — 34 tables for
    ``MUNIC_RES``, 114 for ``DIAG_PRINC`` — and most of those are roll-ups, not
    alternative encodings. Merging them and taking first-wins labels a
    municipality with the name of its health macro-region, which is wrong in a
    way that looks perfectly plausible on the page.

    Several tables are correct only when they are the *same* classification split
    by width: ``SP_ATOPROF`` is 8 characters in one era and 10 in another, so its
    values live in ``TPROC`` and ``TPROC10`` and binding either alone leaves half
    the history unlabelled. That case is a judgement about what the column is,
    which is exactly what ``curation/`` is for — so it is declared there as
    ``codelists: [TPROC, TPROC10]`` and never inferred from how many tables
    happen to mention the field.

    ``family_id=''`` rows are system-wide; a family-specific binding sorts first.
    """
    rows = store.query(
        """
        SELECT field_name, codelist, family_id, source, confidence, decodes_observed
          FROM field_codelists
         WHERE system = ? AND (family_id = '' OR family_id = ?)
        """,
        (system.upper(), family_id or ""),
    )

    def _rank(row: object) -> tuple[int, float, int, str]:
        """Order candidates deterministically, best first.

        Confidence alone is not enough and the gap it leaves is not academic:
        CNES's NAT_JUR is bound by .DEF to six tables — NATJUR, NATJURC,
        ESFERAJUR, ESFERAJURC, ATJURC, RETENCAO — all at 0.9. With nothing to
        break the tie, SQLite returned them in whatever order it liked and the
        renderer picked ATJURC on one run and something else on the next. A
        column whose label depends on row order is not reproducible.

        So a name that matches the field breaks the tie, which is a real signal
        rather than an arbitrary one: NAT_JUR's own table is NATJUR, and the
        others are roll-ups and neighbours. Alphabetical order is the last
        resort, purely so the answer is stable.
        """
        codelist = str(row["codelist"]).upper()  # type: ignore[index]
        field = str(row["field_name"]).upper()  # type: ignore[index]
        squashed = field.replace("_", "")
        if codelist in (field, squashed):
            affinity = 0
        elif squashed.startswith(codelist) or codelist.startswith(squashed):
            affinity = 1
        else:
            affinity = 2
        family_specific = 0 if str(row["family_id"]) else 1  # type: ignore[index]
        # A binding measured to decode none of the column's observed values goes
        # last. `.DEF` declares tabulation axes beside code systems and cannot
        # distinguish them, so a date column arrives bound to ANOMES and an age
        # to a table of age bands — 35.2% of measurable bindings decode nothing.
        # Deprioritised rather than excluded: the measurement is taken against
        # the values the profiler saw, and a partition of other years could hold
        # values it did not. Sorting it last costs nothing when a working table
        # exists and changes nothing when none does.
        measured = row["decodes_observed"]  # type: ignore[index]
        decodes_nothing = 1 if measured is not None and float(measured) == 0 else 0
        return (
            family_specific,
            decodes_nothing,
            -float(row["confidence"] or 0),  # type: ignore[index]
            affinity,
            codelist,
        )

    # Every candidate is kept, best first. They must never be MERGED — that is
    # what labels a municipality with the name of its health macro-region — but
    # the caller can now test them against the column in hand and pick the one
    # that actually decodes it, which ranking alone cannot do.
    out: dict[str, list[str]] = {}
    for r in sorted(rows, key=_rank):
        out.setdefault(str(r["field_name"]).upper(), []).append(str(r["codelist"]))
    return out


#: How many candidates to weigh for one column. `.DEF` binds DIAG_PRINC to 114
#: tables; reading them all to label one column costs more than it can return.
#: The list is ranked, so the right table is near the front when it is present.
_MAX_CANDIDATES = 12

#: A candidate this good ends the search — nothing later can beat it.
_GOOD_ENOUGH = 0.99

#: Below this share, the best candidate is evidence that NONE of the bound
#: tables is the right one. `PROC_REA` has 12 tables bound and the best decodes
#: 3% of its codes — labelling from it would fill 3% of the column and leave 97%
#: null, which reads as "these procedures are unknown" rather than "we bound the
#: wrong table". Refusing is the honest answer and keeps the raw codes usable.
_TOO_WEAK = 0.5


#: Two candidates whose decode rates are within this of each other are treated
#: as equally good, and the tie goes to whichever preserves more distinctions.
_SHARE_TIE = 0.05

#: A table mapping observed codes to fewer distinct labels than this is a
#: ROLLUP: it answers a coarser question than the column asks.
_ROLLUP = 0.5


def _choose_binding(
    field_name: str,
    candidates: Sequence[str],
    observed: set[str],
    load: Callable[[str], dict[str, str] | None],
) -> tuple[str | None, float, int, float]:
    """Pick the bound codelist that decodes the most of what the column holds.

    Ranking got the caller a *deterministic* choice, not a *correct* one, and
    the difference was doing real damage. `CNES` in SIH is bound by `.DEF` to 31
    tables — `TCNESBR`, one per state, and three federal-hospital lists — all at
    confidence 0.9, none whose name resembles the field. Every tie-break fell
    through to alphabetical order, so the renderer chose `HOSFEDRJ`: six rows,
    federal hospitals in Rio de Janeiro. Acre's establishment codes matched none
    of them and the column came back raw, while `TCNESBR` sat in the same lake
    with 7,189 rows including every code in the file.

    The data is right there. Measuring against it turns an arbitrary pick into
    an evidence-based one, and costs one parquet read per candidate — bounded by
    ``_MAX_CANDIDATES`` and short-circuited as soon as a table decodes
    essentially everything.

    Decode rate alone is not enough, and the way it fails is subtle. SINASC's
    CODMUNRES holds municipality codes like ``120040`` (Rio Branco), and the
    health-REGION table ``CIRAC`` contains every one of those codes — mapped to
    the region that contains them. It scores 100% and labels Rio Branco
    "Baixo Acre e Purus", which is not wrong so much as a different question,
    answered confidently.

    So granularity breaks the tie: among candidates that decode about equally
    well, the one preserving the most distinctions wins. A table collapsing 22
    municipalities into 5 regions is a rollup, and the caller is told when the
    best available table is one.

    Returns ``(codelist, share_decoded, candidates_tried, granularity)``.
    """
    if not observed:
        return (candidates[0] if candidates else None), 0.0, 0, 1.0
    scored: list[tuple[str, float, float]] = []
    tried = 0
    for codelist in list(candidates)[:_MAX_CANDIDATES]:
        lookup = load(codelist)
        tried += 1
        if not lookup:
            continue
        hits = [lookup[v] for v in observed if v in lookup]
        share = len(hits) / len(observed)
        # `observed` is a SET, so this weighs a code appearing once the same as
        # one appearing in 90% of rows. That is a deliberate semantic signal —
        # a table that covers the variety of a column is the right table — but
        # it is not the whole story, and the row-weighted figure is reported
        # alongside it so a caller can see both.
        # How much of the column's own variety survives the translation.
        granularity = (len(set(hits)) / len(hits)) if hits else 0.0
        scored.append((codelist, share, granularity))
        if share >= _GOOD_ENOUGH and granularity >= _GOOD_ENOUGH:
            break
    if not scored:
        return (candidates[0] if candidates else None), 0.0, tried, 1.0
    best_share = max(s for _, s, _ in scored)
    # 1e-9 because 1.0 - 0.95 is 0.050000000000000044, and a candidate should
    # not fall out of the band on a rounding artefact.
    contenders = [c for c in scored if best_share - c[1] <= _SHARE_TIE + 1e-9]
    codelist, share, granularity = max(contenders, key=lambda c: (c[2], c[1]))
    return codelist, max(share, 0.0), tried, granularity


def _tokenize(value: str, rule: Mapping[str, Any]) -> list[str]:
    """Split a packed multi-valued cell into its codes, in order.

    Order carries meaning — on a death certificate the sequence *is* the causal
    chain — so nothing here sorts or deduplicates.
    """
    text = (value or "").strip()
    if not text:
        return []
    delimiter = rule.get("delimiter")
    if delimiter:
        # A rule may name SEVERAL separators, and one column needs it: SIM's
        # ATESTADO writes "T07/X366*Y96", mixing '/' and '*' in a single cell.
        # Splitting on one of them leaves the other embedded in a token and the
        # whole value reads as malformed.
        chars = str(delimiter)
        if len(chars) > 1:
            parts = [p.strip() for p in re.split(f"[{re.escape(chars)}]", text)]
        else:
            parts = [p.strip() for p in text.split(chars)]
        return [p for p in parts if p]
    width = int(rule.get("width") or 0)
    if width <= 0:
        return [text]
    return [
        chunk for chunk in (text[i : i + width].strip() for i in range(0, len(text), width)) if chunk
    ]


def _render_multi_valued(
    column: pa.Array, rule: Mapping[str, Any], lookup: Mapping[str, str]
) -> tuple[list[str | None], list[list[str]], list[int]]:
    """Label every token, keep the order, and never drop one.

    A token with no match passes through as its raw code. Dropping it would make
    a shorter causal chain than the physician wrote, and nulling the whole cell
    would discard the tokens that *did* resolve.
    """
    rendered: list[str | None] = []
    code_lists: list[list[str]] = []
    unmatched: list[int] = []
    for value in column.to_pylist():
        if value is None:
            rendered.append(None)
            code_lists.append([])
            unmatched.append(0)
            continue
        tokens = _tokenize(str(value), rule)
        misses = 0
        pieces: list[str] = []
        for token in tokens:
            label = lookup.get(token)
            if label is None:
                misses += 1
                pieces.append(token)
            else:
                pieces.append(f"{token} {label}")
        rendered.append(TOKEN_JOIN.join(pieces) if pieces else None)
        code_lists.append(tokens)
        unmatched.append(misses)
    return rendered, code_lists, unmatched


def _labels_for(column: pa.Array, lookup: Mapping[str, str]) -> pa.Array:
    """Exact width or no match (§6.2).

    Whitespace is stripped and nothing else. No padding, no truncation, no
    matching across widths — a 3-digit CBO-1994 code and the first three digits
    of a 6-digit CBO-2002 code are different things that happen to share a
    prefix, and 452 tables on this tree mix both classifications in one file. An
    exact string comparison enforces this by construction, and
    :func:`_check_width` is what stops a future "helpful" pad from undoing it.
    """
    # Resolved once per DISTINCT code, not once per row. A million-row
    # categorical field with six distinct values was doing a million Python
    # dictionary lookups to answer six questions; dictionary-encoding it turns
    # that into six lookups and an index remap that stays inside Arrow.
    if not len(column):
        return pa.array([], type=pa.string())
    try:
        encoded = pc.dictionary_encode(column)
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError):  # pragma: no cover
        values = column.to_pylist()
        return pa.array(
            [None if v is None else lookup.get(str(v).strip()) for v in values],
            type=pa.string(),
        )
    if isinstance(encoded, pa.ChunkedArray):
        encoded = encoded.combine_chunks()
    uniques = encoded.dictionary.to_pylist()
    mapped = pa.array(
        [None if u is None else lookup.get(str(u).strip()) for u in uniques],
        type=pa.string(),
    )
    # take() carries the nulls through: a null index yields a null label.
    return pc.take(mapped, encoded.indices)


def _check_width(
    field_name: str, codelist: str, column: pa.Array, lookup: Mapping[str, str]
) -> str | None:
    """Warn when a field's values and its codelist disagree about width.

    The dangerous case is silent: a 6-digit CBO column against a table holding
    both 3- and 6-digit codes matches only the 6-digit ones and looks like a
    partial-coverage problem rather than two classifications sharing a file. Say
    so, because the fix is to bind the right width, not to loosen the match.
    """
    table_widths = _widths(lookup)
    if len(table_widths) < 2:
        return None
    observed = {len(str(v).strip()) for v in column.to_pylist() if v is not None}
    if not observed:
        return None
    unmatched = observed - table_widths
    return (
        f"{field_name}: codelist {codelist!r} mixes code widths {sorted(table_widths)}; "
        f"the column holds widths {sorted(observed)}"
        + (f", of which {sorted(unmatched)} match nothing" if unmatched else "")
        + ". Widths are matched exactly and never padded or truncated (§6.2)"
    )


def _combine(codes: pa.Array, labels: pa.Array) -> pa.Array:
    """``code – label``, unless the label already opens with the code.

    Many DATASUS `.CNV` tables write the code into the label — BR_MUNICIPALFA
    maps ``120001`` to ``'120001 Acrelândia, AC'`` — and combining blindly
    produced ``'120001 – 120001 Acrelândia, AC'`` in the report profile's
    output. The code is not missing from those cells, it is doubled, so the fix
    is to not add what is already there.

    The boundary check is what keeps this from over-firing: code ``12`` against
    label ``'120001 Acrelândia'`` starts-with, but ``0`` is not a boundary, so
    the code is still prefixed.
    """
    out: list[str | None] = []
    for code, label in zip(codes.to_pylist(), labels.to_pylist(), strict=True):
        if code is None and label is None:
            out.append(None)
        elif label is None:
            out.append(str(code))
        elif code is None:
            out.append(str(label))
        else:
            text, key = str(label), str(code)
            rest = text[len(key):]
            if text.startswith(key) and (not rest or not rest[0].isalnum()):
                out.append(text)
            else:
                out.append(f"{key}{COMBINED_SEP}{text}")
    return pa.array(out, type=pa.string())


# -------------------------------------------------------------------- derived


_UNIT_YEARS = re.compile(r"\ban(?:o|os)\b", re.I)
_UNIT_MONTHS = re.compile(r"\b(?:m[eê]s|meses)\b", re.I)
_UNIT_DAYS = re.compile(r"\bdias?\b", re.I)
_UNIT_HOURS = re.compile(r"\bhoras?\b", re.I)
_UNIT_MINUTES = re.compile(r"\bminutos?\b", re.I)

#: How many of a unit make a year. Read off the unit column's own labels rather
#: than hardcoded per system, because SIH and SIM number their units differently
#: and both change over time.
_PER_YEAR: tuple[tuple[re.Pattern[str], float], ...] = (
    (_UNIT_YEARS, 1.0),
    (_UNIT_MONTHS, 12.0),
    (_UNIT_DAYS, 365.25),
    (_UNIT_HOURS, 365.25 * 24),
    (_UNIT_MINUTES, 365.25 * 24 * 60),
)


def _unit_divisors(lookup: Mapping[str, str]) -> dict[str, float]:
    """``unit code -> how many of it make a year``, from the codelist's labels."""
    out: dict[str, float] = {}
    for code, label in lookup.items():
        for pattern, per_year in _PER_YEAR:
            if pattern.search(label):
                out[code] = per_year
                break
    return out


def _derive_age_years(
    table: pa.Table, value_column: str, unit_column: str, divisors: Mapping[str, float]
) -> pa.Array | None:
    """Resolve a value+unit pair into years — the canonical multi-column case.

    ``IDADE`` alone is not interpretable: 030 with a unit of months is thirty
    months, and averaging the column across a population mixes units and returns
    a number that is not an age. This is the whole reason ``depends_on`` is
    recorded in §4.
    """
    if value_column not in table.schema.names or unit_column not in table.schema.names:
        return None
    values = table.column(value_column).to_pylist()
    units = table.column(unit_column).to_pylist()
    out: list[float | None] = []
    for raw, unit in zip(values, units, strict=True):
        divisor = divisors.get(str(unit).strip()) if unit is not None else None
        if raw is None or divisor is None:
            out.append(None)
            continue
        try:
            number = float(str(raw).strip())
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(round(number / divisor, 4))
    return pa.array(out, type=pa.float64())


# --------------------------------------------------------------------- render


def resolve_profile(
    profile: str | RenderProfile = "analysis",
    *,
    headers: str | None = None,
    values: str | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
) -> RenderProfile:
    """A named profile with any explicit override applied on top."""
    base = profile if isinstance(profile, RenderProfile) else PROFILES.get(str(profile))
    if base is None:
        raise KeyError(f"unknown render profile {profile!r}; known: {sorted(PROFILES)}")
    changes: dict[str, Any] = {}
    if headers is not None:
        changes["headers"] = headers
    if values is not None:
        changes["values"] = values
    if isinstance(companions, bool):
        changes["companions"] = companions
    if isinstance(derived, bool):
        changes["derived"] = derived
    return replace(base, **changes) if changes else base


@dataclass
class _Selection:
    """Which codelist(s) will decode a column, and whether any can.

    ``unlabelled`` means selection already decided the answer is "none of them"
    and has already recorded why — the caller emits the column as filed and
    moves on.
    """

    codelists: list[str] = field(default_factory=list)
    share: float | None = None
    unlabelled: bool = False


def _select_codelists(
    name: str,
    column: pa.ChunkedArray,
    *,
    doc: object,
    candidates: list[str],
    report: RenderReport,
    strict: bool,
    lookup_one: Callable[[str, int | None], dict[str, str] | None],
    store: Catalog | None = None,
    system: str = "",
    family_id: str = "",
) -> _Selection:
    """Choose the codelist(s) for one column, or decide that none fits.

    Kept apart from rendering because it is a different question. Rendering asks
    "how should this column be shown"; this asks "what does this column MEAN",
    and answering it involves weighing every bound table against the values the
    column actually holds. Inline, the two were interleaved across 200 lines and
    shared six mutable locals, which is where the width, rollup and
    partial-match defects in this review lived.

    It reports its own findings — the caller cannot reconstruct why a column was
    left unlabelled without re-doing the weighing.
    """
    if doc is not None and getattr(doc, "codelist", None):
        # A curated entry decides both the table and whether there are several.
        # Nothing else may widen it.
        return _Selection(codelists=[doc.codelist, *doc.codelists])  # type: ignore[attr-defined]

    # A reviewed adjudication is a semantic declaration too. It lives in the
    # catalog until the next resource/curation build promotes it to YAML; if the
    # runtime ignored it, `adjudicate apply` would close a queue item while the
    # renderer continued making the same refusal.
    if store is not None:
        try:
            dataset = "*"
            if family_id:
                family = store.query(
                    "SELECT series FROM families WHERE family_id=?", (family_id,)
                )
                series = str(family[0]["series"] or "").upper() if family else ""
                dataset = f"{system}.{series}"
            from .semantics.relations import RelationType, relations_for

            artifacts = sorted(
                {
                    item.artifact
                    for item in relations_for(
                        system,
                        dataset,
                        name,
                        relation_type=RelationType.LABEL_OF,
                        catalog=store,
                    )
                }
            )
            if len(artifacts) == 1:
                return _Selection(codelists=artifacts)
        except Exception:  # noqa: BLE001 - old/read-only catalogs keep safe behavior
            pass

    if len(candidates) <= 1:
        if not candidates:
            return _Selection()
        # A LONE binding is still measured for granularity. This returned
        # immediately, so the roll-up guard only ever ran when several
        # codelists competed — and the case it was written for is a single
        # one: SINASC's CODMUNRES bound only to CIRAC, which decodes 100% of
        # the municipality codes and answers with a health region. With one
        # candidate there was nothing to compare it against and nothing said
        # so.
        seen = {
            str(v).strip() for v in column.to_pylist() if v is not None and str(v).strip()
        }
        width_hint = None
        if doc is not None and getattr(doc, "token_rule", None) and not getattr(doc, "multi_valued", False):
            width_hint = doc.token_rule.get("width")
        lookup = lookup_one(candidates[0], width_hint) if seen else None
        if lookup:
            hits = [lookup[v] for v in seen if v in lookup]
            grain = (len(set(hits)) / len(hits)) if hits else 1.0
            if hits and grain < _ROLLUP:
                report.warnings.append(
                    f"{name}: labelled from {candidates[0]!r}, which is a ROLLUP — it "
                    f"maps the observed codes to {grain:.0%} as many distinct labels, "
                    "so the label is broader than the code. It is the only table bound "
                    "to this column."
                )
                report.rollup_used.append(name)
        return _Selection(codelists=candidates)

    if len(candidates) > _MAX_CANDIDATES:
        message = (
            f"{name}: {len(candidates)} codelists are bound without an explicit "
            "semantic declaration. Refused to choose from an arbitrarily capped "
            f"subset of {_MAX_CANDIDATES}; curate this field before labelling it."
        )
        if strict:
            raise LabelUnavailable(message)
        report.warnings.append(message)
        report.unlabelled.append(name)
        if store is not None:
            try:
                from .semantics.relations import ensure_adjudication_item

                ensure_adjudication_item(
                    store,
                    kind="semantic_relation",
                    system=system,
                    family_id=family_id,
                    field=name.upper(),
                    candidates=candidates,
                    reason=message,
                    observed_summary={"distinct_sample": len(set(column.to_pylist()))},
                )
            except Exception:  # noqa: BLE001 - read-only catalogs still return safely
                pass
        return _Selection(unlabelled=True)

    # Several tables claim this column and nothing declared which is right. Ask
    # the data.
    width_hint = None
    if doc is not None and getattr(doc, "token_rule", None) and not getattr(doc, "multi_valued", False):
        width_hint = doc.token_rule.get("width")  # type: ignore[attr-defined]
    seen = {
        str(v).strip() for v in column.to_pylist() if v is not None and str(v).strip()
    }
    picked, share, tried, grain = _choose_binding(
        name.upper(),
        candidates,
        seen,
        # width_hint bound at definition: the callback is invoked synchronously
        # today, but a closure over a loop variable is one refactor away from
        # every column being weighed at the last column's width.
        lambda cl, w=width_hint: lookup_one(cl, w),
    )

    if picked and share < _TOO_WEAK:
        if len(seen) <= 1:
            # One value in every row and nothing decodes it. That is a dead
            # column, not a labelling failure. Recorded in both, so a caller
            # loses nothing and can still tell them apart.
            report.constant[name] = next(iter(seen), "")
            report.unlabelled.append(name)
            return _Selection(unlabelled=True)
        # None of them fits. Say which was closest, and how badly.
        message = (
            f"{name}: {tried} codelists are bound and none decodes the "
            f"column — the best, {picked!r}, matches {share:.0%} of "
            f"observed codes. Left unlabelled rather than partly labelled."
        )
        if strict:
            raise LabelUnavailable(message)
        report.warnings.append(message)
        # The share as a NUMBER. A caller applying a threshold should not have
        # to parse "matches 43% of observed codes" out of prose.
        report.partial_codelist_match[name] = round(float(share), 4)
        report.unlabelled.append(name)
        return _Selection(unlabelled=True)

    if picked and grain < _ROLLUP:
        # The best available table answers a coarser question than the column
        # asks — a municipality labelled with its health region.
        report.warnings.append(
            f"{name}: labelled from {picked!r}, which is a ROLLUP — it maps "
            f"the observed codes to {grain:.0%} as many distinct labels, so "
            f"the label is broader than the code. No finer table is bound."
        )
        report.rollup_used.append(name)
    elif picked and picked != candidates[0]:
        report.warnings.append(
            f"{name}: {tried} codelists are bound; chose {picked!r} "
            f"({share:.0%} of observed codes) over {candidates[0]!r}"
        )
    return _Selection(codelists=[picked] if picked else [], share=share)


def _report_reference_decisions(
    report: RenderReport,
    collected: dict[str, set],
    system: str,
    *,
    strict: bool,
) -> None:
    """Turn the reference layer's substitutions into report fields and warnings.

    Both are cases of "you were answered, but not with what you asked for", and
    both were invisible from the caller's side: a borrowed table produces
    confident labels from the wrong system, and a fallback vintage produces a
    label that may postdate the record. Neither shows up in the data.

    Extracted from render_table because it is a distinct decision — reference
    RESOLUTION, not column rendering — and because inline it was 40 lines in
    the middle of a 350-line function that already had six other jobs.
    """
    # A codelist served from another system's copy is reported, not silently
    # accepted. The contradiction check catches disagreement among overlapping
    # codes; a foreign table whose codes happen not to overlap produces
    # confident labels from the wrong system and nothing said so.
    for table_id, for_system in sorted(collected["borrowed"]):
        if for_system == (system or "").upper():
            report.warnings.append(
                f"{table_id}: no {for_system} copy of this codelist exists, so labels "
                f"were borrowed from another system's table"
            )
            report.borrowed.append(table_id)

    # Same treatment for the vintage. Asking for 1995 and being handed today's
    # table is a defensible answer and an undisclosed one; strict mode rejects
    # it, and everyone else at least gets told.
    for table_id, asked, served in sorted(collected["fallback"]):
        if served == "unresolved":
            report.warnings.append(
                f"{table_id}: no codelist window covers {asked} and there is no "
                "open-ended table, so nothing was labelled from it — rather than "
                "merging every historical window, which would contradict itself"
            )
        else:
            report.warnings.append(
                f"{table_id}: no codelist window covers {asked}, so the current "
                "vintage was used; a label here may postdate the record"
            )
        report.fallback_vintage[table_id] = served
        if strict:
            # strict means "the label I asked for or an error". A label from a
            # vintage the record predates is not the label that was asked for.
            raise LabelUnavailable(
                f"{table_id}: no codelist window covers {asked}"
                + (
                    "; nothing could be labelled from it"
                    if served == "unresolved"
                    else "; the current vintage would have been used, which may "
                    "postdate the record"
                )
            )


def render_table(
    table: pa.Table,
    *,
    store: Catalog,
    lake_root: str | Path,
    system: str,
    family_id: str | None = None,
    profile: str | RenderProfile = "analysis",
    render: Mapping[str, RenderMode] | None = None,
    headers: str | None = None,
    values: str | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    year: int | None = None,
    competencia: int | None = None,
    strict: bool = False,
) -> tuple[pa.Table, RenderReport]:
    """Apply every presentation decision, at read time, from the reference tables.

    ``strict`` turns a label that cannot be produced into a
    :class:`LabelUnavailable` instead of a warning. Either way the field is named
    — what never happens is unlabelled data coming back silently from a request
    for labels.
    """
    from .persist.reference import collecting

    # Every reference decision made inside this block belongs to THIS render.
    with collecting() as collected:
        return _render_table(
            table,
            store=store,
            lake_root=lake_root,
            system=system,
            family_id=family_id,
            profile=profile,
            render=render,
            headers=headers,
            values=values,
            companions=companions,
            derived=derived,
            year=year,
            competencia=competencia,
            strict=strict,
            collected=collected,
        )


def _render_table(
    table: pa.Table,
    *,
    store: Catalog,
    lake_root: str | Path,
    system: str,
    family_id: str | None = None,
    profile: str | RenderProfile = "analysis",
    render: Mapping[str, RenderMode] | None = None,
    headers: str | None = None,
    values: str | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    year: int | None = None,
    competencia: int | None = None,
    strict: bool = False,
    collected: dict[str, set] | None = None,
) -> tuple[pa.Table, RenderReport]:
    settings_profile = resolve_profile(
        profile, headers=headers, values=values, companions=companions, derived=derived
    )
    report = RenderReport()
    collected = collected if collected is not None else {"borrowed": set(), "fallback": set()}
    docs = load_variable_docs(store, system)
    bindings = _bindings(store, system, family_id)
    overrides = {k.upper(): v for k, v in (render or {}).items()}
    lake = Path(lake_root)

    base_columns = frozenset(
        n for n in table.schema.names if column_kind(n, frozenset(table.schema.names)) == "raw"
    )
    kinds = {n: column_kind(n, base_columns) for n in table.schema.names}

    columns: list[pa.Array] = []
    names: list[str] = []
    lookups: dict[tuple, dict[str, str]] = {}

    def _lookup(field_name: str, codelists: Sequence[str]) -> dict[str, str] | None:
        """Merge every table bound to this field. Exact width keeps them apart."""
        doc = docs.get(field_name)
        width = None
        if doc and doc.token_rule and not doc.multi_valued:
            width = doc.token_rule.get("width")
        # The key has to carry EVERYTHING the lookup below depends on. It was
        # just the codelist names, but the result is filtered by the field's
        # curated token width — so two fields sharing a codelist and needing
        # different widths shared a map built for whichever ran first. That
        # quietly undoes §6.2, the rule that keeps merged classifications of
        # different widths apart.
        key = (tuple(codelists), system, year, width)
        if key in lookups:
            return lookups[key] or None
        merged: dict[str, str] = {}
        missing: list[str] = []
        for codelist in codelists:
            try:
                # Later tables must not clobber a higher-authority one, so an
                # existing key wins.
                for code, label in _lookup_map(
                    lake,
                    codelist,
                    system=system,
                    year=year,
                    competencia=competencia,
                    code_width=width,
                ).items():
                    merged.setdefault(code, label)
            except FileNotFoundError:
                missing.append(codelist)
        if not merged:
            names = ", ".join(repr(c) for c in codelists)
            message = f"{field_name}: no reference table for {names} in the lake"
            if strict:
                raise LabelUnavailable(message)
            report.warnings.append(message)
            report.unlabelled.append(field_name)
        elif missing:
            report.warnings.append(
                f"{field_name}: labelled from {len(codelists) - len(missing)} of "
                f"{len(codelists)} bound tables; missing {', '.join(missing)}"
            )
        lookups[key] = merged
        return merged or None

    for name in table.schema.names:
        kind = kinds[name]
        column = table.column(name).combine_chunks()

        if kind == "label":
            # Labels are produced here, not read from storage. A stored one is a
            # build-time artefact of an older path and would shadow the join.
            continue

        if kind == "companion":
            keep = settings_profile.companions
            if isinstance(companions, (list, tuple, set)):
                keep = name in set(companions)
            if not keep:
                report.companions_dropped.append(name)
                continue
            columns.append(column)
            names.append(name)
            continue

        doc = docs.get(name.upper())
        selection = _select_codelists(
            name,
            column,
            doc=doc,
            candidates=list(bindings.get(name.upper()) or []),
            report=report,
            strict=strict,
            lookup_one=lambda cl, w: _single_lookup(lake, cl, system, year, w, competencia),
            store=store,
            system=system,
            family_id=family_id or "",
        )
        if selection.unlabelled:
            # Selection decided this column cannot be labelled and has already
            # said why. Emit it as filed.
            columns.append(column)
            names.append(name)
            continue
        codelists = selection.codelists
        codelist = codelists[0] if codelists else None
        code_system = (doc.code_system if doc else None) or ("internal" if codelist else "none")
        mode: RenderMode = overrides.get(name.upper()) or (
            settings_profile.internal if code_system == "internal" else
            settings_profile.external if code_system == "external" else "code"
        )

        if code_system == "none" or codelist is None or mode == "code":
            if mode != "code" and codelist is None and name.upper() in overrides:
                # An explicit request that cannot be honoured must say so.
                message = f"{name}: no codelist is bound, so no label can be produced"
                if strict:
                    raise LabelUnavailable(message)
                report.warnings.append(message)
                report.unlabelled.append(name)
            columns.append(column)
            names.append(name)
            continue

        lookup = _lookup(name.upper(), codelists)
        if lookup is None:
            columns.append(column)
            names.append(name)
            continue

        if doc and doc.multi_valued and doc.token_rule:
            rendered, code_lists, unmatched = _render_multi_valued(column, doc.token_rule, lookup)
            columns.append(column)
            names.append(name)
            columns.append(pa.array(rendered, type=pa.string()))
            names.append(f"{name}{LABEL_SUFFIX}")
            keep_companions = settings_profile.companions
            if isinstance(companions, (list, tuple, set)):
                keep_companions = f"{name}_codes" in set(companions)
            if keep_companions:
                columns.append(pa.array(code_lists, type=pa.list_(pa.string())))
                names.append(f"{name}_codes")
                columns.append(pa.array(unmatched, type=pa.int32()))
                names.append(f"{name}_unmatched")
            total_missing = sum(unmatched)
            if total_missing:
                report.tokens_unmatched[name] = total_missing
            report.labelled.append(name)
            report.codelist_used[name] = "+".join(codelists)
            continue

        width_warning = _check_width(name, "+".join(codelists), column, lookup)
        if width_warning:
            report.warnings.append(width_warning)

        # A table that disagrees with itself cannot render this column. Refusing
        # is the whole point: an unlabelled code is visibly unfinished, and a
        # confidently wrong label is not.
        observed = {str(v).strip() for v in column.to_pylist() if v is not None}
        try:
            disagreements = _contradictions(
                lake,
                codelists[0],
                system=system,
                year=year,
                competencia=competencia,
                code_width=None,
            )
        except FileNotFoundError:
            # A codelist bound but never materialised. That is a labelling gap
            # for this one column, already reported where the lookup was built —
            # not grounds to fail the whole request. Letting it escape meant a
            # single unmaterialised table made every SINAN dataset unfetchable:
            # `fetch("SINAN-DENG")` died on AGRAVNET while 200 other columns
            # were sitting there ready to be returned.
            disagreements = {}
        ambiguous = {
            code: labels for code, labels in disagreements.items() if code in observed
        }
        if ambiguous:
            example = next(iter(sorted(ambiguous)))
            message = (
                f"{name}: codelist {codelists[0]!r} maps {len(ambiguous)} observed code(s) "
                f"to more than one label — {example!r} means "
                f"{sorted(ambiguous[example])}. Not labelled; the sources disagree."
            )
            if strict:
                raise LabelUnavailable(message)
            report.warnings.append(message)
            report.unlabelled.append(name)
            columns.append(column)
            names.append(name)
            continue
        labels = _labels_for(column, lookup)
        matched = int(pc.sum(pc.is_valid(labels)).as_py() or 0)
        if not matched:
            if len(observed) <= 1:
                # See above: one value throughout is a dead column, not a gap.
                report.constant[name] = next(iter(observed), "")
                report.unlabelled.append(name)
                columns.append(column)
                names.append(name)
                continue
            message = f"{name}: reference table {codelist!r} matched none of the observed codes"
            if strict:
                raise LabelUnavailable(message)
            report.warnings.append(message)
            report.unlabelled.append(name)
            columns.append(column)
            names.append(name)
            continue

        report.labelled.append(name)
        report.codelist_used[name] = "+".join(codelists)
        if name in report.rollup_used:
            # A ROLL-UP is not this column's identity. `CODMUNRES` bound only to
            # `CIRAC` decodes 100% of its values and returns "Baixo Acre e
            # Purus" for a municipality code — a region name wearing a
            # municipality's name. Coverage cannot tell the two apart, so the
            # broader answer is emitted as its own dimension beside the code
            # rather than in place of it, and the code stays what it is.
            columns.append(column)
            names.append(name)
            rollup_name = f"{name}_{selection.codelists[0].lower()}" if selection.codelists else f"{name}_rollup"
            columns.append(labels)
            names.append(rollup_name)
            report.derived_added.append(rollup_name)
            continue
        if mode == "label":
            columns.append(labels)
            names.append(name)
        elif mode == "combined" or settings_profile.values == "combined":
            columns.append(_combine(column, labels))
            names.append(name)
        else:  # "both"
            columns.append(column)
            names.append(name)
            columns.append(labels)
            names.append(f"{name}{LABEL_SUFFIX}")

    _report_reference_decisions(report, collected, system, strict=strict)

    rendered_table = pa.Table.from_arrays(columns, names=names)

    if settings_profile.derived:
        rendered_table = _apply_derived(
            rendered_table, table, docs, bindings, lake, year, derived, report, store,
            system, competencia,
        )

    if settings_profile.headers != "original":
        before_headers = list(rendered_table.schema.names)
        rendered_table = _apply_headers(rendered_table, docs, settings_profile.headers)
        report.renamed_headers.update(
            {new: old for old, new in zip(before_headers, rendered_table.schema.names, strict=True)
             if new != old}
        )

    if settings_profile.values == "combined" and settings_profile.name == "report":
        report.warnings.append(
            "values='combined' produces a reading format: the result cannot be "
            "filtered, joined or aggregated on"
        )
    # ONE warning, not one per finding. A wide dataset with many unresolved or
    # ambiguous columns produced a wall of them — slow to emit and hostile in a
    # notebook, and it trained people to filter the channel entirely. The
    # structured report is the carrier; this is the pointer to it.
    if report.warnings:
        head = report.warnings[0]
        rest = len(report.warnings) - 1
        warnings.warn(
            head + (f" (+{rest} more in RenderReport.warnings)" if rest else ""),
            stacklevel=2,
        )
    return rendered_table, report


def _apply_derived(
    rendered: pa.Table,
    source: pa.Table,
    docs: Mapping[str, VariableDoc],
    bindings: Mapping[str, list[str]],
    lake: Path,
    year: int | None,
    wanted: bool | Sequence[str] | None,
    report: RenderReport,
    store: Catalog,
    system: str,
    competencia: int | None = None,
) -> pa.Table:
    """Add the columns that resolve multi-column semantics into one usable value.

    Driven by ``depends_on``/``derived`` in the variable dictionary, so what can
    be derived is a statement in a curated file rather than a rule in the source.
    """
    requested = set(wanted) if isinstance(wanted, (list, tuple, set)) else None
    for doc in docs.values():
        for recipe in doc.derived or []:
            column_name = str(recipe.get("name") or "")
            if not column_name or column_name in rendered.schema.names:
                continue
            if requested is not None and column_name not in requested:
                continue
            inputs = [str(c).upper() for c in (recipe.get("from") or [])]
            if len(inputs) != 2:
                continue
            absent = [c for c in inputs if c not in source.schema.names]
            if absent:
                # SAY SO. A caller who explicitly asked for this derived column
                # and used a narrow columns= projection got no column and no
                # explanation, because its inputs were never read. Silence here
                # is indistinguishable from "this derivation does not exist".
                if requested is not None and column_name in requested:
                    report.warnings.append(
                        f"{column_name}: cannot be derived because "
                        f"{', '.join(absent)} was not loaded — add it to columns= "
                        f"(it is dropped again unless you asked for it)"
                    )
                continue
            unit_column = inputs[1]
            bound = bindings.get(unit_column) or []
            codelist = bound[0] if bound else (
                docs[unit_column].codelist if unit_column in docs else None
            )
            if not codelist:
                report.warnings.append(
                    f"{column_name}: {unit_column} has no codelist, so its units cannot be read"
                )
                continue
            try:
                divisors = _unit_divisors(
                    _lookup_map(
                        lake,
                        codelist,
                        system=system,
                        year=year,
                        competencia=competencia,
                        code_width=None,
                    )
                )
            except FileNotFoundError:
                report.warnings.append(
                    f"{column_name}: no reference table {codelist!r} for the unit column"
                )
                continue
            if not divisors:
                report.warnings.append(
                    f"{column_name}: no label in {codelist!r} names a time unit, so "
                    f"{inputs[0]} cannot be converted"
                )
                continue
            derived_column = _derive_age_years(source, inputs[0], unit_column, divisors)
            if derived_column is None:
                continue
            rendered = rendered.append_column(column_name, derived_column)
            report.derived_added.append(column_name)
    return rendered


def _apply_headers(
    table: pa.Table, docs: Mapping[str, VariableDoc], style: str
) -> pa.Table:
    """Rename columns for a human reader.

    Off by default and documented as a one-way door: renamed headers break
    scripts, joins and every downstream reference, and accented names cause
    friction in SQL and in some Parquet readers. Fine for a deliverable someone
    reads; a poor choice for a pipeline stage.
    """
    names: list[str] = []
    for name in table.schema.names:
        base = name[: -len(LABEL_SUFFIX)] if name.endswith(LABEL_SUFFIX) else name
        doc = docs.get(base.upper())
        translated = (doc.translated_name if doc else None) or (
            doc.official_name if doc else None
        )
        if not translated:
            names.append(name)
            continue
        if name.endswith(LABEL_SUFFIX):
            translated = f"{translated} (label)"
        names.append(translated if style == "translated" else f"{name} ({translated})")
    return table.rename_columns(names)
