"""Intent-driven query planning over lake and fetch mechanics."""

from __future__ import annotations

import json
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.compute as pc

from .config import UF_TO_NUMERIC, Settings, load_settings
from .crosswalk import EnrichmentReport, EnrichmentRequest, enrich_cnes, enrich_cnpj
from .providers import ResourceRequirement, provider

CNES_ATTRIBUTE_FIELDS = {
    "CNES.NATURE": "NATUREZA",
    "CNES.LEGAL_NATURE": "NAT_JUR",
    "CNES.TYPE": "TP_UNID",
    "CNES.OWNERSHIP": "ESFERA_A",
}


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
    provenance: Literal[False, "derived", "all"] = False
    resource_policy: Literal["auto", "local", "remote"] = "auto"
    time_policy: Literal["adapt", "strict"] = "adapt"


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
    row_geography_field: str | None
    row_time_field: str | None
    source_strategy: str
    hidden_dependencies: tuple[str, ...]
    adaptations: tuple[Adaptation, ...] = ()


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
        if self.retrieval.row_geography_field:
            lines.append(f"Row geography filter: {self.retrieval.row_geography_field}")
        if self.retrieval.row_time_field:
            lines.append(f"Row time filter: {self.retrieval.row_time_field}")
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
            "source_report": (
                self.source_report.as_dict() if hasattr(self.source_report, "as_dict") else self.source_report
            ),
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
    provenance: Literal[False, "derived", "all"] = False,
    resource_policy: Literal["auto", "local", "remote"] = "auto",
    time_policy: Literal["adapt", "strict"] = "adapt",
) -> QuerySpec:
    if provenance not in {False, "derived", "all"}:
        raise ValueError("provenance must be False, 'derived', or 'all'")
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
    )


def _capabilities(
    settings: Settings, system: str, series: str | None
) -> tuple[str, bool, str, str | None, str | None]:
    """Publication resolution, physical axes, source strategy, and row axes."""
    from .retrieve import _families

    if settings.catalog_path.is_file():
        from .catalog.store import Catalog

        store = Catalog(settings.catalog_path, read_only=True)
        try:
            families = _families(store, system, series)
            ids = [str(item["family_id"]) for item in families]
            if ids:
                marks = ",".join("?" for _ in ids)
                rows = store.query(
                    f"SELECT fa.normalized_date, fa.geo_code FROM family_files ff "
                    f"JOIN file_facts fa ON fa.path=ff.path WHERE ff.family_id IN ({marks})",
                    ids,
                )
                monthly = any(int(row["normalized_date"] or 0) % 100 for row in rows)
                uf_axis = any(str(row["geo_code"] or "") not in {"", "BR"} for row in rows)
                lake = bool(
                    store.query(
                        f"SELECT 1 FROM lake_partitions WHERE family_id IN ({marks}) LIMIT 1", ids
                    )
                )
                fields = {
                    str(row["field_name"])
                    for row in store.query(
                        f"SELECT DISTINCT sp.field_name FROM families f JOIN schema_presence sp "
                        f"ON sp.schema_signature=f.schema_signature WHERE f.family_id IN ({marks})",
                        ids,
                    )
                }
                row_geo = next(
                    (
                        name
                        for name in (
                            "MUNIC_RES",
                            "CODMUNRES",
                            "CODMUN_RES",
                            "MUNIC_MOV",
                            "UF",
                            "SG_UF",
                            "UF_RESID",
                        )
                        if name in fields
                    ),
                    None,
                )
                row_time = next(
                    (
                        name
                        for name in (
                            "COMPETEN",
                            "COMPETENCIA",
                            "DT_INTER",
                            "DT_NOTIFIC",
                            "DTOBITO",
                            "DT_OBITO",
                        )
                        if name in fields
                    ),
                    None,
                )
                if row_time is None and {"ANO_CMPT", "MES_CMPT"} <= fields:
                    row_time = "ANO_CMPT+MES_CMPT"
                return (
                    "month" if monthly else "year",
                    uf_axis,
                    "lake" if lake else "fetch",
                    row_geo,
                    row_time,
                )
        finally:
            store.close()
    return "unknown", True, "fetch", None, None


