"""Road distance and car travel time between every pair of Brazilian municipal seats (Saldanha, 2024).

**The product** (Raphael Saldanha, *Road distances and trip duration matrix for Brazilian municipalities*, Zenodo,
doi:10.5281/zenodo.11400243, published 2024-05-31, CC-BY 4.0; code: github.com/rfsaldanha/distbrasil): the OSRM
``table`` service, ``car`` profile, over OpenStreetMap, between the municipal seats IBGE published in 2010 (5,565 points,
from {geobr}). Each unordered pair is routed once (``choose(5565, 2)`` = 15,481,830 routes) and taken as symmetric:
``dist`` in metres and ``dur`` in minutes, the fastest car route. Pairs without a road route (municipalities reached
only by boat or plane) have no value. The OSM network's date is not stated by the source.

**The layer** ``road_osrm`` (`proximity.MOBILITY_LAYERS`): both directions of each routed pair, ``weight`` the minutes,
``distance_km`` beside it, 7-digit codes. Municipalities created after 2010 (Mojuí dos Campos, Pescaria Brava, Balneário
Rincão, Paraíso das Águas, Pinto Bandeira) have no seat in the source and no row: they are counted in the report, never
given a neighbour's times. River and air travel are IBGE's ``waterway_links_2016`` and ANAC's layers.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

RECORD = 11400243
URL = f"https://zenodo.org/records/{RECORD}/files/dist_brasil.parquet?download=1"
KIND, VINTAGE, NAME = "road_osrm", 2024, "road_osrm.parquet"
COLUMNS = ["from", "to", "weight", "kind", "vintage", "distance_km"]
PUBLISHED_ROUTES = 15_481_830


def build(root: str | Path | None = None, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Download the matrix once to ``<root>/registries/road_matrix/`` and write ``registries/mobility/road_osrm.parquet``;
    return the counts and the checks against the source's own figures."""
    import pandas as pd

    from ..config import load_settings
    from ..geography import municipalities
    from ..transport import download

    log = log or (lambda _msg: None)
    registries = load_settings(root=root).registries_dir
    log("road_matrix: dist_brasil.parquet (Zenodo 11400243)")
    src = download(URL, registries / "road_matrix" / "dist_brasil.parquet")
    raw = pd.read_parquet(src)
    raw.columns = [c.lower() for c in raw.columns]
    pairs = pd.DataFrame({"a": raw["orig"].astype("int64"), "b": raw["dest"].astype("int64"),
                          "minutes": pd.to_numeric(raw["dur"], errors="coerce"),
                          "km": pd.to_numeric(raw["dist"], errors="coerce") / 1000})
    routed = pairs.minutes.notna() & pairs.km.notna()
    keep = pairs[routed & (pairs.a != pairs.b)]
    both = pd.concat([keep.rename(columns={"a": "from", "b": "to"}), keep.rename(columns={"b": "from", "a": "to"})],
                     ignore_index=True)
    out = pd.DataFrame({"from": both["from"], "to": both["to"], "weight": both.minutes.astype("float64"), "kind": KIND,
                        "vintage": VINTAGE, "distance_km": both.km.astype("float64")})[COLUMNS]
    folder = registries / "mobility"
    folder.mkdir(parents=True, exist_ok=True)
    out.sort_values(["from", "to"], kind="stable", ignore_index=True).to_parquet(folder / NAME, index=False)
    known = {int(row["code7"]) for row in municipalities().values()}
    seats = set(pairs.a) | set(pairs.b)
    report = {
        "path": str(folder / NAME), "rows": int(len(out)), "seats": len(seats),
        "routes_in_source": int(len(pairs)), "routes_published": PUBLISHED_ROUTES,
        "without_road_route": int((~routed).sum()),
        "municipalities_without_seat": sorted(known - seats),
        "seats_not_in_pack": sorted(seats - known),
        "minutes_median": float(keep.minutes.median()), "km_median": float(keep.km.median()),
    }
    log(f"road_matrix: {len(out)} rows, {report['without_road_route']} pairs without a road route")
    return report
