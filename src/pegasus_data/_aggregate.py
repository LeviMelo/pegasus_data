"""`aggregate()` — persistent, composable, geography × time analytical cells.

The dominant PegaSUS workload is geography × time → measures, and answering it
from microdata is not viable at request time: `fetch("SIH-RD", uf="AC",
years=2022)` takes 130 s for 49,547 admissions, while the same rows at
municipality × month × sex are 989 cells. Fifty times smaller, and Acre is 0.4%
of national SIH volume.

So an aggregate is built once, offline, and served cheaply. Two surfaces:

* :func:`build_aggregate` — maintainer, writes an artifact under the lake. Its cells are records cubes
  (`cells_from_cubes`, ADR-0217): the recipe is a materialisation request (dataset, event type, bindings, dimensions,
  derived strata, measures), read through `query()` like every other read, a year at a time for rows; the old private
  read path (`fetch` chunk by chunk, its own keying and lifting) is removed (finding 30 of the 2026-10-14 review).
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
                {"name": self.age.name, "form": self.age.form, "of": self.age.of,
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
    files are by hospital state (``setting`` in its roles file) and its cells are keyed by residence: the
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


def _spec_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    from .config import curation_root

    return curation_root() / "aggregates"


def family_specs(curation: Path) -> list[dict[str, Any]]:
    """Aggregates declared once for a family of datasets: a ``datasets/*.yml`` file's ``shared.aggregate`` is a recipe
    for each of its datasets that has the shared event type, a label, and axes holding the recipe's place and time
    bindings (SINAN's agravos). ``{dataset}``, ``{label}`` and ``{what_one_row_is}`` are filled from the
    dataset's entry (its ``label``, else its ``official_name``), and of the template's dimensions each keeps those its
    roles file declares. A recipe file of the same name replaces the expansion (dengue's, with its own notes)."""
    from .semantics.curation import read_yaml

    out: list[dict[str, Any]] = []
    for path in sorted((curation / "datasets").glob("*.yml")):
        doc = read_yaml(path, missing_ok=True) or {}
        template = (doc.get("shared") or {}).get("aggregate")
        if not template:
            continue
        for key, entry in (doc.get("datasets") or {}).items():
            dataset = str(key).replace("_", "-", 1)
            label = entry.get("label") or entry.get("official_name")
            roles_path = curation / "roles" / f"{dataset}.yml"
            # the shared event type is every entry's unless it says it has none; its axes (its own, else the shared ones)
            # must hold the recipe's place and time bindings
            axes = entry.get("semantic_axes") or (doc.get("shared") or {}).get("semantic_axes") or {}
            bound = (template.get("geography_binding") in (axes.get("geography") or {})
                     and template.get("time_binding") in (axes.get("time") or {}))
            if entry.get("why_no_event_type") or not bound or not label or not roles_path.is_file():
                continue
            columns = set((read_yaml(roles_path) or {}).get("columns") or {})
            fill = {"dataset": dataset, "dataset_id": dataset.lower().replace("-", "_"), "label": str(label),
                    "what_one_row_is": str(entry.get("what_one_row_is") or "").strip()}
            data = {k: (v.format(**fill) if isinstance(v, str) else v) for k, v in template.items()}
            data["dataset"] = dataset
            data["dimensions"] = [d for d in template.get("dimensions") or () if d in columns]
            data["dimension_labels"] = {d: v for d, v in (template.get("dimension_labels") or {}).items()
                                        if d in data["dimensions"]}
            out.append(data)
    return out


def load_specs(root: Path | None = None) -> dict[str, AggregateSpec]:
    """Every declared aggregate, keyed by name."""
    from .semantics.curation import read_yaml

    folder = _spec_root(root)
    out: dict[str, AggregateSpec] = {}
    if not folder.exists():
        return out
    declared = [(path.stem, read_yaml(path, missing_ok=True) or {}) for path in sorted(folder.glob("*.yml"))]
    named = {str(data.get("name") or stem) for stem, data in declared}
    declared += [(str(data["name"]), data) for data in family_specs(folder.parent) if data["name"] not in named]
    for stem, data in declared:
        name = str(data.get("name") or stem)
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
    from ._age import parse_age

    try:
        return parse_age(body)
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
    #: Of those, the events whose code names their state and no municipality ("Município ignorado - <UF>"), by state
    #: (IBGE code): what the sum of a state's municipalities lacks against the state (the cube's ``unplaced_by_state``).
    unplaced_by_state: dict[str, float] = field(default_factory=dict)
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
            "unplaced_by_state": dict(self.unplaced_by_state),
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
    from ._availability import field_available
    from .config import load_settings
    from .persist.staging import staged_file

    resolved = settings or load_settings(root=Path(root) if root else None)
    spec = spec_named(name)
    semantics = _resolve_semantics(spec)
    from .semantics.event_types import event_type as _event_type

    if spec.event_type:
        _event_type(spec.dataset, spec.event_type)      # an event type the dataset lacks is refused here

    # Refuse a measure the grain contradicts BEFORE reading anything: counting
    # rows on an establishment-month dataset counts establishment-months.
    for measure in spec.measures:
        check_measure(measure, semantics.grain)

    geography_fields = _binding_fields(
        semantics.geography_bindings(), spec.geography_binding, "geography", spec.dataset)
    _require_municipality_geography(semantics, spec)
    _binding_fields(semantics.time_bindings(), spec.time_binding, "time", spec.dataset)   # refuses an unknown binding
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
    if report.uf:
        report.uf_basis_note = _uf_basis_note(spec.dataset, geography_field, report.uf)
        if report.uf_basis_note:
            report.warnings.append(report.uf_basis_note)
    # Asked of the curation now, while the catalog the build reads is at hand, and written into the manifest: serving
    # reads what the build knew, so an artifact served without its catalog still refuses a double-counting roll-up.
    multi_valued = sorted(_curated_multi_valued(spec.dataset, spec.dimensions, resolved))

    # One grouped Arrow table per chunk; merged once at the end (_merge_cells).
    # The cells are records cubes (`cells_from_cubes`, ADR-0217): one per state asked for, or the whole publication.
    cells: list[Any] = []
    for chunk_uf, table, read, error in _chunks(spec, sorted(wanted_years), report.uf, resolved):
        if error is not None:
            report.warnings.append(f"{chunk_uf or 'BR'}: {error}")
            report.missing_chunks.append(f"{min(wanted_years)} {chunk_uf or 'BR'}")
            continue
        cells.append(table)
        report.rows_read += int(read.get("events") or 0)
        report.unkeyed_rows += int(read.get("unplaced_events") or 0)
        for state, n in (read.get("unplaced_by_state") or {}).items():
            report.unplaced_by_state[state] = report.unplaced_by_state.get(state, 0.0) + float(n)
        for year in sorted({int(str(c)[:4]) for c in table.column(TIME_KEY).to_pylist()}):
            if year not in report.years:
                report.years = (*report.years, year)
    for year in sorted(report.years):
        def _support_of(dimension: str, year: int = year) -> str:
            for band in spec.band_dims:
                if dimension == band.name:
                    return str(field_available(spec.dataset, band.field_name, year, settings=resolved))
            if spec.age is not None and dimension == spec.age.name:
                # derived: available where its variable can be made (`field_available` reads the recipe's inputs)
                return min(str(field_available(spec.dataset, f, year, settings=resolved))
                           for f in ([spec.age.of] if spec.age.of else spec.age.fields))
            return str(field_available(spec.dataset, dimension, year, settings=resolved))

        report.support[str(year)] = {dimension: _support_of(dimension) for dimension in spec.dimensions}
    if not cells:
        raise AggregationRefused(f"{name}: no cells produced for years {sorted(wanted_years)}")
    if report.unkeyed_rows:
        report.warnings.append(
            f"{report.unkeyed_rows:,} of {report.rows_read:,} records no municipality places or with no valid period "
            "are in no cell (the cube's unplaced_events)")
    no_cells = sorted(set(wanted_years) - set(report.years))
    if no_cells:
        report.warnings.append(f"no cells for year(s) {no_cells}: nothing was read or nothing usable in them")
    stamp = hashlib.blake2b(digest_size=16)
    from .cubes import _records_stamp

    _records_stamp(resolved, spec.dataset, stamp)
    blob_digests = {stamp.hexdigest()}
    key_names = (GEOGRAPHY_KEY, TIME_KEY, *spec.dimensions)
    arrow = _merge_cells(cells, key_names, spec)
    report.cells = arrow.num_rows
    _flag_partial_periods(spec, semantics, report, wanted_years, arrow.column(TIME_KEY).to_pylist())
    report.fingerprint = _fingerprint(spec, blob_digests, resolved)

    # The cells are not stored: they are the recipe's records cubes, kept by the cube store (`cubes._cached`) and read
    # back through `_load_artifact`. The artifact is its manifest: what was asked for and what the build found.
    target = artifact_dir(name, resolved)
    target.mkdir(parents=True, exist_ok=True)
    manifest_payload = json.dumps({
        "name": name,
        "spec": spec.fingerprint_payload(),
        "fingerprint": report.fingerprint,
        "engine_version": ENGINE_VERSION,
        "cells": report.cells,
        "rows_read": report.rows_read,
        "years": list(report.years),
        "requested_years": sorted(wanted_years),
        "uf": list(report.uf),
        "uf_basis_note": report.uf_basis_note,
        "multi_valued_dimensions": multi_valued,
        "support": report.support,
        "partial_periods": list(report.partial_periods),
        "missing_chunks": list(report.missing_chunks),
        "unkeyed_rows": report.unkeyed_rows,
        "unplaced_by_state": dict(sorted(report.unplaced_by_state.items())),
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


def _reductions(spec: AggregateSpec) -> dict[str, str]:
    """Each state column's merge: min/max for the extremes, a sum for every other kind."""
    return {column: (measure.kind.name if measure.kind.name in ("min", "max") else "sum")
            for measure in spec.measures for column in measure.state_columns()}


def _chunks(spec: AggregateSpec, years: Sequence[int], ufs: Sequence[str], settings: Any):
    """``(uf, cells, read, error)`` for each state asked for (the whole publication when none): a chunk whose publication
    is not there is its error, never an absence."""
    whole: list[str | None] = [None]
    for chunk_uf in (list(ufs) or whole):
        try:
            table, read = cells_from_cubes(spec, list(years), chunk_uf, settings)
        except LookupError as exc:
            yield chunk_uf, None, {}, exc
            continue
        yield chunk_uf, table, read, None


def cells_from_cubes(spec: AggregateSpec, years: Sequence[int], uf: str | None, settings: Any) -> tuple[Any, dict]:
    """A recipe's base cuboid as records cubes (ADR-0217): one cube per measure state over the recipe's dataset, event
    type, bindings, dimensions and derived strata (its age band, its numeric bands), joined on the cell keys. A count is
    the cube's events; a sum its column's (``A+B`` row-wise, null where no part holds a number); a mean its numbers'
    count (``count:<column>``) and sum. A record no municipality places is the cube's ``unplaced_events``, never a cell.
    The cells keep the artifact's columns: ``municipality`` (6 digits), ``competencia`` (``YYYYMM``, or ``YYYY``), the
    dimensions ('' where not recorded) and the state columns; with the first cube's manifest (records read, unplaced)."""
    import pyarrow as pa
    import pyarrow.compute as pc

    from .cubes import cube, manifest

    derived: dict[str, dict[str, Any]] = {}
    if spec.age is not None:
        age = spec.age
        # an age named by its derived variable is banded from the years `query` decodes; one given in place by its form
        derived[age.name] = ({"age": age.of, "bands": list(age.bands)} if age.of else
                             {"form": age.form, "fields": list(age.fields), "units": dict(age.units),
                              "unknown": list(age.unknown), "plain_below": age.plain_below, "bands": list(age.bands),
                              "lookup": dict(age.lookup)})
    for band in spec.band_dims:
        derived[band.name] = {"field": band.field_name, "bands": list(band.bands), "label": band.label, "unit": band.unit}
    source = f"records:{spec.dataset}/{spec.event_type or 'rows'}"
    common = {"by": list(spec.dimensions), "periods": [str(y) for y in years], "settings": settings,
              "at": spec.geography_binding or None, "time": spec.time_binding or None, "grain": spec.time_grain,
              "geography": uf, "derived": derived or None}
    keys = ["place", "period", *spec.dimensions]
    merged = None
    read: dict[str, Any] = {}
    for measure in spec.measures:
        kind, fields = measure.kind.name, list(measure.source_fields)
        parts: dict[str, str | None]
        if kind == "count":
            parts = {f"{measure.name}_n": None}
        elif kind == "sum":
            parts = {f"{measure.name}_sum": "+".join(fields)}
        elif kind in ("mean", "moments") and len(fields) == 1:
            # (n, sum) and, for the variance, the sum of squares: sufficient statistics, never a finished mean
            parts = {f"{measure.name}_n": f"count:{fields[0]}", f"{measure.name}_sum": fields[0]}
            if kind == "moments":
                parts[f"{measure.name}_sumsq"] = f"sumsq:{fields[0]}"
        elif kind == "logmoments" and len(fields) == 1:
            parts = {f"{measure.name}_n": f"countpos:{fields[0]}", f"{measure.name}_sumlog": f"sumlog:{fields[0]}",
                     f"{measure.name}_sumsqlog": f"sumsqlog:{fields[0]}"}
        elif kind in ("min", "max") and len(fields) == 1:
            parts = {f"{measure.name}_{kind}": f"{kind}:{fields[0]}"}
        else:
            raise AggregationRefused(f"{spec.name}: a {kind} measure over {fields} is not built from cubes yet")
        for state, measured in parts.items():
            table = cube(source, measure=measured, **common) if measured else cube(source, **common)
            if not read and kind not in ("min", "max"):
                # what the records were: the first additive cube's manifest (every cube reads the same records; an
                # extreme's has no unplaced count)
                read = manifest(table)
            part = table.select([*keys, "value"]).rename_columns([*keys, state])
            merged = part if merged is None else merged.join(part, keys=keys, join_type="full outer")
    assert merged is not None
    period = pc.replace_substring(merged.column("period"), "-", "")
    out = {"municipality": pc.utf8_slice_codeunits(pc.cast(merged.column("place"), pa.string()), 0, 6),
           "competencia": period,
           **{d: pc.fill_null(pc.cast(merged.column(d), pa.string()), "") for d in spec.dimensions}}
    for state in spec.state_columns():
        column = pc.cast(merged.column(state), pa.float64())
        out[state] = column if state.endswith("_sum") else pc.fill_null(column, 0.0)
    keys_out = ["municipality", "competencia", *spec.dimensions]
    table = pa.table(out).select([*keys_out, *spec.state_columns()])
    return table.sort_by([(k, "ascending") for k in keys_out]), read


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


def geography_pack_checksum(names: tuple[str, ...] = ("geography.parquet",)) -> str:
    """The checksum of the packaged geography file(s) (``""`` when one is absent): the version of whatever was placed
    through them."""
    from importlib.resources import files

    out = ""
    for name in names:
        try:
            pack = Path(str(files("pegasus_data.resources") / name))
            if pack.exists():
                out += hashlib.sha256(pack.read_bytes()).hexdigest()
        except (ModuleNotFoundError, FileNotFoundError):  # pragma: no cover
            pass
    return out


def _fingerprint(spec: AggregateSpec, blob_digests: set[str], settings: Settings) -> str:
    """Identity of an artifact: the spec, its sources, and its semantics.

    The geography pack's checksum is in here deliberately. Changing it changes
    every health-region roll-up derived from this artifact, and an artifact that
    does not notice is stale in a way nobody can see.
    """
    from .config import curation_root
    from .semantics.curation import curation_fingerprint

    digest = hashlib.blake2b(digest_size=16)
    digest.update(json.dumps(spec.fingerprint_payload(), sort_keys=True).encode())
    digest.update(ENGINE_VERSION.encode())
    digest.update(curation_fingerprint(curation_root()).encode())
    digest.update(geography_pack_checksum().encode())
    for blob in sorted(blob_digests):
        digest.update(blob.encode())
    return digest.hexdigest()


# --------------------------------------------------------------------- read


_CUBOIDS: dict[tuple[str, str, int], tuple[Any, dict[str, Any]]] = {}


def _load_artifact(name: str, settings: Settings):
    """The artifact's base cuboid and manifest. The cuboid is the recipe's records cubes (`_chunks`) for the years and
    states the manifest says it was built for, merged; the cube store keeps them, so a read after a build is a file read,
    and after a change of the data or the code the cubes are made again: the cuboid is never older than either."""
    manifest_path = _manifest_path(name, settings)
    if not manifest_path.exists():
        raise ArtifactMissing(
            f"{name!r} has not been built; run "
            f"`pegasus-data aggregate-build {name} --years ...` first"
        )
    key = (name, str(manifest_path), manifest_path.stat().st_mtime_ns)
    if key not in _CUBOIDS:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        spec = spec_named(name)
        years = [int(y) for y in (manifest.get("requested_years") or manifest.get("years") or ())]
        cells = [t for _, t, _, error in _chunks(spec, years, manifest.get("uf") or (), settings) if error is None]
        if not cells:
            raise ArtifactMissing(f"{name!r}: its records cubes cannot be made for years {years}")
        while len(_CUBOIDS) >= 8:
            _CUBOIDS.pop(next(iter(_CUBOIDS)))
        _CUBOIDS[key] = (_merge_cells(cells, manifest["key_columns"], spec), manifest)
    return _CUBOIDS[key]


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


#: Grouping columns get internal names. `by=["municipality"]` and `by=["month"]` would otherwise collide with the
#: artifact's own key columns -- Arrow raises "Multiple matches for FieldRef" -- and renaming at the end is simpler than
#: special-casing the identity pushforward.
_GEO_TMP, _TIME_TMP = "__geo__", "__time__"


@dataclass(frozen=True)
class _Levels:
    """Which level of ``by`` applies to which axis; an axis with none is marginalised."""

    geography: str | None
    time: str | None
    dimensions: list[str]
    trees: list[str]

    @property
    def keys(self) -> tuple[str, ...]:
        """The levels as the result names them."""
        return (*([self.geography] if self.geography else ()), *([self.time] if self.time else ()),
                *self.dimensions, *self.trees)

    @property
    def group_by(self) -> tuple[str, ...]:
        """The same axes under the internal grouping names."""
        return (*([_GEO_TMP] if self.geography else ()), *([_TIME_TMP] if self.time else ()),
                *self.dimensions, *self.trees)


def _new_report(name: str, manifest: Mapping[str, Any]) -> AggregateReport:
    """The report of a read, with what the artifact's manifest says about its support and completeness."""
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
    return report


def _resolve_levels(spec: AggregateSpec, by: Sequence[str] | None) -> _Levels:
    """Which level applies to which axis; a level the artifact does not offer is refused."""
    # Deduplicated, order kept: grouping by an axis twice is grouping by it
    # once, and Arrow would otherwise return two identically named columns --
    # which downstream reads as a KeyError the route misreports as a missing
    # artifact.
    levels = tuple(dict.fromkeys(by or ()))
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
    return _Levels(geography_level, time_level, dimension_levels, tree_levels)


def _check_additivity(spec: AggregateSpec, manifest: Mapping[str, Any], settings: Settings, chosen: Sequence[Measure],
                      lv: _Levels, finalize: bool) -> list[Measure]:
    """Refuse a roll-up the measures do not allow; the measures reduced over time (not summed) are returned."""
    # --- additivity: marginalising an axis is summing along it --------------
    # Naming no time level marginalises time entirely; naming `year` over a
    # monthly artifact coarsens it. Both sum along time, which a stock refuses.
    rolls_up_time = lv.time is None or (lv.time == "year" and spec.time_grain != "year")
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
        if lv.geography != _BASE_LEVEL:
            check_rollup(measure, "geography")
        for dimension in spec.dimensions:
            if dimension not in lv.dimensions:
                check_rollup(measure, "dimensions")
                if several_per_row is None:
                    several_per_row = _served_multi_valued(spec, manifest, settings)
                check_dimension(measure, dimension in several_per_row)
    return reduced


def _apply_map(mapping: dict[str, str | None], column: Any) -> Any:
    """A pushforward applied to a column: `index_in` + `take`, an unmapped code flowing through as a null."""
    import pyarrow as pa
    import pyarrow.compute as pc

    keys = pa.array(list(mapping.keys()), pa.string())
    values = pa.array(list(mapping.values()), pa.string())
    return pc.take(values, pc.index_in(column, value_set=keys))


def _pushforwards(name: str, spec: AggregateSpec, table: Any, lv: _Levels, system: str | None,
                  report: AggregateReport) -> tuple[Any, dict[str, Any], Any]:
    """The base cuboid's geography, tree and time columns mapped to the requested levels (None / empty where unasked)."""
    # --- pushforward maps ---------------------------------------------------
    # The RULE for each level is decided in Python over the DISTINCT codes --
    # a few thousand lookups, where the ownership of `uf_from_code` and
    # `memberships` lives. Applying it to 400k rows is `index_in` + `take`,
    # with an unmapped code flowing through as a null.
    import pyarrow as pa
    import pyarrow.compute as pc

    geo_column = table.column(GEOGRAPHY_KEY)
    time_column = table.column(TIME_KEY)
    geo_map = (
        _geography_pushforward(lv.geography, pc.unique(geo_column).to_pylist(), system, report)
        if lv.geography else None
    )
    time_map = (
        _time_pushforward(lv.time, pc.unique(time_column).to_pylist())
        if lv.time else None
    )
    mapped_geo = _apply_map(geo_map, geo_column) if geo_map is not None else None
    mapped_trees: dict[str, Any] = {}
    for level in lv.trees:
        dimension, tree_level = level.split("@", 1)
        structure = spec.dimension_structures.get(dimension.upper())
        if structure is None:
            raise AggregationRefused(
                f"{dimension} declares no code structure in {name!r}; add it to dimension_structures")
        column = pc.cast(table.column(dimension), pa.string())
        mapped_trees[level] = _apply_map(
            _tree_pushforward(structure, tree_level, tuple(pc.unique(column).drop_null().to_pylist())), column)
    mapped_time = _apply_map(time_map, time_column) if time_map is not None else None
    return mapped_geo, mapped_trees, mapped_time


def _drop_unmapped(table: Any, chosen: Sequence[Measure], keep: Any, mapped_geo: Any,
                   mapped_trees: Mapping[str, Any]) -> tuple[Any, dict[str, float]]:
    """``keep`` narrowed to the rows the pushforwards map, and the mass of the measures lost to a partial mapping."""
    import pyarrow.compute as pc

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
    return pc.fill_null(keep, False), unmapped_mass


def _working_table(table: Any, keep: Any, lv: _Levels, mapped_geo: Any, mapped_trees: Mapping[str, Any],
                   mapped_time: Any) -> Any:
    """The rows kept, with the mapped levels as columns under their internal grouping names."""
    import pyarrow.compute as pc

    working = table.filter(keep)
    for level, mapped in mapped_trees.items():
        working = working.append_column(level, pc.filter(mapped, keep))
    if mapped_geo is not None and lv.geography:
        working = working.append_column(_GEO_TMP, pc.filter(mapped_geo, keep))
    if mapped_time is not None and lv.time:
        working = working.append_column(_TIME_TMP, pc.filter(mapped_time, keep))
    return working


def _reduce_cells(working: Any, chosen: Sequence[Measure], lv: _Levels, reduced: Sequence[Measure],
                  finalize: bool) -> Any:
    """The measures reduced over the cells of ``lv``: a stock over time, grouped states, or one total cell."""
    import pyarrow as pa
    import pyarrow.compute as pc

    from .measures import finalize as _finalize

    key_names, group_by = lv.keys, lv.group_by
    emit_as = dict(zip(group_by, key_names, strict=True))
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
        return _reduce_over_time(working, chosen, group_by, emit_as, TIME_KEY)
    if key_names:
        # The merge is Arrow's grouped aggregation, not a Python loop over cells.
        # That is a property of the design rather than an optimisation: every
        # accumulator here is a commutative monoid whose merge IS a column
        # aggregate. `count` and `sum` merge by summing one column, `mean` by
        # summing (n, sum), `ratio` by summing (num, den), `min`/`max` by MIN/MAX.
        # The whole algebra maps onto group_by().aggregate() with no special cases.
        #
        # The loop this replaced cost about 13 s on a realistic national year, which
        # is not an answer a frontend can wait for.
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
        return pa.table(arrays)
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
    return pa.table(
        {c: pa.array(out[c], pa.float64()) for c in value_columns})


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
    from .config import load_settings

    resolved = settings or load_settings(root=Path(root) if root else None)
    spec = spec_named(name)
    table, manifest = _load_artifact(name, resolved)
    report = _new_report(name, manifest)
    wanted = tuple(measures or [m.name for m in spec.measures])
    chosen = [spec.measure_named(m) for m in wanted]
    lv = _resolve_levels(spec, by)
    reduced = _check_additivity(spec, manifest, resolved, chosen, lv, finalize)

    mapped_geo, mapped_trees, mapped_time = _pushforwards(name, spec, table, lv, system, report)
    keep = _mask(dict(where or {}), spec, table, table.column(GEOGRAPHY_KEY), table.column(TIME_KEY), system)
    keep, unmapped_mass = _drop_unmapped(table, chosen, keep, mapped_geo, mapped_trees)
    working = _working_table(table, keep, lv, mapped_geo, mapped_trees, mapped_time)
    report.rows_read = working.num_rows

    result = _reduce_cells(working, chosen, lv, reduced, finalize)
    report.cells = result.num_rows
    # The data version: a consumer caches by it (handoff §4).
    result = result.replace_schema_metadata({
        **(result.schema.metadata or {}), b"aggregate": spec.name.encode(),
        b"data_version": report.fingerprint.encode()})
    report.unmapped = {k: v for k, v in unmapped_mass.items() if v}
    if report.unmapped:
        report.warnings.append(
            f"rolling up to {lv.geography!r} left "
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
_ARROW_MERGE = {"count": "sum", "sum": "sum", "mean": "sum", "moments": "sum", "logmoments": "sum",
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


def _served_multi_valued(spec: AggregateSpec, manifest: Mapping[str, Any], settings: Settings) -> frozenset[str]:
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
