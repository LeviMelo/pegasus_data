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
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import pyarrow as pa
import pyarrow.compute as pc

from .catalog.store import CatalogStore
from .config import curation_root
from .lookups import (
    _check_width,
    _contradictions,
    _distinct,
    _exists_anywhere,
    _labels_for,
    _merged_lookup,
    _per_distinct,
    _single_lookup,
    contiguous,
    dictionary_of,
    expand,
)
from .normalize.time import parse_date_array, year_bounds
from .persist.reference import collecting, read_reference_table
from .semantics.curation import VariableDoc, form_types_a_date, is_coded, load_variable_docs, read_yaml
from .semantics.label_bindings import (
    _bindings,
    _family_series,
    _key_columns,
    candidates_for,
    compose_key,
    decide,
)

if TYPE_CHECKING:
    from ._age import AgeDimension

RenderMode = Literal["code", "label", "both"]

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


PROFILES: dict[str, RenderProfile] = {
    # The default. Every code keeps its raw value and gains a `_label`
    # companion. It used to REPLACE internal codes in place (MORTE "0" became
    # "Sem óbito"), which discarded the raw value (CLAUDE.md §6) and made the
    # shape of a column depend on which kind of codelist it happened to have.
    "analysis": RenderProfile("analysis", internal="both"),
    # Nothing rendered: the lake as stored, for a pipeline stage that will do its
    # own joining and wants no surprises.
    "codes": RenderProfile(
        "codes", internal="code", external="code", companions=False, derived=False
    ),
    # Everything visible at once, including the internal codes the analysis
    # profile hides, so a disagreement can be traced back to what was stored.
    "audit": RenderProfile("audit", internal="both", external="both"),
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
    #: The `report` profile does, and it is the CLI's default, so anything built
    #: from the rendered table afterwards — the data dictionary — would look up
    #: "Mother's age" in curation, find nothing, and describe nothing.
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
    #: Where the rows came from, as a fetch says it (`retrieve.FetchReport.source_facts`): source file -> (family, year,
    #: competence YYYYMM or None), filled by ``query`` from the lake partitions it read, so one interface serves both
    #: paths. ``origin`` is ``"lake"`` there (a `FetchReport` says ``"fetch"``).
    source_facts: dict[str, tuple[str | None, int | None, int | None]] = field(default_factory=dict)
    origin: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "origin": self.origin,
            "source_facts": {k: list(v) for k, v in self.source_facts.items()},
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


def drop_helper_columns(table: pa.Table, helpers: Iterable[str]) -> pa.Table:
    """``table`` without the columns that were read only so another could be rendered (``required_columns``), and
    without their labels and companions. ``helpers`` are upper-case names the caller did not ask for."""
    gone = {str(h).upper() for h in helpers}
    if not gone:
        return table
    suffixes = (LABEL_SUFFIX, *COMPANION_SUFFIXES)
    keep = [
        name for name in table.column_names
        if name.upper() not in gone
        and not any(name.endswith(s) and name[: -len(s)].upper() in gone for s in suffixes)
    ]
    return table if len(keep) == len(table.column_names) else table.select(keep)


def codelist_levels(
    field: str,
    *,
    store: CatalogStore,
    lake_root: str | Path,
    system: str,
    family_id: str | None = None,
    year: int | None = None,
    competencia: int | None = None,
    codes: Sequence[str] | None = None,
    registries: str | Path | None = None,
) -> dict[str, str]:
    """``code -> label`` for one field's ``codes``, without a table of records to apply it to.

    The capability descriptor has to tell a client that ``SEXO`` takes ``1`` and ``3`` and what those mean, and a
    study has to name the group its finding is in. The codes are rendered as a one-column table by `render_table`, so a
    level named here and the same level in a cell cannot disagree: the same ladder of evidence chooses the table (the
    form's own dictionary, curated tables, measured weighing; `label_bindings.decide`). This used to merge every table
    bound to the field, first wins, and named SINAN-TOXG's outcome 2 "Óbito por meningite" (meningitis's table)
    where a query says "Óbito pelo agravo notificado" (2026-10-11).

    ``codes`` are the values present (``DIAG_PRINC`` binds ~14,000 ICD codes; a control offering them all for an
    artifact holding 40 is a lie about the data); without them nothing is labelled. A code the chosen tables do not
    decode is absent from the result: unknown, never guessed.
    """
    wanted = sorted({str(c).strip() for c in codes or () if c is not None and str(c).strip()})
    if not wanted:
        return {}
    rendered, _ = render_table(pa.table({field: pa.array(wanted, pa.string())}), store=store, lake_root=lake_root,
                               system=system, family_id=family_id, profile="analysis", companions=[field],
                               derived=False, year=year, competencia=competencia, registries=registries)
    if f"{field}{LABEL_SUFFIX}" not in rendered.column_names:
        return {}
    labels = rendered.column(f"{field}{LABEL_SUFFIX}").to_pylist()
    return {c: lbl for c, lbl in zip(rendered.column(field).to_pylist(), labels, strict=True) if lbl}


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


def _strip_code(label: str, code: str) -> str:
    """A label without a leading copy of its own code ("I64 Acidente…" -> "Acidente…")."""
    head, _, rest = label.partition(" ")
    plain = lambda x: "".join(ch for ch in x if ch.isalnum()).upper()  # noqa: E731
    return rest.strip(" -–") if rest and plain(head) == plain(code) else label


def _render_multi_valued(
    column: pa.Array | pa.ChunkedArray, rule: Mapping[str, Any], lookup: Mapping[str, str]
) -> tuple[pa.ChunkedArray, pa.ChunkedArray, pa.ChunkedArray]:
    """Label every token, keep the order, and never drop one: (labels, the codes of each cell, the misses per cell),
    each a ChunkedArray built in pieces (`lookups.expand`), so a column of any size is rendered.

    A token with no match passes through as its raw code. Dropping it would make
    a shorter causal chain than the physician wrote, and nulling the whole cell
    would discard the tokens that *did* resolve. Each distinct cell is rendered
    once and the rows take theirs: a pass per row over a year of births' anomaly
    lists (583,191 cells, 1,658 distinct) was most of a labelled query (2026-10-11).
    """
    # a null cell is an entry of its own (no label, no codes, no miss), so every row has an index to take
    cells, idx = dictionary_of(column, null_encoding="encode")
    distinct = cells.to_pylist()
    rendered: list[str | None] = []
    code_lists: list[list[str]] = []
    unmatched: list[int] = []
    for value in distinct:
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
                # Kept, and visibly undecoded (ADR-0086).
                misses += 1
                pieces.append(f"{token} (?)")
            else:
                pieces.append(f"{_strip_code(label, token)} ({token})")
        rendered.append(TOKEN_JOIN.join(pieces) if pieces else None)
        code_lists.append(tokens)
        unmatched.append(misses)
    # the tokens of a cell are pieces of it, so a cell's own bytes bound its list of codes
    widest_cell = max((len(str(c).encode()) for c in distinct if c is not None), default=0)
    return (expand(pa.array(rendered, type=pa.string()), idx),
            expand(pa.array(code_lists, type=pa.list_(pa.string())), idx, widest=widest_cell),
            expand(pa.array(unmatched, type=pa.int32()), idx))


def resolve_profile(
    profile: str | RenderProfile = "analysis",
    *,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
) -> RenderProfile:
    """A named profile with any explicit override applied on top."""
    base = profile if isinstance(profile, RenderProfile) else PROFILES.get(str(profile))
    if base is None:
        raise KeyError(f"unknown render profile {profile!r}; known: {sorted(PROFILES)}")
    changes: dict[str, Any] = {}
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


def _lookup_key(
    table: pa.Table, doc: object, column: pa.Array | pa.ChunkedArray,
) -> pa.Array | pa.ChunkedArray | None:
    """The column's own values, or the concatenation its curated ``key:`` names; None when the key names a column the
    table lacks. Falling back to the column alone matched it against a different key of the same codelist (CLASS_SR
    against S_CLASSEN's SERV_ESP + CLASS_SR): the column is left undecoded and the report says why."""
    key = getattr(doc, "key", None) if doc is not None else None
    return compose_key(table, key) if key else column


def _label_via(
    lake: Path, system: str, keys: object, via: Mapping[str, str], registries: Path | None = None,
) -> pa.ChunkedArray | None:
    """The ``field`` of ``table``'s row for each value of ``column`` (ADR-0094), a ChunkedArray built in pieces
    (`lookups.expand`): the registry's names for every row of a large table are more than one array holds."""
    try:
        table = read_reference_table(lake, str(via["table"]), system=system, registries=registries)
    except (FileNotFoundError, KeyError):
        return None
    field_name = str(via.get("field") or "label")
    if field_name not in table.column_names:
        return None
    # A join in Arrow: the registry has 692,004 rows, and building a Python
    # dict of it per month group cost 25 s of a year's query (2026-09-29).
    wanted = pc.utf8_trim_whitespace(pc.cast(pa.chunked_array([keys]) if isinstance(keys, pa.Array) else keys, pa.string()))
    at = pc.index_in(wanted, value_set=pc.cast(table.column("code"), pa.string()))
    return expand(pc.cast(table.column(field_name), pa.string()), at)


def _bridge_declarations() -> tuple[dict[str, str], dict[str, tuple[str, int]], float]:
    """A recipe's short names for bridges, the classification and code width each lands in, and the share of the evidence
    a claim must hold to cross, as `codelists.yml` declares them (``bridges:``)."""
    declared = (read_yaml(curation_root() / "codelists.yml") or {})["bridges"]
    targets = {str(k): (str(v["classification"]), int(v["width"])) for k, v in declared["targets"].items()}
    return {str(k): str(v) for k, v in declared["names"].items()}, targets, float(declared["unique"])


@lru_cache(maxsize=1)
def _bridges() -> dict[tuple[str, str], tuple[tuple[str, float], ...]]:
    """``(bridge, old code) -> ((new code, strength), …)``, strongest first."""
    from importlib.resources import files

    import pyarrow.parquet as _pq

    try:
        table = _pq.read_table(str(files("pegasus_data.resources") / "bridges.parquet"))
    except (FileNotFoundError, OSError):
        return {}
    out: dict[tuple[str, str], list[tuple[str, float]]] = {}
    for bridge, old, new, strength in zip(
        table["bridge"].to_pylist(), table["old_code"].to_pylist(),
        table["new_code"].to_pylist(), table["strength"].to_pylist(), strict=True,
    ):
        out.setdefault((str(bridge), str(old)), []).append((str(new), float(strength)))
    return {k: tuple(sorted(v, key=lambda x: -x[1])) for k, v in out.items()}


def bridged(codes: object, bridge: str) -> pa.Array:
    """Each code in the classification that replaced its own (ADR-0101, ADR-0104).

    A code already of the target's width is itself. A code of the replaced
    classification crosses when one claim holds for the declared ``unique`` share of the
    evidence (the official link, or the share of professionals DATASUS moved);
    otherwise it stays null rather than choosing.
    """
    names, targets, unique = _bridge_declarations()
    name = names.get(bridge.upper(), bridge.upper())
    _target, width = targets.get(name, ("", 0))
    table = _bridges()

    def one(v: object) -> str | None:
        code = str(v).strip()
        if width and len(code) == width:
            return code
        claims = table.get((name, code), ())
        return claims[0][0] if claims and claims[0][1] >= unique else None

    empty = table.get((name, ""), ())
    out = _per_distinct(codes, one)
    if empty and empty[0][1] >= unique:   # a null read as "" before; keep that
        out = pc.fill_null(out, empty[0][0])
    return out


def bridge_target(bridge: str) -> str:
    """The classification a bridge lands in (SIGTAP, CBO2002)."""
    names, targets, _unique = _bridge_declarations()
    return targets.get(names.get(bridge.upper(), bridge.upper()), ("SIGTAP", 0))[0]


def _names_of(table: pa.Table, wanted: Sequence[object]) -> dict[str, str]:
    """``code -> label`` of the table's rows for the codes in ``wanted``, the last row of a code winning.

    A dict of the whole classification was built for every group of a month: 0.69 s of MUNICBR's rows each, 8.2 s of a
    12-month query that labelled 205 rows. The groups ask for a few dozen codes.
    """
    strings = sorted({v for v in wanted if isinstance(v, str)})
    if not strings:
        return {}
    column = pc.cast(table.column("code"), pa.string())
    hit = table.filter(pc.is_in(column, value_set=pa.array(strings, pa.string())))
    return dict(zip(hit.column("code").to_pylist(), hit.column("label").to_pylist(), strict=True))


def _labelled_codes(lake: Path, classification: str, codes: object, *, as_code: bool = False) -> pa.Array | None:
    """``label (code)`` from a canonical classification, or None where unknown.

    ``as_code`` gives the code alone, for the codes presentation.
    """
    try:
        table = read_reference_table(lake, classification)
    except FileNotFoundError:
        return None
    if as_code:
        return _per_distinct(codes, lambda v: v or None)
    names = _names_of(table, _distinct(codes))
    return _per_distinct(codes, lambda v: f"{names[v]} ({v})" if v in names else (f"{v} (?)" if v else None))


def _hierarchy_level(lake: Path, classification: str, digits: int, codes: object,
                     *, as_code: bool = False) -> pa.Array | None:
    """``label (prefix)`` for the first ``digits`` of each code, or None if unknown.

    ``as_code`` gives the prefix alone, still only where the classification
    lists it, for the codes presentation.
    """
    if digits <= 0:
        return None
    try:
        table = read_reference_table(lake, classification)
    except FileNotFoundError:
        return None
    names = _names_of(table, [str(v).strip()[:digits] for v in _distinct(codes)])

    def one(v: object) -> str | None:
        prefix = str(v).strip()[:digits]
        label = names.get(prefix) if len(prefix) == digits else None
        if as_code:
            return prefix if label else None
        return f"{label} ({prefix})" if label else None

    return _per_distinct(codes, one)


def _coded(doc: object) -> bool:
    """The curation says this column holds codes (not numbers, dates or text)."""
    return doc is not None and is_coded(getattr(doc, "code_system", None))


def _select_codelists(
    name: str,
    column: pa.ChunkedArray,
    *,
    doc: object,
    candidates: list[str],
    report: RenderReport,
    strict: bool,
    lookup_one: Callable[[str, int | None], Mapping[str, str] | None],
    store: CatalogStore | None = None,
    system: str = "",
    family_id: str = "",
    vintage: int | None = None,
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
    # One ladder of evidence, shared with compile_bindings (ADR-0082).

    series = _family_series(store, family_id)
    # Counted in Arrow, then trimmed: a year of a file is a million cells and a few dozen distinct codes (ADR-0097), so
    # the distinct values are trimmed and merged, not every cell (trimming each cell first took 200 s of a link year's
    # 654, 2026-10-09)
    tallied = pc.value_counts(column if pa.types.is_string(column.type) or pa.types.is_large_string(column.type)
                              else pc.cast(column, pa.string()))
    counts: Counter = Counter()
    for value, n in zip(tallied.field("values").to_pylist(), tallied.field("counts").to_pylist(), strict=True):
        text = None if value is None else str(value).strip()
        if text:
            counts[text] += n
    seen = set(counts)
    decision = decide(
        system=system, family_id=family_id, series=series, field_name=name, doc=doc,
        candidates=candidates, counts=counts, load=lambda cl: lookup_one(cl, None),
        store=store, vintage=vintage, persist=False,
    )
    if decision.basis == "curated" and decision.codelists:
        return _Selection(codelists=list(decision.codelists), share=decision.share)
    candidates = candidates_for(doc, candidates)
    if not decision.labels:
        if candidates or decision.reason != "no codelist is bound to this field":
            if len(seen) <= 1 and seen:
                # One value in every row and nothing decodes it: a dead column,
                # not a labelling failure. Recorded in both, as before.
                report.constant[name] = next(iter(seen))
            message = f"{name}: {decision.reason}"
            if strict and candidates:
                raise LabelUnavailable(message)
            if candidates:
                report.warnings.append(message)
            if decision.share is not None:
                report.partial_codelist_match[name] = float(decision.share)
            report.unlabelled.append(name)
            return _Selection(unlabelled=True)
        return _Selection()
    picked = decision.codelists[0]
    if len(candidates) > 1 and picked != str(candidates[0]).upper():
        report.warnings.append(
            f"{name}: {decision.candidates} codelists weighed; {picked!r} ({decision.reason})"
        )
    return _Selection(codelists=list(decision.codelists), share=decision.share)


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
    store: CatalogStore,
    lake_root: str | Path,
    system: str,
    family_id: str | None = None,
    profile: str | RenderProfile = "analysis",
    render: Mapping[str, RenderMode] | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    year: int | None = None,
    competencia: int | None = None,
    strict: bool = False,
    registries: str | Path | None = None,
) -> tuple[pa.Table, RenderReport]:
    """Apply every presentation decision, at read time, from the reference tables.

    ``registries`` is the root in use's ``Settings.registries_dir``: the establishment and team names are read from
    there (OQ 81); without it a registry-coded column is reported unlabelled, never read from the default home.

    ``strict`` turns a label that cannot be produced into a
    :class:`LabelUnavailable` instead of a warning. Either way the field is named
    — what never happens is unlabelled data coming back silently from a request
    for labels.

    **Size.** No column is flattened into one array, and a column built row by row (a label for every row) is built in
    pieces (`lookups.expand`, `lookups.PIECE_BYTES`), so a table of any length renders: Arrow's ``string`` addresses
    2 GiB of characters per array, and the labels of 58.6 million rows (SNGPC-IND 2014's ``TP_RECEITUARIO``) are 2.3 GB.
    Types do not depend on the size: ``X`` and ``X_label`` are ``string`` in a result of ten rows and of ten billion;
    only the number of chunks of a column grows. The labels are decided once over the value counts of all the rows
    given (`_select_codelists`), then applied to every piece, so they do not depend on how the column was cut.
    """
    table = placed_companions(table)
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
            companions=companions,
            derived=derived,
            year=year,
            competencia=competencia,
            strict=strict,
            collected=collected,
            registries=registries,
        )


