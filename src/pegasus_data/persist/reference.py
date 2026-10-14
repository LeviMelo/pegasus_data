"""Reference code tables as first-class, version-scoped lake citizens.

Why these are not materialised as ``<field>_label`` columns
-----------------------------------------------------------

For a small closed codelist — ``SEXO`` has three categories, ``IDENT`` three —
writing the label beside the code is cheap and unambiguous, and §7.1 step 3 is
right to ask for it.

For a large hierarchical classification it is the wrong shape, for three reasons
that have nothing to do with footprint:

1. **It fixes a granularity choice invisibly.** ``E11`` and ``E119`` are distinct
   rows in the CID-10 table. Materialising one label makes whichever codelist won
   a coverage ranking into *the* answer, and the analyst inherits that choice
   without being told a choice was made. Chapter, block and category are all
   legitimate levels and the consumer must pick.

2. **It freezes a time-varying assertion.** The 1992–1997 kit's CID-10 has 14,197
   rows; the current one has 14,253, and they disagree about labels in between.
   ``dictionary.valid_from``/``valid_to`` exist precisely to keep both true. A
   string baked into a 2019 row throws that scoping away and cannot be corrected
   without rewriting the lake.

3. **The published wording is dated and abbreviated.** ``DESCR`` is a 50-character
   field: ``N39.0`` reads "Infecc do trato urinario de localiz NE", and ICD-10's
   pt-BR wording for several endocrine codes is clinically obsolete. Freezing it
   into every row presents a lossy legacy string as the meaning of the code.

So the code tables are written to ``lake/reference/<table>/window=.../`` and
joined on demand, at the granularity and vintage the consumer chooses. Nothing is
lost: meaning is still fully recoverable, which is what P1 requires, and
``describe()`` still resolves it — it just names the table and the window rather
than pretending one string is the answer.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .._lazy import LazyModule
from ..catalog.store import CatalogStore
from .decisions import (
    borrowed_tables,
    collecting,
    fallback_vintages,
    note_borrowed,
    note_fallback,
    note_pack_fallback,
)
from .staging import staged_tree

pads = LazyModule("pyarrow.dataset")

__all__ = [
    "borrowed_tables",
    "collecting",
    "fallback_vintages",
    "note_borrowed",
    "note_fallback",
    "note_pack_fallback",
    "read_reference_table",
    "write_reference_tables",
    "systems_with_tables",
]

_SAFE = re.compile(r"[^A-Za-z0-9_.=-]+")

#: Tables that are hierarchical classifications rather than closed codelists.
#: A field bound to one of these gets a join, not a materialised label column.
HIERARCHICAL_TABLES: frozenset[str] = frozenset(
    {"CID10", "CID9", "TPROC", "TPROC10", "EMUSO", "EMUSO10", "MUNICBR", "MUNIDB", "CBO", "TCBO"}
)

#: Above this many distinct labels a codelist is treated as a classification even
#: if it is not named above — the distinction is size and hierarchy, not identity.
LARGE_CODELIST_LABELS = 200


@dataclass(slots=True)
class ReferenceTable:
    table_id: str
    system: str
    valid_from: str | None
    valid_to: str | None
    rows: int
    relative_path: str
    source_ref: str
    code_widths: tuple[int, ...] = ()

    @property
    def mixed_widths(self) -> bool:
        """Two code widths in one table means two classifications merged."""
        return len(self.code_widths) > 1

    @property
    def window(self) -> str:
        if self.valid_from and self.valid_to:
            return f"{self.valid_from}-{self.valid_to}"
        return "current"


def is_hierarchical(catalog: CatalogStore, codelist: str) -> bool:
    """Whether a codelist should be joined rather than flattened into labels."""
    name = codelist.upper()
    if any(name.startswith(prefix) for prefix in HIERARCHICAL_TABLES):
        return True
    labels = catalog.scalar(
        "SELECT COUNT(DISTINCT value_label) FROM dictionary WHERE value_group = ?", (codelist,)
    )
    return int(labels or 0) > LARGE_CODELIST_LABELS


def _materialise_reference_tables(
    staging: Path,
    catalog: CatalogStore,
    *,
    compression: str,
    systems: Sequence[str] | None,
    root: Path,
    lake_root: Path,
) -> list[ReferenceTable]:
    """Write every reference table INTO `staging`. Knows nothing about swapping.

    Separated so the durability rule lives in exactly one place
    (:func:`~pegasus_data.persist.staging.staged_tree`) rather than being
    hand-rolled here and again in the lake. This function only has to get the
    content right; it cannot leave a half-built warehouse behind.
    """

    written: list[ReferenceTable] = []

    # One ordered scan, grouped as it streams. Querying per (table, window) meant
    # ~500 separate scans of a 3.4-million-row table, which is quadratic in the
    # number of codelists and dominated the stage.
    # `systems` bounds the rebuild. Materialising EVERY code table for every
    # system is a build-stage side effect, and it used to fire from inside an
    # ordinary interactive fetch: a request for SIH sex and age rebuilt the
    # codelists of all twenty systems first.
    system_clause = ""
    params: list[object] = []
    if systems:
        marks = ",".join("?" for _ in systems)
        system_clause = f" AND system IN ({marks})"
        params = [s.upper() for s in systems]

    cursor = catalog.execute(
        f"""
        SELECT value_group, valid_from, valid_to, value_raw, value_label, source, source_ref,
               confidence, system
          FROM dictionary
         WHERE value_group IS NOT NULL{system_clause}
         ORDER BY value_group, system, valid_from, value_raw
        """,
        params,
    )

    current_key: tuple[str, str, str | None, str | None] | None = None
    batch: list[tuple[Any, ...]] = []

    def _flush() -> None:
        # Any non-empty group is written. This used to require two rows, so a
        # codelist/system/window holding exactly ONE legitimate code was absent
        # from the reference lake with no warning — and a one-code enumeration
        # is a perfectly ordinary thing for DATASUS to publish (a single "not
        # applicable" value, a flag with one meaningful state). A caller then
        # saw "no reference table" and could not tell that from a table that
        # exists and decodes nothing.
        if current_key is None or not batch:
            return
        table_id, system, valid_from, valid_to = current_key
        table = pa.table(
            {
                "code": pa.array([str(e[0]) for e in batch], type=pa.string()),
                "label": pa.array([e[1] for e in batch], type=pa.string()),
                "source": pa.array([e[2] for e in batch], type=pa.string()),
                "source_ref": pa.array([e[3] for e in batch], type=pa.string()),
                "confidence": pa.array([float(e[4] or 0) for e in batch], type=pa.float32()),
                # Code width separates classifications that a kit ships merged.
                # `CBO` in the current SIH kit holds 3,000 three-digit CBO-1994
                # codes and 2,813 six-digit CBO-2002 codes in one file; joining
                # without the width would let a 1994 code label 2002 data.
                "code_width": pa.array([len(str(e[0])) for e in batch], type=pa.int8()),
                "valid_from": pa.array([valid_from] * len(batch), type=pa.string()),
                "valid_to": pa.array([valid_to] * len(batch), type=pa.string()),
            }
        )
        window = str(valid_from or "current")
        # The partition key is `window`, not `valid_from`: a hive key of the same
        # name as a data column shadows it, and the string "current" would come
        # back where the real NULL belongs.
        directory = (
            staging
            / _SAFE.sub("_", table_id)
            / f"system={_SAFE.sub('_', system)}"
            / f"window={_SAFE.sub('_', window)}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "part-00000.parquet"
        pq.write_table(table, target, compression=compression, use_dictionary=True)
        written.append(
            ReferenceTable(
                table_id=table_id,
                system=system,
                valid_from=valid_from,
                valid_to=valid_to,
                rows=table.num_rows,
                # Relative to where the table will LIVE, not where it is being
                # staged: the caller records this and reads it after the swap.
                relative_path=str(
                    (root / target.relative_to(staging)).relative_to(Path(lake_root))
                ).replace("\\", "/"),
                source_ref=str(batch[0][3]),
                code_widths=tuple(sorted({len(str(e[0])) for e in batch})),
            )
        )

    for row in cursor:
        key = (str(row[0]), str(row[8] or "UNKNOWN"), row[1], row[2])
        if key != current_key:
            _flush()
            current_key = key
            batch = []
        batch.append((row[3], row[4], row[5], row[6], row[7]))
    _flush()
    return written


def write_reference_tables(
    catalog: CatalogStore,
    lake_root: str | Path,
    *,
    compression: str = "zstd",
    systems: Sequence[str] | None = None,
) -> list[ReferenceTable]:
    """Materialise every code table, scoped by **system** and by validity window.

    Scoping by system is not a refinement — it is the difference between a usable
    lookup and a contradictory one. Thirteen systems ship a file called
    ``SEXO.CNV`` and they do not agree: SIHSUS codes sex as 1/3, SINASC as 1/2,
    SINAN as M/F. Keying the reference table on the codelist name alone merged
    all thirteen into one table in which ``1`` meant Masculino *and* Feminino,
    and any label drawn from it was a coin toss.

    Measured on the full catalog: 311,844 (code, window) pairs carried more than
    one label when systems were merged, across 264 codelists. Grouped by system
    as well, that number is **zero** — every one of those tables is internally
    consistent, and the contradiction was manufactured entirely here.
    """
    root = Path(lake_root) / "reference"
    # Derived output is replaced, not accumulated (§3). It also has to be, since
    # the directory layout gained a level: a stale `window=` directory sitting
    # beside a new `system=` one makes a hive dataset that will not open.
    # Staged, then swapped. This used to rmtree(root) and rebuild in place, so a
    # failure halfway left the reference warehouse partly absent — and because
    # labelled reads can trigger this rebuild implicitly, an ordinary
    # interactive request could degrade an otherwise working installation.
    # The same rule the lake uses, from the same place. `merge=` is the one
    # genuine difference between the two artifacts: a scoped rebuild must not
    # delete the tables it was not asked about, so it merges its subtrees over
    # the existing tree instead of swapping the whole thing out.
    # Depth 2, because the layout is `<codelist>/system=<sys>/window=<w>` and
    # the scope is a SYSTEM. Merging at depth 1 replaces the whole `<codelist>`
    # directory, which deletes every other system's copy of that codelist —
    # the exact loss the merge path exists to prevent.
    with staged_tree(
        root, merge_depth=2 if (systems and root.exists()) else 0
    ) as staging:
        written = _materialise_reference_tables(
            staging,
            catalog,
            compression=compression,
            systems=systems,
            # Paths are recorded relative to where the tables will LIVE, not
            # where they are being staged: the caller reads them after the swap.
            root=root,
            lake_root=Path(lake_root),
        )
    # Each system's lookups carry the fingerprint of the dictionary they were written from (`stale_systems`).
    _write_stamps(catalog, root, systems or sorted({str(t.system) for t in written}))
    # The render path caches its lookups for the life of the process; tables
    # were just (re)written underneath it. See lookups.clear_lookup_caches.
    from ..lookups import clear_lookup_caches

    clear_lookup_caches()
    return written


STAMPS = "_stamps.json"


_FINGERPRINTS: dict[tuple, str] = {}


def dictionary_fingerprint(catalog: CatalogStore, system: str) -> str:
    """What a system's lookups are written from: its dictionary rows (count and the lengths of their codes and labels)
    and the curation (curated codelists are inline). A lookup written from another fingerprint is stale. Computed once
    per process for a catalog file's state (its modification time): a check on every read cost 27 s a call."""
    import hashlib

    from ..config import curation_root
    from ..semantics.curation import codelist_fingerprint

    path = getattr(catalog, "path", None) or getattr(catalog, "db_path", None)
    state = (str(path), Path(path).stat().st_mtime_ns if path and Path(path).exists() else None, system)
    if state[1] is not None and state in _FINGERPRINTS:
        return _FINGERPRINTS[state]
    row = catalog.query("SELECT count(*) AS n, coalesce(sum(length(value_label)), 0) AS l, "
                        "coalesce(sum(length(value_raw)), 0) AS r FROM dictionary WHERE system = ?", (system,))[0]
    text = f"{row['n']}|{row['l']}|{row['r']}|{codelist_fingerprint(curation_root())}"
    out = hashlib.sha256(text.encode()).hexdigest()[:16]
    if state[1] is not None:
        _FINGERPRINTS[state] = out
    return out