def plan(
    dataset: str,
    *,
    period: object = None,
    geography: object = None,
    select: Sequence[str] | None = None,
    labels: bool = True,
    dimensions: Sequence[str] | None = None,
    enrich: Sequence[str | EnrichmentRequest] | None = None,
    provenance: Literal[False, "derived", "all"] = False,
    resource_policy: Literal["auto", "local", "remote"] = "auto",
    time_policy: Literal["adapt", "strict"] = "adapt",
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> QueryPlan:
    from .retrieve import parse_dataset

    spec = _spec(
        dataset, period=period, geography=geography, select=select, labels=labels,
        dimensions=dimensions, enrich=enrich, provenance=provenance,
        resource_policy=resource_policy, time_policy=time_policy,
    )
    resolved = settings or load_settings(root=Path(root) if root else None)
    system, series = parse_dataset(dataset)
    resolution, has_uf_axis, strategy, row_geo_field, row_time_field = _capabilities(
        resolved, system, series
    )
    adaptations: list[Adaptation] = []
    years = spec.period.years if spec.period else ()
    months: tuple[int, ...] = ()
    if spec.period and spec.period.precision == "month":
        if resolution == "year":
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
        if row_geo not in {"MUNIC_RES", "CODMUNRES", "CODMUN_RES", "MUNIC_MOV"}:
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
            tuple(sorted(hidden)), tuple(adaptations),
        ),
        SemanticPlan(labels, spec.dimensions, spec.enrichments, required, requirements),
    )


def _with_competence(table: pa.Table, source_report: Any) -> pa.Table:
    if "_competencia" in table.column_names or "_source_path" not in table.column_names:
        return table
    facts = getattr(source_report, "source_facts", {}) or {}
    values = [
        (facts.get(str(path), (None, None, None))[2] if path is not None else None)
        for path in table["_source_path"].to_pylist()
    ]
    return table.append_column("_competencia", pa.array(values, pa.int32()))