def placed_companions(table: pa.Table) -> pa.Table:
    """Each ``<base>_ibge7`` companion as the one placing rule reads its base (`geography.place_municipalities`): the
    municipality's IBGE code, Brasília's for its administrative regions and the declared legacy codes, null for a code
    that names none. Normalisation wrote it by the check-digit algorithm, which turned an unknown six-digit code into a
    plausible seven-digit one (the second audit, S1); it is corrected here, where every read passes, so the lake's
    partitions need no rebuild."""
    import pyarrow.compute as pc

    from .geography import place_municipalities

    for name in [n for n in table.column_names if n.endswith("_ibge7") and n[: -len("_ibge7")] in table.column_names]:
        base = pc.cast(table.column(name[: -len("_ibge7")]), pa.string())
        codes = pc.dictionary_encode(base).combine_chunks()
        placed = pa.array([None if c is None else str(c) for c in place_municipalities(codes.dictionary.to_pylist())],
                          pa.string())
        table = table.set_column(table.schema.get_field_index(name), name, pc.take(placed, codes.indices))
    return table


@dataclass
class _RenderContext:
    """What every column's rendering reads, and the report and memo it writes: one render's shared state."""

    table: pa.Table
    store: CatalogStore
    system: str
    family_id: str | None
    lake: Path
    registry_home: Path | None
    year: int | None
    competencia: int | None
    strict: bool
    settings_profile: RenderProfile
    overrides: dict[str, RenderMode]
    companions: bool | Sequence[str] | None
    docs: Mapping[str, VariableDoc]
    series: Any
    bindings: Mapping[str, Any]
    kinds: dict[str, str]
    codes_only: bool
    report: RenderReport
    lookups: dict[tuple, Mapping[str, str]] = field(default_factory=dict)


