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
``packed_mapping_covers_interval`` before using a table. A municipality
dimension read from this pack (``municipality_fields``) keeps that rule: it
calls ``memberships`` for every month of the record's interval and yields
nothing when the months disagree.

The two agree because ``curation/geography.yml`` is the single authority for
which codelist carries which classification, and
``tests/test_geography_relations_agree.py`` fails if a ``rollup_to`` relation in
``joins.yml`` drifts from it. That guard exists because the duplication is what
let ``artifact: CIRAC`` — Acre's 24 rows — stand as the national health-region
roll-up unnoticed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .textenc import fold

__all__ = [
    "build_municipality_points",
    "mesh_file",
    "point_sources",
    "distance_km",
    "great_circle_km",
    "municipality_point",
    "NoPointWarning",
    "classification_names",
    "municipality_fields",
    "Membership",
    "MembershipSet",
    "build_geography_pack",
    "classifications",
    "excluded",
    "members",
    "memberships",
]

GEOGRAPHY_PACK_NAME = "geography.parquet"

#: Municipality identity: `code6 -> (code7, name, uf_code, uf_sigla, uf_name,
#: macroregion)`. Separate from the membership pack because it is an IDENTITY,
#: not a containment: 5,571 rows against the membership pack's 75,000, and it
#: answers "what is this place called and what is its IBGE code" rather than
#: "what is it inside of".
MUNICIPALITY_PACK_NAME = "municipalities.parquet"

_MUNICIPALITY_FIELDS = (
    "code6", "code7", "name", "uf_code", "uf_sigla", "uf_name", "macroregion",
)

#: Which geography roles carry a compatible population denominator.
#:
#: A rate needs its numerator and denominator counted over the SAME population.
#: Population is counted where people live, so only a residence-like binding
#: yields a true rate. Counting admissions by the municipality of the HOSPITAL
#: and dividing by that municipality's population produces a number that looks
#: like a rate and is not one -- a small town with a regional hospital shows a
#: rate several times its own population's risk, because the numerator is drawn
#: from a catchment the denominator does not cover.
#:
#: The binding names are a controlled vocabulary of ten roles across all 125
#: curated datasets, so this is a rule over roles rather than a table over
#: datasets. Curation may override per binding with `denominator: true|false`
#: where a dataset genuinely differs.
DENOMINATOR_COMPATIBLE_ROLES = frozenset({
    "residence",   # MUNIC_RES, ID_MN_RESI, CODMUNRES -- the intended case
    "patient",     # SIA's PA_MUNPCN is the patient's municipality of residence
    "area",        # IBGE's own population geography
})

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


def _curation_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    from .config import curation_root

    return curation_root()


def municipality_fields(system: str, root: Path | None = None) -> frozenset[str]:
    """Columns of ``system`` whose values are municipality codes (``geography.yml``)."""
    from .semantics.curation import read_yaml

    data = read_yaml(_curation_root(root) / "geography.yml", missing_ok=True) or {}
    declared = data.get("municipality_fields") or {}
    return frozenset(str(f).upper() for f in declared.get(str(system).upper(), ()) or ())


def classification_names(pack_path: str | Path | None = None) -> frozenset[str]:
    """The classifications the shipped membership pack holds."""
    path = _pack_path(pack_path)
    if path is None:
        return frozenset()
    table = _pack(str(path))
    return frozenset(str(v) for v in table.column("classification").unique().to_pylist())


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
    from .semantics.curation import read_yaml

    data = read_yaml(_curation_root(root) / "geography.yml", missing_ok=True) or {}
    datasus = {k: {**v, "authority": "datasus"}
               for k, v in (data.get("classifications") or {}).items()}
    ibge = {k: {**v, "authority": "ibge"}
            for k, v in (data.get("ibge_classifications") or {}).items()}
    tabnet = {k: {**v, "authority": "tabnet"}
              for k, v in (data.get("tabnet_classifications") or {}).items()}
    ipea = {k: {**v, "authority": "ipea"}
            for k, v in (data.get("ipea_classifications") or {}).items()}
    if authority == "datasus":
        return datasus
    if authority == "ibge":
        return ibge
    if authority == "tabnet":
        return tabnet
    if authority == "ipea":
        return ipea
    return {**datasus, **ibge, **tabnet, **ipea}


