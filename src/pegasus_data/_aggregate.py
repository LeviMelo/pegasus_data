"""`aggregate()` — persistent, composable, geography × time analytical cells.

The dominant PegaSUS workload is geography × time → measures, and answering it
from microdata is not viable at request time: `fetch("SIH-RD", uf="AC",
years=2022)` takes 130 s for 49,547 admissions, while the same rows at
municipality × month × sex are 989 cells. Fifty times smaller, and Acre is 0.4%
of national SIH volume.

So an aggregate is built once, offline, and served cheaply. Two surfaces:

* :func:`build_aggregate` — maintainer, expensive, writes an artifact under the
  lake. Its rows come from :func:`pegasus_data.fetch`, chunk by chunk (a state-year at a time, to bound memory), NOT from
  the lake or from :func:`pegasus_data.query`: a built lake is never used by an aggregate build, and the planner's
  lake/fetch/hybrid choice is bypassed (hence `_physical_geography`, which asks the plan only which files a year is
  published as). Routing it through `query()` with `select=` is the open alternative (review of the read path, 2026-10-14,
  finding 30).
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
from dataclasses import dataclass, field, replace
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
from .semantics.epoch import curated

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

    from .config import Settings

__all__ = [
    "AggregateReport",
    "AggregateSpec",
    "aggregate",
    "build_aggregate",
    "declared_measures",
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
    #: `dimension -> {code -> label}`, for the interface. Same ladder as the
    #: names: the analyst's statement about THIS artifact wins, the reference
    #: tables fill the rest, the raw code is the honest last resort. Exists
    #: because reference tables are sometimes truncated at source (`Bra` for
    #: Branca) or simply absent (SIM's SEXO has no binding at all).
    level_labels: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    #: What to call this artifact on screen.
    label: str = ""
    #: A derived age-band dimension, or None. Declared rather than raw because
    #: no raw column holds an age in years: every system packs a unit into the
    #: value or a sibling column, each its own way (see _age.py). The band
    #: column participates in `dimensions` like any other -- serve, filters
    #: and the descriptor need never know it was derived.
    age: Any = None
    #: Banded NUMERIC dimensions (birth weight, gestation weeks): the same
    #: derivation as age minus the unit decoding. Tuple of
    #: `_age.NumericBandDimension`.
    band_dims: tuple[Any, ...] = ()
    #: Count EVENTS of this declared type (``curation/datasets``, ADR-0137)
    #: rather than rows: SIH's continuation AIHs are one hospitalisation.
    event_type: str | None = None
    #: ``dimension -> code structure`` (``code_structure()``), so a query can
    #: roll a classifier up its tree: ``by=["CAUSABAS@category"]``.
    dimension_structures: Mapping[str, str] = field(default_factory=dict)

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
            "event_type": self.event_type,
            "dimension_structures": dict(self.dimension_structures),
            "band_dimensions": [
                {"name": b.name, "field": b.field_name, "bands": list(b.bands)}
                for b in self.band_dims
            ],
            "age": (
                {"name": self.age.name, "encoding": self.age.encoding,
                 "fields": list(self.age.fields), "bands": list(self.age.bands)}
                if self.age is not None else None
            ),
            "measures": [
                {
                    "name": m.name, "kind": m.kind.name,
                    "field": list(m.source_fields),
                    "unit": m.unit, "additive_over": sorted(m.additive_over),
                    "time_reducer": m.time_reducer,
                }
                for m in self.measures
            ],
        }


def _uf_basis_note(dataset: str, geography_field: str, ufs: Sequence[str]) -> str:
    """What a state build means when the dataset's files are published by another geography than its cells' key.

    ``uf`` selects PUBLICATIONS, never records (ADR-0043), so a state build keeps whatever its files hold. SIH-RD's
    files are by hospital state (``setting`` in ``curation/roles.yml``) and its cells are keyed by residence: the
    municipalities of the state lose the residents treated in other states, so even the cells that exist are short,
    which "no cell means not observed" does not say. Empty when the files are by the cells' own geography (SIM-DO,
    SINASC-DN: by residence), or when no setting is declared.
    """
    from .linkage.roles import dataset_roles

    try:
        roles = dataset_roles(dataset)
    except KeyError:
        return ""
    setting = roles.roles.get(roles.setting) if roles.setting else None
    if setting is None or setting.column.upper() == geography_field.upper():
        return ""
    return (
        f"{dataset} files are published by {setting.column} ({roles.setting}) and the cells are keyed by "
        f"{geography_field}: the cells of {list(ufs)} omit the records of their municipalities that were published in "
        "other states' files, so a cell that exists is short too; only a build of every state is complete"
    )


def _physical_geography(dataset: str, year: int, settings: Settings) -> tuple[str, ...] | None:
    """The publications a national read of this dataset-year selects: ("BR",)
    for one national file, () for a dataset with no state axis, the states
    otherwise; None when the year cannot be planned (per-state chunks)."""
    import sqlite3
    import time

    from ._query_engine.planner import plan
    from ._request import DatasetUnknown

    # A catalog that does not know the dataset yet (none at all, or no family of it: a fresh install, which `fetch`
    # discovers on demand) keeps the per-state chunks. A locked catalog is retried once, then raised, and any other
    # planning error is raised as it is: swallowing it turned a year held as one national file into 27 state probes
    # that all failed the same way (`NothingPublished` per chunk is recorded; this is not that).
    for attempt in (1, 2):
        try:
            retrieval = plan(dataset, period=str(year), geography="BR", settings=settings).retrieval
        except (FileNotFoundError, DatasetUnknown):
            return None
        except sqlite3.OperationalError:
            if attempt == 2:
                raise
            time.sleep(0.25)
        else:
            return retrieval.geography_for(year) or ()
    return None


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
    from .config import curation_root

    return curation_root() / "aggregates"


def load_specs(root: Path | None = None) -> dict[str, AggregateSpec]:
    """Every declared aggregate, keyed by name."""
    from .semantics.curation import read_yaml

    folder = _spec_root(root)
    out: dict[str, AggregateSpec] = {}
    if not folder.exists():
        return out
    for path in sorted(folder.glob("*.yml")):
        data = read_yaml(path, missing_ok=True) or {}
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
            level_labels={
                str(dim): {str(c): str(lbl) for c, lbl in (body or {}).items()}
                for dim, body in (data.get("level_labels") or {}).items()
            },
            label=str(data.get("label") or ""),
            age=_parse_age(data.get("age_dimension")),
            band_dims=_parse_bands(data.get("band_dimensions")),
            event_type=str(data["event_type"]) if data.get("event_type") else None,
            dimension_structures={
                str(k).upper(): str(v).upper() for k, v in (data.get("dimension_structures") or {}).items()
            },
        )
        spec = out[name]
        # Every derived dimension joins the declared ones, carrying its own
        # labels: the bands are the analyst's construction, so the spec IS the
        # top rung of the ladder here, not an override of a table.
        derived = ([spec.age] if spec.age is not None else []) + list(spec.band_dims)
        if derived:
            out[name] = replace(
                spec,
                dimensions=(*spec.dimensions, *(d.name for d in derived)),
                dimension_labels={
                    **spec.dimension_labels,
                    **{d.name: d.label for d in derived},
                },
                level_labels={
                    **spec.level_labels,
                    **{d.name: d.band_levels() for d in derived},
                },
            )
    return out


def _parse_age(body: Any):
    from ._age import parse_age_dimension

    try:
        return parse_age_dimension(body)
    except ValueError as exc:
        raise AggregationRefused(str(exc)) from exc


def _parse_bands(body: Any) -> tuple[Any, ...]:
    from ._age import parse_band_dimensions

    try:
        return parse_band_dimensions(body)
    except ValueError as exc:
        raise AggregationRefused(str(exc)) from exc


def spec_named(name: str, root: Path | None = None) -> AggregateSpec:
    specs = load_specs(root)
    if name not in specs:
        raise AggregationRefused(
            f"no aggregate spec named {name!r}; declared: {sorted(specs)}"
        )
    return specs[name]


@curated
def declared_measures() -> dict[tuple[str, str], tuple[Measure, ...]]:
    """``(roles file's dataset, column) -> the measures the aggregate recipes declare over that column``.

    The recipes are where the project says along which axes a column's quantity may be added (`additive_over`, and the
    `time_reducer` of a stock); the roles layer states what the number is and in which unit, not how it combines.
    A column read through several recipes is listed under each (`measures.measure_of_role` keeps what all of them allow)."""
    from .semantics.column_roles import declared_key

    out: dict[tuple[str, str], list[Measure]] = {}
    for spec in load_specs().values():
        try:
            dataset = declared_key(spec.dataset)
        except KeyError:
            continue
        for measure in spec.measures:
            for column in measure.source_fields:
                out.setdefault((dataset, column.upper()), []).append(measure)
    return {key: tuple(found) for key, found in out.items()}


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
    #: A state build whose files are published by another geography than the cells' key (SIH: files by hospital state,
    #: cells by residence municipality): even a cell that exists is short. Said in the report and the manifest.
    uf_basis_note: str = ""
    #: The (year, state) chunks that had no publication, so no cells: a hole in the series that is a gap, not a zero.
    missing_chunks: list[str] = field(default_factory=list)
    #: Rows read that no cell holds: no municipality, or a period that is not a month of a plausible year.
    unkeyed_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    fingerprint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "cells": self.cells, "rows_read": self.rows_read,
            "years": list(self.years), "support": self.support,
            "unmapped": self.unmapped, "contested": list(self.contested),
            "uf": list(self.uf),
            "uf_basis_note": self.uf_basis_note,
            "partial_periods": list(self.partial_periods),
            "missing_chunks": list(self.missing_chunks),
            "unkeyed_rows": self.unkeyed_rows,
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
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from ._availability import field_available
    from .config import load_settings
    from .persist.staging import staged_file
    from .retrieve import NothingPublished
    from .retrieve import fetch as _fetch

    resolved = settings or load_settings(root=Path(root) if root else None)
    spec = spec_named(name)
    semantics = _resolve_semantics(spec)
    from .semantics.event_types import event_type as _event_type
    from .semantics.event_types import events_of

    event = _event_type(spec.dataset, spec.event_type) if spec.event_type else None

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
    # Only the columns the recipe reads: a national SIM year is 87 columns,
    # and holding all of them peaked a 2010-2023 build at 12.75 GB (2026-10-04).
    derived_names = {d.name for d in ([spec.age] if spec.age is not None else []) + list(spec.band_dims)}
    needed = sorted({
        *geography_fields, *time_fields,
        *(d for d in spec.dimensions if d not in derived_names),
        *(f for f in (spec.age.fields if spec.age is not None else ())),
        *(b.field_name for b in spec.band_dims),
        *(f for m in spec.measures for f in m.source_fields),
        *((event.status_column,) if event is not None and event.status_column else ()),
        *(event.consolidation_key if event is not None else ()),
        # the source's own duplicate flag (SINAN's NDUPLIC_N, ADR-0159), null where a form lacks it
        *((event.duplicates_flag[0],) if event is not None and event.duplicates_flag else ()),
    })

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
    if report.uf:
        report.uf_basis_note = _uf_basis_note(spec.dataset, geography_field, report.uf)
        if report.uf_basis_note:
            report.warnings.append(report.uf_basis_note)
    # Asked of the curation now, while the catalog the build reads is at hand, and written into the manifest: serving
    # reads what the build knew, so an artifact served without its catalog still refuses a double-counting roll-up.
    multi_valued = sorted(_curated_multi_valued(spec.dataset, spec.dimensions, resolved))

    # One grouped Arrow table per chunk; merged once at the end (_merge_cells).
    cells: list[Any] = []
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
        # A year DATASUS publishes as one national file is read from it, not
        # from its 27 state files: the same records, read once (handoff §1.7).
        out: list[tuple[int, str | Sequence[str] | None]] = []
        for year in sorted(wanted_years):
            physical = _physical_geography(spec.dataset, year, resolved)
            # SINAN publishes one national file and no state axis at all.
            out.extend([(year, None)] if physical == () else [(year, "BR")] if physical == ("BR",)
                       else [(year, u) for u in _ALL_UFS])
        return out

    chunks = _chunks()
    national_fallback = not report.uf

    for year, chunk_uf in chunks:
        # `fetch()` is the retrieval path of a build (not `query()`: see the module docstring). It unions
        # schema generations with structural nulls and returns raw codes, which
        # is what `lift` needs.
        try:
            table, fetch_report = _fetch(
                spec.dataset, uf=chunk_uf, years=year, settings=resolved,
                report=True, labels=False, provenance=True,
                columns=needed, on_missing_column="null_fill",
            )
        except NothingPublished:
            # An empty (year, UF) chunk is DATA for the fallback below, not an
            # error: a dataset published one national file per year -- SINAN's
            # agravos -- answers every per-UF probe with nothing, and raising
            # here made the national fallback unreachable for exactly the
            # datasets it was written for. It is RECORDED all the same: a state-year absent on the server
            # leaves a hole in the series that is a gap, never a zero.
            if national_fallback:
                report.missing_chunks.append(f"{year} {chunk_uf}")
                continue
            raise
        report.rows_read += table.num_rows
        if event is not None:
            table = events_of(table, event)
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
            def _support_of(dimension: str, year: int = year) -> str:
                for band in spec.band_dims:
                    if dimension == band.name:
                        return str(field_available(
                            spec.dataset, band.field_name, year, settings=resolved))
                if spec.age is not None and dimension == spec.age.name:
                    # Derived: available exactly when its sources are. The
                    # weakest source decides -- a band computed from an absent
                    # unit column is not "present".
                    return min(
                        str(field_available(spec.dataset, f, year, settings=resolved))
                        for f in spec.age.fields
                    )
                return str(field_available(spec.dataset, dimension, year, settings=resolved))

            report.support[str(year)] = {
                dimension: _support_of(dimension) for dimension in spec.dimensions
            }

        # lift + merge, columnar. Each accumulator's lift is a column
        # expression and its merge is a sum, so the whole build is one
        # group_by. The row loop this replaced ran at about 1.4 ms per
        # admission -- fine for one state-year, and roughly five hours for a
        # national one, which is not a build anybody would run.
        keyed_and_mask = _key_columns(
            table, geography_field, time_fields, spec.dimensions, names,
            encoding=time_encoding, age=spec.age, band_dims=spec.band_dims)
        if keyed_and_mask is None:
            report.warnings.append(
                f"{year} {chunk_uf}: no usable geography/time values; skipped. If the time "
                f"axis is a date, {list(time_fields)} may hold a layout neither "
                "AAAAMMDD nor DDMMAAAA explains -- which is refused rather than "
                "bucketed under a period that means nothing."
            )
            continue
        keyed, keep_mask = keyed_and_mask
        report.unkeyed_rows += table.num_rows - int(pc.sum(keep_mask).as_py() or 0)
        _accumulate(cells, table.filter(keep_mask), keyed, spec)
        if year not in report.years:
            report.years = (*report.years, year)

    if not cells and national_fallback:
        # Every state came back empty, which for a UF-partitioned dataset would
        # mean nothing was published at all. More likely the dataset is NOT
        # partitioned by state -- IBGE's population files are national, and so
        # is anything published one file a year. Ask for it whole.
        report.missing_chunks = []          # the whole-year read below replaces the per-state probes
        report.warnings.append(
            "no state-partitioned files found; retrying as a single national "
            "fetch. This dataset appears not to be published per UF, so the "
            "build holds a whole year at once."
        )
        for year in sorted(wanted_years):
            table, fetch_report = _fetch(
                spec.dataset, uf=None, years=year, settings=resolved,
                report=True, labels=False, provenance=True,
                columns=needed, on_missing_column="null_fill",
            )
            report.rows_read += table.num_rows
            if event is not None:
                table = events_of(table, event)
            names = set(table.schema.names)
            if [f for f in (geography_field, *time_fields) if f not in names]:
                continue
            if "_blob_sha256" in names:
                for digest in set(table.column("_blob_sha256").to_pylist()):
                    if digest:
                        blob_digests.add(str(digest))
            keyed_and_mask = _key_columns(
                table, geography_field, time_fields, spec.dimensions, names,
                encoding=time_encoding, age=spec.age, band_dims=spec.band_dims)
            if keyed_and_mask is None:
                continue
            keyed, keep_mask = keyed_and_mask
            report.unkeyed_rows += table.num_rows - int(pc.sum(keep_mask).as_py() or 0)
            _accumulate(cells, table.filter(keep_mask), keyed, spec)
            if year not in report.years:
                report.years = (*report.years, year)
            report.warnings.extend(fetch_report.warnings[:3])

    if not cells:
        raise AggregationRefused(
            f"{name}: no cells produced for years {sorted(wanted_years)}"
        )
    if report.unkeyed_rows:
        report.warnings.append(
            f"{report.unkeyed_rows:,} of {report.rows_read:,} rows read have no municipality or no valid period "
            "(a month 01-12 of a year 1900-2200) and are in no cell"
        )
    # What the build did not produce is said, in the report and the manifest, never left as a shorter series.
    no_cells = sorted(set(wanted_years) - set(report.years))
    if no_cells:
        report.warnings.append(f"no cells for year(s) {no_cells}: nothing was read or nothing usable in them")
    if report.missing_chunks:
        by_year: dict[str, int] = {}
        for chunk in report.missing_chunks:
            by_year[chunk.split()[0]] = by_year.get(chunk.split()[0], 0) + 1
        report.warnings.append(
            f"{len(report.missing_chunks)} (year, state) chunk(s) had no publication, so no cells: "
            + ", ".join(f"{y}: {n}" for y, n in sorted(by_year.items()))
            + " (named in missing_chunks); those states are NOT OBSERVED in those years, not zero"
        )

    key_names = (GEOGRAPHY_KEY, TIME_KEY, *spec.dimensions)
    arrow = _merge_cells(cells, key_names, spec)
    report.cells = arrow.num_rows
    _flag_partial_periods(spec, semantics, report, wanted_years, arrow.column(TIME_KEY).to_pylist())
    report.fingerprint = _fingerprint(spec, blob_digests, resolved)

    target = artifact_dir(name, resolved)
    target.mkdir(parents=True, exist_ok=True)
    with staged_file(target / "cells.parquet") as staged:
        pq.write_table(arrow, staged, compression="zstd", compression_level=9)
    manifest_payload = json.dumps({
        "name": name,
        "spec": spec.fingerprint_payload(),
        "fingerprint": report.fingerprint,
        "engine_version": ENGINE_VERSION,
        "cells": report.cells,
        "rows_read": report.rows_read,
        "years": list(report.years),
        "uf": list(report.uf),
        "uf_basis_note": report.uf_basis_note,
        "multi_valued_dimensions": multi_valued,
        "support": report.support,
        "partial_periods": list(report.partial_periods),
        "missing_chunks": list(report.missing_chunks),
        "unkeyed_rows": report.unkeyed_rows,
        "key_columns": list(key_names),
        "warnings": report.warnings,
    }, indent=2, ensure_ascii=False) + "\n"
    # Atomic, like the cells write above it. A plain write_text left a window
    # where a killed build (or a concurrent reader) paired fresh cells with a
    # torn or stale manifest -- and the mtime caches key on BOTH files, so the
    # pair must move together or not at all.
    with staged_file(_manifest_path(name, resolved)) as staged_manifest:
        staged_manifest.write_text(manifest_payload, encoding="utf-8")
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


def _reductions(spec: AggregateSpec) -> dict[str, str]:
    """Each state column's merge: min/max for the extremes, a sum for every other kind."""
    return {column: (measure.kind.name if measure.kind.name in ("min", "max") else "sum")
            for measure in spec.measures for column in measure.state_columns()}


