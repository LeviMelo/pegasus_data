"""Code -> label lookups: the reference tables a rendered column is decoded with.

Split from ``view`` (2026-10-04): reading a codelist at its vintage, merging the
tables bound to a field in authority order, the hierarchy-aware maps (ICD-10,
SIGTAP, path tables), and applying a map to a column at exact width (§6.2).
Every map is cached per process and per table version; ``clear_lookup_caches``
is the one reset.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .identifiers import LABEL_PREFIX
from .persist.reference import read_reference_table

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
    _cached_registry.cache_clear()
    _cached_contradictions.cache_clear()
    _cached_merged_lookup.cache_clear()
    _MAPS_BY_CONTENT.clear()
    _REGISTRIES_BY_CONTENT.clear()


@lru_cache(maxsize=4096)
def _safe_name(codelist: str) -> str:
    """The directory a codelist is written under (`persist.reference._SAFE`)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", codelist)


@lru_cache(maxsize=4096)
def _is_registry(codelist: str) -> bool:
    from .registry import is_registry

    return is_registry(codelist)


def _reference_version(lake_root: Path, codelist: str) -> tuple[int, ...]:
    """What a reference table's content depends on, as file times.

    The lake's copy of the table and, for a registry, its cache files. Shipped canonical tables change only with the
    package, so they need no stamp. NOT cached: every map below is keyed on this stamp, and a stamp frozen at first use
    hid a reference rebuild by another process from a long-lived one (``serve/``) until restart, and kept a table
    absent at first use "absent" after it was written. It is one ``stat`` (a registry adds one directory scan).
    """
    stamps: list[int] = []
    try:
        stamps.append(os.stat(os.path.join(lake_root, "reference", _safe_name(codelist))).st_mtime_ns)
    except OSError:
        pass
    if _is_registry(codelist):
        from .config import load_settings

        try:
            registries = Path(load_settings().root) / "registries"
            stamps.extend(p.stat().st_mtime_ns for p in sorted(registries.glob(f"*/{codelist.upper()}.parquet")))
        except OSError:  # pragma: no cover - an unreadable home is not a cache key
            pass
    return tuple(stamps)


@lru_cache(maxsize=1)
def _packed_codelists() -> frozenset[str]:
    """Every code list the shipped label pack holds, in any validity window."""
    import pyarrow.parquet as pq

    path = Path(__file__).resolve().parent / "resources" / "labels.parquet"
    if not path.exists():
        return frozenset()
    return frozenset(str(v).upper() for v in pq.read_table(path, columns=["codelist"]).column(0).unique().to_pylist())


def _exists_anywhere(lake_root: Path, codelist: str) -> bool:
    """Does any version of this table exist, whatever the period asked?"""
    return codelist.upper() in _packed_codelists() or bool(_reference_version(lake_root, codelist))


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
        name in CLASSIFICATIONS or name in ("UF_BR", "CIR_BR", "MUNIC_BR7") or is_registry(name)
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
    only: frozenset[str] | None = None,
) -> Mapping[str, str]:
    """``_lookup_map_uncached``, built once per process per table version.

    A year of monthly files renders as twelve groups, and each rebuilt the same
    maps: 7 of a 17-second one-month query was reading and re-reading reference
    tables (profiled 2026-09-29), the 692,004-row establishment registry among
    them. Callers only read the result.
    """
    if _vintage_free(codelist):
        year = competencia = None
    version = _reference_version(Path(lake_root), codelist)
    if only is not None:
        # ``only``: the codes a column holds. A registry is cut to them, from
        # Arrow arrays cleaned once per table version, before any label
        # becomes a Python string.
        cleaned = _cached_registry(str(lake_root), codelist, system, year, competencia, code_width, version)
        if cleaned is not None:
            return _code_map(*cleaned, only=only)
    return _cached_lookup_map(str(lake_root), codelist, system, year, competencia, code_width, version)


@lru_cache(maxsize=256)
def _cached_lookup_map(
    lake_root: str, codelist: str, system: str | None, year: int | None,
    competencia: int | None, code_width: int | None, version: tuple[int, ...],
) -> Mapping[str, str]:
    return _lookup_map_uncached(
        Path(lake_root), codelist, system=system, year=year, competencia=competencia, code_width=code_width
    )


