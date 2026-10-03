"""Roles: records from any system as comparable properties of entities (ADR-0109).

Linkage never compares columns by name. ``curation/roles.yml`` declares which
column states which property of whom (``mother.birth_date`` is SINASC's
DTNASCMAE and, in a delivery admission, SIH's NASC), and this module turns one
query's records into a table of those properties, normalised through the
project's own meaning:

* dates are parsed with the dataset's declared format;
* sex is read from the decoded label, because every system codes it
  differently (SIH 1/3, SIM and SINASC 1/2, SIA M/F);
* a municipality or facility whose label says "ignorado" is missing, not a
  place;
* anything that does not parse is null. Missing contributes no evidence; it is
  never guessed.

Each row keeps its record identity, ``(_blob_sha256, _row)`` (ADR-0107), and
the file it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from ..semantics.curation import read_yaml

ROLES_FILE = Path(__file__).resolve().parent.parent / "curation" / "roles.yml"
RECORD_ID = ("_blob_sha256", "_row")
_FORMATS = {"DDMMYYYY": "%d%m%Y", "YYYYMMDD": "%Y%m%d", "YYYYMM": "%Y%m"}
_TYPES = {"date", "month", "sex", "municipality", "facility", "integer", "number", "code", "codes", "label"}


@dataclass(frozen=True, slots=True)
class Role:
    name: str          # "mother.birth_date"
    column: str        # "DTNASCMAE"
    type: str          # "date"
    format: str | None = None
    #: label -> canonical category, for `label` roles that name a shared concept
    categories: tuple[tuple[str, str], ...] = ()
    #: further columns a `codes` role gathers (every diagnosis of an admission)
    also: tuple[str, ...] = ()

    @property
    def entity(self) -> str:
        return self.name.split(".", 1)[0]


@dataclass(frozen=True, slots=True)
class DatasetRoles:
    dataset: str
    record: str
    roles: dict[str, Role] = field(default_factory=dict)


@lru_cache(maxsize=1)
def load_roles() -> dict[str, DatasetRoles]:
    """Every dataset's roles, validated: an unknown type or format is an error."""
    data = read_yaml(ROLES_FILE)
    out: dict[str, DatasetRoles] = {}
    for dataset, body in (data.get("datasets") or {}).items():
        roles: dict[str, Role] = {}
        for name, spec in (body.get("roles") or {}).items():
            kind = str(spec["type"])
            if kind not in _TYPES:
                raise ValueError(f"roles.yml: {dataset}.{name}: unknown type {kind!r}")
            fmt = spec.get("format")
            if kind in ("date", "month") and fmt not in _FORMATS:
                raise ValueError(f"roles.yml: {dataset}.{name}: date needs format in {sorted(_FORMATS)}")
            if "." not in name:
                raise ValueError(f"roles.yml: {dataset}.{name}: a role is <entity>.<property>")
            categories = tuple(
                (str(variant).lower(), str(canonical))
                for canonical, variants in (spec.get("categories") or {}).items()
                for variant in variants
            )
            roles[name] = Role(name, str(spec["column"]), kind, fmt, categories,
                               tuple(str(c) for c in spec.get("also") or ()))
        out[str(dataset).upper()] = DatasetRoles(str(dataset).upper(), str(body.get("record", "")), roles)
    return out


def dataset_roles(dataset: str) -> DatasetRoles:
    try:
        return load_roles()[dataset.upper()]
    except KeyError:
        raise KeyError(f"no roles declared for {dataset!r}; declared: {sorted(load_roles())}") from None


def _strings(column: pa.ChunkedArray | pa.Array) -> pa.Array:
    values = pc.utf8_trim_whitespace(pc.cast(column, pa.string()))
    return pc.if_else(pc.equal(values, ""), pa.scalar(None, pa.string()), values)


def _ignored(labels: pa.Array | None) -> pa.Array | None:
    if labels is None:
        return None
    return pc.fill_null(pc.match_substring_regex(pc.utf8_lower(_strings(labels)), r"ignorad"), False)


def _normalise(role: Role, table: pa.Table) -> pa.Array:
    raw = _strings(table.column(role.column))
    label_name = f"{role.column}_label"
    labels = table.column(label_name) if label_name in table.column_names else None
    if role.type == "month":
        raw = pc.if_else(pc.equal(pc.utf8_length(raw), 6), pc.binary_join_element_wise(raw, "01", ""), raw)
        parsed = pc.strptime(raw, format="%Y%m%d", unit="s", error_is_null=True)
        return pc.cast(parsed, pa.date32())
    if role.type == "date":
        parsed = pc.strptime(raw, format=_FORMATS[role.format or ""], unit="s", error_is_null=True)
        return pc.cast(parsed, pa.date32())
    if role.type == "sex":
        if labels is None:
            source = pc.utf8_lower(raw)
        else:
            source = pc.utf8_lower(_strings(labels))
        male = pc.starts_with(source, "m")
        female = pc.starts_with(source, "f")
        return pc.if_else(male, "M", pc.if_else(female, "F", pa.scalar(None, pa.string())))
    if role.type in ("municipality", "facility"):
        width = 6 if role.type == "municipality" else 7
        valid = pc.and_(pc.utf8_is_digit(raw), pc.equal(pc.utf8_length(raw), width))
        ignored = _ignored(labels)
        if ignored is not None:
            valid = pc.and_(valid, pc.invert(ignored))
        return pc.if_else(valid, raw, pa.scalar(None, pa.string()))
    if role.type == "integer":
        digits = pc.utf8_is_digit(raw)
        return pc.if_else(digits, pc.cast(pc.if_else(digits, raw, "0"), pa.int64()), pa.scalar(None, pa.int64()))
    if role.type == "number":
        return pc.cast(table.column(role.column), pa.float64(), safe=False)
    if role.type == "label":
        text = pc.utf8_lower(_strings(labels) if labels is not None else raw)
        if not role.categories:
            return text
        variants = pa.array([v for v, _ in role.categories], pa.string())
        canonical = pa.array([c for _, c in role.categories], pa.string())
        return pc.take(canonical, pc.index_in(text, value_set=variants))
    if role.type == "codes":
        # Every code the record carries, space-separated: the diagnoses of an
        # admission are one piece of evidence wherever they were written.
        parts = [raw] + [_strings(table.column(c)) for c in role.also if c in table.column_names]
        parts = [pc.fill_null(p, "") for p in parts]
        joined = pc.utf8_trim_whitespace(pc.binary_join_element_wise(*parts, " "))
        return pc.if_else(pc.equal(joined, ""), pa.scalar(None, pa.string()), joined)
    return raw  # code


