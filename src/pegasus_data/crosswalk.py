"""Typed, temporal and cardinality-safe identifier crosswalks."""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa

from ._vintage import SourceVintage, vintage_groups, window_covers, window_overlaps
from .identifiers import valid_cnpj

if TYPE_CHECKING:
    from .config import Settings

__all__ = ["EnrichmentReport", "EnrichmentRequest", "enrich_cnes", "enrich_cnpj", "enrichment", "valid_cnpj"]


@dataclass(frozen=True, slots=True)
class EnrichmentRequest:
    target: str
    from_field: str | None = None
    as_field: str | None = None
    explode: bool = False


def source_field(dataset: str, request: EnrichmentRequest) -> str:
    """The column an enrichment reads its key from: the request's own, else the one the dataset's roles declare (the
    establishment's CNES code; for the CNPJ→CNES route its CNPJ). Never a guessed name: a dataset whose roles name
    none (or several) asks for ``from_field``."""
    from .semantics.column_roles import facility_cnpj_field, facility_code_field

    if request.from_field:
        return request.from_field.upper()
    reverse = request.target == "CNES"
    found = (facility_cnpj_field if reverse else facility_code_field)(dataset)
    if found is None:
        raise KeyError(f"{dataset}: its column roles name no single {'CNPJ' if reverse else 'CNES code'} column "
                       f"of the establishment; say which with from_field")
    return found.upper()


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
    #: ``unavailable`` when the establishment registry could not be had: the claims come from the older kits alone,
    #: which carry no validity window, and the answers are not the registry's
    registry: str = "available"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def enrichment(
    target: str, *, from_field: str | None = None, as_field: str | None = None, explode: bool = False
) -> EnrichmentRequest:
    """Declare an explicit enrichment route for :func:`pegasus_data.query`."""
    return EnrichmentRequest(target.upper(), from_field, as_field, explode)


def _pack_path(settings: Settings | None = None) -> Path:
    """The CNES-CNPJ pack: a copy under the root in use's ``resources/`` when it has one, the shipped one otherwise."""
    local = settings.root / "resources" / "labels_crosswalk.parquet" if settings is not None else None
    return local if local is not None and local.is_file() else Path(
        str(files("pegasus_data.resources") / "labels_crosswalk.parquet")
    )


class ClaimMap(dict):  # type: ignore[type-arg]
    """``key -> claims``, and whether the registry that dates them could be read."""

    registry_unavailable: bool = False


def _crosswalk_slice(
    codes: set[str],
    vintages: Sequence[int | SourceVintage | None],
    *,
    reverse: bool = False,
    resource_path: str | Path | None = None,
    settings: Settings | None = None,
) -> dict[str, list[tuple[str, str, str, str]]]:
    """Scan only requested identifiers and overlapping validity row groups. ``settings`` is the root in use: the
    establishment registry is read from its ``registries_dir`` (OQ 81); without it the registry is unavailable."""
    import pyarrow.dataset as ds

    if not codes:
        return {}
    path = str(resource_path or _pack_path(settings))
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
    registry, unavailable = _registry_slice(
        codes, reverse=reverse, registries=None if settings is None else settings.registries_dir
    )
    out = ClaimMap(registry)
    out.registry_unavailable = unavailable
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


def _registry_slice(
    codes: set[str], *, reverse: bool, registries: Path | None,
) -> tuple[dict[str, list[tuple[str, str, str, str]]], bool]:
    """CNES <-> CNPJ from the establishment registry (ADR-0100), and whether the registry could be read. It is read
    from ``registries``, the root in use's (OQ 81); a caller that names none has no registry.

    The registry's ``cnpj`` is a column checked against the CNPJ check digits,
    not text parsed out of a name, and each establishment carries the dates it
    entered and left the registry, which bound the claim. A registry that
    cannot be had (``lookup`` says so, with a warning) contributes nothing, the pack's claims
    still apply, and the answer is flagged: they are the older kits' undated claims. Any other
    failure reading it is not "no registry" and propagates.
    """
    import pyarrow.compute as pc

    from .registry import lookup

    if not codes:
        return {}, False
    if registries is None:
        return {}, True
    table = lookup("CADGERBR", "CNES", registries)
    if table is None or "cnpj" not in table.column_names:
        return {}, True
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
    return out, False


def _covering(available: Sequence[tuple[str, str, str, str]], vintage: SourceVintage | None) -> set[str]:
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


_NON_DIGIT = re.compile(r"\D")


@lru_cache(maxsize=1 << 16)
def _digits(value: object) -> str:
    return _NON_DIGIT.sub("", str(value or ""))