def excluded(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Classifications deliberately not compiled, with the measured reason."""
    from .semantics.curation import read_yaml

    data = read_yaml(_curation_root(root) / "geography.yml", missing_ok=True) or {}
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


def _tabnet_rows(root: Path | None, cache_dir: str | Path) -> tuple[list[tuple[str, ...]], dict[str, dict[str, int | str]]]:
    """Memberships from TabNet's current territorial tables (``tabnet_classifications``).

    One table per classification and no per-system copies, so nothing to scope
    away: a municipality has one current macroregion. A catch-all range
    ("Ignorado - BR") is not a membership and is skipped, as are rows whose
    label carries no member code.
    """
    from .semantics.cnv_parser import parse_cnv
    from .sources.tabnet import fetch_territorial

    rows: list[tuple[str, ...]] = []
    report: dict[str, dict[str, Any]] = {}

    def memberships(table_name: str) -> dict[str, tuple[str, str]]:
        out: dict[str, tuple[str, str]] = {}
        for category in parse_cnv(fetch_territorial(table_name, cache_dir)).categories:
            if len(category.codes) != 1 or not re.fullmatch(r"\d{6}", category.codes[0]):
                continue
            parsed = _MEMBER.match(category.label)
            if parsed:
                out[category.codes[0]] = (parsed.group(1), parsed.group(2))
        return out

    for name, body in classifications(root, authority="tabnet").items():
        table_name = str(body["table"])
        national = memberships(table_name)
        # TabNet's state forms (sih/cnv/nrro.def: "territorio\RO_macsaud.cnv") classify by the state's own table: it
        # is the authority where it exists, and the national table is the check (it omits Alta Floresta D'Oeste,
        # 110001, which RO_macsaud.cnv puts in 1101)
        chosen: dict[str, tuple[str, str, str]] = {m: (*v, table_name) for m, v in national.items()}
        added: list[str] = []
        contested: list[dict[str, str]] = []
        state_template = body.get("state_table")
        if state_template:
            from .config import UF_CODES

            for uf in sorted(UF_CODES - {"BR"}):
                state_name = str(state_template).format(uf=uf)
                # a state table's labels are not decoded as the national one's (RO_regsaud reads "CafÚ" for Café): it
                # decides membership, and a member keeps the national table's label where that table names it
                national_label = dict(national.values())
                for municipality, member in memberships(state_name).items():
                    before = national.get(municipality)
                    if before is not None and before[0] == member[0]:
                        continue
                    if before is None:
                        added.append(municipality)
                    else:
                        contested.append({"municipality": municipality, state_name: member[0], table_name: before[0]})
                    chosen[municipality] = (member[0], national_label.get(member[0], member[1]), state_name)
        for municipality, (code, label, source) in sorted(chosen.items()):
            rows.append((municipality, name, "", code, label, f"tabnet:territorio/{source}.cnv", "", "", "tabnet"))
        report[name] = {"municipalities": len(chosen), "members": len({v[0] for v in chosen.values()}),
                        "rows": len(chosen), "contested": len(contested), "authority": "tabnet",
                        "added_by_state_tables": sorted(added), "state_and_national_differ": contested}
    return rows, report


def _ipea_rows(root: Path | None, cache_dir: str | Path) -> tuple[list[tuple[str, ...]], dict[str, dict[str, int | str]]]:
    """Comparable-area memberships (``ipea_classifications``), one per period."""
    from .sources.ipea_amc import comparable_areas, fetch

    rows: list[tuple[str, ...]] = []
    report: dict[str, dict[str, int | str]] = {}
    for name, body in classifications(root, authority="ipea").items():
        start = int(body["start_year"])
        members = comparable_areas(fetch(start, cache_dir))
        for code7, amc, label in members:
            rows.append((code7[:6], name, "", amc, label, f"ipea:geobr/amc/{start}-2010", "", "", "ipea"))
        report[name] = {"municipalities": len(members), "members": len({a for _, a, _ in members}),
                        "rows": len(members), "contested": 0, "authority": "ipea"}
    return rows, report


def _expand_ranges(ranges: list[tuple[str, str, str, str, str, str, str, tuple[str, str]]],
                   seen: dict[tuple[str, str, str, str], dict[str, tuple[str, str]]]) -> dict[str, int]:
    """Give each range row's member to the municipalities (``resources/municipalities.parquet``, 6-digit codes) the range
    spans, in ``seen``. A row for a single code outranks a range over it (the narrower answer); two ranges that give
    one municipality different members in the same window and system are a conflict and raise, not a pick. Codes of a
    range that are no municipality (the "ignorado" spans, the Federal District's administrative regions) are counted per
    classification and returned. Raises when a municipality a range spans ends without its row."""
    if not ranges:
        return {}
    codes = sorted(municipalities())
    placeholders: dict[str, int] = {}
    given: dict[tuple[str, str, str, str, str], tuple[str, str]] = {}
    for lo, hi, codelist, valid_from, valid_to, system, name, member in ranges:
        covered = [c for c in codes if lo <= c <= hi]
        placeholders[name] = placeholders.get(name, 0) + (int(hi) - int(lo) + 1 - len(covered))
        for code in covered:
            key = (code, valid_from, valid_to, codelist)
            if system in seen.get(key, {}):
                continue                      # a single-code row is the narrower answer
            previous = given.setdefault((*key, system), member)
            if previous != member:
                raise ValueError(f"{codelist} {code} {valid_from}-{valid_to} {system or '*'}: two ranges give it "
                                 f"{previous} and {member}")
            seen.setdefault(key, {})[system] = member
    for lo, hi, codelist, valid_from, valid_to, system, _name, _member in ranges:
        for code in (c for c in codes if lo <= c <= hi):
            if system not in seen.get((code, valid_from, valid_to, codelist), {}):
                raise ValueError(f"{codelist}: range {lo}-{hi} spans municipality {code}, which ended without a row")
    return placeholders


def _arranjo_rows(root: Path | None, cache_dir: str | Path) -> tuple[list[tuple[str, ...]], dict[str, dict[str, int | str]]]:
    """IBGE's population arrangements and urban concentrations (``source: IBGE/arranjos_populacionais_2ed``)."""
    from .sources.ibge_arranjos import fetch, memberships

    wanted = [name for name, body in classifications(root, authority="ibge").items()
              if body.get("source") == "IBGE/arranjos_populacionais_2ed"]
    if not wanted:
        return [], {}
    published = memberships(fetch(cache_dir))
    rows: list[tuple[str, ...]] = []
    report: dict[str, dict[str, int | str]] = {}
    for name in wanted:
        members = published[name]
        rows.extend((code7[:6], name, "", member, label, "ibge:arranjos_populacionais_2ed", "", "", "ibge")
                    for code7, member, label in members)
        report[name] = {"municipalities": len(members), "members": len({m for _, m, _ in members}),
                        "rows": len(members), "contested": 0, "authority": "ibge"}
    return rows, report


def _biome_rows(root: Path | None, cache_dir: str | Path) -> tuple[list[tuple[str, ...]], dict[str, dict[str, int | str]]]:
    """IBGE's predominant biome per municipality (``source: IBGE/biomas_2024``; sources/ibge_biomas.py, ADR-0213)."""
    from .sources.ibge_biomas import fetch, memberships

    wanted = [name for name, body in classifications(root, authority="ibge").items()
              if body.get("source") == "IBGE/biomas_2024"]
    if not wanted:
        return [], {}
    members = memberships(fetch(cache_dir))
    rows: list[tuple[str, ...]] = []
    report: dict[str, dict[str, int | str]] = {}
    for name in wanted:
        rows.extend((code7[:6], name, "", member, label, "ibge:biomas_2024", "", "", "ibge")
                    for code7, member, label in members)
        report[name] = {"municipalities": len(members), "members": len({m for _, m, _ in members}),
                        "rows": len(members), "contested": 0, "authority": "ibge"}
    return rows, report


def build_geography_pack(
    out_path: str | Path,
    *,
    labels_path: str | Path | None = None,
    root: Path | None = None,
    ibge: Any = None,
    tabnet_cache: str | Path | None = None,
    ipea_cache: str | Path | None = None,
    arranjos_cache: str | Path | None = None,
    biomas_cache: str | Path | None = None,
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
    # A row of the label pack may be a RANGE of codes (CIRBRN: 530000-539999 is the Federal District, 110005-110007 the
    # Vilhena region): it assigns its member to every municipality whose code it spans. The compiled tables hold
    # CIRBRN 16, CSAUDBR 595, BR_PNDR 19, AGLBR 24, BR_REGMETR 11, BR_TERRCID 3 and BR_CAPITAL 3 such rows, and the
    # compiler dropped them all: the Federal District and 24 current municipalities had no health region (2026-10-14).
    ranges: list[tuple[str, str, str, str, str, str, str, tuple[str, str]]] = []
    for i in range(table.num_rows):
        codelist = str(column["codelist"][i]).upper()
        if codelist not in wanted or column["code_width"][i] != 6:
            continue
        lo, hi = column["code_lo"][i], column["code_hi"][i]
        parsed = _MEMBER.match(str(column["label"][i]))
        if not parsed:
            continue
        valid_from = str(column["valid_from"][i] or "") if has_windows else ""
        valid_to = str(column["valid_to"][i] or "") if has_windows else ""
        system = str(column["system"][i] or "")
        if system == "None":
            system = ""
        if lo != hi:
            ranges.append((str(lo), str(hi), codelist, valid_from, valid_to, system, wanted[codelist],
                           (parsed.group(1), parsed.group(2))))
            continue
        key = (str(lo), valid_from, valid_to, codelist)
        seen.setdefault(key, {})[system] = (parsed.group(1), parsed.group(2))
    placeholders = _expand_ranges(ranges, seen)

    rows: list[tuple[str, ...]] = []
    report: dict[str, dict[str, int | str]] = {}
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
        if len({fold(label) for _, label in effective.values()}) > 1:
            contested_set[name].add(municipality)
        for system, (member_code, member_label) in sorted(effective.items()):
            rows.append((municipality, name, system, member_code, member_label,
                         codelist, valid_from, valid_to, "datasus"))
            stat["rows"] = int(stat["rows"]) + 1

    for name, stat in report.items():
        stat["municipalities"] = len(distinct[name])
        stat["contested"] = len(contested_set[name])
        stat["range_placeholder_codes"] = placeholders.get(name, 0)

    if ibge:
        added, seen_classes = _ibge_rows(ibge)
        rows.extend(added)
        for name, count in seen_classes.items():
            report[name] = {"municipalities": count, "rows": count, "contested": 0,
                            "authority": "ibge"}
    if tabnet_cache is not None:
        added, tabnet_report = _tabnet_rows(root, tabnet_cache)
        rows.extend(added)
        report.update(tabnet_report)
    if ipea_cache is not None:
        added, ipea_report = _ipea_rows(root, ipea_cache)
        rows.extend(added)
        report.update(ipea_report)
    if arranjos_cache is not None:
        added, arranjo_report = _arranjo_rows(root, arranjos_cache)
        rows.extend(added)
        report.update(arranjo_report)
    if biomas_cache is not None:
        added, biome_report = _biome_rows(root, biomas_cache)
        rows.extend(added)
        report.update(biome_report)

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
def build_municipality_pack(
    out_path: str | Path, *, ibge: Any = None, cache: str | Path | None = None
) -> dict[str, Any]:
    """Compile municipality identity from IBGE localidades.

    `ibge` is a sequence of `sources.ibge_localidades.Municipality`. When it is
    None the cached download is read; there is no live fetch here, because a
    build that silently reaches the network produces a pack whose contents
    depend on when it ran.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    if ibge is None:
        from .sources.ibge_localidades import load_cached

        if cache is None:
            raise ValueError(
                "build_municipality_pack needs `ibge` or `cache`; refusing to "
                "guess where the IBGE download lives"
            )
        ibge = load_cached(Path(cache))

    rows = sorted(
        (m.code6, m.code7, m.name, m.uf_code, m.uf_sigla, m.uf_name, m.macroregion)
        for m in ibge
    )
    if len(rows) < 5_000:
        # The same floor `fetch_municipalities` uses. A partial answer here
        # would leave whole states unmappable and look like missing data.
        raise ValueError(
            f"only {len(rows)} municipalities; Brazil has ~5,570 and a short "
            "pack would silently unmap whole states"
        )
    table = pa.table({
        name: pa.array([r[i] for r in rows], pa.string())
        for i, name in enumerate(_MUNICIPALITY_FIELDS)
    })
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, str(out), compression="zstd")
    return {"municipalities": len(rows), "path": str(out),
            "bytes": out.stat().st_size}


@lru_cache(maxsize=2)
def _municipality_index(path: str, mtime_ns: int = 0) -> dict[str, dict[str, str]]:
    """`code6 -> row`, built once.

    Cached for the same reason `_index` is: a national roll-up asks 5,570 times,
    and reading the parquet per question cost 62 minutes the last time this
    module answered a question by rescanning (FINDINGS 3q).
    """
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    columns = {name: table.column(name).to_pylist() for name in table.schema.names}
    out: dict[str, dict[str, str]] = {}
    for i in range(table.num_rows):
        row = {name: str(columns[name][i] or "") for name in table.schema.names}
        out[row["code6"]] = row
    return out


def municipalities(pack_path: str | Path | None = None) -> dict[str, dict[str, str]]:
    """`code6 -> {code7, name, uf_code, uf_sigla, uf_name, macroregion}`."""
    resolved = _pack_path(pack_path, MUNICIPALITY_PACK_NAME)
    if resolved is None:
        return {}
    return _municipality_index(str(resolved), _pack_mtime(str(resolved)))


def sole_by_uf(pack_path: str | Path | None = None) -> dict[str, str]:
    """`uf_code -> code6` for each state with exactly one municipality (the Federal District: Brasília)."""
    per_uf: dict[str, list[str]] = {}
    for code6, row in municipalities(pack_path).items():
        per_uf.setdefault(row["uf_code"], []).append(code6)
    return {uf: codes[0] for uf, codes in per_uf.items() if len(codes) == 1}


def uf_codes_by_sigla(pack_path: str | Path | None = None) -> dict[str, str]:
    """`uf_sigla -> uf_code`, from the one municipality table."""
    return {row["uf_sigla"]: row["uf_code"] for row in municipalities(pack_path).values()}


def to_code7(code: str, pack_path: str | Path | None = None) -> str | None:
    """The IBGE 7-digit code of the municipality a 6- or 7-digit code places (`place_municipalities`), or None.

    Returns None rather than guessing: the check digit is not derivable, and a wrong seventh digit joins to the WRONG
    municipality rather than to nothing, which is the more dangerous failure. A 7-digit code is placed by its first six
    like any other: one that names no municipality is None, not itself."""
    placed = place_municipalities([code], pack_path)[0]
    return None if placed is None else str(placed)


@lru_cache(maxsize=4)
def _placer(path: str, mtime_ns: int = 0) -> tuple[dict[str, int], dict[str, int], list[tuple[str, int | None]]]:
    """The placing rule's tables, built once per pack: ``code6 -> code7``, ``uf_code -> sole municipality``, and the
    declared ``legacy_places`` as ``(prefix, code7)``."""
    by_six = {k: int(v["code7"]) for k, v in _municipality_index(path, mtime_ns).items()}
    sole = {uf: by_six[code6] for uf, code6 in sole_by_uf(path).items()}
    from .semantics.curation import read_yaml

    declared = read_yaml(_curation_root(None) / "geography.yml", missing_ok=True) or {}
    legacy = [(str(r["prefix"]), by_six.get(str(r["municipality"])[:6])) for r in declared.get("legacy_places") or []]
    return by_six, sole, legacy


def placing_rule(pack_path: str | Path | None = None) -> dict[str, Any]:
    """The facts the one placing rule applies, for every reader of it (`place_municipalities` in Python, the intake's
    landing in SQL): ``universe`` (a municipality's six digits -> its IBGE code), ``sole`` (a state of one municipality ->
    that municipality: the Federal District's administrative regions are Brasília) and ``legacy`` (``geography.yml``'s
    ``legacy_places``: a code prefix no IBGE municipality has -> the municipality a system wrote it for); the tables
    `_placer` builds once per pack."""
    resolved = _pack_path(pack_path, MUNICIPALITY_PACK_NAME)
    if resolved is None:
        return {"universe": {}, "sole": {}, "legacy": []}
    by_six, sole, legacy = _placer(str(resolved), _pack_mtime(str(resolved)))
    return {"universe": by_six, "sole": sole, "legacy": legacy}


def place_municipalities(codes: Any, pack_path: str | Path | None = None) -> list[int | None]:
    """Each raw municipality code as an IBGE 7-digit code (int), or None: the one placing rule.

    A code is read as filed, less a float's ``.0``; 6 or 7 digits; a 7-digit code by its first 6 (the check digit is
    IBGE's, never trusted from the record). A code of a state that has one municipality is that municipality: the Federal
    District files its administrative regions as 53xxxx codes, and SRAG's notifications of residents of Brasília are
    5,3xx,xxx-coded (105,788 events, 2026-11-09). A code a system wrote for a municipality no IBGE code names is placed by
    ``geography.yml``'s ``legacy_places`` (Rio de Janeiro's 3345xxx of 1991-1998). Any other is no municipality, never a
    guess. The intake's
    landing applies the same rule in SQL to the records it streams (`intake._records_sql`, ``_MUNICIPALITY``)."""
    resolved = _pack_path(pack_path, MUNICIPALITY_PACK_NAME)
    if resolved is None:
        return [None for _ in codes]
    by_six, sole, legacy7 = _placer(str(resolved), _pack_mtime(str(resolved)))
    out: list[int | None] = []
    for raw in codes:
        text = "" if raw is None else str(raw).strip()
        if text.endswith(".0"):
            text = text[:-2]
        if not text.isdigit() or len(text) not in (6, 7):
            out.append(None)
            continue
        placed = by_six.get(text[:6]) or sole.get(text[:2])
        if placed is None:
            placed = next((code for prefix, code in legacy7 if text.startswith(prefix)), None)
        out.append(placed)
    return out


def place_states(codes: Any, pack_path: str | Path | None = None) -> list[int | None]:
    """Each raw municipality code's state (IBGE two-digit code, int), or None: the state of the municipality it places
    (`place_municipalities`), else the state a declared state-only code names (``geography.yml`` ``state_only_codes``:
    a state's two digits followed by zeros, DATASUS's "Município ignorado - <UF>"). Any other code is in no state."""
    from .config import UF_NUMERIC
    from .semantics.curation import read_yaml

    rule = (read_yaml(_curation_root(None) / "geography.yml", missing_ok=True) or {}).get("state_only_codes") or {}
    fill = str(rule.get("suffix_digit") or "")
    codes = list(codes)
    out: list[int | None] = []
    for raw, placed in zip(codes, place_municipalities(codes, pack_path), strict=True):
        if placed is not None:
            out.append(placed // 100000)
            continue
        text = "" if raw is None else str(raw).strip().removesuffix(".0")
        state_only = (fill and text.isdigit() and len(text) in (6, 7) and text[:2] in UF_NUMERIC
                      and set(text[2:]) == {fill})
        out.append(int(text[:2]) if state_only else None)
    return out


def place_six(codes: Any, pack_path: str | Path | None = None) -> list[str | None]:
    """Each raw municipality code as the 6-digit DATASUS code of the municipality it places (`place_municipalities`), or
    None where it places none. The one way to a 6-digit key from a record's code: never a cut of its first six digits."""
    return [None if p is None else str(p)[:6] for p in place_municipalities(codes, pack_path)]


def _pack(path: str) -> Any:
    import pyarrow.parquet as pq

    return pq.read_table(path)


@lru_cache(maxsize=4)
def _index(path: str, mtime_ns: int = 0) -> dict[str, tuple[tuple[str, ...], ...]]:
    """`municipality -> rows`, built once.

    The obvious implementation reads the columns to Python lists inside
    ``memberships()`` and scans them. That is O(pack) per lookup, and the pack
    is 75,000 rows: measured at **665 ms per municipality**, so resolving a
    national roll-up spent 62 MINUTES on geography alone. The artifact it serves
    is meant to answer in seconds.

    Indexing once makes it O(1), and the pack is small enough to hold whole.
    """
    table = _pack(path)
    names = list(table.schema.names)
    columns = [table.column(n).to_pylist() for n in names]
    out: dict[str, list[tuple[str, ...]]] = {}
    for i in range(table.num_rows):
        row = tuple("" if columns[c][i] is None else str(columns[c][i])
                    for c in range(len(names)))
        out.setdefault(row[0], []).append(row)
    return {k: tuple(v) for k, v in out.items()}


@lru_cache(maxsize=4)
def _fields(path: str, mtime_ns: int = 0) -> dict[str, int]:
    return {name: i for i, name in enumerate(_pack(path).schema.names)}


def _pack_mtime(path: str) -> int:
    """The pack file's mtime, so a swapped pack is a different cache key.

    The artifact fingerprint hashes the pack's checksum precisely because a
    new pack changes every roll-up; a path-only key let a long-lived server
    keep serving the old pack's answers after the file changed underneath it.
    """
    from pathlib import Path as _P

    try:
        return _P(path).stat().st_mtime_ns
    except OSError:
        return 0


def _pack_path(pack_path: str | Path | None, name: str = GEOGRAPHY_PACK_NAME) -> Path | None:
    """The pack at ``pack_path``, else the shipped one called ``name`` (the memberships, or the municipalities)."""
    if pack_path is not None:
        return Path(pack_path)
    from importlib.resources import files

    try:
        candidate = Path(str(files("pegasus_data.resources") / name))
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
    stamp_ns = _pack_mtime(str(path))
    index, at = _index(str(path), stamp_ns), _fields(str(path), stamp_ns)

    # the width is matched exactly: 6 or 7 digits (a 7-digit code by its first six, as `place_municipalities` reads it);
    # any other width is no municipality, so no membership (never padded to a width that matches)
    six = str(code).strip()
    six = six[:6] if len(six) == 7 and six.isdigit() else six
    if len(six) != 6:
        return MembershipSet(municipality=str(code))

    stamp = _stamp(vintage)
    covering: dict[str, dict[str, list[tuple[str, str, str, str, str, str]]]] = {}
    for row in index.get(six, ()):
        if not _covers(row[at["valid_from"]], row[at["valid_to"]], stamp):
            continue
        covering.setdefault(row[at["classification"]], {}).setdefault(row[at["system"]], []).append((
            row[at["member_code"]], row[at["member_label"]],
            row[at["source_codelist"]], row[at["valid_from"]], row[at["valid_to"]],
            row[at["authority"]] if "authority" in at else "datasus",
        ))
    # One answer per (classification, system): the narrowest dated window, not the last row of the file (an open row
    # and four dated ones for one municipality returned whichever came last: 176 groups of health_colegiado).
    grouped: dict[str, dict[str, tuple[str, str, str, str, str, str]]] = {}
    window_conflicts: set[str] = set()
    for classification, by_sys in covering.items():
        for sys_name, rows in by_sys.items():
            chosen, conflict = _pick_window(rows, stamp)
            grouped.setdefault(classification, {})[sys_name] = chosen
            if conflict:
                window_conflicts.add(classification)

    out: list[Membership] = []
    contested: list[str] = []
    for classification, by_system in sorted(grouped.items()):
        is_contested = classification in window_conflicts
        if is_contested:
            contested.append(classification)
        if system and system.upper() in {s.upper() for s in by_system if s}:
            chosen_system = next(s for s in by_system if s.upper() == system.upper())
        else:
            if len({fold(v[1]) for v in by_system.values()}) > 1 and classification not in contested:
                is_contested = True
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


def _window(row: tuple[str, ...]) -> tuple[int, int]:
    """A row's validity window as (first, last) YYYYMM, open ends as 0 and 999999."""
    low, high = row[3], row[4]
    return (int(low) if low and str(low).isdigit() else 0, int(high) if high and str(high).isdigit() else 999999)


def _pick_window(rows: list[tuple[str, str, str, str, str, str]], stamp: int | None
                 ) -> tuple[tuple[str, str, str, str, str, str], bool]:
    """Among the rows of one classification and system that cover the vintage, the narrowest dated window (a dated
    window is narrower than an open one; without a vintage, the latest). Also whether the answer is not settled: two
    dated windows that overlap with different members, or an open row and the chosen dated one that disagree."""
    if len(rows) == 1:
        return rows[0], False
    dated = [r for r in rows if _window(r) != (0, 999999)]
    opens = [r for r in rows if _window(r) == (0, 999999)]
    if not dated:
        return opens[0], len({r[0] for r in opens}) > 1
    conflict = any(a[0] != b[0] and _window(a)[0] <= _window(b)[1] and _window(b)[0] <= _window(a)[1]
                   for i, a in enumerate(dated) for b in dated[i + 1:])
    if stamp is None:
        chosen = max(dated, key=lambda r: (_window(r)[0], _window(r)[1]))
    else:
        chosen = min(dated, key=lambda r: (_window(r)[1] - _window(r)[0], -_window(r)[0]))
    return chosen, conflict or any(r[0] != chosen[0] for r in opens)


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


# --- Representative points --------------------------------------------------
#
# A polygon's centroid is a poor stand-in for where a municipality's people
# are: for 2022 boundaries it lies a median 5.6 km from the seat, over 50 km
# for 161 municipalities (Altamira: 407 km), and outside the municipality
# itself for 55 (EVALUATION 2026-10-03 "Municipality points"). The points pack
# keeps three per municipality:
# - the seat, IBGE's Localidades 2022 point for the municipal seat;
# - the population centre, the population-weighted median of the Grade
#   Estatística 2022's cells (a median, so a far district cannot drag it into
#   empty land; ADR-0203);
# - the polygon centroid, kept only to measure against.

POINTS_PACK_NAME = "municipality_points.parquet"
POINT_SOURCES = {
    "localities.gpkg": ("https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/"
                        "Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip"),
}

#: IBGE's mesh levels (``intrarregiao``) by the name a caller uses
MESH_LEVELS = {"municipality": "municipio", "state": "UF", "region": "regiao"}
#: IBGE's mesh API: the one definition of its URL (``quality``: minima, intermediaria or maxima)
MESH_URL = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson"
            "&qualidade={quality}&intrarregiao={level}")


def mesh_file(level: str = "municipality", quality: str = "minima", root: str | Path | None = None) -> Path:
    """IBGE's mesh as a GeoJSON file in the data home's ``registries/ibge_mesh``, downloaded once (streamed and resumed;
    the API answers gzip without saying so, DATA_SOURCES §6.3, and is decompressed file to file). Every reader of the
    mesh takes this file: `mesh`, the points pack, INMET's station placement."""
    import gzip
    import shutil

    from .config import load_settings
    from .transport import download

    if level not in MESH_LEVELS or quality not in ("minima", "intermediaria", "maxima"):
        raise ValueError(f"level in {sorted(MESH_LEVELS)}, quality minima, intermediaria or maxima")
    target = load_settings(root=root).registry_dir("ibge_mesh") / f"{level}_{quality}.json"
    if target.is_file():
        return target
    got = download(MESH_URL.format(quality=quality, level=MESH_LEVELS[level]), target.with_name(target.name + ".dl"),
                   timeout=600)
    with got.open("rb") as handle:
        gzipped = handle.read(2) == bytes((0x1F, 0x8B))
    if gzipped:
        tmp = target.with_name(target.name + ".tmp")
        with gzip.open(got, "rb") as src, tmp.open("wb") as out:
            shutil.copyfileobj(src, out, 1 << 24)
        got.unlink()
        tmp.replace(target)
    else:
        got.replace(target)
    return target


def mesh(level: str = "municipality", quality: str = "minima", root: str | Path | None = None):
    """IBGE's polygons of Brazil's municipalities, states or regions (`/api/v3/malhas`, today's division) as a
    GeoDataFrame (``code``: IBGE's code, 7 digits for a municipality; ``geometry`` in SIRGAS 2000, EPSG:4674), from
    `mesh_file`. ``quality`` is IBGE's: ``minima`` (maps, a few MB) to ``maxima`` (the points pack's)."""
    import geopandas as gpd

    frame = gpd.read_file(mesh_file(level, quality, root)).set_crs("EPSG:4674", allow_override=True)
    return frame.rename(columns={"codarea": "code"})[["code", "geometry"]]


#: A point outside every polygon (a coastal station, a seaside runway) takes the nearest municipality within this distance
COAST_TOLERANCE_M = 2000


def place_points(lon: Any, lat: Any, *, mesh_path: str | Path | None = None, root: str | Path | None = None,
                 tolerance_m: float = COAST_TOLERANCE_M) -> tuple[list[str | None], list[str | None]]:
    """The municipality each point (SIRGAS 2000 degrees) lies in, by IBGE's full-resolution mesh: ``(code7, placed_by)``
    per point, ``placed_by`` ``within`` or ``nearest within <tolerance> m`` (a point just off the coast), both None for a
    point placed nowhere or without coordinates. The one placement of points in municipalities (stations, airports)."""
    import geopandas as gpd
    import pandas as pd

    lon, lat = list(lon), list(lat)
    frame = pd.DataFrame({"lon": pd.to_numeric(pd.Series(lon), errors="coerce"),
                          "lat": pd.to_numeric(pd.Series(lat), errors="coerce")}).dropna()
    points = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(frame.lon, frame.lat), crs="EPSG:4674")
    path = mesh_path or mesh_file("municipality", "maxima", root)
    polygons = gpd.read_file(path)[["codarea", "geometry"]].set_crs("EPSG:4674", allow_override=True)
    placed = gpd.sjoin(points, polygons, how="left", predicate="within")
    placed = placed[~placed.index.duplicated()]
    code = placed["codarea"].copy()
    how = code.where(code.isna(), "within")
    missing = code.isna()
    if missing.any():
        # Distances in metres: SIRGAS 2000 / Brazil Polyconic.
        near = gpd.sjoin_nearest(points[missing].to_crs("EPSG:5880"), polygons.to_crs("EPSG:5880"), how="left",
                                 max_distance=tolerance_m)
        near = near[~near.index.duplicated()]
        code[missing] = near["codarea"]
        how[missing & code.notna()] = f"nearest within {tolerance_m:g} m"
    codes: list[str | None] = [None] * len(lon)
    ways: list[str | None] = [None] * len(lon)
    for i in code.index:
        if pd.notna(code[i]):
            codes[i], ways[i] = str(code[i]), str(how[i])
    return codes, ways


