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

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from ..semantics.curation import read_yaml


def roles_file() -> Path:
    from ..config import curation_root

    return curation_root() / "roles.yml"

_FORMATS = {"DDMMYYYY": "%d%m%Y", "YYYYMMDD": "%Y%m%d", "YYYY-MM-DD": "%Y-%m-%d", "YYYYMM": "%Y%m"}
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
    setting: str | None = None   # the municipality role whose state publishes the record


@lru_cache(maxsize=1)
def load_roles() -> dict[str, DatasetRoles]:
    """Every dataset's roles, validated: an unknown type or format is an error."""
    data = read_yaml(roles_file())
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
        setting = body.get("setting")
        if setting is not None and (setting not in roles or roles[setting].type != "municipality"):
            raise ValueError(f"roles.yml: {dataset}: setting {setting!r} is not a municipality role")
        out[str(dataset).upper()] = DatasetRoles(str(dataset).upper(), str(body.get("record", "")), roles,
                                                 str(setting) if setting else None)
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
    source = table.column(role.column)
    if role.type in ("date", "month") and (pa.types.is_date(source.type) or pa.types.is_timestamp(source.type)):
        days = pc.cast(source, pa.date32())     # typed at normalisation (SINAN): nothing to parse
        return pc.cast(pc.floor_temporal(days, unit="month"), pa.date32()) if role.type == "month" else days
    raw = _strings(source)
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
    declarations (roles.yml), the code that reads, renders and normalises the
    rows, and every lake
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
    # A system without series (CIHA) names its families CIHA_CIHA_<sig>: the
    # glob read CIHA_None_* and CIHA's role table was never cached, so every
    # CIHA link labelled 20 million rows again (2026-10-03).
    files = sorted(lake.glob(f"{system}_{series or system}_*/**/*.parquet")) if lake.exists() else []
    if not files:
        return None
    h = hashlib.sha256()
    h.update(f"{dataset}|{period!r}|{geography!r}".encode())
    h.update(roles_file().read_bytes())
    # The code that reads and renders the rows, not only this normaliser: a fix
    # in the lake read (derived inputs, 2026-10-03) must invalidate the tables.
    package = Path(__file__).resolve().parent.parent
    for source in (Path(__file__), package / "api.py", package / "retrieve.py", package / "_request.py",
                   package / "view.py", package / "lookups.py",
                   package / "_query_engine" / "executor.py", package / "_query_engine" / "filters.py"):
        h.update(source.read_bytes())
    for f in files:
        st = f.stat()
        h.update(f"{f.relative_to(lake)}|{st.st_size}|{st.st_mtime_ns}".encode())
    return Path(settings.lake_dir) / "roles" / dataset / f"{_scope_slug(period, geography)}__{h.hexdigest()[:20]}.parquet"


def _scope_slug(period: object, geography: object) -> str:
    def part(v: object) -> str:
        return "-".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)

    return f"{part(period)}_{part(geography)}".replace("/", "-").replace(" ", "")


