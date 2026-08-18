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
(§13), so a sentinel is only recorded where the dictionary itself labels that
code as ignored/unknown, or where a detector saw it behave like one.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog
from .dictionary import coverage_for_field
from .dictionary import lookup as dict_lookup

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

#: Labels TabNet uses for "unknown / not stated". A code carrying one of these is
#: a sentinel *for that field only*, evidenced by the dictionary entry itself.
_IGNORED_LABEL = re.compile(
    r"^(ign|ign\.|ignorado|ignorada|ignor|nao\s*informad|não\s*informad|sem\s*inform|"
    r"outras?/?ignorado|branco|em\s*branco|nao\s*se\s*aplica|não\s*se\s*aplica)",
    re.I,
)


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


def _official_names(catalog: Catalog) -> dict[tuple[str | None, str], str]:
    """``(system, field) → official display name`` from the ``.DEF`` files.

    Shortest label wins, mirroring ``DefFile.official_names``: TabNet's longer
    variants are display decorations of the same variable.
    """
    out: dict[tuple[str | None, str], str] = {}
    for row in catalog.query(
        "SELECT system, field_name, display_name FROM def_variables ORDER BY LENGTH(display_name)"
    ):
        key = (row["system"], row["field_name"])
        out.setdefault(key, str(row["display_name"]).strip())
        out.setdefault((None, row["field_name"]), str(row["display_name"]).strip())
    return out


def _declared_measures(catalog: Catalog) -> set[tuple[str | None, str]]:
    """Fields TabNet declares as *incrementos*, i.e. the Ministry sums them."""
    out: set[tuple[str | None, str]] = set()
    for row in catalog.query("SELECT system, field_name FROM def_variables WHERE usage = 'I'"):
        out.add((row["system"], row["field_name"]))
        out.add((None, row["field_name"]))
    return out


def _sentinels_for(catalog: Catalog, system: str | None, field_name: str) -> list[str]:
    """Codes the dictionary itself labels as ignored/unknown, for this field only.

    Derived from the field's own bound codelists, never from a global list: a
    ``9`` labelled "Ignorado" in ``SEXO`` says nothing about ``9`` in a field
    where it means a valid category (§13).
    """
    labels = dict_lookup(catalog, system=system, field_name=field_name)
    return sorted({code for code, label in labels.items() if _IGNORED_LABEL.match(str(label or ""))})


def build_ledger(catalog: Catalog, *, systems: Sequence[str] | None = None) -> list[LedgerEntry]:
    """Assemble the ledger from profiles, DEF declarations and the dictionary."""
    official = _official_names(catalog)
    measures = _declared_measures(catalog)

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
        coverage, observed, decoded = coverage_for_field(
            catalog,
            family_id=row["family_id"],
            field_name=field_name,
            schema_signature=row["schema_signature"],
        )
        semantic = row["semantic_type"] or "unknown"
        declared_additive = (system, field_name) in measures or (None, field_name) in measures
        if declared_additive or semantic in ADDITIVE_TYPES:
            aggregation = "additive"
        elif semantic in MEAN_TYPES:
            aggregation = "mean"
        else:
            aggregation = "non_summable"

        provenance: list[str] = [f"profile:{row['schema_signature']}"]
        name = official.get((system, field_name)) or official.get((None, field_name))
        if name:
            provenance.append("def:official_name")
        if declared_additive:
            provenance.append("def:incremento")
        if coverage > 0:
            provenance.append("dictionary")

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

        unit = None
        if semantic == "money":
            unit = "BRL"
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
                sentinel_values=_sentinels_for(catalog, system, field_name),
                first_seen=row["time_min"],
                last_seen=row["time_max"],
                dictionary_coverage=coverage,
                distinct_observed=observed,
                distinct_decoded=decoded,
                provenance=provenance,
                open_questions=questions,
            )
        )
    return entries


def persist_ledger(catalog: Catalog, entries: Sequence[LedgerEntry]) -> int:
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


def coverage_report(catalog: Catalog) -> list[dict[str, object]]:
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


def field_report(catalog: Catalog, system: str, family_id: str | None = None) -> list[dict[str, object]]:
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
