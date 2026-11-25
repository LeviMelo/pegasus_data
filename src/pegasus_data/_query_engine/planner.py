"""Translate source-publication intent into a retrieval and semantic plan."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from ..config import Settings, load_settings
from ..crosswalk import EnrichmentRequest, enrichment_route, source_field
from ..providers import provider
from .coverage import _coverage, download_estimate, shared_catalog
from .model import Adaptation, QueryPlan, RetrievalPlan, SemanticPlan, _spec


def plan(
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
    allow_unbounded: bool = False,
    root: str | Path | None = None,
    settings: Settings | None = None,
    rows: Mapping[str, Sequence[str]] | None = None,
) -> QueryPlan:
    """The plan of a query: what is read from the lake, what from the published files, and what that downloads.
    ``rows`` (the query's row filter) lets the plan read from an extract that holds every record it can keep."""
    from ..retrieve import parse_dataset

    spec = _spec(
        dataset, period=period, geography=geography, select=select, labels=labels,
        dimensions=dimensions, enrich=enrich, provenance=provenance,
        resource_policy=resource_policy, time_policy=time_policy,
        allow_unbounded=allow_unbounded,
    )
    resolved = settings or load_settings(root=Path(root) if root else None)
    system, series = parse_dataset(dataset)
    with shared_catalog(resolved) as catalog:
        capabilities = _coverage(
            resolved, catalog, system, series, years=spec.period.years if spec.period else (),
            geography=spec.geography, period=spec.period,
        )
    resolution = capabilities.resolution
    has_uf_axis = capabilities.physical_uf
    strategy = capabilities.source_strategy
    adaptations: list[Adaptation] = []
    years = spec.period.years if spec.period else ()
    months: tuple[int, ...] = ()
    year_months: list[tuple[int, tuple[int, ...]]] = []
    if spec.period and spec.period.precision == "month":
        resolutions = dict(capabilities.year_resolutions)
        for year in years:
            pushed = spec.period.months_in(year) if resolutions.get(year) == "month" else ()
            year_months.append((year, pushed))
        months = tuple(sorted({month for _year, values in year_months for month in values}))
        annual_enclosure = resolution in {"year", "mixed"} or any(
            value == "year" for _, value in capabilities.year_resolutions
        )
        if annual_enclosure:
            effective = f"{years[0]}" if len(years) == 1 else f"{years[0]}..{years[-1]}"
            adaptation = Adaptation(
                "time_resolution", str(spec.period), effective,
                "source publishes annual data; the enclosing publication is returned "
                "without row-level date filtering",
            )
            if time_policy == "strict":
                raise ValueError(
                    f"requested {spec.period}; source supports annual resolution only"
                )
            adaptations.append(adaptation)
    for year, absent in capabilities.unpublished:
        # a month the source files nothing for: the files of the others are read, and nothing comes back for it (before
        # monthly intake units there was nothing to say, the year was read whole and the empty month hidden in it)
        adaptations.append(Adaptation(
            "publication", ", ".join(f"{year}-{month:02d}" for month in absent), "none",
            "the source files no publication for these months; the table holds nothing for them",
        ))
    physical_uf = spec.geography.ufs if spec.geography and has_uf_axis else ()
    if capabilities.national_ufs:
        physical_uf = capabilities.national_ufs
        adaptations.append(Adaptation(
            "geography", "BR", ",".join(physical_uf),
            "DATASUS publishes this dataset per state only; the nation is read as every state",
        ))
    if capabilities.year_geography:
        # one reading of each such year (coverage.national_or_states, ADR-0230): the national file, or the state files
        # where the national file cuts a column they hold whole
        by_national = [str(y) for y, ufs in capabilities.year_geography if tuple(ufs) == ("BR",)]
        by_states = [str(y) for y, ufs in capabilities.year_geography if tuple(ufs) != ("BR",)]
        read = "; ".join(part for part in (
            f"{', '.join(by_national)} from the national file" if by_national else "",
            f"{', '.join(by_states)} from the 27 state files, whose columns the national file cuts" if by_states else "",
        ) if part)
        adaptations.append(Adaptation(
            "geography", "all states", "BR" if not by_states else "one reading",
            f"DATASUS publishes {', '.join([*by_national, *by_states])} both as a national file and as one file per "
            f"state, the same records; each year is read once ({read})",
        ))
    if capabilities.missing_lake_years:
        adaptations.append(Adaptation(
            "lake_partition", f"{', '.join(map(str, capabilities.missing_lake_years))} from the lake", "the source",
            "the catalog lists lake partitions of these years that are not on disk, so they are read from the source",
        ))
    if spec.geography and spec.geography.municipality:
        raise ValueError(
            "geography selects source publications only; municipality is not a "
            "declared publication coordinate for this dataset"
        )
    elif spec.geography and spec.geography.ufs == ("BR",) and not has_uf_axis:
        # The nation of a dataset published nationally (SINAN) is its one
        # publication: nothing to select, and nothing to refuse.
        adaptations.append(Adaptation(
            "geography", "BR", "",
            "this dataset is held as one national publication; BR is the whole of it",
        ))
    elif spec.geography and spec.geography.ufs and not has_uf_axis:
        from .readplan import resolve_family

        with shared_catalog(resolved) as catalog:
            known = bool(resolve_family(catalog, system, series, None))
        if not known:   # a dataset the catalog does not hold has no partitions at all: say so, not "no UF axis"
            from .._request import DatasetUnknown

            raise DatasetUnknown(f"no dataset {dataset!r}: nothing catalogued for system={system!r} series={series!r}")
        raise ValueError(
            "requested UF is not a source/publication partition for this dataset; "
            "Pegasus will not manufacture it by filtering a record field"
        )
    hidden = {"_source_path", "year", "_competencia", "_source_resolution"}
    hidden.update(item.field for item in spec.dimensions)
    # Each target is a declared route (curation/joins.yml `enrichments:`); an undeclared one raises. Only the column the
    # route reads is required: the record's own identifier, when the layout has one, is compared if present, and
    # requiring a column named CNPJ made enrich=["CNPJ"] fail on every SIH query (ADR-0100). The resources a route
    # needs are its declared `requires` (the attributes read CNES.ST itself and need none: requiring the names resource
    # refused every attribute enrichment on an install without it, 2026-10-03).
    required_set: set[str] = set()
    for item in spec.enrichments:
        route = enrichment_route(item.target)
        hidden.add(source_field(spec.dataset, item))
        required_set.update(str(name) for name in route.get("requires") or ())
    required = tuple(sorted(required_set))
    resource_period = (
        (spec.period.start, spec.period.end) if spec.period is not None else None
    )
    requirements = tuple(
        provider(name).describe(resolved, resource_period) for name in required
    )
    held: frozenset[str] = frozenset()
    if capabilities.fetch_years:
        # what the home holds of the fetch years' files, read and never downloaded (ADR-0236): the lake's partitions,
        # whole, and the extract store's rows that cover the row filter
        from ..extract import held_files

        held = frozenset(held_files(resolved, dataset, rows))
    with shared_catalog(resolved) as catalog:
        estimate = download_estimate(
            resolved, catalog, system, series, capabilities.fetch_years, dict(year_months), physical_uf,
            dict(capabilities.year_geography), held=held,
        )
    return QueryPlan(
        spec,
        RetrievalPlan(
            system, series, resolution, years, months, physical_uf, strategy,
            tuple(sorted(hidden)), tuple(adaptations), capabilities.lake_years,
            capabilities.fetch_years, capabilities.year_resolutions,
            tuple(year_months), estimate[0], estimate[1], capabilities.year_geography, capabilities.lake_partitions,
            capabilities.lake_competence, estimate[2] or 0,
        ),
        SemanticPlan(labels, spec.dimensions, spec.enrichments, required, requirements),
    )
