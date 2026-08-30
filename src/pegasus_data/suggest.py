"""Suggest an aggregate recipe from what the data and the curation already know.

The recipes were being written by hand, naming three or four fields of files
that carry over a hundred — and every hand-written dimension list quietly
duplicates knowledge the catalog already holds: which fields are coded, what
they mean, how many levels they actually take. This module closes that gap:

* **cardinality is measured**, on one real state-year from the lake, because
  documented code lists routinely disagree with what the files contain (the
  SIH SEXO table documents codes the data does not use);
* **meaning comes from curation** (`variable_docs`: code system, translated
  name, description), which is the project's single source for what a column
  IS;
* **cost is projected**, by counting distinct key combinations as candidate
  dimensions are added greedily, so the analyst declaring a spec sees what
  each dimension spends before any national build pays it.

The output is a REPORT for the analyst, not an auto-written spec. A dimension
is an analytical claim; this module puts the evidence on one screen so the
claim takes a minute instead of an afternoon, and stops at exactly the line
where judgement starts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Fields that are never dimensions: identifiers, geography and time belong to
#: other axes, and free-text or continuous fields band rather than enumerate.
_STRUCTURAL_HINTS = (
    "MUNIC", "CODMUN", "_source", "_blob", "ANO", "MES", "DT", "DATA",
    "CEP", "CNES", "CNPJ", "CPF", "NUM", "N_AIH", "SEQ",
)


@dataclass(slots=True)
class Candidate:
    field_name: str
    distinct: int
    null_share: float
    code_system: str
    translated_name: str
    description: str
    sample: tuple[str, ...]
    #: Distinct key combinations if this and every candidate above it joined
    #: municipality x month as dimensions. The analyst's cost column.
    cumulative_cells: int = 0


@dataclass(slots=True)
class Suggestion:
    dataset: str
    rows: int
    base_cells: int
    candidates: list[Candidate] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def suggest(
    dataset: str,
    *,
    uf: str | None = "PE",
    years: int = 2022,
    max_levels: int = 40,
    settings: Any = None,
) -> Suggestion:
    """Measure one state-year and rank the fields that could be dimensions.

    ``uf=None`` measures a whole national year — for datasets published one
    file a year (SINAN) where no per-state slice exists.
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    from .catalog.store import Catalog
    from .config import load_settings
    from .retrieve import fetch
    from .semantics.curation import semantics_for

    resolved = settings or load_settings()
    table, _report = fetch(
        dataset, uf=uf, years=years, settings=resolved,
        report=True, labels=False, provenance=True,
    )
    rows = table.num_rows

    semantics = semantics_for(dataset)
    geo_fields = {
        str(f)
        for body in (semantics.geography_bindings() or {}).values()
        for f in (body.get("fields") or ())
    }
    time_fields = {
        str(f)
        for body in (semantics.time_bindings() or {}).values()
        for f in (body.get("fields") or ())
    }
    # The DEFAULT bindings, not an alphabetical accident: the cost curve must
    # be priced against the same key the artifact will actually use.
    geography = semantics.geography_bindings() or {}
    times = semantics.time_bindings() or {}
    default_geo = str(getattr(semantics, "default_geography", "") or "")
    default_time = str(getattr(semantics, "default_time", "") or "")
    geo_body = geography.get(default_geo) or next(iter(geography.values()), {})
    time_body = times.get(default_time) or next(iter(times.values()), {})
    geo = str((geo_body.get("fields") or [None])[0] or "") or None
    time_parts = [str(f) for f in (time_body.get("fields") or ())]

    docs: dict[str, dict[str, str]] = {}
    catalog = Catalog(resolved.catalog_path)
    try:
        system = str(getattr(semantics, "system", "") or "").upper()
        for row in catalog.query(
            "SELECT field_name, code_system, translated_name, description "
            "FROM variable_docs WHERE system=?",
            (system,),
        ):
            docs[str(row["field_name"]).upper()] = {
                "code_system": str(row["code_system"] or ""),
                "translated_name": str(row["translated_name"] or ""),
                "description": str(row["description"] or "").split("\n")[0][:110],
            }
    finally:
        catalog.close()

    out = Suggestion(dataset=dataset, rows=rows, base_cells=0)
    columns: dict[str, Any] = {}
    for name in table.schema.names:
        upper = name.upper()
        if any(hint in upper for hint in _STRUCTURAL_HINTS):
            out.skipped.append((name, "structural (identity, geography or time)"))
            continue
        if upper in geo_fields or upper in time_fields:
            out.skipped.append((name, "an axis, not a dimension"))
            continue
        text = pc.utf8_trim_whitespace(pc.cast(table.column(name), pa.string()))
        distinct = pc.unique(pc.drop_null(text))
        levels = len(distinct)
        if levels < 2:
            out.skipped.append((name, "constant"))
            continue
        if levels > max_levels:
            out.skipped.append((name, f"{levels} levels; band it or leave it"))
            continue
        doc = docs.get(upper, {})
        nulls = rows - pc.sum(pc.cast(pc.is_valid(text), pa.int64())).as_py()
        columns[name] = text
        out.candidates.append(Candidate(
            field_name=name,
            distinct=levels,
            null_share=(nulls / rows) if rows else 0.0,
            code_system=doc.get("code_system", ""),
            translated_name=doc.get("translated_name", ""),
            description=doc.get("description", ""),
            sample=tuple(sorted(str(v) for v in distinct.to_pylist())[:8]),
        ))

    # Coded-and-documented first, then by how little each costs.
    out.candidates.sort(
        key=lambda c: (
            0 if c.code_system in ("internal", "external") else 1,
            c.distinct,
        )
    )

    # The greedy cost curve: municipality x month, then each candidate in the
    # order above. Counting combinations IS the cost of a dimension set --
    # everything else about a dimension is free.
    key_columns: dict[str, Any] = {}
    if geo and geo in table.schema.names:
        key_columns["_geo"] = pc.cast(table.column(geo), pa.string())
    present = [f for f in time_parts if f in table.schema.names]
    if len(present) >= 2:
        # A two-field competence (ANO_CMPT + MES_CMPT) keys as their join;
        # taking only the year priced every month as one cell and understated
        # the whole curve five-fold.
        key_columns["_time"] = pc.binary_join_element_wise(
            pc.cast(table.column(present[0]), pa.string()),
            pc.cast(table.column(present[1]), pa.string()),
            "-",
        )
    elif len(present) == 1:
        key_columns["_time"] = pc.utf8_slice_codeunits(
            pc.cast(table.column(present[0]), pa.string()), 0, 6)
    if key_columns:
        out.base_cells = (
            pa.table(key_columns).group_by(list(key_columns)).aggregate([]).num_rows
        )
        running = dict(key_columns)
        for candidate in out.candidates:
            running[candidate.field_name] = columns[candidate.field_name]
            candidate.cumulative_cells = (
                pa.table(running).group_by(list(running)).aggregate([]).num_rows
            )
    return out