def point_sources(cache_dir: str | Path) -> dict[str, Path]:
    """The IBGE file the points pack is built from beside the mesh (`mesh_file`) and the grade (`sources.ibge_grade`), the
    localities, downloaded once into ``cache_dir``."""
    import shutil
    import zipfile

    from .transport import download

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name, url in POINT_SOURCES.items():
        target = cache / name
        if not target.is_file():
            got = download(url, target.with_name(target.name + ".dl"), timeout=7200)
            if url.endswith(".zip"):
                tmp = target.with_suffix(target.suffix + ".tmp")
                with zipfile.ZipFile(got) as archive:
                    member = next(n for n in archive.namelist() if n.endswith(".gpkg"))
                    with archive.open(member) as src, tmp.open("wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 24)
                got.unlink()
                tmp.replace(target)
            else:
                got.replace(target)
        out[name] = target
    return out


def build_municipality_points(out_path: str | Path, *, localities: str | Path, mesh: str | Path,
                              grade_root: str | Path | None = None) -> dict[str, Any]:
    """Write the points pack from IBGE's 2022 localities, the Grade Estatística 2022 (in the data home ``grade_root``,
    `sources.ibge_grade`) and the municipal mesh."""
    import geopandas as gpd
    import pandas as pd

    from .semantics.curation import declared
    from .sources.ibge_grade import ALBERS, population_points

    projected = "EPSG:5880"   # SIRGAS 2000 / Brazil Polyconic: metres
    loc = gpd.read_file(localities)
    seats = loc[loc["SCT_LOCALIDADE"].isin(declared("published_tables.yml", "ibge_localities", "seat_categories"))][["CD_MUN", "geometry"]].drop_duplicates("CD_MUN")
    seats = seats.set_index(seats["CD_MUN"].astype(str))["geometry"]
    # The people: the grade's 200 m / 1 km cells, placed by CNEFE 2022's household coordinates (ADR-0203). The
    # population-weighted MEDIAN of the cells' centres, coordinate by coordinate in the grade's equal-area projection.
    # A weighted mean is pulled by a far district into empty land: Altamira's landed 94 km from the town, drawn by
    # Castelo de Sonhos about 900 km south.
    def _median(values: pd.Series, weights: pd.Series) -> float:
        order = values.argsort()
        v, w = values.iloc[order].to_numpy(), weights.iloc[order].to_numpy()
        return float(v[(w.cumsum() >= w.sum() / 2).argmax()])

    tr = population_points(root=grade_root)
    grouped = tr.groupby(tr["municipality7"].astype(str))
    weighted = pd.DataFrame({
        "x": grouped.apply(lambda g: _median(g["x"], g["population"])),
        "y": grouped.apply(lambda g: _median(g["y"], g["population"])),
        "people": grouped["population"].sum()})
    population = gpd.GeoSeries(gpd.points_from_xy(weighted["x"], weighted["y"]),
                               index=weighted.index, crs=ALBERS).to_crs("EPSG:4674")
    polygons = gpd.read_file(mesh)[["codarea", "geometry"]].set_crs("EPSG:4674", allow_override=True)
    polygons = polygons.set_index(polygons["codarea"].astype(str))["geometry"]
    centroids = polygons.to_crs(projected).centroid.to_crs("EPSG:4674")
    codes = sorted(set(polygons.index) | set(seats.index))
    frame = pd.DataFrame({"municipality7": codes})
    frame["municipality"] = frame["municipality7"].str[:6]
    for prefix, series in (("seat", seats), ("population", population), ("centroid", centroids)):
        points = gpd.GeoSeries(series.reindex(codes).values, crs="EPSG:4674")
        frame[f"{prefix}_lon"] = points.x.values
        frame[f"{prefix}_lat"] = points.y.values
    frame["population_grade_2022"] = weighted["people"].reindex(codes).values
    pts = {k: gpd.GeoSeries(gpd.points_from_xy(frame[f"{k}_lon"], frame[f"{k}_lat"]), crs="EPSG:4674").to_crs(projected)
           for k in ("seat", "population", "centroid")}
    frame["km_seat_to_population"] = (pts["seat"].distance(pts["population"]) / 1000).round(2)
    frame["km_seat_to_centroid"] = (pts["seat"].distance(pts["centroid"]) / 1000).round(2)
    frame.to_parquet(out_path, index=False)
    return {"municipalities": len(frame), "with_seat": int(frame["seat_lon"].notna().sum()),
            "with_population_centre": int(frame["population_lon"].notna().sum()),
            "km_seat_to_population_median": float(frame["km_seat_to_population"].median()),
            "km_seat_to_centroid_median": float(frame["km_seat_to_centroid"].median())}


@lru_cache(maxsize=1)
def _points() -> dict[str, dict[str, float]]:
    from importlib.resources import files

    import pyarrow.parquet as pq

    path = Path(str(files("pegasus_data.resources") / POINTS_PACK_NAME))
    if not path.exists():
        return {}
    rows = pq.read_table(path).to_pylist()
    return {str(r["municipality"]): r for r in rows} | {str(r["municipality7"]): r for r in rows}


class NoPointWarning(UserWarning):
    """A municipality has no point of the kind asked for, and why (`municipality_point`)."""


def municipality_point(code: str, kind: str = "population") -> tuple[float, float] | None:
    """(lon, lat) of a municipality: ``population`` (the Grade Estatística 2022 centre), ``seat`` or ``centroid``.

    None, with a `NoPointWarning` saying why, for a code with no such point: a municipality created after IBGE's 2022
    mesh has no polygon and no people placed in it (5101837 Boa Esperança do Norte), a district with no municipal seat in
    IBGE's localities has no seat (2605459 Fernando de Noronha), and an unknown code has nothing."""
    import warnings

    if kind not in ("population", "seat", "centroid"):
        raise ValueError("kind is population, seat or centroid")
    key = str(code).strip()
    row = _points().get(key)
    if not row:
        warnings.warn(f"{key}: not a municipality of the points pack", NoPointWarning, stacklevel=2)
        return None
    if row.get(f"{kind}_lon") is None:
        why = ("IBGE's 2022 municipal mesh has no polygon for it (created after the mesh), so no centroid and no people "
               "placed in it" if row.get("centroid_lon") is None else
               "IBGE's 2022 localities name no municipal seat for it" if kind == "seat" else
               "the Grade Estatística 2022 places no people in it")
        warnings.warn(f"{key}: no {kind} point: {why}", NoPointWarning, stacklevel=2)
        return None
    return float(row[f"{kind}_lon"]), float(row[f"{kind}_lat"])


def great_circle_km(lon1: Any, lat1: Any, lon2: Any, lat2: Any) -> Any:
    """Great-circle (haversine) distance in km between points in degrees; scalars or arrays (NaN stays NaN). The one
    distance code: `distance_km` and the linkage's residence levels both call it."""
    import numpy as np

    lon1, lat1, lon2, lat2 = (np.radians(np.asarray(x, dtype=float)) for x in (lon1, lat1, lon2, lat2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(h))


def distance_km(a: str, b: str, kind: str = "population") -> float | None:
    """Great-circle distance between two municipalities' points, in km (None when either is unknown)."""
    pa_, pb = municipality_point(a, kind), municipality_point(b, kind)
    if pa_ is None or pb is None:
        return None
    return float(great_circle_km(*pa_, *pb))


def _uf_codes(ufs: list[str]) -> list[int]:
    """IBGE state codes for sigla or numeric codes (``"SE"`` or ``"28"`` -> 28)."""
    by_sigla = uf_codes_by_sigla()
    out = []
    for uf in ufs:
        text = str(uf).strip().upper()
        code = by_sigla.get(text, text)
        if not str(code).isdigit():
            raise KeyError(f"unknown state {uf!r}")
        out.append(int(code))
    return sorted(set(out))

