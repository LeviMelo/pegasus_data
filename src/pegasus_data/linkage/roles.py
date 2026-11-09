"""Roles: records from any system as comparable properties of entities (ADR-0109).

Linkage never compares columns by name. A dataset's roles file (``curation/roles/<dataset>.yml``, the one
declaration of its columns) says which column states which property of whom (``mother.birth_date`` is SINASC's
DTNASCMAE and, in a delivery admission, SIH's NASC); a column linkage compares carries ``compare:``, how each of its
roles is normalised before comparison, and the file's ``setting:`` names the municipality role whose state publishes a
record (DATASUS files SIM and SINASC by residence, SIH and CIHA by the hospital's municipality; error channels are
estimated per setting, ADR-0123). This module turns one query's records into a table of those properties, normalised
through the project's own meaning. A ``compare`` type is one of:

* ``date`` (a calendar date, with ``format`` DDMMYYYY, YYYYMMDD or YYYY-MM-DD), ``month`` (``format`` YYYYMM, its first
  day), ``year``, or ``birth_from_age`` (the birth date an age in ``column`` and the one ``also`` reference date fix);
* ``sex``: M or F from the column's decoded label, because every system codes it
  differently (SIH 1/3, SIM and SINASC 1/2, SIA M/F);
* ``municipality`` (6-digit IBGE code) or ``facility`` (7-digit CNES): one whose label says "ignorado" is missing,
  not a place;
* ``integer``/``number`` (a count or measure), ``code`` (compared exactly), ``codes`` (every code of ``column`` and
  the ``also`` columns: all of an admission's diagnoses);
* ``label``: the decoded label, lower-cased; with ``categories`` (canonical -> each system's spellings) the canonical
  category, a label outside the map missing (SIM writes "cesáreo", SINASC "cesário": compared as text they
  disagreed in 54% of linked pairs);
* anything that does not parse is null. Missing contributes no evidence; it is
  never guessed.

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

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from ..semantics.categories import canonical_sex
from ..semantics.curation import read_yaml
from ..semantics.epoch import curated


def roles_files() -> list[Path]:
    """The datasets' roles files (`curation/roles/*.yml`); those with a ``compare:`` column are linkable."""
    from ..config import curation_root

    return sorted((curation_root() / "roles").glob("*.yml"))

_FORMATS = {"DDMMYYYY": "%d%m%Y", "YYYYMMDD": "%Y%m%d", "YYYY-MM-DD": "%Y-%m-%d", "YYYYMM": "%Y%m"}
_TYPES = {"date", "month", "year", "birth_from_age", "sex", "municipality", "facility", "integer", "number", "code",
          "codes", "label"}


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


@curated
def load_roles() -> dict[str, DatasetRoles]:
    """Every linkable dataset's roles, read from its roles file's ``compare:`` columns and validated: an unknown type
    or format is an error."""
    out: dict[str, DatasetRoles] = {}
    for path in roles_files():
        doc = read_yaml(path, shared=True) or {}
        dataset = str(doc.get("dataset") or path.stem)
        specs = {str(name): {**dict(spec), "column": str(column)}
                 for column, body in (doc.get("columns") or {}).items() if isinstance(body, dict)
                 for name, spec in (body.get("compare") or {}).items()}
        if not specs:
            continue
        body = doc
        roles: dict[str, Role] = {}
        for name, spec in specs.items():
            kind = str(spec["type"])
            if kind not in _TYPES:
                raise ValueError(f"roles/{dataset}.yml: {dataset}.{name}: unknown type {kind!r}")
            fmt = spec.get("format")
            if kind in ("date", "month", "year", "birth_from_age") and fmt not in _FORMATS:
                raise ValueError(f"roles/{dataset}.yml: {dataset}.{name}: date needs format in {sorted(_FORMATS)}")
            if kind == "birth_from_age" and len(spec.get("also") or ()) != 1:
                raise ValueError(f"roles/{dataset}.yml: {dataset}.{name}: birth_from_age reads the age in `column` and "
                                 "the reference date in the one `also` column")
            if "." not in name:
                raise ValueError(f"roles/{dataset}.yml: {dataset}.{name}: a role is <entity>.<property>")
            categories = tuple(
                (str(variant).lower(), str(canonical))
                for canonical, variants in (spec.get("categories") or {}).items()
                for variant in variants
            )
            roles[name] = Role(name, str(spec["column"]), kind, fmt, categories,
                               tuple(str(c) for c in spec.get("also") or ()))
        setting = body.get("setting")
        if setting is not None and (setting not in roles or roles[setting].type != "municipality"):
            raise ValueError(f"roles/{dataset}.yml: {dataset}: setting {setting!r} is not a municipality role")
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