def _write_stamps(catalog: CatalogStore, root: Path, systems: Sequence[str]) -> None:
    import json

    path = root / STAMPS
    stamps = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for system in systems:
        stamps[str(system).upper()] = dictionary_fingerprint(catalog, str(system).upper())
    path.write_text(json.dumps(stamps, indent=1, sort_keys=True), encoding="utf-8")


def stale_systems(catalog: CatalogStore, lake_root: str | Path, systems: Sequence[str]) -> list[str]:
    """The systems among ``systems`` whose lookups were written from another dictionary than the catalog holds now (or
    carry no stamp). The lookups were written once and never again: SINAN's labels kept the codelist's match
    expression ("Ign/Branco ,9 ,09,99,") for weeks after the dictionary was corrected (2026-10-07)."""
    import json

    path = Path(lake_root) / "reference" / STAMPS
    stamps = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return [s for s in (str(x).upper() for x in systems) if stamps.get(s) != dictionary_fingerprint(catalog, s)]


def flag_mixed_width_tables(catalog: CatalogStore, tables: Sequence[ReferenceTable]) -> int:
    """Record any reference table that merges two code widths.

    Not a defect in the ingestion — it is what the kit ships — but a hazard the
    consumer has to know about, because the two widths are different
    classifications with overlapping numeric ranges.
    """
    flagged = 0
    for t in tables:
        if not t.mixed_widths:
            continue
        flagged += 1
        catalog.note_question(
            f"reference.mixed_code_widths:{t.table_id}",
            area="semantics",
            question=(
                f"Reference table {t.table_id} ({t.window}) mixes code widths {list(t.code_widths)}, "
                f"which means it merges more than one classification vintage in a single file. "
                f"Joining on code alone can label data from one vintage with the other's meanings."
            ),
            verification_procedure=(
                "Filter the reference table by `code_width` matching the width actually observed "
                "in the column being decoded, and confirm against the record layout's declared "
                "width for that field."
            ),
            blocking=f"safe decoding of fields bound to {t.table_id}",
        )
    return flagged


