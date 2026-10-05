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
  death, counted from the records as events of their declared type, per year,
  with ``share`` (the part of the origin's events going to ``to``); to the
  hospital's municipality or, with ``destination="establishment"``, to its
  CNES. Computed on request, since it depends on what the lake holds. Its
  derived products (self-sufficiency, catchments, flow communities, the
  comparison with official health regions) are in ``careflow.py``.

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


#: dataset -> (event type, origin column, destination column, what the flow is). SIH-RD reads the
#: residence through ``MUNIC_RES_municipio``, which gives Brasilia's 2008-2017 administrative-region
#: codes (530020 ... 530180) back to the one municipality, 530010 (DATA_SOURCES; OQ-71).
FLOWS = {
    "SIH-RD": ("hospitalisation", "MUNIC_RES_municipio", "MUNIC_MOV", "residence -> hospital municipality"),
    "CIHA": ("hospitalisation", "MUNIC_RES", "MUNIC_MOV", "residence -> hospital municipality"),
    "SINASC-DN": ("birth", "CODMUNRES", "CODMUNNASC", "mother's residence -> place of birth"),
    "SIM-DO": ("death", "CODMUNRES", "CODMUNOCOR", "residence -> place of death"),
}
#: dataset -> the column naming the establishment: the institution variant of the same graph
#: (``destination="establishment"``), for the institution lattice.
FACILITIES = {"SIH-RD": "CNES", "SINASC-DN": "CODESTAB"}


def care_flows(dataset: str, *, period: object, geography: object = "BR", by: str | None = None,
               level: str | None = None, destination: str = "municipality", **query_kwargs: Any) -> pa.Table:
    """The care-flow graph: events moving from residence to where they happened, per year.

    One edge per (``from``, ``to``, ``vintage`` = the year [, ``by``]): ``weight`` is the events,
    ``share`` the part of the origin's events in the same year (and ``by`` group) that went to
    ``to``, ``kind`` ``care_flow:<dataset>``. Municipalities are IBGE's 7-digit codes, as in the
    other graphs. ``by`` names a classifier and ``level`` a level of its code structure
    (``by="DIAG_PRINC", level="chapter"``, or ``by="COMPLEX"``).

    ``destination="establishment"`` ends the edges at the facility (SIH ``CNES``) instead of its
    municipality: the institution graph, whose ``to`` is the CNES code.

    Every event is accounted for. The table's metadata carries the events counted (``events``),
    those whose origin or destination is blank (``unplaced``) and those whose municipality code is
    none of IBGE's (``unresolved``), with the codes per year in ``accounting``; the edges sum to
    ``events - unplaced - unresolved``. ``geography`` selects publications (SIH files are by the
    hospital's state), so a state gives the flows into its hospitals, not out of its residents.
    """
    import json

    from ._aggregate import _tree_pushforward
    from ._query_engine.executor import query
    from ._query_engine.model import _period
    from .geography import municipalities
    from .semantics.event_types import event_type, events_of

    key = dataset.upper()
    if key not in FLOWS:
        raise KeyError(f"no flow declared for {dataset!r}; declared: {sorted(FLOWS)}")
    if destination not in ("municipality", "establishment"):
        raise ValueError("destination is 'municipality' or 'establishment'")
    name, origin, to_column, _what = FLOWS[key]
    if destination == "establishment":
        if key not in FACILITIES:
            raise KeyError(f"{dataset} declares no establishment column; declared: {sorted(FACILITIES)}")
        to_column = FACILITIES[key]
    event = event_type(dataset, name)
    columns = {origin, to_column, *(c for c in (event.status_column, *event.consolidation_key) if c),
               *([by] if by else [])}
    span = _period(period)
    if span is None:
        raise ValueError("care flows are counted per year: pass a period")
    code7 = {c6: row["code7"] for c6, row in municipalities().items()}
    known7 = frozenset(code7.values())

    def trimmed(values: pa.ChunkedArray) -> pa.Array:
        text = pc.utf8_trim_whitespace(pc.cast(values, pa.string()))
        return pc.if_else(pc.fill_null(pc.equal(text, ""), True), pa.scalar(None, pa.string()), text)

    def municipal(text: pa.Array) -> pa.Array:
        """6-digit DATASUS (or 7-digit IBGE) codes to IBGE's 7 digits; none for a code that is no municipality."""
        uniques = pc.unique(text).drop_null()
        resolved = pa.array([code7.get(u) or (u if u in known7 else None) for u in uniques.to_pylist()], pa.string())
        return pc.take(resolved, pc.index_in(text, value_set=uniques))

    pieces, accounting, events_total, unplaced_total, unresolved_total = [], {}, 0, 0, 0
    for year in span.years:
        part = events_of(query(dataset, period=str(year), geography=geography, select=sorted(columns),
                               present="codes", **query_kwargs), event)
        raw_o, raw_d = trimmed(part.column(origin)), trimmed(part.column(to_column))
        o = municipal(raw_o)
        d = municipal(raw_d) if destination == "municipality" else raw_d
        placed = pc.and_(pc.is_valid(raw_o), pc.is_valid(raw_d))
        usable = pc.and_(pc.is_valid(o), pc.is_valid(d))
        unresolved = pc.and_(placed, pc.invert(usable))
        n_unplaced, n_unresolved = part.num_rows - (pc.sum(placed).as_py() or 0), pc.sum(unresolved).as_py() or 0
        lost = pc.filter(pc.if_else(pc.is_valid(o), raw_d, raw_o), unresolved)
        accounting[str(year)] = {"events": part.num_rows, "unplaced": n_unplaced, "unresolved": n_unresolved,
                                 "unresolved_codes": {c["values"]: c["counts"] for c in
                                                      sorted(pc.value_counts(lost).to_pylist(), key=lambda c: -c["counts"])[:30]}}
        events_total, unplaced_total, unresolved_total = (events_total + part.num_rows, unplaced_total + n_unplaced,
                                                          unresolved_total + n_unresolved)
        parts = {"from": pc.filter(o, usable), "to": pc.filter(d, usable)}
        if by:
            values = pc.filter(pc.cast(part.column(by), pa.string()), usable)
            if level:
                from .semantics.event_types import load_event_types

                structure = next((c.structure for e in load_event_types().get(_flow_key(dataset), ())
                                  for c in e.classifiers if c.column == by and c.structure), None)
                if structure is None:
                    raise KeyError(f"{by} has no declared code structure to roll up to {level!r}")
                mapping = _tree_pushforward(structure, level, tuple(pc.unique(values).drop_null().to_pylist()))
                values = pc.take(pa.array(list(mapping.values()), pa.string()),
                                 pc.index_in(values, value_set=pa.array(list(mapping), pa.string())))
            parts[by] = values
        counted = pa.table(parts).group_by(list(parts)).aggregate([([], "count_all")]).rename_columns([*parts, "weight"])
        pieces.append(counted.append_column("vintage", pa.array([year] * counted.num_rows, pa.int32())))
        del part
    flows = pa.concat_tables(pieces, promote_options="default")
    import duckdb

    # share: the origin's events of the year (and group) going to `to`; a window, since a null group is a group.
    cut = ", ".join(['"vintage"', '"from"', *([f'"{by}"'] if by else [])])
    flows = duckdb.sql(f'SELECT *, weight / sum(weight) OVER (PARTITION BY {cut}) AS share FROM flows '
                       'ORDER BY vintage, "from", weight DESC, "to"').to_arrow_table()
    kind = f"care_flow:{key}" + (":establishment" if destination == "establishment" else "")
    flows = flows.append_column("kind", pa.array([kind] * flows.num_rows, pa.string()))
    flows = flows.select(["from", "to", "weight", "kind", "vintage", "share", *([by] if by else [])])
    return flows.replace_schema_metadata({
        b"events": str(events_total).encode(), b"unplaced": str(unplaced_total).encode(),
        b"unresolved": str(unresolved_total).encode(), b"accounting": json.dumps(accounting, ensure_ascii=False).encode()})


def _flow_key(dataset: str) -> str:
    from .semantics.event_types import _key

    return _key(dataset)
