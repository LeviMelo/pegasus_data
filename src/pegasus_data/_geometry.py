"""Geometry repair shared by the readers of the municipal mesh (`proximity`, `sources.ibge_grade`)."""

from __future__ import annotations

from typing import Any


def polygonal(geometry: Any) -> Any:
    """The (multi)polygon inside a repaired geometry; collections lose their lines and points."""
    import shapely

    if geometry is None or geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    parts = [g for g in shapely.get_parts(geometry) if g.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else None
