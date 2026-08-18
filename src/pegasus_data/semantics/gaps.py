"""The coverage gap list: which variables still have no dictionary, ranked.

``dictionary_coverage`` turns "DATASUS has no dictionary" into a number. This
module turns the *remainder* into a work list, because a headline average hides
where the work is: a field carrying 12 million rows and no mapping matters more
than fifty rarely-populated ones, and the mean treats them alike.

Ranking is by **observed row mass**, not by field count. A gap is weighted by how
much data flows through it, so the list opens with the fields whose absence
actually costs an analysis something.

Nothing here guesses. It reports what is missing, what it looks like, and — where
a codelist name resembles the field — what the *candidates* would be if someone
verified them (§13: "obvious" is how a wrong mapping gets in without provenance).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog
from .dictionary import codelists_for, match_codelist_by_name

#: Semantic verdicts that do not want a codelist at all. A date has no code
#: table; listing it as an undecoded gap would pad the list with non-problems.
SELF_DESCRIBING = frozenset(
    {
        "date", "competencia", "money", "numeric_measure", "free_text",
        "personal_identifier_cpf", "personal_identifier_cns", "personal_identifier_cnpj",
        "uf_alpha", "uf_numeric", "datasus_age",
    }
)


@dataclass(slots=True)
class Gap:
    """One field with no usable dictionary, and everything known about it."""

    system: str
    family_id: str
    series: str | None
    field_name: str
    semantic_type: str
    observed_rows: int
    distinct_observed: int
    dictionary_coverage: float
    years: tuple[int | None, int | None]
    file_count: int
    top_values: list[str] = field(default_factory=list)
    candidate_codelists: list[str] = field(default_factory=list)
    official_name: str | None = None

    @property
    def kind(self) -> str:
        """What sort of gap this is, which determines how it gets closed."""
        if self.semantic_type == "constant_column":
            return "retired_column"
        if self.semantic_type == "categorical_undecoded":
            return "missing_codelist"
        if self.semantic_type in {"procedure_code", "cnes_establishment", "icd10"}:
            return "missing_reference_table"
        if self.semantic_type == "unknown":
            return "unclassified"
        return "missing_codelist"

    def as_dict(self) -> dict[str, object]:
        return {
            "system": self.system,
            "series": self.series,
            "family_id": self.family_id,
            "field": self.field_name,
            "kind": self.kind,
            "semantic_type": self.semantic_type,
            "observed_rows": self.observed_rows,
            "distinct_observed": self.distinct_observed,
            "dictionary_coverage": round(self.dictionary_coverage, 4),
            "years": list(self.years),
            "files": self.file_count,
            "top_values": self.top_values[:8],
            "candidate_codelists": self.candidate_codelists[:5],
            "official_name": self.official_name,
        }


def find_gaps(
    catalog: Catalog,
    *,
    systems: Sequence[str] | None = None,
    max_coverage: float = 0.5,
    include_self_describing: bool = False,
) -> list[Gap]:
    """Every profiled field whose values are not (mostly) decodable, ranked by mass."""
    clauses = ["l.dictionary_coverage <= ?"]
    params: list[object] = [max_coverage]
    if systems:
        clauses.append(f"l.system IN ({','.join('?' * len(systems))})")
        params.extend(systems)
    where = " AND ".join(clauses)

    rows = catalog.query(
        f"""
        SELECT l.system, l.family_id, l.field_name, l.semantic_type, l.dictionary_coverage,
               l.distinct_observed, l.official_name, l.schema_signature_scope,
               f.series, f.time_min, f.time_max, f.file_count
          FROM ledger l JOIN families f ON f.family_id = l.family_id
         WHERE {where}
        """,
        params,
    )

    gaps: list[Gap] = []
    for row in rows:
        semantic = str(row["semantic_type"] or "unknown")
        if not include_self_describing and semantic in SELF_DESCRIBING:
            continue
        mass = int(
            catalog.scalar(
                """
                SELECT SUM(count) FROM value_frequencies
                 WHERE family_id = ? AND field_name = ? AND schema_signature = ?
                """,
                (row["family_id"], row["field_name"], row["schema_signature_scope"]),
            )
            or 0
        )
        # A field's reach is its rows per file times the files in the family: a
        # gap in a 12,000-file series costs far more than the same gap in one.
        reach = mass * max(1, int(row["file_count"] or 1))
        top = [
            str(r["value"])
            for r in catalog.query(
                """
                SELECT value FROM value_frequencies
                 WHERE family_id = ? AND field_name = ? AND schema_signature = ?
                 ORDER BY count DESC LIMIT 8
                """,
                (row["family_id"], row["field_name"], row["schema_signature_scope"]),
            )
        ]
        bound = codelists_for(catalog, system=row["system"], field_name=row["field_name"])
        gaps.append(
            Gap(
                system=str(row["system"]),
                family_id=str(row["family_id"]),
                series=row["series"],
                field_name=str(row["field_name"]),
                semantic_type=semantic,
                observed_rows=reach,
                distinct_observed=int(row["distinct_observed"] or 0),
                dictionary_coverage=float(row["dictionary_coverage"] or 0.0),
                years=(row["time_min"], row["time_max"]),
                file_count=int(row["file_count"] or 0),
                top_values=top,
                candidate_codelists=[] if bound else match_codelist_by_name(catalog, str(row["field_name"])),
                official_name=row["official_name"],
            )
        )
    gaps.sort(key=lambda g: (-g.observed_rows, g.system, g.field_name))
    return gaps


def summarise_gaps(gaps: Sequence[Gap]) -> dict[str, object]:
    by_kind: dict[str, int] = {}
    by_system: dict[str, int] = {}
    for g in gaps:
        by_kind[g.kind] = by_kind.get(g.kind, 0) + 1
        by_system[g.system] = by_system.get(g.system, 0) + 1
    with_candidates = sum(1 for g in gaps if g.candidate_codelists)
    return {
        "gaps": len(gaps),
        "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1])),
        "by_system": dict(sorted(by_system.items(), key=lambda kv: -kv[1])),
        "with_name_matched_candidates": with_candidates,
        "note": (
            "candidates are name matches only and are never applied; verify against a "
            ".DEF, a layout document or a published table before binding one"
        ),
    }


def distinct_field_gaps(gaps: Sequence[Gap]) -> list[dict[str, object]]:
    """Collapse per-family rows to one row per ``(system, field)``.

    The same field appears once per schema generation. For deciding what to go and
    find, the question is "which *variable* is undecoded", not "in how many
    generations".
    """
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for g in gaps:
        key = (g.system, g.field_name)
        entry = merged.get(key)
        if entry is None:
            merged[key] = {
                "system": g.system,
                "field": g.field_name,
                "kind": g.kind,
                "semantic_type": g.semantic_type,
                "observed_rows": g.observed_rows,
                "generations": 1,
                "distinct_observed": g.distinct_observed,
                "years": [g.years[0], g.years[1]],
                "top_values": g.top_values[:6],
                "candidate_codelists": g.candidate_codelists[:5],
                "series": {g.series} if g.series else set(),
            }
            continue
        entry["observed_rows"] = int(entry["observed_rows"]) + g.observed_rows
        entry["generations"] = int(entry["generations"]) + 1
        entry["distinct_observed"] = max(int(entry["distinct_observed"]), g.distinct_observed)
        years = entry["years"]
        assert isinstance(years, list)
        if g.years[0] is not None:
            years[0] = min(years[0], g.years[0]) if years[0] is not None else g.years[0]
        if g.years[1] is not None:
            years[1] = max(years[1], g.years[1]) if years[1] is not None else g.years[1]
        if g.series:
            series = entry["series"]
            assert isinstance(series, set)
            series.add(g.series)
    out = []
    for entry in merged.values():
        series = entry.pop("series")
        assert isinstance(series, set)
        entry["series"] = ",".join(sorted(series))
        out.append(entry)
    out.sort(key=lambda e: -int(e["observed_rows"]))
    return out


def persist_gaps(catalog: Catalog, gaps: Sequence[Gap]) -> int:
    """Record the gap list as open questions so it survives the run."""
    for entry in distinct_field_gaps(gaps)[:200]:
        catalog.note_question(
            f"gap.undecoded_field:{entry['system']}.{entry['field']}",
            area="semantics",
            question=(
                f"{entry['system']}.{entry['field']} ({entry['semantic_type']}, "
                f"{entry['distinct_observed']} distinct values across {entry['generations']} "
                f"schema generation(s), {entry['years'][0]}–{entry['years'][1]}) has no "
                f"dictionary mapping. Sample values: {', '.join(map(str, entry['top_values'][:5]))}"
            ),
            verification_procedure=(
                "Look for a .CNV bound by a .DEF, a record-layout document under the system's "
                "Doc/Docs tree, or a published table. Candidates by name only (unverified): "
                + (", ".join(map(str, entry["candidate_codelists"])) or "none")
            ),
            blocking=f"decoding {entry['field']} in {entry['series'] or entry['system']}",
        )
    return min(len(distinct_field_gaps(gaps)), 200)


def gap_report_json(gaps: Sequence[Gap], *, limit: int = 50) -> str:
    return json.dumps(
        {
            "summary": summarise_gaps(gaps),
            "by_field": distinct_field_gaps(gaps)[:limit],
        },
        ensure_ascii=False,
        indent=1,
        default=str,
    )