# The bookkeeping lives in `decisions`, which imports neither this module nor
# `labelpack`. It used to live here, and `labelpack` imported it while this
# module imports `labelpack` for the fresh-install fallback — a cycle that only
# survived because both imports were hidden inside functions.
#
# Re-exported so every existing caller keeps working.


@functools.lru_cache(maxsize=1)
def _states() -> pa.Table:
    """IBGE states by numeric code AND by abbreviation -> full name (ADR-0087).

    SINAN's SG_UF_NOT 32 read "ES", SINASC's CODUFNATU 12 read "AC": an
    abbreviation is a code. Derived from the shipped municipalities resource.
    """
    from importlib.resources import files as _files

    import pyarrow.parquet as _pq

    rows = _pq.read_table(
        str(_files("pegasus_data.resources") / "municipalities.parquet"),
        columns=["uf_code", "uf_sigla", "uf_name"],
    ).to_pylist()
    names: dict[str, str] = {}
    for r in rows:
        names[str(r["uf_code"])] = str(r["uf_name"])
        names[str(r["uf_sigla"])] = str(r["uf_name"])
    return pa.table({"code": list(names), "label": list(names.values())})


#: IBGE's seven-digit municipality codes (ADR-0118).
MUNIC_BR7 = "MUNIC_BR7"


