"""Execute lake/fetch/hybrid plans and assemble the query report."""

from __future__ import annotations

import json
import warnings
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa

from ..config import Settings, load_settings
from ..crosswalk import EnrichmentRequest, enrich_cnes, enrich_cnpj
from .filters import (
    _filter_geography,
    _filter_period,
    _with_competence,
    _with_row_competence,
)
from .model import (
    CrosswalkAmbiguityWarning,
    QueryReport,
    QuerySpec,
    StructuralSchemaWarning,
    TimeResolutionWarning,
    UnresolvedTimeWarning,
)
from .planner import plan
from .semantics import (
    _apply_dimensions,
    _enforce_identity_labels,
    _enrich_cnes_attribute,
    _enrich_cnes_name,
    _enrichment_output_name,
)


def _final_projection(table: pa.Table, spec: QuerySpec) -> pa.Table:
    if spec.select is None:
        keep = list(table.column_names)
    else:
        wanted = set(spec.select)
        keep = [name for name in table.column_names if name in wanted]
        keep += [
            name for name in table.column_names
            if name.endswith("_label") and name.removesuffix("_label") in wanted
        ]
        keep += [name for name in table.column_names if any(name.startswith(f"{item.field}_") for item in spec.dimensions)]
        keep += [name for name in table.column_names if name.endswith(("_resolved", "_resolution_status"))]
        enrichment_names = {_enrichment_output_name(item) for item in spec.enrichments}
        keep += [
            name
            for name in table.column_names
            if name in enrichment_names
            or any(name.startswith(f"{base}_") for base in enrichment_names)
        ]
        keep = list(dict.fromkeys(keep))
    if spec.provenance != "all":
        keep = [name for name in keep if not name.startswith("_") and name != "year"]
    return table.select(keep)


