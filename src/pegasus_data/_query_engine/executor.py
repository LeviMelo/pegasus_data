"""Execute lake/fetch/hybrid plans and assemble the query report."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa

from ..conditions import CONDITION
from ..config import Settings, load_settings
from ..crosswalk import (
    EnrichmentRequest,
    enrich_cnes,
    enrich_cnpj,
    enrichment_route,
    record_column,
    source_field,
)
from ..semantics.through import attach as attach_through
from ..semantics.through import describe as describe_through
from ..semantics.through import split as split_through
from .coverage import shared_catalog
from .filters import _filter_source_period, _with_competence, _with_source_resolution
from .model import (
    CrosswalkAmbiguityWarning,
    PartialSourceWarning,
    QueryReport,
    QuerySpec,
    StructuralSchemaWarning,
    ThroughKeyWarning,
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


def _final_projection(table: pa.Table, spec: QuerySpec, *, keep_condition: bool = False) -> pa.Table:
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
        # a column the caller named is kept (the intake's `_MUNICIPALITY` and `year`: the place and period it landed a
        # record by, `semantics.curation._landed_axes`); other internal columns are not part of a record's answer
        named = {str(item).upper() for item in spec.select} if spec.select is not None else set()
        keep = [name for name in keep if name.upper() in named or (not name.startswith("_") and name != "year")]
    if keep_condition and CONDITION in table.column_names:
        keep.append(CONDITION)         # the engine's: the record's answer to a condition, for the caller to count by group
    return table.select(keep)


#: The crosswalk routes an enrichment declaration may name, by the direction they resolve.
_CROSSWALKS = {"cnes_to_cnpj": enrich_cnpj, "cnpj_to_cnes": enrich_cnes}


def _shared_request(
    query_plan: Any, resolved: Settings, *, labels: bool, rows: Mapping[str, Sequence[str]] | None,
    condition: object, render: Mapping[str, Any] | None,
) -> tuple[Any, list[str] | None]:
    """The ONE request for both sources, built (and so checked) before any file moves, and the columns it names."""
    from .request import ReadRequest

    retrieval = query_plan.retrieval
    # `_competencia`, `year` and `_source_resolution` are DERIVED downstream by `_with_competence` out of
    # `_source_path` and the source report. They are columns of no DATASUS family, so they are never asked of a
    # source. `_source_path` stays in the projection: it IS a real column of both sources.
    columns = (
        set(query_plan.spec.select or ()) | set(retrieval.hidden_dependencies)
    ) - SYNTHESISED_COLUMNS
    requested_columns = sorted(columns) if query_plan.spec.select is not None else None
    # ONE request for both sources (the lake's years and the fetched ones), checked before any file moves: an empty
    # row filter, a role the dataset does not declare, a number compared with a code, an ambiguous column. Derived
    # columns travel with labels; under the codes presentation only the ones the caller selected are built, as codes.
    with shared_catalog(resolved) as known_store:
        request = ReadRequest.build(
            known_store, retrieval.system, retrieval.series, columns=requested_columns, rows=rows,
            condition=condition,
            years=[*retrieval.lake_years, *retrieval.fetch_years, *(retrieval.years or ())],
            profile="audit" if labels else "codes", render=render, companions=False,
            derived=labels or list(query_plan.spec.select or []), on_missing_column="null_fill",
        )
    return request, requested_columns


def _refuse_before_reading(query_plan: Any, *, as_of: object, max_download: int | None) -> None:
    """The refusals that need no file: no period, the download budget, max_download=0, a missing local resource."""
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


def _crosswalk_path(query_plan: Any, resolved: Settings) -> str | None:
    """The CNES-CNPJ crosswalk resource's path when the plan needs it."""
    if "cnes_cnpj" in query_plan.semantics.required_resources:
        from .._resources import ResourceManager

        return ResourceManager(resolved).ensure("cnes_cnpj").path
    return None


