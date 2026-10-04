"""Proximity graphs between municipalities, as edge lists (handoff §6; DESIGN §4).

Every graph is ``(from, to, weight, kind, vintage)`` with 7-digit IBGE codes:

* ``contiguity``: municipalities that share a border, weighted by its length
  in km, from IBGE's 2022 municipal mesh (maximum quality). Lake and sea
  shores are not borders. Built once, shipped (``proximity.parquet``).
* ``population_distance``: the population-weighted mean distance in km
  between the people of two municipalities, from Census 2022 tracts
  aggregated to a 5 km grid, for each municipality's 30 nearest and its
  neighbours. Shipped.
* ``regic_network``, ``regic_health_basic``, ``regic_health_high``: IBGE's
  REGIC 2018 links between cities (a municipality, or the core municipality
  standing for a population arrangement): the urban-network links
  (``vinculo``), and the links for low/medium and for high-complexity health
  care, weighted by their order (1 the strongest, 3 the weakest). Shipped.
  ``regic_cities()`` maps every municipality to its REGIC city and level.
* ``care_flow`` (:func:`care_flows`): residence -> place of care, birth or
  death, counted from the records as events of their declared type, per year;
  computed on request, since it depends on what the lake holds.

Areas (km², the mesh in SIRGAS 2000 / Brazil Polyconic) are served by
:func:`municipality_areas`. New municipalities: a code the 2022 mesh lacks
has no contiguity row and says so rather than inheriting a neighbour's.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

PROXIMITY_PACK_NAME = "proximity.parquet"
REGIC_PACK_NAME = "regic_cities.parquet"
AREAS_PACK_NAME = "municipality_areas.parquet"
_PROJECTED = "EPSG:5880"   # SIRGAS 2000 / Brazil Polyconic, metres
_GRID_M = 5000
_NEAREST = 30


def _polygonal(geometry: Any) -> Any:
    """The (multi)polygon inside a repaired geometry; collections lose their lines and points."""
    import shapely

    if geometry is None or geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    parts = [g for g in shapely.get_parts(geometry) if g.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else None


def build_proximity_graphs(out_dir: str | Path, *, mesh: str | Path, tracts: str | Path) -> dict[str, Any]:
    """Write ``proximity.parquet`` (contiguity, population distance) and the areas table."""
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq
    from scipy.spatial import cKDTree

    out = Path(out_dir)
    polygons = gpd.read_file(mesh)[["codarea", "geometry"]].set_crs("EPSG:4674", allow_override=True)
    polygons["code"] = polygons["codarea"].astype(str)
    projected = polygons.to_crs(_PROJECTED)
    # make_valid can return a GeometryCollection (the polygon plus stray lines or points); its
    # boundary is None, which left 32 borders without a length (PegaSUS, 2026-10-04). Keep the
    # polygonal part only.
    projected["geometry"] = projected.geometry.make_valid().apply(_polygonal)
    # One geometry per municipality: a code in several pieces is one polygon,
    # and an empty piece is no geometry at all.
    projected = projected[projected.geometry.notna() & ~projected.geometry.is_empty]
    projected = projected[["code", "geometry"]].dissolve(by="code").reset_index()
    areas = pd.DataFrame({"municipality7": projected["code"], "area_km2": (projected.area / 1e6).round(3)})

    # Contiguity: shared boundary length. A spatial self-join on touching or
    # intersecting polygons, then the length of the intersection of their
    # boundaries (a point contact has length 0 and is kept as a 0 km border).
    joined = gpd.sjoin(projected[["code", "geometry"]], projected[["code", "geometry"]],
                       how="inner", predicate="intersects")
    joined = joined[joined["code_left"] < joined["code_right"]]
    import shapely

    boundary = projected.set_index("code").geometry.boundary
    lengths = shapely.length(shapely.intersection(
        boundary.loc[joined["code_left"]].values, boundary.loc[joined["code_right"]].values)) / 1000
    contiguity = pd.DataFrame({"from": joined["code_left"].values, "to": joined["code_right"].values,
                               "weight": np.round(lengths, 3)})
    contiguity = pd.concat([contiguity, contiguity.rename(columns={"from": "to", "to": "from"})])
    contiguity["kind"], contiguity["vintage"] = "contiguity", 2022

    # Population on a 5 km grid per municipality, from the Census 2022 tracts.
    tr = gpd.read_file(tracts, columns=["CD_SETOR", "CD_MUN", "v0001"])
    tr = tr.dissolve(by="CD_SETOR", aggfunc="first").reset_index()
    tr["people"] = pd.to_numeric(tr["v0001"], errors="coerce").fillna(0)
    tr = tr[tr["people"] > 0]
    point = tr.to_crs(_PROJECTED).geometry.representative_point()
    grid = pd.DataFrame({"code": tr["CD_MUN"].astype(str).values,
                         "gx": (point.x // _GRID_M).astype(int).values, "gy": (point.y // _GRID_M).astype(int).values,
                         "x": point.x.values, "y": point.y.values, "people": tr["people"].values})
    grid["wx"], grid["wy"] = grid["x"] * grid["people"], grid["y"] * grid["people"]
    cells = grid.groupby(["code", "gx", "gy"], as_index=False)[["people", "wx", "wy"]].sum()
    cells["x"], cells["y"] = cells["wx"] / cells["people"], cells["wy"] / cells["people"]
    by_code = {c: g[["x", "y", "people"]].to_numpy() for c, g in cells.groupby("code")}
    centre = {c: (v[:, 0] @ v[:, 2] / v[:, 2].sum(), v[:, 1] @ v[:, 2] / v[:, 2].sum()) for c, v in by_code.items()}
    codes = sorted(centre)
    xy = np.array([centre[c] for c in codes])
    _, nearest = cKDTree(xy).query(xy, k=min(_NEAREST + 1, len(codes)))
    pairs = {(codes[i], codes[j]) for i, row in enumerate(nearest) for j in row if i != j}
    pairs |= {(a, b) for a, b in zip(contiguity["from"], contiguity["to"], strict=True)
              if a in by_code and b in by_code}
    rows = []
    for a, b in sorted(pairs):
        pa_, pb_ = by_code[a], by_code[b]
        d = np.hypot(pa_[:, None, 0] - pb_[None, :, 0], pa_[:, None, 1] - pb_[None, :, 1])
        w = pa_[:, None, 2] * pb_[None, :, 2]
        rows.append((a, b, round(float((d * w).sum() / w.sum()) / 1000, 3)))
    distance = pd.DataFrame(rows, columns=["from", "to", "weight"])
    distance["kind"], distance["vintage"] = "population_distance", 2022

    edges = pd.concat([contiguity, distance], ignore_index=True)
    edges["from"], edges["to"] = edges["from"].astype(str), edges["to"].astype(str)
    pq.write_table(pa.Table.from_pandas(edges[["from", "to", "weight", "kind", "vintage"]], preserve_index=False).replace_schema_metadata(None),
                   out / PROXIMITY_PACK_NAME, compression="zstd")
    pq.write_table(pa.Table.from_pandas(areas, preserve_index=False).replace_schema_metadata(None), out / AREAS_PACK_NAME, compression="zstd")
    return {"municipalities_in_mesh": len(polygons), "contiguity_edges": len(contiguity),
            "population_distance_edges": len(distance), "municipalities_with_population": len(by_code),
            "without_neighbour": int(len(set(polygons["code"]) - set(contiguity["from"])))}


def build_regic(out_dir: str | Path, *, links: str | Path, cities: str | Path, arrangements: str | Path) -> dict[str, Any]:
    """Append REGIC 2018's links to ``proximity.parquet`` and write ``regic_cities.parquet``."""
    import pandas as pd
    import pyarrow.parquet as pq
    import pyogrio

    out = Path(out_dir)
    df = pyogrio.read_dataframe(links, read_geometry=False)
    edges = []
    network = df[df["vinculo"].astype(str).str.lower() == "sim"]
    edges.append(pd.DataFrame({"from": network["cod_ori"], "to": network["cod_dest"], "weight": 1.0,
                               "kind": "regic_network"}))
    for column, kind in (("quest_3", "regic_health_basic"), ("quest_4", "regic_health_high")):
        order = pd.to_numeric(df[column], errors="coerce").fillna(0)
        part = df[order > 0]
        edges.append(pd.DataFrame({"from": part["cod_ori"], "to": part["cod_dest"],
                                   "weight": order[order > 0].astype(float), "kind": kind}))
    regic = pd.concat(edges, ignore_index=True)
    regic["from"], regic["to"], regic["vintage"] = regic["from"].astype(str), regic["to"].astype(str), 2018
    existing = pq.read_table(out / PROXIMITY_PACK_NAME).to_pandas()
    existing = existing[~existing["kind"].str.startswith("regic_")]
    merged = pd.concat([existing, regic[["from", "to", "weight", "kind", "vintage"]]], ignore_index=True)
    pq.write_table(pa.Table.from_pandas(merged, preserve_index=False).replace_schema_metadata(None), out / PROXIMITY_PACK_NAME, compression="zstd")

    city = pd.read_excel(cities, sheet_name=0)[["COD_CIDADE", "NOME_CIDADE", "VAR09", "VAR10"]]
    city.columns = ["city", "city_name", "level", "level_name"]
    members = pd.read_excel(arrangements, sheet_name=0)[["Codmun", "Código do AP"]]
    members.columns = ["municipality7", "city"]
    alone = city[~city["city"].isin(members["city"])][["city"]].assign(municipality7=lambda d: d["city"])
    nodes = pd.concat([members, alone[["municipality7", "city"]]]).merge(city, on="city", how="left")
    nodes = nodes.astype({"municipality7": str, "city": str}).drop_duplicates("municipality7")
    pq.write_table(pa.Table.from_pandas(nodes, preserve_index=False).replace_schema_metadata(None), out / REGIC_PACK_NAME, compression="zstd")
    return {"regic_edges": {k: int(v) for k, v in regic["kind"].value_counts().items()},
            "municipalities_placed": len(nodes), "cities": len(city)}


