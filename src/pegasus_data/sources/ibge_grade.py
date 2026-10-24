"""IBGE's Grade Estatística 2022: where Brazil's people live, on a regular equal-area grid (ADR-0203).

**The product** (IBGE, Notas metodológicas 01/2025, Grade Estatística; ``SOURCE`` below): 14,127,809 square cells in
the Albers equal-area projection on SIRGAS 2000 (central meridian −54°, origin −12°, standard parallels −2° and −22°,
false origin 5,000,000 E and 10,000,000 N), 200 m × 200 m where the cell meets an urban Census 2022 tract and
1 km × 1 km elsewhere. Each cell holds ``TOTAL`` (residents) and ``TOTAL_DOM`` (occupied households, private and
collective) of the 2022 Census universe, placed by the coordinates of each household in CNEFE 2022. Households whose
coordinate is only a street median or a tract centroid (CNEFE's levels 5 and 6) are left out: 56,229 people, so the
grid holds 203,002,064 of the census's 203,058,293 (0.028 %; Quadro 02). There is no sex, age or municipality in it.

**What this module adds** is the municipality. A cell is assigned to the municipalities of IBGE's municipal mesh
(`geography.mesh_file`, maximum quality) it intersects, with ``share`` the part of its area inside each (the shares of
a cell sum to 1; a coastal cell inside one municipality has share 1 whatever part of it is sea). A cell crossing a
border is split by area, which assumes its people spread evenly over it: at 200 m in towns and 1 km elsewhere, the
assumption touches only border cells, and their number is reported. A cell that meets no municipality keeps
``municipality7`` null when empty; one with people (an islet, a shore the mesh's line leaves out) goes whole to the
nearest municipality, with ``placed`` "nearest" instead of "area" and the people and distance reported.

**Stored** once per data home in ``registries/ibge_grade/``: the 56 zipped shapefiles as IBGE publishes them and
``cells_2022.parquet``, one row per cell and municipality (``cell``, ``size_m``, ``x``, ``y``: the south-west corner in
the Albers metres, ``municipality7``, ``share``, ``placed``, ``total``, ``total_dom``: the cell's whole counts, never split in
storage). Counts are only ever summed: `cells` multiplies by the share and aggregates to a coarser cell with sums,
never means (CLAUDE.md §6).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

SOURCE = "https://geoftp.ibge.gov.br/recortes_para_fins_estatisticos/grade_estatistica/censo_2022/"
NOTE = SOURCE + "Notas_metodologicas_grade_estatistica_2022.pdf"
#: IBGE's projection of the grade (Notas metodológicas 01/2025, p. 5)
ALBERS = ("+proj=aea +lat_0=-12 +lon_0=-54 +lat_1=-2 +lat_2=-22 +x_0=5000000 +y_0=10000000 "
          "+ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs")
#: The grade's own coarser cells (its ``nome_<n>KM`` columns), in metres
RESOLUTIONS = (1000, 5000, 10000, 50000, 100000, 500000)
#: Totals the note publishes for the grade (Quadros 02 and 03, levels 1-4): the build is checked against them
PUBLISHED_TOTAL, PUBLISHED_TOTAL_DOM = 203_002_064, 72_546_543
CELLS_NAME = "cells_2022.parquet"
#: Points per side sampled over a border cell to share it between municipalities
SAMPLES = 8

__all__ = ["ALBERS", "RESOLUTIONS", "build", "cell_lonlat", "cells", "geometry", "grid_weights", "population_points"]


def _directory(root: str | Path | None) -> Path:
    from ..config import load_settings

    return Path(root or load_settings().root) / "registries" / "ibge_grade"


def _quadrants() -> list[str]:
    """The zip files IBGE lists under ``grade_estatistica/`` (one per quadrant of its articulation map)."""
    from ..transport import get_text

    return sorted(set(re.findall(r'href="(grade_id\d+\.zip)"', get_text(SOURCE + "grade_estatistica/"))))


def _read_quadrant(path: Path, polygons: Any, tree: Any, codes: Any) -> tuple[Any, dict[str, int]]:
    """One quadrant's cells with their municipalities and shares (a pyarrow table) and what was found on the way."""
    import geopandas as gpd
    import numpy as np
    import pyarrow as pa
    import shapely

    frame = gpd.read_file(f"zip://{path.as_posix()}", columns=["ID_UNICO", "nome_5KM", "TOTAL", "TOTAL_DOM"])
    if frame.crs is None or frame.crs.to_epsg() not in (4674, None):
        raise ValueError(f"{path.name}: unexpected CRS {frame.crs}")
    frame = frame.set_crs("EPSG:4674", allow_override=True).to_crs(ALBERS)
    ids = frame["ID_UNICO"].to_numpy(dtype=str)
    size = np.where(np.char.startswith(ids, "200M"), 200, np.where(np.char.startswith(ids, "1KM"), 1000, 0))
    if (size == 0).any():
        raise ValueError(f"{path.name}: cells of unknown size, first {ids[size == 0][0]}")
    bounds = frame.geometry.bounds
    x = (np.round(bounds["minx"].to_numpy() / size) * size).astype(np.int64)
    y = (np.round(bounds["miny"].to_numpy() / size) * size).astype(np.int64)
    # The geometry is the authority; the identifier must say the same (the 1 km name is the south-west corner in km, the
    # 200 m name the west edge and the NORTH edge in hectometres: 200ME63250N88392 spans N 8,839,000-8,839,200 m), and
    # the 5 km name is the floor of the corner in kilometres to a multiple of 5.
    parsed = np.array([re.fullmatch(r"(?:200M|1KM)E(\d+)N(\d+)", i).groups() for i in ids], dtype=np.int64)
    unit = np.where(size == 200, 100, 1000)
    north = np.where(size == 200, y + 200, y)
    mismatched = int(((parsed[:, 0] * unit != x) | (parsed[:, 1] * unit != north)).sum())
    five = np.char.add(np.char.add(np.char.add("5KME", ((x // 5000) * 5).astype(str)), "N"), ((y // 5000) * 5).astype(str))
    mismatched_5km = int((five != frame["nome_5KM"].to_numpy(dtype=str)).sum())

    # Each municipal polygon (prepared once) is tested against a tree of the quadrant's boxes, not each box against the
    # full-resolution polygons: a box wholly inside one municipality has share 1; a box on a border has the share of
    # SAMPLES × SAMPLES points spread over it that fall in each polygon (a 1/64 resolution of its area); a border box no
    # sample point lands in (a sliver) takes the exact areas of its intersections.
    boxes = shapely.box(x, y, x + size, y + size)
    boxes_tree = shapely.STRtree(boxes)
    near = tree.query(shapely.box(x.min(), y.min(), (x + size).max(), (y + size).max()), predicate="intersects")
    poly_hit, cell_hit = boxes_tree.query(polygons[near], predicate="intersects")
    poly_hit = near[poly_hit]
    counts = np.bincount(cell_hit, minlength=len(ids))
    order = np.argsort(cell_hit, kind="stable")
    cell_index, poly_index = cell_hit[order], poly_hit[order]
    share = np.ones(len(cell_index))
    split = np.flatnonzero(counts[cell_index] > 1)
    if len(split):
        offsets = (np.arange(SAMPLES) + 0.5) / SAMPLES
        ox, oy = np.meshgrid(offsets, offsets)
        ox, oy = ox.ravel(), oy.ravel()
        cells_ = cell_index[split]
        px = (x[cells_][:, None] + ox[None, :] * size[cells_][:, None]).ravel()
        py = (y[cells_][:, None] + oy[None, :] * size[cells_][:, None]).ravel()
        owner = np.repeat(poly_index[split], len(ox))
        inside = np.zeros(len(px), dtype=bool)
        by_owner = np.argsort(owner, kind="stable")
        bounds_ = np.flatnonzero(np.diff(owner[by_owner])) + 1
        for chunk in np.split(by_owner, bounds_):
            inside[chunk] = shapely.contains_xy(polygons[owner[chunk[0]]], px[chunk], py[chunk])
        hits = inside.reshape(len(split), len(ox)).sum(axis=1).astype(float)
        total_hits = np.bincount(cells_, weights=hits, minlength=len(ids))
        sliver = total_hits[cells_] == 0
        if sliver.any():
            hits[sliver] = shapely.area(shapely.intersection(boxes[cells_[sliver]], polygons[poly_index[split][sliver]]))
            total_hits = np.bincount(cells_, weights=hits, minlength=len(ids))
        share[split] = hits / total_hits[cells_]
        keep = np.ones(len(cell_index), dtype=bool)
        keep[split[share[split] == 0]] = False        # a polygon that only touches the box's edge holds none of it
        cell_index, poly_index, share = cell_index[keep], poly_index[keep], share[keep]
        counts = np.bincount(cell_index, minlength=len(ids))
    total = frame["TOTAL"].to_numpy(dtype=np.int64)
    total_dom = frame["TOTAL_DOM"].to_numpy(dtype=np.int64)
    # A cell outside every polygon with people in it (an islet or a shore the mesh's line leaves out) is placed in the
    # nearest municipality and says so (``placed`` = "nearest"); an empty one has no municipality.
    outside = np.flatnonzero(counts == 0)
    peopled = outside[total[outside] > 0]
    empty = outside[total[outside] == 0]
    nearest = tree.query_nearest(boxes[peopled], return_distance=True, all_matches=False) if len(peopled) else (np.zeros((2, 0), int), np.zeros(0))
    (_, near_poly), distance = nearest
    rows_cell = np.concatenate([cell_index, peopled, empty])
    municipality = np.concatenate([codes[poly_index], codes[near_poly], np.full(len(empty), None, dtype=object)])
    share = np.concatenate([share, np.ones(len(peopled)), np.ones(len(empty))])
    placed = np.concatenate([np.full(len(cell_index), "area", dtype=object), np.full(len(peopled), "nearest", dtype=object),
                             np.full(len(empty), None, dtype=object)])
    table = pa.table({
        "cell": pa.array(ids[rows_cell]), "size_m": pa.array(size[rows_cell], pa.int16()),
        "x": pa.array(x[rows_cell], pa.int32()), "y": pa.array(y[rows_cell], pa.int32()),
        "municipality7": pa.array(municipality, pa.string()), "share": pa.array(share, pa.float32()),
        "placed": pa.array(placed, pa.string()),
        "total": pa.array(total[rows_cell], pa.int32()), "total_dom": pa.array(total_dom[rows_cell], pa.int32())})
    found = {"cells": len(ids), "cells_200m": int((size == 200).sum()), "cells_split": int((counts > 1).sum()),
             "cells_outside": len(outside), "people_outside": int(total[outside].sum()),
             "cells_placed_nearest": len(peopled), "nearest_max_m": round(float(distance.max()), 1) if len(peopled) else 0.0,
             "people": int(total.sum()), "households": int(total_dom.sum()),
             "id_mismatches": mismatched, "id_5km_mismatches": mismatched_5km}
    return table, found


def build(root: str | Path | None = None, log: Any = None) -> dict[str, Any]:
    """Download the grade's 56 quadrants (once) and write ``cells_2022.parquet``: every cell with its municipalities.

    Checked against the note: the people and households summed over the cells equal its published totals, or the build
    raises. Returns what was found: cells, 200 m cells, cells split between municipalities, cells outside every
    municipality (the people in them, placed in the nearest one, and how far) and identifiers that disagree with their
    geometry."""
    import geopandas as gpd
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely

    from ..geography import mesh_file
    from ..proximity import _polygonal
    from ..transport import download

    directory = _directory(root)
    directory.mkdir(parents=True, exist_ok=True)
    names = _quadrants()
    for name in names:
        download(SOURCE + "grade_estatistica/" + name, directory / name, timeout=3600)
    mesh = gpd.read_file(mesh_file("municipality", "maxima", root))[["codarea", "geometry"]]
    mesh = mesh.set_crs("EPSG:4674", allow_override=True).to_crs(ALBERS)
    mesh["geometry"] = mesh.geometry.make_valid().apply(_polygonal)
    mesh = mesh[mesh.geometry.notna() & ~mesh.geometry.is_empty].dissolve(by="codarea").reset_index()
    polygons = mesh.geometry.to_numpy()
    codes = mesh["codarea"].astype(str).to_numpy(dtype=object)
    shapely.prepare(polygons)
    tree = shapely.STRtree(polygons)
    parts, report = [], {"quadrants": len(names), "municipalities_in_mesh": len(codes)}
    for name in names:
        table, found = _read_quadrant(directory / name, polygons, tree, codes)
        parts.append(table)
        for key, value in found.items():
            report[key] = max(report.get(key, 0), value) if key == "nearest_max_m" else report.get(key, 0) + value
        if log:
            log(f"{name}: {found['cells']} cells, {found['people']} people")
    whole = pa.concat_tables(parts)
    # IBGE's quadrants do not overlap: a cell in two files would be counted twice
    unique_cells = len(set(whole.column("cell").to_pylist()))
    if unique_cells != report["cells"]:
        raise ValueError(f"{report['cells'] - unique_cells} cells appear in two quadrants")
    if (report["people"], report["households"]) != (PUBLISHED_TOTAL, PUBLISHED_TOTAL_DOM):
        raise ValueError(f"the grade sums to {report['people']} people and {report['households']} households; the note "
                         f"publishes {PUBLISHED_TOTAL} and {PUBLISHED_TOTAL_DOM}")
    whole = whole.sort_by([("municipality7", "ascending"), ("cell", "ascending")])
    shares = whole.group_by("cell").aggregate([("share", "sum")]).column("share_sum").to_numpy()
    report["share_sum_max_error"] = float(np.abs(shares - 1).max())
    target = directory / CELLS_NAME
    tmp = target.with_name(f"_{target.name}.{os.getpid()}.tmp")
    try:
        pq.write_table(whole, tmp, compression="zstd", row_group_size=1 << 20)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    report["rows"] = whole.num_rows
    report["file"] = str(target)
    return report


def _codes(values: Any, width: int) -> list[str]:
    return [str(v).strip() for v in ([values] if isinstance(values, (str, int)) else values) if len(str(v).strip()) == width]


def cells(*, municipality: Any = None, uf: Any = None, resolution: int | None = None, populated: bool = False,
          by_municipality: bool = True, root: str | Path | None = None) -> Any:
    """The grade as a pyarrow table: ``cell``, ``size_m``, ``x``, ``y`` (south-west corner, Albers metres), ``municipality7``,
    ``share``, ``population`` and ``households`` (the cell's counts × its share in that municipality), ``area_km2``
    (the cell's area × share).

    ``municipality`` (6 or 7 digits, one or several) or ``uf`` (2-digit codes) selects; ``populated`` keeps rows with
    people. ``resolution`` (one of `RESOLUTIONS`, metres) sums the cells into the grade's coarser cells, named as IBGE
    names them (``5KME6325N8835``); with ``by_municipality=False`` a coarse cell is one row whatever municipalities it
    spans. Counts are summed, never averaged. Raises when the grade is not built (`build`, ``pegasus-data grade``)."""
    import duckdb

    path = _directory(root) / CELLS_NAME
    if not path.is_file():
        raise FileNotFoundError(f"the Grade Estatística is not built in {path.parent}; run `pegasus-data grade`")
    if resolution is not None and resolution not in RESOLUTIONS:
        raise ValueError(f"resolution is one of {RESOLUTIONS} metres, or None for the native 200 m / 1 km cells")
    where = []
    if municipality is not None:
        values = [str(v).strip() for v in ([municipality] if isinstance(municipality, (str, int)) else municipality)]
        seven = [v for v in values if len(v) == 7]
        six = [v for v in values if len(v) == 6]
        if len(seven) + len(six) != len(values):
            raise ValueError(f"municipality codes have 6 or 7 digits: {values}")
        clauses = [f"municipality7 IN ({','.join(repr(v) for v in seven)})"] if seven else []
        clauses += [f"substr(municipality7, 1, 6) IN ({','.join(repr(v) for v in six)})"] if six else []
        where.append("(" + " OR ".join(clauses) + ")")
    if uf is not None:
        states = _codes(uf, 2)
        if not states:
            raise ValueError(f"uf takes IBGE's 2-digit state codes: {uf!r}")
        where.append(f"substr(municipality7, 1, 2) IN ({','.join(repr(s) for s in states)})")
    if populated:
        where.append("total > 0")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    base = f"""SELECT cell, size_m, x, y, municipality7, share, total * share AS population, total_dom * share AS households,
                      size_m::DOUBLE * size_m * share / 1e6 AS area_km2
               FROM read_parquet('{path.as_posix()}') {clause}"""
    con = duckdb.connect()
    if resolution is None:
        return con.execute(base + " ORDER BY municipality7, cell").to_arrow_table()
    km, r = resolution // 1000, resolution
    keys = "gx, gy" + (", municipality7" if by_municipality else "")
    return con.execute(f"""
        SELECT '{km}KME' || (gx * {km})::VARCHAR || 'N' || (gy * {km})::VARCHAR AS cell, {r} AS size_m,
               gx * {r} AS x, gy * {r} AS y, {'municipality7,' if by_municipality else ''}
               sum(population) AS population, sum(households) AS households, sum(area_km2) AS area_km2
        FROM (SELECT *, floor(x / {r})::BIGINT AS gx, floor(y / {r})::BIGINT AS gy FROM ({base}))
        GROUP BY {keys} ORDER BY {keys}""").to_arrow_table()


def population_points(resolution: int | None = None, root: str | Path | None = None) -> Any:
    """Where each municipality's people are, as weighted points (a pandas frame): ``municipality7``, ``x`` and ``y``
    (Albers metres), ``lon``, ``lat`` and ``population``. Natively one point per populated cell part (its centre);
    with ``resolution`` one per coarse cell part, at the population-weighted centre of its native cells, so a 5 km cell
    with a town in one corner stands where the town is."""
    import numpy as np
    import pandas as pd

    native = cells(populated=True, root=root).select(["municipality7", "x", "y", "size_m", "population"]).to_pandas()
    native["cx"] = native["x"] + native["size_m"] / 2
    native["cy"] = native["y"] + native["size_m"] / 2
    if resolution is not None:
        if resolution not in RESOLUTIONS:
            raise ValueError(f"resolution is one of {RESOLUTIONS} metres")
        native["gx"], native["gy"] = native["x"] // resolution, native["y"] // resolution
        native["wx"], native["wy"] = native["cx"] * native["population"], native["cy"] * native["population"]
        grouped = native.groupby(["municipality7", "gx", "gy"], as_index=False)[["population", "wx", "wy"]].sum()
        native = pd.DataFrame({"municipality7": grouped["municipality7"], "cx": grouped["wx"] / grouped["population"],
                               "cy": grouped["wy"] / grouped["population"], "population": grouped["population"]})
    from pyproj import Transformer

    lon, lat = Transformer.from_crs(ALBERS, "EPSG:4674", always_xy=True).transform(native["cx"].to_numpy(), native["cy"].to_numpy())
    return pd.DataFrame({"municipality7": native["municipality7"].to_numpy(), "x": native["cx"].to_numpy(),
                         "y": native["cy"].to_numpy(), "lon": np.asarray(lon), "lat": np.asarray(lat),
                         "population": native["population"].to_numpy()})


def geometry(table: Any, crs: str = "EPSG:4674") -> Any:
    """A table of `cells` as a GeoDataFrame of squares (built from ``x``, ``y`` and ``size_m`` in the grade's projection,
    then reprojected to ``crs``; ``ALBERS`` keeps IBGE's)."""
    import geopandas as gpd
    import shapely

    frame = table.to_pandas()
    x, y, s = frame["x"].to_numpy(), frame["y"].to_numpy(), frame["size_m"].to_numpy()
    out = gpd.GeoDataFrame(frame, geometry=shapely.box(x, y, x + s, y + s), crs=ALBERS)
    return out if crs == ALBERS else out.to_crs(crs)


def cell_lonlat(x: Any, y: Any, size_m: Any) -> tuple[Any, Any]:
    """The centre of each cell (arrays of its south-west corner and size, Albers metres) in longitude and latitude
    (SIRGAS 2000)."""
    import numpy as np
    from pyproj import Transformer

    half = np.asarray(size_m, dtype=float) / 2
    to = Transformer.from_crs(ALBERS, "EPSG:4674", always_xy=True)
    return to.transform(np.asarray(x, dtype=float) + half, np.asarray(y, dtype=float) + half)


def grid_weights(lon: Any, lat: Any, *, root: str | Path | None = None) -> Any:
    """Each municipality's weights over the cells of a regular longitude-latitude grid, from the grade: a pyarrow table
    of ``municipality7``, ``i`` (index into ``lat``), ``j`` (into ``lon``), ``population`` and ``area_km2``.

    ``lon`` and ``lat`` are the grid's cell centres, evenly spaced (either order). Every grade row (a 200 m or 1 km cell's
    part in a municipality) falls in the grid cell that holds its centre and carries its people and area there, so a
    population-weighted mean over the grid is Σ population × value / Σ population, and an area-weighted one the same
    with ``area_km2``, at the grade's resolution (a 1 km cell is not split across two grid cells: its centre decides).
    Grade rows whose centre is outside the grid are dropped and counted in the table's metadata (``outside``)."""
    import duckdb
    import numpy as np
    import pyarrow as pa

    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    steps = [np.diff(lon), np.diff(lat)]
    if any(len(s) == 0 or not np.allclose(s, s[0], rtol=1e-6, atol=1e-9) for s in steps):
        raise ValueError("lon and lat must be evenly spaced cell centres")
    grade = cells(root=root)
    gx, gy = cell_lonlat(grade.column("x").to_numpy(), grade.column("y").to_numpy(), grade.column("size_m").to_numpy())
    j = np.floor((gx - (lon[0] - steps[0][0] / 2)) / steps[0][0]).astype(np.int64)
    i = np.floor((gy - (lat[0] - steps[1][0] / 2)) / steps[1][0]).astype(np.int64)
    inside = (j >= 0) & (j < len(lon)) & (i >= 0) & (i < len(lat)) & grade.column("municipality7").is_valid().to_numpy(
        zero_copy_only=False)
    table = pa.table({"municipality7": grade.column("municipality7").filter(pa.array(inside)),
                      "i": pa.array(i[inside]), "j": pa.array(j[inside]),
                      "population": grade.column("population").filter(pa.array(inside)),
                      "area_km2": grade.column("area_km2").filter(pa.array(inside))})
    con = duckdb.connect()
    con.register("t", table)
    out = con.execute("""SELECT municipality7, i, j, sum(population) AS population, sum(area_km2) AS area_km2
                         FROM t GROUP BY ALL ORDER BY municipality7, i, j""").to_arrow_table()
    return out.replace_schema_metadata({"outside": str(int((~inside).sum()))})


#: The public name (`pegasus_data.grade_cells`)
grade_cells = cells