_Emitted = list[tuple[str, Any]]


def _lookup(
    ctx: _RenderContext, field_name: str, codelists: Sequence[str], only: frozenset[str] | None = None,
) -> Mapping[str, str] | None:
    """Merge every table bound to this field. Exact width keeps them apart."""
    # No width filter. Exact string matching already keeps classifications of
    # different widths apart (§6.2); filtering the TABLE to the curated token
    # width as well dropped every legitimate code of another width. SIH's
    # DIAG_PRINC is curated at width 4 and holds 3-character CID-10
    # categories (I64, J18, I10) beside 4-character subcategories: 13% of
    # AL 2023-01 admissions came back unlabelled (live run 2026-09-28).
    width = None
    # The key has to carry EVERYTHING the lookup below depends on. It was
    # just the codelist names, but the result is filtered by the field's
    # curated token width — so two fields sharing a codelist and needing
    # different widths shared a map built for whichever ran first. That
    # quietly undoes §6.2, the rule that keeps merged classifications of
    # different widths apart.
    key = (tuple(codelists), ctx.system, ctx.year, width, only)
    if key in ctx.lookups:
        return ctx.lookups[key] or None
    merged, missing = _merged_lookup(
        ctx.lake, tuple(codelists), ctx.system, ctx.year, ctx.competencia, only, ctx.registry_home)
    if not merged:
        names = ", ".join(repr(c) for c in codelists)
        message = f"{field_name}: no reference table for {names} in the lake"
        if ctx.strict:
            raise LabelUnavailable(message)
        ctx.report.warnings.append(message)
        ctx.report.unlabelled.append(field_name)
    elif missing:
        # A table with no version for this period is not missing: ICD-9's
        # chapter files end in 1997, and every SIH query of 2022 warned that
        # seventeen of them were "missing" (2026-09-30). Only a table that
        # exists in no window at all is worth saying.
        absent = [c for c in missing if not _exists_anywhere(Path(ctx.lake), c, ctx.registry_home)]
        if absent:
            ctx.report.warnings.append(
                f"{field_name}: labelled from {len(codelists) - len(missing)} of "
                f"{len(codelists)} bound tables; no version at all of {', '.join(absent)}"
            )
    if merged:
        merged = _within_code_windows(ctx, field_name, codelists, merged)
    ctx.lookups[key] = merged
    return merged or None