def query(
    dataset: str,
    *,
    period: object = None,
    geography: object = None,
    select: Sequence[str] | None = None,
    labels: bool = True,
    dimensions: Sequence[str] | None = None,
    enrich: Sequence[str | EnrichmentRequest] | None = None,
    provenance: Literal[False, "all"] = False,
    resource_policy: Literal["local"] = "local",
    time_policy: Literal["adapt", "strict"] = "adapt",
    time_by: str | None = None,
    geography_by: str | None = None,
    unresolved_time: Literal["exclude", "retain", "error"] = "exclude",
    return_report: bool = False,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> pa.Table | tuple[pa.Table, QueryReport]:
    query_plan = plan(
        dataset, period=period, geography=geography, select=select, labels=labels,
        dimensions=dimensions, enrich=enrich, provenance=provenance,
        resource_policy=resource_policy, time_policy=time_policy, time_by=time_by,
        geography_by=geography_by, unresolved_time=unresolved_time,
        root=root, settings=settings,
    )
    resolved = settings or load_settings(root=Path(root) if root else None)
    retrieval = query_plan.retrieval
    missing_resources = [
        item for item in query_plan.semantics.resource_requirements if not item.local
    ]
    if missing_resources:
        details = "; ".join(
            f"{item.identity}"
            + (
                f" (estimated {item.estimated_bytes:,} source bytes)"
                if item.estimated_bytes is not None
                else ""
            )
            for item in missing_resources
        )
        raise FileNotFoundError(
            f"query requires missing local resource(s): {details}. "
            "Inspect the plan, then use `pegasus-data resources build ...` explicitly; "
            f"resource_policy={query_plan.spec.resource_policy!r} never hides an unbounded build"
        )
    crosswalk_path: str | None = None
    if "cnes_cnpj" in query_plan.semantics.required_resources:
        from .._resources import ResourceManager

        crosswalk_path = ResourceManager(resolved).ensure("cnes_cnpj").path
    report = QueryReport(
        requested_period=str(query_plan.spec.period) if query_plan.spec.period else None,
        effective_period=(
            retrieval.adaptations[-1].effective if retrieval.adaptations else (
                str(query_plan.spec.period) if query_plan.spec.period else None
            )
        ),
        source_strategy=retrieval.source_strategy,
        publication_resolution=retrieval.publication_resolution,
        adaptations=[asdict(item) for item in retrieval.adaptations],
    )
    columns = set(query_plan.spec.select or ()) | set(retrieval.hidden_dependencies)
    requested_columns = sorted(columns) if query_plan.spec.select is not None else None
    tables: list[pa.Table] = []
    source_reports: list[Any] = []
    if retrieval.lake_years or (retrieval.source_strategy == "lake" and not retrieval.years):
        from ..api import Catalog as PublicCatalog
        from ..api import load

        cat = PublicCatalog(settings=resolved)
        try:
            local_table, local_report = load(
                retrieval.system, retrieval.series,
                uf=[retrieval.physical_geography] if retrieval.physical_geography else None,
                years=retrieval.lake_years or None, columns=requested_columns,
                labels=labels, profile="audit" if labels else "codes",
                companions=False, derived=False, on_missing_column="null_fill",
                report=True, catalog=cat, _preserve_internal=True,
            )
            tables.append(local_table)
            source_reports.append(local_report)
        finally:
            cat.close()
    fetch_years: tuple[int, ...] | tuple[None, ...] = retrieval.fetch_years
    if retrieval.source_strategy == "fetch" and not retrieval.years:
        fetch_years = (None,)
    if fetch_years:
        from ..retrieve import fetch

        resolutions = dict(retrieval.year_resolutions)
        for fetch_year in fetch_years:
            fetch_months: tuple[int, ...] | None = None
            if (
                fetch_year is not None
                and query_plan.spec.period
                and query_plan.spec.period.precision == "month"
                and resolutions.get(fetch_year) == "month"
            ):
                lo = query_plan.spec.period.start % 100 if fetch_year == query_plan.spec.period.start // 100 else 1
                hi = query_plan.spec.period.end % 100 if fetch_year == query_plan.spec.period.end // 100 else 12
                fetch_months = tuple(range(lo, hi + 1))
            fetched_table, fetched_report = fetch(
                dataset,
                uf=retrieval.physical_geography,
                years=[fetch_year] if fetch_year is not None else None,
                months=fetch_months,
                columns=requested_columns,
                labels=labels,
                profile="audit" if labels else "codes",
                companions=False,
                derived=False,
                provenance=True,
                on_missing_column="null_fill",
                allow_partial=False,
                settings=resolved,
                report=True,
            )
            tables.append(_with_competence(fetched_table, fetched_report))
            source_reports.append(fetched_report)
    if not tables:
        raise FileNotFoundError("the retrieval plan found neither complete local coverage nor fetchable years")
    table = tables[0] if len(tables) == 1 else pa.concat_tables(tables, promote_options="default")
    source_report: Any = source_reports[0] if len(source_reports) == 1 else source_reports
    report.source_report = source_report
    raw_absence: dict[str, list[str]] = {}
    for item in source_reports:
        current = dict(
            getattr(item, "structural_absence", None)
            or getattr(item, "columns_structurally_absent", {})
            or {}
        )
        for family, fields in current.items():
            raw_absence.setdefault(str(family), []).extend(str(field) for field in fields)
    user_fields = set(query_plan.spec.select or ())
    by_field: dict[str, list[str]] = {}
    for family, absent_fields in raw_absence.items():
        for field_name in absent_fields:
            if field_name in user_fields:
                by_field.setdefault(field_name, []).append(str(family))
    report.structural_absence = {name: sorted(families) for name, families in sorted(by_field.items())}
    if report.structural_absence:
        message = "selected fields are structurally absent from some schema generations"
        report.warnings.append(message)
        warnings.warn(message, StructuralSchemaWarning, stacklevel=2)
    coarsening = next(
        (item for item in retrieval.adaptations if item.kind == "time_resolution"), None
    )
    for adaptation in retrieval.adaptations:
        message = (
            f"requested {adaptation.requested}; effective period {adaptation.effective}: "
            f"{adaptation.reason}"
        )
        report.warnings.append(message)
        warnings.warn(message, TimeResolutionWarning, stacklevel=2)
    table = _with_row_competence(table, retrieval.row_time_field)
    table = _filter_period(
        table, query_plan.spec.period, coarsening is not None,
        unresolved_time=query_plan.spec.unresolved_time, report=report,
    )
    if report.rows_time_unresolved:
        message = (
            f"{report.rows_time_unresolved} row(s) had no parseable value for declared "
            f"time axis {retrieval.time_axis!r}; policy={query_plan.spec.unresolved_time!r}"
        )
        report.warnings.append(message)
        warnings.warn(message, UnresolvedTimeWarning, stacklevel=2)
    table = _filter_geography(
        table, query_plan.spec.geography, bool(retrieval.physical_geography),
        retrieval.row_geography_field,
    )
    table = _enforce_identity_labels(table, query_plan, source_report, report, resolved)
    table = _apply_dimensions(table, query_plan, report, resolved)
    for request in query_plan.spec.enrichments:
        if request.target == "CNPJ":
            table, enrichment_report = enrich_cnpj(
                table, from_field=(request.from_field or "CNES").upper(),
                as_field=request.as_field or "CNPJ_resolved", explode=request.explode,
                resource_path=crosswalk_path,
            )
        elif request.target == "CNES":
            table, enrichment_report = enrich_cnes(
                table, from_field=(request.from_field or "CNPJ").upper(),
                as_field=request.as_field or "CNES_resolved", explode=request.explode,
                resource_path=crosswalk_path,
            )
        elif request.target == "CNES.ESTABLISHMENT_NAME":
            table, enrichment_report = _enrich_cnes_name(table, request, resolved)
        else:
            table, enrichment_report = _enrich_cnes_attribute(
                table, request, query_plan, resolved
            )
        report.enrichments.append(enrichment_report)
        if enrichment_report.ambiguous or enrichment_report.conflicts:
            message = (
                f"{request.target} enrichment: {enrichment_report.ambiguous} ambiguous and "
                f"{enrichment_report.conflicts} conflicting rows were left unresolved"
            )
            report.warnings.append(message)
            warnings.warn(message, CrosswalkAmbiguityWarning, stacklevel=2)
    # A selected field known to some generation can still be absent from every
    # materialised partition that contributed rows. Preserve the declared union
    # schema rather than letting physical availability shorten the projection.
    for field_name in query_plan.spec.select or ():
        if field_name not in table.column_names and field_name in report.structural_absence:
            table = table.append_column(field_name, pa.nulls(table.num_rows))
    table = _final_projection(table, query_plan.spec)
    metadata = dict(table.schema.metadata or {})
    metadata[b"pegasus.structural_absence"] = json.dumps(
        report.structural_absence, sort_keys=True
    ).encode()
    table = table.replace_schema_metadata(metadata)
    return (table, report) if return_report else table