def _warn_registry(report: EnrichmentReport) -> None:
    if report.registry == "unavailable":
        warnings.warn(f"{report.route}: the establishment registry (CADGERBR) could not be read, so the answers are the "
                      "older kits' undated claims alone", stacklevel=3)


def _resolver(available_for: Any, distinct: Sequence[SourceVintage | None]) -> Any:
    """``(key, vintage index) -> (candidate values, coarse ambiguity)``, computed once per DISTINCT pair: a table has
    thousands of establishments and a handful of vintages, and its millions of rows ask the same few questions."""
    memo: dict[tuple[str, int], tuple[set[str], bool]] = {}

    def resolve(key: str, vintage_index: int) -> tuple[set[str], bool]:
        hit = memo.get((key, vintage_index))
        if hit is None:
            available = available_for(key)
            vintage = distinct[vintage_index]
            candidates = _covering(available, vintage)
            coarse = bool(vintage is not None and not vintage.exact and not candidates
                          and any(window_overlaps(lo, hi, vintage) for _value, lo, hi, _source in available))
            hit = memo[(key, vintage_index)] = (candidates, coarse)
        return hit

    return resolve


def enrich_cnpj(
    table: pa.Table,
    *,
    from_field: str = "CNES",
    raw_field: str | None = None,
    as_field: str = "CNPJ_resolved",
    explode: bool = False,
    resource_path: str | Path | None = None,
    settings: Settings | None = None,
) -> tuple[pa.Table, EnrichmentReport]:
    """Resolve CNPJ additively from CNES without changing fact-row count. ``from_field`` is the column holding the
    CNES code and ``raw_field`` the record's own CNPJ, compared with the answer when given; the dataset's roles name
    both (`column_roles.facility_code_field`, `facility_cnpj_field`)."""
    if from_field not in table.column_names:
        raise KeyError(f"{from_field}: required source field for CNES→CNPJ enrichment")
    source_values = table[from_field].to_pylist()
    raw_values = table[raw_field].to_pylist() if raw_field in table.column_names else [None] * table.num_rows
    distinct, vintage_index = vintage_groups(table)
    rows = _crosswalk_slice(
        {str(value or "").strip() for value in source_values},
        distinct,
        resource_path=resource_path,
        settings=settings,
    )
    resolve = _resolver(lambda key: rows.get(key, ()), distinct)
    valid: dict[str, bool] = {}
    report = EnrichmentReport("CNPJ", from_field, f"{from_field}→CNPJ", rows_before=table.num_rows,
                              registry="unavailable" if getattr(rows, "registry_unavailable", False) else "available")
    _warn_registry(report)
    resolved: list[str | None] = []
    statuses: list[str] = []
    take_indices: list[int] = []
    for row_index, (source, raw, vintage_at) in enumerate(
        zip(source_values, raw_values, vintage_index.to_pylist(), strict=True)
    ):
        candidates, coarse_ambiguity = resolve(str(source or "").strip(), vintage_at)
        raw_digits = _digits(raw)
        raw_valid = valid.get(raw_digits)
        if raw_valid is None:
            raw_valid = valid[raw_digits] = valid_cnpj(raw_digits)
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
    raw_field: str | None = None,
    as_field: str = "CNES_resolved",
    explode: bool = False,
    resource_path: str | Path | None = None,
    settings: Settings | None = None,
) -> tuple[pa.Table, EnrichmentReport]:
    """Reverse CNPJ→CNES lookup; one-to-many is explicit and safe by default."""
    if from_field not in table.column_names:
        raise KeyError(f"{from_field}: required source field for CNPJ→CNES enrichment")
    raw_values = table[raw_field].to_pylist() if raw_field in table.column_names else [None] * table.num_rows
    distinct, vintage_index = vintage_groups(table)
    source_values = table[from_field].to_pylist()
    reverse = _crosswalk_slice(
        {_digits(value) for value in source_values},
        distinct,
        reverse=True,
        resource_path=resource_path,
        settings=settings,
    )
    resolve = _resolver(lambda key: reverse.get(key, ()), distinct)
    report = EnrichmentReport(
        "CNES", from_field, f"{from_field}→CNES", cardinality="one-to-many per validity window",
        rows_before=table.num_rows,
        registry="unavailable" if getattr(reverse, "registry_unavailable", False) else "available",
    )
    _warn_registry(report)
    indices: list[int] = []
    resolved: list[str | None] = []
    statuses: list[str] = []
    for index, (cnpj, raw, vintage_at) in enumerate(
        zip(source_values, raw_values, vintage_index.to_pylist(), strict=True)
    ):
        candidates, coarse_ambiguity = resolve(_digits(cnpj), vintage_at)
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
