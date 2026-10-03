"""Identity labels, vintage dimensions and registry enrichments."""

from __future__ import annotations

import warnings

import pyarrow as pa

from .._vintage import months_in, source_vintages
from ..config import Settings
from ..crosswalk import EnrichmentReport, EnrichmentRequest
from .model import QueryPlan, QueryReport, SemanticFallbackWarning
from .planner import CNES_ATTRIBUTE_FIELDS

#: ``source_namespace`` of a relation whose table holds shorter codes than the
#: field, matched on the field's leading characters as TabWin does.
TABWIN_LEADING = "tabwin_leading"


def _apply_dimensions(
    table: pa.Table, query_plan: QueryPlan, report: QueryReport, settings: Settings
) -> pa.Table:
    from ..catalog.store import Catalog
    from ..labelpack import (
        packed_mapping_covers_interval,
        packed_mapping_is_time_invariant,
        read_packed,
    )
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
                output = _geography_dimension(output, request, query_plan.retrieval.system, report)
                continue
            if request.field not in output.column_names:
                raise KeyError(f"{request.field}: required dimension source is absent")
            codes = output[request.field].to_pylist()
            vintages = source_vintages(output)
            lookups: dict[tuple[str, int | None, int | None], dict[str, object]] = {}
            values: list[object] = []
            artifacts: set[str] = set()
            unresolved_relation = 0
            # The effective relations depend on the vintage only; resolving
            # them per row queried the catalog for every month of every row.
            effective_by_vintage: dict[object, list] = {}
            for code, vintage in zip(codes, vintages, strict=True):
                vintage_key = (vintage.start, vintage.end) if vintage is not None else None
                if vintage_key in effective_by_vintage:
                    relations = effective_by_vintage[vintage_key]
                elif vintage is None:
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
                    monthly_relations = []
                    for month in months_in(vintage):
                        effective = [
                            *relations_for(
                                query_plan.retrieval.system,
                                dataset_code,
                                request.field,
                                relation_type=RelationType.ROLLUP_TO,
                                catalog=catalog,
                                vintage=month,
                            ),
                            *relations_for(
                                query_plan.retrieval.system,
                                dataset_code,
                                request.field,
                                relation_type=RelationType.ATTRIBUTE_OF,
                                catalog=catalog,
                                vintage=month,
                            ),
                        ]
                        monthly_relations.append(
                            tuple(
                                item
                                for item in effective
                                if item.target_name == request.name
                            )
                        )
                    relations = list(monthly_relations[0]) if monthly_relations else []
                    if any(value != monthly_relations[0] for value in monthly_relations[1:]):
                        relations = []
                effective_by_vintage[vintage_key] = relations
                if len(relations) > 1:
                    raise KeyError(
                        f"multiple effective relations for {request.field}.{request.name} "
                        f"across source vintage {vintage}"
                    )
                if not relations:
                    values.append(None)
                    unresolved_relation += 1
                    continue
                relation = relations[0]
                if vintage is not None and not packed_mapping_covers_interval(
                    relation.artifact,
                    system=query_plan.retrieval.system,
                    start=vintage.start,
                    end=vintage.end,
                ):
                    values.append(None)
                    unresolved_relation += 1
                    continue
                artifacts.add(relation.artifact)
                key = (
                    relation.artifact,
                    vintage.start if vintage is not None else None,
                    vintage.end if vintage is not None else None,
                )
                if key not in lookups:
                    months = months_in(vintage) if vintage is not None else ()
                    references = [
                        read_packed(
                            relation.artifact,
                            system=query_plan.retrieval.system,
                            competencia=month,
                        )
                        for month in months
                    ] or [
                        read_packed(
                            relation.artifact,
                            system=query_plan.retrieval.system,
                        )
                    ]
                    mappings = [
                        dict(
                            zip(
                                reference["code"].to_pylist(),
                                reference["label"].to_pylist(),
                                strict=True,
                            )
                        )
                        for reference in references
                    ]
                    first = mappings[0]
                    lookups[key] = {
                        source_code: label
                        for source_code, label in first.items()
                        if all(mapping.get(source_code) == label for mapping in mappings[1:])
                    }
                text = str(code).strip() if code is not None else None
                if text and relation.source_namespace == TABWIN_LEADING:
                    # The source's own .DEF maps the field through a table of
                    # shorter codes (RD2008.DEF: PROC_REA through TB_GRUPO);
                    # TabWin matches the leading characters to the table's
                    # code width. Only a relation that says so is read this way.
                    widths = {len(k) for k in lookups[key]}
                    text = text[:widths.pop()] if len(widths) == 1 else None
                values.append(lookups[key].get(text) if text else None)
            name = f"{request.field}_{request.name}"
            output = output.append_column(name, pa.array(values, pa.string()))
            report.dimensions.append(
                {
                    "request": f"{request.field}.{request.name}",
                    "relation": "declared temporal relation",
                    "artifacts": sorted(artifacts),
                    "vintage": "source vintage interval",
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


def _geography_dimension(table: pa.Table, request: object, system: str, report: QueryReport) -> pa.Table:
    """A municipality column rolled up through the membership pack.

    The field must be declared a municipality column for the system
    (``geography.yml`` ``municipality_fields``) and the name a classification
    of the pack. Vintage-exact as the codelist path is: the membership is
    resolved for every month of the record's interval, and a month that
    disagrees with another, or a classification the publishing systems
    contest, yields null and is counted, never chosen.
    """
    from ..geography import classification_names, memberships, municipality_fields

    field, name = request.field, request.name  # type: ignore[attr-defined]
    if field.upper() not in municipality_fields(system) or name not in classification_names():
        raise KeyError(f"no declared dimension {field}.{name}")
    if field not in table.column_names:
        raise KeyError(f"{field}: required dimension source is absent")
    cache: dict[tuple[str, int | None], tuple[str | None, bool]] = {}

    def at(code: str, month: int | None) -> tuple[str | None, bool]:
        key = (code, month)
        if key not in cache:
            found = memberships(code, system=system, vintage=month)
            member = next((m for m in found.memberships if m.classification == name), None)
            cache[key] = (member.member_label if member else None,
                          bool(member and member.contested))
        return cache[key]

    values: list[str | None] = []
    unresolved = contested = 0
    for code, vintage in zip(table[field].to_pylist(), source_vintages(table), strict=True):
        text = str(code or "").strip()
        if not text.isdigit() or len(text) not in (6, 7):
            values.append(None)
            unresolved += text != ""
            continue
        months = months_in(vintage) if vintage is not None else (None,)
        answers = {at(text, month) for month in months}
        if any(flag for _, flag in answers):
            values.append(None)
            contested += 1
        elif len(answers) == 1:
            label = next(iter(answers))[0]
            values.append(label)
            unresolved += label is None
        else:
            values.append(None)
            unresolved += 1
    table = table.append_column(f"{field}_{name}", pa.array(values, pa.string()))
    report.dimensions.append({
        "request": f"{field}.{name}", "relation": "membership pack (geography.parquet)",
        "artifacts": ["geography.parquet"], "vintage": "every month of the source interval",
        "unresolved_vintage_rows": unresolved, "contested_rows": contested,
    })
    for count, why in ((unresolved, "no membership for the code at its vintage"),
                       (contested, "the publishing systems contest the membership; name the system's own table")):
        if count:
            message = f"{field}.{name}: {count} row(s): {why}; derived values are null"
            report.warnings.append(message)
            warnings.warn(message, SemanticFallbackWarning, stacklevel=3)
    return table


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

    source_codes = {str(value or "").strip() for value in table[source_field].to_pylist()}
    try:
        path = ResourceManager(settings).ensure("cnes_names").path
    except FileNotFoundError:
        return _enrich_cnes_name_current(table, request, source_field, source_codes)
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


def _enrich_cnes_name_current(
    table: pa.Table, request: EnrichmentRequest, source_field: str, source_codes: set[str]
) -> tuple[pa.Table, EnrichmentReport]:
    """The establishment's name from the current CNES registry (ADR-0100).

    Used when the monthly history (``cnes_names``, built from CNES-ST) has not
    been built. It is the same registry that labels CNES columns, and each row
    says ``current_registry``: an establishment renamed since the record is
    named as it is now.
    """
    import pyarrow.compute as pc

    from ..registry import lookup

    registry = lookup("CADGERBR", "CNES")
    names: dict[str, str] = {}
    if registry is not None:
        hit = registry.filter(pc.is_in(registry["code"], value_set=pa.array(sorted(source_codes), pa.string())))
        names = {str(c): str(n) for c, n in zip(hit["code"].to_pylist(), hit["label"].to_pylist(), strict=True) if n}
    report = EnrichmentReport(
        request.target, source_field, f"{source_field}→CNES registry name (current)",
        rows_before=table.num_rows, rows_after=table.num_rows,
    )
    values: list[str | None] = []
    statuses: list[str] = []
    for code in table[source_field].to_pylist():
        name = names.get(str(code or "").strip())
        values.append(name)
        statuses.append("current_registry" if name else "unresolved")
        if name:
            report.matched += 1
        else:
            report.unmatched += 1
    output_name = _enrichment_output_name(request)
    output = _append_or_replace(table, output_name, values)
    output = _append_or_replace(output, f"{output_name}_resolution_status", statuses)
    return output, report


def _period_text(value: int) -> str:
    return f"{value // 100:04d}-{value % 100:02d}"


def _enrich_cnes_attribute(
    table: pa.Table,
    request: EnrichmentRequest,
    query_plan: QueryPlan,
    settings: Settings,
) -> tuple[pa.Table, EnrichmentReport]:
    import pyarrow.compute as pc

    source_field = (request.from_field or "CNES").upper()
    if source_field not in table.column_names:
        raise KeyError(f"{source_field}: required source field for CNES registry enrichment")
    registry_field = CNES_ATTRIBUTE_FIELDS[request.target]
    source_codes = {
        str(value or "").strip() for value in table[source_field].to_pylist()
    }
    # CNES.ST through the one door to data (ADR-0073), at the query's own
    # period and geography: the lake when it is built, the publications
    # otherwise. A lake-only scan refused every enrichment until someone had
    # built the national CNES.ST lake by hand (2026-10-03).
    from .executor import query as _query

    period = query_plan.spec.period
    registry = _query(
        "CNES-ST",
        period=(_period_text(period.start), _period_text(period.end)) if period else None,
        geography=list(query_plan.spec.geography.ufs) if query_plan.spec.geography else None,
        select=["CNES", registry_field, "COMPETEN"],
        present="analysis" if query_plan.spec.labels else "codes",
        settings=settings,
        allow_partial=True,
    )
    registry = registry.filter(pc.is_in(pc.cast(registry["CNES"], pa.string()),
                                        value_set=pa.array(sorted(source_codes), pa.string())))
    registry = _with_registry_competence(
        registry, "COMPETEN" if "COMPETEN" in registry.column_names else None
    )
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
            if value is None or str(value).strip() == "":
                # The establishment is in CNES.ST that month but the attribute
                # is empty (ESFERA_A in 2022): not a value, and not "matched".
                statuses.append("not_recorded")
                report.unmatched += 1
            else:
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
