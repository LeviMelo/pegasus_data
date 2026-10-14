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
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pyarrow as pa

from ._lazy import LazyModule  # noqa: E402
from .catalog.store import CatalogStore as _Store
from .config import Settings, load_settings
from .lookups import _single_lookup
from .normalize.engine import MissingColumnError
from .persist.duck import DuckLake
from .persist.lake import Lake, LakePartition
from .persist.reference import is_hierarchical, read_reference_table
from .persist.staging import staged_file
from .profile.drift import field_availability
from .semantics.dictionary import (
    binding_sources,
    codelists_for,
    lookup,
    match_codelist_by_name,
    observed_values,
    rollups_for,
)
from .semantics.label_bindings import field_decision
from .sources.ibge import KNOWN_SERIES, UnsupportedStratification, series_catalogue
from .view import (
    COMPANION_SUFFIXES,
    PROFILES,
    LabelUnavailable,
    RenderMode,
    RenderReport,
)

ds = LazyModule("pyarrow.dataset")

__all__ = [
    "Catalog",
    "describe",
    "levels",
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
    #: What the curation layer says this column MEANS, and in English.
    #:
    #: describe() answers "what does this column mean" and had nowhere to put an
    #: answer: it carried `official_name` and no prose, and read that name from
    #: the ledger, `field_documentation` and `def_variables` while never
    #: consulting `variable_docs` — so 4,534 curated descriptions, the whole
    #: point of the curation layer and of §9, were invisible to the one verb
    #: whose job is to show them. ARCHITECTURE §14 lists curation as backing
    #: this function; now it does.
    translated_name: str | None = None
    description: str | None = None
    code_system: str | None = None
    #: The evidence rung behind `description` — `manual`, `layout_doc`, `def`,
    #: `web` or `inferred` — and the document it cites. An inferred description
    #: read as a documented one is the failure the rungs exist to prevent, so
    #: the rung travels with the prose rather than being left in the YAML.
    description_source: str | None = None
    description_source_ref: str | None = None
    #: Whether a cell holds several codes, and how to split them (the curation's ``multi_valued`` and
    #: ``token_rule``): SINASC's CODANOMAL packs four-character ICD-10 codes. A reader that took such a cell as one
    #: code would mis-read every newborn with two anomalies.
    multi_valued: bool = False
    token_rule: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "series": self.series,
            "family_id": self.family_id,
            "field": self.field_name,
            "official_name": self.official_name,
            "translated_name": self.translated_name,
            "description": self.description,
            "code_system": self.code_system,
            "description_source": self.description_source,
            "description_source_ref": self.description_source_ref,
            "multi_valued": self.multi_valued,
            "token_rule": self.token_rule,
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
        # An existing catalog is read through the process's one read-only connection to it (`CatalogStore.shared`):
        # warm pages, and the snapshot the memoised reads below are exact against. close() releases it.
        self.store = _Store.shared(self.settings.catalog_path) if exists else _Store(self.settings.catalog_path)
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


def _system_spellings(system: str) -> list[str]:
    """Every name the crawl might have filed this system under.

    The declaration carries them: `SystemNode.crawled_as` is exactly the list of
    directory names a system has appeared as. Asking for all of them makes the
    institutional name and the crawled name interchangeable at the API, which is
    what `info()` and `fetch()` already promise and `describe()`/`load()` did not
    deliver.
    """
    asked = str(system or "").strip().upper()
    if not asked:
        return [asked]
    from ._request import _ontology

    onto = _ontology()
    node = onto.system_of(asked) if onto is not None else None
    if node is None:
        return [asked]
    return sorted({asked, str(node.code).upper(), *(str(a).upper() for a in node.crawled_as)})


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

    The SYSTEM half of that fix was missed. `families.system` holds the CRAWLED
    name — SIHSUS, SIASUS — while the API and the ontology speak the
    institutional one, SIH and SIA, so filtering the table with the caller's
    spelling returned nothing at all for exactly the names §14.5 promises
    resolve: `describe("SIH", "RD")` raised DatasetUnknown while
    `describe("SIHSUS", "RD")` worked, and `fetch("SIH-RD")` worked throughout.
    Every spelling the declaration knows is asked for instead.
    """
    def resolve() -> list[dict[str, Any]]:
        spellings = _system_spellings(system)
        rows = store.query(
            "SELECT family_id, system, series, schema_signature, field_count, time_min, time_max "
            f"FROM families WHERE system IN ({','.join('?' * len(spellings))}) "
            "ORDER BY COALESCE(time_max, 0) DESC",
            spellings,
        )
        families = [dict(r) for r in rows]
        if series:
            from ._request import _ontology

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
        # THE labelling table: the one a query renders from (label_bindings.field_decision, OQ 79)
        decision = field_decision(
            store, system=system, family_id=family_id, field_name=field, counts=observed,
            load=lambda codelist: _single_lookup(
                cat.settings.lake_dir, codelist, system, None, None, registries=cat.settings.registries_dir
            ),
        )
        labelled_by = decision.codelists if decision.labels else ()
        labels = lookup(store, system=system, field_name=field, observed=observed, labelled_by=labelled_by)
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

        # CURATION FIRST. `manual` is source authority 0 — a person who read the
        # form outranks any extraction — and this is the door §9 exists to open.
        # It was never consulted here, so a curated column answered with a null
        # name and no prose, which reads as "nothing is known about this" rather
        # than "look in the layer built to answer exactly this".
        from .semantics.curation import load_variable_docs

        curated = load_variable_docs(store, system).get(field.upper())
        translated_name = curated.translated_name if curated else None
        description = curated.description if curated else None
        code_system = curated.code_system if curated else None
        description_source = curated.source if curated else None
        description_source_ref = curated.source_ref if curated else None

        official_name = (curated.official_name if curated else None) or led.get("official_name")
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
        chosen = labelled_by[0] if labelled_by else None
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
                "tables": list(labelled_by),
                "decided_by": decision.basis,
                "decision": decision.reason,
                # a catalog never profiled holds no values to weigh against: the decision then rests on what needs none
                "observed_codes": len(observed),
                "hierarchical": hierarchical,
                "bound_by": sources.get(chosen) or ("curation" if decision.basis == "curated" else "unknown"),
                "authoritative": decision.basis == "curated" or sources.get(chosen) in {"def", "manual", "layout_doc"},
                "validity_windows": windows,
                "rollup_levels": [
                    r["codelist"]
                    for r in rollups_for(store, system=system, field_name=field, observed=observed, labelled_by=labelled_by)
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
            translated_name=translated_name,
            description=description,
            code_system=code_system,
            description_source=description_source,
            description_source_ref=description_source_ref,
            multi_valued=bool(curated and curated.multi_valued),
            token_rule=dict(curated.token_rule) if curated and curated.token_rule else None,
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
            rollups=rollups_for(store, system=system, field_name=field, observed=observed, labelled_by=labelled_by),
            provenance=json.loads(led.get("provenance") or "[]"),
            open_questions=open_questions,
            reference=reference,
            label_policy=label_policy,
            generations=generations,
        )
    finally:
        if own:
            cat.close()


def levels(
    dataset: str,
    field: str,
    codes: Sequence[str],
    *,
    year: int | None = None,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> dict[str, str]:
    """``code -> label`` for ``codes`` of one field of ``dataset``, labelled as a query labels them (`view.codelist_levels`:
    the same renderer, so a level named here and the same level in a cell cannot disagree). A code no chosen table
    decodes is absent: its label is unknown, never guessed."""
    from ._request import parse_dataset
    from .view import codelist_levels

    system, series = parse_dataset(dataset)
    own = catalog is None
    cat = catalog or Catalog(root=root, settings=settings)
    try:
        candidates = _resolve_family(cat.store, system, series, field)
        family_id = candidates[0]["family_id"] if candidates else None
        return codelist_levels(field, store=cat.store, lake_root=cat.settings.lake_dir, system=system,
                               family_id=family_id, year=year, codes=list(codes),
                               registries=cat.settings.registries_dir)
    finally:
        if own:
            cat.close()


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


@dataclass(slots=True)
class _Resolved:
    """What :func:`_resolve_generations` decided: which generations answer a request, which files, what they carry."""

    #: the generations in play: those with a listed lake partition in the states and years asked
    families: list[dict[str, Any]]
    #: schema signature -> the fields its census lists, for every generation of the dataset
    presence: dict[str, frozenset[str]]
    axis_notes: list[str]
    #: family_id -> the partition files to read (the catalog's list, narrowed to the request)
    partitions: dict[str, list[LakePartition]]
    #: every generation of the dataset (or the one family asked for), in play or not
    dataset_families: list[dict[str, Any]]


def _schema_presence(store: _Store, families: Sequence[Mapping[str, Any]]) -> dict[str, frozenset[str]]:
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


def _resolve_generations(
    store: _Store,
    system: str,
    series: str | None,
    *,
    family_id: str | None,
    uf: Sequence[str] | None,
    years: Sequence[int] | None,
    lake: Lake,
) -> _Resolved:
    """Which schema generations answer this request, which files they are, and what fields they carry.

    Dataset resolution, the file-axis refusal, the lake's own list of partitions and the schema-presence matrix —
    everything that decides WHICH generations are in play, before any of them is opened. Kept apart from reading them
    because the two failure modes differ: this one refuses a question, the other reports what a generation could not
    give. ``load`` and ``scan`` both start here, so a dataset is resolved, refused and pruned one way.
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
    dataset_families = families

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

    # The files come from the catalog's list of the lake (`lake_partitions`, written with each file), not from a walk
    # of the directory: only the generations with a partition in the states and years asked are opened, and a file
    # the catalog does not list is never read.
    listed = lake.listed([str(f["family_id"]) for f in families]) or {}
    partitions: dict[str, list[LakePartition]] = {}
    for f in families:
        # an empty list of states or years is no filter, as it is to the axis refusal above (`bool(uf)`)
        parts = Lake.narrow(listed.get(str(f["family_id"]), ()), uf or None, years or None)
        if parts:
            partitions[str(f["family_id"])] = parts
    if not uf:
        # no state asked: a year held as the national file AND as its state files is the same records twice
        from ._query_engine.coverage import national_or_states

        by_year: dict[int, list[tuple[str, LakePartition]]] = {}
        for fid, parts in partitions.items():
            for part in parts:
                by_year.setdefault(part.year, []).append((fid, part))
        kept: set[tuple[str, str]] = set()
        total = 0
        for items in by_year.values():
            chosen = national_or_states(items, lambda item: item[1].uf)
            kept.update((fid, part.relative_path) for fid, part in chosen)
            total += len(items)
        if len(kept) < total:
            partitions = {
                fid: [p for p in parts if (fid, p.relative_path) in kept] for fid, parts in partitions.items()
            }
            partitions = {fid: parts for fid, parts in partitions.items() if parts}
            axis_notes = [*axis_notes, (
                f"{system}.{series or ''}: the lake holds {total - len(kept)} state partition(s) of years that also have "
                "a national file; only the national file is read (the state files are the same records)"
            )]
    in_play = [f for f in families if str(f["family_id"]) in partitions]
    return _Resolved(
        in_play, _schema_presence(store, dataset_families), list(axis_notes), partitions, dataset_families,
    )


def _require_known_columns(
    store: _Store, system: str, series: str | None, dataset_families: Sequence[Mapping[str, Any]],
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
    presence = _schema_presence(store, dataset_families)
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


def _keeps_companions(profile: str, companions: bool | Sequence[str] | None) -> bool:
    """Will the render keep companion columns (``X_uf``, ``X_ibge7`` ...)? If not they are not worth reading."""
    from .view import resolve_profile

    if isinstance(companions, (list, tuple, set)):
        return bool(companions)
    return resolve_profile(profile, companions=companions).companions


def normalise_prefix(code: object) -> str:
    """A code prefix as every row filter compares it: without dots, trimmed, upper case (``"j18.9"`` is ``"J189"``,
    the way DATASUS writes the code). The one spelling for the lake's scan, the fetched year and the extracts."""
    return str(code).replace(".", "").strip().upper()


def prefix_match(text: Any, prefixes: Sequence[str]) -> Any:
    """Is ``text`` (an array, or a scan expression) one of the codes that start with one of the normalised
    ``prefixes``? The one prefix test of the lake's scan, the fetched year and the extracts."""
    import pyarrow.compute as pc

    upper = pc.utf8_upper(text)
    hit = None
    for prefix in prefixes:
        one = pc.starts_with(upper, pattern=prefix)
        hit = one if hit is None else pc.or_kleene(hit, one)
    return hit


def _rows_filters(rows: Mapping[str, Sequence[str]] | None) -> dict[str, tuple[str, ...]]:
    """The row filter, checked: ``{column: code prefixes}``, each a non-empty column name with non-empty prefixes,
    the prefixes normalised (:func:`normalise_prefix`).

    An empty list of prefixes selects no row, and the filter used to select every row instead (a topic with no codes
    read a whole year of admissions as its cases); a second empty one crashed in Arrow.
    """
    out: dict[str, tuple[str, ...]] = {}
    for column, prefixes in (rows or {}).items():
        if not isinstance(column, str) or not column.strip():
            raise ValueError(f"rows: {column!r} is not a column name")
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        codes = tuple(normalise_prefix(p) for p in prefixes)
        if not codes:
            raise ValueError(f"rows[{column!r}] is empty: a filter on no codes selects no record (give prefixes, or drop it)")
        if any(not p for p in codes):
            raise ValueError(f"rows[{column!r}] holds a blank prefix, which every value starts with")
        out[column] = codes
    return out


def _rows_expression(rows: Mapping[str, Sequence[str]]) -> ds.Expression:
    """The rows whose every named column starts with one of its codes (``{column: prefixes}``), as a scan predicate."""
    import pyarrow.compute as pc

    out = None
    for column, prefixes in _rows_filters(rows).items():
        hit = prefix_match(pc.field(column).cast(pa.string()), prefixes)
        out = hit if out is None else (out & hit)
    return out


def _read_generations(
    cat: Catalog,
    resolved: _Resolved,
    *,
    system: str,
    wanted: list[str] | None,
    on_missing_column: str,
    rows: Mapping[str, Sequence[str]] | None = None,
    companion_probes: bool = True,
    leave_out: frozenset[str] = frozenset(),
    also_read: Sequence[str] = (),
) -> tuple[list, dict[str, list[str]]]:
    """Read each generation, applying the structural missing-column policy.

    Returns ``(tables, structurally_absent)``. Generations are read separately
    and combined by the caller: two generations do not share a schema, and
    which of them may be null-filled together is a policy decision
    (``on_missing_column``), not something a reader should settle quietly.

    Every file the catalog lists for the request must be on disk (`PartialLakeError`): a generation is never skipped
    because its file went missing. ``leave_out``: stored columns not worth decoding when ``wanted`` is None (the
    provenance the caller drops, labels the renderer ignores). ``also_read``: columns read only if a generation
    carries them, for the render to use (a label's key parts) and the caller to drop; never required, never reported.
    """
    lake = cat.lake
    structurally_absent: dict[str, list[str]] = {}
    tables: list[pa.Table] = []
    filters = _rows_filters(rows)
    where = _rows_expression(filters) if filters else None
    for family in resolved.families:
        fid = str(family["family_id"])
        parts = resolved.partitions[fid]
        lake.check_files(parts)
        projection = None
        if wanted is not None:
            # Partition columns are columns of the LAKE, not fields of the
            # source schema, so `schema_presence` does not list them. Asking
            # for `year` or `uf` is legitimate and was being refused as a
            # column no generation carries.
            #
            # AN UNCENSUSED GENERATION IS NOT AN EMPTY ONE. A signature with no
            # `schema_presence` rows produced an empty set, so every requested
            # column looked absent and the caller was told, positively, that the
            # field does not exist there. That is unknown reported as absent —
            # the one substitution this package exists to refuse. The Parquet
            # files are the fallback evidence: they are the data, and they say
            # exactly which columns are in them.
            present = resolved.presence.get(str(family["schema_signature"]), frozenset())
            if not present:
                present = frozenset(lake.columns_of(parts))
            present = present | LAKE_COLUMNS
            missing = [c for c in wanted if c not in present]
            if missing and on_missing_column == "null_fill":
                # Keep the generation and read what it does have; concat
                # null-fills the rest. Recorded, because those nulls are
                # STRUCTURAL — the field does not exist here.
                structurally_absent[fid] = list(missing)
                projection = [c for c in wanted if c in present]
                missing = []
            if missing:
                elsewhere = [
                    str(f["family_id"])
                    for f in resolved.dataset_families
                    if all(
                        c in resolved.presence.get(str(f["schema_signature"]), frozenset())
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
        elif leave_out:
            stored = lake.columns_of(parts)
            projection = [
                c for c in stored
                if c not in leave_out and not (c.endswith("_label") and c.removesuffix("_label") in stored)
            ]
        # Companion columns the build materialised are still worth reading when the caller keeps companions; labels
        # are no longer projected here, they are joined below.
        optional = [f"{c}{suffix}" for c in (wanted or []) for suffix in COMPANION_SUFFIXES] if companion_probes else []
        # `year` is an internal SEMANTIC DEPENDENCY of rendering, not a column
        # the caller asked for. Rendering splits the answer so 1995 records are
        # translated with the 1995 codebook, and that split reads the `year`
        # partition column. A projection dropped it, so a projected multi-year
        # load silently fell back to translating everything at the earliest
        # requested vintage — reintroducing the exact defect the split fixes.
        # Requested as OPTIONAL so a generation without the column is not an
        # error, and dropped again before the result is returned.
        optional.append("year")
        optional.append("_competencia")
        optional.append("_source_resolution")
        optional.extend(also_read)
        # a row filter needs its columns in the generation. One without them cannot say which of its rows match: none
        # is returned, unread, and the absence is RECORDED, never an empty generation that looks like no records (a
        # residence filter on SIM-DOFET's 1995 files, whose residence is MUNIRES, had read as no foetal deaths)
        if filters:
            physical = set(lake.columns_of(parts))
            unfilterable = [c for c in filters if c not in physical]
            if unfilterable:
                structurally_absent.setdefault(fid, []).extend(f"{c} (row filter)" for c in unfilterable)
                continue
        table = lake.read(
            system=system,
            family_id=fid,
            columns=projection,
            optional_columns=optional,
            where=where,
            partitions=parts,
        )
        # A generation read and filtered to nothing is a result (zero records of the codes asked), kept so the answer
        # can be an empty table with its schema; without a filter an empty read has nothing to say.
        if table.num_rows or where is not None:
            tables.append((fid, table))
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
    render: Mapping[str, RenderMode] | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    strict_labels: bool = False,
    historical_labels: str = "current",
    allow_borrowed_labels: bool = False,
    on_missing_column: str = "raise",
    report: bool = False,
    _preserve_internal: bool = False,
    rows: Mapping[str, Sequence[str]] | None = None,
    _leave_out: frozenset[str] = frozenset(),
) -> pa.Table | tuple[pa.Table, RenderReport]:
    """Read a family out of the lake, rendered for reading. ``rows`` (``{column: code prefixes}``) keeps only the rows
    whose columns start with one of their codes, pushed into the scan, before anything is rendered or derived: a code
    set's records out of a year of admissions, not the year labelled and then filtered. An empty list of codes is
    refused (``ValueError``), a column no generation carries raises :class:`MissingColumnError`, and a filter that
    matches no record returns an empty table with its schema (not ``NothingPublished``, which is "no lake data").

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
        resolved = _resolve_generations(
            store,
            system,
            series,
            family_id=family_id,
            uf=uf,
            years=years,
            lake=cat.lake,
        )
        filters = _rows_filters(rows)
        wanted: list[str] | None = None
        helpers: frozenset[str] = frozenset()
        derived_names: frozenset[str] = frozenset()
        file_state = False
        if columns:
            # What a projection reads is `required_columns`, the rule fetch() follows too: a curated derived column
            # (IDADE_anos from IDADE and COD_IDADE) is made at render from its inputs, and a label from the columns of
            # its key, its sibling or its establishment. A select= that left them out labelled the column for fetched
            # years and not for lake years (2026-10-03: 0 newborn admissions, link "not viable"; CNES CLASS_SR
            # keyed by SERV_ESP + CLASS_SR came back undecoded). They are read, used, and dropped again below.
            from .semantics.curation import derived_inputs, load_variable_docs, required_columns
            from .view import resolve_profile

            docs = load_variable_docs(store, system)
            inputs_of = derived_inputs(docs)
            produced = isinstance(derived, (list, tuple, set)) and bool(derived) or (
                derived if isinstance(derived, bool) else resolve_profile(profile).derived)
            if produced:
                derived_names = frozenset(inputs_of)
            asked = {str(c).upper() for c in columns}
            needed = required_columns(docs, columns)
            # read only to render, and the derived columns the extra reads made possible: a projection means what it says
            helpers = frozenset((needed - asked) | (set(inputs_of) - asked))
            # a derived column is made after reading: its inputs are read, it is not
            wanted = [c for c in columns if str(c).upper() not in derived_names]
            file_state = any("@UF" in (docs[c].key or []) for c in needed if c in docs)
        # A column NO generation carries is a typo or a renamed field, never a structural absence to fill with nulls;
        # likewise a row filter on one. (A column some generations lack stays the recorded, null-filled case.)
        if columns and on_missing_column == "null_fill":
            _require_known_columns(store, system, series, resolved.dataset_families, list(columns), exempt=derived_names)
        if filters:
            _require_known_columns(store, system, series, resolved.dataset_families, list(filters))
        if not resolved.families:
            from .retrieve import NothingPublished

            raise NothingPublished(
                f"no lake data for system={system!r} series={series!r}"
                + (f", uf={list(uf)}" if uf else "") + (f", years={list(years)}" if years else "")
                + "; the catalog lists no lake partition for it. Run `pegasus-data build` first"
            )
        tables, structurally_absent = _read_generations(
            cat,
            resolved,
            system=system,
            wanted=wanted,
            on_missing_column=on_missing_column,
            rows=filters,
            companion_probes=_keeps_companions(profile, companions),
            leave_out=_leave_out,
            also_read=[*sorted(helpers), *(["uf"] if file_state else [])],
        )
        if not tables:
            # Every generation in play lacks a column the filter is on: the rows asked for cannot be told from the
            # others, and an empty answer would read as "none of those codes" (recorded in structural_absence).
            names = sorted({c.removesuffix(" (row filter)") for cols in structurally_absent.values() for c in cols})
            if filters and names:
                carriers = [
                    str(f["family_id"]) for f in resolved.dataset_families
                    if all(c in resolved.presence.get(str(f["schema_signature"]), frozenset()) for c in names)
                ]
                raise MissingColumnError(
                    names[0], ", ".join(sorted(structurally_absent)), carriers, also_absent=names[1:],
                )
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
        # The same operation fetch() uses. Two implementations of one rule is
        # how fetch() kept the cross-vintage bug this fixed in load().
        from .persist.decisions import borrowed_label_policy, historical_label_policy
        from .render_groups import render_groups, split_by_year_column

        groups = [
            group
            for family_id, table in tables
            for group in split_by_year_column(table, years, family_id)
        ]
        with (
            historical_label_policy(historical_labels),
            borrowed_label_policy(allow_borrowed_labels),
        ):
            rendered, render_report = render_groups(
                groups,
                store=store,
                lake_root=cat.settings.lake_dir,
                system=system,
                profile=profile,
                render=render,
                companions=companions,
                derived=derived,
                strict=strict_labels,
                registries=cat.settings.registries_dir,
            )
        if helpers:
            from .view import drop_helper_columns

            rendered = drop_helper_columns(rendered, helpers)
        if file_state and "uf" in rendered.schema.names and "UF" not in {str(c).upper() for c in columns or ()}:
            rendered = rendered.drop_columns(["uf"])        # read for a key's "@UF" part, not asked for
        if not _preserve_internal and wanted is not None and "YEAR" not in {c.upper() for c in wanted} and (
            "year" in rendered.schema.names
        ):
            # Carried for the vintage split, not requested. Dropped so a
            # projection means what it says.
            rendered = rendered.drop_columns(["year"])
        if not _preserve_internal and "_competencia" in rendered.column_names:
            rendered = rendered.drop_columns(["_competencia"])
        if not _preserve_internal and "_source_resolution" in rendered.column_names:
            rendered = rendered.drop_columns(["_source_resolution"])
        for note in resolved.axis_notes:
            render_report.warnings.append(note)
        if structurally_absent and render_report is not None:
            render_report.structural_absence = dict(sorted(structurally_absent.items()))
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
    years: int | Sequence[int] | range | None = None,
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
    if isinstance(years, int):
        years = [years]
    if isinstance(uf, str):
        uf = [uf]
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
        if uf is not None:
            ufs = [uf] if isinstance(uf, str) else list(uf)
            if "uf" in dataset.schema.names:
                expression = pads.field("uf").isin(ufs)
            elif "municipality" in dataset.schema.names:
                # POPSVS carries no uf column: the state is the municipality
                # code's first two digits. The filter used to be skipped here,
                # so uf="SE" returned the whole country (2026-10-03).
                from .geography import _uf_codes

                codes = _uf_codes(ufs)
                field_ = pads.field("municipality")
                for code in codes:
                    clause = (field_ >= code * 100000) & (field_ < (code + 1) * 100000)
                    expression = clause if expression is None else (expression | clause)
            else:
                raise ValueError(f"population series {series!r} has neither uf nor municipality to filter by")
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
    system: str | None = None,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
    competencia: int | None = None,
    allow_borrowed_labels: bool = False,
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
        from .persist.decisions import borrowed_label_policy

        with borrowed_label_policy(allow_borrowed_labels):
            return read_reference_table(
                cat.settings.lake_dir,
                table,
                valid_from=valid_from,
                year=year,
                competencia=competencia,
                code_width=code_width,
                # SEXO.CNV means 1/3 in SIHSUS and 1/2 in SINASC.
                system=system,
                registries=cat.settings.registries_dir,
            )
    finally:
        if own:
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
    #: When set, every yielded batch is conformed to this public schema.
    #: Physical scanners may carry an anchor partition column solely to retain
    #: row counts for a generation that lacks every requested data column.
    output_schema: pa.Schema | None = None

    @property
    def schema(self) -> pa.Schema:
        """The first generation's PROJECTED schema — what a batch will carry.

        `dataset_schema` is the physical file schema, which is not the scanner's
        output when `columns=` was given. Reporting it made a projected scan
        advertise columns the caller deliberately excluded, and
        `_write_streaming` builds the output file from these: a two-column
        request produced a file with every physical column, null-filled, and
        could fail on a type conflict in a column nobody asked for.
        """
        if self.output_schema is not None:
            return self.output_schema
        return self.scanners[0][1].projected_schema if self.scanners else pa.schema([])

    @property
    def schemas(self) -> dict[str, pa.Schema]:
        if self.output_schema is not None:
            return {fam: self.output_schema for fam, _sc in self.scanners}
        return {fam: sc.projected_schema for fam, sc in self.scanners}

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
            for batch in scanner.to_batches():
                yield (
                    _conform_batch(batch, self.output_schema)
                    if self.output_schema is not None
                    else batch
                )

    def __iter__(self) -> Iterator[pa.RecordBatch]:
        return self.iter_batches()

    def to_table(self) -> pa.Table:
        """Materialise it after all. The escape hatch, named as one."""
        batches = list(self.iter_batches())
        if not batches:
            return pa.Table.from_batches([], schema=self.schema)
        if self.output_schema is not None:
            return pa.Table.from_batches(batches, schema=self.output_schema)
        parts = [pa.Table.from_batches([batch]) for batch in batches]
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
    on_missing_column: str = "raise",
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
        if isinstance(years, int):
            years = [years]
        if isinstance(uf, str):
            uf = [uf]

        # The same resolution, axis refusal and pruning `load()` applies (`_resolve_generations`): a filter on an axis
        # this dataset does not have is a false answer, not a narrow one.
        resolved = _resolve_generations(
            store, system, series, family_id=family_id, uf=uf, years=years, lake=cat.lake,
        )
        warnings_out: list[str] = list(resolved.axis_notes)
        absent_by_family: dict[str, list[str]] = {}
        scanners: list[tuple[str, ds.Scanner]] = []
        requested = list(dict.fromkeys(str(c) for c in columns)) if columns else None
        requested_fields: dict[str, pa.Field] = {}
        declared_requested: set[str] = set()
        if requested:
            # a field some generation of the dataset declares exists, even where this lake holds no partition of it
            declared_requested = {name for name in requested
                                  if any(name in fields for fields in resolved.presence.values())}
        for family in resolved.families:
            family_name = str(family["family_id"])
            parts = resolved.partitions[family_name]
            cat.lake.check_files(parts)
            physical = cat.lake.dataset_of(parts)

            available = {field_.name: field_ for field_ in physical.schema}
            projection = requested
            if requested is None:
                # Month competence is retained solely to choose reference
                # vintages in load(); it is not a public data column.
                projection = [
                    name
                    for name in physical.schema.names
                    if name not in {"_competencia", "_source_resolution"}
                ]
            if requested is not None:
                missing = [name for name in requested if name not in available]
                for name in requested:
                    field_ = available.get(name)
                    if field_ is None:
                        continue
                    prior = requested_fields.get(name)
                    if prior is not None and prior.type != field_.type:
                        raise ValueError(
                            f"cannot scan {name!r} as one column: generations "
                            f"declare it as {prior.type} and {field_.type}"
                        )
                    requested_fields.setdefault(name, field_)
                if missing:
                    if on_missing_column != "null_fill":
                        raise MissingColumnError(
                            missing[0],
                            family_name,
                            [
                                str(f["family_id"])
                                for f in resolved.dataset_families
                                if str(f["family_id"]) != family_name
                            ],
                            also_absent=missing[1:],
                        )
                    absent_by_family[family_name] = missing
                    # Read only requested fields that physically exist. Lake's
                    # projection helper adds one partition anchor when this is
                    # empty so rows survive to be conformed into all-null
                    # requested batches.
                    projection = [name for name in requested if name in available]

            scanner = cat.lake.scanner(
                system=system,
                family_id=family_name,
                columns=projection,
                where=where,
                batch_size=batch_size,
                partitions=parts,
            )
            scanners.append((family_name, scanner))
        if not scanners:
            from .retrieve import NothingPublished

            raise NothingPublished(
                f"no lake data for system={system!r} series={series!r}"
                + (f"; {warnings_out[0]}" if warnings_out else "")
                + "; run `pegasus-data build` first"
            )
        if requested is not None:
            missing_everywhere = [name for name in requested if name not in requested_fields]
            # A declared generation may have no built partition in this lake.
            # It is still evidence that the requested field exists somewhere
            # in the dataset, while every selected row can legitimately be a
            # structural null.  With no physical Arrow type available the
            # honest output type is `null`, not an invented string.
            for name in list(missing_everywhere):
                if name in declared_requested:
                    requested_fields[name] = pa.field(name, pa.null())
                    missing_everywhere.remove(name)
            if missing_everywhere:
                raise MissingColumnError(
                    missing_everywhere[0],
                    "; ".join(fam for fam, _scanner in scanners),
                    [],
                    also_absent=missing_everywhere[1:],
                )
            output_schema = pa.schema([requested_fields[name] for name in requested])
        else:
            output_schema = None

        for fam, missing in sorted(absent_by_family.items()):
            warnings_out.append(
                f"{fam}: {', '.join(missing)} absent — those rows are null here "
                "STRUCTURALLY, the "
                "field does not exist in that generation"
            )
        return LakeScan(
            scanners=scanners,
            system=system,
            series=series,
            families=[fam for fam, _ in scanners],
            warnings=warnings_out,
            output_schema=output_schema,
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


_FORMATS = frozenset({"csv", "parquet", "xlsx"})
_SUFFIX_FORMATS = {".csv": "csv", ".parquet": "parquet", ".pq": "parquet", ".xlsx": "xlsx"}


def _format_for(path: Path | None, requested: str | None) -> str:
    """What to write: the explicit format, else the destination's suffix.

    ``format`` defaulted to ``"csv"``, so ``export(t, "x.parquet")`` wrote
    comma-separated text into a file named .parquet and every reader downstream
    failed on it. A suffix that names a format is a clear statement of intent
    and is now honoured.

    A contradiction between the two is refused rather than resolved: writing csv
    into a file called .parquet is never what the caller meant, and picking a
    winner silently is how the original bug read.
    """
    named = _SUFFIX_FORMATS.get(path.suffix.lower()) if path is not None else None
    if requested is not None:
        fmt = str(requested).lower().lstrip(".")
        if fmt not in _FORMATS:
            raise ValueError(
                f"unknown export format {requested!r}; use csv, parquet or xlsx"
            )
        if named and named != fmt:
            raise ValueError(
                f"export(format={requested!r}) writes {fmt}, but the destination is "
                f"named {path.name!r}. Give one or make them agree."  # type: ignore[union-attr]
            )
        return fmt
    return named or "csv"


def export(
    system: str | pa.Table,
    series: str | Path | None = None,
    *,
    path: str | Path | None = None,
    out: str | Path | None = None,
    format: str | None = None,
    uf: str | Sequence[str] | None = None,
    years: int | Sequence[int] | range | None = None,
    columns: Sequence[str] | None = None,
    family_id: str | None = None,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
    profile: str = "audit",
    present: object = None,
    render: Mapping[str, RenderMode] | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    strict_labels: bool = False,
    historical_labels: str = "current",
    allow_borrowed_labels: bool = False,
    stream: bool = False,
    on_missing_column: str = "raise",
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

    **A table already in hand is written directly**::

        table = fetch("SINASC-DN", uf="AC", years=2022)
        export(table, "births.parquet")

    Without this there was no supported way to put a fetched table on disk:
    export() only ever re-read from the lake, so the one flow the package
    exists for — fetch, then save what you fetched — ran out of API at the last
    step. Everything after the writer is skipped for that form; the table has
    already been rendered by whatever produced it, and rendering it twice would
    label labels.

    ``format`` is taken from the destination's suffix when it is not given.
    Defaulting it to csv meant ``export(t, "x.parquet")`` wrote a CSV into a
    file named .parquet, which every reader downstream then failed to open.
    """
    if isinstance(system, pa.Table):
        destination = path if path is not None else out if out is not None else series
        if destination is None:
            raise ValueError(
                "export(table, ...) needs somewhere to write: "
                'export(table, "births.parquet") or export(table, path=...)'
            )
        if not isinstance(destination, (str, Path)):
            raise TypeError(
                f"export(table, {destination!r}) — the second argument is the "
                "destination path when the first is a table"
            )
        target = Path(destination)
        return write_table(system, target, _format_for(target, format))

    if path is not None and out is not None and Path(path) != Path(out):
        # Two different destinations in one call is a mistake, not a preference.
        # Letting one silently win writes the file somewhere the caller did not
        # ask for and reports success.
        raise ValueError(
            f"export() got both path={path!r} and out={out!r}. `out` is the old "
            "name for `path`; give one."
        )
    path = path if path is not None else out
    # `fetch`, `load` and `scan` all take an int year; export reached list()
    # and raised. Public functions that present themselves as parallel should
    # accept the same filters.
    if isinstance(years, int):
        years = [years]
    if isinstance(uf, str):
        uf = [uf]
    fmt = _format_for(Path(path) if path is not None else None, format)

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
            cast("str | None", series),
            uf=uf,
            years=years,
            columns=columns,
            family_id=family_id,
            on_missing_column=on_missing_column,
            catalog=catalog,
            root=root,
            settings=settings,
        )
        if scan_result.warnings:
            # scan()'s warnings used to die here. A streaming export that
            # null-filled a whole generation said so to nobody.
            import warnings as _warnings

            for note in scan_result.warnings:
                _warnings.warn(note, UserWarning, stacklevel=2)
        return _write_streaming(scan_result, path, fmt)

    table = load(
        system,
        cast("str | None", series),
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
        companions=companions,
        derived=derived,
        strict_labels=strict_labels,
        historical_labels=historical_labels,
        allow_borrowed_labels=allow_borrowed_labels,
    )
    assert isinstance(table, pa.Table)
    # A file someone opens reads like the query default: meaning first, the
    # code in parentheses (ADR-0084).
    from .presentation import documented_names
    from .presentation import present as apply_presentation

    resolved = settings or load_settings(root=Path(root) if root else None)
    store_for_names = Catalog(settings=resolved) if catalog is None else catalog
    try:
        names = documented_names(store_for_names.store, system)
    finally:
        if catalog is None:
            store_for_names.close()
    table = apply_presentation(table, present if present is not None else resolved.presentation, names=names)  # type: ignore[arg-type]
    return write_table(table, path, fmt)


def _unified_schema(schemas: Sequence[pa.Schema]) -> pa.Schema:
    """One schema covering every generation, or a refusal naming the conflict.

    A file has one header. Generations do not share a schema — that is why
    `scan()` keeps them apart — so writing them into one file means deciding up
    front what its columns are, in first-seen order, with each generation
    null-filled for the columns it does not have. That is exactly what
    `promote_options="permissive"` does for the eager path.

    A column two generations declare with DIFFERENT TYPES is a genuine conflict
    and is refused rather than coerced: silently widening an int32 to a string
    because one vintage stored it differently is the kind of quiet change this
    package exists not to make.
    """
    fields: dict[str, pa.Field] = {}
    for schema in schemas:
        for field_ in schema:
            existing = fields.get(field_.name)
            if existing is None:
                fields[field_.name] = field_
            elif existing.type != field_.type:
                raise ValueError(
                    f"cannot stream {field_.name!r} into one file: generations "
                    f"declare it as {existing.type} and {field_.type}. Export "
                    "each generation separately (family_id=), or use the eager "
                    "path, which reports the promotion."
                )
    return pa.schema(list(fields.values()))


def _conform(table: pa.Table, schema: pa.Schema) -> pa.Table:
    """Give `table` exactly `schema`'s columns, null-filling what it lacks."""
    if table.schema.names == schema.names:
        return table
    arrays = []
    for field_ in schema:
        if field_.name in table.schema.names:
            arrays.append(table.column(field_.name))
        else:
            # STRUCTURAL absence: this generation has no such field. The eager
            # path null-fills it the same way and says so in the report.
            arrays.append(pa.nulls(table.num_rows, type=field_.type))
    return pa.Table.from_arrays(arrays, schema=schema)


def _conform_batch(batch: pa.RecordBatch, schema: pa.Schema) -> pa.RecordBatch:
    """Give one lazy batch exactly ``schema``, including structural nulls."""
    if batch.schema == schema:
        return batch
    arrays = []
    available = set(batch.schema.names)
    for field_ in schema:
        if field_.name in available:
            arrays.append(batch.column(field_.name))
        else:
            arrays.append(pa.nulls(batch.num_rows, type=field_.type))
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


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
    # Decided BEFORE the first batch: a file has one header, and the writer
    # cannot be created from whichever generation happened to come first.
    # _flatten_lists can change a column's type (a list becomes a joined
    # string), so the schema is taken from a flattened sample of each
    # generation rather than from the raw scan schema.
    schema = _unified_schema(
        [
            _flatten_lists(pa.Table.from_batches([], schema=s)).schema
            for s in scan_result.schemas.values()
        ]
    )

    writer = None
    # The same unique, target-directory staging primitive as eager exports and
    # lake parts.  `<target>.part` let simultaneous exports overwrite one
    # another's work and made the first finisher publish the second's bytes.
    with staged_file(target, require_nonempty=False) as staged:
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
                flat = _conform(
                    _flatten_lists(pa.Table.from_batches([batch])), schema
                )
                if writer is None:
                    writer = (
                        pq.ParquetWriter(sink, schema, compression="zstd")
                        if fmt == "parquet"
                        else pacsv.CSVWriter(sink, schema)
                    )
                writer.write_table(flat)
            if writer is not None:
                writer.close()
        if writer is None:
            # No rows at all. Write an empty but readable artifact at the
            # staged path; the context publishes it atomically on exit.
            if fmt == "parquet":
                pq.write_table(pa.Table.from_batches([], schema=schema), staged)
            else:
                pacsv.write_csv(pa.Table.from_batches([], schema=schema), staged)
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

    # STAGED, like every other artifact this package writes. An interrupted
    # export used to leave a truncated file under the final name, and a short
    # CSV is indistinguishable from a small answer — the exact rule the streaming
    # writer already followed and this one did not.
    with staged_file(target, require_nonempty=False) as staged:
        if fmt == "parquet":
            import pyarrow.parquet as pq

            pq.write_table(table, staged, compression="zstd")
        elif fmt == "csv":
            import pyarrow.csv as pacsv

            # A list column (a multi-valued field's *_codes companion) has no
            # CSV representation, so it is joined rather than silently
            # stringified as a Python repr.
            pacsv.write_csv(_flatten_lists(table), staged)
        else:
            _write_xlsx(table, staged)
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
