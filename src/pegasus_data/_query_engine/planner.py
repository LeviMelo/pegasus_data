"""Translate analytical intent into a retrieval and semantic plan."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from ..config import Settings, load_settings
from ..crosswalk import EnrichmentRequest
from ..providers import provider
from .capabilities import _capabilities
from .model import Adaptation, QueryPlan, RetrievalPlan, SemanticPlan, _spec

CNES_ATTRIBUTE_FIELDS = {
    "CNES.NATURE": "NATUREZA",
    "CNES.LEGAL_NATURE": "NAT_JUR",
    "CNES.TYPE": "TP_UNID",
    "CNES.OWNERSHIP": "ESFERA_A",
}

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
    time_by: str | None = None,
    geography_by: str | None = None,
    unresolved_time: Literal["exclude", "retain", "error"] = "exclude",
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> QueryPlan:
    from ..retrieve import parse_dataset

    spec = _spec(
        dataset, period=period, geography=geography, select=select, labels=labels,
        dimensions=dimensions, enrich=enrich, provenance=provenance,
        resource_policy=resource_policy, time_policy=time_policy, time_by=time_by,
        geography_by=geography_by, unresolved_time=unresolved_time,
    )
    resolved = settings or load_settings(root=Path(root) if root else None)
    system, series = parse_dataset(dataset)
    capabilities = _capabilities(
        resolved, system, series, years=spec.period.years if spec.period else (),
        geography=spec.geography, time_by=spec.time_by, geography_by=spec.geography_by,
    )
    resolution = capabilities.resolution
    has_uf_axis = capabilities.physical_uf
    strategy = capabilities.source_strategy
    row_geo_field = capabilities.row_geography
    row_time_field = capabilities.row_time
    adaptations: list[Adaptation] = []
    years = spec.period.years if spec.period else ()
    months: tuple[int, ...] = ()
    if spec.period and spec.period.precision == "month":
        annual_enclosure = resolution in {"year", "mixed"} or any(
            value == "year" for _, value in capabilities.year_resolutions
        )
        if annual_enclosure:
            if row_time_field:
                adaptations.append(
                    Adaptation(
                        "publication_enclosure_exact_filter",
                        str(spec.period),
                        str(spec.period),
                        f"source publishes annual files; rows are filtered exactly by {row_time_field}",
                    )
                )
            else:
                effective = f"{years[0]}" if len(years) == 1 else f"{years[0]}..{years[-1]}"
                adaptation = Adaptation(
                    "time_resolution", str(spec.period), effective,
                    "source publishes annual data and no reliable row-month capability is declared",
                )
                if time_policy == "strict":
                    raise ValueError(
                        f"requested {spec.period}; source supports annual resolution only"
                    )
                adaptations.append(adaptation)
        else:
            months = tuple(range(1, 13)) if len(years) > 1 else tuple(
                range(spec.period.start % 100, spec.period.end % 100 + 1)
            )
    physical_uf = spec.geography.uf if spec.geography and has_uf_axis else None
    row_geo = None
    if spec.geography and spec.geography.municipality:
        row_geo = row_geo_field
        if row_geo is None:
            raise ValueError(
                "requested municipality cannot be represented by a reliable row geography field"
            )
    elif spec.geography and spec.geography.uf and not has_uf_axis:
        row_geo = row_geo_field
        if row_geo is None:
            raise ValueError(
                "requested UF cannot be represented physically and no reliable row geography field is declared"
            )
    hidden = {"_source_path", "year", "_competencia"}
    hidden.update(item.field for item in spec.dimensions)
    if row_geo:
        hidden.add(row_geo)
    if row_time_field:
        hidden.update(row_time_field.split("+"))
    for item in spec.enrichments:
        if item.target == "CNPJ":
            hidden.add((item.from_field or "CNES").upper())
            hidden.add("CNPJ")
        elif item.target == "CNES":
            hidden.add((item.from_field or "CNPJ").upper())
            hidden.add("CNES")
        elif item.target in CNES_ATTRIBUTE_FIELDS or item.target == "CNES.ESTABLISHMENT_NAME":
            hidden.add((item.from_field or "CNES").upper())
        else:
            raise KeyError(f"no declared enrichment route to {item.target}")
    required_set = {
        "cnes_cnpj" for item in spec.enrichments if item.target in {"CNPJ", "CNES"}
    }
    required_set.update(
        "cnes_registry" for item in spec.enrichments if item.target in CNES_ATTRIBUTE_FIELDS
    )
    required_set.update(
        "cnes_names"
        for item in spec.enrichments
        if item.target == "CNES.ESTABLISHMENT_NAME"
    )
    required = tuple(sorted(required_set))
    resource_period = (
        (spec.period.start, spec.period.end) if spec.period is not None else None
    )
    requirements = tuple(
        provider(name).describe(resolved, resource_period) for name in required
    )
    return QueryPlan(
        spec,
        RetrievalPlan(
            system, series, resolution, years, months, physical_uf, row_geo, row_time_field, strategy,
            tuple(sorted(hidden)), tuple(adaptations), capabilities.lake_years,
            capabilities.fetch_years, capabilities.year_resolutions,
            capabilities.time_axis, capabilities.geography_axis,
        ),
        SemanticPlan(labels, spec.dimensions, spec.enrichments, required, requirements),
    )