def _subset(table: pa.Table, names: list[str]) -> pa.Table:
    keep = ["_blob_sha256", "_row", "_source_path", *(["_record_key"] if "_record_key" in table.column_names else []),
            *names]
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

    Only NATIONAL tables of whole years are kept under ``<lake>/roles/``
    (``_national_year``): labelling a national file took 10-20 s and was
    repeated by every link that read it. A multi-year period is the union of
    its years, and a state the rows of the national table that came from that
    state's own publication (``_uf``). Caching every scope separately had
    stored SIH-RD six times over, 2.2 GB (2026-10-04). A scope the cache
    cannot answer exactly (a month, a nation published as one file) is
    computed and not kept.
    """
    from ..config import load_settings

    spec = dataset_roles(dataset)
    names = list(roles or spec.roles)
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    years, ufs = _whole_years(period), _ufs(geography)
    if years and ufs:
        parts = [_national_year(spec, year, settings, query_kwargs) for year in years]
        if all(part is not None for part in parts):
            table = pa.concat_tables([p for p in parts if p is not None], promote_options="default")
            if ufs != ("BR",):
                origin = table.column("_uf")
                if pc.any(pc.equal(origin, "BR")).as_py():
                    table = None  # one national file: its rows do not say which state published them
                else:
                    table = table.filter(pc.is_in(origin, value_set=pa.array(ufs)))
            if table is not None:
                return _subset(table, names)
    full, _strategy = _compute_roles(spec, list(spec.roles), period=period, geography=geography, **query_kwargs)
    return _subset(full, names)


def _whole_years(period: object) -> tuple[int, ...]:
    """The years a period spans when it is whole years, else ()."""
    from .._query_engine.model import _period

    try:
        span = _period(period)
    except Exception:  # noqa: BLE001 - an unusual period is answered uncached
        return ()
    return span.years if span is not None and span.precision == "year" else ()


def _ufs(geography: object) -> tuple[str, ...]:
    values = list(geography) if isinstance(geography, (list, tuple)) else [geography]
    out = tuple(sorted({str(v).strip().upper() for v in values if v is not None}))
    if not out or any(len(v) != 2 or not v.isalpha() for v in out):
        return ()
    return ("BR",) if "BR" in out else out


def _national_year(spec: DatasetRoles, year: int, settings: Any, query_kwargs: dict[str, Any]) -> pa.Table | None:
    """The national role table of one year, from the cache or built and kept.

    None when the lake does not back the whole nation for that year: a "BR"
    table assembled from the few states a lake holds would have been cached
    as the nation (2026-10-04).
    """
    import os

    import pyarrow.parquet as pq

    from .._query_engine.planner import plan

    path = _cache_path(spec.dataset, str(year), "BR", settings)
    if path is None:
        return None
    if path.exists():
        os.utime(path)  # recency for the size cap
        return pq.read_table(path)
    kwargs = {k: v for k, v in query_kwargs.items() if k in ("settings", "root")}
    try:
        backed = plan(spec.dataset, period=str(year), geography="BR", **kwargs).retrieval.source_strategy == "lake"
    except Exception:  # noqa: BLE001 - a scope that cannot be planned is not cached
        return None
    if not backed:
        return None
    full, strategy = _compute_roles(spec, list(spec.roles), period=str(year), geography="BR", **query_kwargs)
    if strategy != "lake":
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    pq.write_table(full, tmp, compression="zstd")
    tmp.replace(path)
    # The same scope under an older key can never be served again (its code
    # or its lake files changed): 4.3 GB of them had piled up.
    # So can a table of any other scope than one national year: the layout
    # before 2026-10-04 kept states and multi-year periods beside the nation.
    prefix = path.name.split("__", 1)[0] + "__"
    for stale in path.parent.glob("*.parquet"):
        national_year = re.fullmatch(r"\d{4}_BR", stale.name.split("__", 1)[0])
        if stale != path and (stale.name.startswith(prefix) or not national_year):
            stale.unlink(missing_ok=True)
    _cap_cache(Path(settings.lake_dir) / "roles", float(getattr(settings, "role_cache_gb", 20.0)), keep=path)
    return full


def _cap_cache(root: Path, limit_gb: float, *, keep: Path) -> None:
    """Delete the least recently used role tables until the cache fits."""
    files = sorted(root.glob("*/*.parquet"), key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    for f in files:
        if total <= limit_gb * 2**30:
            break
        if f != keep:
            total -= f.stat().st_size
            f.unlink(missing_ok=True)


def _state_partitions(dataset: str, geography: object, settings: Any) -> list[str]:
    """The states to build a national role table from, one at a time: the
    lake's per-state partitions of the dataset when it holds no national one.
    Labelling a national SIH year at once held 12.5 million rows and took one
    process past 14 GB (2026-10-03); a state at a time holds one state."""
    from ..retrieve import parse_dataset

    if str(geography).upper() != "BR":
        return []
    try:
        system, series = parse_dataset(dataset)
    except Exception:  # noqa: BLE001 - an unknown dataset is reported by the query itself
        return []
    lake = Path(settings.lake_dir) / system
    ufs = {p.name.split("=", 1)[1] for p in lake.glob(f"{system}_{series or system}_*/*/uf=*") if p.is_dir()}
    return [] if not ufs or "BR" in ufs else sorted(ufs)


def _compute_roles(spec: DatasetRoles, names: list[str], *, period: object, geography: object,
                   **query_kwargs: Any) -> tuple[pa.Table, str]:
    from ..config import load_settings

    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    states = _state_partitions(spec.dataset, geography, settings)
    if not states:
        table, strategy = _compute_roles_one(spec, names, period=period, geography=geography, **query_kwargs)
        # Read from the scope's own publication(s): a state, or one national file.
        origin = geography if isinstance(geography, str) and len(geography) == 2 else "BR"
        return table.append_column("_uf", pa.array([str(origin).upper()] * table.num_rows, pa.string())), strategy
    parts = [_compute_roles_one(spec, names, period=period, geography=uf, **query_kwargs) for uf in states]
    tagged = [t.append_column("_uf", pa.array([uf] * t.num_rows, pa.string())) for (t, _), uf in zip(parts, states, strict=True)]
    table = pa.concat_tables(tagged, promote_options="default")
    absent = set.intersection(*(set(absent_roles(t)) for t, _ in parts))
    meta = dict(parts[0][0].schema.metadata or {})
    meta[b"absent_roles"] = ",".join(sorted(absent)).encode()
    strategy = "lake" if all(s == "lake" for _, s in parts) else "other"
    return table.replace_schema_metadata(meta), strategy


def _carried(dataset: str, columns: set[str], period: object, query_kwargs: dict[str, Any]) -> set[str]:
    """The roles' columns that some year of ``period`` may carry. A role whose column the period lacks is an absent
    role (nulls, named in the table's ``absent_roles``), and one is built from the additional columns present
    (`_normalise`); asking the query for a column every year lacks failed the whole table: SIH-RD's DIAGSEC1-9 before
    2014, SIM-DO's SEMAGESTAC in 2010 (every SIH and SINAN-to-SIM link before 2014, 2026-10-08). A year nothing was
    decoded for keeps the column, and the query decides."""
    from .._availability import availability
    from .._query_engine.model import _period

    found = availability(dataset, root=query_kwargs.get("root"), settings=query_kwargs.get("settings"))
    years = _period(period).years if period is not None else tuple(found.decoded_years)
    return {c for c in columns if (w := found.fields.get(c.upper())) is None or any(w.state(y) != "absent" for y in years)}


def _compute_roles_one(spec: DatasetRoles, names: list[str], *, period: object, geography: object,
                       **query_kwargs: Any) -> tuple[pa.Table, str]:
    """One scope's role table. A period of several years is read year by year, each asking for the columns its own
    files may carry (`_carried`): a padded side reads a year whose generation lacks a column the next one has
    (SINASC 2009 without DTNASCMAE, read by the 2010 infant-death link), and one query for both failed."""
    from .._query_engine.model import _period

    years = _period(period).years if period is not None else ()
    if len(years) > 1:
        parts = [_compute_roles_one(spec, names, period=y, geography=geography, **query_kwargs) for y in years]
        absent = set.intersection(*(set(absent_roles(t)) for t, _ in parts))
        table = pa.concat_tables([t for t, _ in parts], promote_options="default")
        meta = dict(parts[0][0].schema.metadata or {})
        meta[b"absent_roles"] = ",".join(sorted(absent)).encode()
        return table.replace_schema_metadata(meta), ("lake" if all(s == "lake" for _, s in parts) else "other")
    return _compute_roles_year(spec, names, period=period, geography=geography, **query_kwargs)


def _compute_roles_year(spec: DatasetRoles, names: list[str], *, period: object, geography: object,
                        **query_kwargs: Any) -> tuple[pa.Table, str]:
    from .._query_engine.executor import query

    wanted = [spec.roles[name] for name in names]
    # Only the columns the roles read: a national year of SIH-RD is about 12
    # million rows of 113 columns, and linkage needs a dozen of them.
    select = sorted(_carried(spec.dataset, {c for role in wanted for c in (role.column, *role.also)}, period,
                             query_kwargs))
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
    if "_record_key" in table.column_names:
        columns["_record_key"] = pc.cast(table.column("_record_key"), pa.string())
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


__all__ = ["DatasetRoles", "Role", "absent_roles", "dataset_roles", "load_roles", "role_table"]