def _accumulate(cells: list, table: Any, keyed: dict, spec: AggregateSpec) -> None:
    """Lift and group one chunk; the chunks are merged once, by ``_merge_cells``.

    The merge is a commutative monoid, which is exactly why a national build can
    be assembled a chunk at a time: the order chunks arrive in cannot change the
    artifact, and neither can how they are divided. Each chunk stays an Arrow
    table: merging a million cells a year through a Python dict was most of a
    national cause-of-death build (2026-10-04).
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    lifted, state_names = _lift_columns(table, spec.measures)
    reduction = _reductions(spec)
    grouped = pa.table({**keyed, **lifted}).group_by(list(keyed)).aggregate(
        [(name, reduction[name]) for name in state_names])
    grouped = grouped.rename_columns(
        [n if n in keyed else n.rsplit("_", 1)[0] for n in grouped.schema.names])
    cells.append(pa.table({
        **{k: pc.cast(grouped.column(k), pa.string()) for k in keyed},
        **{c: _filled(_kind_of(spec.measures, c), pc.cast(grouped.column(c), pa.float64())) for c in state_names},
    }))


def _merge_cells(cells: list, key_names: Sequence[str], spec: AggregateSpec) -> Any:
    """The chunks' cells merged by the monoid, one row per key, sorted by key."""
    import pyarrow as pa

    reduction = _reductions(spec)
    whole = pa.concat_tables(cells, promote_options="default")
    merged = whole.group_by(list(key_names)).aggregate([(c, reduction[c]) for c in spec.state_columns()])
    merged = merged.rename_columns(
        [n if n in key_names else n.rsplit("_", 1)[0] for n in merged.schema.names])
    merged = merged.select([*key_names, *spec.state_columns()])
    return merged.sort_by([(k, "ascending") for k in key_names])


