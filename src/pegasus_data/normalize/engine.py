"""L6 — the normalisation engine.

Every step is vectorised over Arrow arrays, never row by row, and every step is
driven by the ledger rather than by a global rule.

The one deliberate exception is the fallback in
:func:`~pegasus_data.normalize.time.parse_date_array`: impossible calendar dates
(``20150230`` is in the raw data) make Arrow's whole-column cast fail, and it
re-parses element-wise so one bad row does not null a whole column. It runs only
after that cast raises. Everything else — including the municipality expansion,
the UF lookup and the epidemiological week, which used to run Python loops
behind vectorised-sounding docstrings — is Arrow the whole way down.

The steps:

1. **Type canonicalisation** from the container's declared width and decimals.
2. **Sentinel nulling**, per field, from ``ledger.sentinel_values`` — a ``9`` is
   missing in one field and a valid category in another, and a global rule
   silently corrupts data.
3. **Code decoding** (opt-in, ``emit_labels``), emitting **both** ``field`` (raw) and
   ``field_label`` (decoded). Nothing is destroyed, and the raw column costs almost
   nothing after Parquet dictionary encoding.
4. **Geo canonicalisation** by join, with the check digit as secondary validation.
5. **Time canonicalisation**, using the source's own epidemiological week where it
   publishes one.
6. **Provenance columns** on every row group.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.compute as pc

from ..catalog.store import CatalogStore, utcnow
from ..decode.base import DecodedTable
from ..duckdb_session import connect as duck_connect
from ..semantics.dictionary import (
    DictionaryCache,
    codelists_for,
    most_granular_codelist,
    observed_values,
)
from ..semantics.dictionary import lookup as dict_lookup
from .geo import MunicipalityIndex, to_seven_digit, uf_array
from .time import SOURCE_EPI_WEEK_FIELDS, epi_week_array, parse_date_array
from .types import arrow_type_for, cast_boolean, cast_numeric

#: ``_row`` is the record's ordinal in its source member, counted before any
#: filtering: with ``_blob_sha256`` (content-addressed) and the member in
#: ``_source_path`` it identifies the record *in that publication* (ADR-0107).
#: ``_record_key`` identifies the record whatever publication it was read from:
#: the MD5 of its own fields. SINASC publishes the same births in a national
#: file and per-state files, and a birth had two identities, one per file
#: (OQ-65; 2026-10-03: all 28,524 Sergipe births hash identically in both).
PROVENANCE_COLUMNS = ("_source_path", "_blob_sha256", "_row", "_ingested_at", "_schema_signature", "_record_key")


def key_fields(names: Iterable[str]) -> list[str]:
    """The fields a record key hashes, in hash order: the source's own fields, without provenance (``_*``), companion
    labels (``*_label``) or the lake's Hive partition columns, which are not in a partition file."""
    return sorted(n for n in names if not n.startswith("_") and not n.endswith("_label"))


def record_key_sql(fields: Sequence[str]) -> str:
    """The record key as SQL over ``fields`` (`key_fields`): MD5 over the fields in name order, a null hashed as a
    distinct marker, never as an empty string. The one definition: the decoder stamps it (`record_keys`) and the lake
    computes it on read from a partition file's own columns (`persist.lake`), which reproduces the stamped key on every
    file (2026-11-21, OQ #99)."""
    parts = ", ".join(f'coalesce(CAST("{n}" AS VARCHAR), chr(0))' for n in fields)
    return f"md5(concat_ws('|', {parts}))"


def record_keys(batch: pa.RecordBatch, fields: Sequence[str] | None = None) -> pa.Array:
    """The content key of each record (`record_key_sql`) over ``fields``, by default every field of the batch
    (`key_fields`), so the key depends only on what the source published for the record."""

    names = key_fields(batch.schema.names) if fields is None else list(fields)
    if not names:
        return pa.nulls(batch.num_rows, pa.string())
    con = duck_connect()
    con.register("b", pa.Table.from_batches([batch.select(names)]))
    return con.execute(f"SELECT {record_key_sql(names)} AS k FROM b").to_arrow_table().column("k").combine_chunks()


