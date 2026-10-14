"""Execute lake/fetch/hybrid plans and assemble the query report."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa

from ..config import Settings, load_settings
from ..crosswalk import EnrichmentRequest, enrich_cnes, enrich_cnpj
from .coverage import shared_catalog
from .filters import _filter_source_period, _with_competence, _with_source_resolution
from .model import (
    CrosswalkAmbiguityWarning,
    PartialSourceWarning,
    QueryReport,
    QuerySpec,
    StructuralSchemaWarning,
    TimeResolutionWarning,
)
from .planner import plan
from .semantics import (
    _apply_dimensions,
    _enrich_cnes_attribute,
    _enrich_cnes_name,
    _enrichment_output_name,
)

#: Added after retrieval, never read from a source file. Keeping them out of a
#: source projection is what lets `select=` work at all.
SYNTHESISED_COLUMNS = frozenset({"_competencia", "year", "_source_resolution"})


def _final_projection(table: pa.Table, spec: QuerySpec) -> pa.Table:
    if spec.select is None:
        keep = list(table.column_names)
    else:
        # Case-insensitive: the planner upper-cases select=, and a curated
        # derived column keeps its own spelling (IDADE_anos, PROC_REA_grupo).
        wanted = {str(item).upper() for item in spec.select}
        keep = [name for name in table.column_names if name.upper() in wanted]
        keep += [
            name for name in table.column_names
            if name.endswith("_label") and name.removesuffix("_label").upper() in wanted
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
        if spec.provenance == "all":
            # Provenance is a promise about every row, not a column to select:
            # with `select=` it silently vanished (2026-09-30), and record
            # linkage needs `_blob_sha256` and `_row` on every row (ADR-0107).
            from ..normalize.engine import PROVENANCE_COLUMNS

            keep += [name for name in table.column_names if name in PROVENANCE_COLUMNS]
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
    present: str | Mapping[str, Any] | object | None = None,
    dimensions: Sequence[str] | None = None,
    enrich: Sequence[str | EnrichmentRequest] | None = None,
    provenance: Literal[False, "all"] = False,
    resource_policy: Literal["local"] = "local",
    time_policy: Literal["adapt", "strict"] = "adapt",
    allow_unbounded: bool = False,
    max_download: int | None = 1024**3,
    allow_partial: bool = False,
    return_report: bool = False,
    root: str | Path | None = None,
    settings: Settings | None = None,
    as_of: str | date | datetime | None = None,
    render: Mapping[str, Any] | None = None,
    rows: Mapping[str, Sequence[str]] | None = None,
) -> pa.Table | tuple[pa.Table, QueryReport]:
    """Run a query. ``as_of`` reads each source file as the snapshot history
    kept it on that date (``pegasus-data snapshot``, ADR-0141): the lake and the
    network are not used, and a file with no version by then is a gap.
    ``render`` sets a column's rendering (``"code"``: as filed, no codelist
    chosen), as `load` and `fetch` take it. ``rows`` (``{column: code prefixes}``) keeps only the records whose columns
    start with one of their codes: an explicit filter the caller names (period and geography never filter records),
    pushed into the lake's scan before anything is rendered, and applied to a fetched year as it arrives."""
    from ..api import _rows_filters
    from ..presentation import resolve as resolve_presentation

    rows = _rows_filters(rows) or None          # a filter that selects no record is refused, not read as "every record"
    resolved_settings = settings or load_settings(root=Path(root) if root else None)
    # How the result is shown (ADR-0084): the engine always builds the
    # canonical form (codes + labels), and the presentation is applied last.
    presentation = resolve_presentation(present, default=resolved_settings.presentation)  # type: ignore[arg-type]
    labels = not presentation.codes_only
    query_plan = plan(
        dataset, period=period, geography=geography, select=select, labels=labels,
        dimensions=dimensions, enrich=enrich, provenance=provenance,
        resource_policy=resource_policy, time_policy=time_policy,
        allow_unbounded=allow_unbounded,
        root=root, settings=settings,
    )
    resolved = resolved_settings
    retrieval = query_plan.retrieval
    # No period first: the more specific refusal, and the one that says what
    # to change (it was masked by the budget's 22 GiB message, 2026-10-04).
    if not query_plan.spec.period and (
        retrieval.fetch_years
        or (retrieval.source_strategy == "fetch" and not retrieval.years)
    ) and not query_plan.spec.allow_unbounded:
        raise ValueError(
            "this query requires source acquisition but period is unbounded; provide "
            "period=... or explicitly pass allow_unbounded=True after inspecting plan()"
        )
    # A download budget the caller sees before anything moves (ADR-0076):
    # 1 GiB of NEW compressed bytes by default; cached files cost nothing.
    if as_of is None and max_download is not None and retrieval.download_bytes is not None:
        new = retrieval.download_bytes - (retrieval.cached_bytes or 0)
        if new > max_download:
            from ..retrieve import DownloadBudgetExceeded

            raise DownloadBudgetExceeded(
                f"this query would download {new / 2**30:.2f} GiB of new files "
                f"({retrieval.download_bytes / 2**30:.2f} GiB selected), over max_download="
                f"{max_download / 2**30:.2f} GiB. Narrow period or geography, or pass a larger "
                "max_download (None for no limit) after checking plan(...).explain()"
            )
    # max_download=0 reads the lake only: no source file is fetched or decoded, whatever the cache claims. SIA-PA 2016
    # planned 6.75 GB "cached" whose blobs an extract had released, and fetched them again, 324 files, inside a study
    # that had set 0 (2026-10-12); a dataset with no lake at all plans "fetch" with no fetch_years
    fetching = bool(retrieval.fetch_years) or retrieval.source_strategy == "fetch"
    if as_of is None and max_download == 0 and fetching:
        from ..retrieve import DownloadBudgetExceeded

        raise DownloadBudgetExceeded(
            f"this query would fetch {query_plan.spec.dataset} files ({retrieval.source_strategy}, years "
            f"{list(retrieval.fetch_years or retrieval.years or ())}), and max_download=0 forbids any download")
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
        effective_period=next(
            (item.effective for item in reversed(retrieval.adaptations) if item.kind == "time_resolution"),
            str(query_plan.spec.period) if query_plan.spec.period else None,
        ),
        source_strategy=retrieval.source_strategy,
        publication_resolution=retrieval.publication_resolution,
        adaptations=[asdict(item) for item in retrieval.adaptations],
    )
    # `_competencia`, `year` and `_source_resolution` are DERIVED downstream by
    # `_with_competence` out of `_source_path` and the source report. They are
    # not columns of any DATASUS family, so asking a source for them makes the
    # read refuse:
    #
    #   query("SIH-RD", period="2022-01", geography="AC", select=[...])
    #   -> MissingColumnError: column '_competencia' is not present in family
    #      SIHSUS_RD_e2f7244ae5 (also absent: _source_resolution, year)
    #
    # It only bit when `select=` was given, because without it nothing is
    # projected and everything arrives anyway. `_source_path` stays in the
    # projection: it IS a real column, supplied by `provenance=True` on the
    # fetch path and present in the lake.
    columns = (
        set(query_plan.spec.select or ()) | set(retrieval.hidden_dependencies)
    ) - SYNTHESISED_COLUMNS
    requested_columns = sorted(columns) if query_plan.spec.select is not None else None
    if requested_columns or rows:
        # a column NO generation of the dataset carries is a typo or a renamed field: refused here, for the lake and
        # the fetch path alike, instead of coming back as an all-null column with a warning
        from ..api import _require_known_columns, _resolve_family
        from ..retrieve import _derived_inputs
        from ..semantics.curation import load_variable_docs

        with shared_catalog(resolved) as known_store:
            dataset_families = _resolve_family(known_store, retrieval.system, retrieval.series, None)
            derived_names = frozenset(_derived_inputs(load_variable_docs(known_store, retrieval.system)))
            _require_known_columns(
                known_store, retrieval.system, retrieval.series, dataset_families,
                [*(requested_columns or []), *(rows or {})], exempt=derived_names,
            )
    # Derived columns travel with labels; under the codes presentation only the
    # ones the caller selected are built, as codes (view._apply_derived).
    derived: bool | list[str] = labels or list(query_plan.spec.select or [])
    tables: list[pa.Table] = []
    source_reports: list[Any] = []
    if as_of is None and (
        retrieval.lake_years or (retrieval.source_strategy == "lake" and not retrieval.years)
    ):
        from ..api import Catalog as PublicCatalog
        from ..api import load

        cat = PublicCatalog(settings=resolved)
        # Provenance is a promise about every row on both paths: the fetch path
        # asks for it (provenance=True below); the lake stores it, but a
        # projection that names only the selected fields dropped it, and a
        # linkage over a built lake had no record identity (2026-10-03).
        lake_columns = requested_columns
        if lake_columns is not None and query_plan.spec.provenance == "all":
            from ..normalize.engine import PROVENANCE_COLUMNS

            lake_columns = sorted(set(lake_columns) | set(PROVENANCE_COLUMNS))
        # a full-width read decodes what the answer then drops: the record key (32 hex characters a row), the blob
        # digest, the stored labels the renderer ignores
        leave_out: frozenset[str] = frozenset()
        if lake_columns is None and query_plan.spec.provenance != "all":
            from ..normalize.engine import PROVENANCE_COLUMNS

            leave_out = frozenset(c for c in PROVENANCE_COLUMNS if c != "_source_path")
        # the years of one reading (a national file beside its state files is one) load together
        by_geography: dict[tuple[str, ...], list[int]] = {}
        for lake_year in retrieval.lake_years:
            by_geography.setdefault(retrieval.geography_for(lake_year), []).append(lake_year)
        if not by_geography:
            by_geography[retrieval.physical_geography] = []
        try:
            for geography_ufs, geography_years in by_geography.items():
                local_table, local_report = load(
                    retrieval.system, retrieval.series,
                    uf=list(geography_ufs) or None,
                    years=geography_years or None, columns=lake_columns,
                    labels=labels, profile="audit" if labels else "codes", render=render,
                    companions=False, derived=derived, on_missing_column="null_fill",
                    report=True, catalog=cat, _preserve_internal=True, rows=rows, _leave_out=leave_out,
                )
                tables.append(_with_competence(local_table, local_report))
                source_reports.append(local_report)
        finally:
            cat.close()
    fetch_years: tuple[int, ...] | tuple[None, ...] = retrieval.fetch_years
    if as_of is not None:
        fetch_years = tuple(sorted({*retrieval.fetch_years, *retrieval.lake_years}))  # type: ignore[arg-type]
    if (retrieval.source_strategy == "fetch" or as_of is not None) and not retrieval.years:
        fetch_years = (None,)
    if fetch_years:
        from ..retrieve import fetch

        months_by_year = dict(retrieval.year_months)
        for fetch_year in fetch_years:
            fetch_months = months_by_year.get(fetch_year) or None  # type: ignore[arg-type]
            fetched_table, fetched_report = fetch(
                dataset,
                uf=list(retrieval.geography_for(fetch_year)) or None,
                years=[fetch_year] if fetch_year is not None else None,
                months=fetch_months,
                # the filter's columns are read too: it runs on the decoded year, and `select=` drops them after
                columns=sorted({*requested_columns, *(rows or {})}) if requested_columns is not None else None,
                labels=labels,
                profile="audit" if labels else "codes",
                render=render,
                companions=False,
                # Curated derivations (IDADE_anos) are declarations like labels
                # are, so they travel with them.
                derived=derived,
                provenance=True,
                # the key is hashed per row (about 9 us each) and kept only for the caller who asked for provenance
                _record_key=query_plan.spec.provenance == "all",
                on_missing_column="null_fill",
                # A file that would not download or open is a recorded gap
                # (report.excluded), never a silent absence; accepting a short
                # table is the caller's explicit choice.
                allow_partial=allow_partial,
                max_bytes=None,  # the budget is max_download, checked above on NEW bytes
                as_of=as_of,
                settings=resolved,
                report=True,
            )
            if rows:
                from ..api import _rows_expression

                fetched_table = fetched_table.filter(_rows_expression(rows))
            tables.append(_with_competence(fetched_table, fetched_report))
            source_reports.append(fetched_report)
            if not fetched_report.is_complete:
                gaps = sum(len(v) for v in fetched_report.excluded.values())
                message = (
                    f"{gaps} source file(s) for {fetch_year} did not contribute; the table is short "
                    f"(report.source_report.excluded names them)"
                )
                report.warnings.append(message)
                warnings.warn(message, PartialSourceWarning, stacklevel=2)
    if not tables:
        raise FileNotFoundError("the retrieval plan found neither complete local coverage nor fetchable years")
    table = tables[0] if len(tables) == 1 else pa.concat_tables(tables, promote_options="default")
    table = _with_source_resolution(table, retrieval.year_resolutions)
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
    coarsening = any(
        item.kind == "time_resolution" for item in retrieval.adaptations
    )
    for adaptation in retrieval.adaptations:
        message = (
            f"requested {adaptation.requested}; effective period {adaptation.effective}: "
            f"{adaptation.reason}"
        )
        report.warnings.append(message)
        warnings.warn(message, TimeResolutionWarning, stacklevel=2)
    table = _filter_source_period(
        table, query_plan.spec.period, retain_annual_enclosures=coarsening
    )
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
        present = {name.upper() for name in table.column_names}
        if str(field_name).upper() not in present and field_name in report.structural_absence:
            table = table.append_column(field_name, pa.nulls(table.num_rows))
    table = _final_projection(table, query_plan.spec)
    metadata = dict(table.schema.metadata or {})
    metadata[b"pegasus.structural_absence"] = json.dumps(
        report.structural_absence, sort_keys=True
    ).encode()
    table = table.replace_schema_metadata(metadata)
    table = _presented(table, presentation, query_plan, resolved)
    return (table, report) if return_report else table


def _presented(table: pa.Table, presentation: Any, query_plan: Any, settings: Settings) -> pa.Table:
    """Apply the presentation with the curated names of this dataset's system."""
    from ..presentation import documented_names, present

    with shared_catalog(settings) as store:
        names = documented_names(store, query_plan.retrieval.system)
    metadata = table.schema.metadata
    shown = present(table, presentation, names=names)
    return shown.replace_schema_metadata(metadata) if metadata else shown