def _key_columns(table: Any, geography_field: str, time_fields: Sequence[str],
                 dimensions: Sequence[str], names: set[str],
                 encoding: str = "", age: Any = None,
                 band_dims: Sequence[Any] = (),
                 ) -> tuple[dict[str, Any], Any] | None:
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
    banded = {b.name: b for b in band_dims}
    for dimension in dimensions:
        if dimension in banded:
            out[dimension] = pc.filter(banded[dimension].column(table), keep)
        elif age is not None and dimension == age.name:
            # Derived, not read: decoded to years by the system's own
            # convention and banded per the spec (see _age.py). Undecodable
            # ages land in their own level rather than vanishing.
            from ._age import band_column, years_column

            out[dimension] = pc.filter(band_column(age, years_column(age, table)), keep)
        elif dimension in names:
            column = pc.utf8_trim_whitespace(pc.cast(table.column(dimension), pa.string()))
            out[dimension] = pc.filter(pc.fill_null(column, ""), keep)
        else:
            # Structurally absent in this generation. An empty category is not
            # "unknown" -- the support mask is what says the column did not
            # exist -- but the cell still has to exist so its measures are not
            # silently lost.
            # `or 0`: Arrow sums an empty mask to null, not to nought.
            kept = int(pc.sum(pc.cast(keep, pa.int64())).as_py() or 0)
            out[dimension] = pa.array([""] * kept, pa.string())
    # The mask goes back WITH the keys. The keys are filtered by it; measures
    # must be lifted from a table filtered the same way, and returning only
    # the keys let the two drift -- length-mismatch crash on the first dataset
    # with an undecodable row, silent misalignment never (Arrow validates).
    return out, keep


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