def _declared_code_windows() -> dict[str, dict[str, str]]:
    """``codelists.yml`` ``code_windows``: the codelists whose codes carry their own validity windows."""
    return {str(k): {kk: str(vv) for kk, vv in v.items()} for k, v in
            ((read_yaml(curation_root() / "codelists.yml") or {}).get("code_windows") or {}).items()}


@lru_cache(maxsize=8)
def _code_windows(registry_home: str, registry: str, file: str, code: str) -> tuple[dict[str, tuple[int, int]], int]:
    """``code -> (first, last)`` of one declared window table, the newest export's codes open-ended, and the first
    competência it can judge. Empty when the table is not built."""
    import pyarrow.parquet as _pq

    path = Path(registry_home) / registry / file
    if not path.is_file():
        return {}, 0
    rows = _pq.read_table(path, columns=[code, "first", "last"]).to_pylist()
    newest = max(int(r["last"]) for r in rows)
    return ({str(r[code]): (int(r["first"]), 999912 if int(r["last"]) == newest else int(r["last"])) for r in rows},
            min(int(r["first"]) for r in rows))


def _within_code_windows(ctx: _RenderContext, field_name: str, codelists: Sequence[str],
                         merged: Mapping[str, str]) -> Mapping[str, str]:
    """``merged`` without the codes that did not exist in the period read, for every bound codelist ``codelists.yml``
    declares dated code by code (`code_windows`): a label is joined by validity window (ARCHITECTURE invariant), and
    SIH's PROC_REA labelled mechanical thrombectomy in 2015, a procedure SIGTAP lists from 202312. A code outside its
    window is undecoded, visibly, and the report counts it; periods before the table's first competência are not
    judged. Which columns this applies to is what they are bound to, never the shape of their codes."""
    if ctx.registry_home is None or (ctx.year is None and ctx.competencia is None):
        return merged
    declared = _declared_code_windows()
    bound = [name for name in codelists if name in declared]
    if not bound:
        return merged
    lo, hi = ((int(ctx.competencia), int(ctx.competencia)) if ctx.competencia
              else (int(ctx.year) * 100 + 1, int(ctx.year) * 100 + 12))  # type: ignore[arg-type]
    gone: set[str] = set()
    for name in bound:
        spec = declared[name]
        windows, first_known = _code_windows(str(ctx.registry_home), spec["registry"], spec["file"], spec.get("code", "code"))
        if not windows or hi < first_known:
            continue
        gone |= {code for code in merged if code in windows and not (windows[code][0] <= hi and lo <= windows[code][1])}
    if not gone:
        return merged
    example = sorted(gone)[0]
    ctx.report.warnings.append(
        f"{field_name}: {len(gone)} code(s) of {', '.join(bound)} did not exist in {lo}-{hi} and are left undecoded "
        f"(e.g. {example})")
    return {code: label for code, label in merged.items() if code not in gone}


def _undecoded(name: str, column: Any, doc: Any, *, with_label: bool = True) -> _Emitted:
    """The column as filed, with an empty label companion when the curation says it is coded (ADR-0085/0086)."""
    out: _Emitted = [(name, column)]
    if with_label and _coded(doc):
        out.append((f"{name}{LABEL_SUFFIX}", pa.nulls(len(column), type=pa.string())))
    return out


def _refused(ctx: _RenderContext, name: str, message: str) -> None:
    """Record that ``name`` could not be labelled (or raise under ``strict``)."""
    if ctx.strict:
        raise LabelUnavailable(message)
    ctx.report.warnings.append(message)
    ctx.report.unlabelled.append(name)


def _companion_column(ctx: _RenderContext, name: str) -> _Emitted:
    """A stored companion column: kept or dropped by the profile or by the caller's list."""
    keep = ctx.settings_profile.companions
    if isinstance(ctx.companions, (list, tuple, set)):
        keep = name in set(ctx.companions)
    if not keep:
        ctx.report.companions_dropped.append(name)
        return []
    return [(name, ctx.table.column(name))]