@functools.lru_cache(maxsize=1)
def _municipalities7() -> pa.Table:
    """Seven-digit IBGE municipality code -> "Name, UF" (ADR-0118).

    DATASUS's own tables are six digits. Older SINAN files write the full IBGE
    code with its check digit (LTAN 2003: 28,338 of 28,441 are current IBGE
    codes), which exact-width matching rightly left undecoded against them.
    The current division: a renamed municipality reads its current name.
    """
    from importlib.resources import files as _files

    import pyarrow.parquet as _pq

    rows = _pq.read_table(
        str(_files("pegasus_data.resources") / "municipalities.parquet"),
        columns=["code7", "name", "uf_sigla"],
    ).to_pylist()
    return pa.table({"code": [str(r["code7"]) for r in rows],
                     "label": [f"{r['name']}, {r['uf_sigla']}" for r in rows]})


#: SIA's pre-2008 establishments, keyed by state + code (ADR-0103).
SIA_UPS_TABLE = "SIA_UPS_BR"
_UF_CODES = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)


def _legacy_sia_establishments(
    lake_root: str | Path, *, year: int | None, competencia: int | None
) -> pa.Table:
    """SIA's pre-2008 establishment codes, one table, keyed ``UF + code``.

    Before 2008 SIA identified a unit by a 6-digit code that is unique only
    WITHIN its state: 14,187 codes name different establishments in different
    states (``000001`` is Hospital de Base in Acre and another unit in
    Alagoas). TabWin picks ``UPS-N<UF>`` (kits 1994-2003) or ``CNESN<UF>``
    (2003-2007, split into parts for MG and SP) by the file's state. Here the
    state goes into the code, and the record's key carries its file's state
    (``key: ["@UF", …]``). The vintage windows of each kit are kept.
    """
    codes: list[str] = []
    labels: list[str | None] = []
    for uf in _UF_CODES:
        for table_id in (f"UPS-N{uf}", f"CNESN{uf}", f"CNESN{uf}1", f"CNESN{uf}2", f"CNESN{uf}3"):
            try:
                part = read_reference_table(
                    lake_root, table_id, system="SIASUS", year=year, competencia=competencia
                )
            except (FileNotFoundError, KeyError):
                continue
            codes.extend(f"{uf}{c}" for c in part.column("code").to_pylist())
            labels.extend(part.column("label").to_pylist())
    return pa.table({"code": pa.array(codes, pa.string()), "label": pa.array(labels, pa.string())})


@functools.lru_cache(maxsize=1)
def _health_regions() -> pa.Table:
    """IBGE health regions (CIR, 5 digits) -> name, from the shipped geography.

    SINAN files Espírito Santo's regions as CIR codes (32002): measured
    2026-09-29, all 568 such rows in SINAN-HANS 2023 match their notifying
    municipality's CIR, none its colegiado, whose codes reuse the same numbers
    for other regions (32002 is "ES Metropolitana" as a CIR, "Colatina" as a
    colegiado).
    """
    from importlib.resources import files as _files

    import pyarrow.parquet as _pq

    rows = _pq.read_table(
        str(_files("pegasus_data.resources") / "geography.parquet"),
        columns=["classification", "member_code", "member_label", "source_codelist"],
    ).to_pylist()
    names = {
        str(r["member_code"]): str(r["member_label"])
        for r in rows
        if r["classification"] == "health_region" and r["source_codelist"] == "CIRBRN" and r["member_label"]
    }
    return pa.table({"code": list(names), "label": list(names.values())})


#: Standard classifications served from one canonical table for every system
#: (ADR-0087): name -> file under pegasus_data/resources.
CLASSIFICATIONS: dict[str, str] = {
    "ICD10": "icd10.parquet", "CBO2002": "cbo2002.parquet", "BANCO_BR": "banks.parquet",
    "SIGTAP": "sigtap.parquet", "CNAE20": "cnae20.parquet",
    "NATURALIDADE": "countries.parquet",
}


