"""Supramunicipal geography: which region a municipality belongs to.

`normalize/geo.py` canonicalises a municipality — six digits to seven, the check
digit, the UF prefix. It cannot answer "which health region is this in", and
that is the question almost every PegaSUS roll-up asks.

The answer was already in the shipped label pack and nothing could reach it.
DATASUS publishes each supramunicipal classification as an ordinary `.CNV`
codelist keyed on the six-digit municipality code — `CIRBRN` maps 5,680
municipalities to 478 health regions, nationally. `CIRAC`, the 24-row Acre table
that once labelled Rio Branco "Baixo Acre e Purus" (FINDINGS §3k), is one
state's slice of that same classification.

So this module COMPILES rather than sources. `curation/geography.yml` names
which codelist carries which classification — the one fact that is irreducible —
and everything else is read out of the pack.

**The compile is only deterministic when scoped by publishing system.** Grouped
by municipality alone, `CIRBRN` appears to contradict itself on 295
municipalities and `RSAUDBR` on 2,612. Add the validity window and the system
and every one of those collapses to zero. Almost all of the apparent
contradiction is manufactured by the comparison, exactly as in FINDINGS §3e —
and what survives is real and is recorded rather than resolved by picking.

WHAT THIS MODULE IS NOT
-----------------------
It is a **compiled reference view**: cheap lookup for one municipality, and the
member list a UI needs to offer "group by health region". It is deliberately not
a second resolver.

Row-level dimension derivation stays with
``_query_engine.semantics._apply_dimensions``, which is vintage-EXACT — it
re-resolves the relation per competência, refuses when the effective relation
differs across the months of an interval, and checks
``packed_mapping_covers_interval`` before using a table. This module's window
check is coarser and must never be used where that one applies.

The two agree because ``curation/geography.yml`` is the single authority for
which codelist carries which classification, and
``tests/test_geography_relations_agree.py`` fails if a ``rollup_to`` relation in
``joins.yml`` drifts from it. That guard exists because the duplication is what
let ``artifact: CIRAC`` — Acre's 24 rows — stand as the national health-region
roll-up unnoticed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "Membership",
    "MembershipSet",
    "build_geography_pack",
    "classifications",
    "excluded",
    "members",
    "memberships",
]

GEOGRAPHY_PACK_NAME = "geography.parquet"

#: A member label as DATASUS writes it: the member code, a space, then the name.
#: `'11001 RO Ariquemes'` -> `('11001', 'RO Ariquemes')`.
_MEMBER = re.compile(r"^(\d{3,7})\s+(\S.*)$")

#: Columns of the compiled pack.
_FIELDS = (
    "municipality",       # 6-digit IBGE code, as DATASUS writes it
    "classification",     # 'health_region', 'ibge_mesoregion', ...
    "system",             # publishing system; '' means "applies to all systems"
    "member_code",
    "member_label",
    "source_codelist",
    "valid_from",
    "valid_to",
    #: Who says so. `datasus` for the .CNV tables TabNet tabulates against,
    #: `ibge` for the authority that defines territorial identity. Kept per row
    #: because the two answer different halves: health regions are a Ministry
    #: construct IBGE has none of, and the current 2017 hierarchy is one DATASUS
    #: does not publish at all.
    "authority",
)


@dataclass(frozen=True, slots=True)
class Membership:
    """One municipality's membership of one supramunicipal unit."""

    classification: str
    member_code: str
    member_label: str
    system: str = ""
    source_codelist: str = ""
    valid_from: str = ""
    valid_to: str = ""
    authority: str = "datasus"
    #: The publishing systems disagree about this membership and no system was
    #: named, so the value is one of several defensible answers rather than the
    #: answer. Set on 46 of 5,680 municipalities for `health_region`.
    contested: bool = False

    @property
    def system_neutral(self) -> bool:
        return not self.system