@dataclass(slots=True)
class FieldPlan:
    """What normalisation will do to one column, decided once and reused."""

    name: str
    physical_type: str | None = None
    width: int | None = None
    decimals: int | None = None
    semantic_type: str = "unknown"
    aggregation: str = "non_summable"
    sentinels: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    official_name: str | None = None
    date_order: str = "YYYYMMDD"
    #: The codelist the labels came from, and whether it is a hierarchical
    #: classification rather than a small closed set.
    codelist: str | None = None
    hierarchical: bool = False

    @property
    def emits_label(self) -> bool:
        """Only small closed codelists get a materialised label column.

        A hierarchical classification (ICD, procedures, CBO, municipality) is
        joined against a version-scoped reference table instead — see
        ``pegasus_data.persist.reference`` for why baking one of its labels into
        every row is the wrong shape, not merely a larger one.
        """
        return bool(self.labels) and not self.hierarchical


@dataclass(slots=True)
class NormalizePlan:
    family_id: str
    system: str
    schema_signature: str
    fields: dict[str, FieldPlan] = field(default_factory=dict)
    #: The family's catalogued columns, in order. A file carrying all of them
    #: and more is a republication that gained columns (ADR-0078).
    columns: tuple[str, ...] = ()
    municipalities: MunicipalityIndex | None = None
    keep_raw: bool = True
    #: Materialise a `<field>_label` column for small closed codelists (§7.1
    #: step 3). Off unless asked: a label frozen into the lake is today's meaning on every historical row, whatever the
    #: codelist's validity windows (labels are joined at read time, by window). Hierarchical classifications are
    #: excluded regardless: they are joined from `lake/reference/` at the granularity and vintage the consumer
    #: chooses. False drops label columns entirely; every raw code and every dictionary entry is still present, so
    #: meaning stays recoverable. It is part of the plan fingerprint: the built lakes were written with it off.
    emit_labels: bool = False

    def for_field(self, name: str) -> FieldPlan:
        return self.fields.get(name) or FieldPlan(name=name)


#: Bumped by hand when normalisation semantics change in a way that would give
#: different output for the same input. The fingerprint below cannot hash the
#: code, so this is the honest stand-in — and a build after a normalisation fix
#: must not silently reuse partitions produced by the old rules.
TRANSFORM_VERSION = "1"


def plan_fingerprint(plan: NormalizePlan) -> str:
    """A stable digest of everything in the plan that changes the output.

    Stable across processes, so it must not touch `id()`, `hash()` of anything
    salted, or dict ordering — hence the sorting.
    """
    h = hashlib.sha256()
    h.update(b"pegasus.normalize.plan.v1\0")
    h.update(TRANSFORM_VERSION.encode())
    h.update(f"\0{plan.family_id}\0{plan.system}\0{plan.schema_signature}\0".encode())
    h.update(f"keep_raw={plan.keep_raw}\0emit_labels={plan.emit_labels}\0".encode())
    muni = plan.municipalities
    # Content, not cardinality: correcting one municipality mapping commonly
    # leaves the entry count unchanged while changing every rebuilt value for
    # that code.
    h.update(
        f"municipalities={muni.fingerprint if muni is not None else 'none'}\0".encode()
    )
    for name in sorted(plan.fields):
        fp = plan.fields[name]
        h.update(name.encode())
        h.update(
            f"\0{fp.physical_type}\0{fp.width}\0{fp.decimals}\0{fp.semantic_type}"
            f"\0{fp.aggregation}\0{fp.official_name}\0{fp.date_order}"
            f"\0{fp.codelist}\0{fp.hierarchical}\0".encode()
        )
        h.update(("|".join(sorted(fp.sentinels))).encode())
        h.update(b"\0")
        h.update(("|".join(f"{k}={v}" for k, v in sorted(fp.labels.items()))).encode())
        h.update(b"\0")
    return h.hexdigest()