def read_reference_table(
    lake_root: str | Path,
    table_id: str,
    *,
    system: str | None = None,
    valid_from: str | None = None,
    year: int | None = None,
    competencia: int | None = None,
    code_width: int | None = None,
    registries: str | Path | None = None,
) -> pa.Table:
    """``_read_reference_table``, falling back to the systems this one inherits.

    A system that republishes another's fields (``curation.INHERITS``:
    DADOS_ABERTOS carries SIASUS's APAC columns) decodes them against the
    parent's own copy when it ships none (ADR-0095). Declared inheritance is
    not borrowing: it names the one system the field belongs to.
    """
    from ..semantics.curation import INHERITS

    kwargs = {
        "valid_from": valid_from, "year": year, "competencia": competencia, "code_width": code_width,
        "registries": registries,
    }
    parents = INHERITS.get(str(system).upper(), ()) if system else ()
    try:
        return _read_reference_table(lake_root, table_id, system=system, **kwargs)  # type: ignore[arg-type]
    except FileNotFoundError:
        for parent in parents:
            try:
                return _read_reference_table(lake_root, table_id, system=parent, **kwargs)  # type: ignore[arg-type]
            except FileNotFoundError:
                continue
        raise


def _read_reference_table(
    lake_root: str | Path,
    table_id: str,
    *,
    system: str | None = None,
    valid_from: str | None = None,
    year: int | None = None,
    competencia: int | None = None,
    code_width: int | None = None,
    registries: str | Path | None = None,
) -> pa.Table:
    """Load one reference table, optionally the vintage covering a given year.

    Asking for a ``year`` picks the window that contains it, which is the whole
    point of keeping the windows apart: a 1995 admission decodes against the
    1992–1997 table, not against today's.

    ``competencia`` (``AAAAMM``) asks the same question a month at a time.
    ``valid_from``/``valid_to`` are stored as ``AAAAMM``, so a codelist revised
    in July is two windows inside one calendar year and ``year=`` cannot choose
    between them — it matches any window overlapping the year, which for a
    mid-year revision is both. Pass ``competencia`` where the source semantics
    turn over mid-year; ``year`` remains the right question for the common case
    of a table that changes at most once a year.

    Asking for a ``system`` picks that system's own copy of the codelist, which
    matters just as much. A field belonging to SIHSUS must decode against
    SIHSUS's ``SEXO.CNV`` (1 = Masculino, 3 = Feminino) and not against the union
    of thirteen systems that disagree. Where the requested system ships no copy,
    the lookup is refused by default. Foreign-system mappings are available only
    inside an explicit ``borrowed_label_policy(True)`` scope.

    A registry (CADGER*: establishment names) is not in the lake: it is read from ``registries``, the
    ``Settings.registries_dir`` of the root in use (OQ 81); a caller that names none finds no registry (the read goes
    on to the lake and the pack, as for a registry that is not built), never the default home's.
    """
    from ..registry import is_registry
    from ..registry import lookup as registry_lookup
    from ..semantics.curation import inline_codelist

    if table_id.upper() == "UF_BR":
        return _states()
    if table_id.upper() == "CIR_BR":
        return _health_regions()
    if table_id.upper() == MUNIC_BR7:
        return _municipalities7()
    if table_id.upper() == SIA_UPS_TABLE:
        return _legacy_sia_establishments(lake_root, year=year, competencia=competencia)
    canonical = CLASSIFICATIONS.get(table_id.upper())
    if canonical is not None:
        # A published standard classification, one table for every system
        # (ADR-0087): DATASUS's official ICD-10 with full descriptions, where
        # each system's own .CNV carries "N03.9 NE".
        from importlib.resources import files as _files

        import pyarrow.parquet as _pq

        return _pq.read_table(str(_files("pegasus_data.resources") / canonical), columns=["code", "label"])
    if is_registry(table_id):
        # A registry (CADGER*: establishment names) comes from the system's own
        # CURRENT kit, built by `pegasus-data registries build` into the root in
        # use's registries directory (ADR-0086, ADR-0176); the pack's partial copy
        # is older and incomplete.
        registry = registry_lookup(table_id, system, registries) if registries is not None else None
        if registry is not None:
            return registry

    inline = inline_codelist(table_id)
    if inline is not None:
        # Written in the curation itself; one vintage, no system copies (ADR-0079).
        return pa.table({"code": list(inline), "label": list(inline.values())})
    base = Path(lake_root) / "reference" / _SAFE.sub("_", table_id)
    if not base.exists():
        # Nothing in the lake. Fall back to the label pack the package ships,
        # which is what lets `fetch(labels=True)` work on a fresh install: the
        # lake is built from a 14 GB catalog no user has any reason to build,
        # so without this, data came back and nothing was ever translated.
        from ..labelpack import read_packed

        try:
            # The vintage travels with the request. Dropping it here is what
            # made the fresh-install fallback answer a historical question with
            # today's labels while the warehouse answered it correctly.
            return read_packed(
                table_id,
                system=system,
                code_width=code_width,
                year=year,
                competencia=competencia,
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"no reference table {table_id!r} in the lake or the shipped "
                "label pack; run `pegasus-data reference` to materialise it"
            ) from None

    table, _scope = _scoped_table(base, table_id, system, code_width)
    if valid_from is not None:
        return table.filter(pc.fill_null(pc.equal(pc.cast(table.column("valid_from"), pa.string()), valid_from), False))
    if competencia is not None or year is not None:
        # A competencia is one month; a year is any window overlapping it.
        if competencia is not None:
            span_lo = span_hi = int(competencia)
            asked = str(int(competencia))
        else:
            span_lo, span_hi = year * 100 + 1, year * 100 + 12  # type: ignore[operator]
            asked = str(year)
        # as text: an all-null column (an open-ended table's bounds) is typed null, which the string kernels refuse
        start = pc.cast(table.column("valid_from"), pa.string())
        end = pc.cast(table.column("valid_to"), pa.string())
        # a window is dated by AAAAMM bounds, an open end running on; anything else is the open-ended table published
        # today. Judged in Arrow: a Python loop over the table's rows was 153 ms of MUNICBR's 25,733 on its own.
        is_dated = pc.fill_null(pc.match_substring_regex(start, r"^\d+$"), False)
        lo = pc.cast(pc.if_else(is_dated, start, "0"), pa.int64())
        has_end = pc.fill_null(pc.match_substring_regex(end, r"^\d+$"), False)
        hi = pc.cast(pc.if_else(has_end, end, "999912"), pa.int64())
        covers = pc.and_(is_dated, pc.and_(pc.less_equal(lo, span_hi), pc.less_equal(span_lo, hi)))
        # A window that explicitly covers the request wins.
        matched = table.filter(covers)
        if matched.num_rows:
            return matched
        # Otherwise the open-ended table stands in. That is a real answer, but
        # it is not the vintage that was asked for, so it is RECORDED.
        fallback = table.filter(pc.invert(is_dated))
        table_key = _SAFE.sub("_", table_id)
        if fallback.num_rows:
            note_fallback(table_key, asked, "current")
            return fallback
        # Nothing covers the request and there is no open-ended table either.
        # This used to return the WHOLE table — every historical window at once
        # — which is the one thing the no-year branch below exists to prevent:
        # it merges windows that disagree and manufactures a contradiction out
        # of ordinary editorial drift. An unresolved request is answered as
        # unresolved.
        note_fallback(table_key, asked, "unresolved")
        return table.slice(0, 0)

    # No year asked for: give the CURRENT vintage, not every vintage at once.
    # RECORDED all the same (translate()'s docstring promises the report says
    # which vintage was applied): "correct for recent data and wrong for a 1998
    # extract" is a judgement only the caller can make, and they can only make
    # it if the substitution is visible.
    # Merging windows is never what a caller wants and manufactures a
    # contradiction out of ordinary editorial drift — SIHSUS's CID10 renders
    # C96.7 as "…tec linf hematop e relac" today and "…e corr" in the 1992–1997
    # kit, which is one code with a reworded label, not two meanings. A caller
    # who wants a specific vintage names a year; everyone else means "now".
    if "valid_from" in table.schema.names:
        start = pc.cast(table.column("valid_from"), pa.string())
        open_ended = pc.fill_null(pc.equal(pc.utf8_trim_whitespace(start), ""), True)
        if pc.any(open_ended).as_py():
            note_fallback(_SAFE.sub("_", table_id), "unscoped", "current")
            return table.filter(open_ended)
        if pc.any(pc.is_valid(start)).as_py():
            newest = pc.max(start).as_py()
            return table.filter(pc.fill_null(pc.equal(start, newest), False))
    return table