@dataclass(frozen=True, slots=True)
class MembershipSet:
    """Every membership resolved for one municipality, plus what disagreed.

    `conflicts` is not an error channel. Two publishing systems really do assign
    46 municipalities to differently-named health regions, and an aggregate over
    SIH must roll up through SIH's answer or its totals will not reconcile with
    DATASUS's own output for the same query. Naming the disagreement is the only
    honest way to hand that decision to the caller.
    """

    municipality: str
    memberships: tuple[Membership, ...] = ()
    conflicts: tuple[str, ...] = ()

    def get(self, classification: str) -> Membership | None:
        for item in self.memberships:
            if item.classification == classification:
                return item
        return None

    def as_dict(self) -> dict[str, str]:
        return {m.classification: m.member_label for m in self.memberships}

    def __len__(self) -> int:
        return len(self.memberships)

    def __repr__(self) -> str:  # pragma: no cover - display
        extra = f", {len(self.conflicts)} contested" if self.conflicts else ""
        return f"<MembershipSet {self.municipality}: {len(self.memberships)} classifications{extra}>"


def _fold(text: str) -> str:
    """Accent- and case-insensitive, so `Xanxerê` and `Xanxere` are one name."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def _curation_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    from .ontology import CURATION

    return CURATION


def classifications(root: Path | None = None, *, authority: str | None = None
                    ) -> dict[str, dict[str, Any]]:
    """Every declared classification, from either authority.

    `authority="datasus"` gives the ones compiled out of the label pack —
    health region, metropolitan region and the rest of the health-service
    geography, which is DATASUS's to define and which IBGE does not publish.
    `authority="ibge"` gives territorial identity, which is IBGE's to define.
    Without an argument, both, because a caller asking "what can I group by"
    wants the whole vocabulary.
    """
    from .ontology import _read_yaml

    data = _read_yaml(_curation_root(root) / "geography.yml") or {}
    datasus = {k: {**v, "authority": "datasus"}
               for k, v in (data.get("classifications") or {}).items()}
    ibge = {k: {**v, "authority": "ibge"}
            for k, v in (data.get("ibge_classifications") or {}).items()}
    if authority == "datasus":
        return datasus
    if authority == "ibge":
        return ibge
    return {**datasus, **ibge}


def excluded(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Classifications deliberately not compiled, with the measured reason."""
    from .ontology import _read_yaml

    data = _read_yaml(_curation_root(root) / "geography.yml") or {}
    return dict(data.get("excluded") or {})


# ------------------------------------------------------------------- compile


def _ibge_rows(municipalities) -> tuple[list[tuple[str, ...]], dict[str, int]]:
    """IBGE memberships in the pack's own shape.

    System-neutral by construction: IBGE publishes one territorial division for
    the country, so there is no per-system disagreement to scope away. That is
    itself the argument for sourcing identity here rather than from thirty
    `.CNV` variants.
    """
    import collections

    rows: list[tuple[str, ...]] = []
    counted: dict[str, set[str]] = collections.defaultdict(set)
    for item in municipalities:
        for classification, member_code, member_label in item.memberships():
            rows.append((item.code6, classification, "", member_code, member_label,
                         "IBGE/localidades", "", "", "ibge"))
            counted[classification].add(item.code6)
    return rows, {k: len(v) for k, v in counted.items()}