def build_plan(
    catalog: CatalogStore,
    *,
    family_id: str,
    municipalities: MunicipalityIndex | None = None,
    cache: DictionaryCache | None = None,
) -> NormalizePlan:
    """Read the ledger and dictionary once, into a reusable per-family plan.

    Pass a shared ``cache`` when building several families in one run: the
    codelists are the same across them, and ``MUNICBR`` alone is 25,000 rows to
    re-read per family otherwise.
    """
    cache = cache or DictionaryCache(catalog)
    family = catalog.query(
        "SELECT system, series, schema_signature FROM families WHERE family_id = ?", (family_id,)
    )
    if not family:
        raise KeyError(f"unknown family: {family_id}")
    system = family[0]["system"]
    signature = family[0]["schema_signature"]

    schema_row = catalog.query(
        "SELECT fields_json FROM schemas WHERE schema_signature = ?", (signature,)
    )
    columns: tuple[str, ...] = ()
    if schema_row and schema_row[0]["fields_json"]:
        columns = tuple(
            str(f["name"] if isinstance(f, dict) else f).upper()
            for f in json.loads(schema_row[0]["fields_json"])
        )
    plan = NormalizePlan(
        family_id=family_id,
        system=system,
        schema_signature=signature,
        columns=columns,
        municipalities=municipalities,
    )

    profiles = {
        r["field_name"]: r
        for r in catalog.query(
            """
            SELECT field_name, physical_type, width, decimals, semantic_type, semantic_evidence
              FROM variable_profiles WHERE family_id = ?
            """,
            (family_id,),
        )
    }
    ledger_rows = {
        r["field_name"]: r
        for r in catalog.query(
            """
            SELECT field_name, semantic_type, aggregation, sentinel_values, official_name
              FROM ledger WHERE family_id = ?
            """,
            (family_id,),
        )
    }

    # A column no profile describes (the seed ships none; only a maintainer's catalog has them)
    # still has its container's own declaration: a DBF 'D' field is a date, whatever the profile.
    # SINAN's DBCs declare 'D' on every date column, 213 names in 96 of its 98 families, and no
    # other system declares any; before this they arrived as YYYYMMDD text in a fresh home.
    header_dates = [
        r["field_name"]
        for r in catalog.query(
            """
            SELECT DISTINCT field_name FROM schema_header_facts
             WHERE schema_signature = ? AND type_code = 'D'
            """,
            (signature,),
        )
    ]
    for name in header_dates:
        if name not in profiles:
            plan.fields[name] = FieldPlan(name=name, physical_type="D", width=8)

    for name, profile in profiles.items():
        ledger = ledger_rows.get(name)
        semantic = (ledger["semantic_type"] if ledger else None) or profile["semantic_type"] or "unknown"
        sentinels = json.loads(ledger["sentinel_values"]) if ledger and ledger["sentinel_values"] else []
        order = "YYYYMMDD"
        if profile["semantic_evidence"]:
            try:
                order = json.loads(profile["semantic_evidence"]).get("order", "YYYYMMDD")
            except (json.JSONDecodeError, AttributeError):
                order = "YYYYMMDD"
        observed = observed_values(
            catalog, family_id=family_id, field_name=name, schema_signature=signature
        )
        # The opt-in stored label column's own table (`emit_labels`, off; a read renders from `label_bindings`, OQ 79).
        # NOT dead when it is off: `labels`, `codelist` and `hierarchical` are inputs of `plan_fingerprint`, which says
        # which built partitions are current (ADR-0173), so computing them differently would restale every one.
        labels = dict_lookup(
            catalog, system=system, field_name=name, observed=observed, cache=cache
        )
        bound = codelists_for(catalog, system=system, field_name=name, cache=cache)
        codelist = most_granular_codelist(
            catalog, bound, system=system, observed=observed, cache=cache
        )
        hierarchical = bool(codelist) and cache.is_hierarchical(codelist)
        plan.fields[name] = FieldPlan(
            name=name,
            physical_type=profile["physical_type"],
            width=profile["width"],
            decimals=profile["decimals"],
            semantic_type=semantic,
            aggregation=(ledger["aggregation"] if ledger else "non_summable"),
            sentinels=sentinels,
            labels=labels,
            official_name=(ledger["official_name"] if ledger else None),
            date_order=order,
            codelist=codelist,
            hierarchical=hierarchical,
        )
    return plan


def _null_sentinels(array: pa.Array, sentinels: Sequence[str]) -> pa.Array:
    if not sentinels:
        return array
    if array.type != pa.string():
        array = array.cast(pa.string())
    mask = pc.is_in(array, value_set=pa.array(list(sentinels), type=pa.string()))
    return pc.if_else(pc.fill_null(mask, False), pa.scalar(None, pa.string()), array)


def _label_array(array: pa.Array, labels: dict[str, str]) -> pa.Array:
    """Map raw codes to labels; unmapped values become null, never invented."""
    if array.type != pa.string():
        array = array.cast(pa.string())
    # once per DISTINCT code, taken back to the rows (a null stays null): a loop over every row of a state-year
    encoded = pc.dictionary_encode(array)
    mapped = pa.array([labels.get(v) for v in encoded.dictionary.to_pylist()], type=pa.string())
    return pc.take(mapped, encoded.indices)


