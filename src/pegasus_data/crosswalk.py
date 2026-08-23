"""Typed, temporal and cardinality-safe identifier crosswalks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import pyarrow as pa


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
    competences: list[int | None],
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
    expression = ds.field(key_field).isin(sorted(codes))
    known = [int(value) for value in competences if value]
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
    out: dict[str, list[tuple[str, str, str, str]]] = {}
    for key, value, lo, hi, codelist in zip(
        table[key_field].to_pylist(),
        table[value_field].to_pylist(),
        valid_from,
        valid_to,
        codelists,
        strict=True,
    ):
        out.setdefault(str(key).strip(), []).append(
            (str(value), str(lo or ""), str(hi or ""), str(codelist))
        )
    return out


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def valid_cnpj(value: object) -> bool:
    digits = _digits(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    numbers = [int(char) for char in digits]
    for length in (12, 13):
        weights = list(range(length - 7, 1, -1)) + list(range(9, 1, -1))
        remainder = sum(n * w for n, w in zip(numbers[:length], weights, strict=True)) % 11
        check = 0 if remainder < 2 else 11 - remainder
        if numbers[length] != check:
            return False
    return True


def _covers(lo: str, hi: str, competence: int | None) -> bool:
    if competence is None:
        return not lo and not hi
    if not lo:
        return not hi or competence <= int(hi)
    return int(lo) <= competence <= (int(hi) if hi else 999912)


def enrich_cnpj(
    table: pa.Table,
    *,
    from_field: str = "CNES",
    raw_field: str = "CNPJ",
    as_field: str = "CNPJ_resolved",
    explode: bool = False,
    resource_path: str | Path | None = None,
) -> tuple[pa.Table, EnrichmentReport]:
    """Resolve CNPJ additively from CNES without changing fact-row count."""
    if from_field not in table.column_names:
        raise KeyError(f"{from_field}: required source field for CNES→CNPJ enrichment")
    source_values = table[from_field].to_pylist()
    raw_values = table[raw_field].to_pylist() if raw_field in table.column_names else [None] * table.num_rows
    if "_competencia" in table.column_names:
        competences = table["_competencia"].to_pylist()
    elif "year" in table.column_names:
        competences = [int(year) * 100 + 12 if year else None for year in table["year"].to_pylist()]
    else:
        competences = [None] * table.num_rows
    rows = _crosswalk_slice(
        {str(value or "").strip() for value in source_values},
        competences,
        resource_path=resource_path,
    )
    report = EnrichmentReport("CNPJ", from_field, f"{from_field}→CNPJ", rows_before=table.num_rows)
    resolved: list[str | None] = []
    statuses: list[str] = []
    take_indices: list[int] = []
    for row_index, (source, raw, competence) in enumerate(
        zip(source_values, raw_values, competences, strict=True)
    ):
        candidates = {
            cnpj for cnpj, lo, hi, _source in rows.get(str(source or "").strip(), ())
            if _covers(lo, hi, int(competence) if competence else None)
        }
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
    if "_competencia" in table.column_names:
        competences = table["_competencia"].to_pylist()
    elif "year" in table.column_names:
        competences = [
            int(year) * 100 + 12 if year else None
            for year in table["year"].to_pylist()
        ]
    else:
        competences = [None] * table.num_rows
    source_values = table[from_field].to_pylist()
    reverse = _crosswalk_slice(
        {_digits(value) for value in source_values},
        competences,
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
    for index, (cnpj, raw, competence) in enumerate(
        zip(source_values, raw_values, competences, strict=True)
    ):
        candidates = {
            cnes for cnes, lo, hi, _source in reverse.get(_digits(cnpj), ())
            if _covers(lo, hi, int(competence) if competence else None)
        }
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