def _new_report(query_plan: Any) -> QueryReport:
    """The report, opened with the plan's period, strategy and adaptations."""
    retrieval = query_plan.retrieval
    return QueryReport(
        requested_period=str(query_plan.spec.period) if query_plan.spec.period else None,
        effective_period=next(
            (item.effective for item in reversed(retrieval.adaptations) if item.kind == "time_resolution"),
            str(query_plan.spec.period) if query_plan.spec.period else None,
        ),
        source_strategy=retrieval.source_strategy,
        publication_resolution=retrieval.publication_resolution,
        adaptations=[asdict(item) for item in retrieval.adaptations],
    )


def _require_known_columns(
    query_plan: Any, request: Any, requested_columns: list[str] | None, resolved: Settings,
) -> None:
    """Refuse a column no generation of the dataset carries, before any file is read."""
    from .readplan import resolve_family

    retrieval = query_plan.retrieval
    if requested_columns or request.filters:
        # a column NO generation of the dataset carries is a typo or a renamed field: refused here, for the lake and
        # the fetch path alike, instead of coming back as an all-null column with a warning
        with shared_catalog(resolved) as known_store:
            request.require_known(known_store, resolve_family(known_store, retrieval.system, retrieval.series, None))


def _read_lake(
    tables: list[pa.Table], source_reports: list[Any], query_plan: Any, request: Any,
    requested_columns: list[str] | None, resolved: Settings,
) -> None:
    """Read the lake's years in one scan; the table and its report are appended to the two lists."""
    from ..api import Catalog as PublicCatalog
    from ..api import read_lake
    from ..normalize.engine import PROVENANCE_COLUMNS

    retrieval = query_plan.retrieval
    cat = PublicCatalog(settings=resolved)
    # Provenance is a promise about every row on both paths: the published files' read keeps it; the lake stores
    # it, but a projection that names only the selected fields dropped it, and a linkage over a built lake had
    # no record identity (2026-10-03).
    lake_request = request
    if requested_columns is not None and query_plan.spec.provenance == "all":
        lake_request = replace(request, columns=tuple(sorted(set(requested_columns) | set(PROVENANCE_COLUMNS))))
    # a full-width read decodes what the answer then drops: the record key (32 hex characters a row), the blob
    # digest, the stored labels the renderer ignores
    leave_out: frozenset[str] = frozenset()
    if requested_columns is None and query_plan.spec.provenance != "all":
        leave_out = frozenset(c for c in PROVENANCE_COLUMNS if c != "_source_path")
    try:
        # the files the plan chose, read once: one reading of each year (the national file beside its state files
        # is one), whatever mix of national and state years the plan holds
        local_table, local_report = read_lake(
            cat, lake_request,
            uf=list(retrieval.physical_geography) or None,
            years=list(retrieval.lake_years) or None,
            partitions=retrieval.lake_partitions, leave_out=leave_out,
        )
        # the lake's report says where its rows came from as a fetch's does: the source files of the partitions read
        competence = dict(retrieval.lake_competence)
        if hasattr(local_report, "source_facts"):
            local_report.origin = "lake"
            for partition in retrieval.lake_partitions:
                for source in sorted(partition.sources):
                    local_report.source_facts.setdefault(
                        source, (partition.family_id, int(partition.year), competence.get(source)))
        tables.append(_with_competence(local_table, local_report, competence))
        source_reports.append(local_report)
        del local_table      # the list holds the table from here: a name left bound keeps its columns to the end
    finally:
        cat.close()


def _fetch_years_of(retrieval: Any, as_of: object) -> tuple[int, ...] | tuple[None, ...]:
    """The years to read from the published files: the plan's, every year under ``as_of``, or the one open read."""
    fetch_years: tuple[int, ...] | tuple[None, ...] = retrieval.fetch_years
    if as_of is not None:
        fetch_years = tuple(sorted({*retrieval.fetch_years, *retrieval.lake_years}))  # type: ignore[arg-type]
    if (retrieval.source_strategy == "fetch" or as_of is not None) and not retrieval.years:
        fetch_years = (None,)
    return fetch_years


