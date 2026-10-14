"""The metadata ledger (§6.1) — what each variable *is*, per family and field.

Two columns carry most of the weight:

* ``aggregation`` ∈ ``additive | mean | non_summable``. This is the rule that
  **counts may be summed across cells and rates may not** — the rate of two
  municipalities combined is not the mean of their rates, it is the summed
  numerator over the summed denominator. Downstream systems read this field to
  refuse illegal aggregations. Where TabNet's own ``.DEF`` declares a variable an
  *incremento*, that declaration is used: it is the Ministry stating which of its
  variables it sums.

* ``dictionary_coverage`` — the fraction of observed values in that field that
  have a dictionary entry. **This is the headline metric of the whole module**:
  it turns "DATASUS has no dictionary" from a complaint into a number that goes
  up as work proceeds, reportable per system and per field.

``sentinel_values`` is per field and never global. A ``9`` is missing in one
field and a valid category in another; a global rule silently corrupts data
(§13), so a sentinel is only recorded where the column's own role declaration
(``missing:`` in ``curation/roles``) names the code that means "not recorded".
It is never read from a label: "Ignorado" is a category a report can show as
undecoded, "Branco" a race, "Não se aplica" an answer to a conditional question.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..catalog.store import CatalogStore
from .dictionary import (
    DictionaryCache,
    coverage_for_field,
    observed_values,
)
from .epoch import curated

#: Semantic types that are never additive, whatever their name suggests.
NON_SUMMABLE_TYPES = {
    "icd10", "datasus_age", "municipality_code_6", "municipality_code_7",
    "uf_alpha", "uf_numeric", "date", "competencia", "procedure_code",
    "cnes_establishment", "categorical_undecoded", "free_text",
    "personal_identifier_cpf", "personal_identifier_cns", "personal_identifier_cnpj",
    "constant_column", "unknown",
}
MEAN_TYPES: set[str] = set()
ADDITIVE_TYPES = {"money", "numeric_measure"}

@dataclass(slots=True)
class LedgerEntry:
    system: str
    family_id: str
    field_name: str
    schema_signature_scope: str
    official_name: str | None = None
    semantic_type: str | None = None
    semantic_confidence: float | None = None
    semantic_evidence: str | None = None
    unit: str | None = None
    aggregation: str = "non_summable"
    sentinel_values: list[str] = field(default_factory=list)
    first_seen: int | None = None
    last_seen: int | None = None
    dictionary_coverage: float = 0.0
    distinct_observed: int = 0
    distinct_decoded: int = 0
    provenance: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


def _official_names(catalog: CatalogStore) -> dict[tuple[str | None, str], str]:
    """``(system, field) → the name a ``.DEF`` gives the field *itself*.

    Only declarations with no lookup are counted here. A declaration that names a
    codelist is naming an *aggregation level*, not the column: ``RD.DEF`` offers
    ``DIAG_PRINC`` more than two hundred times — "Diag CID10 (capit)",
    "Diag CID10 (grupo)", "Diag CID10 cap 01" … — and every one of them is a
    roll-up. None names the raw ICD code, because TabNet never offers it as an
    axis. Picking the shortest of those would label the column "CID Capítulos",
    which is the name of a 24-category grouping, not of the diagnosis field.
    Where nothing names the field directly, the answer is that there is no
    official name, and that is what gets recorded (§13).
    """
    out: dict[tuple[str | None, str], str] = {}
    for row in catalog.query(
        """
        SELECT system, field_name, display_name FROM def_variables
         WHERE lookup_ref IS NULL ORDER BY LENGTH(display_name)
        """
    ):
        out.setdefault((row["system"], row["field_name"]), str(row["display_name"]).strip())
    return out


def _layout_names(catalog: CatalogStore) -> dict[tuple[str | None, str], tuple[str, str]]:
    """``(system, field) -> (description, source_ref)`` from the record layouts.

    This is the strongest answer to "what is this column called", stronger than
    ``.DEF``: a record layout describes the column, while a ``.DEF`` enumerates
    the tabulation axes built on it. Measured, `IT_SIHSUS_1603.pdf` gives
    ``DIAG_PRINC`` as "Código do diagnóstico principal (CID10)", which no ``.DEF``
    line says anywhere.
    """
    out: dict[tuple[str | None, str], tuple[str, str]] = {}
    for row in catalog.query(
        """
        SELECT system, field_name, description, source_ref FROM field_documentation
         ORDER BY confidence DESC, LENGTH(description)
        """
    ):
        value = (str(row["description"]).strip(), str(row["source_ref"]))
        out.setdefault((row["system"], row["field_name"]), value)
    return out


def _names_by_codelist(catalog: CatalogStore) -> dict[tuple[str | None, str, str], str]:
    """``(system, field, codelist) → the display name declared for that pairing``."""
    out: dict[tuple[str | None, str, str], str] = {}
    for row in catalog.query(
        """
        SELECT system, field_name, display_name, lookup_ref FROM def_variables
         WHERE lookup_ref IS NOT NULL ORDER BY LENGTH(display_name)
        """
    ):
        codelist = PurePosixPath(str(row["lookup_ref"]).replace("\\", "/")).stem.upper()
        name = str(row["display_name"]).strip()
        out.setdefault((row["system"], row["field_name"], codelist), name)
    return out


def _declared_measures(catalog: CatalogStore) -> set[tuple[str | None, str]]:
    """Fields TabNet declares as *incrementos*, i.e. the Ministry sums them."""
    out: set[tuple[str | None, str]] = set()
    for row in catalog.query("SELECT system, field_name FROM def_variables WHERE usage = 'I'"):
        out.add((row["system"], row["field_name"]))
    return out


def _sentinels_for(system: str | None, series: str | None, field_name: str) -> list[str]:
    """The codes the column's role declaration names as "not recorded" (``missing:``), for this field only.

    Never a global list and never a label: a ``9`` labelled "Ignorado" in ``SEXO`` says nothing about ``9`` in a field
    where it means a valid category (§13), and the raw code of a category stays in the data. A column whose role names
    none (or none of whose dataset has roles) has none."""
    from .column_roles import roles

    try:
        declared = roles(f"{system}.{series}")
    except KeyError:
        return []
    return sorted({str(code) for r in declared if str(r["column"]).upper() == field_name.upper()
                   for code in r["missing"] or ()})


@curated
def _units_of(system: str | None, series: str | None) -> dict[str, str]:
    """``column (upper-cased) -> unit`` of one dataset's role declarations (``unit:``): what the layout or dictionary
    says the column is measured in (``curation/roles``), never what its values look like. A column with none, or whose
    rows disagree, is absent."""
    from .column_roles import roles

    try:
        declared = roles(f"{system}.{series}")
    except KeyError:
        return {}
    found: dict[str, set[str]] = {}
    for r in declared:
        if r["unit"]:
            found.setdefault(str(r["column"]).upper(), set()).add(r["unit"])
    return {column: next(iter(units)) for column, units in found.items() if len(units) == 1}


def build_ledger(
    catalog: CatalogStore,
    *,
    systems: Sequence[str] | None = None,
    lake_root: str | Path | None = None,
    registries: str | Path | None = None,
) -> list[LedgerEntry]:
    """Assemble the ledger from profiles, DEF declarations and the dictionary.

    A field is named after the table that labels it, and that table is the renderer's decision
    (``label_bindings.field_decision``, OQ 79). A decision made by curation or stored needs no reference table; one
    that has to be measured reads them from ``lake_root`` (and ``registries``), and finds none without."""
    from .label_bindings import field_decision

    def loader(system: str | None) -> Callable[[str], Mapping[str, str] | None]:
        from ..lookups import _single_lookup

        if lake_root is None:
            return lambda codelist: None
        return lambda codelist: _single_lookup(
            Path(lake_root), codelist, system, None, None,
            registries=None if registries is None else Path(registries),
        )

    official = _official_names(catalog)
    measures = _declared_measures(catalog)
    cache = DictionaryCache(catalog)
    names_by_codelist = _names_by_codelist(catalog)
    layout_names = _layout_names(catalog)
    sentinel_cache: dict[tuple[str | None, str | None, str], list[str]] = {}

    clause = ""
    params: list[object] = []
    if systems:
        clause = f" AND f.system IN ({','.join('?' * len(systems))})"
        params = list(systems)

    rows = catalog.query(
        f"""
        SELECT vp.family_id, vp.field_name, vp.schema_signature, vp.semantic_type,
               vp.semantic_confidence, vp.semantic_evidence, vp.physical_type,
               vp.width, vp.decimals, vp.distinct_count,
               f.system, f.series, f.time_min, f.time_max
          FROM variable_profiles vp
          JOIN families f ON f.family_id = vp.family_id
         WHERE 1=1{clause}
        """,
        params,
    )

    entries: list[LedgerEntry] = []
    for row in rows:
        system = row["system"]
        field_name = row["field_name"]
        coverage, observed, decoded, via_rule = coverage_for_field(
            catalog,
            family_id=row["family_id"],
            field_name=field_name,
            schema_signature=row["schema_signature"],
            cache=cache,
        )
        semantic = row["semantic_type"] or "unknown"
        # a field's name never decides for another system's field: an undeclared field stays non-summable and
        # unnamed until its own system's documents say otherwise
        declared_additive = (system, field_name) in measures
        if declared_additive or semantic in ADDITIVE_TYPES:
            aggregation = "additive"
        elif semantic in MEAN_TYPES:
            aggregation = "mean"
        else:
            aggregation = "non_summable"

        provenance: list[str] = [f"profile:{row['schema_signature']}"]
        # Name the field after the codelist that actually labels it, so a column
        # decoded with full ICD-10 descriptions is not called "CID Capítulos".
        decision = field_decision(
            catalog, system=system, family_id=row["family_id"], field_name=field_name,
            counts=observed_values(
                catalog,
                family_id=row["family_id"],
                field_name=field_name,
                schema_signature=row["schema_signature"],
            ),
            load=loader(system),
        )
        chosen = decision.codelists[0] if decision.labels else None
        # The record layout names the column itself and so comes first; a .DEF
        # bound to the labelling codelist comes next; a .DEF that names the field
        # with no codelist at all comes last. Only when all three miss is there
        # genuinely no official name.
        name = None
        layout = layout_names.get((system, field_name))
        if layout:
            name = layout[0]
            provenance.append("layout_doc:official_name")
        if name is None and chosen:
            name = names_by_codelist.get((system, field_name, chosen))
        if name is None:
            name = official.get((system, field_name))
        if name is not None and "layout_doc:official_name" not in provenance:
            provenance.append("def:official_name")
        if declared_additive:
            provenance.append("def:incremento")
        if coverage > 0:
            provenance.append("dictionary")
        if via_rule > 0:
            provenance.append(f"dictionary:via_rule={via_rule:.4f}")

        questions: list[str] = []
        if semantic == "categorical_undecoded" and coverage < 0.5:
            questions.append(
                "low-cardinality field with no dictionary mapping: locate its .CNV or "
                "the notification form that defines it"
            )
        if semantic == "constant_column":
            questions.append(
                "single-valued in this schema generation: confirm whether it was "
                "retired and which field superseded it"
            )
        if semantic.startswith("personal_identifier"):
            questions.append(
                "direct personal identifier present in public data: confirm handling "
                "obligations before redistribution"
            )
        if semantic == "unknown":
            questions.append("no detector matched: needs a dictionary source or a new detector")
        if name is None and chosen:
            questions.append(
                "TabNet declares this field only at roll-up levels, never at the "
                "granularity its values are stored in, so no official name applies "
                f"to the raw column; the labels come from {chosen}"
            )

        # a money-shaped column was labelled BRL by its values: SIH's US_TOT is dollars, so the unit is the role
        # declaration's (`curation/roles`, with the document it rests on), or none
        unit = _units_of(system, row["series"]).get(field_name.upper())
        if unit is not None:
            provenance.append("roles:unit")
        elif semantic == "datasus_age":
            unit = "coded_age"

        entries.append(
            LedgerEntry(
                system=system,
                family_id=row["family_id"],
                field_name=field_name,
                schema_signature_scope=row["schema_signature"],
                official_name=name,
                semantic_type=semantic,
                semantic_confidence=row["semantic_confidence"],
                semantic_evidence=row["semantic_evidence"],
                unit=unit,
                aggregation=aggregation,
                sentinel_values=sentinel_cache.setdefault(
                    (system, row["series"], field_name), _sentinels_for(system, row["series"], field_name)
                ),
                first_seen=row["time_min"],
                last_seen=row["time_max"],
                dictionary_coverage=coverage,
                # The profiler's own distinct count, not the number of rows kept
                # in value_frequencies — those are capped at the top N and would
                # understate a high-cardinality field like DIAG_PRINC.
                distinct_observed=int(row["distinct_count"] or observed),
                distinct_decoded=decoded,
                provenance=provenance,
                open_questions=questions,
            )
        )
    return entries


def persist_ledger(
    catalog: CatalogStore, entries: Sequence[LedgerEntry], *, systems: Sequence[str] | None = None
) -> int:
    """Replace the ledger for the systems in scope.

    ``build_ledger`` derives every row from the current profiles, so a field that
    is no longer profiled — dropped by a schema correction, or moved when a family
    was re-derived — must stop having a ledger row. ON CONFLICT UPDATE can only
    ever refresh a row, never retire one, which is how derived state accumulates.

    The delete is scoped to the same systems the build was scoped to. Deleting
    outside that scope would discard the ledger for systems this run never looked
    at, which is the opposite failure and just as wrong.
    """
    keep = {(e.system, e.family_id, e.field_name, e.schema_signature_scope) for e in entries}
    clause, params = "", []
    if systems:
        clause = f" WHERE system IN ({','.join('?' * len(systems))})"
        params = list(systems)
    stale = [
        (r["system"], r["family_id"], r["field_name"], r["schema_signature_scope"])
        for r in catalog.query(
            "SELECT system, family_id, field_name, schema_signature_scope FROM ledger" + clause,
            params,
        )
        if (r["system"], r["family_id"], r["field_name"], r["schema_signature_scope"]) not in keep
    ]
    if stale:
        catalog.executemany(
            "DELETE FROM ledger WHERE system=? AND family_id=? AND field_name=? "
            "AND schema_signature_scope=?",
            stale,
        )
    catalog.executemany(
        """
        INSERT INTO ledger (system, family_id, field_name, schema_signature_scope, official_name,
            semantic_type, semantic_confidence, semantic_evidence, unit, aggregation,
            sentinel_values, first_seen, last_seen, dictionary_coverage, distinct_observed,
            distinct_decoded, provenance, open_questions)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(system, family_id, field_name, schema_signature_scope) DO UPDATE SET
            official_name=excluded.official_name,
            semantic_type=excluded.semantic_type,
            semantic_confidence=excluded.semantic_confidence,
            semantic_evidence=excluded.semantic_evidence,
            unit=excluded.unit,
            aggregation=excluded.aggregation,
            sentinel_values=excluded.sentinel_values,
            first_seen=excluded.first_seen,
            last_seen=excluded.last_seen,
            dictionary_coverage=excluded.dictionary_coverage,
            distinct_observed=excluded.distinct_observed,
            distinct_decoded=excluded.distinct_decoded,
            provenance=excluded.provenance,
            open_questions=excluded.open_questions
        """,
        [
            (
                e.system, e.family_id, e.field_name, e.schema_signature_scope, e.official_name,
                e.semantic_type, e.semantic_confidence, e.semantic_evidence, e.unit,
                e.aggregation, json.dumps(e.sentinel_values), e.first_seen, e.last_seen,
                e.dictionary_coverage, e.distinct_observed, e.distinct_decoded,
                json.dumps(e.provenance), json.dumps(e.open_questions),
            )
            for e in entries
        ],
    )
    return len(entries)


def coverage_report(catalog: CatalogStore) -> list[dict[str, object]]:
    """``dictionary_coverage`` per system — the headline number (§6.2)."""
    rows = catalog.query(
        """
        SELECT system,
               COUNT(*)                                AS fields,
               ROUND(AVG(dictionary_coverage), 4)      AS mean_coverage,
               SUM(CASE WHEN dictionary_coverage >= 0.99 THEN 1 ELSE 0 END) AS fully_covered,
               SUM(CASE WHEN dictionary_coverage = 0 THEN 1 ELSE 0 END)     AS uncovered,
               SUM(CASE WHEN official_name IS NOT NULL THEN 1 ELSE 0 END)   AS named,
               SUM(CASE WHEN aggregation='additive' THEN 1 ELSE 0 END)      AS additive
          FROM ledger
         GROUP BY system
         ORDER BY fields DESC
        """
    )
    return [dict(r) for r in rows]


def field_report(catalog: CatalogStore, system: str, family_id: str | None = None) -> list[dict[str, object]]:
    clause = "system = ?"
    params: list[object] = [system]
    if family_id:
        clause += " AND family_id = ?"
        params.append(family_id)
    rows = catalog.query(
        f"""
        SELECT family_id, field_name, official_name, semantic_type, semantic_confidence,
               aggregation, dictionary_coverage, distinct_observed, distinct_decoded, open_questions
          FROM ledger
         WHERE {clause}
         ORDER BY dictionary_coverage ASC, field_name
        """,
        params,
    )
    return [dict(r) for r in rows]