def normalize_batch(batch: pa.RecordBatch, plan: NormalizePlan) -> pa.RecordBatch:
    """Apply the plan to one RecordBatch."""
    columns: list[pa.Array] = []
    names: list[str] = []

    for name in batch.schema.names:
        raw = batch.column(name)
        fp = plan.for_field(name)
        cleaned = _null_sentinels(raw, fp.sentinels)

        typed: pa.Array
        semantic = fp.semantic_type
        if semantic in {"date"}:
            typed = parse_date_array(cleaned, order=fp.date_order, sentinels=tuple(fp.sentinels))
        elif semantic in {"money", "numeric_measure"}:
            target = arrow_type_for(fp.physical_type, fp.width, fp.decimals)
            typed = cast_numeric(cleaned, target, decimals=fp.decimals, field=name)
        elif (fp.physical_type or "").upper() == "L":
            typed = cast_boolean(cleaned)
        elif (fp.physical_type or "").upper() == "D":
            typed = parse_date_array(cleaned, order="YYYYMMDD", sentinels=tuple(fp.sentinels))
        else:
            typed = cleaned if cleaned.type == pa.string() else cleaned.cast(pa.string())

        # The raw column is always retained (§13: never discard the raw value
        # when writing a decoded label). Typed columns keep the original name;
        # where typing changed the representation, the raw text goes alongside.
        names.append(name)
        columns.append(typed)
        if semantic in {"date", "money", "numeric_measure"} and plan.keep_raw:
            names.append(f"{name}_raw")
            columns.append(cleaned if cleaned.type == pa.string() else cleaned.cast(pa.string()))

        if fp.emits_label and plan.emit_labels:
            names.append(f"{name}_label")
            columns.append(_label_array(cleaned, fp.labels))

        if semantic in {"municipality_code_6", "municipality_code_7"}:
            names.append(f"{name}_ibge7")
            columns.append(to_seven_digit(cleaned, plan.municipalities))
            names.append(f"{name}_uf")
            columns.append(uf_array(cleaned))

        if semantic == "date" and name.upper() not in SOURCE_EPI_WEEK_FIELDS:
            epi_year, epi_wk = epi_week_array(typed)
            names.append(f"{name}_epi_year")
            columns.append(epi_year)
            names.append(f"{name}_epi_week")
            columns.append(epi_wk)

    return pa.RecordBatch.from_arrays(columns, names=names)


def add_provenance(
    batch: pa.RecordBatch, *, source_path: str, blob_sha256: str, schema_signature: str,
    first_row: int = 0, record_key: bool = True, rows: pa.Array | None = None,
) -> pa.RecordBatch:
    n = batch.num_rows
    stamp = utcnow()

    def _constant(value: str) -> pa.Array:
        """One value repeated for every row, stored once.

        These were built as `pa.array([value] * n)` — a full string buffer per
        column per batch, four of them, every value identical. At millions of
        rows that is hundreds of megabytes of transient Arrow buffers carrying
        four distinct facts. A dictionary array stores the value once and an
        index per row, and Parquet already round-trips it as dictionary-encoded.
        """
        return pa.DictionaryArray.from_arrays(
            pa.array([0] * n, type=pa.int32()),
            pa.array([value], type=pa.string()),
        )

    extra = {
        "_source_path": _constant(source_path),
        "_blob_sha256": _constant(blob_sha256),
        "_row": rows if rows is not None else pa.array(range(first_row, first_row + n), type=pa.int64()),
        "_ingested_at": _constant(stamp),
        "_schema_signature": _constant(schema_signature),
        # a content key over a projection is not the record's key: the same record read with other
        # columns got another key, and links stored in a lake-less home could not be joined back to
        # their records (PegaSUS, 2026-10-04). A projected batch carries none; identity then falls
        # back to _blob_sha256:_row, which every projection of the file shares. Nor is one nobody
        # reads: a `fetch()` without provenance drops the column, after about 9 us a row to hash it.
        "_record_key": record_keys(batch) if record_key else pa.nulls(n, pa.string()),
    }
    return pa.RecordBatch.from_arrays(
        list(batch.columns) + list(extra.values()),
        names=list(batch.schema.names) + list(extra.keys()),
    )


