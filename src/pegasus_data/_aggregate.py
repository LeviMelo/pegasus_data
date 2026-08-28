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
    warnings: list[str] = field(default_factory=list)
    fingerprint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "cells": self.cells, "rows_read": self.rows_read,
            "years": list(self.years), "support": self.support,
            "unmapped": self.unmapped, "contested": list(self.contested),
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
    time_fields = _binding_fields(
        semantics.time_bindings(), spec.time_binding, "time", spec.dataset)
    geography_field = geography_fields[0]

    report = AggregateReport(name=name)
    wanted_years = tuple(int(y) for y in (years or ()))
    if not wanted_years:
        raise AggregationRefused(
            "build_aggregate needs explicit years; an unbounded build would "
            "download the whole publication history"
        )

    cells: dict[tuple[str, ...], dict[str, tuple[float, ...]]] = {}
    blob_digests: set[str] = set()

    for year in sorted(wanted_years):
        # `query()` is the only retrieval path. It plans lake-vs-fetch, unions
        # schema generations with structural nulls and returns raw codes, which
        # is what `lift` needs.
        table, fetch_report = _fetch(
            spec.dataset, uf=uf, years=year, settings=resolved,
            report=True, labels=False, provenance=True,
        )
        report.rows_read += table.num_rows
        names = set(table.schema.names)
        missing = [f for f in (geography_field, *time_fields) if f not in names]
        if missing:
            report.warnings.append(
                f"{year}: {missing} absent from this generation; year skipped")
            continue

        columns = {c: table.column(c).to_pylist() for c in names & {
            geography_field, *time_fields, *spec.dimensions,
            *(m.source_field for m in spec.measures if m.source_field), "_blob_sha256",
        }}
        for digest in set(columns.get("_blob_sha256") or ()):
            if digest:
                blob_digests.add(str(digest))

        # The support mask, from the existing availability verb rather than
        # from schema logic re-derived here.
        report.support[str(year)] = {
            dimension: str(field_available(spec.dataset, dimension, year, settings=resolved))
            for dimension in spec.dimensions
        }

        present_dimensions = [d for d in spec.dimensions if d in names]
        for index in range(table.num_rows):
            row = {c: values[index] for c, values in columns.items()}
            municipality = str(row.get(geography_field) or "").strip()
            competencia = _competencia(row, time_fields)
            if not municipality or not competencia:
                continue
            key = (municipality, competencia, *(
                str(row.get(d) or "").strip() if d in present_dimensions else ""
                for d in spec.dimensions
            ))
            bucket = cells.setdefault(key, {})
            for measure in spec.measures:
                state = measure.kind.lift(
                    row.get(measure.source_field) if measure.source_field else None)
                prior = bucket.get(measure.name)
                bucket[measure.name] = (
                    state if prior is None else measure.kind.merge(prior, state))
        report.years = (*report.years, year)

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
            "support": report.support,
            "key_columns": list(key_names),
            "warnings": report.warnings,
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


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
) -> pa.Table | tuple[pa.Table, AggregateReport]:
    """Serve cells from a built artifact: filter, roll up, finalize.

    ``by`` names a level per axis — ``["health_region", "year", "SEXO"]``. An
    axis you do not name is **marginalised**, which is what "Total" is: the
    pushforward to a one-point space, the same operation as municipality →
    health region with a smaller target.

    No microdata is read. Every result derives from the one materialised base
    cuboid, so a total and the sum of its parts cannot disagree.
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
    unmapped_mass: dict[str, float] = {m.name: 0.0 for m in chosen}
    grouped: dict[tuple[str, ...], dict[str, tuple[float, ...]]] = {}
    kept = 0

    for index in range(total_rows):
        municipality = columns[GEOGRAPHY_KEY][index]
        competencia = columns[TIME_KEY][index]
        if not _passes(filters, spec, columns, index, municipality, competencia):
            continue
        geography_value = geo_map.get(municipality) if geo_map is not None else None
        if geo_map is not None and geography_value is None:
            # A partial classification: metropolitan_region covers 1,325 of
            # ~5,570 municipalities, so the pushforward is not total and the
            # lost mass is REPORTED rather than silently dropped.
            for measure in chosen:
                state = tuple(columns[c][index] for c in measure.state_columns())
                unmapped_mass[measure.name] += float(state[0])
            continue
        key: list[str] = []
        if geography_level:
            key.append(str(geography_value))
        if time_level:
            key.append(str(time_map.get(competencia)))
        for dimension in dimension_levels:
            key.append(str(columns[dimension][index]))
        bucket = grouped.setdefault(tuple(key), {})
        for measure in chosen:
            state = tuple(float(columns[c][index]) for c in measure.state_columns())
            prior = bucket.get(measure.name)
            bucket[measure.name] = (
                state if prior is None else measure.kind.merge(prior, state))
        kept += 1

    key_names = (
        *( [geography_level] if geography_level else [] ),
        *( [time_level] if time_level else [] ),
        *dimension_levels,
    )
    ordered = sorted(grouped)
    out: dict[str, list[Any]] = {n: [] for n in key_names}
    for measure in chosen:
        out[measure.name] = []
    for key in ordered:
        for position, column in enumerate(key_names):
            out[column].append(key[position])
        for measure in chosen:
            state = grouped[key].get(measure.name) or measure.kind.identity()
            out[measure.name].append(_finalize(measure, state))

    result = pa.table({
        **{n: pa.array(out[n], pa.string()) for n in key_names},
        **{m.name: pa.array(out[m.name], pa.float64()) for m in chosen},
    })
    report.cells = result.num_rows
    report.rows_read = kept
    report.unmapped = {k: v for k, v in unmapped_mass.items() if v}
    if report.unmapped:
        report.warnings.append(
            f"rolling up to {geography_level!r} left "
            f"{max(report.unmapped.values()):,.0f} of the base measure unmapped: "
            "that classification does not cover every municipality, so this is a "
            "subset total and not a national one."
        )
    return (result, report) if return_report else result


def _is_classification(level: str) -> bool:
    from .geography import classifications

    return level in classifications()


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


def _passes(filters: Mapping[str, Any], spec: AggregateSpec,
            columns: Mapping[str, list[Any]], index: int,
            municipality: str, competencia: str) -> bool:
    for key, value in filters.items():
        wanted = {str(v) for v in (value if isinstance(value, (list, tuple, set)) else [value])}
        if key in ("period", TIME_KEY, "month"):
            if competencia not in wanted:
                return False
        elif key == "year":
            if competencia[:4] not in wanted:
                return False
        elif key == _UF_LEVEL:
            if municipality[:2] not in {w[:2] for w in wanted} and not _uf_matches(municipality, wanted):
                return False
        elif key in (_BASE_LEVEL, GEOGRAPHY_KEY):
            if municipality not in wanted:
                return False
        elif key in spec.dimensions:
            if str(columns[key][index]) not in wanted:
                return False
        else:
            raise AggregationRefused(
                f"cannot filter on {key!r}; this artifact has "
                f"{[_BASE_LEVEL, _UF_LEVEL, 'year', 'period', *spec.dimensions]}"
            )
    return True


def _uf_matches(municipality: str, wanted: set[str]) -> bool:
    from .normalize.geo import uf_from_code

    return uf_from_code(municipality) in wanted