@lru_cache(maxsize=32)
def _cached_registry(
    lake_root: str, codelist: str, system: str | None, year: int | None,
    competencia: int | None, code_width: int | None, version: tuple[int, ...],
) -> tuple[pa.Array, pa.Array, frozenset[int]] | None:
    """A registry's cleaned codes and labels, or None for a table small enough
    to become one dict (``REGISTRY_ROWS``)."""
    table = read_reference_table(
        Path(lake_root), codelist, system=system, year=year, competencia=competencia, code_width=code_width,
    )
    if table.num_rows <= REGISTRY_ROWS:
        return None
    # Asked month by month, a registry is usually one table twelve times.
    key = (codelist, _content_digest(table))
    if key not in _REGISTRIES_BY_CONTENT:
        if len(_REGISTRIES_BY_CONTENT) > 16:
            _REGISTRIES_BY_CONTENT.clear()
        _REGISTRIES_BY_CONTENT[key] = _cleaned(table)
    return _REGISTRIES_BY_CONTENT[key]


_REGISTRIES_BY_CONTENT: dict[tuple[str, bytes], tuple[pa.Array, pa.Array, frozenset[int]]] = {}


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

#: Above this many rows a table is cut to a column's own codes before it becomes
#: a dict. CADGERBR (692,004 establishments) cost 0.9 s of a 7-second query to
#: label a few dozen hospitals, 0.7 s of it turning Arrow strings into Python
#: ones (profiled 2026-10-04).
REGISTRY_ROWS = 100_000


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


def _map_from_table(table: pa.Table) -> CodeMap:
    """``code -> label``: last line wins, and blank labels are dropped."""
    return _code_map(*_cleaned(table))


def _cleaned(table: pa.Table) -> tuple[pa.Array, pa.Array, frozenset[int]]:
    """A table's usable codes and labels, in order, and the code widths among them."""
    # Nulls and blanks are dropped in Arrow, before 700,000 registry rows
    # become Python strings; order is kept, so the dict below still lets the
    # last line win.
    codes = pc.cast(table.column("code"), pa.string())
    labels = pc.cast(table.column("label"), pa.string())
    # No CNPJ or CPF inside a label (ADR-0102): DATASUS's registry tables glue
    # them onto names, CPFs of sole practitioners among them.
    labels = pc.replace_substring_regex(labels, pattern=LABEL_PREFIX.pattern, replacement="")
    keep = pc.and_(
        pc.and_(pc.is_valid(codes), pc.is_valid(labels)),
        pc.not_equal(pc.utf8_trim_whitespace(labels), ""),
    )
    codes, labels = pc.filter(codes, keep), pc.filter(labels, keep)
    widths = frozenset(int(w) for w in pc.unique(pc.utf8_length(codes)).to_pylist() if w is not None)
    return codes, labels, widths


def _code_map(
    codes: pa.Array, labels: pa.Array, widths: frozenset[int], *, only: frozenset[str] | None = None,
) -> CodeMap:
    """The dict, cut to ``only`` when given. ``widths`` stay the whole table's,
    so the width check (§6.2) sees the table as it is."""
    if only is not None:
        wanted = pc.is_in(codes, value_set=pa.array(sorted(only), type=pa.string()))
        codes, labels = pc.filter(codes, wanted), pc.filter(labels, wanted)
    # Last write wins, matching .CNV semantics, where a later line deliberately
    # overrides an earlier one. A blank label is dropped rather than stored: an
    # empty string is not a translation, and offering one turns a labelled column
    # into a column of nothing while still reporting that it was labelled. This
    # is how CADMUN behaved — a DBF lookup that picked OBSERV as its label
    # column, which is blank for 5,517 of its 5,579 rows.
    built = CodeMap(zip(codes.to_pylist(), labels.to_pylist(), strict=True))
    built.widths = widths
    return built


def _single_lookup(
    lake_root: Path,
    codelist: str,
    system: str | None,
    year: int | None,
    code_width: int | None,
    competencia: int | None = None,
) -> Mapping[str, str] | None:
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
    only: frozenset[str] | None = None,
) -> tuple[Mapping[str, str], list[str]]:
    """Every table bound to a field, merged in authority order, once per process.

    It was rebuilt for every render group, and a group is a month: merging the
    692,004-row registry twelve times was 16 million ``setdefault`` calls in a
    year's query (ADR-0097). Tables with no vintages drop the year from the key.
    """
    if all(_vintage_free(c) for c in codelists):
        year = competencia = None
    if any(str(c).upper() in HIERARCHICAL_CODELISTS or str(c).upper() in PATH_CODELISTS for c in codelists):
        # These answer codes the column does not literally hold (a category
        # for an unlisted subcategory): never cut to the observed ones.
        only = None
    versions = tuple(_reference_version(Path(lake), c) for c in codelists)
    return _cached_merged_lookup(str(lake), codelists, system, year, competencia, versions, only)


