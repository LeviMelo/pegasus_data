"""The public surface (§9).

    from pegasus_data import Catalog, load, describe, load_population

    cat = Catalog()
    cat.systems()
    cat.families(system="SIHSUS")
    cat.coverage("SIHSUS", "RD")

    describe("SIHSUS", "RD", field="DIAG_PRINC")

    df = load("SIHSUS", "RD", uf="AL", years=range(2015, 2025),
              columns=[...], labels=True)

``describe()`` is the module's user-facing face: the answer to "what is this
variable and what do its values mean", which DATASUS does not provide anywhere.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.dataset as ds

from .catalog.store import Catalog as _Store
from .config import Settings, load_settings
from .normalize.engine import MissingColumnError
from .persist.duck import DuckLake
from .persist.lake import Lake
from .persist.reference import available_tables, is_hierarchical, read_reference_table
from .profile.drift import field_availability
from .semantics.dictionary import (
    binding_sources,
    codelists_for,
    lookup,
    match_codelist_by_name,
    most_granular_codelist,
    observed_values,
    rollups_for,
)
from .sources.ibge import KNOWN_SERIES, UnsupportedStratification, series_catalogue
from .view import (
    COMPANION_SUFFIXES,
    PROFILES,
    LabelUnavailable,
    RenderReport,
    render_table,
)

__all__ = [
    "Catalog",
    "describe",
    "load",
    "load_population",
    "load_reference",
    "open_lake",
    "scan",
    "LakeScan",
    "FieldDescription",
    "MissingColumnError",
    "export",
    "write_table",
    "LabelUnavailable",
    "RenderReport",
    "PROFILES",
]


@dataclass(slots=True)
class FieldDescription:
    """Everything the module knows about one variable, with its provenance."""

    system: str
    series: str | None
    family_id: str
    field_name: str
    official_name: str | None
    semantic_type: str | None
    semantic_confidence: float | None
    semantic_evidence: dict[str, Any]
    aggregation: str
    unit: str | None
    dictionary_coverage: float
    distinct_observed: int
    distinct_decoded: int
    sentinel_values: list[str]
    top_values: list[dict[str, Any]] = field(default_factory=list)
    codelists: list[str] = field(default_factory=list)
    rollups: list[dict[str, Any]] = field(default_factory=list)
    #: Where meaning actually comes from for this field: the reference table, the
    #: validity windows it is published in, how the binding was established, and
    #: — for a hierarchical classification — the roll-up levels available.
    reference: dict[str, Any] | None = None
    label_policy: str = "materialised"
    provenance: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    generations: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "series": self.series,
            "family_id": self.family_id,
            "field": self.field_name,
            "official_name": self.official_name,
            "semantic_type": self.semantic_type,
            "semantic_confidence": self.semantic_confidence,
            "semantic_evidence": self.semantic_evidence,
            "aggregation": self.aggregation,
            "unit": self.unit,
            "dictionary_coverage": self.dictionary_coverage,
            "distinct_observed": self.distinct_observed,
            "distinct_decoded": self.distinct_decoded,
            "sentinel_values": self.sentinel_values,
            "top_values": self.top_values,
            "codelists": self.codelists,
            "rollups": self.rollups,
            "reference": self.reference,
            "label_policy": self.label_policy,
            "provenance": self.provenance,
            "open_questions": self.open_questions,
            "generations": self.generations,
        }

    def __repr__(self) -> str:
        head = f"{self.system}.{self.series or ''}.{self.field_name}"
        name = f" — {self.official_name}" if self.official_name else ""
        # semantic_confidence is Optional. Formatting None with :.2f raised
        # TypeError, so an unresolved field could not even be displayed in a
        # notebook — the one place a caller meets it.
        confidence = (
            f"({self.semantic_confidence:.2f})"
            if self.semantic_confidence is not None
            else "(confidence unknown)"
        )
        coverage = (
            f" | coverage {self.dictionary_coverage:.1%}"
            if self.dictionary_coverage is not None
            else ""
        )
        return f"<{head}{name} | {self.semantic_type} {confidence}{coverage} | {self.aggregation}>"


class Catalog:
    """Read access to the shipped catalog, lake and dictionary."""

    def __init__(
        self,
        root: str | Path | None = None,
        settings: Settings | None = None,
        *,
        create: bool = False,
    ) -> None:
        """Read access to the catalog at ``root``.

        ``create=False`` by default, because this is the INSPECTION door. It
        used to open read-only when the file existed and create a writable one
        when it did not — so a typo in ``root`` silently produced an empty
        database and every question answered "nothing found" instead of "there
        is no catalog here". Pipelines and builds pass ``create=True``.
        """
        self.settings = settings or load_settings(root=Path(root) if root else None)
        exists = self.settings.catalog_path.exists()
        if not exists and not create:
            raise FileNotFoundError(
                f"no catalog at {self.settings.catalog_path}. Check `root`, or run "
                "`pegasus-data crawl` to build one. Pass create=True to make an "
                "empty catalog here on purpose."
            )
        self.store = _Store(self.settings.catalog_path, read_only=exists)
        self._lake: Lake | None = None

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> Catalog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def lake(self) -> Lake:
        if self._lake is None:
            self._lake = Lake(self.settings.lake_dir, self.store)
        return self._lake

    # ------------------------------------------------------------- inventory

    def systems(self) -> list[dict[str, Any]]:
        """What exists, with how much of it and over what span."""
        return [
            dict(r)
            for r in self.store.query(
                """
                SELECT system,
                       COUNT(*) AS files,
                       COUNT(DISTINCT series_prefix) AS series,
                       MIN(year) AS year_min, MAX(year) AS year_max
                  FROM file_facts
                 WHERE system IS NOT NULL
                 GROUP BY system ORDER BY files DESC
                """
            )
        ]

    def families(self, system: str | None = None, series: str | None = None) -> list[dict[str, Any]]:
        clauses, params = [], []
        if system:
            clauses.append("system = ?")
            params.append(system)
        if series:
            clauses.append("series = ?")
            params.append(series)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return [
            dict(r)
            for r in self.store.query(
                f"""
                SELECT family_id, system, series, schema_signature, field_count,
                       time_min, time_max, file_count, stratum_count, geo_coverage
                  FROM families{where}
                 ORDER BY system, series, COALESCE(time_min, 0)
                """,
                params,
            )
        ]

    def coverage(self, system: str, series: str | None = None) -> dict[str, Any]:
        """Span, UFs, schema generations, and the gaps — per §9."""
        fams = self.families(system, series)
        gaps = [
            dict(r)
            for r in self.store.query(
                "SELECT path, kind, attempts, last_error FROM coverage_gaps WHERE resolved = 0 AND path LIKE ?",
                (f"%/{system}/%",),
            )
        ]
        drift = [
            dict(r)
            for r in self.store.query(
                "SELECT series, observed_strata, schema_signature_count, drift_status FROM schema_drift WHERE system = ?",
                (system,),
            )
        ]
        ufs = sorted(
            {
                u
                for f in fams
                for u in json.loads(f.get("geo_coverage") or "[]")
            }
        )
        years = [f["time_min"] for f in fams if f["time_min"]] + [
            f["time_max"] for f in fams if f["time_max"]
        ]
        return {
            "system": system,
            "series": series,
            "families": len(fams),
            "schema_generations": [
                {
                    "family_id": f["family_id"],
                    "series": f["series"],
                    "columns": f["field_count"],
                    "years": [f["time_min"], f["time_max"]],
                    "files": f["file_count"],
                    "schema_signature": f["schema_signature"],
                }
                for f in fams
            ],
            "years": [min(years), max(years)] if years else [None, None],
            "ufs": ufs,
            "drift": drift,
            "open_gaps": gaps,
        }

    def open_questions(self, status: str | None = "open") -> list[dict[str, Any]]:
        clause = " WHERE status = ?" if status else ""
        params = (status,) if status else ()
        return [dict(r) for r in self.store.query(f"SELECT * FROM open_questions{clause} ORDER BY key", params)]

    def dictionary_coverage(self) -> list[dict[str, Any]]:
        from .semantics.ledger import coverage_report

        return coverage_report(self.store)

    def population_series(self) -> list[dict[str, Any]]:
        catalogued = series_catalogue(self.store)
        if catalogued:
            return catalogued
        return [
            {
                "series": s.name,
                "authority": s.authority,
                "year_min": s.year_min,
                "year_max": s.year_max,
                "stratifications": s.stratifications,
                "age_standardizable": s.age_standardizable,
                "notes": s.notes,
            }
            for s in KNOWN_SERIES.values()
        ]

    # --------------------------------------------------------------- describe

    def describe(self, system: str, series: str | None = None, *, field: str | None = None) -> Any:
        if field is None:
            return self.coverage(system, series)
        return describe(system, series, field=field, catalog=self)

    # ------------------------------------------------------------------- load

    def load(self, system: str, series: str | None = None, **kwargs: Any) -> pa.Table:
        return load(system, series, catalog=self, **kwargs)

    def duckdb(self, database: str = ":memory:") -> DuckLake:
        duck = DuckLake(self.settings.lake_dir, self.store, database=database)
        duck.register_all()
        return duck


def _by_vintage(table: pa.Table, years: Sequence[int] | None):
    """Split a table into ``(chunk, year)`` so each is rendered at its own vintage.

    The lake stores ``year`` as a partition column, so it is present on every
    row and the split is exact. Without that column there is nothing to split
    on and the whole table is rendered once, with the request's earliest year as
    the hint — the old behaviour, kept only for that case.
    """
    import pyarrow.compute as pc

    if "year" not in table.column_names:
        return [(table, min(years) if years else None)]
    distinct = pc.unique(table.column("year")).to_pylist()
    usable = sorted(y for y in distinct if y not in (None, 0))
    if len(usable) <= 1:
        only = usable[0] if usable else (min(years) if years else None)
        return [(table, only)]
    out = []
    for year in usable:
        mask = pc.equal(table.column("year"), year)
        chunk = table.filter(mask)
        if chunk.num_rows:
            out.append((chunk, int(year)))
    # Rows whose year is null or 0 carry no vintage of their own.
    rest = table.filter(pc.is_null(pc.if_else(pc.equal(table.column("year"), 0), None, table.column("year"))))
    if rest.num_rows:
        out.append((rest, min(years) if years else None))
    return out


def _merge_reports(into, addition):
    """Fold one render report into another, keeping every field's information."""
    if into is None:
        return addition
    for name in ("labelled", "unlabelled", "derived_added", "companions_dropped", "warnings"):
        seen = set(getattr(into, name))
        for item in getattr(addition, name, ()):
            if item not in seen:
                getattr(into, name).append(item)
                seen.add(item)
    into.constant.update(getattr(addition, "constant", {}) or {})
    for key, value in (getattr(addition, "tokens_unmatched", {}) or {}).items():
        into.tokens_unmatched[key] = into.tokens_unmatched.get(key, 0) + value
    return into


