"""Immutable query intent, plans, reports and input parsing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from ..crosswalk import EnrichmentReport, EnrichmentRequest
from ..providers import ResourceRequirement


class TimeResolutionWarning(UserWarning):
    pass


class StructuralSchemaWarning(UserWarning):
    pass


class SemanticFallbackWarning(UserWarning):
    pass


class CrosswalkAmbiguityWarning(UserWarning):
    pass


@dataclass(frozen=True, slots=True)
class Period:
    start: int
    end: int
    precision: Literal["year", "month"]

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(range(self.start // 100, self.end // 100 + 1))

    def __str__(self) -> str:
        def show(value: int) -> str:
            return f"{value // 100:04d}-{value % 100:02d}" if self.precision == "month" else str(value // 100)

        return show(self.start) if self.start == self.end else f"{show(self.start)}..{show(self.end)}"


@dataclass(frozen=True, slots=True)
class Geography:
    uf: str | None = None
    municipality: str | None = None


@dataclass(frozen=True, slots=True)
class DimensionRequest:
    field: str
    name: str


@dataclass(frozen=True, slots=True)
class QuerySpec:
    dataset: str
    period: Period | None
    geography: Geography | None
    select: tuple[str, ...] | None
    schema_policy: Literal["union"] = "union"
    labels: bool = True
    dimensions: tuple[DimensionRequest, ...] = ()
    enrichments: tuple[EnrichmentRequest, ...] = ()
    provenance: Literal[False, "all"] = False
    resource_policy: Literal["local"] = "local"
    time_policy: Literal["adapt", "strict"] = "adapt"
    allow_unbounded: bool = False


@dataclass(frozen=True, slots=True)
class Adaptation:
    kind: str
    requested: str
    effective: str
    reason: str


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    system: str
    series: str | None
    publication_resolution: str
    years: tuple[int, ...]
    months: tuple[int, ...]
    physical_geography: str | None
    source_strategy: str
    hidden_dependencies: tuple[str, ...]
    adaptations: tuple[Adaptation, ...] = ()
    lake_years: tuple[int, ...] = ()
    fetch_years: tuple[int, ...] = ()
    year_resolutions: tuple[tuple[int, str], ...] = ()
    year_months: tuple[tuple[int, tuple[int, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticPlan:
    labels: bool
    dimensions: tuple[DimensionRequest, ...]
    enrichments: tuple[EnrichmentRequest, ...]
    required_resources: tuple[str, ...]
    resource_requirements: tuple[ResourceRequirement, ...]


@dataclass(frozen=True, slots=True)
class QueryPlan:
    spec: QuerySpec
    retrieval: RetrievalPlan
    semantics: SemanticPlan

    def explain(self) -> str:
        lines = [
            f"Dataset: {self.spec.dataset}",
            f"Requested period: {self.spec.period or 'all available'}",
            f"Publication resolution: {self.retrieval.publication_resolution}",
            f"Source strategy: {self.retrieval.source_strategy}",
            "Schema policy: union; structurally absent fields become null",
            f"Labels: {'identity-level only' if self.spec.labels else 'off'}",
        ]
        if self.retrieval.physical_geography:
            lines.append(f"Physical geography filter: {self.retrieval.physical_geography}")
        for adaptation in self.retrieval.adaptations:
            lines.append(
                f"Adaptation: {adaptation.requested} -> {adaptation.effective} ({adaptation.reason})"
            )
        for item in self.spec.dimensions:
            lines.append(f"Dimension: {item.field}.{item.name}")
        for item in self.spec.enrichments:
            lines.append(f"Enrichment: {item.from_field or 'inferred'} -> {item.target}")
        for requirement in self.semantics.resource_requirements:
            state = "local" if requirement.local else "missing"
            estimate = (
                f", estimated {requirement.estimated_bytes:,} source bytes"
                if requirement.estimated_bytes is not None and not requirement.local
                else ""
            )
            lines.append(f"Resource: {requirement.identity} ({state}{estimate})")
        return "\n".join(lines)


@dataclass(slots=True)
class QueryReport:
    requested_period: str | None = None
    effective_period: str | None = None
    source_strategy: str = ""
    publication_resolution: str = "unknown"
    adaptations: list[dict[str, str]] = field(default_factory=list)
    structural_absence: dict[str, list[str]] = field(default_factory=dict)
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    enrichments: list[EnrichmentReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_report: Any = None

    def as_dict(self) -> dict[str, Any]:
        if isinstance(self.source_report, (list, tuple)):
            source_report: Any = [
                item.as_dict() if hasattr(item, "as_dict") else item
                for item in self.source_report
            ]
        else:
            source_report = (
                self.source_report.as_dict()
                if hasattr(self.source_report, "as_dict")
                else self.source_report
            )
        return {
            "requested_period": self.requested_period,
            "effective_period": self.effective_period,
            "source_strategy": self.source_strategy,
            "publication_resolution": self.publication_resolution,
            "adaptations": self.adaptations,
            "structural_absence": self.structural_absence,
            "dimensions": self.dimensions,
            "enrichments": [item.as_dict() for item in self.enrichments],
            "warnings": self.warnings,
            "source_report": source_report,
        }


def _period(value: object) -> Period | None:
    if value is None:
        return None
    values = list(value) if isinstance(value, (tuple, list)) else [value]
    if len(values) not in {1, 2}:
        raise ValueError("period must be one value or a (start, end) pair")

    def parse(item: object, *, end: bool) -> tuple[int, str]:
        text = str(item).strip()
        if len(text) == 4 and text.isdigit():
            return int(text) * 100 + (12 if end else 1), "year"
        if len(text) == 7 and text[4] == "-" and text[:4].isdigit() and text[5:].isdigit():
            month = int(text[5:])
            if not 1 <= month <= 12:
                raise ValueError(f"period month {month} is not in 1..12")
            return int(text[:4]) * 100 + month, "month"
        raise ValueError(f"period value {item!r} must be YYYY or YYYY-MM")

    start, start_precision = parse(values[0], end=False)
    end, end_precision = parse(values[-1], end=True)
    if start > end:
        raise ValueError("period start is after its end")
    precision = "month" if "month" in {start_precision, end_precision} else "year"
    return Period(start, end, precision)


def _geography(value: object) -> Geography | None:
    if value is None:
        return None
    if isinstance(value, str):
        return Geography(uf=value.strip().upper())
    if isinstance(value, dict):
        return Geography(
            uf=str(value.get("uf") or "").upper() or None,
            municipality=str(value.get("municipality") or "") or None,
        )
    raise TypeError("geography must be a UF string or mapping")


def _dimensions(values: Sequence[str] | None) -> tuple[DimensionRequest, ...]:
    out: list[DimensionRequest] = []
    for value in values or ():
        field_name, separator, name = str(value).partition(".")
        if not separator or not field_name or not name:
            raise ValueError(f"dimension {value!r} must be FIELD.dimension")
        out.append(DimensionRequest(field_name.upper(), name))
    return tuple(out)


def _enrichments(values: Sequence[str | EnrichmentRequest] | None) -> tuple[EnrichmentRequest, ...]:
    out = []
    for item in values or ():
        if isinstance(item, EnrichmentRequest):
            out.append(
                EnrichmentRequest(
                    item.target.upper(), item.from_field, item.as_field, item.explode
                )
            )
        else:
            out.append(EnrichmentRequest(str(item).upper()))
    return tuple(out)


def _spec(
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
) -> QuerySpec:
    if provenance not in {False, "all"}:
        raise ValueError("provenance must be False or 'all'")
    if resource_policy != "local":
        raise ValueError(
            "resource_policy currently supports only 'local'; explicit resource builds "
            "are never hidden inside a query"
        )
    return QuerySpec(
        dataset=dataset,
        period=_period(period),
        geography=_geography(geography),
        select=tuple(str(item).upper() for item in select) if select else None,
        labels=labels,
        dimensions=_dimensions(dimensions),
        enrichments=_enrichments(enrich),
        provenance=provenance,
        resource_policy=resource_policy,
        time_policy=time_policy,
        allow_unbounded=bool(allow_unbounded),
    )