def _as_date(source: pa.Array | pa.ChunkedArray, fmt: str | None) -> pa.Array:
    """A date column as dates: typed already (SINAN) or parsed with the declared format."""
    if pa.types.is_date(source.type) or pa.types.is_timestamp(source.type):
        return pc.cast(source, pa.date32())
    parsed = pc.strptime(_strings(source), format=_FORMATS[fmt or ""], unit="s", error_is_null=True)
    return pc.cast(parsed, pa.date32())


def _birth_from_age(age: pa.Array | pa.ChunkedArray, reference: pa.Array) -> pa.Array:
    """The birth date of a child whose age was coded in days (SINAN's NU_IDADE_N: 2 and the number of days) at the
    reference date; null for any other unit, where the age fixes no day. SINAN carries no birth date since the LGPD
    rewrite but its age was computed from one: in congenital toxoplasmosis, with the date of first symptoms or
    diagnosis as reference (docs/evaluation/2026-10-10-links-toxoplasmosis.md)."""
    text = _strings(age)
    digits = pc.and_(pc.utf8_is_digit(text), pc.equal(pc.utf8_length(text), 4))
    in_days = pc.fill_null(pc.and_(digits, pc.starts_with(text, "2")), False)
    count = pc.cast(pc.if_else(in_days, pc.utf8_slice_codeunits(text, 1), "0"), pa.int32())
    back = pc.subtract(pc.cast(reference, pa.int32()), count)
    return pc.if_else(in_days, pc.cast(back, pa.date32()), pa.scalar(None, pa.date32()))


#: the role types whose normalisation reads the column's label (`_normalise`)
_READS_LABELS = frozenset({"sex", "municipality", "facility", "label"})


def _normalise(role: Role, table: pa.Table) -> pa.Array:
    source = table.column(role.column)
    if role.type == "birth_from_age":
        return _birth_from_age(source, _as_date(table.column(role.also[0]), role.format))
    if role.type == "year":
        return pc.cast(pc.year(_as_date(source, role.format)), pa.int64())
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
        return canonical_sex(raw if labels is None else labels)      # the whole label, as curation/categories.yml spells it
    if role.type in ("municipality", "facility"):
        width = 6 if role.type == "municipality" else 7
        valid = pc.and_(pc.utf8_is_digit(raw), pc.equal(pc.utf8_length(raw), width))
        ignored = _ignored(labels)
        if ignored is not None:
            valid = pc.and_(valid, pc.invert(ignored))
        place = pc.if_else(valid, raw, pa.scalar(None, pa.string()))
        if role.type == "municipality":
            # The Federal District has one municipality, Brasília (530010). SIH-RD writes its residents'
            # administrative-region codes (530020 ... 530180) up to 2017-12 (2017: 140,876 of 151,901 DF rows,
            # DATA_SOURCES), so a residence key could never pair a DF resident with SIM or SINASC (530010). Any 53xxxx
            # is Brasília, as the recipe `MUNIC_RES_municipio` and pegasus_core's `_residence_sql` have it.
            place = pc.if_else(pc.starts_with(place, "53"), pa.scalar("530010"), place)
        return place
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


#: Bumped when `_normalise`, `_compute_roles_year` or the reading and labelling of the rows they use changes what a
#: role table holds. A cached table's key (`table_key`) is this, the dataset's own role definitions, the codelists
#: its labelled columns can be labelled with and that dataset-year's lake partition files: not the text of seven source
#: files and every partition of every year, which made any commit to them, or one new month of another year, discard
#: all 48 cached national tables (2026-10-14), and not the shipped label pack as a whole, which made the re-windowing
#: of CIH's labels (a dataset no link reads) discard every stored 2022 run (2026-10-23).
ROLE_TABLE_VERSION = 1


def _labelled_columns(wanted: Iterable[Role]) -> set[str]:
    """The columns a role table is rendered with labels for: those of the roles whose normalisation reads the label
    (`_READS_LABELS`: a sex, a place, a facility, a category). Every other role is read as filed
    (`_compute_roles_year`), so no label can reach it."""
    return {c for role in wanted if role.type in _READS_LABELS for c in (role.column, *role.also)}