def _resolve_family(store: _Store, system: str, series: str | None, field_name: str | None) -> list[dict[str, Any]]:
    """Families of one logical dataset, resolved the way ``fetch()`` resolves it.

    This used to match ``series = ?`` exactly, while ``retrieve._families()``
    resolved through the ontology — two resolvers for the package's central
    abstraction. ``series`` is derived from filenames, so one dataset is spread
    across many spellings of itself: exact matching found 9 of SIA-PA's 736
    families and **none** of SIA-AC's 7. That made ``fetch("SIA-AC")`` and
    ``load("SIA", "AC")`` disagree about what the dataset even contains, and
    ``describe()`` describe a subset of what ``fetch()`` returns.

    The raw filename-derived series stays as provenance. It is not identity.
    """
    rows = store.query(
        "SELECT family_id, system, series, schema_signature, field_count, time_min, time_max "
        "FROM families WHERE system = ? ORDER BY COALESCE(time_max, 0) DESC",
        [system],
    )
    families = [dict(r) for r in rows]
    if series:
        from .retrieve import _ontology

        onto = _ontology()
        target = onto.resolve(f"{system}.{series}") if onto else None
        bound: list[dict[str, Any]] = []
        if target and target[0] == "dataset":
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


def describe(
    system: str,
    series: str | None = None,
    *,
    field: str,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> FieldDescription:
    """Ledger entry + dictionary coverage + top values **with labels** + provenance.

    When a field exists in some schema generations and not others, that is stated
    rather than hidden: ``generations`` lists every generation and whether it
    carries the column, which is the information that stops a query for
    ``DIAG_SECUN`` against a 2020 file from quietly returning nothing useful.
    """
    own = catalog is None
    cat = catalog or Catalog(root=root, settings=settings)
    try:
        store = cat.store
        candidates = _resolve_family(store, system, series, field)
        if not candidates:
            from .retrieve import DatasetUnknown

            raise DatasetUnknown(
                f"no family found for system={system!r} series={series!r}"
            )
        family = candidates[0]
        family_id = family["family_id"]

        ledger_rows = store.query(
            """
            SELECT * FROM ledger WHERE family_id = ? AND field_name = ?
            """,
            (family_id, field),
        )
        profile_rows = store.query(
            "SELECT * FROM variable_profiles WHERE family_id = ? AND field_name = ?",
            (family_id, field),
        )
        in_schema = bool(
            store.count(
                "schema_presence", "schema_signature = ? AND field_name = ?",
                (family["schema_signature"], field),
            )
        )
        if not ledger_rows and not profile_rows and not in_schema:
            # Genuinely absent from every generation we know about.
            availability = field_availability(store, system, series or family["series"] or "", field)
            raise MissingColumnError(field, family_id, [
                g["family_id"] for g in availability.get("generations", []) if g.get("has_field")
            ])

        led = dict(ledger_rows[0]) if ledger_rows else {}
        prof = dict(profile_rows[0]) if profile_rows else {}
        signature = str(prof.get("schema_signature") or family["schema_signature"])

        observed = observed_values(
            store, family_id=family_id, field_name=field, schema_signature=signature
        )
        labels = lookup(store, system=system, field_name=field, observed=observed)
        total = sum(observed.values()) or 1
        top = [
            {
                "value": value,
                "count": count,
                "percent": round(count / total, 6),
                "label": labels.get(value),
            }
            for value, count in sorted(observed.items(), key=lambda kv: -kv[1])[:25]
        ]

        evidence: dict[str, Any] = {}
        raw_evidence = led.get("semantic_evidence") or prof.get("semantic_evidence")
        if raw_evidence:
            try:
                evidence = json.loads(raw_evidence)
            except json.JSONDecodeError:
                evidence = {"raw": raw_evidence}

        generations = [
            {
                "family_id": f["family_id"],
                "columns": f["field_count"],
                "years": [f["time_min"], f["time_max"]],
                "has_field": bool(
                    store.count(
                        "schema_presence", "schema_signature = ? AND field_name = ?",
                        (f["schema_signature"], field),
                    )
                ),
            }
            for f in _resolve_family(store, system, series, None)
        ]

        open_questions = json.loads(led.get("open_questions") or "[]")
        if not ledger_rows and not profile_rows:
            # In the schema, but never profiled: say so rather than implying the
            # column does not exist, and rather than implying it is understood.
            open_questions.append(
                f"{field} is declared by this schema generation but has not been profiled; "
                "run `pegasus-data profile` to populate its statistics and dictionary coverage"
            )

        official_name = led.get("official_name")
        if official_name is None:
            # The record layout names the column itself; check it before giving up.
            documented = store.query(
                """
                SELECT description, source_ref FROM field_documentation
                 WHERE field_name = ? AND (system = ? OR system IS NULL)
                 ORDER BY confidence DESC LIMIT 1
                """,
                (field, system),
            )
            if documented:
                official_name = str(documented[0]["description"])
        if official_name is None:
            # Same rule the ledger uses: only a declaration that names the field
            # itself counts. A declaration bound to a codelist names an
            # aggregation level, and reporting one of those as the column's
            # official name would be a plausible-looking guess (§13).
            named = store.query(
                """
                SELECT display_name FROM def_variables
                 WHERE field_name = ? AND lookup_ref IS NULL AND (system = ? OR system IS NULL)
                 ORDER BY LENGTH(display_name) LIMIT 1
                """,
                (field, system),
            )
            official_name = named[0]["display_name"] if named else None

        bound = codelists_for(store, system=system, field_name=field)
        sources = binding_sources(store, system=system, field_name=field)
        chosen = most_granular_codelist(store, bound, system=system, observed=observed)
        reference: dict[str, Any] | None = None
        label_policy = "materialised"
        if chosen:
            hierarchical = is_hierarchical(store, chosen)
            windows = [
                {"valid_from": r["valid_from"], "valid_to": r["valid_to"], "codes": int(r["n"])}
                for r in store.query(
                    """
                    SELECT valid_from, valid_to, COUNT(*) AS n FROM dictionary
                     WHERE value_group = ? GROUP BY valid_from, valid_to ORDER BY valid_from
                    """,
                    (chosen,),
                )
            ]
            reference = {
                "table": chosen,
                "hierarchical": hierarchical,
                "bound_by": sources.get(chosen, "unknown"),
                "authoritative": sources.get(chosen) in {"def", "manual", "layout_doc"},
                "validity_windows": windows,
                "rollup_levels": [
                    r["codelist"]
                    for r in rollups_for(store, system=system, field_name=field, observed=observed)
                    if r["codelist"] != chosen
                ][:8],
                "join": (
                    f"load_reference({chosen!r}, year=<year>) and join on the raw code; the "
                    "window is chosen by year so a 1995 record decodes against the table "
                    "published for 1995"
                )
                if hierarchical
                else None,
            }
            label_policy = "join_reference_table" if hierarchical else "materialised"
            if hierarchical:
                open_questions.append(
                    f"{field} is decoded by {chosen}, a hierarchical classification: no single "
                    "label is written into the lake, because chapter, block and category are all "
                    "valid levels and the published wording is version-specific. Join "
                    f"load_reference({chosen!r}, year=...) at the level you want."
                )
            if sources.get(chosen) == "semantic_match":
                open_questions.append(
                    f"the binding {field} -> {chosen} rests on a measured membership rate, not on "
                    "a .DEF or a layout document; treat it as a candidate until corroborated"
                )
        if not bound:
            # Name-matched codelists are *candidates*, never applied: "obvious" is
            # how a wrong mapping gets in without provenance (§13). Surfacing them
            # turns an undecoded field into an actionable lead.
            suggestions = match_codelist_by_name(store, field)
            if suggestions:
                open_questions.append(
                    f"no .DEF binds a codelist to {field}; codelists whose name matches, "
                    f"as unverified candidates: {', '.join(suggestions[:5])}"
                )

        return FieldDescription(
            system=system,
            series=series or family["series"],
            family_id=family_id,
            field_name=field,
            official_name=official_name,
            semantic_type=led.get("semantic_type") or prof.get("semantic_type"),
            semantic_confidence=led.get("semantic_confidence") or prof.get("semantic_confidence"),
            semantic_evidence=evidence,
            aggregation=str(led.get("aggregation") or "non_summable"),
            unit=led.get("unit"),
            dictionary_coverage=float(led.get("dictionary_coverage") or 0.0),
            distinct_observed=int(led.get("distinct_observed") or len(observed)),
            distinct_decoded=int(led.get("distinct_decoded") or 0),
            sentinel_values=json.loads(led.get("sentinel_values") or "[]"),
            top_values=top,
            codelists=bound,
            rollups=rollups_for(store, system=system, field_name=field, observed=observed),
            provenance=json.loads(led.get("provenance") or "[]"),
            open_questions=open_questions,
            reference=reference,
            label_policy=label_policy,
            generations=generations,
        )
    finally:
        if own:
            cat.close()


def _resolve_generations(
    store: _Store,
    system: str,
    series: str | None,
    *,
    family_id: str | None,
    uf: Sequence[str] | None,
    years: Sequence[int] | None,
    columns: Sequence[str] | None,
) -> tuple[list, dict[str, set[str]], list[str]]:
    """Which schema generations answer this request, and what fields they carry.

    Dataset resolution, the file-axis refusal, partition pruning and the
    schema-presence matrix — everything that decides WHICH generations are in
    play, before any of them is opened. Kept apart from reading them because
    the two failure modes differ: this one refuses a question, the other
    reports what a generation could not give.
    """
    families = _resolve_family(store, system, series, None)
    if not families:
        from .retrieve import DatasetUnknown

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

    # The same guard fetch() has. Without it, load(uf="AC") on a national
    # dataset filtered a Hive partition that does not exist and returned a
    # false empty, which reads as "Acre has no records".
    from .retrieve import FilterHasNoAxis, axis_refusal

    refusal, axis_notes = axis_refusal(
        store,
        system,
        series or (families[0]["series"] if families else None),
        uf=bool(uf),
        years=bool(years),
        months=False,
    )
    if refusal:
        raise FilterHasNoAxis(refusal)

    wanted: list[str] | None = list(columns) if columns else None

    # PRUNE before touching the filesystem. load() used to try every family
    # the ontology resolves and let a FileNotFoundError say no — one dataset
    # open per generation per call, which on a fragmented system is most of
    # the call. lake_partitions already knows exactly which (family, uf,
    # year) exist.
    family_ids = [str(f["family_id"]) for f in families]
    if family_ids:
        marks = ",".join("?" for _ in family_ids)
        held: dict[str, set[tuple[str, int]]] = {}
        for row in store.query(
            f"SELECT family_id AS fam, uf, year FROM lake_partitions "
            f"WHERE family_id IN ({marks})",
            tuple(family_ids),
        ):
            held.setdefault(str(row["fam"]), set()).add(
                (str(row["uf"]), int(row["year"] or 0))
            )
        # Only prune on evidence. An empty lake_partitions means the catalog
        # does not know what the lake holds, not that the lake is empty, and
        # pruning on that would turn a stale catalog into "no data".
        if held:
            want_ufs = {str(u).upper() for u in (uf or [])}
            want_years = {int(y) for y in (years or [])}

            def _relevant(fid: str) -> bool:
                parts = held.get(fid)
                if parts is None:
                    return True  # nothing recorded for it; let it try
                return any(
                    (not want_ufs or p_uf.upper() in want_ufs)
                    and (not want_years or p_year in want_years)
                    for p_uf, p_year in parts
                )

            narrowed = [f for f in families if _relevant(str(f["family_id"]))]
            if narrowed:
                families = narrowed

    # ONE presence query for every remaining generation. This was a query
    # per family, and on the failure path a count() per (family x missing
    # column) inside a loop over families — N+1 nested in N+1, on the path
    # that is already about to raise.
    presence: dict[str, set[str]] = {}
    if wanted:
        signatures = sorted({str(f["schema_signature"]) for f in families})
        if signatures:
            marks = ",".join("?" for _ in signatures)
            for row in store.query(
                f"SELECT schema_signature AS sig, field_name AS fld "
                f"FROM schema_presence WHERE schema_signature IN ({marks})",
                tuple(signatures),
            ):
                presence.setdefault(str(row["sig"]), set()).add(str(row["fld"]))
    return families, presence, axis_notes


def _read_generations(
    cat: Catalog,
    families: Sequence[Mapping[str, object]],
    *,
    system: str,
    uf: Sequence[str] | None,
    years: Sequence[int] | None,
    wanted: list[str] | None,
    presence: dict[str, set[str]],
    on_missing_column: str,
) -> tuple[list, dict[str, list[str]]]:
    """Read each generation, applying the structural missing-column policy.

    Returns ``(tables, structurally_absent)``. Generations are read separately
    and combined by the caller: two generations do not share a schema, and
    which of them may be null-filled together is a policy decision
    (``on_missing_column``), not something a reader should settle quietly.
    """
    structurally_absent: dict[str, list[str]] = {}
    tables: list[pa.Table] = []
    for family in families:
        projection = None
        if wanted:
            present = presence.get(str(family["schema_signature"]), set())
            missing = [c for c in wanted if c not in present]
            if missing and on_missing_column == "null_fill":
                # Keep the generation and read what it does have; concat
                # null-fills the rest. Recorded, because those nulls are
                # STRUCTURAL — the field does not exist here.
                structurally_absent[str(family["family_id"])] = list(missing)
                projection = [c for c in wanted if c in present]
                missing = []
            if missing:
                elsewhere = [
                    str(f["family_id"])
                    for f in families
                    if all(
                        c in presence.get(str(f["schema_signature"]), set())
                        for c in missing
                    )
                ]
                # RAISE, do not skip. This used to append to `errors` and
                # `continue`, and `errors` was only raised when NO family
                # produced a table — so if a later generation happened to
                # have the column, every earlier generation was dropped in
                # silence. A 1995-2025 request for a field added in 2006
                # returned 2006 onward and looked like a dataset that simply
                # starts in 2006. The docstring already promised this raises.
                raise MissingColumnError(
                    missing[0],
                    family["family_id"],
                    elsewhere,
                    also_absent=missing[1:],
                )
            if projection is None:
                projection = list(wanted)
        # Companion columns the build materialised are still worth reading;
        # labels are no longer projected here, they are joined below.
        optional = [f"{c}{suffix}" for c in (wanted or []) for suffix in COMPANION_SUFFIXES]
        try:
            table = cat.lake.read(
                system=system,
                family_id=family["family_id"],
                uf=uf,
                years=years,
                columns=projection,
                optional_columns=optional,
            )
        except FileNotFoundError:
            continue
        if table.num_rows:
            tables.append((family["family_id"], table))
    return tables, structurally_absent


def load(
    system: str,
    series: str | None = None,
    *,
    uf: str | Sequence[str] | None = None,
    years: int | Sequence[int] | range | None = None,
    columns: Sequence[str] | None = None,
    labels: bool | None = None,
    family_id: str | None = None,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
    profile: str = "analysis",
    render: Mapping[str, str] | None = None,
    headers: str | None = None,
    values: str | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    strict_labels: bool = False,
    on_missing_column: str = "raise",
    report: bool = False,
) -> pa.Table | tuple[pa.Table, RenderReport]:
    """Read a family out of the lake, rendered for reading.

    Labels are produced **here**, at read time, by joining the version-scoped
    reference table for the years being read — not projected out of the Parquet.
    That was the bug: ``labels=True`` used to select ``*_label`` columns that had
    to already exist, so asking for a label after a ``--no-labels`` build, or for
    any field whose codelist was never materialised, returned unlabelled data
    with no error at all. A label that cannot be produced is now named, in a
    warning or — with ``strict_labels=True`` — in a :class:`LabelUnavailable`.

    ``profile`` selects how much is rendered: ``analysis`` (default) labels
    internal codes in place and keeps external codes beside their labels;
    ``codes`` renders nothing; ``audit`` shows everything at once; ``report``
    translates headers and combines values for a document someone reads. Any
    single column can be overridden with ``render={"SEXO": "both"}``.

    A requested column that does not exist in the target generation **raises**
    (:class:`MissingColumnError`) rather than returning empty — an empty result
    looks legitimate and is the easiest way to publish a wrong number (§13).
    """
    # One normalisation, stated once. `labels` and `profile` are two ways to
    # say the same thing and the precedence was never defined: `labels=True`
    # did not override `profile="codes"`, and the `labels is True` branch below
    # was a literal no-op (`strict_labels or False` is `strict_labels`).
    #
    # `profile` is the richer control, so an explicit non-default profile wins.
    # `labels` only decides between rendering and not.
    # `fetch(years=2024)` works; `load(years=2024)` used to reach
    # `list(years)` and raise. Public functions that present themselves as
    # parallel should accept the same filters.
    if isinstance(years, int):
        years = [years]
    if isinstance(uf, str):
        uf = [uf]

    if labels is False:
        profile = "codes"
    elif labels is True and profile == "codes":
        profile = "analysis"
    own = catalog is None
    cat = catalog or Catalog(root=root, settings=settings)
    try:
        store = cat.store
        families, presence, axis_notes = _resolve_generations(
            store,
            system,
            series,
            family_id=family_id,
            uf=uf,
            years=years,
            columns=columns,
        )
        wanted: list[str] | None = list(columns) if columns else None
        tables, structurally_absent = _read_generations(
            cat,
            families,
            system=system,
            uf=uf,
            years=years,
            wanted=wanted,
            presence=presence,
            on_missing_column=on_missing_column,
        )
        if not tables:
            # The same class fetch() raises for the same situation. load() used
            # to raise a bare FileNotFoundError here and KeyError above, so
            # robust downstream handling depended on which retrieval path the
            # caller happened to use.
            from .retrieve import NothingPublished

            raise NothingPublished(
                f"no lake data for system={system!r} series={series!r}; run "
                "`pegasus-data build` first"
            )

        # Render each (family, year) with ITS OWN bindings and codelist vintage,
        # then combine. This used to concatenate everything first and render the
        # lot once with `min(years)` and `family_id=None`, which meant
        # `load(years=range(1995, 2025))` labelled every row with the 1995
        # vintage, `years=None` labelled historical rows with today's codelist,
        # and any family-specific binding was discarded the moment two families
        # were combined. A plausible wrong label is worse than a missing one,
        # and classification vintages are exactly where that bites.
        #
        # `year` is a Hive partition column in the lake, so the scoping is
        # row-level rather than a hint about the request.
        rendered_parts: list[pa.Table] = []
        render_report = None
        for family_id, table in tables:
            for chunk, chunk_year in _by_vintage(table, years):
                part, part_report = render_table(
                    chunk,
                    store=store,
                    lake_root=cat.settings.lake_dir,
                    system=system,
                    family_id=family_id,
                    profile=profile,
                    render=render,
                    headers=headers,
                    values=values,
                    companions=companions,
                    derived=derived,
                    year=chunk_year,
                    strict=strict_labels,
                )
                rendered_parts.append(part)
                render_report = _merge_reports(render_report, part_report)
        rendered = (
            rendered_parts[0]
            if len(rendered_parts) == 1
            else pa.concat_tables(rendered_parts, promote_options="permissive")
        )
        for note in axis_notes:
            render_report.warnings.append(note)
        if structurally_absent and render_report is not None:
            for fam, cols in sorted(structurally_absent.items()):
                render_report.warnings.append(
                    f"{', '.join(cols)}: absent from the schema of generation {fam}; "
                    "those rows are null here STRUCTURALLY — the field does not "
                    "exist for them, it was not left blank"
                )
        return (rendered, render_report) if report else rendered
    finally:
        if own:
            cat.close()


def load_population(
    *,
    series: str = "POPSVS",
    uf: str | Sequence[str] | None = None,
    years: Sequence[int] | range | None = None,
    by: Sequence[str] = ("municipality", "year"),
    catalog: Catalog | None = None,
    # Both of these were REFERENCED in the body and never declared, so every
    # call without an explicit catalog raised NameError: name 'root' is not
    # defined. Same family as export() forwarding root= nowhere.
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> pa.Table:
    """Load a denominator series, refusing a stratification it cannot support.

    ``POPTCU`` carries no age and no sex, so asking it for an age breakdown
    raises rather than silently returning a coarser table that would then be
    labelled age-standardised.
    """
    own = catalog is None
    cat = catalog or Catalog(root=root, settings=settings)
    try:
        spec = KNOWN_SERIES.get(series)
        if spec is None:
            raise KeyError(f"unknown population series {series!r}; known: {sorted(KNOWN_SERIES)}")
        supported, missing = spec.supports(list(by))
        if not supported:
            raise UnsupportedStratification(series, missing, spec.stratifications)
        directory = cat.settings.population_dir / series
        if not directory.exists():
            raise FileNotFoundError(
                f"population series {series!r} is not in the lake; run `pegasus-data population`"
            )
        import pyarrow.dataset as pads

        dataset = pads.dataset(directory, format="parquet", partitioning="hive")
        expression = None
        if uf is not None and "uf" in dataset.schema.names:
            ufs = [uf] if isinstance(uf, str) else list(uf)
            expression = pads.field("uf").isin(ufs)
        if years is not None and "year" in dataset.schema.names:
            year_filter = pads.field("year").isin(list(years))
            expression = year_filter if expression is None else (expression & year_filter)
        return dataset.to_table(filter=expression)
    finally:
        if own:
            cat.close()


def load_reference(
    table: str,
    *,
    year: int | None = None,
    valid_from: str | None = None,
    code_width: int | None = None,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
    competencia: int | None = None,
) -> pa.Table:
    """Load a reference code table at the vintage that covers `year`.

    This is where the meaning of a hierarchical code lives — CID-10, procedures,
    CBO, municipalities. It is a join rather than a materialised column so the
    consumer picks the granularity (a code or its chapter) and the vintage (the
    1992–1997 table or today's), neither of which the lake should settle on their
    behalf::

        cid = load_reference("CID10", year=2019)
        admissions.join(cid, keys="DIAG_PRINC", right_keys="code")
    """
    own = catalog is None
    cat = catalog or Catalog(root=root, settings=settings)
    try:
        return read_reference_table(
            cat.settings.lake_dir,
            table,
            valid_from=valid_from,
            year=year,
            competencia=competencia,
            code_width=code_width,
        )
    finally:
        if own:
            cat.close()


def reference_tables(root: str | Path | None = None) -> list[dict[str, Any]]:
    """Which reference tables the lake holds, and in which validity windows."""
    cat = Catalog(root)
    try:
        return available_tables(cat.settings.lake_dir)
    finally:
        cat.close()


@dataclass
class LakeScan:
    """A lazy, bounded-memory read of one dataset. The missing middle primitive.

    Between ``fetch()``/``load()``, which materialise a whole ``pa.Table``, and
    a raw DuckDB connection, which knows nothing about generations, axes or
    codelists, there was nothing. A national multi-year question therefore had
    exactly one supported shape: build the entire answer in memory first.

    A scan carries the same guards as ``load()`` — declared-dataset resolution,
    the file-axis refusal, generation pruning — and then hands back batches.
    Projection and the year/UF filters are pushed into the Parquet scan, so
    unread columns and unmatched partitions are never read at all.

    Iterating twice re-scans; nothing is cached, which is the point.
    """

    #: One scanner per schema generation. They are separate deliberately: two
    #: generations do not share a schema, and concatenating them is a decision
    #: (see `on_missing_column`) rather than something a scan should do quietly.
    scanners: list[tuple[str, ds.Scanner]]
    system: str
    series: str | None = None
    families: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def schema(self) -> pa.Schema:
        """The first generation's schema. Others may differ — that is the point
        of keeping them apart, and `schemas` gives all of them."""
        return self.scanners[0][1].dataset_schema if self.scanners else pa.schema([])

    @property
    def schemas(self) -> dict[str, pa.Schema]:
        return {fam: sc.dataset_schema for fam, sc in self.scanners}

    def count_rows(self) -> int:
        """How many rows the request matches, WITHOUT reading them.

        Parquet stores row counts in its footers, so this reads metadata rather
        than data — which is what makes "is this question too big for memory?"
        answerable before committing to it.
        """
        return sum(sc.count_rows() for _, sc in self.scanners)

    def iter_batches(self) -> Iterator[pa.RecordBatch]:
        """Yield batches across every generation, in family order."""
        for _fam, scanner in self.scanners:
            yield from scanner.to_batches()

    def __iter__(self) -> Iterator[pa.RecordBatch]:
        return self.iter_batches()

    def to_table(self) -> pa.Table:
        """Materialise it after all. The escape hatch, named as one."""
        parts = [sc.to_table() for _, sc in self.scanners]
        parts = [p for p in parts if p.num_rows]
        if not parts:
            return pa.table({})
        if len({tuple(p.schema.names) for p in parts}) == 1:
            return pa.concat_tables(parts)
        return pa.concat_tables(parts, promote_options="permissive")


def scan(
    system: str,
    series: str | None = None,
    *,
    uf: str | Sequence[str] | None = None,
    years: int | Sequence[int] | range | None = None,
    columns: Sequence[str] | None = None,
    where: ds.Expression | None = None,
    batch_size: int = 131_072,
    family_id: str | None = None,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> LakeScan:
    """A lazy read of lake data: projection, predicates, bounded memory.

    ``where`` is a ``pyarrow.dataset`` expression over the data columns, pushed
    into the scan — ``scan("SIHSUS", "RD", where=ds.field("SEXO") == "1")``
    reads only the row groups that can contain matches.

    Labels are NOT applied. Rendering weighs codelists against the values a
    column actually holds, which is a whole-column question, and answering it
    per batch would let two batches of one column disagree. Call
    :func:`load` when you want labels, or render a batch yourself.
    """
    own = catalog is None
    cat = catalog or Catalog(root=root, settings=settings)
    try:
        store = cat.store
        families = _resolve_family(store, system, series, None)
        if not families:
            from .retrieve import DatasetUnknown

            raise DatasetUnknown(
                f"no family found for system={system!r} series={series!r}"
            )
        if family_id:
            families = [f for f in families if f["family_id"] == family_id]
        if isinstance(years, int):
            years = [years]
        if isinstance(uf, str):
            uf = [uf]

        # The same refusal load() and fetch() apply. A filter on an axis this
        # dataset does not have is a false answer, not a narrow one.
        from .retrieve import FilterHasNoAxis, axis_refusal

        refusal, axis_notes = axis_refusal(
            store,
            system,
            series or (families[0]["series"] if families else None),
            uf=bool(uf),
            years=bool(years),
            months=False,
        )
        if refusal:
            raise FilterHasNoAxis(refusal)

        warnings_out: list[str] = list(axis_notes)
        scanners: list[tuple[str, ds.Scanner]] = []
        for family in families:
            try:
                scanner = cat.lake.scanner(
                    system=system,
                    family_id=str(family["family_id"]),
                    uf=uf,
                    years=list(years) if years else None,
                    columns=list(columns) if columns else None,
                    optional_columns=[
                        f"{c}{suffix}"
                        for c in (columns or [])
                        for suffix in COMPANION_SUFFIXES
                    ],
                    where=where,
                    batch_size=batch_size,
                )
            except FileNotFoundError:
                continue
            except KeyError as exc:
                # A generation that lacks a requested column. Named, not
                # silently dropped — that was CR-03.
                warnings_out.append(f"{family['family_id']}: {exc}")
                continue
            scanners.append((str(family["family_id"]), scanner))
        if not scanners:
            from .retrieve import NothingPublished

            raise NothingPublished(
                f"no lake data for system={system!r} series={series!r}"
                + (f"; {warnings_out[0]}" if warnings_out else "")
                + "; run `pegasus-data build` first"
            )
        return LakeScan(
            scanners=scanners,
            system=system,
            series=series,
            families=[fam for fam, _ in scanners],
            warnings=warnings_out,
        )
    finally:
        if own:
            cat.close()


def open_lake(
    root: str | Path | None = None, *, settings: Settings | None = None
) -> DuckLake:
    """A DuckDB connection with every family registered as a view.

    The returned object owns the catalog it opened. It used to create a
    `Catalog`, hand its store to `DuckLake` and return only the DuckLake — whose
    close() closes DuckDB and nothing else. The catalog connection then had no
    reachable owner, so `open_lake()` leaked one every call.
    """
    cat = Catalog(root, settings=settings)
    duck = DuckLake(cat.settings.lake_dir, cat.store)
    duck.register_all()
    duck._owned_catalog = cat  # closed by DuckLake.close()
    return duck


def export(
    system: str,
    series: str | None = None,
    *,
    path: str | Path | None = None,
    out: str | Path | None = None,
    format: str = "csv",
    uf: str | Sequence[str] | None = None,
    years: Sequence[int] | range | None = None,
    columns: Sequence[str] | None = None,
    family_id: str | None = None,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
    profile: str = "report",
    render: Mapping[str, str] | None = None,
    headers: str | None = None,
    values: str | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    strict_labels: bool = False,
    stream: bool = False,
) -> Path:
    """Write a rendered extract to a file. ``load()`` plus a writer.

    Deliberately not a second implementation: this calls :func:`load` and shares
    its rendering path entirely, so an option can never mean one thing in a
    notebook and another in an exported file. The only differences are the
    default profile — ``report``, because a file someone opens in Excel wants
    translated headers and combined values — and the writer at the end.

    ``format`` is ``csv``, ``parquet`` or ``xlsx``. Excel needs the optional
    ``openpyxl`` dependency and is refused with a clear message when absent
    rather than half-written.

    ``stream=True`` writes batch by batch through :func:`scan` instead of
    building the whole table first, which is what makes a national multi-year
    export possible on an ordinary machine. It is only available WITHOUT
    rendering (``profile="codes"``), and to csv or parquet: choosing a codelist
    weighs it against the values a column actually holds, which is a
    whole-column question, and answering it per batch would let two batches of
    one column disagree. xlsx has to build a workbook in memory regardless.
    """
    path = path if path is not None else out
    fmt = format.lower().lstrip(".")
    if fmt not in {"csv", "parquet", "xlsx"}:
        raise ValueError(f"unknown export format {format!r}; use csv, parquet or xlsx")

    if path is None:
        parts = [system, series or "all"]
        if uf:
            parts.append(uf if isinstance(uf, str) else "-".join(uf))
        if years:
            ys = list(years)
            parts.append(str(ys[0]) if len(ys) == 1 else f"{min(ys)}-{max(ys)}")
        path = Path(f"{'_'.join(str(p) for p in parts)}.{fmt}")

    if stream:
        if profile != "codes":
            raise ValueError(
                f"stream=True cannot render (profile={profile!r}). Choosing a "
                "codelist weighs it against the values a column holds, which is a "
                'whole-column question; use profile="codes" to stream, or drop '
                "stream= to render."
            )
        if fmt == "xlsx":
            raise ValueError(
                "stream=True is not available for xlsx: a workbook is built in "
                "memory before it can be written. Use csv or parquet."
            )
        scan_result = scan(
            system,
            series,
            uf=uf,
            years=years,
            columns=columns,
            family_id=family_id,
            catalog=catalog,
            root=root,
            settings=settings,
        )
        return _write_streaming(scan_result, path, fmt)

    table = load(
        system,
        series,
        uf=uf,
        years=years,
        columns=columns,
        family_id=family_id,
        catalog=catalog,
        # Forward where to look. export() grew root=/settings= but kept passing
        # only `catalog`, so export(root=...) loaded from the DEFAULT root and
        # failed with "no family found" while the requested root held the data.
        root=root,
        settings=settings,
        profile=profile,
        render=render,
        headers=headers,
        values=values,
        companions=companions,
        derived=derived,
        strict_labels=strict_labels,
    )
    assert isinstance(table, pa.Table)
    return write_table(table, path, fmt)


def _write_streaming(scan_result: LakeScan, path: str | Path, fmt: str) -> Path:
    """Write a scan batch by batch. Never holds more than one batch.

    Staged and renamed, like every other write in this package: an interrupted
    export otherwise leaves a truncated file at the name the caller will read
    back, and a short CSV is indistinguishable from a small answer.
    """
    import pyarrow.csv as pacsv
    import pyarrow.parquet as pq

    target = Path(path)
    if target.parent != Path():
        target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(target.name + ".part")

    writer = None
    try:
        # The writer must be closed INSIDE this block: both Arrow writers finish
        # their output on close (parquet writes its footer), and closing after
        # the handle is gone raises "write to closed file" and leaves a file
        # with no footer — unreadable, at the name the caller will read back.
        with staged.open("wb") as sink:
            for batch in scan_result.iter_batches():
                if not batch.num_rows:
                    continue
                # Same list-flattening rule as write_table: a multi-valued
                # field's *_codes companion has no CSV representation, and
                # letting it through as a Python repr is how a column silently
                # stops being parseable.
                flat = _flatten_lists(pa.Table.from_batches([batch]))
                if writer is None:
                    writer = (
                        pq.ParquetWriter(sink, flat.schema, compression="zstd")
                        if fmt == "parquet"
                        else pacsv.CSVWriter(sink, flat.schema)
                    )
                writer.write_table(flat)
            if writer is not None:
                writer.close()
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    if writer is None:
        # No rows at all. Write the header so the file is still readable.
        staged.unlink(missing_ok=True)
        return write_table(pa.table({}), target, fmt)
    os.replace(staged, target)
    return target


def write_table(table: pa.Table, path: str | Path, format: str = "csv") -> Path:
    """Write a rendered table to CSV, Parquet or Excel.

    Split out of :func:`export` so the ``get`` command can reach it: a table
    fetched straight from DATASUS and a table read out of the lake are the same
    thing by the time they arrive here, and writing them two different ways
    would be two different sets of quoting and list-flattening rules to keep in
    agreement.
    """
    fmt = format.lower().lstrip(".")
    if fmt not in {"csv", "parquet", "xlsx"}:
        raise ValueError(f"unknown export format {format!r}; use csv, parquet or xlsx")
    target = Path(path)
    if target.parent != Path():
        target.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "parquet":
        import pyarrow.parquet as pq

        pq.write_table(table, target, compression="zstd")
    elif fmt == "csv":
        import pyarrow.csv as pacsv

        # A list column (a multi-valued field's *_codes companion) has no CSV
        # representation, so it is joined rather than silently stringified as a
        # Python repr.
        flattened = _flatten_lists(table)
        pacsv.write_csv(flattened, target)
    else:
        _write_xlsx(table, target)
    return target


def _flatten_lists(table: pa.Table) -> pa.Table:
    """Render list columns as text so CSV and Excel can carry them."""
    columns = []
    for name in table.schema.names:
        column = table.column(name)
        if pa.types.is_list(column.type) or pa.types.is_large_list(column.type):
            columns.append(
                pa.array(
                    [
                        None if v is None else " | ".join("" if t is None else str(t) for t in v)
                        for v in column.to_pylist()
                    ],
                    type=pa.string(),
                )
            )
        else:
            columns.append(column.combine_chunks())
    return pa.Table.from_arrays(columns, names=list(table.schema.names))


#: Excel's hard limits. A workbook beyond either is not a large workbook, it is
#: a file Excel opens truncated or refuses outright.
XLSX_MAX_ROWS = 1_048_576
XLSX_MAX_COLUMNS = 16_384


def _write_xlsx(table: pa.Table, target: Path) -> None:
    # Checked BEFORE writing. A large epidemiological extract silently exceeded
    # these and produced a workbook Excel cannot faithfully represent — the
    # rows past the limit simply are not there, and nothing said so.
    if table.num_rows > XLSX_MAX_ROWS - 1:  # -1 for the header row
        raise ValueError(
            f"{table.num_rows:,} rows exceeds what Excel can hold "
            f"({XLSX_MAX_ROWS:,} including the header). Export to csv or parquet, "
            f"or narrow the request with uf=/years=/columns=."
        )
    if table.num_columns > XLSX_MAX_COLUMNS:
        raise ValueError(
            f"{table.num_columns:,} columns exceeds Excel's limit of "
            f"{XLSX_MAX_COLUMNS:,}. Use columns= to choose what you need."
        )
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise ImportError(
            "xlsx export needs openpyxl: pip install 'pegasus-data[excel]'"
        ) from exc

    flattened = _flatten_lists(table)
    book = Workbook(write_only=True)
    sheet = book.create_sheet("data")
    sheet.append(list(flattened.schema.names))
    for batch in flattened.to_batches(max_chunksize=2048):
        rows = [batch.column(i).to_pylist() for i in range(batch.num_columns)]
        for values in zip(*rows, strict=True):
            sheet.append(list(values))
    book.save(target)