def _read_fetched(
    tables: list[pa.Table], source_reports: list[Any], report: QueryReport, dataset: str, request: Any,
    query_plan: Any, fetch_years: tuple[int, ...] | tuple[None, ...], resolved: Settings, *,
    allow_partial: bool, as_of: str | date | datetime | None,
) -> None:
    """Read each fetched year from the published files; tables and reports are appended, a short year is warned."""
    from .._request import _as_years, _clean_months, _clean_ufs
    from ..retrieve import read_source

    retrieval = query_plan.retrieval
    months_by_year = dict(retrieval.year_months)
    for fetch_year in fetch_years:
        fetched_table, fetched_report = read_source(
            dataset, request,
            uf=_clean_ufs(list(retrieval.geography_for(fetch_year)) or None),
            years=_as_years([fetch_year] if fetch_year is not None else None),
            months=_clean_months(months_by_year.get(fetch_year) or None),  # type: ignore[arg-type]
            settings=resolved,
            # every provenance column rides to the end of the query; the key is hashed per row (about 9 us each)
            # and kept only for the caller who asked for provenance
            provenance=True, record_key=query_plan.spec.provenance == "all",
            # A file that would not download or open is a recorded gap (report.excluded), never a silent
            # absence; accepting a short table is the caller's explicit choice.
            allow_partial=allow_partial,
            max_bytes=None,  # the budget is max_download, checked before anything moves, on NEW bytes
            as_of=as_of,
        )
        tables.append(_with_competence(fetched_table, fetched_report))
        source_reports.append(fetched_report)
        del fetched_table
        if not fetched_report.is_complete:
            gaps = sum(len(v) for v in fetched_report.excluded.values())
            message = (
                f"{gaps} source file(s) for {fetch_year} did not contribute; the table is short "
                f"(report.source_report.excluded names them)"
            )
            report.warnings.append(message)
            warnings.warn(message, PartialSourceWarning, stacklevel=3)


def _report_absence_and_adaptations(report: QueryReport, source_reports: list[Any], query_plan: Any) -> bool:
    """Record the selected fields structurally absent from some generation and the period adaptations, each warned
    once; returns whether the period was coarsened."""
    retrieval = query_plan.retrieval
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
        warnings.warn(message, StructuralSchemaWarning, stacklevel=3)
    coarsening = any(
        item.kind == "time_resolution" for item in retrieval.adaptations
    )
    for adaptation in retrieval.adaptations:
        message = (
            f"requested {adaptation.requested}; effective period {adaptation.effective}: "
            f"{adaptation.reason}"
        )
        report.warnings.append(message)
        warnings.warn(message, TimeResolutionWarning, stacklevel=3)
    return coarsening


def _enriched(
    table: pa.Table, query_plan: Any, report: QueryReport, resolved: Settings, crosswalk_path: str | None,
) -> pa.Table:
    """The table with each declared enrichment attached by the route its target declares."""
    for request in query_plan.spec.enrichments:
        dataset = query_plan.spec.dataset
        request = replace(request, from_field=source_field(dataset, request))
        # the target's declared route (curation/joins.yml `enrichments:`) names the method; the target names nothing
        route = enrichment_route(request.target)
        method = str(route["route"])
        if method in _CROSSWALKS:
            compares = route.get("compares")
            table, enrichment_report = _CROSSWALKS[method](
                table, from_field=request.from_field,
                raw_field=record_column(dataset, str(compares)) if compares else None,
                as_field=_enrichment_output_name(request), explode=request.explode,
                resource_path=crosswalk_path, settings=resolved,
            )
        elif method == "establishment_name":
            table, enrichment_report = _enrich_cnes_name(table, request, resolved)
        elif method == "establishment_attribute":
            table, enrichment_report = _enrich_cnes_attribute(table, request, query_plan, resolved)
        else:
            raise ValueError(f"{request.target}: curation/joins.yml declares route {method!r}, which is no method")
        report.enrichments.append(enrichment_report)
        if enrichment_report.ambiguous or enrichment_report.conflicts:
            message = (
                f"{request.target} enrichment: {enrichment_report.ambiguous} ambiguous and "
                f"{enrichment_report.conflicts} conflicting rows were left unresolved"
            )
            report.warnings.append(message)
            warnings.warn(message, CrosswalkAmbiguityWarning, stacklevel=3)
    return table