def label_tables(dataset: str, families: Sequence[str], settings: Any) -> frozenset[str] | None:
    """The codelists the labelled columns of ``dataset``'s roles can be labelled with in these lake families
    (`label_bindings.label_candidates`: the tables the renderer's ladder can return for them, upper case); None when
    the data home has no catalog to say, and a reader then has to take the label pack whole. Memoised by the catalog
    file's size and time and the curation's digest (a long-lived process sees a catalog written since only when SQLite
    checkpoints it), so asking for every year of a run costs one answer."""
    from ..semantics.epoch import curation_epoch

    path = Path(settings.catalog_path)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _label_tables(dataset.upper(), tuple(families), str(path), (stat.st_size, stat.st_mtime_ns),
                         curation_epoch()[1])


@lru_cache(maxsize=256)
def _label_tables(dataset: str, families: tuple[str, ...], catalog: str, identity: tuple[int, int],
                  curation: str) -> frozenset[str] | None:
    import sqlite3

    from .._request import parse_dataset
    from ..catalog.store import CatalogStore
    from ..semantics.label_bindings import label_candidates

    del identity, curation                        # the memo's key: which catalog and curation this answer is about
    fields = sorted(_labelled_columns(dataset_roles(dataset).roles.values()))
    if not fields:
        return frozenset()
    system, series = parse_dataset(dataset)
    store = CatalogStore.shared(catalog)
    try:
        return label_candidates(store, system, series or "", families, fields)
    except sqlite3.OperationalError as exc:       # a catalog older than the tables the ladder reads: none to name them
        if "no such table" not in str(exc) and "no such column" not in str(exc):
            raise                                 # a busy catalog is not "no catalog": a key must not depend on a lock
        return None
    finally:
        store.close()


def label_inputs(dataset: str, files: Sequence[Path], lake: Path, settings: Any) -> str:
    """What the labels contribute to a role table's key: for each codelist its labelled columns can be labelled with
    in the families of ``files`` (`label_tables`), the codelist's name and a digest of what it is read from for the
    dataset's system (`persist.reference.reference_fingerprint`: the pack's rows of this system and the shared ones,
    in every validity window, or the curated table, or the canonical file). The whole pack's digest when there is no
    catalog to name the codelists."""
    from .._request import parse_dataset
    from ..persist.reference import reference_fingerprint, resource_digest

    families = tuple(sorted({f.relative_to(lake).parts[0] for f in files}))
    names = label_tables(dataset, families, settings)
    if names is None:
        return f"labels|whole pack|{resource_digest('labels.parquet')}|"
    system = parse_dataset(dataset)[0]
    return "".join(f"label|{name}|{reference_fingerprint(settings.lake_dir, name, system)}|" for name in sorted(names))


def partition_files(dataset: str, year: int, settings: Any) -> tuple[Path, list[Path]]:
    """The lake's published partition files of a dataset's year: (the system's directory, the files). A write in
    progress stages under a hidden directory the pattern does not match."""
    from ..retrieve import parse_dataset

    system, series = parse_dataset(dataset)
    lake = Path(settings.lake_dir) / system
    files = sorted(lake.glob(f"{system}_{series or system}_*/**/year={year}/*.parquet")) if lake.exists() else []
    return lake, files