def _scoped_table(
    base: Path, table_id: str, system: str | None, code_width: int | None,
) -> tuple[pa.Table, tuple[str, int, str | None, int | None]]:
    """Every window of a warehouse table, in the scope of ``system`` (``FileNotFoundError`` where it ships no copy and
    borrowing is off), at ``code_width`` when given, with the key of that state of the table. Records a borrowed copy."""
    # Which systems the table holds is read off the directory names (`system=<SYSTEM>`): a system that ships no copy
    # is known without reading a byte. It used to read the whole table (every system and window), filter it in Python
    # and only then raise, for every render group again: 0.4-2.4 s per attempt, 70-95% of a warm re-render
    # (SIM's BR_MUNICIPALFA, whose only copy is another system's).
    stamp = base.stat().st_mtime_ns
    held = _systems_held(base, stamp)
    scope: str | None = None
    if system and held:
        wanted = _SAFE.sub("_", system.upper())
        if wanted in held:
            scope = wanted
        else:
            # Only narrow when the system actually has this table. Returning an
            # empty result for a field whose codelist came from a neighbour's kit
            # would turn a labelling gap into a silent blank column.
            from .decisions import borrowed_labels_allowed

            if not borrowed_labels_allowed():
                raise FileNotFoundError(
                    f"reference table {table_id!r} has no {wanted} mapping; "
                    "cross-system labels are disabled"
                )
            note_borrowed(_SAFE.sub("_", table_id), wanted)
    return _warehouse_table(base, stamp, scope, code_width), (str(base), stamp, scope, code_width)