def _projected(table: pa.Table, query_plan: Any, report: QueryReport, *, keep_condition: bool) -> pa.Table:
    """The final projection, with the declared union schema kept and the structural absence stamped in the metadata."""
    # A selected field known to some generation can still be absent from every
    # materialised partition that contributed rows. Preserve the declared union
    # schema rather than letting physical availability shorten the projection.
    for field_name in query_plan.spec.select or ():
        present = {name.upper() for name in table.column_names}
        if str(field_name).upper() not in present and field_name in report.structural_absence:
            table = table.append_column(field_name, pa.nulls(table.num_rows))
    table = _final_projection(table, query_plan.spec, keep_condition=keep_condition)
    metadata = dict(table.schema.metadata or {})
    metadata[b"pegasus.structural_absence"] = json.dumps(
        report.structural_absence, sort_keys=True
    ).encode()
    return table.replace_schema_metadata(metadata)


def _with_through_columns(
    table: pa.Table, report: QueryReport, dataset: str, through_roles: Any, select: Sequence[str] | None,
    read_through: Any,
) -> pa.Table:
    """The columns the dataset reads through a key, attached from the source's own read; rows with no key row are said."""
    table, report.through = attach_through(table, dataset, through_roles, select or (), read_through)
    for entry in report.through.values():
        message = describe_through(entry, dataset)
        if message:                       # rows with no row to read the column from: said, never silently null
            report.warnings.append(message)
            warnings.warn(message, ThroughKeyWarning, stacklevel=3)
    return table


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
    condition: object = None,
    _keep_unknown: bool = False,
) -> pa.Table | tuple[pa.Table, QueryReport]:
    """Run a query. ``as_of`` reads each source file as the snapshot history
    kept it on that date (``pegasus-data snapshot``, ADR-0141): the lake and the
    network are not used, and a file with no version by then is a gap.
    ``render`` sets a column's rendering (``"code"``: as filed, no codelist
    chosen), as `load` and `fetch` take it. ``rows`` (``{column: code prefixes}``) keeps only the records whose columns
    start with one of their codes: an explicit filter the caller names (period and geography never filter records),
    pushed into the lake's scan, and applied to a fetched year as it is decoded: before anything is rendered.

    ``condition`` keeps the records that satisfy a condition on ROLES (:mod:`pegasus_data.conditions`): a list of
    clauses ANDed, e.g. ``[{"role": "birth.weight", "op": "<", "value": 2500}, {"role": "birth.delivery", "in": ["2"]}]``.
    Each role is resolved to the column of the dataset and year that carries it; a number is read as the role's unit
    says and never from a declared not-recorded value or outside the role's domain, a category as filed, and an age is
    the role pegasus_data derives in years. The raw columns are tested in the lake's scan, a derived one after the read,
    both before anything is rendered. Records the condition cannot decide (a missing weight is not "under 2,500") are not in the
    result; their number is ``report.condition["unknown"]`` and the table's `conditions.condition_report`.
    ``_keep_unknown`` (the event readers') leaves them in, each record's answer in ``conditions.CONDITION``."""
    from ..presentation import resolve as resolve_presentation

    resolved = settings or load_settings(root=Path(root) if root else None)
    # How the result is shown (ADR-0084): the engine always builds the
    # canonical form (codes + labels), and the presentation is applied last.
    presentation = resolve_presentation(present, default=resolved.presentation)  # type: ignore[arg-type]
    labels = not presentation.codes_only
    # columns the dataset does not file but reads through a key (SIH-SP's sex and age, SIH-RD's: ADR-0199) are not asked of
    # its own files; they are attached to what these answer, from the source's files for the same period and geography
    own_select, through_roles = split_through(dataset, select)
    query_plan = plan(
        dataset, period=period, geography=geography, select=own_select, labels=labels,
        dimensions=dimensions, enrich=enrich, provenance=provenance,
        resource_policy=resource_policy, time_policy=time_policy,
        allow_unbounded=allow_unbounded,
        root=root, settings=settings,
    )
    retrieval = query_plan.retrieval

    # checks before any file moves, in the order their errors take precedence
    request, requested_columns = _shared_request(
        query_plan, resolved, labels=labels, rows=rows, condition=condition, render=render)
    _refuse_before_reading(query_plan, as_of=as_of, max_download=max_download)
    crosswalk_path = _crosswalk_path(query_plan, resolved)
    report = _new_report(query_plan)
    _require_known_columns(query_plan, request, requested_columns, resolved)

    # the two source reads: the lake's years once, then each fetched year
    tables: list[pa.Table] = []
    source_reports: list[Any] = []
    if as_of is None and retrieval.lake_years:
        _read_lake(tables, source_reports, query_plan, request, requested_columns, resolved)
    fetch_years = _fetch_years_of(retrieval, as_of)
    if fetch_years:
        _read_fetched(tables, source_reports, report, dataset, request, query_plan, fetch_years, resolved,
                      allow_partial=allow_partial, as_of=as_of)
    if not tables:
        raise FileNotFoundError("the retrieval plan found neither complete local coverage nor fetchable years")
    table = tables[0] if len(tables) == 1 else pa.concat_tables(tables, promote_options="default")
    # `table` is the one holder from here: the reading's own table, with every column the answer will drop (SNGPC-IND
    # 2014's `_source_path` is 5.4 of its 6 GB), was kept to the end of the query by this list
    tables.clear()
    table = _with_source_resolution(table, retrieval.year_resolutions)
    report.source_report = source_reports[0] if len(source_reports) == 1 else source_reports

    # what the sources could not carry, and how the period was adapted
    coarsening = _report_absence_and_adaptations(report, source_reports, query_plan)
    table = _filter_source_period(
        table, query_plan.spec.period, retain_annual_enclosures=coarsening
    )
    if request.condition is not None:
        # after the period: a record outside it is neither satisfied nor unknown
        from ..conditions import settle

        table, report.condition = settle(table, request.condition, keep_unknown=_keep_unknown)
    table = _apply_dimensions(table, query_plan, report, resolved)
    table = _enriched(table, query_plan, report, resolved, crosswalk_path)
    table = _projected(table, query_plan, report, keep_condition=_keep_unknown)

    if through_roles:
        def read_through(source: str, columns: list[str]) -> pa.Table:
            # the publications the request names, in the canonical form this table is in; the presentation is applied once, last
            return query(source, period=period, geography=geography, select=columns,
                         present="codes" if presentation.codes_only else "analysis", resource_policy=resource_policy,
                         time_policy=time_policy, allow_unbounded=allow_unbounded, max_download=max_download,
                         allow_partial=allow_partial, root=root, settings=settings, as_of=as_of, render=render)

        table = _with_through_columns(table, report, dataset, through_roles, select, read_through)
    state = None
    if _keep_unknown and CONDITION in table.column_names:
        state = table.column(CONDITION)             # row for row, set aside while the presentation reshapes the columns
        table = table.drop_columns([CONDITION])
    table = _presented(table, presentation, query_plan, resolved)
    if state is not None:
        table = table.append_column(CONDITION, state)
    return (table, report) if return_report else table


def _presented(table: pa.Table, presentation: Any, query_plan: Any, settings: Settings) -> pa.Table:
    """Apply the presentation with the curated names of this dataset's system."""
    from ..presentation import documented_names, present

    with shared_catalog(settings) as store:
        names = documented_names(store, query_plan.retrieval.system)
    metadata = table.schema.metadata
    shown = present(table, presentation, names=names)
    return shown.replace_schema_metadata(metadata) if metadata else shown