def _sibling_label(ctx: _RenderContext, name: str, column: Any, sibling: str) -> _Emitted:
    """The record names its own code (ADR-0090): the sibling column is the label."""
    named = pc.utf8_trim(ctx.table.column(sibling).cast(pa.string()), characters=" ")
    named = pc.if_else(pc.equal(named, ""), pa.scalar(None, pa.string()), named)
    ctx.report.labelled.append(name)
    ctx.report.codelist_used[name] = f"column {sibling}"
    return [(name, column), (f"{name}{LABEL_SUFFIX}", named)]


def _label_via_column(ctx: _RenderContext, name: str, column: Any, doc: Any) -> _Emitted | None:
    """The label read through another column (an establishment's name by its code), or None when it does not apply."""
    via = getattr(doc, "label_via", None) if doc is not None else None
    # ``column`` may list candidates: one variable, several layouts (SIA BI
    # names its establishment CODUNI, PS names it CNES_EXEC).
    via_columns = via.get("column", []) if via else []
    via_column = next(
        (str(c).upper() for c in (via_columns if isinstance(via_columns, list) else [via_columns])
         if str(c).upper() in ctx.table.schema.names),
        None,
    )
    if not (via and via_column):
        return None
    named_via = _label_via(ctx.lake, ctx.system, ctx.table.column(via_column), via, ctx.registry_home)
    if named_via is None:
        return None
    # The field's own tables first: they name THIS value exactly (a
    # CNPJ's own legal name, a documented "zeros: no maintainer").
    # The row's establishment's maintainer fills what they leave.
    own = [c for c in (doc.codelist, *doc.codelists) if c] if doc is not None else []
    own_lookup = _lookup(ctx, name.upper(), own) if own else None
    if own_lookup:
        named_via = pc.coalesce(_labels_for(column, own_lookup), named_via)
    ctx.report.labelled.append(name)
    ctx.report.codelist_used[name] = f"{via.get('table')}.{via.get('field')} via {via_column}"
    return [(name, column), (f"{name}{LABEL_SUFFIX}", named_via)]


def _is_not_coded(ctx: _RenderContext, name: str, doc: Any) -> bool:
    """The curation says the column is not coded, or the family's form dictionary types it a date."""
    # The curation says this column is not coded (a date, a count, an
    # identifier), or the family's own form dictionary types it a date. A kit .DEF may still bind it to a table (DT_SAIDA to
    # ANOMES), and weighing that table against its values warned "no
    # bound table decodes the column" on every SIH and SIM query
    # (2026-09-30). The curation's word is the stronger evidence.
    return doc is not None and (
        (getattr(doc, "code_system", None) == "none" and not getattr(doc, "codes", None))
        or bool(ctx.series and form_types_a_date(ctx.system, ctx.series, name))
    )


def _not_coded_column(ctx: _RenderContext, name: str, column: Any) -> _Emitted:
    """A column that is not coded, as filed; an explicit request for its label is answered with a warning."""
    if ctx.overrides.get(name.upper(), "code") != "code":
        # But an explicit request that cannot be honoured must say so.
        _refused(ctx, name, f"{name}: not a coded column (curation: code_system none), so no label can be produced")
    return [(name, column)]


def _multi_valued_columns(
    ctx: _RenderContext, name: str, column: Any, doc: Any, codelists: list[str], lookup: Mapping[str, str],
) -> _Emitted:
    """A column holding several codes: the code, its labels, and the optional code-list and unmatched companions."""
    rendered, code_lists, unmatched = _render_multi_valued(column, doc.token_rule, lookup)
    out: _Emitted = [(name, column), (f"{name}{LABEL_SUFFIX}", rendered)]
    keep_companions = ctx.settings_profile.companions
    if isinstance(ctx.companions, (list, tuple, set)):
        keep_companions = f"{name}_codes" in set(ctx.companions)
    if keep_companions:
        out.append((f"{name}_codes", code_lists))
        out.append((f"{name}_unmatched", unmatched))
    total_missing = int(pc.sum(unmatched).as_py() or 0)
    if total_missing:
        ctx.report.tokens_unmatched[name] = total_missing
    ctx.report.labelled.append(name)
    ctx.report.codelist_used[name] = "+".join(codelists)
    return out


def _disagreements(ctx: _RenderContext, codelists: list[str]) -> dict[str, set[str]]:
    """Codes that a bound table maps to more than one label, over every table the merged lookup draws from."""
    # A table that disagrees with itself cannot render this column. Refusing
    # is the whole point: an unlabelled code is visibly unfinished, and a
    # confidently wrong label is not.
    try:
        disagreements: dict[str, set[str]] = {}
        for bound in codelists:
            # Every table the merged lookup draws from, not just the
            # first: a self-contradictory SECOND table was never checked,
            # and its labels reached the merge all the same.
            for code, found in _contradictions(
                ctx.lake,
                bound,
                system=ctx.system,
                year=ctx.year,
                competencia=ctx.competencia,
                code_width=None,
                registries=ctx.registry_home,
            ).items():
                disagreements.setdefault(code, set()).update(found)
    except FileNotFoundError:
        # A codelist bound but never materialised. That is a labelling gap
        # for this one column, already reported where the lookup was built —
        # not grounds to fail the whole request. Letting it escape meant a
        # single unmaterialised table made every SINAN dataset unfetchable:
        # `fetch("SINAN-DENG")` died on AGRAVNET while 200 other columns
        # were sitting there ready to be returned.
        disagreements = {}
    return disagreements


def _labelled_columns(
    ctx: _RenderContext, name: str, column: Any, doc: Any, key_column: Any, selection: _Selection,
    codelist: str, mode: RenderMode,
) -> _Emitted:
    """Apply the chosen codelists to a column: the label, the refusals (contradiction, no match) and the roll-up case."""
    codelists = selection.codelists
    observed = {str(v).strip() for v in _distinct(key_column)}
    multi = bool(doc and doc.multi_valued and doc.token_rule)
    lookup = _lookup(ctx, name.upper(), codelists, None if multi else frozenset(observed))
    if lookup is None:
        return [(name, column)]

    if doc and doc.multi_valued and doc.token_rule:
        return _multi_valued_columns(ctx, name, column, doc, codelists, lookup)

    width_warning = _check_width(name, "+".join(codelists), key_column, lookup)
    if width_warning:
        ctx.report.warnings.append(width_warning)

    ambiguous = {
        code: labels for code, labels in _disagreements(ctx, codelists).items() if code in observed
    }
    if ambiguous:
        example = next(iter(sorted(ambiguous)))
        _refused(ctx, name, (
            f"{name}: codelist {codelists[0]!r} maps {len(ambiguous)} observed code(s) "
            f"to more than one label — {example!r} means "
            f"{sorted(ambiguous[example])}. Not labelled; the sources disagree."
        ))
        return [(name, column)]
    labels = _labels_for(key_column, lookup)
    matched = int(pc.sum(pc.is_valid(labels)).as_py() or 0)
    if not matched:
        if len(observed) <= 1:
            # See above: one value throughout is a dead column, not a gap.
            ctx.report.constant[name] = next(iter(observed), "")
            ctx.report.unlabelled.append(name)
            return _undecoded(name, column, doc)  # visibly undecoded, not a plain value (ADR-0086)
        _refused(ctx, name, f"{name}: reference table {codelist!r} matched none of the observed codes")
        return _undecoded(name, column, doc)

    ctx.report.labelled.append(name)
    ctx.report.codelist_used[name] = "+".join(codelists)
    if name in ctx.report.rollup_used:
        # A ROLL-UP is not this column's identity. `CODMUNRES` bound only to
        # `CIRAC` decodes 100% of its values and returns "Baixo Acre e
        # Purus" for a municipality code — a region name wearing a
        # municipality's name. Coverage cannot tell the two apart, so the
        # broader answer is emitted as its own dimension beside the code
        # rather than in place of it, and the code stays what it is.
        rollup_name = f"{name}_{selection.codelists[0].lower()}" if selection.codelists else f"{name}_rollup"
        ctx.report.derived_added.append(rollup_name)
        return [(name, column), (rollup_name, labels)]
    if mode == "label":
        return [(name, labels)]
    return [(name, column), (f"{name}{LABEL_SUFFIX}", labels)]  # "both"


