"""Translate source-publication intent into a retrieval and semantic plan."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from ..config import Settings, load_settings
from ..crosswalk import EnrichmentRequest
from ..providers import provider
from .coverage import _coverage, download_estimate, shared_catalog
from .model import Adaptation, QueryPlan, RetrievalPlan, SemanticPlan, _spec

#: What an establishment WAS at a record's competence, read from CNES.ST for
#: that month (joins.yml warns that today's registry answers the wrong
#: question for a 2015 admission). Every column is published in CNES.ST 2022;
#: one a given year leaves empty resolves as ``not_recorded``, never as a value.
CNES_ATTRIBUTE_FIELDS = {
    "CNES.NATURE": "NATUREZA",
    "CNES.LEGAL_NATURE": "NAT_JUR",
    "CNES.TYPE": "TP_UNID",
    "CNES.OWNERSHIP": "ESFERA_A",
    "CNES.MANAGEMENT": "TPGESTAO",
    "CNES.SUS_LINK": "VINC_SUS",
    "CNES.PROVIDER_TYPE": "TP_PREST",
    "CNES.CARE_LEVEL": "NIV_HIER",
    "CNES.CLIENTELE": "CLIENTEL",
    "CNES.HAS_HOSPITAL_BEDS": "LEITHOSP",
    "CNES.SURGICAL_BEDS": "QTLEITP1",
    "CNES.CLINICAL_BEDS": "QTLEITP2",
    "CNES.COMPLEMENTARY_BEDS": "QTLEITP3",
    "CNES.HAS_EMERGENCY": "URGEMERG",
    "CNES.HAS_OBSTETRIC_CENTRE": "CENTROBS",
    "CNES.HAS_NEONATAL_UNIT": "CENTRNEO",
    "CNES.HAS_SURGICAL_CENTRE": "CENTRCIR",
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
    allow_unbounded: bool = False,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> QueryPlan:
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
            geography=spec.geography,
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
            lo = spec.period.start % 100 if year == spec.period.start // 100 else 1
            hi = spec.period.end % 100 if year == spec.period.end // 100 else 12
            pushed = tuple(range(lo, hi + 1)) if resolutions.get(year) == "month" else ()
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
    physical_uf = spec.geography.ufs if spec.geography and has_uf_axis else ()
    if capabilities.national_ufs:
        physical_uf = capabilities.national_ufs
        adaptations.append(Adaptation(
            "geography", "BR", ",".join(physical_uf),
            "DATASUS publishes this dataset per state only; the nation is read as every state",
        ))
    if capabilities.year_geography:
        national = ", ".join(str(year) for year, _ in capabilities.year_geography)
        adaptations.append(Adaptation(
            "geography", "all states", "BR",
            f"DATASUS publishes {national} both as a national file and as one file per state, the same records; "
            "only the national file is read (the state files would count every record twice)",
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
            "DATASUS publishes this dataset nationally only; BR is the whole publication",
        ))
    elif spec.geography and spec.geography.ufs and not has_uf_axis:
        raise ValueError(
            "requested UF is not a source/publication partition for this dataset; "
            "Pegasus will not manufacture it by filtering a record field"
        )
    hidden = {"_source_path", "year", "_competencia", "_source_resolution"}
    hidden.update(item.field for item in spec.dimensions)
    for item in spec.enrichments:
        # Only the column the route reads is required. The record's own
        # identifier, when the layout has one, is compared if present
        # (crosswalk.OWN_CNPJ_FIELDS); requiring a column named CNPJ made
        # enrich=["CNPJ"] fail on every SIH query (ADR-0100).
        if item.target == "CNPJ":
            hidden.add((item.from_field or "CNES").upper())
        elif item.target == "CNES":
            hidden.add((item.from_field or "CNPJ").upper())
        elif item.target in CNES_ATTRIBUTE_FIELDS or item.target == "CNES.ESTABLISHMENT_NAME":
            hidden.add((item.from_field or "CNES").upper())
        else:
            raise KeyError(f"no declared enrichment route to {item.target}")
    required_set = {
        "cnes_cnpj" for item in spec.enrichments if item.target in {"CNPJ", "CNES"}
    }
    # CNES attributes are read from CNES.ST at each record's competence; they
    # never needed the names resource (cnes_registry), and requiring it refused
    # every attribute enrichment on an install without it (2026-10-03).
    # CNES.ESTABLISHMENT_NAME needs no built resource: without the monthly
    # history (cnes_names) it answers from the current registry and says so
    # (ADR-0100).
    required = tuple(sorted(required_set))
    resource_period = (
        (spec.period.start, spec.period.end) if spec.period is not None else None
    )
    requirements = tuple(
        provider(name).describe(resolved, resource_period) for name in required
    )
    with shared_catalog(resolved) as catalog:
        estimate = download_estimate(
            resolved, catalog, system, series, capabilities.fetch_years, dict(year_months), physical_uf,
            dict(capabilities.year_geography),
        )
    return QueryPlan(
        spec,
        RetrievalPlan(
            system, series, resolution, years, months, physical_uf, strategy,
            tuple(sorted(hidden)), tuple(adaptations), capabilities.lake_years,
            capabilities.fetch_years, capabilities.year_resolutions,
            tuple(year_months), estimate[0], estimate[1], capabilities.year_geography, capabilities.lake_partitions,
        ),
        SemanticPlan(labels, spec.dimensions, spec.enrichments, required, requirements),
    )