def regic_cities() -> pa.Table:
    """``municipality7 -> REGIC 2018 city`` (itself, or its arrangement's core), with the city's level."""
    return _pack(REGIC_PACK_NAME)


@lru_cache(maxsize=4)
def _pack(name: str) -> pa.Table:
    import pyarrow.parquet as pq

    return pq.read_table(Path(__file__).resolve().parent / "resources" / name)


def proximity_graph(kind: str) -> pa.Table:
    """A shipped graph as an edge list: ``contiguity`` or ``population_distance``."""
    edges = _pack(PROXIMITY_PACK_NAME)
    part = edges.filter(pc.equal(edges.column("kind"), kind))
    if not part.num_rows:
        raise KeyError(f"no proximity graph {kind!r}; shipped: {sorted(set(edges.column('kind').to_pylist()))}"
                       "; care flows come from care_flows()")
    return part


def municipality_areas() -> pa.Table:
    """``municipality7 -> area_km2`` from the 2022 mesh."""
    return _pack(AREAS_PACK_NAME)


#: dataset -> (event type, origin column, destination column, what the flow is)
FLOWS = {
    "SIH-RD": ("hospitalisation", "MUNIC_RES", "MUNIC_MOV", "residence -> hospital municipality"),
    "CIHA": ("hospitalisation", "MUNIC_RES", "MUNIC_MOV", "residence -> hospital municipality"),
    "SINASC-DN": ("birth", "CODMUNRES", "CODMUNNASC", "mother's residence -> place of birth"),
    "SIM-DO": ("death", "CODMUNRES", "CODMUNOCOR", "residence -> place of death"),
}


