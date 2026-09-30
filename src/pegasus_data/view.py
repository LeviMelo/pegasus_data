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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.compute as pc

from .catalog.store import Catalog
from .identifiers import ID_PREFIX
from .persist.reference import read_reference_table
from .semantics.curation import VariableDoc, load_variable_docs

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


def clear_lookup_caches() -> None:
    """Forget every code->label map derived from the lake's reference tables.

    The maps below are cached for the life of the process, which is only sound
    while the tables they were built from stand still. Anything that installs
    or rewrites ``lake/reference/`` -- the reference build stage, the first-use
    materialisation inside ``fetch``, a bundle unpacked mid-process -- must
    call this, or the process keeps labelling from the tables it saw first.
    """
    _cached_lookup_map.cache_clear()
    _cached_contradictions.cache_clear()
    _cached_merged_lookup.cache_clear()
    _MAPS_BY_CONTENT.clear()


# Cached for the life of the process, like the packed reads underneath: a
# monthly dataset asks for the same map twelve times per fetch. Callers
# treat the returned dict as read-only; mutating it would poison the cache.
@lru_cache(maxsize=512)
def _reference_version(lake_root: Path, codelist: str) -> tuple[int, ...]:
    """What a reference table's content depends on, as file times.

    The lake's copy of the table and any registry cache of that name. Shipped
    canonical tables change only with the package, so they need no stamp.
    """
    import re as _re

    from .config import load_settings

    stamps: list[int] = []
    lake_copy = Path(lake_root) / "reference" / _re.sub(r"[^A-Za-z0-9_.-]", "_", codelist)
    if lake_copy.exists():
        stamps.append(lake_copy.stat().st_mtime_ns)
    try:
        registries = Path(load_settings().root) / "registries"
        stamps.extend(p.stat().st_mtime_ns for p in sorted(registries.glob(f"*/{codelist.upper()}.parquet")))
    except OSError:  # pragma: no cover - an unreadable home is not a cache key
        pass
    return tuple(stamps)


def _vintage_free(codelist: str) -> bool:
    """Is this table one version for every year?

    Canonical classifications, registries and curated inline codes are read
    before any vintage filter (``read_reference_table``), so asking for them
    per month only multiplied cache misses: 492 rebuilds in a year's query.
    """
    from .persist.reference import CLASSIFICATIONS
    from .registry import is_registry
    from .semantics.curation import inline_codelist

    name = codelist.upper()
    return (
        name in CLASSIFICATIONS or name in ("UF_BR", "CIR_BR") or is_registry(name)
        or inline_codelist(codelist) is not None
    )


def _lookup_map(
    lake_root: Path,
    codelist: str,
    *,
    system: str | None,
    year: int | None,
    competencia: int | None = None,
    code_width: int | None,
) -> Mapping[str, str]:
    """``_lookup_map_uncached``, built once per process per table version.

    A year of monthly files renders as twelve groups, and each rebuilt the same
    maps: 7 of a 17-second one-month query was reading and re-reading reference
    tables (profiled 2026-09-29), the 692,004-row establishment registry among
    them. Callers only read the result.
    """
    if _vintage_free(codelist):
        year = competencia = None
    return _cached_lookup_map(
        str(lake_root), codelist, system, year, competencia, code_width,
        _reference_version(Path(lake_root), codelist),
    )


@lru_cache(maxsize=256)
def _cached_lookup_map(
    lake_root: str, codelist: str, system: str | None, year: int | None,
    competencia: int | None, code_width: int | None, version: tuple[int, ...],
) -> Mapping[str, str]:
    return _lookup_map_uncached(
        Path(lake_root), codelist, system=system, year=year, competencia=competencia, code_width=code_width
    )


def _contradictions(
    lake_root: Path,
    codelist: str,
    *,
    system: str | None,
    year: int | None,
    competencia: int | None = None,
    code_width: int | None,
) -> Mapping[str, set[str]]:
    """``_contradictions_uncached``, cached like ``_lookup_map``."""
    if _vintage_free(codelist):
        year = competencia = None
    return _cached_contradictions(
        str(lake_root), codelist, system, year, competencia, code_width,
        _reference_version(Path(lake_root), codelist),
    )