#: AAAAMM: a year 1900-2200 and a month 01-12 (`normalize.time.competencia_to_year_month`'s own bounds).
_PERIOD = r"^(19\d\d|20\d\d|21\d\d|2200)(0[1-9]|1[0-2])$"


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
        column = table.column(present[0])
        if encoding == "date" and (pa.types.is_date(column.type) or pa.types.is_timestamp(column.type)):
            # a column already typed as a date (SINAN's, from its DBF header) has no layout to guess
            return pc.strftime(column, format="%Y%m")
        joined = pc.utf8_trim_whitespace(pc.cast(column, pa.string()))
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
    # a period is a month of a plausible year, as `normalize.time.competencia_to_year_month` judges it: the length alone
    # let `00000000` and `20229999` become periods 000000 and 202299 (month 99), each a cell of its own
    valid = pc.fill_null(pc.match_substring_regex(sliced, _PERIOD), False)
    return pc.if_else(valid, sliced, pa.nulls(len(sliced), pa.string()))


def _lift_columns(table: Any, measures: Sequence[Measure]) -> tuple[dict[str, Any], list[str]]:
    """Every measure's `lift`, as columns rather than per-row calls.

    The mapping is exact, not an approximation of the algebra:

    * ``count``  -> a column of ones, so its sum is the row count;
    * ``sum``    -> the numeric column, a null staying null: it contributes
      nothing to a cell that has other values, and a cell with none has no sum
      (null), not a sum of zero;
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
        present = [f for f in measure.source_fields if f in table.schema.names]
        if present:
            # Several columns sum row-wise (null contributes nothing, but a
            # row where NO column parses stays null, not zero).
            numeric = _to_number(table.column(present[0]), rows)
            for extra in present[1:]:
                more = _to_number(table.column(extra), rows)
                numeric = pc.if_else(
                    pc.is_valid(numeric),
                    pc.add(pc.fill_null(numeric, 0.0), pc.fill_null(more, 0.0)),
                    more,
                )
        else:
            numeric = pa.nulls(rows, pa.float64())
        valid = pc.cast(pc.is_valid(numeric), pa.float64())
        filled = pc.fill_null(numeric, 0.0)
        if measure.kind.name == "count":
            out[columns[0]] = pa.array([1.0] * rows, pa.float64())
        elif measure.kind.name == "sum":
            out[columns[0]] = numeric      # a null stays null: a cell with no value has no sum, not a sum of zero
        elif measure.kind.name in ("mean", "ratio"):
            first, second = columns
            if measure.kind.name == "mean":
                out[first], out[second] = valid, filled
            else:
                out[first], out[second] = filled, valid
        elif measure.kind.name == "moments":
            n, total, squares = columns
            out[n], out[total], out[squares] = valid, filled, pc.multiply(filled, filled)
        elif measure.kind.name == "logmoments":
            # a value that is not positive has no logarithm: out of the state, like a blank
            n, total, squares = columns
            positive = pc.and_(pc.is_valid(numeric), pc.greater(pc.fill_null(numeric, 0.0), 0.0))
            logs = pc.if_else(positive, pc.ln(pc.if_else(positive, numeric, 1.0)), 0.0)
            out[n], out[total], out[squares] = pc.cast(positive, pa.float64()), logs, pc.multiply(logs, logs)
        elif measure.kind.name in ("min", "max"):
            # The fill is the kind's IDENTITY, not zero: a blank lifted to 0.0
            # would drag every minimum to nought and hand every maximum a floor.
            identity = measure.kind.identity()[0]
            out[columns[0]] = pc.fill_null(numeric, identity)
        else:
            raise AggregationRefused(
                f"no columnar lift for kind {measure.kind.name!r}; a new kind "
                "must be added here explicitly, because the generic fallback "
                "this replaced summed whatever it was handed"
            )
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

    from .config import curation_root
    from .semantics.curation import curation_fingerprint

    digest = hashlib.blake2b(digest_size=16)
    digest.update(json.dumps(spec.fingerprint_payload(), sort_keys=True).encode())
    digest.update(ENGINE_VERSION.encode())
    digest.update(curation_fingerprint(curation_root()).encode())
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


@lru_cache(maxsize=8)
def _read_artifact(cells_path: str, cells_mtime_ns: int,
                   manifest_path: str, manifest_mtime_ns: int):
    """The parquet and manifest, read once per on-disk version.

    Keyed on mtime rather than content: a rebuild writes new files, the key
    changes, the stale entry ages out of the LRU. Without this every request
    re-read a multi-megabyte parquet to answer a question about it.
    """
    import pyarrow.parquet as pq

    del cells_mtime_ns, manifest_mtime_ns  # cache key only
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return pq.read_table(cells_path), manifest


def _load_artifact(name: str, settings: Settings):
    path = artifact_dir(name, settings) / "cells.parquet"
    if not path.exists():
        raise ArtifactMissing(
            f"{name!r} has not been built; run "
            f"`pegasus-data aggregate-build {name} --years ...` first"
        )
    manifest_path = _manifest_path(name, settings)
    return _read_artifact(
        str(path), path.stat().st_mtime_ns,
        str(manifest_path), manifest_path.stat().st_mtime_ns,
    )


def _geography_pushforward(level: str, codes: Sequence[str], system: str | None,
                           report: AggregateReport) -> dict[str, str | None]:
    """`municipality -> member` for one level, or None where unmapped.

    Uses the compiled geography rather than a hierarchy of its own. `uf` comes
    from `normalize.geo.uf_from_code`, which already owns that rule.
    """
    from .normalize.geo import uf_from_code

    distinct = sorted({str(c) for c in codes if c})
    if level == _BASE_LEVEL:
        return {c: c for c in distinct}
    if level == _NATIONAL_LEVEL:
        return dict.fromkeys(distinct, "BR")
    if level == _UF_LEVEL:
        return {c: uf_from_code(c) for c in distinct}
    mapping, contested = _classification_map(level, system, tuple(distinct))
    if contested:
        report.contested = tuple(sorted({*report.contested, *contested}))
        report.warnings.append(
            f"{len(contested)} municipalities have a contested {level}; publishing "
            "systems disagree and no system was named, so one defensible answer "
            "was used. Name a system to resolve it."
        )
    return mapping


@lru_cache(maxsize=64)
def _classification_map(
    level: str, system: str | None, codes: tuple[str, ...]
) -> tuple[dict[str, str | None], tuple[str, ...]]:
    """`code -> member label` for one classification, resolved once.

    5,570 `memberships()` lookups cost ~0.9 s, and the answer depends only on
    the level, the system and the code set -- none of which change between two
    requests for the same artifact. Hashing the 5,570-tuple key costs a
    fraction of a millisecond; recomputing the mapping cost a visible share of
    every classification roll-up.
    """
    from .geography import memberships

    mapping: dict[str, str | None] = {}
    contested: list[str] = []
    for code in codes:
        found = memberships(code, system=system).get(level)
        mapping[code] = found.member_label if found else None
        if found is not None and found.contested:
            contested.append(code)
    return mapping, tuple(contested)


@lru_cache(maxsize=64)
def _tree_pushforward(structure: str, level: str, codes: tuple[str, ...]) -> dict[str, str | None]:
    """``code -> its ancestor at level`` in a code tree, or None off the tree.

    SIM writes a 3-character category as ``I64X``; that filler is the category.
    """
    from .semantics.code_structures import code_structure

    tree = code_structure(structure)
    parent = dict(zip(tree.column("code").to_pylist(), tree.column("parent").to_pylist(), strict=True))
    node_level = dict(zip(tree.column("code").to_pylist(), tree.column("level").to_pylist(), strict=True))
    if level not in set(node_level.values()):
        raise AggregationRefused(f"{structure} has no level {level!r}; it has {sorted(set(node_level.values()))}")
    out: dict[str, str | None] = {}
    for code in codes:
        node: str | None = str(code).strip().upper().replace(".", "")
        if node and len(node) == 4 and node.endswith("X") and node[:3] in node_level:
            node = node[:3]
        while node is not None and node in node_level and node_level[node] != level:
            node = parent.get(node)
        out[code] = node if node is not None and node_level.get(node) == level else None
    return out


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
        uf_basis_note=str(manifest.get("uf_basis_note") or ""),
        partial_periods=tuple(str(x) for x in (manifest.get("partial_periods") or ())),
    )
    if report.uf:
        report.warnings.append(
            f"this artifact was built from {list(report.uf)} only; a municipality "
            "with no cell was NOT OBSERVED, not observed as zero, and any total "
            "here is that subset's total rather than a national one"
        )
        if report.uf_basis_note:
            report.warnings.append(report.uf_basis_note)
    if report.partial_periods:
        report.warnings.append(
            f"{len(report.partial_periods)} period(s) in this artifact are known "
            "to be short because its time axis is a record date and the "
            "publication years built do not fully contain them: "
            f"{list(report.partial_periods[:6])}"
        )

    wanted = tuple(measures or [m.name for m in spec.measures])
    chosen = [spec.measure_named(m) for m in wanted]
    # Deduplicated, order kept: grouping by an axis twice is grouping by it
    # once, and Arrow would otherwise return two identically named columns --
    # which downstream reads as a KeyError the route misreports as a missing
    # artifact.
    levels = tuple(dict.fromkeys(by or ()))

    # --- which level applies to which axis, and what gets marginalised -------
    geography_level = next(
        (level for level in levels
         if level in (_BASE_LEVEL, _UF_LEVEL, _NATIONAL_LEVEL) or _is_classification(level)),
        None)
    time_level = next((level for level in levels if level in ("month", "year")), None)
    dimension_levels = [level for level in levels if level in spec.dimensions]
    # `CAUSABAS@category`: a classifier rolled up its code tree (DESIGN §3.4).
    tree_levels = [level for level in levels
                   if "@" in level and level.split("@", 1)[0] in spec.dimensions]
    unknown = [
        level for level in levels
        if level not in (geography_level, time_level) and level not in dimension_levels
        and level not in tree_levels
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
    # A stock with a declared time reducer (CNES beds: mean) is not summed
    # along time: each month is totalled over the other axes, then the months
    # are reduced (OQ-14). The reduction yields finished values only.
    reduced = [m for m in chosen if rolls_up_time and "time" not in m.additive_over and m.time_reducer]
    if reduced and not finalize:
        raise AggregationRefused(
            f"{[m.name for m in reduced]} reduce over time ({reduced[0].time_reducer}); a reduced "
            "value is finished, not a state. Ask for months (by=[..., 'month']) to keep states.")
    several_per_row: frozenset[str] | None = None
    for measure in chosen:
        if rolls_up_time and measure not in reduced:
            check_rollup(measure, "time")
        if geography_level != _BASE_LEVEL:
            check_rollup(measure, "geography")
        for dimension in spec.dimensions:
            if dimension not in dimension_levels:
                check_rollup(measure, "dimensions")
                if several_per_row is None:
                    several_per_row = _served_multi_valued(spec, manifest, resolved)
                check_dimension(measure, dimension in several_per_row)

    # --- pushforward maps ---------------------------------------------------
    # The RULE for each level is decided in Python over the DISTINCT codes --
    # a few thousand lookups, where the ownership of `uf_from_code` and
    # `memberships` lives. Applying it to 400k rows is `index_in` + `take`,
    # with an unmapped code flowing through as a null.
    import pyarrow.compute as pc

    geo_column = table.column(GEOGRAPHY_KEY)
    time_column = table.column(TIME_KEY)

    def _apply(mapping: dict[str, str | None], column: Any) -> Any:
        keys = pa.array(list(mapping.keys()), pa.string())
        values = pa.array(list(mapping.values()), pa.string())
        return pc.take(values, pc.index_in(column, value_set=keys))

    geo_map = (
        _geography_pushforward(
            geography_level, pc.unique(geo_column).to_pylist(), system, report)
        if geography_level else None
    )
    time_map = (
        _time_pushforward(time_level, pc.unique(time_column).to_pylist())
        if time_level else None
    )
    mapped_geo = _apply(geo_map, geo_column) if geo_map is not None else None
    mapped_trees: dict[str, Any] = {}
    for level in tree_levels:
        dimension, tree_level = level.split("@", 1)
        structure = spec.dimension_structures.get(dimension.upper())
        if structure is None:
            raise AggregationRefused(
                f"{dimension} declares no code structure in {name!r}; add it to dimension_structures")
        column = pc.cast(table.column(dimension), pa.string())
        mapped_trees[level] = _apply(
            _tree_pushforward(structure, tree_level, tuple(pc.unique(column).drop_null().to_pylist())), column)
    mapped_time = _apply(time_map, time_column) if time_map is not None else None

    filters = dict(where or {})
    keep = _mask(filters, spec, table, geo_column, time_column, system)

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
        *tree_levels,
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
        *tree_levels,
    )
    emit_as = dict(zip(group_by, key_names, strict=True))

    unmapped_mass: dict[str, float] = {}
    if mapped_geo is not None:
        # A partial classification -- `metropolitan_region` covers 1,325 of
        # ~5,570 municipalities -- makes the pushforward non-total. The lost mass
        # is REPORTED, never silently dropped: a subset total that reads as a
        # national one is the failure this layer exists to prevent.
        lost = pc.and_(keep, pc.is_null(mapped_geo))
        if pc.any(lost).as_py():
            for measure in chosen:
                column = table.column(measure.state_columns()[0])
                total = pc.sum(pc.filter(column, lost)).as_py() or 0.0
                if total:
                    unmapped_mass[measure.name] = float(total)
        keep = pc.and_(keep, pc.is_valid(mapped_geo))

    for level, mapped in mapped_trees.items():
        # A code the tree does not hold has no ancestor: its mass is reported,
        # never folded into a neighbour.
        lost = pc.and_(keep, pc.is_null(mapped))
        if pc.any(lost).as_py():
            for measure in chosen:
                total = pc.sum(pc.filter(table.column(measure.state_columns()[0]), lost)).as_py() or 0.0
                if total:
                    unmapped_mass[f"{measure.name} ({level})"] = float(total)
        keep = pc.and_(keep, pc.is_valid(mapped))

    keep = pc.fill_null(keep, False)
    working = table.filter(keep)
    for level, mapped in mapped_trees.items():
        working = working.append_column(level, pc.filter(mapped, keep))
    report.rows_read = working.num_rows
    if mapped_geo is not None and geography_level:
        working = working.append_column(GEO_TMP, pc.filter(mapped_geo, keep))
    if mapped_time is not None and time_level:
        working = working.append_column(TIME_TMP, pc.filter(mapped_time, keep))

    state_columns = [c for m in chosen for c in m.state_columns()]
    # What the result carries: one finished value per measure, or the state
    # columns that produced it.
    value_columns = (
        [m.name for m in chosen] if finalize
        else [c for m in chosen for c in m.state_columns()]
    )
    if reduced:
        # a reduced-time measure (a bed stock) takes the same tail as every other: the data version, and the mass a
        # partial classification left unmapped, which returned before either (a roll-up to `metropolitan_region`,
        # 1,325 of 5,570 municipalities, gave a subset total with no warning)
        result = _reduce_over_time(working, chosen, group_by, emit_as, TIME_KEY)
    elif key_names:
        aggregated = working.group_by(list(group_by)).aggregate(
            [(c, _ARROW_MERGE[_kind_of(chosen, c).name]) for c in state_columns])
        suffixed = {c: f"{c}_{_ARROW_MERGE[_kind_of(chosen, c).name]}"
                    for c in state_columns}
        aggregated = aggregated.sort_by([(n, "ascending") for n in group_by])

        arrays: dict[str, Any] = {}
        for name in group_by:
            arrays[emit_as[name]] = pc.cast(aggregated.column(name), pa.string())
        for measure in chosen:
            state = tuple(
                _filled(measure.kind, pc.cast(aggregated.column(suffixed[c]), pa.float64()))
                for c in measure.state_columns()
            )
            if finalize:
                arrays[measure.name] = _finalize_column(measure, state)
            else:
                for column, values in zip(
                        measure.state_columns(), state, strict=True):
                    arrays[column] = values
        result = pa.table(arrays)
    else:
        # No axis named at all: one cell, everything totalled.
        out: dict[str, list[Any]] = {}
        for measure in chosen:
            state = tuple(_merge_column(measure, working.column(c))
                          for c in measure.state_columns())
            if finalize:
                out[measure.name] = [_finalize(measure, state)]
            else:
                for column, value in zip(measure.state_columns(), state, strict=True):
                    out[column] = [value]
        result = pa.table(
            {c: pa.array(out[c], pa.float64()) for c in value_columns})
    report.cells = result.num_rows
    # The data version: a consumer caches by it (handoff §4).
    result = result.replace_schema_metadata({
        **(result.schema.metadata or {}), b"aggregate": spec.name.encode(),
        b"data_version": report.fingerprint.encode()})
    report.unmapped = {k: v for k, v in unmapped_mass.items() if v}
    if report.unmapped:
        report.warnings.append(
            f"rolling up to {geography_level!r} left "
            f"{max(report.unmapped.values()):,.0f} of the base measure unmapped: "
            "that classification does not cover every municipality, so this is a "
            "subset total and not a national one."
        )
    return (result, report) if return_report else result



def _reduce_over_time(working: Any, chosen: Sequence[Measure], group_by: Sequence[str],
                      emit_as: Mapping[str, str], month_key: str) -> Any:
    """Total each month over the other axes, then reduce the months per cell.

    ``mean`` is the mean over the months present, ``last`` the latest month,
    ``max``/``min`` the extreme month. A measure that is additive over time
    is summed over the months, as before.
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    keys = [*group_by, month_key]
    states = [c for m in chosen for c in m.state_columns()]
    monthly = working.group_by(keys).aggregate([(c, _ARROW_MERGE[_kind_of(chosen, c).name]) for c in states])
    suffixed = {c: f"{c}_{_ARROW_MERGE[_kind_of(chosen, c).name]}" for c in states}
    per_month: dict[str, Any] = {k: monthly.column(k) for k in keys}
    for measure in chosen:
        state = tuple(_filled(measure.kind, pc.cast(monthly.column(suffixed[c]), pa.float64()))
                      for c in measure.state_columns())
        per_month[measure.name] = _finalize_column(measure, state)
    table = pa.table(per_month)
    if group_by:
        reducers = []
        for measure in chosen:
            how = (measure.time_reducer or "sum") if "time" not in measure.additive_over else "sum"
            if how == "last":
                continue
            reducers.append((measure.name, {"mean": "mean", "max": "max", "min": "min", "sum": "sum"}[how]))
        out = table.group_by(list(group_by)).aggregate(reducers) if reducers else None
        result: dict[str, Any] = {}
        base = out if out is not None else table.group_by(list(group_by)).aggregate([])
        for name in group_by:
            result[emit_as[name]] = pc.cast(base.column(name), pa.string())
        for measure in chosen:
            how = (measure.time_reducer or "sum") if "time" not in measure.additive_over else "sum"
            if how == "last":
                latest = table.sort_by([(month_key, "descending")])
                seen: dict[tuple, Any] = {}
                for row in latest.select([*group_by, measure.name]).to_pylist():
                    seen.setdefault(tuple(row[k] for k in group_by), row[measure.name])
                result[measure.name] = pa.array([seen.get(tuple(r[k] for k in group_by))
                                                 for r in base.select(list(group_by)).to_pylist()], pa.float64())
            else:
                agg = {"mean": "mean", "max": "max", "min": "min", "sum": "sum"}[how]
                result[measure.name] = base.column(f"{measure.name}_{agg}")
        return pa.table(result).sort_by([(emit_as[n], "ascending") for n in group_by])
    values: dict[str, Any] = {}
    for measure in chosen:
        how = (measure.time_reducer or "sum") if "time" not in measure.additive_over else "sum"
        column = table.sort_by([(month_key, "descending")]).column(measure.name)
        values[measure.name] = [
            column[0].as_py() if how == "last" and len(column) else
            getattr(pc, {"mean": "mean", "max": "max", "min": "min", "sum": "sum"}.get(how, "sum"))(column).as_py()]
    return pa.table({k: pa.array(v, pa.float64()) for k, v in values.items()})


