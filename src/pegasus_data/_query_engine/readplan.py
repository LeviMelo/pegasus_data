"""The read plan of the lake: which generations answer a request, which files they are, what they carry.

A query is planned once and executed once. ``plan()`` decides which years the lake holds and, with them, the exact partition
files of one reading of each year (the national file or the states', never both): they are the plan's
``lake_partitions``. ``load``, ``scan`` and ``export(stream=True)`` start here: the dataset's generations, the file-axis
refusal, the schema census, and either the files the planner chose or, for a caller with no plan, the catalog's list
narrowed to the states and years asked by the same rule (:func:`coverage.one_reading`). Nothing walks a directory, and a file
the catalog does not list is never read.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..catalog.store import CatalogStore
from ..normalize.engine import MissingColumnError
from ..persist.lake import Lake, LakePartition, listed_partitions
from ..view import COMPANION_SUFFIXES
from .coverage import one_reading


def resolve_family(store: CatalogStore, system: str, series: str | None, field_name: str | None) -> list[dict[str, Any]]:
    """Families of one logical dataset, resolved the way ``fetch()`` resolves it.

    This used to match ``series = ?`` exactly, while ``retrieve._families()``
    resolved through the ontology — two resolvers for the package's central
    abstraction. ``series`` is derived from filenames, so one dataset is spread
    across many spellings of itself: exact matching found 9 of SIA-PA's 736
    families and **none** of SIA-AC's 7. That made ``fetch("SIA-AC")`` and
    ``load("SIA", "AC")`` disagree about what the dataset even contains, and
    ``describe()`` describe a subset of what ``fetch()`` returns.

    The raw filename-derived series stays as provenance. It is not identity.

    The SYSTEM half of that fix was missed. `families.system` holds the CRAWLED
    name — SIHSUS, SIASUS — while the API and the ontology speak the
    institutional one, SIH and SIA, so filtering the table with the caller's
    spelling returned nothing at all for exactly the names §14.5 promises
    resolve: `describe("SIH", "RD")` raised DatasetUnknown while
    `describe("SIHSUS", "RD")` worked, and `fetch("SIH-RD")` worked throughout.
    Every spelling the declaration knows is asked for instead.
    """
    def resolve() -> list[dict[str, Any]]:
        from ..semantics.curation import system_spellings

        spellings = system_spellings(system)
        rows = store.query(
            "SELECT family_id, system, series, schema_signature, field_count, time_min, time_max "
            f"FROM families WHERE system IN ({','.join('?' * len(spellings))}) "
            "ORDER BY COALESCE(time_max, 0) DESC",
            spellings,
        )
        families = [dict(r) for r in rows]
        if series:
            from .._request import _ontology

            onto = _ontology()
            target = onto.resolve(f"{system}.{series}") if onto else None
            bound: list[dict[str, Any]] = []
            if onto and target and target[0] == "dataset":
                code = target[1].code
                bound = [
                    f
                    for f in families
                    if onto.bind(str(f["system"]), str(f["series"])).dataset == code
                ]
            # Fall back to the plain match when the ontology cannot name it: a
            # narrower answer beats an exception.
            families = bound or [f for f in families if str(f["series"]) == series]
        if field_name:
            with_field = [
                f
                for f in families
                if store.count(
                    "schema_presence", "schema_signature = ? AND field_name = ?",
                    (f["schema_signature"], field_name),
                )
            ]
            if with_field:
                return with_field
        return families

    # remembered until the catalog changes: the same dataset is resolved by every read of it (0.1-0.2 s on
    # SIA-PA's 736 spellings), and callers get their own copies
    return [dict(f) for f in store.memo(("family", system, series, field_name), resolve)]


#: Structural columns every lake partition carries, whatever the source schema
#: held. Hive partition keys, written by the build rather than decoded from a
#: file, so they never appear in `schema_presence`.
#: Columns of the lake rather than fields of a source schema: the Hive
#: partitions, and the provenance every normalised row carries
#: (normalize/engine.PROVENANCE_COLUMNS). A projection naming a provenance
#: column dropped it as absent, so a query over a built lake lost record
#: identity (2026-10-03).
LAKE_COLUMNS: frozenset[str] = frozenset(
    {"year", "uf", "_source_path", "_blob_sha256", "_row", "_ingested_at", "_schema_signature", "_record_key"}
)


def schema_presence(store: CatalogStore, families: Sequence[Mapping[str, Any]]) -> dict[str, frozenset[str]]:
    """``signature -> fields`` of these generations' schema census, one query for all, remembered per catalog state.

    ``schema_presence`` is the index of the census; where it holds nothing for a signature (30 of the real catalog's 321,
    among them SIM's 2006 and SIH's 1994, 2002-2004 generations) the schema's own field list stands in, the record
    `normalize` and `profile` read the fields from. A signature with neither is absent from the answer: uncensused.
    """
    signatures = tuple(sorted({str(f["schema_signature"]) for f in families}))
    if not signatures:
        return {}

    def load_presence() -> dict[str, frozenset[str]]:
        found: dict[str, set[str]] = {}
        for start in range(0, len(signatures), 500):
            chunk = signatures[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            for row in store.query(
                f"SELECT schema_signature AS sig, field_name AS fld FROM schema_presence "
                f"WHERE schema_signature IN ({marks})", chunk,
            ):
                found.setdefault(str(row["sig"]), set()).add(str(row["fld"]))
        unindexed = [sig for sig in signatures if sig not in found]
        for start in range(0, len(unindexed), 500):
            chunk = unindexed[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            for row in store.query(
                f"SELECT schema_signature AS sig, fields_json FROM schemas WHERE schema_signature IN ({marks})", chunk,
            ):
                try:
                    names = json.loads(row["fields_json"] or "[]")
                except json.JSONDecodeError:
                    continue
                fields = {str(f["name"] if isinstance(f, dict) else f) for f in names}
                if fields:
                    found[str(row["sig"])] = fields
        return {sig: frozenset(fields) for sig, fields in found.items()}

    return store.memo(("presence", signatures), load_presence)


def require_known_columns(
    store: CatalogStore, system: str, series: str | None, dataset_families: Sequence[Mapping[str, Any]],
    columns: Sequence[str], *, exempt: frozenset[str] = frozenset(),
) -> None:
    """Raise :class:`MissingColumnError` for a column NO generation of the dataset carries.

    ``on_missing_column="null_fill"`` is for a field that exists in some generations and not others: the structural
    absence is recorded and the rows are null. A column in none of them is a typo or a renamed field, and filling it
    with nulls (the column is "structurally absent from every generation") is the empty result that looks legitimate.
    ``exempt`` are names produced after reading (derived columns); the partition keys, the stored labels and the
    companions of a known column are never refused. Silent when a generation has no schema census: absence of
    evidence is not evidence of absence.
    """
    presence = schema_presence(store, dataset_families)
    signatures = {str(f["schema_signature"]) for f in dataset_families}
    if not signatures or any(not presence.get(sig) for sig in signatures):
        return
    known = frozenset().union(*(presence[sig] for sig in signatures)) | LAKE_COLUMNS
    known_upper = {k.upper() for k in known}
    skip = {c.upper() for c in (*LAKE_COLUMNS, *exempt)}

    def produced_from_known(name: str) -> bool:
        upper = name.upper()
        return any(
            upper.endswith(suffix.upper()) and upper[: -len(suffix)] in known_upper
            for suffix in ("_label", *COMPANION_SUFFIXES)
        )

    unknown = [c for c in columns if c not in known and c.upper() not in skip and not produced_from_known(c)]
    if unknown:
        label = f"{system}.{series}" if series else system
        near = sorted(k for k in known if k.upper() in {u.upper() for u in unknown})
        raise MissingColumnError(
            unknown[0], f"{label}, in any of its {len(dataset_families)} generations", near, also_absent=unknown[1:],
        )


@dataclass(slots=True)
class LakeRead:
    """What :func:`plan_lake_read` decided: which generations answer a request, which files, what they carry."""

    #: the generations in play: those with a partition to read in the states and years asked
    families: list[dict[str, Any]]
    #: schema signature -> the fields its census lists, for every generation of the dataset
    presence: dict[str, frozenset[str]]
    notes: list[str]
    #: family_id -> the partition files to read, by (state, year)
    partitions: dict[str, list[LakePartition]]
    #: every generation of the dataset (or the one family asked for), in play or not
    dataset_families: list[dict[str, Any]]


def plan_lake_read(
    store: CatalogStore,
    system: str,
    series: str | None,
    *,
    family_id: str | None,
    uf: Sequence[str] | None,
    years: Sequence[int] | None,
    partitions: Sequence[LakePartition] | None = None,
) -> LakeRead:
    """Which schema generations answer this request, which files they are, and what fields they carry.

    Dataset resolution, the file-axis refusal, the files and the schema-presence matrix: everything that decides WHICH
    generations are in play, before any of them is opened. Kept apart from reading them because the two failure modes
    differ: this one refuses a question, the other reports what a generation could not give. ``partitions`` are the files
    the planner chose (``RetrievalPlan.lake_partitions``); without them the catalog's list is narrowed to ``uf`` and
    ``years``, and with no state asked a year held as a national file and as its state files reads the national one.
    """
    families = resolve_family(store, system, series, None)
    if not families:
        from ..retrieve import DatasetUnknown

        raise DatasetUnknown(
            f"no family found for system={system!r} series={series!r}"
        )
    if family_id:
        narrowed = [f for f in families if f["family_id"] == family_id]
        if not narrowed:
            # Naming the filter that emptied the set, not the one that did
            # not: reporting "no family for SIHSUS/RD" when twenty exist and
            # the family_id was simply mistyped sends the reader to the
            # wrong question entirely.
            known = ", ".join(f["family_id"] for f in families[:5])
            raise KeyError(
                f"no family {family_id!r} in system={system!r} series={series!r}; "
                f"{len(families)} exist, e.g. {known}"
            )
        families = narrowed
    dataset_families = families

    # The same guard fetch() has. Without it, load(uf="AC") on a national
    # dataset filtered a Hive partition that does not exist and returned a
    # false empty, which reads as "Acre has no records".
    from ..retrieve import FilterHasNoAxis, axis_refusal

    refusal, notes = axis_refusal(
        store,
        system,
        series or (families[0]["series"] if families else None),
        uf=bool(uf),
        years=bool(years),
        months=False,
    )
    if refusal:
        raise FilterHasNoAxis(refusal)

    # The files come from the catalog's list of the lake (`lake_partitions`, written with each file), not from a walk
    # of the directory: only the generations with a partition in the states and years asked are opened, and a file
    # the catalog does not list is never read.
    ids = {str(f["family_id"]) for f in families}
    if partitions is None:
        listed = listed_partitions(store, sorted(ids))
        asked = Lake.narrow((p for fam in sorted(ids) for p in listed.get(fam, ())), uf or None, years or None)
        chosen = asked if uf else one_reading(asked)
        if len(chosen) < len(asked):
            notes = [*notes, (
                f"{system}.{series or ''}: the lake holds {len(asked) - len(chosen)} state partition(s) of years that "
                "also have a national file; only the national file is read (the state files are the same records)"
            )]
    else:
        chosen = [p for p in partitions if p.family_id in ids]
    by_family: dict[str, list[LakePartition]] = {}
    for part in sorted(chosen, key=lambda p: (p.uf, p.year, p.relative_path)):
        by_family.setdefault(part.family_id, []).append(part)
    return LakeRead(
        [f for f in families if str(f["family_id"]) in by_family],
        schema_presence(store, dataset_families), list(notes), by_family, dataset_families,
    )


def generation_columns(
    read: LakeRead, family: Mapping[str, Any], wanted: Sequence[str], present: Collection[str], on_missing_column: str,
) -> tuple[list[str], list[str]]:
    """``(columns to read, columns this generation lacks)`` of the ``wanted`` ones: the missing-column policy of a read.

    A column some generation carries and this one does not is a structural absence: under ``null_fill`` the generation
    is kept, read for what it has, and the absence returned to be recorded (those nulls are STRUCTURAL: the field does
    not exist here). Otherwise it RAISES. It used to be recorded and the generation skipped, and so, if a later one
    happened to have the column, every earlier generation was dropped in silence: a 1995-2025 request for a field added
    in 2006 returned 2006 onward and looked like a dataset that simply starts in 2006. ``load`` and ``scan`` both read
    their generations through this one rule.
    """
    missing = [c for c in wanted if c not in present]
    if missing and on_missing_column != "null_fill":
        elsewhere = [
            str(f["family_id"])
            for f in read.dataset_families
            if all(c in read.presence.get(str(f["schema_signature"]), frozenset()) for c in missing)
        ]
        raise MissingColumnError(missing[0], family["family_id"], elsewhere, also_absent=missing[1:])
    return [c for c in wanted if c in present], missing