def table_key(dataset: str, year: int, settings: Any) -> str | None:
    """Fingerprint of one dataset-year's role table, or None when no lake partition backs it. Also what a stored link
    run records for the years it read (`store.fingerprint`): a run is current while its inputs' keys are.

    A record's identity is a hash of its normalised fields, so whatever changes what the table holds makes every id
    stored against it match nothing. Exactly that is in the key, and nothing a table is not computed from:

    * ``ROLE_TABLE_VERSION``, the dataset, the year;
    * the dataset's record kind and roles (every role: the table holds them all, and its columns follow their order);
    * the lake partition files of the year (relative path, size, time);
    * for the codelists the labelled columns can be labelled with (`label_inputs`): the rows they are read from, for
      this dataset's system, in every window.

    The labels once were the whole shipped pack (and three other resource files), so a change to any codelist of any
    system, CIH's re-windowing on 2026-10-23 among them, made every role table and every stored run stale, each costing
    8 to 12 minutes and up to 11 GB to make again. What a role table reads of them is the label of a sex, a place, a
    facility or a category (`_labelled_columns`; the other roles are read as filed, a derived age from the raw
    columns): 1 to 11 columns of a dataset, which name 2 (SIM-DOFET) to 22 codelists (SIM-DO) in a year, the sex and
    municipality tables of the system and the curated tables of its form dictionary (docs/evaluation/
    2026-10-24-link-keys-by-what-they-read.md). Of the four resource files once hashed, a build opens ``labels.parquet``
    only; ``labels_crosswalk.parquet`` and ``code_lists.parquet`` are read by enrichments and code structures, which a
    role table does not ask for, and ``municipalities.parquet`` is in the key when a labelled column is bound to UF_BR
    or MUNIC_BR7. The dataset's ``setting`` (the municipality role whose state publishes a record) is not here: no table
    holds it, and a stored run takes it into its fingerprint (`store._fingerprint_of`).

    A role table is never built from a codelist this key does not name: `_check_labels_named` compares what the render
    labelled the columns with against the names and refuses the build. A CNES registry is read from the data home, is
    not shipped, and was never in the key; `persist.reference.reference_fingerprint` says why that is exact."""
    import hashlib

    try:
        lake, files = partition_files(dataset, year, settings)
    except Exception:  # noqa: BLE001 - an unknown dataset is reported by the query itself
        return None
    if not files:
        return None
    spec = dataset_roles(dataset)
    h = hashlib.sha256(f"{ROLE_TABLE_VERSION}|{dataset.upper()}|{year}|".encode())
    # in the roles' name order: where they are declared (a column's `compare:`) does not change the table
    h.update(repr((spec.record, sorted(spec.roles.items()))).encode())
    h.update(label_inputs(dataset, files, lake, settings).encode())
    for f in files:
        st = f.stat()
        h.update(f"{f.relative_to(lake)}|{st.st_size}|{st.st_mtime_ns}".encode())
    return h.hexdigest()[:20]


def _cache_path(dataset: str, year: int, settings: Any) -> Path | None:
    """Where a dataset's national role table of one year is kept, or None when no lake backs it."""
    key = table_key(dataset, year, settings)
    return None if key is None else Path(settings.lake_dir) / "roles" / dataset / f"{year}_BR__{key}.parquet"


def _subset(table: pa.Table, names: list[str]) -> pa.Table:
    keep = ["_blob_sha256", "_row", "_source_path", *(["_record_key"] if "_record_key" in table.column_names else []),
            *names]
    absent = [r for r in absent_roles(table) if r in names]
    meta = dict(table.schema.metadata or {})
    meta[b"absent_roles"] = ",".join(absent).encode()
    return table.select(keep).replace_schema_metadata(meta)


def _where_roles(spec: DatasetRoles, where: str | None) -> list[str]:
    return [r for r in spec.roles if where and f'"{r}"' in where]


def _filtered(table: pa.Table, where: str | None) -> pa.Table:
    """``table`` kept where the SQL condition over its role columns holds (the schema's metadata kept)."""
    if not where:
        return table
    from .identity import connect

    con = connect()
    con.register("t", table)
    out = con.execute(f"SELECT * FROM t WHERE {where}").to_arrow_table()
    return out.replace_schema_metadata(table.schema.metadata)


def _read_cached(path: Path, columns: list[str], ufs: tuple[str, ...], where: str | None) -> pa.Table | None:
    """The projected, filtered rows of a cached national year. DuckDB pushes the projection, the state predicate
    (the table is clustered by ``_uf``: one state is a row group in twelve) and the side's filter into the read; the
    whole table read in full took 3.5 GiB and 2 s for a state of 0.1 s and 30 MiB (2026-10-14). None when the table
    came from one national file whose rows do not say which state published them."""
    import pyarrow.parquet as pq

    from .identity import connect

    con = connect()
    source = f"read_parquet('{path.as_posix()}')"
    schema = pq.read_schema(path)
    conds = [f"({where})"] if where else []
    if ufs != ("BR",):
        if con.execute(f"SELECT count(*) FROM {source} WHERE _uf = 'BR'").fetchone()[0]:  # type: ignore[index]
            return None
        conds.append("_uf IN (" + ", ".join("'" + u + "'" for u in ufs) + ")")
    have = set(schema.names)
    select = ", ".join(f'"{c}"' for c in columns if c in have)
    sql = f"SELECT {select} FROM {source}" + (f" WHERE {' AND '.join(conds)}" if conds else "")
    return con.execute(sql).to_arrow_table().replace_schema_metadata(schema.metadata)


