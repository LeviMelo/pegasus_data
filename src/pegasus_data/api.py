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
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa

from .catalog.store import Catalog as _Store
from .config import Settings, load_settings
from .normalize.engine import MissingColumnError
from .persist.duck import DuckLake
from .persist.lake import Lake
from .profile.drift import field_availability
from .semantics.dictionary import (
    codelists_for,
    lookup,
    observed_values,
    rollups_for,
)
from .sources.ibge import KNOWN_SERIES, UnsupportedStratification, series_catalogue

__all__ = [
    "Catalog",
    "describe",
    "load",
    "load_population",
    "open_lake",
    "FieldDescription",
    "MissingColumnError",
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
            "provenance": self.provenance,
            "open_questions": self.open_questions,
            "generations": self.generations,
        }

    def __repr__(self) -> str:
        head = f"{self.system}.{self.series or ''}.{self.field_name}"
        name = f" — {self.official_name}" if self.official_name else ""
        return (
            f"<{head}{name} | {self.semantic_type} "
            f"({self.semantic_confidence:.2f}) | coverage {self.dictionary_coverage:.1%} "
            f"| {self.aggregation}>"
        )


class Catalog:
    """Read access to the shipped catalog, lake and dictionary."""

    def __init__(self, root: str | Path | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings(root=Path(root) if root else None)
        self.store = _Store(self.settings.catalog_path, read_only=self.settings.catalog_path.exists())
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


def _resolve_family(store: _Store, system: str, series: str | None, field_name: str | None) -> list[dict[str, Any]]:
    clauses = ["system = ?"]
    params: list[object] = [system]
    if series:
        clauses.append("series = ?")
        params.append(series)
    rows = store.query(
        f"SELECT family_id, system, series, schema_signature, field_count, time_min, time_max "
        f"FROM families WHERE {' AND '.join(clauses)} ORDER BY COALESCE(time_max, 0) DESC",
        params,
    )
    families = [dict(r) for r in rows]
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
) -> FieldDescription:
    """Ledger entry + dictionary coverage + top values **with labels** + provenance.

    When a field exists in some schema generations and not others, that is stated
    rather than hidden: ``generations`` lists every generation and whether it
    carries the column, which is the information that stops a query for
    ``DIAG_SECUN`` against a 2020 file from quietly returning nothing useful.
    """
    own = catalog is None
    cat = catalog or Catalog()
    try:
        store = cat.store
        candidates = _resolve_family(store, system, series, field)
        if not candidates:
            raise KeyError(f"no family found for system={system!r} series={series!r}")
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
            codelists=codelists_for(store, system=system, field_name=field),
            rollups=rollups_for(store, system=system, field_name=field, observed=observed),
            provenance=json.loads(led.get("provenance") or "[]"),
            open_questions=open_questions,
            generations=generations,
        )
    finally:
        if own:
            cat.close()


def load(
    system: str,
    series: str | None = None,
    *,
    uf: str | Sequence[str] | None = None,
    years: Sequence[int] | range | None = None,
    columns: Sequence[str] | None = None,
    labels: bool = False,
    family_id: str | None = None,
    catalog: Catalog | None = None,
) -> pa.Table:
    """Read a family out of the lake.

    ``labels=True`` adds the decoded ``*_label`` companion columns that
    normalisation wrote; the raw columns are always present alongside them.

    A requested column that does not exist in the target generation **raises**
    (:class:`MissingColumnError`) rather than returning empty — an empty result
    looks legitimate and is the easiest way to publish a wrong number (§13).
    """
    own = catalog is None
    cat = catalog or Catalog()
    try:
        store = cat.store
        families = _resolve_family(store, system, series, None)
        if family_id:
            families = [f for f in families if f["family_id"] == family_id]
        if not families:
            raise KeyError(f"no family found for system={system!r} series={series!r}")

        wanted: list[str] | None = list(columns) if columns else None
        tables: list[pa.Table] = []
        errors: list[MissingColumnError] = []
        for family in families:
            projection = None
            if wanted:
                present = {
                    r["field_name"]
                    for r in store.query(
                        "SELECT field_name FROM schema_presence WHERE schema_signature = ?",
                        (family["schema_signature"],),
                    )
                }
                missing = [c for c in wanted if c not in present]
                if missing:
                    elsewhere = [
                        f["family_id"]
                        for f in families
                        if all(
                            store.count(
                                "schema_presence", "schema_signature = ? AND field_name = ?",
                                (f["schema_signature"], c),
                            )
                            for c in missing
                        )
                    ]
                    errors.append(MissingColumnError(missing[0], family["family_id"], elsewhere))
                    continue
                projection = list(wanted)
            optional = [f"{c}_label" for c in (wanted or [])] if labels else None
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
                tables.append(table)
        if not tables:
            if errors:
                raise errors[0]
            raise FileNotFoundError(
                f"no lake data for system={system!r} series={series!r}; run `pegasus-data build` first"
            )
        if len(tables) == 1:
            return tables[0]
        return pa.concat_tables(tables, promote_options="permissive")
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
) -> pa.Table:
    """Load a denominator series, refusing a stratification it cannot support.

    ``POPTCU`` carries no age and no sex, so asking it for an age breakdown
    raises rather than silently returning a coarser table that would then be
    labelled age-standardised.
    """
    own = catalog is None
    cat = catalog or Catalog()
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


def open_lake(root: str | Path | None = None) -> DuckLake:
    """A DuckDB connection with every family registered as a view."""
    cat = Catalog(root)
    duck = DuckLake(cat.settings.lake_dir, cat.store)
    duck.register_all()
    return duck