#: ``(scoped table's key, covering windows, served) -> the first request that was answered so``: see
#: :func:`reference_vintage`.
_VINTAGES: dict[tuple, tuple[int | None, int | None]] = {}


def reference_vintage(
    lake_root: str | Path, table_id: str, *, system: str | None, year: int | None, competencia: int | None,
    code_width: int | None = None,
) -> tuple[int | None, int | None]:
    """The request ``(year, competencia)`` that stands for this one: every month the table answers with the same
    validity windows is one request.

    A caller that keys what it derives from a table by the month it was asked for (the code -> label map, its
    contradictions, the merge of a field's tables) derives it again for every month of one window: a year of a
    monthly dataset is twelve renders of the same table. Keyed by the first request answered with a given set of
    windows it is one, and the table is read for that request alone. The decisions a read records (a window that does
    not cover the month, a copy borrowed from another system) are recorded here, on EVERY call, for the month actually
    asked, so a cached read reports what an uncached one does. A table the lake does not hold in windows (the
    shipped pack, a canonical classification) is returned as asked.
    """
    if year is None and competencia is None:
        return year, competencia
    base = Path(lake_root) / "reference" / _SAFE.sub("_", table_id)
    if competencia is not None:
        span, asked = (int(competencia), int(competencia)), str(int(competencia))
    else:
        span, asked = (year * 100 + 1, year * 100 + 12), str(year)       # type: ignore[operator]
    from ..labelpack import read_packed, select_windows, windows_answering

    try:
        if base.is_dir():
            table, scope = _scoped_table(base, table_id, system, code_width)
            covering, served = select_windows(_windows_of(table, scope), span)
            if served is not None:
                note_fallback(_SAFE.sub("_", table_id), asked, served)
        else:
            # no copy in the lake: the shipped pack answers, windowed by its own rows (it records its own decisions)
            read_packed(table_id, system=system, year=year, competencia=competencia)
            found = windows_answering(table_id, system, span)
            if found is None:
                return year, competencia
            covering, served = found
            scope = ("pack", table_id.upper(), str(system or "").upper(), None)
    except (OSError, ValueError):       # absent, no copy for the system, a window bound that is no AAAAMM: the read says
        return year, competencia
    key = (scope, tuple(covering), served)
    if key not in _VINTAGES:
        if len(_VINTAGES) > 4096:
            _VINTAGES.clear()
        _VINTAGES[key] = (year, competencia)
    return _VINTAGES[key]


_WINDOWS: dict[tuple, list[tuple[str, str]]] = {}


def _windows_of(table: pa.Table, scope: tuple) -> list[tuple[str, str]]:
    """The distinct ``(valid_from, valid_to)`` windows of a scoped warehouse table, once per state of the table."""
    windows = _WINDOWS.get(scope)
    if windows is None:
        pairs = table.select(["valid_from", "valid_to"]).cast(
            pa.schema([("valid_from", pa.string()), ("valid_to", pa.string())]))
        distinct = pairs.group_by(["valid_from", "valid_to"], use_threads=False).aggregate([])
        windows = [(str(lo or ""), str(hi or "")) for lo, hi in zip(
            distinct["valid_from"].to_pylist(), distinct["valid_to"].to_pylist(), strict=True)]
        if len(_WINDOWS) > 512:
            _WINDOWS.clear()
        _WINDOWS[scope] = windows
    return windows


#: ``(table directory, its modification time) -> the systems it holds``: read off the directory names once per state of
#: the table (a rebuild renames directories inside it, which moves the time).
_HELD: dict[tuple[str, int], frozenset[str]] = {}

#: ``(table directory, its time, system, code width) -> every window of that scope``, newest used last. A monthly
#: dataset asks a single-window table for each of its months, and every ask read, concatenated and filtered it again
#: (MUNICBR, 25,733 rows, 48-1,047 ms a month); the windows are chosen below, in memory, from one read.
_WAREHOUSE: dict[tuple[str, int, str | None, int | None], pa.Table] = {}
_WAREHOUSE_MAX = 48


def _systems_held(base: Path, stamp: int) -> frozenset[str]:
    key = (str(base), stamp)
    held = _HELD.get(key)
    if held is None:
        held = frozenset(
            d.name.split("=", 1)[1] for d in base.iterdir() if d.is_dir() and d.name.startswith("system=")
        )
        if len(_HELD) > 512:
            _HELD.clear()
        _HELD[key] = held
    return held


