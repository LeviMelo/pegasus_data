"""Typed, temporal and cardinality-safe identifier crosswalks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import pyarrow as pa

from ._vintage import SourceVintage, source_vintages, window_covers, window_overlaps
from .identifiers import valid_cnpj

__all__ = ["EnrichmentReport", "EnrichmentRequest", "enrich_cnes", "enrich_cnpj", "enrichment", "valid_cnpj"]


@dataclass(frozen=True, slots=True)
class EnrichmentRequest:
    target: str
    from_field: str | None = None
    as_field: str | None = None
    explode: bool = False


@dataclass(slots=True)
class EnrichmentReport:
    target: str
    source_field: str
    route: str
    cardinality: str = "many-to-one per validity window"
    rows_before: int = 0
    rows_after: int = 0
    matched: int = 0
    unmatched: int = 0
    placeholders_replaced: int = 0
    confirmed: int = 0
    conflicts: int = 0
    ambiguous: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def enrichment(
    target: str, *, from_field: str | None = None, as_field: str | None = None, explode: bool = False
) -> EnrichmentRequest:
    """Declare an explicit enrichment route for :func:`pegasus_data.query`."""
    return EnrichmentRequest(target.upper(), from_field, as_field, explode)


def _pack_path() -> Path:
    from .config import load_settings

    local = load_settings().root / "resources" / "labels_crosswalk.parquet"
    return local if local.is_file() else Path(
        str(files("pegasus_data.resources") / "labels_crosswalk.parquet")
    )


def _crosswalk_slice(
    codes: set[str],
    vintages: list[int | SourceVintage | None],
    *,
    reverse: bool = False,
    resource_path: str | Path | None = None,
) -> dict[str, list[tuple[str, str, str, str]]]:
    """Scan only requested identifiers and overlapping validity row groups."""
    import pyarrow.dataset as ds

    if not codes:
        return {}
    path = str(resource_path or _pack_path())
    dataset = ds.dataset(path, format="parquet")
    names = set(dataset.schema.names)
    source = "source_code" if "source_code" in names else "code"
    target = "target_code" if "target_code" in names else "cnpj"
    key_field, value_field = (target, source) if reverse else (source, target)
    columns = [key_field, value_field]
    for optional in ("valid_from", "valid_to", "source_codelist", "codelist"):
        if optional in names and optional not in columns:
            columns.append(optional)
    # The pack writes CNPJs punctuated (14.354.955/0001-51); the question comes
    # in digits. Asking for digits alone matched nothing, so CNPJ->CNES never
    # resolved a row (ADR-0100).
    wanted = set(codes) | ({_punctuated(c) for c in codes if len(c) == 14} if reverse else set())
    expression = ds.field(key_field).isin(sorted(wanted))
    known: list[int] = []
    for value in vintages:
        if isinstance(value, SourceVintage):
            known.extend((value.start, value.end))
        elif value:
            known.append(int(value))
    if known and "valid_from" in names:
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
    table = dataset.to_table(columns=columns, filter=expression)
    valid_from = table["valid_from"].to_pylist() if "valid_from" in names else [""] * table.num_rows
    valid_to = table["valid_to"].to_pylist() if "valid_to" in names else [""] * table.num_rows
    codelist_name = "source_codelist" if "source_codelist" in names else "codelist"
    codelists = (
        table[codelist_name].to_pylist()
        if codelist_name in table.column_names
        else [""] * table.num_rows
    )
    out: dict[str, list[tuple[str, str, str, str]]] = _registry_slice(codes, reverse=reverse)
    for key, value, lo, hi, codelist in zip(
        table[key_field].to_pylist(),
        table[value_field].to_pylist(),
        valid_from,
        valid_to,
        codelists,
        strict=True,
    ):
        key_text = _digits(key) if reverse else str(key).strip()
        value_text = str(value).strip() if reverse else _digits(value)
        if not reverse and not valid_cnpj(value_text):
            continue  # 4,065 pack rows glue a digit of the name on (…/0007-85-4)
        if reverse and not valid_cnpj(key_text):
            continue
        out.setdefault(key_text, []).append(
            (value_text, str(lo or ""), str(hi or ""), str(codelist))
        )
    return out


def _punctuated(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


#: The source tag of a claim read from the establishment registry.
REGISTRY_SOURCE = "registry:CADGERBR"


def _registry_slice(codes: set[str], *, reverse: bool) -> dict[str, list[tuple[str, str, str, str]]]:
    """CNES <-> CNPJ from the establishment registry (ADR-0100).

    The registry's ``cnpj`` is a column checked against the CNPJ check digits,
    not text parsed out of a name, and each establishment carries the dates it
    entered and left the registry, which bound the claim. A registry that
    cannot be had contributes nothing; the pack's claims still apply.
    """
    import pyarrow.compute as pc

    from .registry import lookup

    try:
        table = lookup("CADGERBR", "CNES")
    except Exception:  # noqa: BLE001 - no registry is a gap, not a crash
        table = None
    if table is None or "cnpj" not in table.column_names or not codes:
        return {}
    key = "cnpj" if reverse else "code"
    table = table.filter(pc.is_in(table[key], value_set=pa.array(sorted(codes), pa.string())))
    table = table.filter(pc.is_valid(table["cnpj"]))
    out: dict[str, list[tuple[str, str, str, str]]] = {}
    for code, cnpj, included, excluded in zip(
        table["code"].to_pylist(), table["cnpj"].to_pylist(),
        table["included"].to_pylist(), table["excluded"].to_pylist(), strict=True,
    ):
        lo = str(included or "")[:6]
        hi = str(excluded or "")[:6]
        hi = "" if hi.startswith("9999") else hi
        k, v = (cnpj, code) if reverse else (code, cnpj)
        out.setdefault(str(k), []).append((str(v), lo, hi, REGISTRY_SOURCE))
    return out


def _covering(available: object, vintage: object) -> set[str]:
    """The claims whose window covers the vintage: the registry's when it has one.

    The registry is DATASUS's current record, with dates; the pack's claims are
    older kits' snapshots with no windows, so they speak only where the
    registry does not.
    """
    claims = list(available or ())
    registry = {v for v, lo, hi, src in claims if src == REGISTRY_SOURCE and window_covers(lo, hi, vintage)}
    if registry:
        return registry
    return {v for v, lo, hi, src in claims if src != REGISTRY_SOURCE and window_covers(lo, hi, vintage)}


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


#: A record's own CNPJ for its establishment, by layout: compared with the
#: crosswalk's answer when present (SIH/CIH hospital CGC_HOSP, APAC and BPA-I
#: executing establishment).
OWN_CNPJ_FIELDS = ("CNPJ", "CGC_HOSP", "AP_CNPJCPF", "CNPJCPF", "PA_CNPJCPF")


def enrich_cnpj(
    table: pa.Table,
    *,
    from_field: str = "CNES",
    raw_field: str | None = None,
    as_field: str = "CNPJ_resolved",
    explode: bool = False,
    resource_path: str | Path | None = None,
) -> tuple[pa.Table, EnrichmentReport]:
    """Resolve CNPJ additively from CNES without changing fact-row count."""
    if from_field not in table.column_names:
        raise KeyError(f"{from_field}: required source field for CNES→CNPJ enrichment")
    source_values = table[from_field].to_pylist()
    raw_field = raw_field or next((f for f in OWN_CNPJ_FIELDS if f in table.column_names), None)
    raw_values = table[raw_field].to_pylist() if raw_field in table.column_names else [None] * table.num_rows
    vintages = source_vintages(table)
    rows = _crosswalk_slice(
        {str(value or "").strip() for value in source_values},
        vintages,
        resource_path=resource_path,
    )
    report = EnrichmentReport("CNPJ", from_field, f"{from_field}→CNPJ", rows_before=table.num_rows)
    resolved: list[str | None] = []
    statuses: list[str] = []
    take_indices: list[int] = []
    for row_index, (source, raw, vintage) in enumerate(
        zip(source_values, raw_values, vintages, strict=True)
    ):
        available = rows.get(str(source or "").strip(), ())
        candidates = _covering(available, vintage)
        coarse_ambiguity = bool(
            vintage is not None
            and not vintage.exact
            and any(window_overlaps(lo, hi, vintage) for _value, lo, hi, _source in available)
            and not candidates
        )
        raw_digits = _digits(raw)
        raw_valid = valid_cnpj(raw_digits)
        if len(candidates) > 1 and explode:
            for candidate in sorted(candidates):
                take_indices.append(row_index)
                resolved.append(candidate)
                statuses.append("crosswalk_exploded")
            report.ambiguous += 1
            report.matched += 1
            continue
        take_indices.append(row_index)
        if len(candidates) > 1:
            value, status = None, "ambiguous_crosswalk"
            report.ambiguous += 1
        elif len(candidates) == 1:
            candidate = next(iter(candidates))
            if raw_valid and raw_digits == candidate:
                value, status = raw_digits, "observed_confirmed"
                report.confirmed += 1
            elif raw_valid:
                value, status = None, "conflict"
                report.conflicts += 1
            else:
                value, status = candidate, "crosswalk_fallback"
                report.placeholders_replaced += 1
            report.matched += 1
        elif raw_valid:
            value, status = raw_digits, "observed"
            report.unmatched += 1
        elif coarse_ambiguity:
            value, status = None, "coarse_vintage"
            report.ambiguous += 1
        else:
            value, status = None, "unresolved"
            report.unmatched += 1
        resolved.append(value)
        statuses.append(status)
    report.rows_after = len(take_indices)
    output = table.take(pa.array(take_indices, pa.int64())) if explode else table
    for name, array in (
        (as_field, pa.array(resolved, pa.string())),
        (f"{as_field.removesuffix('_resolved')}_resolution_status", pa.array(statuses, pa.string())),
    ):
        if name in output.column_names:
            output = output.set_column(output.column_names.index(name), name, array)
        else:
            output = output.append_column(name, array)
    return output, report


def enrich_cnes(
    table: pa.Table,
    *,
    from_field: str = "CNPJ",
    raw_field: str = "CNES",
    as_field: str = "CNES_resolved",
    explode: bool = False,
    resource_path: str | Path | None = None,
) -> tuple[pa.Table, EnrichmentReport]:
    """Reverse CNPJ→CNES lookup; one-to-many is explicit and safe by default."""
    if from_field not in table.column_names:
        raise KeyError(f"{from_field}: required source field for CNPJ→CNES enrichment")
    raw_values = table[raw_field].to_pylist() if raw_field in table.column_names else [None] * table.num_rows
    vintages = source_vintages(table)
    source_values = table[from_field].to_pylist()
    reverse = _crosswalk_slice(
        {_digits(value) for value in source_values},
        vintages,
        reverse=True,
        resource_path=resource_path,
    )
    report = EnrichmentReport(
        "CNES", from_field, f"{from_field}→CNES", cardinality="one-to-many per validity window",
        rows_before=table.num_rows,
    )
    indices: list[int] = []
    resolved: list[str | None] = []
    statuses: list[str] = []
    for index, (cnpj, raw, vintage) in enumerate(
        zip(source_values, raw_values, vintages, strict=True)
    ):
        available = reverse.get(_digits(cnpj), ())
        candidates = _covering(available, vintage)
        coarse_ambiguity = bool(
            vintage is not None
            and not vintage.exact
            and any(window_overlaps(lo, hi, vintage) for _value, lo, hi, _source in available)
            and not candidates
        )
        if len(candidates) > 1 and explode:
            for candidate in sorted(candidates):
                indices.append(index)
                resolved.append(candidate)
                statuses.append("crosswalk_exploded")
            report.ambiguous += 1
            report.matched += 1
            continue
        indices.append(index)
        raw_code = str(raw or "").strip()
        if len(candidates) > 1:
            value, status = None, "ambiguous_crosswalk"
            report.ambiguous += 1
        elif len(candidates) == 1:
            candidate = next(iter(candidates))
            if raw_code and raw_code == candidate:
                value, status = raw_code, "observed_confirmed"
                report.confirmed += 1
            elif raw_code:
                value, status = None, "conflict"
                report.conflicts += 1
            else:
                value, status = candidate, "crosswalk_fallback"
            report.matched += 1
        elif raw_code:
            value, status = raw_code, "observed"
            report.unmatched += 1
        elif coarse_ambiguity:
            value, status = None, "coarse_vintage"
            report.ambiguous += 1
        else:
            value, status = None, "unresolved"
            report.unmatched += 1
        resolved.append(value)
        statuses.append(status)
    output = table.take(pa.array(indices, pa.int64())) if explode else table
    report.rows_after = len(indices)
    for name, values in (
        (as_field, pa.array(resolved, pa.string())),
        (f"{as_field.removesuffix('_resolved')}_resolution_status", pa.array(statuses, pa.string())),
    ):
        output = output.append_column(name, values)
    return output, report