@lru_cache(maxsize=512)
def _cached_merged_lookup(
    lake: str, codelists: tuple[str, ...], system: str | None, year: int | None,
    competencia: int | None, versions: tuple[tuple[int, ...], ...],
    only: frozenset[str] | None = None,
) -> tuple[Mapping[str, str], list[str]]:
    missing: list[str] = []
    maps: list[Mapping[str, str]] = []
    for codelist in codelists:
        try:
            maps.append(_lookup_map(
                Path(lake), codelist, system=system, year=year, competencia=competencia, code_width=None,
                only=only,
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
    else:
        # A path table keeps its path behaviour behind a column's own inline
        # codes: SIH-SP SERV_CLA curates 000000 ahead of S_CLASSEN, and 126000
        # (service 126, no classification) stopped being named by its service
        # when the chain became two tables (2026-09-30).
        tables = [str(c).upper() for c in codelists if not str(c).upper().startswith("CURATED.")]
        if len(tables) == 1 and tables[0] in PATH_CODELISTS:
            merged = PathLabels(merged, table=tables[0], segment=PATH_CODELISTS[tables[0]])
    merged.widths = frozenset().union(*(_widths(m) for m in maps))  # type: ignore[union-attr]
    return merged, missing


def _widths(lookup: Mapping[str, str]) -> set[int]:
    known = getattr(lookup, "widths", None)
    return set(known) if known else {len(code) for code in lookup}



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
        if len(code) == 5 and code[3] == "." and code[4].isalnum():
            # WHO's dotted notation of the same code: SINAN-PFA writes its
            # differential diagnoses as "G61.0" (CON_DESCAR, ATE_HIPOTE).
            # Dropping the dot changes the notation, not the code (§6.2).
            return self.get(code[:3] + code[4], default)
        if len(code) == 4 and code[:3].isalnum() and code[3] != "X":
            category = super().get(code[:3]) or super().get(f"{code[:3]}X")
            if category is not None and code[3] == ".":
                # "A16." is the category with its subcategory left blank, not
                # a subcategory missing from ICD-10 (SINAN-TB: 1,513 records in
                # TUBEBR20, 2,289 in TUBEBR25; DATA_SOURCES §1.9).
                return f"{category} — categoria {code[:3]} (subcategoria não informada)"
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
#: Tables that label codes they do not list (ADR-0089): never cut to a column's codes.
HIERARCHICAL_CODELISTS = frozenset({"ICD10", "SIGTAP"})


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


def _per_distinct(codes: object, fn: Callable[[Any], str | None]) -> pa.Array:
    """``fn`` of every value, computed once per distinct value and expanded by
    index; a null stays null. A file is a million cells and a few dozen
    distinct codes: the row loops this replaced were most of a role table's
    build (CIHA PR 2022, 1.4M rows: 35 of 40 s in rendering, 2026-10-03)."""
    if not isinstance(codes, (pa.Array, pa.ChunkedArray)):
        return pa.array([None if v is None else fn(v) for v in codes], type=pa.string())  # type: ignore[attr-defined]
    column = codes.combine_chunks() if isinstance(codes, pa.ChunkedArray) else codes
    encoded = pc.dictionary_encode(column)
    mapped = pa.array([None if u is None else fn(u) for u in encoded.dictionary.to_pylist()], type=pa.string())
    return mapped.take(encoded.indices)


def _distinct(column: object) -> list:
    """The distinct non-null values of a column (Arrow does the pass)."""
    if isinstance(column, (pa.Array, pa.ChunkedArray)):
        return [v for v in pc.unique(column).to_pylist() if v is not None]
    return list({v for v in column if v is not None})  # type: ignore[attr-defined]


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
    observed = {len(str(v).strip()) for v in _distinct(column)}
    if not observed:
        return None
    unmatched = observed - table_widths
    return (
        f"{field_name}: codelist {codelist!r} mixes code widths {sorted(table_widths)}; "
        f"the column holds widths {sorted(observed)}"
        + (f", of which {sorted(unmatched)} match nothing" if unmatched else "")
        + ". Widths are matched exactly and never padded or truncated (§6.2)"
    )