def _competence_value(value: object) -> int | None:
    """Return YYYYMM from common DATASUS competence/date encodings."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.year * 100 + value.month
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 7 and text[:4].isdigit() and text[4] in {"-", "/"}:
        month = text[5:7]
        if month.isdigit() and 1 <= int(month) <= 12:
            return int(text[:4]) * 100 + int(month)
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) == 6 and 190001 <= int(digits) <= 219912:
        month = int(digits[4:])
        return int(digits) if 1 <= month <= 12 else None
    if len(digits) == 8:
        if 1900 <= int(digits[:4]) <= 2199 and 1 <= int(digits[4:6]) <= 12:
            return int(digits[:6])
        if 1900 <= int(digits[-4:]) <= 2199 and 1 <= int(digits[2:4]) <= 12:
            return int(digits[-4:]) * 100 + int(digits[2:4])
    return None


def _with_row_competence(table: pa.Table, row_time_field: str | None) -> pa.Table:
    if not row_time_field:
        return table
    if "+" in row_time_field:
        year_field, month_field = row_time_field.split("+", 1)
        if year_field not in table.column_names or month_field not in table.column_names:
            return table
        values = []
        for year, month in zip(
            table[year_field].to_pylist(), table[month_field].to_pylist(), strict=True
        ):
            try:
                year_number, month_number = int(year), int(month)
            except (TypeError, ValueError):
                values.append(None)
                continue
            values.append(
                year_number * 100 + month_number
                if 1900 <= year_number <= 2199 and 1 <= month_number <= 12
                else None
            )
    else:
        if row_time_field not in table.column_names:
            return table
        values = [_competence_value(value) for value in table[row_time_field].to_pylist()]
    row_values = pa.array(values, pa.int32())
    if "_competencia" not in table.column_names:
        return table.append_column("_competencia", row_values)
    # A declared row-time field is analytically more precise than the file
    # competence. This matters for annual containers, whose file fact is an
    # enclosure (YYYY00), not the month of every contained record.
    return table.set_column(table.column_names.index("_competencia"), "_competencia", row_values)


def _filter_period(table: pa.Table, period: Period | None, adapted: bool) -> pa.Table:
    if period is None or adapted or "_competencia" not in table.column_names:
        return table
    values = table["_competencia"]
    mask = pc.and_(pc.greater_equal(values, period.start), pc.less_equal(values, period.end))
    return table.filter(pc.fill_null(mask, False))


def _filter_geography(table: pa.Table, geography: Geography | None, physical: bool) -> pa.Table:
    if geography is None or (physical and not geography.municipality):
        return table
    if geography.municipality:
        for name in ("MUNIC_RES", "CODMUNRES", "CODMUN_RES"):
            if name in table.column_names:
                return table.filter(pc.equal(pc.cast(table[name], pa.string()), geography.municipality))
        raise ValueError("requested municipality cannot be represented by this dataset's rows")
    if geography.uf:
        for name in ("UF", "SG_UF", "UF_RESID"):
            if name in table.column_names:
                return table.filter(pc.equal(pc.cast(table[name], pa.string()), geography.uf))
        prefix = UF_TO_NUMERIC.get(geography.uf)
        for name in ("MUNIC_RES", "CODMUNRES", "CODMUN_RES", "MUNIC_MOV"):
            if name in table.column_names and prefix:
                return table.filter(pc.starts_with(pc.cast(table[name], pa.string()), prefix))
        raise ValueError("requested UF cannot be represented physically or by a reliable row field")
    return table


def _apply_dimensions(
    table: pa.Table, query_plan: QueryPlan, report: QueryReport
) -> pa.Table:
    from .labelpack import read_packed
    from .semantics.relations import RelationType, relations_for

    output = table
    dataset_code = query_plan.spec.dataset.replace("-", ".").upper()
    for request in query_plan.spec.dimensions:
        relations = [
            *relations_for(
                query_plan.retrieval.system, dataset_code, request.field,
                relation_type=RelationType.ROLLUP_TO,
            ),
            *relations_for(
                query_plan.retrieval.system, dataset_code, request.field,
                relation_type=RelationType.ATTRIBUTE_OF,
            ),
        ]
        relations = [item for item in relations if item.target_name == request.name]
        if len(relations) != 1:
            raise KeyError(f"no unique declared dimension {request.field}.{request.name}")
        relation = relations[0]
        if request.field not in output.column_names:
            raise KeyError(f"{request.field}: required dimension source is absent")
        reference = read_packed(relation.artifact, system=query_plan.retrieval.system)
        lookup = dict(zip(reference["code"].to_pylist(), reference["label"].to_pylist(), strict=True))
        values = [lookup.get(str(value).strip()) if value is not None else None for value in output[request.field].to_pylist()]
        name = f"{request.field}_{request.name}"
        output = output.append_column(name, pa.array(values, pa.string()))
        report.dimensions.append(
            {"request": f"{request.field}.{request.name}", "relation": relation.relation_type.value, "artifact": relation.artifact}
        )
    return output


def _enforce_identity_labels(
    table: pa.Table, query_plan: QueryPlan, source_report: Any, report: QueryReport
) -> pa.Table:
    """Remove any rendered label proven to be a roll-up or attribute."""
    from .semantics.relations import RelationType, relations_for

    render = getattr(source_report, "render", None) or source_report
    used = getattr(render, "codelist_used", {}) or {}
    rollups = set(getattr(render, "rollup_used", ()) or ())
    dataset_code = query_plan.spec.dataset.replace("-", ".").upper()
    output = table
    for field_name, artifacts in used.items():
        relations = relations_for(query_plan.retrieval.system, dataset_code, field_name)
        nonlabels = {
            item.artifact
            for item in relations
            if item.relation_type in {RelationType.ROLLUP_TO, RelationType.ATTRIBUTE_OF}
        }
        chosen = {part.strip() for part in str(artifacts).split(",")}
        if field_name not in rollups and not (chosen & nonlabels):
            continue
        label_name = f"{field_name}_label"
        if label_name in output.column_names:
            output = output.drop_columns([label_name])
        message = (
            f"{field_name}: {artifacts} is a dimension/roll-up, not an identity label; "
            "the raw code was preserved and the label output was refused"
        )
        report.warnings.append(message)
        warnings.warn(message, SemanticFallbackWarning, stacklevel=3)
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


def _enrich_cnes_name(
    table: pa.Table, request: EnrichmentRequest, settings: Settings
) -> tuple[pa.Table, EnrichmentReport]:
    import pyarrow.parquet as pq

    source_field = (request.from_field or "CNES").upper()
    if source_field not in table.column_names:
        raise KeyError(f"{source_field}: required source field for CNES registry enrichment")
    path = settings.root / "resources" / "cnes_registry.parquet"
    registry = pq.read_table(path)
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
    competences = (
        table["_competencia"].to_pylist()
        if "_competencia" in table.column_names
        else [None] * table.num_rows
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
            if competence is None
            or (not lo or int(lo) <= int(competence))
            and (not hi or int(competence) <= int(hi))
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
    from .api import Catalog as PublicCatalog
    from .api import load

    source_field = (request.from_field or "CNES").upper()
    if source_field not in table.column_names:
        raise KeyError(f"{source_field}: required source field for CNES registry enrichment")
    registry_field = CNES_ATTRIBUTE_FIELDS[request.target]
    catalog = PublicCatalog(settings=settings)
    try:
        registry = load(
            "CNES",
            "ST",
            uf=(
                [query_plan.spec.geography.uf]
                if query_plan.spec.geography and query_plan.spec.geography.uf
                else None
            ),
            years=query_plan.retrieval.years or None,
            columns=["CNES", registry_field],
            labels=query_plan.spec.labels,
            profile="audit" if query_plan.spec.labels else "codes",
            companions=False,
            derived=False,
            on_missing_column="error",
            catalog=catalog,
            _preserve_internal=True,
        )
    finally:
        catalog.close()
    registry = _with_row_competence(registry, "COMPETEN" if "COMPETEN" in registry.column_names else None)
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
    provenance: Literal[False, "derived", "all"] = False,
    resource_policy: Literal["auto", "local", "remote"] = "auto",
    time_policy: Literal["adapt", "strict"] = "adapt",
    return_report: bool = False,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> pa.Table | tuple[pa.Table, QueryReport]:
    query_plan = plan(
        dataset, period=period, geography=geography, select=select, labels=labels,
        dimensions=dimensions, enrich=enrich, provenance=provenance,
        resource_policy=resource_policy, time_policy=time_policy, root=root, settings=settings,
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
        from ._resources import ResourceManager

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
    if retrieval.source_strategy == "lake":
        from .api import Catalog as PublicCatalog
        from .api import load

        cat = PublicCatalog(settings=resolved)
        try:
            table, source_report = load(
                retrieval.system, retrieval.series,
                uf=[retrieval.physical_geography] if retrieval.physical_geography else None,
                years=retrieval.years or None, columns=requested_columns,
                labels=labels, profile="audit" if labels else "codes",
                companions=False, derived=False, on_missing_column="null_fill",
                report=True, catalog=cat, _preserve_internal=True,
            )
        finally:
            cat.close()
    else:
        from .retrieve import fetch

        table, source_report = fetch(
            dataset,
            uf=retrieval.physical_geography,
            years=retrieval.years or None,
            months=retrieval.months or None,
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
        table = _with_competence(table, source_report)
    report.source_report = source_report
    raw_absence = dict(
        getattr(source_report, "structural_absence", None)
        or getattr(source_report, "columns_structurally_absent", {})
        or {}
    )
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
    if coarsening:
        adaptation = coarsening
        message = (
            f"requested {adaptation.requested}; effective period {adaptation.effective}: "
            f"{adaptation.reason}"
        )
        report.warnings.append(message)
        warnings.warn(message, TimeResolutionWarning, stacklevel=2)
    table = _with_row_competence(table, retrieval.row_time_field)
    table = _filter_period(table, query_plan.spec.period, coarsening is not None)
    table = _filter_geography(table, query_plan.spec.geography, bool(retrieval.physical_geography))
    table = _enforce_identity_labels(table, query_plan, source_report, report)
    table = _apply_dimensions(table, query_plan, report)
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
