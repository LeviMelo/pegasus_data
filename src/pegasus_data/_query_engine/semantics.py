"""Identity labels, vintage dimensions and registry enrichments."""

from __future__ import annotations

import warnings
from typing import Any

import pyarrow as pa

from ..config import Settings
from ..crosswalk import EnrichmentReport, EnrichmentRequest
from .model import QueryPlan, QueryReport, SemanticFallbackWarning
from .planner import CNES_ATTRIBUTE_FIELDS


def _apply_dimensions(
    table: pa.Table, query_plan: QueryPlan, report: QueryReport, settings: Settings
) -> pa.Table:
    from ..catalog.store import Catalog
    from ..labelpack import packed_mapping_is_time_invariant, read_packed
    from ..semantics.relations import RelationType, relations_for

    output = table
    dataset_code = f"{query_plan.retrieval.system}.{query_plan.retrieval.series or '*'}"
    catalog = Catalog(settings.catalog_path, read_only=True) if settings.catalog_path.is_file() else None
    try:
        for request in query_plan.spec.dimensions:
            declared = [
                *relations_for(
                    query_plan.retrieval.system, dataset_code, request.field,
                    relation_type=RelationType.ROLLUP_TO, catalog=catalog,
                ),
                *relations_for(
                    query_plan.retrieval.system, dataset_code, request.field,
                    relation_type=RelationType.ATTRIBUTE_OF, catalog=catalog,
                ),
            ]
            declared = [item for item in declared if item.target_name == request.name]
            if not declared:
                raise KeyError(f"no declared dimension {request.field}.{request.name}")
            if request.field not in output.column_names:
                raise KeyError(f"{request.field}: required dimension source is absent")
            codes = output[request.field].to_pylist()
            competences = (
                output["_competencia"].to_pylist()
                if "_competencia" in output.column_names
                else [None] * output.num_rows
            )
            lookups: dict[tuple[str, int | None], dict[str, object]] = {}
            values: list[object] = []
            artifacts: set[str] = set()
            unresolved_relation = 0
            for code, competence in zip(codes, competences, strict=True):
                number = int(competence) if competence is not None else None
                is_month = number is not None and 1 <= number % 100 <= 12
                if number is None:
                    relations = [
                        item
                        for item in declared
                        if not item.valid_from
                        and not item.valid_to
                        and packed_mapping_is_time_invariant(
                            item.artifact, system=query_plan.retrieval.system
                        )
                    ]
                else:
                    relations = [
                        *relations_for(
                            query_plan.retrieval.system,
                            dataset_code,
                            request.field,
                            relation_type=RelationType.ROLLUP_TO,
                            catalog=catalog,
                            vintage=number,
                        ),
                        *relations_for(
                            query_plan.retrieval.system,
                            dataset_code,
                            request.field,
                            relation_type=RelationType.ATTRIBUTE_OF,
                            catalog=catalog,
                            vintage=number,
                        ),
                    ]
                    relations = [
                        item for item in relations if item.target_name == request.name
                    ]
                if len(relations) > 1:
                    raise KeyError(
                        f"multiple effective relations for {request.field}.{request.name} "
                        f"at source vintage {number}"
                    )
                if not relations:
                    values.append(None)
                    unresolved_relation += 1
                    continue
                relation = relations[0]
                artifacts.add(relation.artifact)
                key = (relation.artifact, number if is_month else -(number // 100) if number else None)
                if key not in lookups:
                    reference = read_packed(
                        relation.artifact,
                        system=query_plan.retrieval.system,
                        competencia=number if is_month else None,
                        year=number // 100 if number and not is_month else None,
                    )
                    lookups[key] = dict(
                        zip(
                            reference["code"].to_pylist(),
                            reference["label"].to_pylist(),
                            strict=True,
                        )
                    )
                values.append(
                    lookups[key].get(str(code).strip()) if code is not None else None
                )
            name = f"{request.field}_{request.name}"
            output = output.append_column(name, pa.array(values, pa.string()))
            report.dimensions.append(
                {
                    "request": f"{request.field}.{request.name}",
                    "relation": "declared temporal relation",
                    "artifacts": sorted(artifacts),
                    "vintage": "source competence",
                    "unresolved_vintage_rows": unresolved_relation,
                }
            )
            if unresolved_relation:
                message = (
                    f"{request.field}.{request.name}: {unresolved_relation} row(s) lack "
                    "an applicable semantic relation/vintage; derived values are null"
                )
                report.warnings.append(message)
                warnings.warn(message, SemanticFallbackWarning, stacklevel=3)
    finally:
        if catalog is not None:
            catalog.close()
    return output


def _enforce_identity_labels(
    table: pa.Table,
    query_plan: QueryPlan,
    source_report: Any,
    report: QueryReport,
    settings: Settings,
) -> pa.Table:
    """Keep a high-level label only when an effective ``label_of`` allows it."""
    from ..catalog.store import Catalog
    from ..semantics.relations import (
        RelationType,
        ensure_adjudication_item,
        relations_for,
    )

    source_reports = source_report if isinstance(source_report, (list, tuple)) else [source_report]
    used: dict[str, set[str]] = {}
    for item in source_reports:
        render = getattr(item, "render", None) or item
        for field_name, artifacts in (getattr(render, "codelist_used", {}) or {}).items():
            used.setdefault(str(field_name), set()).update(
                part.strip() for part in str(artifacts).split(",") if part.strip()
            )
    for column_name in table.column_names:
        if column_name.endswith("_label"):
            used.setdefault(column_name.removesuffix("_label"), set())
    dataset_code = f"{query_plan.retrieval.system}.{query_plan.retrieval.series or '*'}"
    output = table
    catalog = Catalog(settings.catalog_path) if settings.catalog_path.is_file() else None
    try:
        for field_name, chosen in used.items():
            relations = relations_for(
                query_plan.retrieval.system, dataset_code, field_name,
                relation_type=RelationType.LABEL_OF, catalog=catalog,
            )
            allowed = {item.artifact for item in relations}
            if chosen and chosen <= allowed:
                continue
            label_name = f"{field_name}_label"
            if label_name in output.column_names:
                output = output.drop_columns([label_name])
            message = (
                f"{field_name}: rendered artifact(s) {', '.join(sorted(chosen)) or 'unknown'} "
                "lack an explicit label_of relation; the raw code was preserved and the "
                "high-level label was refused"
            )
            if catalog is not None:
                ensure_adjudication_item(
                    catalog, kind="label_relation", system=query_plan.retrieval.system,
                    dataset=dataset_code, field=field_name, candidates=sorted(chosen),
                    reason="renderer selected an artifact without an effective label_of relation",
                )
            report.warnings.append(message)
            warnings.warn(message, SemanticFallbackWarning, stacklevel=3)
    finally:
        if catalog is not None:
            catalog.close()
    return output


def _enrichment_output_name(request: EnrichmentRequest) -> str:
    if request.as_field:
        return request.as_field
    namespace, _, attribute = request.target.partition(".")
    return f"{namespace}_{attribute.lower()}" if attribute else f"{namespace}_resolved"


def _append_or_replace(table: pa.Table, name: str, values: list[object]) -> pa.Table:
    array = pa.array(values)
    if name in table.column_names:
        return table.set_column(table.column_names.index(name), name, array)
    return table.append_column(name, array)


def _with_registry_competence(table: pa.Table, field: str | None) -> pa.Table:
    """Attach the CNES relation's explicit validity clock to registry rows."""
    if not field or field not in table.column_names:
        return table
    values: list[int | None] = []
    for raw in table[field].to_pylist():
        text = str(raw or "").strip()
        digits = "".join(character for character in text if character.isdigit())
        value = int(digits[:6]) if len(digits) >= 6 else 0
        values.append(value if 190001 <= value <= 219912 and value % 100 else None)
    return _append_or_replace(table, "_competencia", values)


def _enrich_cnes_name(
    table: pa.Table, request: EnrichmentRequest, settings: Settings
) -> tuple[pa.Table, EnrichmentReport]:
    import pyarrow.dataset as ds

    source_field = (request.from_field or "CNES").upper()
    if source_field not in table.column_names:
        raise KeyError(f"{source_field}: required source field for CNES registry enrichment")
    from .._resources import ResourceManager

    path = ResourceManager(settings).ensure("cnes_names").path
    source_codes = {str(value or "").strip() for value in table[source_field].to_pylist()}
    competences = (
        table["_competencia"].to_pylist()
        if "_competencia" in table.column_names
        else [None] * table.num_rows
    )
    expression = ds.field("cnes").isin(sorted(source_codes))
    known = [int(value) for value in competences if value]
    if known:
        lower, upper = str(min(known)), str(max(known))
        expression &= (
            ds.field("valid_from").is_null()
            | (ds.field("valid_from") == "")
            | (ds.field("valid_from") <= upper)
        )
        expression &= (
            ds.field("valid_to").is_null()
            | (ds.field("valid_to") == "")
            | (ds.field("valid_to") >= lower)
        )
    registry = ds.dataset(path, format="parquet").to_table(
        columns=["cnes", "establishment_name", "valid_from", "valid_to"],
        filter=expression,
    )
    lookup: dict[str, list[tuple[str, str, str]]] = {}
    for code, name, lo, hi in zip(
        registry["cnes"].to_pylist(),
        registry["establishment_name"].to_pylist(),
        registry["valid_from"].to_pylist(),
        registry["valid_to"].to_pylist(),
        strict=True,
    ):
        lookup.setdefault(str(code).strip(), []).append(
            (str(name), str(lo or ""), str(hi or ""))
        )
    values: list[str | None] = []
    statuses: list[str] = []
    report = EnrichmentReport(
        request.target,
        source_field,
        f"{source_field}→CNES registry name",
        rows_before=table.num_rows,
        rows_after=table.num_rows,
    )
    for code, competence in zip(table[source_field].to_pylist(), competences, strict=True):
        applicable = {
            name
            for name, lo, hi in lookup.get(str(code or "").strip(), ())
            if (
                (competence is None and not lo and not hi)
                or (
                    competence is not None
                    and (not lo or int(lo) <= int(competence))
                    and (not hi or int(competence) <= int(hi))
                )
            )
        }
        if len(applicable) == 1:
            values.append(next(iter(applicable)))
            statuses.append("matched")
            report.matched += 1
        elif len(applicable) > 1:
            values.append(None)
            statuses.append("ambiguous_registry")
            report.ambiguous += 1
        else:
            values.append(None)
            statuses.append("unresolved")
            report.unmatched += 1
    name = _enrichment_output_name(request)
    output = _append_or_replace(table, name, values)
    output = _append_or_replace(output, f"{name}_resolution_status", statuses)
    return output, report


def _enrich_cnes_attribute(
    table: pa.Table,
    request: EnrichmentRequest,
    query_plan: QueryPlan,
    settings: Settings,
) -> tuple[pa.Table, EnrichmentReport]:
    import pyarrow.dataset as ds

    from ..api import Catalog as PublicCatalog
    from ..api import scan
    from ..render_groups import render_groups, split_by_year_column

    source_field = (request.from_field or "CNES").upper()
    if source_field not in table.column_names:
        raise KeyError(f"{source_field}: required source field for CNES registry enrichment")
    registry_field = CNES_ATTRIBUTE_FIELDS[request.target]
    source_codes = {
        str(value or "").strip() for value in table[source_field].to_pylist()
    }
    from .._resources import ResourceManager

    ResourceManager(settings).ensure(
        "cnes_registry",
        period=(
            (query_plan.spec.period.start, query_plan.spec.period.end)
            if query_plan.spec.period
            else None
        ),
    )
    catalog = PublicCatalog(settings=settings)
    try:
        registry = scan(
            "CNES",
            "ST",
            uf=None,
            years=query_plan.retrieval.years or None,
            columns=["CNES", registry_field, "COMPETEN"],
            where=ds.field("CNES").isin(sorted(source_codes)),
            on_missing_column="null_fill",
            catalog=catalog,
        ).to_table()
        registry = _with_registry_competence(
            registry, "COMPETEN" if "COMPETEN" in registry.column_names else None
        )
        if query_plan.spec.labels:
            registry, _render_report = render_groups(
                split_by_year_column(registry, query_plan.retrieval.years),
                store=catalog.store,
                lake_root=settings.lake_dir,
                system="CNES",
                profile="audit",
                companions=False,
                derived=False,
            )
    finally:
        catalog.close()
    label_field = f"{registry_field}_label"
    lookup: dict[tuple[str, int | None], set[tuple[object, object]]] = {}
    registry_competence = (
        registry["_competencia"].to_pylist()
        if "_competencia" in registry.column_names
        else [None] * registry.num_rows
    )
    registry_labels = (
        registry[label_field].to_pylist()
        if label_field in registry.column_names
        else [None] * registry.num_rows
    )
    for code, competence, value, label in zip(
        registry["CNES"].to_pylist(),
        registry_competence,
        registry[registry_field].to_pylist(),
        registry_labels,
        strict=True,
    ):
        lookup.setdefault((str(code or "").strip(), competence), set()).add((value, label))
    competences = (
        table["_competencia"].to_pylist()
        if "_competencia" in table.column_names
        else [None] * table.num_rows
    )
    values: list[object] = []
    labels: list[object] = []
    statuses: list[str] = []
    report = EnrichmentReport(
        request.target,
        source_field,
        f"{source_field}→CNES.ST.{registry_field} as-of competence",
        rows_before=table.num_rows,
        rows_after=table.num_rows,
    )
    for code, competence in zip(table[source_field].to_pylist(), competences, strict=True):
        candidates = lookup.get((str(code or "").strip(), competence), set())
        if len(candidates) == 1:
            value, label = next(iter(candidates))
            values.append(value)
            labels.append(label)
            statuses.append("matched")
            report.matched += 1
        elif len(candidates) > 1:
            values.append(None)
            labels.append(None)
            statuses.append("ambiguous_registry")
            report.ambiguous += 1
        else:
            values.append(None)
            labels.append(None)
            statuses.append("unresolved")
            report.unmatched += 1
    name = _enrichment_output_name(request)
    output = _append_or_replace(table, name, values)
    if any(value is not None for value in labels):
        output = _append_or_replace(output, f"{name}_label", labels)
    output = _append_or_replace(output, f"{name}_resolution_status", statuses)
    return output, report
