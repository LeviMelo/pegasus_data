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
3. **Code decoding**, emitting **both** ``field`` (raw) and ``field_label``
   (decoded). Nothing is destroyed, and the raw column costs almost nothing after
   Parquet dictionary encoding.
4. **Geo canonicalisation** by join, with the check digit as secondary validation.
5. **Time canonicalisation**, using the source's own epidemiological week where it
   publishes one.
6. **Provenance columns** on every row group.
"""

from __future__ import annotations

import hashlib

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.compute as pc

from ..catalog.store import Catalog, utcnow
from ..decode.base import DecodedTable
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

PROVENANCE_COLUMNS = ("_source_path", "_blob_sha256", "_ingested_at", "_schema_signature")


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
    municipalities: MunicipalityIndex | None = None
    keep_raw: bool = True
    #: Materialise a `<field>_label` column for small closed codelists (§7.1
    #: step 3). Hierarchical classifications are excluded regardless: they are
    #: joined from `lake/reference/` at the granularity and vintage the consumer
    #: chooses. Setting this False drops label columns entirely; every raw code
    #: and every dictionary entry is still present, so meaning stays recoverable.
    emit_labels: bool = True

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
    # The municipality index is derived from the dictionary; its size moves when
    # that evidence changes, which is exactly when re-normalising is warranted.
    h.update(f"municipalities={muni.size if muni is not None else 0}\0".encode())
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
    catalog: Catalog,
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

    plan = NormalizePlan(
        family_id=family_id,
        system=system,
        schema_signature=signature,
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
    return pa.array([labels.get(v) if v is not None else None for v in array.to_pylist()], type=pa.string())


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
            typed = cast_numeric(cleaned, target, decimals=fp.decimals)
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
    batch: pa.RecordBatch, *, source_path: str, blob_sha256: str, schema_signature: str
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
        "_ingested_at": _constant(stamp),
        "_schema_signature": _constant(schema_signature),
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
) -> Iterator[pa.RecordBatch]:
    """Stream a decoded table through the plan, batch by batch."""
    for batch in table.batches():
        out = normalize_batch(batch, plan)
        if with_provenance:
            out = add_provenance(
                out,
                source_path=table.source_id,
                blob_sha256=blob_sha256,
                schema_signature=plan.schema_signature,
            )
        yield out


class MissingColumnError(KeyError):
    """A requested column does not exist in this schema generation.

    Raised rather than returning empty, because an empty result looks legitimate
    and is the single easiest way to publish a wrong number (§13). The message
    names the generations that *do* carry the column.
    """

    def __init__(self, field_name: str, family_id: str, available: Sequence[str]) -> None:
        self.field_name = field_name
        self.family_id = family_id
        self.available = list(available)
        hint = ", ".join(sorted(available)[:12]) or "no other generation carries it"
        super().__init__(
            f"column {field_name!r} is not present in family {family_id}; "
            f"generations that do carry it: {hint}"
        )


def require_columns(catalog: Catalog, family_id: str, columns: Sequence[str]) -> None:
    """Fail loudly when a requested column is absent from this generation."""
    row = catalog.query(
        "SELECT system, series, schema_signature FROM families WHERE family_id = ?", (family_id,)
    )
    if not row:
        raise KeyError(f"unknown family: {family_id}")
    present = {
        r["field_name"]
        for r in catalog.query(
            "SELECT field_name FROM schema_presence WHERE schema_signature = ?",
            (row[0]["schema_signature"],),
        )
    }
    for column in columns:
        if column in present:
            continue
        elsewhere = [
            r["family_id"]
            for r in catalog.query(
                """
                SELECT DISTINCT f.family_id
                  FROM families f
                  JOIN schema_presence sp ON sp.schema_signature = f.schema_signature
                 WHERE f.system = ? AND f.series IS ? AND sp.field_name = ?
                """,
                (row[0]["system"], row[0]["series"], column),
            )
        ]
        raise MissingColumnError(column, family_id, elsewhere)