def _coded_column(ctx: _RenderContext, name: str, column: Any, doc: Any) -> _Emitted:
    """Choose the codelists for a column that may be coded and render it by the profile's mode."""
    report = ctx.report
    key_column = _lookup_key(ctx.table, doc, column)
    if key_column is None:
        absent = _key_columns(ctx.table, doc.key)[1]
        _refused(ctx, name, (
            f"{name}: its codelist is keyed by {' + '.join(doc.key)} and {', '.join(absent)} is not in "
            "the table, so the column is left undecoded (its own values would match a different key)"
        ))
        return _undecoded(name, column, doc)
    selection = _select_codelists(
        name,
        key_column,
        doc=doc,
        candidates=list(ctx.bindings.get(name.upper()) or []),
        report=report,
        strict=ctx.strict,
        lookup_one=lambda cl, w: _single_lookup(
            ctx.lake, cl, ctx.system, ctx.year, w, ctx.competencia, ctx.registry_home),
        store=ctx.store,
        system=ctx.system,
        family_id=ctx.family_id or "",
        vintage=ctx.competencia if ctx.competencia is not None else ctx.year,
    )
    if selection.unlabelled:
        # Selection decided this column cannot be labelled and has already
        # said why. Emit it as filed, with an EMPTY label companion when the
        # curation says the column is coded, so the presentation shows its
        # codes as undecoded ("9 (?)") rather than as plain values (ADR-0085).
        return _undecoded(name, column, doc)
    codelists = selection.codelists
    codelist = codelists[0] if codelists else None
    code_system = (doc.code_system if doc else None) or ("internal" if codelist else "none")
    profile = ctx.settings_profile
    mode: RenderMode = ctx.overrides.get(name.upper()) or (
        profile.internal if code_system == "internal" else
        profile.external if code_system == "external" else "code"
    )

    if code_system == "none" or codelist is None or mode == "code":
        if (codelist is None and code_system in ("internal", "external")
                and name not in report.unlabelled):
            # Curation says this column IS coded; nothing is bound to
            # decode it. The unlabelled list is the machine-readable form
            # of "visibly unfinished" -- without it the column reverted to
            # raw codes with no trace anywhere in the report.
            report.unlabelled.append(name)
        if mode != "code" and codelist is None and name.upper() in ctx.overrides:
            # An explicit request that cannot be honoured must say so.
            _refused(ctx, name, f"{name}: no codelist is bound, so no label can be produced")
        # Coded, and nothing decodes it: visibly undecoded (ADR-0085).
        return _undecoded(name, column, doc, with_label=mode != "code" and codelist is None)
    return _labelled_columns(ctx, name, column, doc, key_column, selection, codelist, mode)


def _render_column(ctx: _RenderContext, name: str) -> _Emitted:
    """The output column(s) one stored column becomes: nothing, the column as filed, or the column with its label."""
    kind = ctx.kinds[name]
    if kind == "label":
        # Labels are produced here, not read from storage. A stored one is a
        # build-time artefact of an older path and would shadow the join.
        return []
    if kind == "companion":
        return _companion_column(ctx, name)

    # A column is read as the ChunkedArray it is, never flattened into one array: past 2 GiB of characters a
    # `string` cannot be one (`lookups.PIECE_BYTES`), and a column that passes through unchanged (a 58.6-million-row
    # SNGPC-IND year's `_source_path` is 5.4 GB) is not copied for being kept. The table is assembled below with
    # each column that fits one array made one (`contiguous`), as every column always was.
    column = ctx.table.column(name)

    if ctx.codes_only or ctx.overrides.get(name.upper()) == "code":
        # a column asked for as filed: no codelist chosen for it (a role table reads labels of five of its
        # eighteen SIH columns; labelling all of them was 31-48 s of a state-year against 4-9 s, 2026-10-11)
        return [(name, column)]

    doc = ctx.docs.get(name.upper())
    sibling = getattr(doc, "label_from", None) if doc is not None else None
    if sibling and sibling in ctx.table.schema.names:
        return _sibling_label(ctx, name, column, sibling)
    via_out = _label_via_column(ctx, name, column, doc)
    if via_out is not None:
        return via_out
    # The value a table is keyed by. Usually the column itself; for a code
    # that only means something with another column (CNES CLASS_SR, keyed
    # by SERV_ESP + CLASS_SR in S_CLASSEN), the concatenation (ADR-0088).
    if _is_not_coded(ctx, name, doc):
        return _not_coded_column(ctx, name, column)
    if name.startswith("_"):
        # the record's bookkeeping (row number, source file, record key): never coded. Weighed against every
        # codelist, `_row`'s 583,191 distinct values were most of a labelled SINASC SP year (2026-10-11)
        return [(name, column)]
    return _coded_column(ctx, name, column, doc)


def _with_label_companions(
    columns: list[Any], names: list[str], docs: Mapping[str, VariableDoc],
) -> tuple[list[Any], list[str]]:
    """THE INVARIANT (ADR-0086): a column the curation says is coded leaves with a label companion, null where nothing
    decoded it, so the presentation shows "9 (?)" instead of a bare code that reads like a value. Enforced once here
    rather than in each of the rendering's refusal branches."""
    present_names = set(names)
    final_columns: list[Any] = []
    final_names: list[str] = []
    for col, col_name in zip(columns, names, strict=True):
        final_columns.append(col)
        final_names.append(col_name)
        label_name = f"{col_name}{LABEL_SUFFIX}"
        if (not col_name.endswith(LABEL_SUFFIX) and label_name not in present_names
                and _coded(docs.get(col_name.upper()))):
            final_columns.append(pa.nulls(len(col), type=pa.string()))
            final_names.append(label_name)
    return final_columns, final_names