def care_flows(dataset: str, *, period: object, geography: object = "BR", by: str | None = None,
               level: str | None = None, **query_kwargs: Any) -> pa.Table:
    """Events moving from residence to where they happened, per year (and per ``by``).

    ``by`` names a classifier and ``level`` a level of its code structure
    (``by="DIAG_PRINC", level="chapter"``), for flows per specialty or chapter.
    Every event is counted once: the flows of a year sum to that year's events,
    and an event whose origin or destination is blank is reported, not dropped
    silently (``unplaced`` in the table's metadata).
    """
    from ._aggregate import _tree_pushforward
    from ._query_engine.executor import query
    from .semantics.event_types import event_type, events_of

    key = dataset.upper()
    if key not in FLOWS:
        raise KeyError(f"no flow declared for {dataset!r}; declared: {sorted(FLOWS)}")
    name, origin, destination, _what = FLOWS[key]
    event = event_type(dataset, name)
    columns = {origin, destination, *(c for c in (event.status_column, *event.consolidation_key) if c),
               *([by] if by else [])}
    from ._query_engine.model import _period

    span = _period(period)
    if span is None:
        raise ValueError("care flows are counted per year: pass a period")
    pieces = []
    for year in span.years:
        part = events_of(query(dataset, period=str(year), geography=geography, select=sorted(columns),
                               present="codes", **query_kwargs), event)
        pieces.append(part.append_column("__year", pa.array([str(year)] * part.num_rows, pa.string())))
    table = pa.concat_tables(pieces, promote_options="default")
    years = table.column("__year")
    o = pc.utf8_trim_whitespace(pc.cast(table.column(origin), pa.string()))
    d = pc.utf8_trim_whitespace(pc.cast(table.column(destination), pa.string()))
    placed = pc.and_(pc.and_(pc.is_valid(o), pc.is_valid(d)), pc.and_(pc.not_equal(o, ""), pc.not_equal(d, "")))
    unplaced = table.num_rows - (pc.sum(placed).as_py() or 0)
    parts = {"from": pc.filter(o, placed), "to": pc.filter(d, placed), "vintage": pc.filter(years, placed)}
    if by:
        codes = pc.filter(pc.cast(table.column(by), pa.string()), placed)
        if level:
            from .semantics.event_types import load_event_types

            structure = next((c.structure for e in load_event_types().get(_flow_key(dataset), ())
                              for c in e.classifiers if c.column == by and c.structure), None)
            if structure is None:
                raise KeyError(f"{by} has no declared code structure to roll up to {level!r}")
            mapping = _tree_pushforward(structure, level, tuple(pc.unique(codes).drop_null().to_pylist()))
            keys = pa.array(list(mapping), pa.string())
            codes = pc.take(pa.array(list(mapping.values()), pa.string()), pc.index_in(codes, value_set=keys))
        parts[by] = codes
    flows = pa.table(parts).group_by(list(parts)).aggregate([([], "count_all")]).rename_columns(
        [*parts, "weight"])
    flows = flows.append_column("kind", pa.array([f"care_flow:{key}"] * flows.num_rows, pa.string()))
    return flows.replace_schema_metadata({b"events": str(table.num_rows).encode(), b"unplaced": str(unplaced).encode()})


def _flow_key(dataset: str) -> str:
    from .semantics.event_types import _key

    return _key(dataset)