def build_geography_pack(
    out_path: str | Path,
    *,
    labels_path: str | Path | None = None,
    root: Path | None = None,
    ibge: Any = None,
) -> dict[str, Any]:
    """Compile the membership pack out of the shipped label pack.

    Returns a report naming, per classification, how many municipalities were
    compiled and how many were left contested.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    if labels_path is None:
        from importlib.resources import files

        labels_path = Path(str(files("pegasus_data.resources") / "labels.parquet"))
    table = pq.read_table(str(labels_path))
    column = {name: table.column(name).to_pylist() for name in table.schema.names}
    has_windows = "valid_from" in table.schema.names

    declared = classifications(root, authority="datasus")
    wanted = {str(body["codelist"]).upper(): name for name, body in declared.items()
              if body.get("codelist")}

    # (municipality, window, codelist) -> {system: (code, label)}
    seen: dict[tuple[str, str, str, str], dict[str, tuple[str, str]]] = {}
    for i in range(table.num_rows):
        codelist = str(column["codelist"][i]).upper()
        if codelist not in wanted or column["code_width"][i] != 6:
            continue
        lo, hi = column["code_lo"][i], column["code_hi"][i]
        if lo != hi:
            # A RANGE in a classification table would assign a span of
            # municipalities to one region. None of the compiled tables uses
            # one; if that changes, it needs deciding rather than expanding.
            continue
        parsed = _MEMBER.match(str(column["label"][i]))
        if not parsed:
            continue
        valid_from = str(column["valid_from"][i] or "") if has_windows else ""
        valid_to = str(column["valid_to"][i] or "") if has_windows else ""
        key = (str(lo), valid_from, valid_to, codelist)
        system = str(column["system"][i] or "")
        if system == "None":
            system = ""
        seen.setdefault(key, {})[system] = (parsed.group(1), parsed.group(2))

    rows: list[tuple[str, ...]] = []
    report: dict[str, dict[str, int]] = {}
    # Counted as DISTINCT municipalities, not as (municipality, window) keys. A
    # municipality published under five validity windows is one municipality,
    # and reporting it as five is the counting bug this project keeps making.
    distinct: dict[str, set[str]] = {}
    contested_set: dict[str, set[str]] = {}
    for (municipality, valid_from, valid_to, codelist), by_system in sorted(seen.items()):
        name = wanted[codelist]
        stat = report.setdefault(name, {"municipalities": 0, "rows": 0, "contested": 0})
        distinct.setdefault(name, set()).add(municipality)
        contested_set.setdefault(name, set())
        # The label pack's own precedence: a system-specific row outranks a
        # system-neutral one. Applying it here keeps geography consistent with
        # how every other label in this project resolves.
        specific = {s: v for s, v in by_system.items() if s}
        effective = specific or by_system
        if len({_fold(label) for _, label in effective.values()}) > 1:
            contested_set[name].add(municipality)
        for system, (member_code, member_label) in sorted(effective.items()):
            rows.append((municipality, name, system, member_code, member_label,
                         codelist, valid_from, valid_to, "datasus"))
            stat["rows"] += 1

    for name, stat in report.items():
        stat["municipalities"] = len(distinct[name])
        stat["contested"] = len(contested_set[name])

    if ibge:
        added, seen_classes = _ibge_rows(ibge)
        rows.extend(added)
        for name, count in seen_classes.items():
            report[name] = {"municipalities": count, "rows": count, "contested": 0,
                            "authority": "ibge"}

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    arrow = pa.table({
        field: pa.array([r[n] for r in rows], pa.string())
        for n, field in enumerate(_FIELDS)
    }).sort_by([("municipality", "ascending"), ("classification", "ascending")])
    pq.write_table(arrow, out, compression="zstd", compression_level=19)
    return {"path": str(out), "rows": len(rows), "classifications": report}


# --------------------------------------------------------------------- read


@lru_cache(maxsize=4)
def _pack(path: str) -> Any:
    import pyarrow.parquet as pq

    return pq.read_table(path)


def _pack_path(pack_path: str | Path | None) -> Path | None:
    if pack_path is not None:
        return Path(pack_path)
    from importlib.resources import files

    try:
        candidate = Path(str(files("pegasus_data.resources") / GEOGRAPHY_PACK_NAME))
    except (ModuleNotFoundError, FileNotFoundError):  # pragma: no cover
        return None
    return candidate if candidate.exists() else None


def memberships(
    code: str,
    *,
    system: str | None = None,
    vintage: int | str | None = None,
    pack_path: str | Path | None = None,
) -> MembershipSet:
    """Every supramunicipal unit a municipality belongs to.

    ``code`` takes the six-digit form DATASUS writes or the seven-digit IBGE
    form; both resolve to the same municipality.

    ``system`` picks the publishing system's answer where they differ. Without
    it, a classification whose systems disagree is reported in ``conflicts`` and
    the system-neutral or first-sorted answer is returned — never silently
    averaged, and never dropped.

    ``vintage`` is a year or ``AAAAMM`` competence; a mapping whose validity
    window excludes it is not returned.
    """
    path = _pack_path(pack_path)
    if path is None:
        return MembershipSet(municipality=str(code))
    table = _pack(str(path))
    col = {name: table.column(name).to_pylist() for name in table.schema.names}

    six = str(code).strip()
    if len(six) == 7:
        six = six[:6]
    six = six.zfill(6) if six.isdigit() else six

    stamp = _stamp(vintage)
    grouped: dict[str, dict[str, tuple[str, str, str, str, str]]] = {}
    for i, municipality in enumerate(col["municipality"]):
        if municipality != six:
            continue
        if not _covers(col["valid_from"][i], col["valid_to"][i], stamp):
            continue
        grouped.setdefault(col["classification"][i], {})[col["system"][i]] = (
            col["member_code"][i], col["member_label"][i],
            col["source_codelist"][i], col["valid_from"][i], col["valid_to"][i],
            col["authority"][i] if "authority" in col else "datasus",
        )

    out: list[Membership] = []
    contested: list[str] = []
    for classification, by_system in sorted(grouped.items()):
        is_contested = False
        if system and system.upper() in {s.upper() for s in by_system if s}:
            chosen_system = next(s for s in by_system if s.upper() == system.upper())
        else:
            is_contested = len({_fold(v[1]) for v in by_system.values()}) > 1
            if is_contested:
                contested.append(classification)
            # A system-neutral row is a real answer and is preferred. Falling
            # back to `sorted()[0]` is ALPHABETICAL and therefore arbitrary —
            # the same tie-break that once labelled Rio Branco with its health
            # region (FINDINGS 3k). It is kept only so a caller gets a usable
            # value, and `contested` is what says not to trust it. Where the
            # systems agree the pick cannot be wrong, so the flag is the whole
            # of the difference.
            chosen_system = "" if "" in by_system else sorted(by_system)[0]
        member_code, member_label, codelist, valid_from, valid_to, authority =             by_system[chosen_system]
        out.append(Membership(
            classification=classification, member_code=member_code,
            member_label=member_label, system=chosen_system,
            source_codelist=codelist, valid_from=valid_from, valid_to=valid_to,
            contested=is_contested, authority=authority,
        ))
    return MembershipSet(municipality=six, memberships=tuple(out), conflicts=tuple(contested))


def _stamp(vintage: int | str | None) -> int | None:
    if vintage is None:
        return None
    text = str(vintage)
    if len(text) == 4 and text.isdigit():
        return int(text) * 100 + 6      # mid-year, so a whole year is covered
    if len(text) == 6 and text.isdigit():
        return int(text)
    return None


def _covers(valid_from: str, valid_to: str, stamp: int | None) -> bool:
    """An open-ended window covers everything; unknown vintage matches all."""
    if stamp is None:
        return True
    low = int(valid_from) if valid_from and str(valid_from).isdigit() else None
    high = int(valid_to) if valid_to and str(valid_to).isdigit() else None
    if low is not None and stamp < low:
        return False
    return not (high is not None and stamp > high)


def members(
    classification: str,
    *,
    system: str | None = None,
    pack_path: str | Path | None = None,
) -> dict[str, str]:
    """``member_code -> member_label`` for one classification.

    The list a frontend needs to offer "group by health region" as a control.
    """
    path = _pack_path(pack_path)
    if path is None:
        return {}
    table = _pack(str(path))
    col = {name: table.column(name).to_pylist() for name in table.schema.names}
    out: dict[str, str] = {}
    for i, name in enumerate(col["classification"]):
        if name != classification:
            continue
        if system and col["system"][i] and col["system"][i].upper() != system.upper():
            continue
        out[col["member_code"][i]] = col["member_label"][i]
    return out


def iter_pack(pack_path: str | Path | None = None) -> Iterable[Mapping[str, str]]:
    """The compiled pack as rows, for tests and diagnostics."""
    path = _pack_path(pack_path)
    if path is None:
        return ()
    return _pack(str(path)).to_pylist()