def _render_table(
    table: pa.Table,
    *,
    store: CatalogStore,
    lake_root: str | Path,
    system: str,
    family_id: str | None = None,
    profile: str | RenderProfile = "analysis",
    render: Mapping[str, RenderMode] | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    year: int | None = None,
    competencia: int | None = None,
    strict: bool = False,
    collected: dict[str, set] | None = None,
    registries: str | Path | None = None,
) -> tuple[pa.Table, RenderReport]:
    settings_profile = resolve_profile(
        profile, companions=companions, derived=derived
    )
    report = RenderReport()
    collected = collected if collected is not None else {"borrowed": set(), "fallback": set()}
    docs = load_variable_docs(store, system)
    series = _family_series(store, family_id or "")
    # the bindings are the catalog's, the same for every group of a family: read once per catalog state
    bindings = store.memo(("bindings", system, family_id or ""), lambda: _bindings(store, system, family_id))
    overrides = {k.upper(): v for k, v in (render or {}).items()}
    lake = Path(lake_root)
    registry_home = None if registries is None else Path(registries)

    base_columns = frozenset(
        n for n in table.schema.names if column_kind(n, frozenset(table.schema.names)) == "raw"
    )
    kinds = {n: column_kind(n, base_columns) for n in table.schema.names}

    # When every column will be emitted as its stored code -- the `codes`
    # profile with no per-column override asking for more -- codelist selection
    # has no bearing on the output at all: whatever it decides, the branch below
    # renders the column as filed. Selection is nevertheless the expensive part
    # of rendering (it reads reference tables and weighs every binding against
    # the observed values), and `fetch(labels=False)` runs through here once per
    # file. Measured on one state-year of SIH-RD: 205 of a 209-second fetch was
    # selection whose result was then discarded.
    codes_only = (
        settings_profile.internal == "code"
        and settings_profile.external == "code"
        and all(mode == "code" for mode in overrides.values())
    )

    ctx = _RenderContext(
        table=table, store=store, system=system, family_id=family_id, lake=lake, registry_home=registry_home,
        year=year, competencia=competencia, strict=strict, settings_profile=settings_profile,
        overrides=overrides, companions=companions, docs=docs, series=series, bindings=bindings, kinds=kinds,
        codes_only=codes_only, report=report,
    )
    columns: list[pa.Array | pa.ChunkedArray] = []
    names: list[str] = []
    for name in table.schema.names:
        for out_name, out_column in _render_column(ctx, name):
            names.append(out_name)
            columns.append(out_column)

    _report_reference_decisions(report, collected, system, strict=strict)

    if not codes_only:
        columns, names = _with_label_companions(columns, names, docs)
    rendered_table = pa.Table.from_arrays([contiguous(c) for c in columns], names=names)

    # A derived column the caller names is built under every profile. The codes
    # profile turned derived columns off, so `select=["PROC_REA_grupo"]` with
    # present="codes" came back as an all-null column, which reads like data
    # (2026-10-03). There it carries the code: the group "04", not its label.
    named = isinstance(derived, (list, tuple, set)) and bool(derived)
    if settings_profile.derived or named:
        rendered_table = _apply_derived(
            rendered_table, table, docs, bindings, lake, year, derived, report, store,
            system, competencia, as_code=codes_only,
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


def _remapped(codes: object, recipe: Mapping[str, Any], *, year: int | None, competencia: int | None,
              report: RenderReport) -> pa.Array:
    """``codes`` through the recipe's ``remap`` (exact codes) and ``ranges`` (a declared range of codes to one code) where
    its ``valid`` window (YYYYMM) holds; with ``municipalities_only`` a code that ends as no IBGE municipality is null and
    said in the report.

    The window is judged by the file's competence; a year alone decides only when the whole
    year is inside or outside it. Where it cannot be settled the code stays as written and
    the report says so: an unremapped code is visibly the source's own, a guess is not.
    """
    table = {str(k): str(v) for k, v in dict(recipe["remap"] or {}).items()}
    # a declared range of codes that all stand for one (SINAN writes the Federal District's 53xxxx region codes where
    # Brasília, its one municipality, is 530010; DATASUS's own AGLBR and BR_CAPITAL tables map 530000-539999 to it)
    ranges = [(str(r["from"]), str(r["to"]), str(r["code"])) for r in recipe.get("ranges") or ()]
    only = None
    if recipe.get("municipalities_only"):
        from .geography import municipalities

        only = set(municipalities())

    def mapped(value: Any) -> str | None:
        code = str(value).strip()
        if not code:
            return None
        out = table.get(code)
        if out is None:
            out = next((target for lo_, hi_, target in ranges if len(code) == len(lo_) and lo_ <= code <= hi_), code)
        if only is not None and out not in only:
            unplaced[code] = unplaced.get(code, 0) + 1
            return None
        return out

    unplaced: dict[str, int] = {}
    window = recipe.get("valid") or {}
    lo, hi = int(window.get("from") or 0), int(window.get("to") or 999912)
    applies = None
    if competencia is not None:
        applies = lo <= int(competencia) <= hi
    elif year is not None:
        first, last = year_bounds(year)
        applies = True if lo <= first and last <= hi else False if last < lo or first > hi else None
    if applies is None:
        report.warnings.append(
            f"{recipe.get('name')}: the window {lo}-{hi} cuts the year read, so the codes stand as written")
    if not applies:
        return _per_distinct(codes, lambda v: str(v).strip() or None)
    out = _per_distinct(codes, mapped)
    if unplaced:
        # a code no municipality list holds (a state with its municipality unknown, ``350000``) is null here, never
        # guessed; the raw column keeps it
        report.warnings.append(f"{recipe.get('name')}: {len(unplaced)} distinct codes are no IBGE municipality and are null "
                               f"(first {sorted(unplaced)[:5]}); the raw column keeps them")
    return out


def _apply_derived(
    rendered: pa.Table,
    source: pa.Table,
    docs: Mapping[str, VariableDoc],
    bindings: Mapping[str, list[str]],
    lake: Path,
    year: int | None,
    wanted: bool | Sequence[str] | None,
    report: RenderReport,
    store: CatalogStore,
    system: str,
    competencia: int | None = None,
    *,
    as_code: bool = False,
) -> pa.Table:
    """Add the columns that resolve multi-column semantics into one usable value.

    Driven by ``depends_on``/``derived`` in the variable dictionary, so what can
    be derived is a statement in a curated file rather than a rule in the source.
    """
    # Names compare case-insensitively: the planner upper-cases `select`.
    requested = {str(w).upper() for w in wanted} if isinstance(wanted, (list, tuple, set)) else None
    for doc in docs.values():
        for recipe in doc.derived or []:
            column_name = str(recipe.get("name") or "")
            if not column_name or column_name in rendered.schema.names:
                continue
            if requested is not None and column_name.upper() not in requested:
                continue
            inputs = [str(c).upper() for c in (recipe.get("from") or [])]
            if not inputs:
                continue
            # an input null-filled for a layout that does not carry it is absent: a system may hold one derived
            # name with a recipe per layout (SIA's IDADE_anos from AP_NUIDADE in the APACs, from IDADEPAC elsewhere),
            # and the recipe that applies is the one whose inputs this layout has
            absent = [c for c in inputs if c not in source.schema.names
                      or (source.num_rows and source.column(c).null_count == source.num_rows
                          and pa.types.is_null(source.column(c).type))]
            if absent and any(
                    all(str(x).upper() in source.schema.names and not pa.types.is_null(source.column(str(x).upper()).type)
                        for x in (other.get("from") or []))
                    for d in docs.values() for other in (d.derived or [])
                    if str(other.get("name") or "") == column_name and other is not recipe):
                continue                        # another recipe of this name applies to this layout
            if absent:
                # SAY SO. A caller who explicitly asked for this derived column
                # and used a narrow columns= projection got no column and no
                # explanation, because its inputs were never read. Silence here
                # is indistinguishable from "this derivation does not exist".
                if requested is not None and column_name.upper() in requested:
                    report.warnings.append(
                        f"{column_name}: cannot be derived because "
                        f"{', '.join(absent)} was not loaded — add it to columns= "
                        f"(it is dropped again unless you asked for it)"
                    )
                continue
            bridge = recipe.get("bridge")
            codes_in = source.column(inputs[0])
            if recipe.get("date"):
                # A date the source writes as 8-digit text (DDMMYYYY in SIM and SINASC), as a
                # date beside the raw column. A value that is not a calendar date is null here
                # and still there in the raw column.

                order = str(recipe["date"])
                if order not in ("YYYYMMDD", "DDMMYYYY"):
                    report.warnings.append(f"{column_name}: unknown date order {order!r}")
                    continue
                rendered = rendered.append_column(column_name, parse_date_array(codes_in, order=order))
                report.derived_added.append(column_name)
                continue
            if recipe.get("remap") is not None or recipe.get("ranges"):
                # A code the source wrote for a thing the canonical list names otherwise,
                # inside a declared window (SIH-RD before 2018 writes the Federal District's
                # administrative regions where Brasília is 530010). The raw column is untouched;
                # outside the window, or where the window is not settled, the code stands.
                rendered_codes = _remapped(codes_in, recipe, year=year, competencia=competencia, report=report)
                derived_column = None if as_code else _labelled_codes(
                    lake, str(recipe.get("to") or "MUNICBR"), rendered_codes)
                if derived_column is None:
                    derived_column = rendered_codes
                rendered = rendered.append_column(column_name, derived_column)
                report.derived_added.append(column_name)
                continue
            if bridge:
                # Across the 2008 change of classification: an old SIA/SIH
                # procedure becomes the SIGTAP procedure that replaced it, when
                # exactly one did (ADR-0101).
                codes_in = bridged(codes_in, str(bridge))
            hierarchy = recipe.get("hierarchy")
            if bridge and not hierarchy:
                derived_column = _labelled_codes(lake, str(recipe.get("to") or bridge_target(str(bridge))), codes_in,
                                                 as_code=as_code)
                if derived_column is not None:
                    rendered = rendered.append_column(column_name, derived_column)
                    report.derived_added.append(column_name)
                continue
            if hierarchy:
                # A level of a hierarchical classification as its own dimension:
                # PROC_REA's SIGTAP group, "Procedimentos cirurgicos (04)", which
                # is what "was this a surgery" means (ADR-0092).
                derived_column = _hierarchy_level(
                    lake, str(hierarchy), int(recipe.get("digits") or 0), codes_in, as_code=as_code
                )
                if derived_column is not None:
                    rendered = rendered.append_column(column_name, derived_column)
                    report.derived_added.append(column_name)
                continue
            # One age converter for the whole package (`_age.years_column`),
            # chosen by the encoding the recipe declares. This used to read the
            # unit column's LABELS for words like "meses" and divide, a second
            # converter that disagreed with the aggregate path's and produced
            # nothing when the unit column had no codelist (SIH's COD_IDADE).
            derived_column = _age_years(recipe, column_name, inputs, source)
            if derived_column is None:
                from ._age import FORMS as AGE_FORMS

                report.warnings.append(
                    f"{column_name}: the curated recipe declares no age form "
                    f"(age: {{form: {'|'.join(AGE_FORMS)}}}), so it cannot be derived"
                )
                continue
            rendered = rendered.append_column(column_name, derived_column)
            report.derived_added.append(column_name)
    return rendered


def _age_years(recipe: Mapping[str, Any], name: str, inputs: Sequence[str], source: pa.Table) -> Any:
    """The age a curated recipe declares, in fractional years, made from ``source``'s raw columns by the one converter
    (`_age.years_column`); None when the recipe declares no age (``age: {form: ...}``). A band's ``lookup`` is the
    recipe's own table, beside its form."""
    from ._age import parse_age, years_column

    body = recipe.get("age")
    if not isinstance(body, dict):
        return None
    body = {**body, "lookup": body.get("lookup") or recipe.get("lookup")}
    return years_column(cast("AgeDimension", parse_age(body, tuple(inputs), name=name)), source)


def derived_age_years(docs: Mapping[str, VariableDoc], name: str, source: pa.Table) -> Any:
    """The derived age column ``name`` (IDADE_anos) of ``source``, a table of raw columns, made as rendering makes it
    (`_apply_derived`: the recipe whose inputs this layout carries, the one converter): fractional years, null where
    the age is undecodable. None when no recipe of that name has its inputs in ``source``, or it is no age."""
    for doc in docs.values():
        for recipe in doc.derived or []:
            if str(recipe.get("name") or "").upper() != name.upper():
                continue
            inputs = [str(c).upper() for c in (recipe.get("from") or [])]
            if inputs and all(c in source.schema.names and not pa.types.is_null(source.column(c).type) for c in inputs):
                return _age_years(recipe, name, inputs, source)
    return None