def _warehouse_table(base: Path, stamp: int, scope: str | None, code_width: int | None) -> pa.Table:
    """Every window of a reference table (of one system when ``scope``), at one code width when given."""
    key = (str(base), stamp, scope, code_width)
    table = _WAREHOUSE.pop(key, None)
    if table is None:
        dataset = pads.dataset(base, format="parquet", partitioning="hive")
        # `system` is a hive partition key, so this skips whole directories rather than reading every system and
        # window for a codelist and discarding almost all of it afterwards
        scan_filter = None
        if scope is not None and "system" in dataset.schema.names:
            scan_filter = pc.field("system") == scope
        if code_width is not None and "code_width" in dataset.schema.names:
            width_filter = pc.field("code_width") == code_width
            scan_filter = width_filter if scan_filter is None else (scan_filter & width_filter)
        table = dataset.to_table(filter=scan_filter) if scan_filter is not None else dataset.to_table()
        while len(_WAREHOUSE) >= _WAREHOUSE_MAX:
            _WAREHOUSE.pop(next(iter(_WAREHOUSE)))
    _WAREHOUSE[key] = table
    return table


def register_reference_tables(catalog: CatalogStore, tables: Sequence[ReferenceTable]) -> int:
    catalog.executemany(
        """
        INSERT INTO lake_datasets (dataset, system, series, family_ids, description)
        VALUES (?, NULL, NULL, NULL, ?)
        ON CONFLICT(dataset) DO UPDATE SET description=excluded.description
        """,
        [
            (
                f"ref_{t.table_id.lower()}__{t.system.lower()}",
                f"reference table {t.table_id} ({t.system}), {t.rows} codes, "
                f"window {t.window}, from {t.source_ref}",
            )
            for t in tables
        ],
    )
    return len(tables)


def systems_with_tables(lake_root: str | Path) -> set[str]:
    """Which systems the reference warehouse actually holds tables for.

    "Are there any reference tables?" is the wrong question on first use. The
    warehouse is built per system, so a lake holding SINASC's codelists answers
    yes while a SIH request still has nothing to join against — which made
    reference availability depend on the order requests happened to arrive in.
    """
    root = Path(lake_root) / "reference"
    if not root.exists():
        return set()
    found: set[str] = set()
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        for system_dir in directory.iterdir():
            if system_dir.is_dir() and system_dir.name.startswith("system="):
                found.add(system_dir.name.split("=", 1)[1].upper())
    return found


def has_reference_tables(lake_root: str | Path) -> bool:
    """Whether any lookup is materialised: the question once answered by walking every codelist, system and
    window directory (283,000 stat calls, about 9 s a `translate`, 2026-10-08)."""
    root = Path(lake_root) / "reference"
    return root.exists() and any(p.is_dir() for p in root.iterdir())


#: A lookup whose labels are this blank did not decode anything. Not 100%:
#: CADMUN carries 62 stray labels among 5,579 rows and would slip past an
#: equality test while being useless.
BLANK_LABEL_THRESHOLD = 0.9


def flag_unlabelled_codelists(catalog: CatalogStore) -> list[dict[str, object]]:
    """Report codelists whose labels are overwhelmingly empty.

    These are not sparse tables — they are *failed column selections*. A DBF
    lookup has to guess which column holds the code and which the label, and
    when it guesses wrong the result still looks like a codelist: the right
    number of rows, plausible codes, and nothing to translate them to. ``CADMUN``
    picked ``MUNSIAFI`` as its code and ``OBSERV`` as its label, and ``OBSERV``
    is blank, so the municipality table decoded no municipalities.

    Reported rather than deleted: the row count and the source_ref are the
    evidence for re-reading the DBF with the right columns.
    """
    rows = catalog.query(
        """
        SELECT value_group, system, COUNT(*) AS n,
               SUM(CASE WHEN value_label IS NULL OR TRIM(value_label) = '' THEN 1 ELSE 0 END) AS blank,
               MIN(source_ref) AS source_ref
          FROM dictionary
         WHERE value_group IS NOT NULL
         GROUP BY value_group, system
        HAVING n >= 20 AND CAST(blank AS REAL) / n >= ?
         ORDER BY n DESC
        """,
        (BLANK_LABEL_THRESHOLD,),
    )
    out: list[dict[str, object]] = []
    for r in rows:
        entry = {
            "codelist": str(r["value_group"]),
            "system": str(r["system"]),
            "rows": int(r["n"]),
            "blank": int(r["blank"]),
            "share_blank": round(int(r["blank"]) / int(r["n"]), 3),
            "source_ref": str(r["source_ref"]),
        }
        out.append(entry)
        catalog.note_question(
            f"semantics.unlabelled_codelist:{entry['system']}.{entry['codelist']}",
            area="semantics",
            question=(
                f"Codelist {entry['codelist']} ({entry['system']}) has {entry['blank']} blank "
                f"labels out of {entry['rows']} rows ({entry['share_blank']:.0%}). It decodes "
                "nothing, which usually means the lookup picked the wrong label column."
            ),
            verification_procedure=(
                f"Re-read {entry['source_ref']} and choose the column holding the name rather "
                "than a code or a note. Until then any field bound to it renders unlabelled."
            ),
            blocking=f"labelling anything bound to {entry['codelist']}",
        )
    return out