def role_table(
    dataset: str,
    *,
    period: object,
    geography: object,
    roles: list[str] | None = None,
    where: str | None = None,
    **query_kwargs: Any,
) -> pa.Table:
    """One query's records as normalised role columns, with record identity.

    Roles whose column this scope does not carry come back null and are named
    in the table's metadata (``absent_roles``), so a caller that needs one can
    refuse rather than link on nothing. ``where`` (SQL over the role names, as a link side's filter) keeps the
    matching records, applied where each year is read.

    Only NATIONAL tables of whole years are kept under ``<lake>/roles/``
    (``_national_year``): labelling a national file took 10-20 s and was
    repeated by every link that read it. A multi-year period is the union of
    its years, and a state the rows of the national table that came from that
    state's own publication (``_uf``). A year is read projected to the roles asked and filtered to the state, never
    whole. A state whose national year is not cached is computed for the roles asked, not by building the nation
    (53 s) to keep 1/27 of it. A scope the cache cannot answer exactly (a month, a nation published as one file) is
    computed and not kept.
    """
    from ..config import load_settings

    spec = dataset_roles(dataset)
    names = list(roles or spec.roles)
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    needed = list(dict.fromkeys([*names, *_where_roles(spec, where)]))
    provenance = ["_blob_sha256", "_row", "_source_path", "_record_key"]
    years, ufs = _whole_years(period), _ufs(geography)
    if years and ufs:
        parts: list[pa.Table] = []
        for year in years:
            part = _national_year(spec, year, ufs, geography, [*provenance, *needed], where, settings, query_kwargs)
            if part is None:
                parts = []
                break
            parts.append(part)
        if parts:
            return _subset(_stack(parts), names)
    full, _strategy = _compute_roles(spec, needed, period=period, geography=geography, **query_kwargs)
    return _subset(_filtered(full, where), names)


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


def _national_year(spec: DatasetRoles, year: int, ufs: tuple[str, ...], geography: object, columns: list[str],
                   where: str | None, settings: Any, query_kwargs: dict[str, Any]) -> pa.Table | None:
    """One year's role table for ``ufs``, projected to ``columns`` and filtered, from the national cache, or built.

    The nation is built (and kept) only for a national call, and only when the lake backs the whole nation for that
    year: a "BR" table assembled from the few states a lake holds would have been cached as the nation (2026-10-04).
    A state call whose national table is not cached computes that state for the roles asked and keeps nothing.
    None when the year cannot be answered from the cache (the caller computes the scope).
    """
    import os

    import pyarrow.parquet as pq

    from .._query_engine.planner import plan

    path = _cache_path(spec.dataset, year, settings)
    if path is None:
        return None
    if path.exists():
        os.utime(path)  # recency for the size cap
        return _read_cached(path, columns, ufs, where)
    if ufs != ("BR",):
        roles = [c for c in columns if c in spec.roles]
        table, _strategy = _compute_roles(spec, roles, period=str(year), geography=geography, **query_kwargs)
        return _filtered(table, where)
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
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")   # one name per process: two studies building one year
    pq.write_table(full, tmp, compression="zstd")            # interleaved on a shared name (2026-10-14 review)
    tmp.replace(path)
    # The same year under an older key can never be served again (its lake files or roles changed): 4.3 GB of them
    # had piled up. A table of any other scope than one national year can neither (the layout before 2026-10-04
    # kept states and multi-year periods beside the nation).
    prefix = path.name.split("__", 1)[0] + "__"
    for stale in path.parent.glob("*.parquet"):
        national_year = re.fullmatch(r"\d{4}_BR", stale.name.split("__", 1)[0])
        if stale != path and (stale.name.startswith(prefix) or not national_year):
            stale.unlink(missing_ok=True)
    _cap_cache(Path(settings.lake_dir) / "roles", float(getattr(settings, "role_cache_gb", 20.0)), keep=path)
    kept = full.select([c for c in columns if c in full.column_names]).replace_schema_metadata(full.schema.metadata)
    return _filtered(kept, where)


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


def _stack(tables: list[pa.Table]) -> pa.Table:
    """Role tables of one dataset (years, state partitions) as one table. A role is absent when it is absent from every
    part; ``role_gaps`` keeps what each year lacked."""
    if len(tables) == 1:
        return tables[0]
    absent = set.intersection(*(set(absent_roles(t)) for t in tables))
    meta = {**(tables[0].schema.metadata or {}), b"absent_roles": ",".join(sorted(absent)).encode(),
            b"role_gaps": merged_gaps(tables)}
    return pa.concat_tables(tables, promote_options="default").replace_schema_metadata(meta)


