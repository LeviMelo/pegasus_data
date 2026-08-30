"""`aggregate()` — persistent, composable, geography × time analytical cells.

The dominant PegaSUS workload is geography × time → measures, and answering it
from microdata is not viable at request time: `fetch("SIH-RD", uf="AC",
years=2022)` takes 130 s for 49,547 admissions, while the same rows at
municipality × month × sex are 989 cells. Fifty times smaller, and Acre is 0.4%
of national SIH volume.

So an aggregate is built once, offline, and served cheaply. Two surfaces:

* :func:`build_aggregate` — maintainer, expensive, writes an artifact under the
  lake. Its ONLY source of rows is :func:`pegasus_data.query`; there is no
  second retrieval path in this module.
* :func:`aggregate` — filter, roll up, finalize. Arithmetic on a few thousand
  rows, no microdata touched.

What is stored is **accumulator state**, never a finished number — `los_n` and
`los_sum`, not a mean. `measures.py` holds the algebra and the refusals;
`docs/AGGREGATE_ALGEBRA.md` derives why. The short version: roll-up is
pushforward along a map of key spaces, so it is valid exactly when the measure
is a commutative monoid and the map is a total single-valued function. Every
refusal below is one of those two failing.

**One base cuboid.** Every view is derived from the single materialised finest
table. Computing "sex = Total" independently of the per-sex rows would let them
disagree — different retrieval moments, different source vintages — and a table
where the total is not the sum of its parts destroys trust in everything else on
the page. Deriving makes that consistency structural rather than hoped for.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .measures import (
    AggregationRefused,
    Measure,
    check_dimension,
    check_measure,
    check_rollup,
    measure_from_declaration,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

    from .config import Settings

__all__ = [
    "AggregateReport",
    "AggregateSpec",
    "aggregate",
    "build_aggregate",
    "load_specs",
    "spec_named",
]

#: Bump when the build's arithmetic changes, so every artifact rebuilds.
ENGINE_VERSION = "1"

#: The physical key columns of a base cuboid.
GEOGRAPHY_KEY = "municipality"
TIME_KEY = "competencia"

#: Levels the geography axis understands beyond the compiled classifications.
#: `municipality` is the base; the others are pushforwards from it.
_BASE_LEVEL = "municipality"
_UF_LEVEL = "uf"
_NATIONAL_LEVEL = "brazil"

#: Marginalising an axis IS rolling it up to a one-point space, so "Total" is
#: not a special case in the code either.
TOTAL = "__total__"


class ArtifactMissing(RuntimeError):
    """The artifact has not been built, so nothing can be served from it."""


# --------------------------------------------------------------------- spec


@dataclass(frozen=True, slots=True)
class AggregateSpec:
    """A recipe for one artifact. Build-time metadata, not a query."""

    name: str
    dataset: str
    geography_binding: str
    time_binding: str
    time_grain: str
    dimensions: tuple[str, ...]
    measures: tuple[Measure, ...]
    description: str = ""
    #: `dimension -> display name`, for the interface. Optional: an absent entry
    #: falls back to curation's translated name and then to the column itself.
    dimension_labels: Mapping[str, str] = field(default_factory=dict)
    #: What to call this artifact on screen.
    label: str = ""

    def measure_named(self, name: str) -> Measure:
        for item in self.measures:
            if item.name == name:
                return item
        raise AggregationRefused(
            f"{self.name!r} has no measure {name!r}; it has "
            f"{[m.name for m in self.measures]}"
        )

    def state_columns(self) -> tuple[str, ...]:
        return tuple(c for m in self.measures for c in m.state_columns())

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dataset": self.dataset,
            "geography_binding": self.geography_binding,
            "time_binding": self.time_binding,
            "time_grain": self.time_grain,
            "dimensions": list(self.dimensions),
            "measures": [
                {
                    "name": m.name, "kind": m.kind.name, "field": m.source_field,
                    "unit": m.unit, "additive_over": sorted(m.additive_over),
                    "time_reducer": m.time_reducer,
                }
                for m in self.measures
            ],
        }


#: Every UF, for chunking a national build. Ordered by IBGE code so a build's
#: progress reads north to south, which is also roughly smallest to largest and
#: therefore fails fast on a systematic problem.
_ALL_UFS: tuple[str, ...] = (
    "RO", "AC", "AM", "RR", "PA", "AP", "TO",
    "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA",
    "MG", "ES", "RJ", "SP",
    "PR", "SC", "RS",
    "MS", "MT", "GO", "DF",
)


def _spec_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    from .ontology import CURATION

    return CURATION / "aggregates"


def load_specs(root: Path | None = None) -> dict[str, AggregateSpec]:
    """Every declared aggregate, keyed by name."""
    from .ontology import _read_yaml

    folder = _spec_root(root)
    out: dict[str, AggregateSpec] = {}
    if not folder.exists():
        return out
    for path in sorted(folder.glob("*.yml")):
        data = _read_yaml(path) or {}
        name = str(data.get("name") or path.stem)
        measures = tuple(
            measure_from_declaration(key, body or {})
            for key, body in (data.get("measures") or {}).items()
        )
        if not measures:
            raise AggregationRefused(f"aggregate {name!r} declares no measures")
        out[name] = AggregateSpec(
            name=name,
            dataset=str(data["dataset"]),
            geography_binding=str(data.get("geography_binding") or ""),
            time_binding=str(data.get("time_binding") or ""),
            time_grain=str(data.get("time_grain") or "month"),
            dimensions=tuple(str(d) for d in (data.get("dimensions") or ())),
            measures=measures,
            description=str(data.get("description") or ""),
            dimension_labels={
                str(k): str(v) for k, v in (data.get("dimension_labels") or {}).items()
            },
            label=str(data.get("label") or ""),
        )
    return out


def spec_named(name: str, root: Path | None = None) -> AggregateSpec:
    specs = load_specs(root)
    if name not in specs:
        raise AggregationRefused(
            f"no aggregate spec named {name!r}; declared: {sorted(specs)}"
        )
    return specs[name]


# ------------------------------------------------------------------- report


@dataclass
class AggregateReport:
    """What the build or the read actually did, including what it refused."""

    name: str = ""
    cells: int = 0
    rows_read: int = 0
    years: tuple[int, ...] = ()
    #: ``year -> {dimension: present|absent|unknown}``. The support mask: a
    #: dimension absent from a schema generation produces cells that mean "we
    #: could not have known", not "it happened zero times".
    support: dict[str, dict[str, str]] = field(default_factory=dict)
    #: Mass lost rolling up through a partial classification, per measure.
    unmapped: dict[str, float] = field(default_factory=dict)
    contested: tuple[str, ...] = ()
    #: The UFs this build FETCHED, or empty for a national build. An artifact
    #: built from one state's files is not a national artifact with a lot of
    #: zeroes -- it is a partial observation, and a municipality with no cell
    #: was never in view. Without this the interface presents a state as a
    #: country, which is the same class of error as reading a structural
    #: absence as a clinical zero.
    uf: tuple[str, ...] = ()
    #: Periods whose cells are known to be SHORT, because the time axis is a
    #: record date and the publication years fetched do not fully contain it.
    #: A December admission is billed in January, so a series by admission date
    #: built from one publication year is missing its own edges.
    partial_periods: tuple[str, ...] = ()
    warnings: list[str] = field(default_factory=list)
    fingerprint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "cells": self.cells, "rows_read": self.rows_read,
            "years": list(self.years), "support": self.support,
            "unmapped": self.unmapped, "contested": list(self.contested),
            "uf": list(self.uf),
            "partial_periods": list(self.partial_periods),
            "warnings": self.warnings, "fingerprint": self.fingerprint,
        }

    def __repr__(self) -> str:  # pragma: no cover - display
        return f"<AggregateReport {self.name}: {self.cells:,} cells from {self.rows_read:,} rows>"


# -------------------------------------------------------------------- paths


def artifact_dir(name: str, settings: Settings) -> Path:
    """Artifacts are DERIVED DATA and live under the lake, never in the wheel.

    ARCHITECTURE §14a: the wheel ships what makes the module self-describing —
    curation, the label pack, the compiled geography. A SIH cube is rebuildable
    from the tree and is not that.
    """
    return Path(settings.lake_dir) / "aggregates" / name


def _manifest_path(name: str, settings: Settings) -> Path:
    return artifact_dir(name, settings) / "manifest.json"


# -------------------------------------------------------------------- build


def _resolve_semantics(spec: AggregateSpec):
    from .semantics.curation import semantics_for

    semantics = semantics_for(spec.dataset)
    if semantics is None:
        raise AggregationRefused(
            f"no curated semantics for {spec.dataset!r}; an aggregate needs its "
            "grain and its semantic_axes to know what a row is and which field "
            "carries geography"
        )
    return semantics



def _require_municipality_geography(semantics: Any, spec: AggregateSpec) -> None:
    """The base cuboid is keyed on a municipality, so the binding must be one.

    `IBGE.PROJUF` is population projected by STATE and its geography axis is
    `UFCOD`. Building it as if the key were a municipality would produce cells
    keyed on 27 two-digit codes that no municipality table can resolve — every
    roll-up unmapped, every total a subset — so it is refused at the spec rather
    than discovered in the output.
    """
    body = semantics.geography_bindings().get(spec.geography_binding) or {}
    code_system = str(body.get("code_system") or "")
    if code_system and code_system != "ibge_municipality":
        raise AggregationRefused(
            f"{spec.dataset} binding {spec.geography_binding!r} is keyed on "
            f"{code_system!r}, and an aggregate's base cuboid is keyed on a "
            "municipality. A different spatial grain needs its own artifact, "
            "not this one with a different column in the same slot."
        )


def _binding_fields(bindings: Mapping[str, Any], chosen: str, kind: str,
                    dataset: str) -> tuple[str, ...]:
    if not bindings:
        raise AggregationRefused(f"{dataset} declares no {kind} axes")
    if chosen not in bindings:
        raise AggregationRefused(
            f"{dataset} has no {kind} binding {chosen!r}; it declares "
            f"{sorted(bindings)}. These are `semantic_axes` in curation — the "
            "aggregate layer reads them rather than naming fields itself."
        )
    body = bindings[chosen] or {}
    fields = tuple(str(f) for f in (body.get("fields") or ()))
    if not fields:
        raise AggregationRefused(f"{kind} binding {chosen!r} names no fields")
    return fields


def _competencia(row: Mapping[str, Any], fields: Sequence[str]) -> str | None:
    """AAAAMM from the declared time fields, however they are spelled."""
    if len(fields) >= 2:
        year, month = row.get(fields[0]), row.get(fields[1])
        if year is None or month is None:
            return None
        return f"{str(year).strip():>04}{str(month).strip().zfill(2)}"
    value = row.get(fields[0])
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 6 and text[:6].isdigit():
        return text[:6]
    return None


def build_aggregate(
    name: str,
    *,
    years: Sequence[int] | None = None,
    uf: str | Sequence[str] | None = None,
    settings: Settings | None = None,
    root: str | Path | None = None,
    rebuild: bool = False,
) -> AggregateReport:
    """Materialise the base cuboid for one spec.

    Rows come from :func:`pegasus_data.query` and nowhere else. Everything after
    that is arithmetic: lift each row into accumulator state, group by the key
    tuple, merge.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from ._availability import field_available
    from .config import load_settings
    from .persist.staging import staged_file
    from .retrieve import fetch as _fetch

    resolved = settings or load_settings(root=Path(root) if root else None)
    spec = spec_named(name)
    semantics = _resolve_semantics(spec)

    # Refuse a measure the grain contradicts BEFORE reading anything: counting
    # rows on an establishment-month dataset counts establishment-months.
    for measure in spec.measures:
        check_measure(measure, semantics.grain)

    geography_fields = _binding_fields(
        semantics.geography_bindings(), spec.geography_binding, "geography", spec.dataset)
    _require_municipality_geography(semantics, spec)
    time_fields = _binding_fields(
        semantics.time_bindings(), spec.time_binding, "time", spec.dataset)
    time_encoding = str(
        (semantics.time_bindings().get(spec.time_binding) or {}).get("encoding") or "")
    geography_field = geography_fields[0]

    report = AggregateReport(name=name)
    # Normalised the same way `fetch` reads it, so the manifest says what was
    # actually asked for rather than what the caller happened to type.
    report.uf = (
        (str(uf).upper(),) if isinstance(uf, str)
        else tuple(str(u).upper() for u in uf) if uf
        else ()
    )
    wanted_years = tuple(int(y) for y in (years or ()))
    if not wanted_years:
        raise AggregationRefused(
            "build_aggregate needs explicit years; an unbounded build would "
            "download the whole publication history"
        )

    cells: dict[tuple[str, ...], dict[str, tuple[float, ...]]] = {}
    blob_digests: set[str] = set()

    # One chunk per (year, UF) rather than one per year.
    #
    # `_fetch(uf=None, years=Y)` materialises a whole national year as one Arrow
    # table before any cell is written. Measured on SIH-RD 2022: 7.9 GB resident
    # and climbing, for ~11.8 million admissions.
    #
    # The merge is a commutative monoid, so `cells` accumulating across chunks
    # gives exactly the artifact one big call would have. Chunking caps the peak
    # at the LARGEST STATE instead of the country, and lets the build report
    # progress rather than going quiet for half an hour.
    def _chunks() -> list[tuple[int, str | Sequence[str] | None]]:
        if report.uf:
            return [(year, u) for year in sorted(wanted_years) for u in report.uf]
        return [(year, u) for year in sorted(wanted_years) for u in _ALL_UFS]

    chunks = _chunks()
    national_fallback = not report.uf

    for year, chunk_uf in chunks:
        # `query()` is the only retrieval path. It plans lake-vs-fetch, unions
        # schema generations with structural nulls and returns raw codes, which
        # is what `lift` needs.
        table, fetch_report = _fetch(
            spec.dataset, uf=chunk_uf, years=year, settings=resolved,
            report=True, labels=False, provenance=True,
        )
        report.rows_read += table.num_rows
        names = set(table.schema.names)
        missing = [f for f in (geography_field, *time_fields) if f not in names]
        if missing:
            report.warnings.append(
                f"{year} {chunk_uf}: {missing} absent from this generation; skipped")
            continue

        if "_blob_sha256" in names:
            for digest in set(table.column("_blob_sha256").to_pylist()):
                if digest:
                    blob_digests.add(str(digest))

        # The support mask, from the existing availability verb rather than
        # from schema logic re-derived here.
        if str(year) not in report.support:
            report.support[str(year)] = {
                dimension: str(
                    field_available(spec.dataset, dimension, year, settings=resolved))
                for dimension in spec.dimensions
            }

        # lift + merge, columnar. Each accumulator's lift is a column
        # expression and its merge is a sum, so the whole build is one
        # group_by. The row loop this replaced ran at about 1.4 ms per
        # admission -- fine for one state-year, and roughly five hours for a
        # national one, which is not a build anybody would run.
        keyed = _key_columns(
            table, geography_field, time_fields, spec.dimensions, names,
            encoding=time_encoding)
        if keyed is None:
            report.warnings.append(
                f"{year} {chunk_uf}: no usable geography/time values; skipped. If the time "
                f"axis is a date, {list(time_fields)} may hold a layout neither "
                "AAAAMMDD nor DDMMAAAA explains -- which is refused rather than "
                "bucketed under a period that means nothing."
            )
            continue
        _accumulate(cells, table, keyed, spec)
        if year not in report.years:
            report.years = (*report.years, year)

    if not cells and national_fallback:
        # Every state came back empty, which for a UF-partitioned dataset would
        # mean nothing was published at all. More likely the dataset is NOT
        # partitioned by state -- IBGE's population files are national, and so
        # is anything published one file a year. Ask for it whole.
        report.warnings.append(
            "no state-partitioned files found; retrying as a single national "
            "fetch. This dataset appears not to be published per UF, so the "
            "build holds a whole year at once."
        )
        for year in sorted(wanted_years):
            table, fetch_report = _fetch(
                spec.dataset, uf=None, years=year, settings=resolved,
                report=True, labels=False, provenance=True,
            )
            report.rows_read += table.num_rows
            names = set(table.schema.names)
            if [f for f in (geography_field, *time_fields) if f not in names]:
                continue
            if "_blob_sha256" in names:
                for digest in set(table.column("_blob_sha256").to_pylist()):
                    if digest:
                        blob_digests.add(str(digest))
            keyed = _key_columns(
                table, geography_field, time_fields, spec.dimensions, names,
                encoding=time_encoding)
            if keyed is None:
                continue
            _accumulate(cells, table, keyed, spec)
            if year not in report.years:
                report.years = (*report.years, year)
            report.warnings.extend(fetch_report.warnings[:3])

    if not cells:
        raise AggregationRefused(
            f"{name}: no cells produced for years {sorted(wanted_years)}"
        )

    key_names = (GEOGRAPHY_KEY, TIME_KEY, *spec.dimensions)
    ordered = sorted(cells)
    data: dict[str, list[Any]] = {n: [] for n in key_names}
    for measure in spec.measures:
        for column in measure.state_columns():
            data[column] = []
    for key in ordered:
        for position, column in enumerate(key_names):
            data[column].append(key[position])
        bucket = cells[key]
        for measure in spec.measures:
            state = bucket.get(measure.name) or measure.kind.identity()
            for position, column in enumerate(measure.state_columns()):
                data[column].append(float(state[position]))

    arrow = pa.table({
        **{n: pa.array(data[n], pa.string()) for n in key_names},
        **{c: pa.array(data[c], pa.float64()) for c in spec.state_columns()},
    })
    report.cells = arrow.num_rows
    _flag_partial_periods(spec, semantics, report, wanted_years, data[TIME_KEY])
    report.fingerprint = _fingerprint(spec, blob_digests, resolved)

    target = artifact_dir(name, resolved)
    target.mkdir(parents=True, exist_ok=True)
    with staged_file(target / "cells.parquet") as staged:
        pq.write_table(arrow, staged, compression="zstd", compression_level=9)
    _manifest_path(name, resolved).write_text(
        json.dumps({
            "name": name,
            "spec": spec.fingerprint_payload(),
            "fingerprint": report.fingerprint,
            "engine_version": ENGINE_VERSION,
            "cells": report.cells,
            "rows_read": report.rows_read,
            "years": list(report.years),
            "uf": list(report.uf),
            "support": report.support,
            "partial_periods": list(report.partial_periods),
            "key_columns": list(key_names),
            "warnings": report.warnings,
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report




#: DATASUS writes numbers as fixed-width text, and a blank is ABSENT rather than
#: zero. Arrow's cast raises on `''` and on anything else unparseable, so
#: non-numeric cells are nulled first: a null contributes nothing to a sum and
#: nothing to a mean's denominator, which is what "we did not observe this"
#: should do. Casting them to zero instead would drag every mean down invisibly.
_NUMERIC = r"^[+-]?\d+([.,]\d+)?$"


def _to_number(column: Any, rows: int) -> Any:
    import pyarrow as pa
    import pyarrow.compute as pc

    text = pc.utf8_trim_whitespace(pc.cast(column, pa.string()))
    looks_numeric = pc.fill_null(pc.match_substring_regex(text, _NUMERIC), False)
    cleaned = pc.if_else(looks_numeric, text, pa.nulls(rows, pa.string()))
    # A decimal comma is how some DATASUS layouts write money.
    cleaned = pc.replace_substring(cleaned, ",", ".")
    return pc.cast(cleaned, pa.float64(), safe=False)


def _accumulate(cells: dict, table: Any, keyed: dict, spec: AggregateSpec) -> None:
    """Lift, group and merge one chunk into the accumulating cells.

    The merge is a commutative monoid, which is exactly why a national build can
    be assembled a state at a time: the order chunks arrive in cannot change the
    artifact, and neither can how they are divided.
    """
    import pyarrow as pa

    lifted, state_names = _lift_columns(table, spec.measures)
    grouped = pa.table({**keyed, **lifted}).group_by(list(keyed)).aggregate(
        [(name, "sum") for name in state_names])
    got = {n: grouped.column(n).to_pylist() for n in grouped.schema.names}
    key_order = list(keyed)
    for i in range(grouped.num_rows):
        key = tuple(str(got[k][i]) for k in key_order)
        bucket = cells.setdefault(key, {})
        for measure in spec.measures:
            state = tuple(float(got[f"{c}_sum"][i] or 0.0)
                          for c in measure.state_columns())
            prior = bucket.get(measure.name)
            bucket[measure.name] = (
                state if prior is None else measure.kind.merge(prior, state))


def _key_columns(table: Any, geography_field: str, time_fields: Sequence[str],
                 dimensions: Sequence[str], names: set[str],
                 encoding: str = "") -> dict[str, Any] | None:
    """The cell key, as columns: municipality, competencia, then dimensions.

    Rows with no municipality or no resolvable period are dropped here rather
    than being bucketed under an empty key, which would silently invent a cell
    that means "we could not tell".
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    municipality = pc.utf8_trim_whitespace(
        pc.cast(table.column(geography_field), pa.string()))
    period = _competencia_column(table, time_fields, encoding)
    if period is None:
        return None
    keep = pc.and_(pc.not_equal(municipality, ""), pc.is_valid(period))
    keep = pc.fill_null(keep, False)
    out: dict[str, Any] = {
        GEOGRAPHY_KEY: pc.filter(municipality, keep),
        TIME_KEY: pc.filter(period, keep),
    }
    for dimension in dimensions:
        if dimension in names:
            column = pc.utf8_trim_whitespace(pc.cast(table.column(dimension), pa.string()))
            out[dimension] = pc.filter(pc.fill_null(column, ""), keep)
        else:
            # Structurally absent in this generation. An empty category is not
            # "unknown" -- the support mask is what says the column did not
            # exist -- but the cell still has to exist so its measures are not
            # silently lost.
            out[dimension] = pa.array([""] * pc.sum(pc.cast(keep, pa.int64())).as_py(),
                                      pa.string())
    return out


#: How many values to look at when deciding a date column's layout. The two
#: hypotheses separate on the first handful of real rows; this is generous.
_LAYOUT_SAMPLE = 4_000
#: The winner must explain at least this share of the values it was shown.
_LAYOUT_CONFIDENCE = 0.9


def _date_layout(values: Sequence[Any]) -> str | None:
    """``"ymd"``, ``"dmy"`` or None, decided by measurement.

    DATASUS does not use one date format. Measured on live 2022 files:

    ==========  ==========  ==========  ==================
    dataset     column      example     layout
    ==========  ==========  ==========  ==================
    SIH-RD      DT_INTER    20211227    AAAAMMDD (ymd)
    SIM-DO      DTOBITO     07052022    DDMMAAAA (dmy)
    SINASC-DN   DTNASC      16041976    DDMMAAAA (dmy)
    ==========  ==========  ==========  ==================

    Nineteen (system, field) pairs declare a `date` encoding, so a table of
    declared formats is nineteen things to maintain and to get wrong. The two
    layouts are separable by inspection instead: `20211227` cannot be day-first
    because `12` is a plausible month but `1227` is not a year, and `07052022`
    cannot be year-first because `0705` is not a year.

    The two readings are in fact DISJOINT for any real date: if `text[4:8]` is a
    plausible year (19xx/20xx) then `text[4:6]` is 19 or 20, which is not a
    month, so year-first cannot also hold. There is no genuinely ambiguous
    eight-digit date after 1900 -- which is why a sample of a few rows settles
    it and why the confidence threshold is a guard against junk rather than a
    tie-break.

    Returns None when neither hypothesis dominates. That is deliberate -- a
    column this cannot read is refused upstream rather than bucketed under a
    period that means nothing, which is how `0101` through `3112` became months.
    """
    ymd = dmy = seen = 0
    for value in values:
        text = str(value or "").strip()
        if len(text) != 8 or not text.isdigit():
            continue
        seen += 1
        # year-first: YYYYMMDD
        if 1900 <= int(text[0:4]) <= 2100 and 1 <= int(text[4:6]) <= 12:
            ymd += 1
        # day-first: DDMMYYYY
        if 1900 <= int(text[4:8]) <= 2100 and 1 <= int(text[2:4]) <= 12:
            dmy += 1
    if not seen:
        return None
    if ymd >= _LAYOUT_CONFIDENCE * seen and ymd > dmy:
        return "ymd"
    if dmy >= _LAYOUT_CONFIDENCE * seen and dmy > ymd:
        return "dmy"
    return None


def _competencia_column(
    table: Any, time_fields: Sequence[str], encoding: str = ""
) -> Any | None:
    """AAAAMM from the declared time fields, as a column.

    Two fields means year and month held apart (`ANO_CMPT`, `MES_CMPT`). One
    field is either a competence already packed year-first -- of which the first
    six characters ARE the period -- or a record date, whose layout is measured
    rather than assumed (:func:`_date_layout`).
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    present = [f for f in time_fields if f in table.schema.names]
    if not present:
        return None
    if len(present) >= 2:
        year = pc.utf8_trim_whitespace(pc.cast(table.column(present[0]), pa.string()))
        month = pc.utf8_trim_whitespace(pc.cast(table.column(present[1]), pa.string()))
        month = pc.utf8_lpad(month, 2, padding="0")
        joined = pc.binary_join_element_wise(year, month, "")
    else:
        joined = pc.utf8_trim_whitespace(pc.cast(table.column(present[0]), pa.string()))
        if encoding == "date":
            layout = _date_layout(
                joined.slice(0, min(_LAYOUT_SAMPLE, len(joined))).to_pylist())
            if layout is None:
                return None
            if layout == "dmy":
                # DDMMAAAA -> AAAAMM. Built by concatenation rather than by a
                # regex so it stays inside Arrow at national volume.
                year = pc.utf8_slice_codeunits(joined, 4, 8)
                month = pc.utf8_slice_codeunits(joined, 2, 4)
                joined = pc.binary_join_element_wise(year, month, "")
    sliced = pc.utf8_slice_codeunits(joined, 0, 6)
    return pc.if_else(pc.equal(pc.utf8_length(sliced), 6), sliced, pa.nulls(len(sliced), pa.string()))


def _lift_columns(table: Any, measures: Sequence[Measure]) -> tuple[dict[str, Any], list[str]]:
    """Every measure's `lift`, as columns rather than per-row calls.

    The mapping is exact, not an approximation of the algebra:

    * ``count``  -> a column of ones, so its sum is the row count;
    * ``sum``    -> the numeric column with nulls as zero, which contributes
      nothing, unlike a null that would poison the sum;
    * ``mean``   -> (1 where the value parses, else 0) and (the value, else 0),
      so a blank stay is an unknown length rather than a stay of no days;
    * ``ratio``  -> the value and a validity indicator.
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    out: dict[str, Any] = {}
    order: list[str] = []
    rows = table.num_rows
    for measure in measures:
        columns = measure.state_columns()
        if measure.source_field and measure.source_field in table.schema.names:
            numeric = _to_number(table.column(measure.source_field), rows)
        else:
            numeric = pa.nulls(rows, pa.float64())
        valid = pc.cast(pc.is_valid(numeric), pa.float64())
        filled = pc.fill_null(numeric, 0.0)
        if measure.kind.name == "count":
            out[columns[0]] = pa.array([1.0] * rows, pa.float64())
        elif measure.kind.name == "sum":
            out[columns[0]] = filled
        elif measure.kind.name in ("mean", "ratio"):
            first, second = columns
            if measure.kind.name == "mean":
                out[first], out[second] = valid, filled
            else:
                out[first], out[second] = filled, valid
        else:
            out[columns[0]] = filled
        order.extend(columns)
    return out, order



def _flag_partial_periods(spec: AggregateSpec, semantics: Any, report: AggregateReport,
                          wanted_years: Sequence[int], periods: Sequence[str]) -> None:
    """Name the periods this build cannot have filled completely.

    DATASUS publishes by a coordinate that is NOT the record date. Measured on
    SIH: the file published under 2022 for Acre holds 3,687 admissions (7.44%)
    that happened in 2021, the earliest in February — because a December
    admission is billed in January. So when the time axis is a record date, the
    publication years fetched do not contain their own edges.

    A `competence` axis has no such problem: the competence IS the publication
    coordinate, so every period inside the fetched years is whole.

    This does not silently widen the fetch. It says which periods are short, in
    the report and in the manifest, so a series is not read as a fall in
    admissions when it is a fall in coverage.
    """
    bindings = semantics.time_bindings()
    encoding = str((bindings.get(spec.time_binding) or {}).get("encoding") or "")
    if encoding != "date":
        return
    fetched = {int(y) for y in wanted_years}
    seen = sorted({str(p)[:4] for p in periods if p})
    partial = [
        year for year in seen
        if int(year) not in fetched            # a fragment from a neighbour
        or (int(year) + 1) not in fetched      # its own tail is billed next year
    ]
    if not partial:
        return
    report.partial_periods = tuple(sorted(set(partial)))
    report.warnings.append(
        f"the time axis {spec.time_binding!r} is a record date, so these years "
        f"are NOT complete in this build: {report.partial_periods}. A record "
        "dated December is published in the following year's files; build the "
        "next publication year too, or read these edges as short."
    )


def _fingerprint(spec: AggregateSpec, blob_digests: set[str], settings: Settings) -> str:
    """Identity of an artifact: the spec, its sources, and its semantics.

    The geography pack's checksum is in here deliberately. Changing it changes
    every health-region roll-up derived from this artifact, and an artifact that
    does not notice is stale in a way nobody can see.
    """
    from importlib.resources import files

    from .ontology import CURATION
    from .semantics.curation import curation_fingerprint

    digest = hashlib.blake2b(digest_size=16)
    digest.update(json.dumps(spec.fingerprint_payload(), sort_keys=True).encode())
    digest.update(ENGINE_VERSION.encode())
    digest.update(curation_fingerprint(CURATION).encode())
    try:
        pack = Path(str(files("pegasus_data.resources") / "geography.parquet"))
        if pack.exists():
            digest.update(hashlib.sha256(pack.read_bytes()).hexdigest().encode())
    except (ModuleNotFoundError, FileNotFoundError):  # pragma: no cover
        pass
    for blob in sorted(blob_digests):
        digest.update(blob.encode())
    return digest.hexdigest()


# --------------------------------------------------------------------- read


def _load_artifact(name: str, settings: Settings):
    import pyarrow.parquet as pq

    path = artifact_dir(name, settings) / "cells.parquet"
    if not path.exists():
        raise ArtifactMissing(
            f"{name!r} has not been built; run "
            f"`pegasus-data aggregate-build {name} --years ...` first"
        )
    manifest = json.loads(_manifest_path(name, settings).read_text(encoding="utf-8"))
    return pq.read_table(path), manifest


def _geography_pushforward(level: str, codes: Sequence[str], system: str | None,
                           report: AggregateReport) -> dict[str, str | None]:
    """`municipality -> member` for one level, or None where unmapped.

    Uses the compiled geography rather than a hierarchy of its own. `uf` comes
    from `normalize.geo.uf_from_code`, which already owns that rule.
    """
    from .geography import memberships
    from .normalize.geo import uf_from_code

    distinct = sorted({c for c in codes if c})
    if level == _BASE_LEVEL:
        return {c: c for c in distinct}
    if level == _NATIONAL_LEVEL:
        return dict.fromkeys(distinct, "BR")
    if level == _UF_LEVEL:
        return {c: uf_from_code(c) for c in distinct}
    mapping: dict[str, str | None] = {}
    contested: list[str] = []
    for code in distinct:
        found = memberships(code, system=system).get(level)
        mapping[code] = found.member_label if found else None
        if found is not None and found.contested:
            contested.append(code)
    if contested:
        report.contested = tuple(sorted({*report.contested, *contested}))
        report.warnings.append(
            f"{len(contested)} municipalities have a contested {level}; publishing "
            "systems disagree and no system was named, so one defensible answer "
            "was used. Name a system to resolve it."
        )
    return mapping


def _time_pushforward(level: str, values: Sequence[str]) -> dict[str, str | None]:
    distinct = sorted({v for v in values if v})
    if level in ("month", "competencia", TIME_KEY):
        return {v: v for v in distinct}
    if level == "year":
        return {v: v[:4] for v in distinct}
    raise AggregationRefused(
        f"unknown time level {level!r}; known levels are 'month' and 'year'"
    )


def aggregate(
    name: str,
    *,
    measures: Sequence[str] | None = None,
    by: Sequence[str] | None = None,
    where: Mapping[str, Any] | None = None,
    system: str | None = None,
    settings: Settings | None = None,
    root: str | Path | None = None,
    return_report: bool = False,
    finalize: bool = True,
) -> pa.Table | tuple[pa.Table, AggregateReport]:
    """Serve cells from a built artifact: filter, roll up, and optionally finalize.

    ``by`` names a level per axis — ``["health_region", "year", "SEXO"]``. An
    axis you do not name is **marginalised**, which is what "Total" is: the
    pushforward to a one-point space, the same operation as municipality →
    health region with a smaller target.

    No microdata is read. Every result derives from the one materialised base
    cuboid, so a total and the sum of its parts cannot disagree.

    ``finalize=False`` returns the accumulator STATE -- `los_n` and `los_sum`
    rather than `los` -- which is what a caller that intends to keep aggregating
    needs. `finalize` is a projection out of the monoid, not part of it: a mean
    finalised at municipality level and then averaged across municipalities is a
    mean of means, which is not the mean. Anything crossing a process boundary
    with more aggregation ahead of it should ask for state.
    """
    import pyarrow as pa

    from .config import load_settings
    from .measures import finalize as _finalize

    resolved = settings or load_settings(root=Path(root) if root else None)
    spec = spec_named(name)
    table, manifest = _load_artifact(name, resolved)
    report = AggregateReport(
        name=name, support=dict(manifest.get("support") or {}),
        fingerprint=str(manifest.get("fingerprint") or ""),
        years=tuple(int(y) for y in (manifest.get("years") or ())),
        uf=tuple(str(u) for u in (manifest.get("uf") or ())),
        partial_periods=tuple(str(x) for x in (manifest.get("partial_periods") or ())),
    )
    if report.uf:
        report.warnings.append(
            f"this artifact was built from {list(report.uf)} only; a municipality "
            "with no cell was NOT OBSERVED, not observed as zero, and any total "
            "here is that subset's total rather than a national one"
        )
    if report.partial_periods:
        report.warnings.append(
            f"{len(report.partial_periods)} period(s) in this artifact are known "
            "to be short because its time axis is a record date and the "
            "publication years built do not fully contain them: "
            f"{list(report.partial_periods[:6])}"
        )

    wanted = tuple(measures or [m.name for m in spec.measures])
    chosen = [spec.measure_named(m) for m in wanted]
    levels = tuple(by or ())

    columns = {c: table.column(c).to_pylist() for c in table.schema.names}
    total_rows = table.num_rows

    # --- which level applies to which axis, and what gets marginalised -------
    geography_level = next(
        (level for level in levels
         if level in (_BASE_LEVEL, _UF_LEVEL, _NATIONAL_LEVEL) or _is_classification(level)),
        None)
    time_level = next((level for level in levels if level in ("month", "year")), None)
    dimension_levels = [level for level in levels if level in spec.dimensions]
    unknown = [
        level for level in levels
        if level not in (geography_level, time_level) and level not in dimension_levels
    ]
    if unknown:
        raise AggregationRefused(
            f"unknown level(s) {unknown}; this artifact offers geography "
            f"({_BASE_LEVEL}, {_UF_LEVEL}, {_NATIONAL_LEVEL} or a classification), "
            f"time (month, year) and dimensions {list(spec.dimensions)}"
        )

    # --- additivity: marginalising an axis is summing along it --------------
    # Naming no time level marginalises time entirely; naming `year` over a
    # monthly artifact coarsens it. Both sum along time, which a stock refuses.
    rolls_up_time = time_level is None or (
        time_level == "year" and spec.time_grain != "year")
    for measure in chosen:
        if rolls_up_time:
            check_rollup(measure, "time")
        if geography_level != _BASE_LEVEL:
            check_rollup(measure, "geography")
        for dimension in spec.dimensions:
            if dimension not in dimension_levels:
                check_rollup(measure, "dimensions")
                check_dimension(measure, _is_multi_valued(spec.dataset, dimension))

    # --- pushforward maps ---------------------------------------------------
    geo_map = (
        _geography_pushforward(geography_level, columns[GEOGRAPHY_KEY], system, report)
        if geography_level else None
    )
    time_map = _time_pushforward(time_level, columns[TIME_KEY]) if time_level else None

    filters = dict(where or {})
    keep = _mask(filters, spec, columns, total_rows)

    # The merge is Arrow's grouped aggregation, not a Python loop over cells.
    # That is a property of the design rather than an optimisation: every
    # accumulator here is a commutative monoid whose merge IS a column
    # aggregate. `count` and `sum` merge by summing one column, `mean` by
    # summing (n, sum), `ratio` by summing (num, den), `min`/`max` by MIN/MAX.
    # The whole algebra maps onto group_by().aggregate() with no special cases.
    #
    # The loop this replaced cost about 13 s on a realistic national year, which
    # is not an answer a frontend can wait for.
    key_names = (
        *([geography_level] if geography_level else ()),
        *([time_level] if time_level else ()),
        *dimension_levels,
    )
    # Grouping columns get internal names. `by=["municipality"]` and
    # `by=["month"]` would otherwise collide with the artifact's own key columns
    # -- Arrow raises "Multiple matches for FieldRef" -- and renaming at the end
    # is simpler than special-casing the identity pushforward.
    GEO_TMP, TIME_TMP = "__geo__", "__time__"
    group_by = (
        *([GEO_TMP] if geography_level else ()),
        *([TIME_TMP] if time_level else ()),
        *dimension_levels,
    )
    emit_as = dict(zip(group_by, key_names, strict=True))
    mapped_geo = (
        [geo_map.get(v) for v in columns[GEOGRAPHY_KEY]] if geo_map is not None else None
    )
    mapped_time = (
        [time_map.get(v) for v in columns[TIME_KEY]] if time_map is not None else None
    )

    unmapped_mass: dict[str, float] = {}
    if mapped_geo is not None:
        # A partial classification -- `metropolitan_region` covers 1,325 of
        # ~5,570 municipalities -- makes the pushforward non-total. The lost mass
        # is REPORTED, never silently dropped: a subset total that reads as a
        # national one is the failure this layer exists to prevent.
        lost = [i for i in range(total_rows) if keep[i] and mapped_geo[i] is None]
        for measure in chosen:
            column = columns[measure.state_columns()[0]]
            total = sum(float(column[i]) for i in lost)
            if total:
                unmapped_mass[measure.name] = total
        for i in lost:
            keep[i] = False

    indices = [i for i in range(total_rows) if keep[i]]
    report.rows_read = len(indices)
    working = table.take(indices) if len(indices) != total_rows else table
    if mapped_geo is not None and geography_level:
        working = working.append_column(
            GEO_TMP, pa.array([mapped_geo[i] for i in indices], pa.string()))
    if mapped_time is not None and time_level:
        working = working.append_column(
            TIME_TMP, pa.array([mapped_time[i] for i in indices], pa.string()))

    state_columns = [c for m in chosen for c in m.state_columns()]
    # What the result carries: one finished value per measure, or the state
    # columns that produced it.
    value_columns = (
        [m.name for m in chosen] if finalize
        else [c for m in chosen for c in m.state_columns()]
    )
    out: dict[str, list[Any]] = {n: [] for n in key_names}
    for column in value_columns:
        out[column] = []

    if key_names:
        aggregated = working.group_by(list(group_by)).aggregate(
            [(c, _ARROW_MERGE[_kind_of(chosen, c).name]) for c in state_columns])
        suffixed = {c: f"{c}_{_ARROW_MERGE[_kind_of(chosen, c).name]}"
                    for c in state_columns}
        got = {n: aggregated.column(n).to_pylist() for n in aggregated.schema.names}
        order = sorted(range(aggregated.num_rows),
                       key=lambda i: tuple(str(got[n][i]) for n in group_by))
        for i in order:
            for name in group_by:
                out[emit_as[name]].append(str(got[name][i]))
            for measure in chosen:
                state = tuple(float(got[suffixed[c]][i] or 0.0)
                              for c in measure.state_columns())
                if finalize:
                    out[measure.name].append(_finalize(measure, state))
                else:
                    for column, value in zip(measure.state_columns(), state, strict=True):
                        out[column].append(value)
    else:
        # No axis named at all: one cell, everything totalled.
        for measure in chosen:
            state = tuple(_merge_column(measure, working.column(c))
                          for c in measure.state_columns())
            if finalize:
                out[measure.name].append(_finalize(measure, state))
            else:
                for column, value in zip(measure.state_columns(), state, strict=True):
                    out[column].append(value)

    result = pa.table({
        **{n: pa.array(out[n], pa.string()) for n in key_names},
        **{c: pa.array(out[c], pa.float64()) for c in value_columns},
    })
    report.cells = result.num_rows
    report.unmapped = {k: v for k, v in unmapped_mass.items() if v}
    if report.unmapped:
        report.warnings.append(
            f"rolling up to {geography_level!r} left "
            f"{max(report.unmapped.values()):,.0f} of the base measure unmapped: "
            "that classification does not cover every municipality, so this is a "
            "subset total and not a national one."
        )
    return (result, report) if return_report else result



#: How each monoid's merge is spelled as a column aggregate. The mapping is
#: total because every kind here is a commutative monoid over numbers, which is
#: exactly why the serve path needs no per-row arithmetic.
_ARROW_MERGE = {"count": "sum", "sum": "sum", "mean": "sum", "ratio": "sum",
                "min": "min", "max": "max"}


def _kind_of(measures: Sequence[Measure], state_column: str) -> Any:
    for measure in measures:
        if state_column in measure.state_columns():
            return measure.kind
    raise AggregationRefused(f"no measure owns state column {state_column!r}")


def _merge_column(measure: Measure, column: Any) -> float:
    """Reduce one state column to a scalar, the monoid's way."""
    import pyarrow.compute as pc

    if measure.kind.name == "min":
        value = pc.min(column).as_py()
        return float("inf") if value is None else float(value)
    if measure.kind.name == "max":
        value = pc.max(column).as_py()
        return float("-inf") if value is None else float(value)
    value = pc.sum(column).as_py()
    return 0.0 if value is None else float(value)


def _mask(filters: Mapping[str, Any], spec: AggregateSpec,
          columns: Mapping[str, list[Any]], total_rows: int) -> list[bool]:
    """Row filter, evaluated once per column rather than once per row."""
    keep = [True] * total_rows
    for key, value in filters.items():
        wanted = {str(v) for v in
                  (value if isinstance(value, (list, tuple, set)) else [value])}
        if key in ("period", TIME_KEY, "month"):
            source = [str(v) for v in columns[TIME_KEY]]
        elif key == "year":
            source = [str(v)[:4] for v in columns[TIME_KEY]]
        elif key == _UF_LEVEL:
            from .normalize.geo import uf_from_code

            source = [str(uf_from_code(str(v)) or "") for v in columns[GEOGRAPHY_KEY]]
        elif key in (_BASE_LEVEL, GEOGRAPHY_KEY):
            source = [str(v) for v in columns[GEOGRAPHY_KEY]]
        elif key in spec.dimensions:
            source = [str(v) for v in columns[key]]
        else:
            raise AggregationRefused(
                f"cannot filter on {key!r}; this artifact has "
                f"{[_BASE_LEVEL, _UF_LEVEL, 'year', 'period', *spec.dimensions]}"
            )
        for i in range(total_rows):
            if keep[i] and source[i] not in wanted:
                keep[i] = False
    return keep


def _is_classification(level: str) -> bool:
    from .geography import classifications

    return level in classifications()


@lru_cache(maxsize=256)
def _is_multi_valued(dataset: str, field_name: str) -> bool:
    """`CODANOMAL` holds up to five ICD codes; a row lands in several cells."""
    from .catalog.store import Catalog
    from .config import load_settings

    try:
        settings = load_settings()
        if not settings.catalog_path.is_file():
            return False
        catalog = Catalog(settings.catalog_path, read_only=True)
        try:
            rows = list(catalog.query(
                "SELECT multi_valued FROM variable_docs WHERE field_name = ? LIMIT 1",
                (field_name.upper(),)))
        finally:
            catalog.close()
        return bool(rows and rows[0]["multi_valued"])
    except Exception:  # noqa: BLE001 - an unreadable catalog must not block a read
        return False