#: How each monoid's merge is spelled as a column aggregate. The mapping is
#: total because every kind here is a commutative monoid over numbers, which is
#: exactly why the serve path needs no per-row arithmetic.
_ARROW_MERGE = {"count": "sum", "sum": "sum", "mean": "sum", "moments": "sum", "logmoments": "sum", "ratio": "sum",
                "min": "min", "max": "max"}


def _finalize_column(measure: Measure, state: tuple[Any, ...]) -> Any:
    """`Kind.finalize`, one column at a time instead of one cell at a time.

    The semantics are the scalar ones exactly -- 0/0 is a null, not a zero,
    because an empty cell displaying a mean of nought is a claim nobody made --
    and `test_formula_matches_finalize` is what ties all three spellings of
    this projection (scalar, columnar, the wire formula) together.
    """
    import pyarrow.compute as pc

    kind = measure.kind.name
    if kind in ("count", "sum"):
        return state[0]
    if kind in ("min", "max"):
        # The identity means "never observed", and the scalar finalize nulls it.
        # Passing it through here handed orjson a literal Infinity, which JSON
        # cannot carry -- an unobserved cell became a crash instead of a null.
        identity = measure.kind.identity()[0]
        return pc.if_else(pc.equal(state[0], identity), None, state[0])
    if kind in ("mean", "moments", "logmoments"):
        n, total = state[0], state[1]
        return pc.if_else(pc.equal(n, 0.0), None, pc.divide(total, pc.if_else(
            pc.equal(n, 0.0), 1.0, n)))
    if kind == "ratio":
        num, den = state
        return pc.if_else(pc.equal(den, 0.0), None, pc.divide(num, pc.if_else(
            pc.equal(den, 0.0), 1.0, den)))
    raise AggregationRefused(f"no columnar finalize for kind {kind!r}")