@lru_cache(maxsize=256)
def _cached_contradictions(
    lake_root: str, codelist: str, system: str | None, year: int | None,
    competencia: int | None, code_width: int | None, version: tuple[int, ...],
) -> Mapping[str, set[str]]:
    return _contradictions_uncached(
        Path(lake_root), codelist, system=system, year=year, competencia=competencia, code_width=code_width
    )


def _lookup_map_uncached(
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
    # A vintaged kit table asked for month by month is usually the same table
    # twelve times: built once per distinct content (ADR-0097).
    digest = _content_digest(table)
    known = _MAPS_BY_CONTENT.get((codelist, digest))
    if known is not None:
        return known
    built = _map_from_table(table)
    if len(_MAPS_BY_CONTENT) > 512:
        _MAPS_BY_CONTENT.clear()
    _MAPS_BY_CONTENT[(codelist, digest)] = built
    return built


#: ``(codelist, content digest) -> code -> label`` (see ``_lookup_map_uncached``).
_MAPS_BY_CONTENT: dict[tuple[str, bytes], dict[str, str]] = {}


def _content_digest(table: pa.Table) -> bytes:
    """A digest of a reference table's codes and labels, from Arrow's buffers."""
    import hashlib

    h = hashlib.blake2b(digest_size=16)
    for name in ("code", "label"):
        column = pc.cast(table.column(name), pa.string()).combine_chunks()
        h.update(str(len(column)).encode())
        for buffer in column.buffers():
            if buffer is not None:
                h.update(memoryview(buffer))
    return h.digest()


def _map_from_table(table: pa.Table) -> dict[str, str]:
    """``code -> label``: last line wins, and blank labels are dropped."""
    # Nulls and blanks are dropped in Arrow, before 700,000 registry rows
    # become Python strings; order is kept, so the dict below still lets the
    # last line win.
    codes = pc.cast(table.column("code"), pa.string())
    labels = pc.cast(table.column("label"), pa.string())
    # No CNPJ or CPF inside a label (ADR-0102): DATASUS's registry tables glue
    # them onto names, CPFs of sole practitioners among them.
    labels = pc.replace_substring_regex(labels, pattern=ID_PREFIX.pattern, replacement="")
    keep = pc.and_(
        pc.and_(pc.is_valid(codes), pc.is_valid(labels)),
        pc.not_equal(pc.utf8_trim_whitespace(labels), ""),
    )
    codes = pc.filter(codes, keep).to_pylist()
    labels = pc.filter(labels, keep).to_pylist()
    # Last write wins, matching .CNV semantics, where a later line deliberately
    # overrides an earlier one. A blank label is dropped rather than stored: an
    # empty string is not a translation, and offering one turns a labelled column
    # into a column of nothing while still reporting that it was labelled. This
    # is how CADMUN behaved — a DBF lookup that picked OBSERV as its label
    # column, which is blank for 5,517 of its 5,579 rows.
    return dict(zip(codes, labels, strict=True))


def codelist_levels(
    field: str,
    *,
    store: Catalog,
    lake_root: str | Path,
    system: str,
    family_id: str | None = None,
    year: int | None = None,
    competencia: int | None = None,
    codes: Sequence[str] | None = None,
) -> dict[str, str]:
    """``code -> label`` for one field, without a table to apply it to.

    The capability descriptor has to tell a client that ``SEXO`` takes ``1`` and
    ``3`` and what those mean, so the client can draw a control. Everything
    needed already lives in this module: :func:`_bindings` chooses which
    codelists are bound to the field, and :func:`_lookup_map` reads the
    version-scoped reference table for each. This composes them and adds
    nothing, so a level rendered in a control and the same level rendered in a
    cell cannot disagree.

    ``codes`` narrows the result to values actually present. That matters more
    than it saves: ``DIAG_PRINC`` binds a table of ~14,000 ICD codes, and a
    control offering 14,000 levels for an artifact that contains 40 of them is a
    lie about the data. Passing the observed codes makes the descriptor describe
    THIS artifact rather than the classification in the abstract.

    Higher authority wins on collision, matching :func:`_bindings`' own ordering.
    """
    bindings = _bindings(store, system, family_id)
    codelists = bindings.get(field) or []
    if not codelists:
        return {}
    docs = load_variable_docs(store, system)
    doc = docs.get(field)
    width = None
    if doc and doc.token_rule and not doc.multi_valued:
        width = doc.token_rule.get("width")
    merged: dict[str, str] = {}
    for codelist in codelists:
        try:
            mapping = _lookup_map(
                Path(lake_root), codelist, system=system, year=year,
                competencia=competencia, code_width=width,
            )
        except FileNotFoundError:
            continue
        for code, label in mapping.items():
            merged.setdefault(code, label)
    if codes is None:
        return merged
    wanted = {str(c).strip() for c in codes}
    return {c: lbl for c, lbl in merged.items() if c in wanted}


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


# Same contract as _lookup_map: cached, and the returned mapping is shared.
def _contradictions_uncached(
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
    # In Arrow, not per row: the registries hold 700,000 codes and almost none
    # contradict, so only the few that do are brought into Python.
    pairs = table.select(["code", "label"]).cast(
        pa.schema([("code", pa.string()), ("label", pa.string())])
    )
    pairs = pairs.filter(pc.and_(pc.is_valid(pairs["code"]), pc.is_valid(pairs["label"])))
    counted = pairs.group_by("code").aggregate([("label", "count_distinct")])
    multi = counted.filter(pc.greater(counted["label_count_distinct"], 1))["code"]
    if not len(multi):
        return {}
    clash = pairs.filter(pc.is_in(pairs["code"], value_set=multi))
    seen: dict[str, set[str]] = {}
    for code, label in zip(clash["code"].to_pylist(), clash["label"].to_pylist(), strict=True):
        seen.setdefault(code, set()).add(label)
    return seen


class CodeMap(dict):  # type: ignore[type-arg]
    """A merged ``code -> label`` map that knows its code widths (§6.2)."""

    widths: frozenset[int] = frozenset()


def _merged_lookup(
    lake: Path, codelists: tuple[str, ...], system: str | None, year: int | None, competencia: int | None,
) -> tuple[Mapping[str, str], list[str]]:
    """Every table bound to a field, merged in authority order, once per process.

    It was rebuilt for every render group, and a group is a month: merging the
    692,004-row registry twelve times was 16 million ``setdefault`` calls in a
    year's query (ADR-0097). Tables with no vintages drop the year from the key.
    """
    if all(_vintage_free(c) for c in codelists):
        year = competencia = None
    versions = tuple(_reference_version(Path(lake), c) for c in codelists)
    return _cached_merged_lookup(str(lake), codelists, system, year, competencia, versions)


@lru_cache(maxsize=512)
def _cached_merged_lookup(
    lake: str, codelists: tuple[str, ...], system: str | None, year: int | None,
    competencia: int | None, versions: tuple[tuple[int, ...], ...],
) -> tuple[Mapping[str, str], list[str]]:
    missing: list[str] = []
    maps: list[Mapping[str, str]] = []
    for codelist in codelists:
        try:
            maps.append(_lookup_map(
                Path(lake), codelist, system=system, year=year, competencia=competencia, code_width=None,
            ))
        except FileNotFoundError:
            missing.append(codelist)
    merged: dict[str, str]
    if len(maps) == 1:
        merged = CodeMap(maps[0])
    else:
        # Later tables must not clobber a higher-authority one: the first wins.
        merged = CodeMap()
        for mapping in reversed(maps):
            merged.update(mapping)
    if any(str(c).upper() == "ICD10" for c in codelists):
        # ICD-10 is a defined hierarchy: a subcategory the classification does
        # not list still belongs to its category (ADR-0089).
        merged = IcdLabels(merged)
    elif any(str(c).upper() == "SIGTAP" for c in codelists):
        merged = SigtapLabels(merged)
    elif len(codelists) == 1 and str(codelists[0]).upper() in PATH_CODELISTS:
        name = str(codelists[0]).upper()
        merged = PathLabels(merged, table=name, segment=PATH_CODELISTS[name])
    merged.widths = frozenset(len(code) for code in merged)  # type: ignore[attr-defined]
    return merged, missing


def _widths(lookup: Mapping[str, str]) -> set[int]:
    known = getattr(lookup, "widths", None)
    return set(known) if known else {len(code) for code in lookup}


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
           -- A binding inferred from value overlap alone is a guess, not a
           -- source: it bound SIA's OPC_PRIPAL (a procedure) to municipalities
           -- and SIH's CEP to procedures (ADR-0091).
           AND source <> 'semantic_match'
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
                # Kept, and visibly undecoded (ADR-0086).
                misses += 1
                pieces.append(f"{token} (?)")
            else:
                pieces.append(f"{_strip_code(label, token)} ({token})")
        rendered.append(TOKEN_JOIN.join(pieces) if pieces else None)
        code_lists.append(tokens)
        unmatched.append(misses)
    return rendered, code_lists, unmatched


class IcdLabels(dict):  # type: ignore[type-arg]
    """ICD-10 labels that fall back from a subcategory to its category.

    SIM writes ``R969`` and ``I100``: subcategories CID-10 does not list (R96
    and I10 are not subdivided). The category still says what the death was.
    The label says so rather than passing the category off as the code:
    "Hipertensão essencial (primária) — categoria I10 (subcategoria I10.0 não
    consta da CID-10)". Only for ICD-10, whose hierarchy is defined: a prefix of
    a CBO code is not its parent (§6.2).
    """

    def get(self, key: object, default: object = None) -> object:
        found = super().get(key)
        if found is not None:
            return found
        code = str(key).strip().upper()
        if len(code) == 4 and code[:3].isalnum() and code[3] != "X":
            category = super().get(code[:3]) or super().get(f"{code[:3]}X")
            if category is not None:
                return (
                    f"{category} — categoria {code[:3]} "
                    f"(subcategoria {code[:3]}.{code[3]} não consta da CID-10)"
                )
        return default


class SigtapLabels(dict):  # type: ignore[type-arg]
    """SIGTAP labels that fall back from a procedure to its form, subgroup, group.

    A 10-digit procedure missing from the table (created after the kit, or
    retired before it) still belongs to its form of organisation (6 digits),
    subgroup (4) and group (2): "Parto — forma 041101 (procedimento 0411019999
    não consta da tabela SIGTAP)". The canonical SIGTAP table carries every
    level, so the parents are in this mapping (ADR-0092).
    """

    _LEVELS = ((6, "forma de organização"), (4, "subgrupo"), (2, "grupo"))

    def get(self, key: object, default: object = None) -> object:
        found = super().get(key)
        if found is not None:
            return found
        code = str(key).strip()
        if len(code) == 10 and code.isdigit():
            for width, name in self._LEVELS:
                parent = super().get(code[:width])
                if parent is not None:
                    return f"{parent} — {name} {code[:width]} (procedimento {code} não consta da tabela SIGTAP)"
        return default


class PathLabels(dict):  # type: ignore[type-arg]
    """Labels of a code built from fixed-width levels, spelled out as a path.

    CNES ``VINCULO`` keys a professional's employment bond by three 2-digit
    levels and labels each code with its path: ``080501`` = "08 INTERMEDIADO /
    05 AUTONOMO / 01 PESSOA JURIDICA". A code the table does not list
    (``080701``) is named by the deepest level a listed code shares, and the
    label says which levels are undocumented: "08 INTERMEDIADO — nível 07 / 01
    não consta da tabela VINCULO". The path is read from the table's own labels,
    never inferred from a prefix alone (§6.2).
    """

    def __init__(self, mapping: Mapping[str, str], *, table: str, segment: int) -> None:
        super().__init__(mapping)
        self._table = table
        self._segment = segment

    def get(self, key: object, default: object = None) -> object:
        found = super().get(key)
        if found is not None:
            return found
        code = str(key).strip()
        seg = self._segment
        if not code.isdigit() or len(code) % seg:
            return default
        # A code that IS a leading level (SIA PA_SRV "115", beside PA_CLASS_S)
        # is named by that level of any listed code under it.
        longer = next((str(v) for k, v in self.items() if len(str(k)) > len(code) and str(k).startswith(code)), None)
        if longer is not None:
            parts = longer.split(" / ")
            if len(parts) >= len(code) // seg:
                return " / ".join(parts[: len(code) // seg])
        if len(code) <= seg:
            return default
        for depth in range(len(code) // seg - 1, 0, -1):
            prefix = code[: depth * seg]
            sibling = next(
                (str(v) for k, v in self.items() if len(str(k)) == len(code) and str(k).startswith(prefix)),
                None,
            )
            parts = sibling.split(" / ") if sibling else []
            if len(parts) >= depth:
                missing = " / ".join(code[i : i + seg] for i in range(depth * seg, len(code), seg))
                return f"{' / '.join(parts[:depth])} — nível {missing} não consta da tabela {self._table}"
        return default


#: Codelists whose labels spell out a fixed-width level path (``PathLabels``).
PATH_CODELISTS: dict[str, int] = {"VINCULO": 2, "S_CLASSEN": 3}


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


def key_parts(key: Sequence[str]) -> list[tuple[str, int | None]]:
    """``[COD_IDADE, IDADE:2]`` -> ``[(COD_IDADE, None), (IDADE, 2)]``.

    A width is the part's fixed width in the source record. TabWin reads a
    composite key from the DBF's own bytes, where the numeric ``IDADE`` (N 2) is
    ``05``; decoded, it is ``5``, and ``45`` matches nothing in IDADEDET.CNV
    while ``405`` is "5 anos". Rebuilding the record's form of a quantity is not
    padding a code (§6.2): the part is a number, and the width is the layout's.
    """
    out: list[tuple[str, int | None]] = []
    for part in key:
        name, _, width = str(part).partition(":")
        out.append((name.strip().upper(), int(width) if width.strip().isdigit() else None))
    return out


def compose_key(table: pa.Table, key: Sequence[str]) -> pa.Array | None:
    """The concatenated key the codelist is indexed by, or None if a part is missing.

    The one place a composite key is built: rendering and the bindings compiler
    both call it, so a column is measured exactly as it is looked up (ADR-0088).
    """
    parts = [("_source_uf" if name == "@UF" else name, width) for name, width in key_parts(key)]
    if not parts or not all(name in table.schema.names for name, _ in parts):
        return None
    arrays = []
    for name, width in parts:
        values = pc.cast(table.column(name).combine_chunks(), pa.string())
        if width:
            values = pc.utf8_lpad(pc.utf8_trim_whitespace(values), width, "0")
        arrays.append(values)
    joined = pc.binary_join_element_wise(*arrays, "")
    return joined.combine_chunks() if hasattr(joined, "combine_chunks") else joined


def _lookup_key(table: pa.Table, doc: object, column: pa.Array) -> pa.Array:
    """The column's own values, or the concatenation its curated ``key:`` names."""
    key = getattr(doc, "key", None) if doc is not None else None
    composed = compose_key(table, key) if key else None
    return column if composed is None else composed


def _label_via(lake: Path, system: str, keys: object, via: Mapping[str, str]) -> pa.Array | None:
    """The ``field`` of ``table``'s row for each value of ``column`` (ADR-0094)."""
    try:
        table = read_reference_table(lake, str(via["table"]), system=system)
    except (FileNotFoundError, OSError, KeyError):
        return None
    field_name = str(via.get("field") or "label")
    if field_name not in table.column_names:
        return None
    # A join in Arrow: the registry has 692,004 rows, and building a Python
    # dict of it per month group cost 25 s of a year's query (2026-09-29).
    wanted = pc.utf8_trim_whitespace(pc.cast(pa.chunked_array([keys]) if isinstance(keys, pa.Array) else keys, pa.string()))
    at = pc.index_in(wanted, value_set=pc.cast(table.column("code"), pa.string()))
    return pc.take(pc.cast(table.column(field_name), pa.string()), at).combine_chunks()


#: A recipe's short names for bridges, and the classification each lands in.
BRIDGE_NAMES = {"A": "SIGTAP_A", "H": "SIGTAP_H"}
BRIDGE_TARGETS = {"SIGTAP_A": ("SIGTAP", 10), "SIGTAP_H": ("SIGTAP", 10), "CBO94": ("CBO2002", 6)}
#: A claim crosses when it holds for this share of the evidence or more.
BRIDGE_UNIQUE = 0.95


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
    classification crosses when one claim holds for ``BRIDGE_UNIQUE`` of the
    evidence (the official link, or the share of professionals DATASUS moved);
    otherwise it stays null rather than choosing.
    """
    name = BRIDGE_NAMES.get(bridge.upper(), bridge.upper())
    _target, width = BRIDGE_TARGETS.get(name, ("", 0))
    table = _bridges()
    values = codes.to_pylist() if hasattr(codes, "to_pylist") else list(codes)  # type: ignore[union-attr]
    out: list[str | None] = []
    for v in values:
        code = str(v).strip() if v is not None else ""
        if width and len(code) == width:
            out.append(code)
            continue
        claims = table.get((name, code), ())
        out.append(claims[0][0] if claims and claims[0][1] >= BRIDGE_UNIQUE else None)
    return pa.array(out, type=pa.string())


def bridge_target(bridge: str) -> str:
    """The classification a bridge lands in (SIGTAP, CBO2002)."""
    return BRIDGE_TARGETS.get(BRIDGE_NAMES.get(bridge.upper(), bridge.upper()), ("SIGTAP", 0))[0]


def _labelled_codes(lake: Path, classification: str, codes: object) -> pa.Array | None:
    """``label (code)`` from a canonical classification, or None where unknown."""
    try:
        table = read_reference_table(lake, classification)
    except (FileNotFoundError, OSError):
        return None
    names = dict(zip(table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True))
    values = codes.to_pylist() if hasattr(codes, "to_pylist") else list(codes)  # type: ignore[union-attr]
    return pa.array(
        [f"{names[v]} ({v})" if v in names else (f"{v} (?)" if v else None) for v in values], type=pa.string()
    )


def _hierarchy_level(lake: Path, classification: str, digits: int, codes: object) -> pa.Array | None:
    """``label (prefix)`` for the first ``digits`` of each code, or None if unknown."""
    if digits <= 0:
        return None
    try:
        table = read_reference_table(lake, classification)
    except (FileNotFoundError, OSError):
        return None
    names = dict(zip(table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True))
    values = codes.to_pylist() if hasattr(codes, "to_pylist") else list(codes)  # type: ignore[union-attr]
    out: list[str | None] = []
    for v in values:
        prefix = str(v).strip()[:digits] if v is not None else ""
        label = names.get(prefix) if len(prefix) == digits else None
        out.append(f"{label} ({prefix})" if label else None)
    return pa.array(out, type=pa.string())


def _coded(doc: object) -> bool:
    """The curation says this column holds codes (not numbers, dates or text)."""
    return doc is not None and getattr(doc, "code_system", None) in ("internal", "external")


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
    from .semantics.label_bindings import candidates_for, decide

    series = ""
    if store is not None and family_id:
        try:
            row = store.query("SELECT series FROM families WHERE family_id=?", (family_id,))
            series = str(row[0]["series"] or "").upper() if row else ""
        except Exception:  # noqa: BLE001 - old/read-only catalogs keep safe behaviour
            series = ""
    # Counted in Arrow: a year of a file is a million cells and a few dozen
    # distinct codes (ADR-0097).
    trimmed = pc.utf8_trim_whitespace(pc.cast(column, pa.string()))
    trimmed = pc.filter(trimmed, pc.and_(pc.is_valid(trimmed), pc.not_equal(trimmed, "")))
    tallied = pc.value_counts(trimmed)
    counts = Counter(dict(zip(
        tallied.field("values").to_pylist(), tallied.field("counts").to_pylist(), strict=True
    )))
    seen = set(counts)
    decision = decide(
        system=system, family_id=family_id, series=series, field_name=name, doc=doc,
        candidates=candidates, counts=counts, load=lambda cl: lookup_one(cl, None),
        store=store, vintage=vintage,
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
    store: Catalog,
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
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    year: int | None = None,
    competencia: int | None = None,
    strict: bool = False,
    collected: dict[str, set] | None = None,
) -> tuple[pa.Table, RenderReport]:
    settings_profile = resolve_profile(
        profile, companions=companions, derived=derived
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

    columns: list[pa.Array] = []
    names: list[str] = []
    lookups: dict[tuple, dict[str, str]] = {}

    def _lookup(field_name: str, codelists: Sequence[str]) -> dict[str, str] | None:
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
        key = (tuple(codelists), system, year, width)
        if key in lookups:
            return lookups[key] or None
        merged, missing = _merged_lookup(lake, tuple(codelists), system, year, competencia)
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

        if codes_only:
            columns.append(column)
            names.append(name)
            continue

        doc = docs.get(name.upper())
        sibling = getattr(doc, "label_from", None) if doc is not None else None
        if sibling and sibling in table.schema.names:
            # The record names its own code (ADR-0090): no table to choose.
            named = pc.utf8_trim(table.column(sibling).combine_chunks().cast(pa.string()), characters=" ")
            named = pc.if_else(pc.equal(named, ""), pa.scalar(None, pa.string()), named)
            columns.append(column)
            names.append(name)
            columns.append(named)
            names.append(f"{name}{LABEL_SUFFIX}")
            report.labelled.append(name)
            report.codelist_used[name] = f"column {sibling}"
            continue
        via = getattr(doc, "label_via", None) if doc is not None else None
        # ``column`` may list candidates: one variable, several layouts (SIA BI
        # names its establishment CODUNI, PS names it CNES_EXEC).
        via_columns = via.get("column", []) if via else []
        via_column = next(
            (str(c).upper() for c in (via_columns if isinstance(via_columns, list) else [via_columns])
             if str(c).upper() in table.schema.names),
            None,
        )
        if via and via_column:
            named_via = _label_via(lake, system, table.column(via_column), via)
            if named_via is not None:
                # The field's own tables first: they name THIS value exactly (a
                # CNPJ's own legal name, a documented "zeros: no maintainer").
                # The row's establishment's maintainer fills what they leave.
                own = [c for c in (doc.codelist, *doc.codelists) if c] if doc is not None else []
                own_lookup = _lookup(name.upper(), own) if own else None
                if own_lookup:
                    named_via = pc.coalesce(_labels_for(column, own_lookup), named_via)
                columns.append(column)
                names.append(name)
                columns.append(named_via)
                names.append(f"{name}{LABEL_SUFFIX}")
                report.labelled.append(name)
                report.codelist_used[name] = f"{via.get('table')}.{via.get('field')} via {via_column}"
                continue
        # The value a table is keyed by. Usually the column itself; for a code
        # that only means something with another column (CNES CLASS_SR, keyed
        # by SERV_ESP + CLASS_SR in S_CLASSEN), the concatenation (ADR-0088).
        key_column = _lookup_key(table, doc, column)
        selection = _select_codelists(
            name,
            key_column,
            doc=doc,
            candidates=list(bindings.get(name.upper()) or []),
            report=report,
            strict=strict,
            lookup_one=lambda cl, w: _single_lookup(lake, cl, system, year, w, competencia),
            store=store,
            system=system,
            family_id=family_id or "",
            vintage=competencia if competencia is not None else year,
        )
        if selection.unlabelled:
            # Selection decided this column cannot be labelled and has already
            # said why. Emit it as filed, with an EMPTY label companion when the
            # curation says the column is coded, so the presentation shows its
            # codes as undecoded ("9 (?)") rather than as plain values (ADR-0085).
            columns.append(column)
            names.append(name)
            if _coded(doc):
                columns.append(pa.nulls(len(column), type=pa.string()))
                names.append(f"{name}{LABEL_SUFFIX}")
            continue
        codelists = selection.codelists
        codelist = codelists[0] if codelists else None
        code_system = (doc.code_system if doc else None) or ("internal" if codelist else "none")
        mode: RenderMode = overrides.get(name.upper()) or (
            settings_profile.internal if code_system == "internal" else
            settings_profile.external if code_system == "external" else "code"
        )

        if code_system == "none" or codelist is None or mode == "code":
            if (codelist is None and code_system in ("internal", "external")
                    and name not in report.unlabelled):
                # Curation says this column IS coded; nothing is bound to
                # decode it. The unlabelled list is the machine-readable form
                # of "visibly unfinished" -- without it the column reverted to
                # raw codes with no trace anywhere in the report.
                report.unlabelled.append(name)
            if mode != "code" and codelist is None and name.upper() in overrides:
                # An explicit request that cannot be honoured must say so.
                message = f"{name}: no codelist is bound, so no label can be produced"
                if strict:
                    raise LabelUnavailable(message)
                report.warnings.append(message)
                report.unlabelled.append(name)
            columns.append(column)
            names.append(name)
            if mode != "code" and codelist is None and _coded(doc):
                # Coded, and nothing decodes it: visibly undecoded (ADR-0085).
                columns.append(pa.nulls(len(column), type=pa.string()))
                names.append(f"{name}{LABEL_SUFFIX}")
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

        width_warning = _check_width(name, "+".join(codelists), key_column, lookup)
        if width_warning:
            report.warnings.append(width_warning)

        # A table that disagrees with itself cannot render this column. Refusing
        # is the whole point: an unlabelled code is visibly unfinished, and a
        # confidently wrong label is not.
        observed = {str(v).strip() for v in key_column.to_pylist() if v is not None}
        try:
            disagreements = {}
            for bound in codelists:
                # Every table the merged lookup draws from, not just the
                # first: a self-contradictory SECOND table was never checked,
                # and its labels reached the merge all the same.
                for code, found in _contradictions(
                    lake,
                    bound,
                    system=system,
                    year=year,
                    competencia=competencia,
                    code_width=None,
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
        labels = _labels_for(key_column, lookup)
        matched = int(pc.sum(pc.is_valid(labels)).as_py() or 0)
        if not matched:
            if len(observed) <= 1:
                # See above: one value throughout is a dead column, not a gap.
                report.constant[name] = next(iter(observed), "")
                report.unlabelled.append(name)
                columns.append(column)
                names.append(name)
                if _coded(doc):  # visibly undecoded, not a plain value (ADR-0086)
                    columns.append(pa.nulls(len(column), type=pa.string()))
                    names.append(f"{name}{LABEL_SUFFIX}")
                continue
            message = f"{name}: reference table {codelist!r} matched none of the observed codes"
            if strict:
                raise LabelUnavailable(message)
            report.warnings.append(message)
            report.unlabelled.append(name)
            columns.append(column)
            names.append(name)
            if _coded(doc):
                columns.append(pa.nulls(len(column), type=pa.string()))
                names.append(f"{name}{LABEL_SUFFIX}")
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
        else:  # "both"
            columns.append(column)
            names.append(name)
            columns.append(labels)
            names.append(f"{name}{LABEL_SUFFIX}")

    _report_reference_decisions(report, collected, system, strict=strict)

    # THE INVARIANT (ADR-0086): a column the curation says is coded leaves with a
    # label companion, null where nothing decoded it, so the presentation shows
    # "9 (?)" instead of a bare code that reads like a value. Enforced once
    # here rather than in each of the loop's refusal branches.
    if not codes_only:
        present_names = set(names)
        final_columns: list[pa.Array] = []
        final_names: list[str] = []
        for col, col_name in zip(columns, names, strict=True):
            final_columns.append(col)
            final_names.append(col_name)
            label_name = f"{col_name}{LABEL_SUFFIX}"
            if (not col_name.endswith(LABEL_SUFFIX) and label_name not in present_names
                    and _coded(docs.get(col_name.upper()))):
                final_columns.append(pa.nulls(len(col), type=pa.string()))
                final_names.append(label_name)
        columns, names = final_columns, final_names
    rendered_table = pa.Table.from_arrays(columns, names=names)

    if settings_profile.derived:
        rendered_table = _apply_derived(
            rendered_table, table, docs, bindings, lake, year, derived, report, store,
            system, competencia,
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
            if not inputs:
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
            bridge = recipe.get("bridge")
            codes_in = source.column(inputs[0])
            if bridge:
                # Across the 2008 change of classification: an old SIA/SIH
                # procedure becomes the SIGTAP procedure that replaced it, when
                # exactly one did (ADR-0101).
                codes_in = bridged(codes_in, str(bridge))
            hierarchy = recipe.get("hierarchy")
            if bridge and not hierarchy:
                derived_column = _labelled_codes(lake, str(recipe.get("to") or bridge_target(str(bridge))), codes_in)
                if derived_column is not None:
                    rendered = rendered.append_column(column_name, derived_column)
                    report.derived_added.append(column_name)
                continue
            if hierarchy:
                # A level of a hierarchical classification as its own dimension:
                # PROC_REA's SIGTAP group, "Procedimentos cirurgicos (04)", which
                # is what "was this a surgery" means (ADR-0092).
                derived_column = _hierarchy_level(
                    lake, str(hierarchy), int(recipe.get("digits") or 0), codes_in
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
            from ._age import AgeDimension, years_column

            encoding = str(recipe.get("encoding") or "")
            if encoding not in ("sih", "sim", "sinan", "years"):
                report.warnings.append(
                    f"{column_name}: the curated recipe declares no age encoding "
                    "(sih|sim|sinan|years), so it cannot be derived"
                )
                continue
            derived_column = years_column(
                AgeDimension(name=column_name, encoding=encoding, fields=tuple(inputs)), source
            )
            rendered = rendered.append_column(column_name, derived_column)
            report.derived_added.append(column_name)
    return rendered