def normalize_table(
    table: DecodedTable,
    plan: NormalizePlan,
    *,
    blob_sha256: str = "",
    with_provenance: bool = True,
    record_key: bool = True,
    rows: Mapping[str, Sequence[str]] | None = None,
    rows_join: str = "all",
) -> Iterator[pa.RecordBatch]:
    """Stream a decoded table through the plan, batch by batch.

    ``record_key=False`` leaves ``_record_key`` null: a caller that drops provenance (``fetch()`` by default) does not
    pay to hash every row. A batch that lacks some of the family's columns has none either way.

    ``rows`` (``{column: code prefixes}``, combined by ``rows_join``) drops, before they are normalised or hashed, the
    raw rows that cannot match (`raw_rows_mask`): an extract kept 1.3% of SIH-SP's 1.6 billion rows and had normalised
    and hashed all of them, two thirds of its time (2026-11-21). A kept row's ``_row`` is still its ordinal in the file.
    The test is a superset of the normalised one, which the caller applies after.
    """
    import pyarrow.compute as pc

    first_row = 0
    for batch in table.batches():
        n = batch.num_rows
        complete = not plan.columns or set(plan.columns) <= set(batch.schema.names)
        ordinals = None
        mask = raw_rows_mask(batch, plan, rows, rows_join) if rows else None
        if mask is not None:
            kept = pc.indices_nonzero(pc.fill_null(mask, False))
            batch = batch.take(kept)
            ordinals = pc.add(kept.cast(pa.int64()), pa.scalar(first_row, pa.int64()))
        out = normalize_batch(batch, plan)
        if with_provenance:
            out = add_provenance(
                out,
                source_path=table.source_id,
                blob_sha256=blob_sha256,
                schema_signature=plan.schema_signature,
                first_row=first_row,
                record_key=record_key and complete,
                rows=ordinals,
            )
        if mask is not None:        # what the file held, before the filter: `retrieve.FetchReport.rows_decoded`
            out = out.replace_schema_metadata({**(out.schema.metadata or {}), b"pegasus.rows_decoded": str(n).encode()})
        first_row += n
        yield out


def raw_rows_mask(batch: pa.RecordBatch, plan: NormalizePlan, rows: Mapping[str, Sequence[str]],
                  join: str = "all") -> pa.Array | None:
    """Which raw rows can match ``rows`` (``{column: prefixes}``), or None when this batch cannot be tested raw. A code
    column is normalised by nulling its sentinels (`normalize_batch`), so a raw prefix test keeps every row the
    normalised test keeps, and the sentinels besides. A column typed on the way (a date, a number) or absent from the
    batch is not tested raw: under ``"all"`` it restricts nothing here, under ``"any"`` nothing is dropped."""
    import pyarrow.compute as pc

    from .._query_engine.request import prefix_match, rows_filters

    out = None
    for column, prefixes in rows_filters(rows).items():
        fp = plan.for_field(column)
        raw = column in batch.schema.names and fp.semantic_type not in {"date", "money", "numeric_measure"}             and (fp.physical_type or "").upper() not in ("L", "D")
        if not raw:
            if join == "any":
                return None
            continue
        hit = prefix_match(batch.column(column).cast(pa.string()), prefixes)
        out = hit if out is None else (pc.and_kleene(out, hit) if join == "all" else pc.or_kleene(out, hit))
    return out


class MissingColumnError(KeyError):
    """A requested column does not exist in this schema generation.

    Raised rather than returning empty, because an empty result looks legitimate
    and is the single easiest way to publish a wrong number (§13). The message
    names the generations that *do* carry the column.
    """

    def __init__(
        self,
        field_name: str,
        family_id: str,
        available: Sequence[str],
        *,
        also_absent: Sequence[str] = (),
        carried_in: str = "",
    ) -> None:
        self.field_name = field_name
        #: The years the dataset's decoded schemas carry the column (`FieldWindow.span`): a family id names a generation
        #: by its hash, and a reader choosing a period needs the years.
        self.carried_in = carried_in
        self.family_id = family_id
        self.available = list(available)
        #: Every requested column absent from this generation, `field_name`
        #: included. Machine-readable: a caller fixing a column list needs all
        #: of them, and naming one at a time turns one mistake into N attempts.
        self.columns_absent = [field_name, *[c for c in also_absent if c != field_name]]
        hint = ", ".join(sorted(available)[:12]) or "no other generation carries it"
        rest = (
            f" (also absent: {', '.join(self.columns_absent[1:])})"
            if len(self.columns_absent) > 1
            else ""
        )
        super().__init__(
            f"column {field_name!r} is not present in family {family_id}{rest}; "
            f"generations that do carry it: {hint}" + (f" (years: {carried_in})" if carried_in else "")
        )