def _compute_roles(spec: DatasetRoles, names: list[str], *, period: object, geography: object,
                   **query_kwargs: Any) -> tuple[pa.Table, str]:
    """One scope's role table, computed by the query engine, one query per state partition and per year. A nation the
    lake holds by state is labelled a state at a time (a national SIH year at once held 12.5 million rows and took one
    process past 14 GB, 2026-10-03); a period of whole years is read year by year, each asking for the columns its own
    files may carry (`_carried`: a padded side reads a year whose generation lacks a column the next one has, SINASC
    2009 without DTNASCMAE, and one query for both failed). Rows carry ``_uf``, the state whose publication they came
    from, or "BR" for a national file. The strategy is "lake" when every query was answered from the lake."""
    from ..config import load_settings

    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    years = _whole_years(period)
    parts: list[pa.Table] = []
    strategies: list[str] = []
    for unit in _state_partitions(spec.dataset, geography, settings) or [geography]:
        origin = unit.upper() if isinstance(unit, str) and len(unit) == 2 else "BR"
        for scope in years if len(years) > 1 else (period,):
            table, strategy = _compute_roles_year(spec, names, period=scope, geography=unit, **query_kwargs)
            parts.append(table.append_column("_uf", pa.array([origin] * table.num_rows, pa.string())))
            strategies.append(strategy)
    return _stack(parts), ("lake" if all(s == "lake" for s in strategies) else "other")


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


def _compute_roles_year(spec: DatasetRoles, names: list[str], *, period: object, geography: object,
                        **query_kwargs: Any) -> tuple[pa.Table, str]:
    from .._query_engine.executor import query

    wanted = [spec.roles[name] for name in names]
    # Only the columns the roles read: a national year of SIH-RD is about 12
    # million rows of 113 columns, and linkage needs a dozen of them.
    select = sorted(_carried(spec.dataset, {c for role in wanted for c in (role.column, *role.also)}, period,
                             query_kwargs))
    # labels only where a role reads them (`_normalise`: sex, places, facilities, label roles); a code read as filed
    labelled = _labelled_columns(wanted)
    table, report = query(
        spec.dataset, period=period, geography=geography, select=select, present="analysis",
        provenance="all", return_report=True, render={c: "code" for c in select if c not in labelled}, **query_kwargs,
    )
    _check_labels_named(spec.dataset, labelled, report, period, query_kwargs)
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
    # what this year lacked, by role: a column the year's files do not carry (the role is null), or an `also` column of a
    # `codes` role (SIH's DIAGSEC1-9 before 2014: the role is built from the columns present, so the cohorts it selects
    # differ by year). A table of several years lists only the roles absent in all of them in `absent_roles`.
    gaps = {str(period): {"absent": absent, "degraded": {
        r.name: miss for r in wanted if r.name not in absent and (miss := [c for c in r.also if c not in table.column_names])}}}
    meta = {b"dataset": spec.dataset.encode(), b"record": spec.record.encode(),
            b"absent_roles": ",".join(absent).encode(), b"role_gaps": json.dumps(gaps).encode()}
    complete = getattr(report, "source_strategy", "") == "lake"
    return out.replace_schema_metadata(meta), ("lake" if complete else "other")


def _check_labels_named(dataset: str, labelled: set[str], report: Any, period: object,
                        query_kwargs: dict[str, Any]) -> None:
    """Refuse a role table labelled from a codelist its key does not name (`table_key`, `label_tables`).

    The key names the codelists the renderer's ladder can return for the labelled columns, from the catalog and the
    curation (`label_bindings.label_candidates`); the render says which it did return (``codelist_used``). Were a rung
    of the ladder missing from the first, a table would be cached, and stored link runs left current, whose labels a
    change to that codelist then alters: the silent stale state the key exists to prevent. This turns it into an error
    at the first build, naming the column and the codelist, and no table is kept."""
    from .._query_engine.model import _period
    from ..config import load_settings

    used = _codelists_used(report, labelled)
    if not used:
        return
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    try:
        years = _period(period).years if period is not None else ()
    except Exception:  # noqa: BLE001 - an unusual period is answered, and not cached
        return
    named: set[str] = set()
    keyed = False                           # a year of the period has a key (a lake partition backs it)
    for year in years:
        try:
            lake, files = partition_files(dataset, year, settings)
        except Exception:  # noqa: BLE001 - an unknown dataset is reported by the query itself
            continue
        if files:
            names = label_tables(dataset, tuple(sorted({f.relative_to(lake).parts[0] for f in files})), settings)
            if names is None:
                return                      # no catalog to name them: the whole pack is in the key
            named |= names
            keyed = True
    outside = {column: sorted(tokens - named) for column, tokens in used.items() if keyed and tokens - named}
    if outside:
        raise RuntimeError(
            f"{dataset}: labelled role columns were labelled from codelists the role table's key does not name: "
            + "; ".join(f"{column} from {', '.join(tokens)}" for column, tokens in sorted(outside.items()))
            + ". `label_bindings.label_candidates` lacks a source of names the labelling ladder (`decide`) draws on; "
            "add it there, or a change to those codelists would leave stored link runs current.")


