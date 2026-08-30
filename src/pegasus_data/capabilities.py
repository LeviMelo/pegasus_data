"""What a client may legitimately do with an artifact, projected from curation.

**This module is a projection, not an authority.** Every fact it reports is read
from somewhere that already owns it:

===========================  =========================================
fact                         owner
===========================  =========================================
what a row is                ``semantics.curation`` -> ``Grain``
which field carries space    ``semantic_axes.geography``
which field carries time     ``semantic_axes.time``
which levels exist           the built artifact + ``view.codelist_levels``
what a measure combines to   ``measures.Kind`` -> ``state_fields``/``formula``
where it can roll up to      ``geography.classifications``
what it cannot answer        ``AggregateReport`` -> ``support``/``partial_periods``
===========================  =========================================

Nothing here decides anything. If a capability looks wrong, the fix belongs in
the module that owns the fact, and this one will follow.

The rule the whole client rests on: **if this descriptor does not declare it,
the interface does not draw it.** A control that is present and inert is worse
than one that is absent, because the user believes the filter applied. That
makes an *omission* here a user-visible defect, which is why the descriptor is
derived rather than authored -- an authored one drifts the moment a spec changes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

from .config import Settings

#: Cardinality decides the control. This lives here rather than in the client so
#: there is no threshold table to keep in sync across a network boundary, and so
#: a dimension that grows past a threshold changes its control on its own.
_CONTROL_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (4, "segmented"),
    (12, "chips"),
    (30, "bars"),
)
_CONTROL_FALLBACK = "combobox"

#: Which visual encodings a measure kind can bear. A count can be stacked; a
#: mean cannot, because stacking asserts the parts sum to the whole and the mean
#: of two groups is not the sum of their means.
_ENCODINGS: dict[str, tuple[str, ...]] = {
    "count": ("choropleth", "line", "ranked_bar", "proportional_symbol", "scatter", "stack"),
    "sum": ("choropleth", "line", "ranked_bar", "proportional_symbol", "scatter", "stack"),
    "mean": ("choropleth", "line", "ranked_bar", "scatter"),
    "ratio": ("choropleth", "line", "ranked_bar", "scatter"),
    "min": ("choropleth", "line", "ranked_bar"),
    "max": ("choropleth", "line", "ranked_bar"),
}

#: Operations that are wrong for a kind, stated so the client can refuse them
#: rather than having to know why.
_FORBIDDEN: dict[str, tuple[str, ...]] = {
    "count": (),
    "sum": (),
    "mean": ("sum", "stack"),
    "ratio": ("sum", "stack"),
    "min": ("sum", "stack"),
    "max": ("sum", "stack"),
}

#: Display precision by unit. A count of admissions has no decimals; a mean
#: length of stay has one; money has two.
_DECIMALS: dict[str, int] = {
    "brl": 2, "day": 1, "year": 1, "percent": 1, "rate": 1,
}


@dataclass(frozen=True, slots=True)
class Level:
    """One value a dimension takes, as it appears in THIS artifact."""

    code: str
    label: str


@dataclass(frozen=True, slots=True)
class Dimension:
    id: str
    label: str
    kind: str
    levels: tuple[Level, ...]
    cardinality: int
    control: str
    #: Per year, ``present`` | ``absent`` | ``unknown``. A dimension absent from
    #: a schema generation produces cells meaning "we could not have known",
    #: which is not the same as "it happened zero times".
    support: dict[str, str] = field(default_factory=dict)
    note: str = ""
    #: ``"age_band"`` / ``"band"`` when the dimension was DERIVED by the build
    #: (banded from a numeric source) rather than read from a raw column.
    #: A client that wants an age-specific rate needs to know which axis is
    #: the banded age, and guessing from labels is exactly the kind of
    #: inference the descriptor exists to make unnecessary.
    derived: str | None = None


@dataclass(frozen=True, slots=True)
class MeasureCapability:
    id: str
    label: str
    kind: str
    #: The additive state columns the payload actually carries.
    components: tuple[str, ...]
    #: An expression over `components`, evaluated by the client after it has
    #: finished aggregating. The artifact never carries a rate or a mean.
    formula: str
    unit: str
    decimals: int
    additive_over: tuple[str, ...]
    forbidden: tuple[str, ...]
    encodings: tuple[str, ...]
    #: Set when the measure only means something under one geography binding --
    #: a rate needs its denominator drawn from the same population.
    requires_binding: str | None = None
    time_reducer: str | None = None


@dataclass(frozen=True, slots=True)
class Binding:
    id: str
    label: str
    fields: tuple[str, ...]
    active: bool
    #: Only a residence-like geography carries a compatible population
    #: denominator. Geography bindings only.
    denominator_compatible: bool | None = None
    #: `date` | `year_month` | `year` | `yyyymm`. Time bindings only. A record
    #: date does not align with the publication coordinate, which is what makes
    #: `partial_periods` non-empty.
    encoding: str | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class Capability:
    """Everything a client needs to build its own interface for one artifact."""

    id: str
    dataset: str
    system: str | None
    series: str | None
    label: str
    description: str
    observation_unit: str
    #: The grain split into its parts. `establishment-bed type-month` is three
    #: components, and a client that counts rows is counting THOSE, not
    #: establishments -- which is why the descriptor carries them rather than
    #: only the prose.
    grain_components: tuple[str, ...]
    #: True when a row is an entity-PERIOD, so a count over months counts
    #: entity-months and summing it across time is a category error.
    period_bearing: bool
    vintage: str
    fingerprint: str
    period: dict[str, Any]
    spatial: dict[str, Any]
    temporal: dict[str, Any]
    completeness: dict[str, Any]
    dimensions: tuple[Dimension, ...]
    measures: tuple[MeasureCapability, ...]
    provenance: dict[str, Any]
    #: Denominator series the lake can actually serve for this artifact's
    #: years, in preference order. Empty when none is materialised -- and the
    #: UI draws no rate control it cannot honour (invariant 4). Whether the
    #: ACTIVE geography binding may meet a population denominator at all is
    #: `spatial.denominator_compatible`; this is the other half of the offer.
    denominators: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ helpers


def _denominators(settings: Any, years: tuple[int, ...]) -> tuple[dict[str, Any], ...]:
    """Population series the lake holds that cover at least one artifact year.

    A PROJECTION of what is materialised, like everything else here: declaring
    POPSVS while `lake/population/POPSVS` does not exist would hand the UI a
    rate toggle that 404s. The order is the preference order -- POPSVS carries
    age and sex, POPTCU is totals-only, and the rest are historical.
    """
    from .sources.ibge import KNOWN_SERIES

    out: list[dict[str, Any]] = []
    for name, series in KNOWN_SERIES.items():
        directory = settings.population_dir / name
        if not directory.exists():
            continue
        covered = [
            y for y in years
            if (series.year_min is None or y >= series.year_min)
            and (series.year_max is None or y <= series.year_max)
        ]
        if not covered:
            continue
        out.append({
            "series": name,
            "authority": series.authority,
            "stratifications": list(series.stratifications),
            "age_standardizable": series.age_standardizable,
            "years": covered,
            "note": series.notes,
        })
    return tuple(out)


def _control_for(cardinality: int) -> str:
    for limit, control in _CONTROL_THRESHOLDS:
        if cardinality <= limit:
            return control
    return _CONTROL_FALLBACK


def _decimals_for(kind: str, unit: str) -> int:
    if unit in _DECIMALS:
        return _DECIMALS[unit]
    return 0 if kind in ("count", "sum") else 1


def _humanise(text: str) -> str:
    """The last resort: show the identifier itself.

    `RACA_COR` -> `Raça cor` would be a prettified guess that reads like a
    translation nobody made. Showing the column name is honest. The real labels
    come from the spec, then from curation -- see `_label_for`.
    """
    return text


def _label_for(
    key: str, declared: Mapping[str, str], docs: Mapping[str, Any]
) -> str:
    """Three sources, most specific first.

    1. The artifact's own spec, where an analyst says what THIS artifact's
       columns are, in the interface's language.
    2. Curation's `translated_name` -- a real human name, in English.
    3. The identifier.
    """
    if declared.get(key):
        return declared[key]
    doc = docs.get(key)
    name = getattr(doc, "translated_name", None) if doc else None
    return str(name) if name else _humanise(key)


# --------------------------------------------------------------- projection


def capabilities(
    name: str,
    *,
    settings: Settings | None = None,
    root: str | Path | None = None,
) -> Capability:
    """Project one built artifact into the descriptor a client draws from.

    Raises :class:`ArtifactMissing` when the artifact has not been built. That
    is deliberate: a capability describes what *exists*, and describing an
    unbuilt artifact would advertise controls for data that cannot be served.

    Cached on the artifact's on-disk identity. The projection reads the cells,
    the catalog and the reference tables, which measured at ~1.2 s on a
    national artifact -- and the serve handler consults the descriptor on EVERY
    cell request, so an uncached projection put a constant floor under every
    answer the API gave. A rebuild changes the mtime and the stale entry ages
    out.
    """
    from ._aggregate import artifact_dir
    from .config import load_settings as _load

    resolved_early = settings or _load(root=Path(root) if root else None)
    cells_path = artifact_dir(name, resolved_early) / "cells.parquet"
    if not cells_path.exists():
        return _capabilities_uncached(name, settings=resolved_early)
    # A plain dict rather than lru_cache: Settings is unhashable, and the key
    # that actually identifies the answer is (artifact, lake, on-disk version).
    # BOTH files' mtimes, matching _read_artifact's key exactly: the manifest
    # carries fingerprint, support and partial_periods, and a manifest-only
    # change must invalidate the descriptor just as it invalidates the read.
    manifest_mtime = 0
    try:
        manifest_mtime = (cells_path.parent / "manifest.json").stat().st_mtime_ns
    except OSError:
        pass
    # The spec file's mtime too: labels and level words live in the SPEC, and
    # an edited YAML must reach the descriptor without waiting for a rebuild.
    spec_mtime = 0
    try:
        from .ontology import CURATION

        spec_mtime = (
            (CURATION / "aggregates" / f"{name}.yml").stat().st_mtime_ns
        )
    except OSError:
        pass
    key = (
        name, str(resolved_early.lake_dir),
        cells_path.stat().st_mtime_ns, manifest_mtime, spec_mtime,
    )
    hit = _CAPABILITY_CACHE.get(key)
    if hit is not None:
        return hit
    built = _capabilities_uncached(name, settings=resolved_early)
    if len(_CAPABILITY_CACHE) >= 16:
        _CAPABILITY_CACHE.clear()
    _CAPABILITY_CACHE[key] = built
    return built


_CAPABILITY_CACHE: dict[tuple[str, str, int], Capability] = {}


def _capabilities_uncached(
    name: str,
    *,
    settings: Settings | None = None,
    root: str | Path | None = None,
) -> Capability:
    """The projection itself; `capabilities` is the cached front door."""
    from ._aggregate import ArtifactMissing, artifact_dir, spec_named
    from .catalog.store import Catalog
    from .config import load_settings
    from .geography import DENOMINATOR_COMPATIBLE_ROLES, classifications
    from .semantics.curation import semantics_for
    from .view import codelist_levels

    resolved = settings or load_settings(root=Path(root) if root else None)
    spec = spec_named(name)
    semantics = semantics_for(spec.dataset)
    if semantics is None:  # pragma: no cover - build_aggregate refuses first
        raise ArtifactMissing(f"no curated semantics for {spec.dataset!r}")

    directory = artifact_dir(name, resolved)
    manifest_path = directory / "manifest.json"
    cells_path = directory / "cells.parquet"
    if not manifest_path.exists() or not cells_path.exists():
        raise ArtifactMissing(
            f"{name!r} has no built artifact under {directory}; "
            f"run `build_aggregate({name!r}, years=[...])` first"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # --- what is actually IN this artifact ------------------------------
    # The descriptor describes THIS build, not the classification in the
    # abstract. DIAG_PRINC binds ~14,000 ICD codes; an artifact holding 40 of
    # them must not offer a control with 14,000 levels.
    import pyarrow.compute as pc

    from ._aggregate import _load_artifact

    cells, _ = _load_artifact(name, resolved)
    observed: dict[str, list[str]] = {}
    for dimension in spec.dimensions:
        if dimension in cells.schema.names:
            values = pc.unique(cells.column(dimension)).to_pylist()
            # An empty string is a row whose dimension column was blank, not a
            # level. Offering it as a selectable chip invites filtering on
            # nothing; its mass still reaches every marginal, unfiltered.
            observed[dimension] = sorted(
                str(v) for v in values if v is not None and str(v).strip() != ""
            )

    periods = sorted({str(p) for p in cells.column("competencia").to_pylist() if p})

    # --- dimensions -----------------------------------------------------
    support = dict(manifest.get("support") or {})
    dimensions: list[Dimension] = []
    with Catalog(resolved.catalog_path) as store:
        docs_system = (semantics.system or "").upper()
        try:
            from .semantics.curation import load_variable_docs

            docs = load_variable_docs(store, docs_system)
        except Exception:  # pragma: no cover - a catalog without variable docs
            docs = {}
        for dimension in spec.dimensions:
            codes = observed.get(dimension, [])
            try:
                mapping = codelist_levels(
                    dimension, store=store, lake_root=resolved.lake_dir,
                    system=docs_system, codes=codes,
                )
            except Exception:  # pragma: no cover - a missing reference table
                mapping = {}
            declared_levels = dict(spec.level_labels.get(dimension) or {})
            levels = tuple(
                # The ladder, per level: the spec's own statement, then the
                # reference tables, then the honest raw code.
                Level(
                    code=code,
                    label=declared_levels.get(code) or mapping.get(code) or code,
                )
                for code in codes
            )
            per_year = {
                year: str((flags or {}).get(dimension) or "unknown")
                for year, flags in support.items()
            }
            unlabelled = sum(1 for lv in levels if lv.label == lv.code)
            doc = docs.get(dimension)
            note = str(getattr(doc, "description", "") or "") if doc else ""
            if unlabelled and levels:
                note = (
                    f"{unlabelled} de {len(levels)} níveis não têm rótulo nas "
                    "tabelas de referência e aparecem como o próprio código"
                )
            derived = None
            if spec.age is not None and dimension == spec.age.name:
                derived = "age_band"
            elif any(dimension == b.name for b in spec.band_dims):
                derived = "band"
            dimensions.append(Dimension(
                id=dimension,
                label=_label_for(dimension, spec.dimension_labels, docs),
                kind="nominal",
                levels=levels,
                cardinality=len(levels),
                control=_control_for(len(levels)),
                support=per_year,
                note=note,
                derived=derived,
            ))

    # --- measures -------------------------------------------------------
    geography_bindings = semantics.geography_bindings()
    active_geography = geography_bindings.get(spec.geography_binding) or {}
    denominator_ok = _denominator_compatible(
        spec.geography_binding, active_geography, DENOMINATOR_COMPATIBLE_ROLES)

    measures = tuple(
        MeasureCapability(
            id=m.name,
            label=m.label or _humanise(m.name),
            kind=m.kind.name,
            components=m.state_columns(),
            formula=m.formula(),
            unit=m.unit,
            decimals=_decimals_for(m.kind.name, m.unit),
            additive_over=tuple(sorted(m.additive_over)),
            forbidden=_FORBIDDEN.get(m.kind.name, ()),
            encodings=_ENCODINGS.get(m.kind.name, ("line",)),
            requires_binding=None,
            time_reducer=m.time_reducer,
        )
        for m in spec.measures
    )

    # --- geography ------------------------------------------------------
    # What this build could have SEEN. Distinct from what it found: a
    # municipality outside the fetched UFs was never in view, and reading its
    # absence as a zero turns one state into a country.
    observed = sorted({str(code)[:2] for code in cells.column("municipality").to_pylist() if code})
    declared_uf = [str(u).upper() for u in (manifest.get("uf") or ())]
    coverage = {
        "kind": "partial" if declared_uf else "unknown",
        # The UFs the build FETCHED. Empty means it was not recorded -- older
        # artifacts predate this, and guessing from the cells would be wrong:
        # a national build of a rare condition also touches few states.
        "declared_ufs": declared_uf,
        # The UF prefixes actually present, which is a measurement either way.
        "observed_ufs": observed,
        "municipalities": len({str(c) for c in cells.column("municipality").to_pylist() if c}),
        "note": (
            f"Construído apenas a partir de {', '.join(declared_uf)}. "
            "Um município sem célula NÃO foi observado — não é zero — e "
            "qualquer total aqui é o total desse subconjunto."
            if declared_uf else ""
        ),
    }
    if not declared_uf:
        coverage["kind"] = "national" if len(observed) >= 25 else "unknown"

    declared = classifications(Path(root) if root else None)
    # `uf` is BOTH a base grain and an IBGE classification, so the two lists
    # overlap. Deduplicated with order kept: the first three are the grains
    # every artifact has, and the rest are what geography.yml declares.
    from ._aggregate import _BASE_LEVEL, _NATIONAL_LEVEL, _UF_LEVEL

    grains = [_BASE_LEVEL, _UF_LEVEL, _NATIONAL_LEVEL]
    hierarchies: dict[str, list[dict[str, Any]]] = {"political": [], "health": []}
    for key, body in declared.items():
        if body.get("attribute"):
            # `capital` is an attribute, not a containment. Rolling up to it is
            # not a partition of Brazil, so it is not a grain.
            continue
        if key not in grains:
            grains.append(key)
        authority = str(body.get("authority") or "datasus")
        tree = "political" if authority == "ibge" else "health"
        hierarchies[tree].append({
            "id": key,
            "authority": authority,
            "partial_coverage": bool(body.get("partial_coverage")),
            "what": str(body.get("what") or "").strip(),
        })

    spatial = {
        "bindings": [
            asdict(_binding(
                key, body, active=(key == spec.geography_binding),
                denominator=_denominator_compatible(
                    key, body, DENOMINATOR_COMPATIBLE_ROLES),
            ))
            for key, body in geography_bindings.items()
        ],
        "active_binding": spec.geography_binding,
        "grains": grains,
        "default_grain": _BASE_LEVEL,
        "hierarchies": [
            {"id": "political", "label": "Político-administrativa",
             "authority": "ibge", "levels": hierarchies["political"]},
            {"id": "health", "label": "Saúde",
             "authority": "datasus", "levels": hierarchies["health"]},
        ],
        "default_hierarchy": "political",
        "code_system": "ibge_municipality",
        "join_key": "code7",
        "denominator_compatible": denominator_ok,
        "coverage": coverage,
    }

    # --- time -----------------------------------------------------------
    time_bindings = semantics.time_bindings()
    active_time = time_bindings.get(spec.time_binding) or {}
    encoding = str(active_time.get("encoding") or "")
    temporal = {
        "bindings": [
            asdict(_binding(key, body, active=(key == spec.time_binding)))
            for key, body in time_bindings.items()
        ],
        "active_binding": spec.time_binding,
        "grains": ["month", "year"] if spec.time_grain == "month" else ["year"],
        "default_grain": spec.time_grain,
        "encoding": encoding,
    }

    partial = [str(p) for p in (manifest.get("partial_periods") or ())]
    completeness = {
        # `competence` IS the publication coordinate, so every period inside a
        # fetched year is whole. A record date is not, and the artifact says
        # which periods it therefore cannot have filled -- measured during the
        # build, never assumed from a file name.
        "kind": "competence" if encoding in ("year_month", "year", "yyyymm") else "record_date",
        "partial_periods": partial,
        "support": support,
        "warnings": list(manifest.get("warnings") or ()),
    }

    return Capability(
        id=name,
        dataset=spec.dataset,
        system=semantics.system,
        series=semantics.series,
        label=spec.label or spec.dataset,
        description=(spec.description or "").strip(),
        observation_unit=str(getattr(semantics.grain, "prose", "") or ""),
        grain_components=tuple(getattr(semantics.grain, "components", ()) or ()),
        period_bearing=bool(getattr(semantics.grain, "is_period_bearing", False)),
        vintage=_vintage(manifest_path),
        fingerprint=str(manifest.get("fingerprint") or ""),
        period={
            "from": _as_period(periods[0]) if periods else None,
            "to": _as_period(periods[-1]) if periods else None,
            "grain": spec.time_grain,
            "years": [int(y) for y in (manifest.get("years") or ())],
        },
        spatial=spatial,
        temporal=temporal,
        completeness=completeness,
        dimensions=tuple(dimensions),
        measures=measures,
        provenance={
            "engine_version": str(manifest.get("engine_version") or ""),
            "cells": int(manifest.get("cells") or 0),
            "rows_read": int(manifest.get("rows_read") or 0),
            "built_from": spec.dataset,
        },
        denominators=_denominators(
            resolved, tuple(int(y) for y in (manifest.get("years") or ()))),
    )


def _denominator_compatible(
    key: str, body: dict[str, Any], roles: frozenset[str]
) -> bool:
    """Curation may override the role rule; otherwise the role decides."""
    declared = body.get("denominator")
    if declared is not None:
        return bool(declared)
    return key in roles


def _binding(
    key: str, body: dict[str, Any], *, active: bool,
    denominator: bool | None = None,
) -> Binding:
    return Binding(
        id=key,
        label=_humanise(key),
        fields=tuple(str(f) for f in (body.get("fields") or ())),
        active=active,
        denominator_compatible=denominator,
        encoding=str(body.get("encoding")) if body.get("encoding") else None,
        note=str(body.get("note") or ""),
    )


def _as_period(raw: str) -> str:
    """`202203` -> `2022-03`; `2022` stays `2022`."""
    text = str(raw)
    return f"{text[:4]}-{text[4:6]}" if len(text) == 6 else text


def _vintage(manifest_path: Path) -> str:
    from datetime import datetime

    stamp = manifest_path.stat().st_mtime
    return datetime.fromtimestamp(stamp, tz=UTC).isoformat(timespec="seconds")


def catalogue(
    *, settings: Settings | None = None, root: str | Path | None = None
) -> list[dict[str, Any]]:
    """Every spec, and whether it has been built.

    Unbuilt specs are listed with ``built: false`` rather than hidden, so an
    operator can see what the deployment is missing instead of wondering why a
    dataset never appears.
    """
    from ._aggregate import artifact_dir, load_specs
    from .config import load_settings
    from .semantics.curation import semantics_for

    resolved = settings or load_settings(root=Path(root) if root else None)
    out: list[dict[str, Any]] = []
    for name, spec in sorted(load_specs(Path(root) if root else None).items()):
        directory = artifact_dir(name, resolved)
        manifest_path = directory / "manifest.json"
        built = manifest_path.exists() and (directory / "cells.parquet").exists()
        # The system identity travels with the listing. A picker that says only
        # "Óbitos" hides WHICH mortality system that is — and DATASUS has more
        # than one thing a reader could mistake it for. The label names the
        # subject; the system names the source, and both are needed to know
        # what you are looking at.
        semantics = semantics_for(spec.dataset)
        entry: dict[str, Any] = {
            "id": name,
            "dataset": spec.dataset,
            "label": spec.label or spec.dataset,
            "system": getattr(semantics, "system", None) if semantics else None,
            "series": getattr(semantics, "series", None) if semantics else None,
            "observation_unit": str(
                getattr(getattr(semantics, "grain", None), "prose", "") or ""
            ) if semantics else "",
            "description": (spec.description or "").strip(),
            "dimensions": list(spec.dimensions),
            "measures": [m.name for m in spec.measures],
            "time_grain": spec.time_grain,
            "built": built,
        }
        if built:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry["years"] = [int(y) for y in (manifest.get("years") or ())]
            entry["cells"] = int(manifest.get("cells") or 0)
            entry["fingerprint"] = str(manifest.get("fingerprint") or "")
            entry["vintage"] = _vintage(manifest_path)
        out.append(entry)
    return out