def _cache_path(dataset: str, period: object, geography: object, settings: Any) -> Path | None:
    """Where a dataset-scope's role table is kept, or None when no lake backs it.

    The key fingerprints everything the table depends on: the scope, the role
    declarations (roles.yml), this module's normalisation code, and every lake
    partition file of the dataset (path, size, mtime). A rebuilt partition, an
    edited role or a changed normaliser is a different key, so a stale table is
    never served (docs/plans/linkage-theory.md §7, step T1).
    """
    import hashlib

    from ..retrieve import parse_dataset

    try:
        system, series = parse_dataset(dataset)
    except Exception:  # noqa: BLE001 - an unknown dataset is reported by the query itself
        return None
    lake = Path(settings.lake_dir) / system
    files = sorted(lake.glob(f"{system}_{series}_*/**/*.parquet")) if lake.exists() else []
    if not files:
        return None
    h = hashlib.sha256()
    h.update(f"{dataset}|{period!r}|{geography!r}".encode())
    h.update(ROLES_FILE.read_bytes())
    h.update(Path(__file__).read_bytes())
    for f in files:
        st = f.stat()
        h.update(f"{f.relative_to(lake)}|{st.st_size}|{st.st_mtime_ns}".encode())
    return Path(settings.lake_dir) / "roles" / dataset / f"{h.hexdigest()[:20]}.parquet"


def _subset(table: pa.Table, names: list[str]) -> pa.Table:
    keep = ["_blob_sha256", "_row", "_source_path", *names]
    absent = [r for r in absent_roles(table) if r in names]
    meta = dict(table.schema.metadata or {})
    meta[b"absent_roles"] = ",".join(absent).encode()
    return table.select(keep).replace_schema_metadata(meta)


def role_table(
    dataset: str,
    *,
    period: object,
    geography: object,
    roles: list[str] | None = None,
    **query_kwargs: Any,
) -> pa.Table:
    """One query's records as normalised role columns, with record identity.

    Roles whose column this scope does not carry come back null and are named
    in the table's metadata (``absent_roles``), so a caller that needs one can
    refuse rather than link on nothing.

    Where the lake fully backs the scope, every role of the dataset is computed
    once and kept under ``<lake>/roles/`` (``_cache_path``): labelling a
    national file took 10-20 s and was repeated by every link that read it.
    """
    import pyarrow.parquet as pq

    from ..config import load_settings

    spec = dataset_roles(dataset)
    names = list(roles or spec.roles)
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    path = _cache_path(dataset, period, geography, settings)
    if path is not None and path.exists():
        return _subset(pq.read_table(path), names)
    full, strategy = _compute_roles(spec, list(spec.roles), period=period, geography=geography, **query_kwargs)
    if path is not None and strategy == "lake":
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        pq.write_table(full, tmp, compression="zstd")
        tmp.replace(path)
    return _subset(full, names)


def _compute_roles(spec: DatasetRoles, names: list[str], *, period: object, geography: object,
                   **query_kwargs: Any) -> tuple[pa.Table, str]:
    from .._query_engine.executor import query

    wanted = [spec.roles[name] for name in names]
    # Only the columns the roles read: a national year of SIH-RD is about 12
    # million rows of 113 columns, and linkage needs a dozen of them.
    select = sorted({col for role in wanted for col in (role.column, *role.also)})
    table, report = query(
        spec.dataset, period=period, geography=geography, select=select, present="analysis",
        provenance="all", return_report=True, **query_kwargs,
    )
    table = table.combine_chunks() if table.num_rows else table
    columns: dict[str, pa.Array] = {
        "_blob_sha256": pc.cast(table.column("_blob_sha256"), pa.string()),
        "_row": table.column("_row"),
        "_source_path": pc.cast(table.column("_source_path"), pa.string()),
    }
    absent: list[str] = []
    for role in wanted:
        if role.column not in table.column_names:
            absent.append(role.name)
            columns[role.name] = pa.nulls(table.num_rows)
            continue
        columns[role.name] = _normalise(role, table)
    out = pa.table(columns)
    meta = {b"dataset": spec.dataset.encode(), b"record": spec.record.encode(),
            b"absent_roles": ",".join(absent).encode()}
    complete = getattr(report, "source_strategy", "") == "lake"
    return out.replace_schema_metadata(meta), ("lake" if complete else "other")


def absent_roles(table: pa.Table) -> list[str]:
    raw = (table.schema.metadata or {}).get(b"absent_roles", b"").decode()
    return [r for r in raw.split(",") if r]


__all__ = ["RECORD_ID", "DatasetRoles", "Role", "absent_roles", "dataset_roles", "load_roles", "role_table"]