def _codelists_used(report: Any, labelled: set[str]) -> dict[str, set[str]]:
    """``column -> codelists (upper case)`` the render of a query labelled the ``labelled`` columns with. A column
    named through another column of the row (``table.field via column``) uses no codelist of its own."""
    wanted = {c.upper() for c in labelled}
    sources = getattr(report, "source_report", None)
    out: dict[str, set[str]] = {}
    for source in sources if isinstance(sources, (list, tuple)) else [sources]:
        used = getattr(source, "codelist_used", None) or getattr(getattr(source, "render", None), "codelist_used", None)
        for column, text in (used or {}).items():
            if str(column).upper() not in wanted:
                continue
            for token in re.split(r"[+,]", str(text)):
                token = token.strip().upper()
                if token and " VIA " not in token and not token.startswith("COLUMN "):
                    out.setdefault(str(column).upper(), set()).add(token)
    return out


def absent_roles(table: pa.Table) -> list[str]:
    raw = (table.schema.metadata or {}).get(b"absent_roles", b"").decode()
    return [r for r in raw.split(",") if r]


def role_gaps(table: pa.Table) -> dict[str, dict[str, Any]]:
    """Per year, the roles the table's files lacked and the `codes` roles built from fewer columns than declared."""
    raw = (table.schema.metadata or {}).get(b"role_gaps", b"")
    return json.loads(raw) if raw else {}


def merged_gaps(tables: list[pa.Table]) -> bytes:
    """The ``role_gaps`` of several tables of one dataset as one metadata value (years' entries joined, a year's roles
    united)."""
    out: dict[str, dict[str, Any]] = {}
    for t in tables:
        for year, gap in role_gaps(t).items():
            have = out.setdefault(year, {"absent": [], "degraded": {}})
            have["absent"] = sorted(set(have["absent"]) | set(gap.get("absent", [])))
            for role, cols in gap.get("degraded", {}).items():
                have["degraded"][role] = sorted(set(have["degraded"].get(role, [])) | set(cols))
    return json.dumps(out).encode()


def why_unusable(left_bad: dict[str, str], right_bad: dict[str, str], lefts: Any, rights: Any) -> str:
    """Why a key over the roles ``lefts`` (left side) and ``rights`` (right side) cannot be used: each role in the
    `unusable_roles` of its side, with the reason; "" when the key can run."""
    return "; ".join([f"{r} {left_bad[r]}" for r in lefts if r in left_bad]
                     + [f"{r} {right_bad[r]}" for r in rights if r in right_bad])


def unusable_roles(table: pa.Table, names: list[str]) -> dict[str, str]:
    """Of the roles ``names``, those a link cannot use on this table: ``absent`` (no file of the scope carries the
    column) or ``all null`` (the column is there but no value normalised: a municipality or facility whose codes are
    not exactly 6 or 7 digits, a date in another format). Such a role used as a key gives an empty pass and an
    agreement of None, with no reason (2026-10-14 review)."""
    absent = set(absent_roles(table))
    out: dict[str, str] = {}
    for name in names:
        if name in absent:
            out[name] = "absent"
        elif name in table.column_names and table.num_rows and table.column(name).null_count == table.num_rows:
            out[name] = "all null"
    return out


__all__ = ["DatasetRoles", "Role", "absent_roles", "dataset_roles", "label_inputs", "label_tables", "load_roles",
           "role_gaps", "role_table", "table_key", "unusable_roles", "why_unusable"]