def _filled(kind: Any, column: Any) -> Any:
    """A state column with its nulls made the kind's zero. A ``sum`` keeps them: null is a cell with no value."""
    import pyarrow.compute as pc

    return column if kind.name == "sum" else pc.fill_null(column, 0.0)


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
    if value is None:
        return measure.kind.identity()[0]    # a sum that saw no value stays None
    return float(value)


def _mask(filters: Mapping[str, Any], spec: AggregateSpec, table: Any,
          geo_column: Any, time_column: Any, system: str | None = None) -> Any:
    """The row filter as an Arrow boolean column: `is_in` per filter, ANDed.

    The Python predecessor walked every row per filter, which at 422k cells was
    a visible share of every request's latency. The one rule that still runs in
    Python is `uf_from_code`, over the DISTINCT municipality codes only.
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    keep = pa.array([True] * table.num_rows, pa.bool_())
    for key, value in filters.items():
        wanted = pa.array(
            sorted({str(v) for v in
                    (value if isinstance(value, (list, tuple, set)) else [value])}),
            pa.string())
        if key in ("period", TIME_KEY, "month"):
            source = time_column
        elif key == "year":
            source = pc.utf8_slice_codeunits(time_column, 0, 4)
        elif key == _UF_LEVEL:
            from .normalize.geo import uf_from_code

            distinct = pc.unique(geo_column).to_pylist()
            mapping = {str(c): str(uf_from_code(str(c)) or "") for c in distinct if c}
            keys = pa.array(list(mapping.keys()), pa.string())
            values = pa.array(list(mapping.values()), pa.string())
            source = pc.take(values, pc.index_in(geo_column, value_set=keys))
        elif key in (_BASE_LEVEL, GEOGRAPHY_KEY):
            source = geo_column
        elif key in spec.dimensions:
            source = table.column(key)
        elif _is_classification(key):
            # Filtering by a health region IS filtering by its member
            # municipalities: the same pushforward the roll-up applies, used
            # as a predicate. Without this, "the composition of THIS region"
            # forced clients to download geography x every dimension and
            # filter locally -- the cuboid, to answer a one-region question.
            distinct = tuple(sorted(set(pc.unique(geo_column).to_pylist())))
            class_map, _contested = _classification_map(key, system, distinct)
            keys = pa.array(list(class_map.keys()), pa.string())
            values = pa.array(
                [v if v is not None else "" for v in class_map.values()], pa.string())
            source = pc.take(values, pc.index_in(geo_column, value_set=keys))
        else:
            raise AggregationRefused(
                f"cannot filter on {key!r}; this artifact has "
                f"{[_BASE_LEVEL, _UF_LEVEL, 'year', 'period', *spec.dimensions]} "
                "and the compiled classifications"
            )
        keep = pc.and_(keep, pc.fill_null(pc.is_in(source, value_set=wanted), False))
    return keep


def _is_classification(level: str) -> bool:
    from .geography import classifications

    return level in classifications()


def _curated_multi_valued(dataset: str, dimensions: Sequence[str], settings: Settings) -> frozenset[str]:
    """The ``dimensions`` that hold several values per row: `CODANOMAL` has up to five ICD codes, so a row lands in
    several cells and marginalising it counts the row more than once.

    Read from the curation of the dataset's SYSTEM in the catalog of ``settings`` (the one the artifact is built from,
    not the default home's): field names are shared identities that disagree across systems, and another system's
    multi-valued CRITERIO had made SINAN's single-character CRITERIO refuse every roll-up. A field the system does not
    curate is not known to be multi-valued. An unreadable catalog RAISES: answering "no" for it let a roll-up
    double-count, and was remembered for the process.
    """
    from ._request import parse_dataset
    from .catalog.store import CatalogStore
    from .semantics.curation import load_variable_docs

    system, _series = parse_dataset(dataset)
    catalog = CatalogStore(settings.catalog_path, read_only=True)
    try:
        docs = load_variable_docs(catalog, system)
    finally:
        catalog.close()
    return frozenset(name for name in dimensions if (doc := docs.get(name.upper())) is not None and doc.multi_valued)


def _served_multi_valued(spec: AggregateSpec, manifest: dict[str, Any], settings: Settings) -> frozenset[str]:
    """The dimensions of a built artifact that hold several values per row.

    The build records them in the manifest (``multi_valued_dimensions``), so an artifact is served with what its build
    knew, and a copy served without the catalog it was built from still refuses a roll-up that would double-count.
    An artifact built before the manifest carried it is read from the catalog of ``settings``; with neither, this
    raises (:func:`_curated_multi_valued`): "none" would let a roll-up double-count.
    """
    recorded = manifest.get("multi_valued_dimensions")
    if recorded is not None:
        return frozenset(str(name) for name in recorded)
    return _curated_multi_valued(spec.dataset, spec.dimensions, settings)
