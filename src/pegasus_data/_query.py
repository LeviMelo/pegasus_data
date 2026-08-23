"""Compatibility facade for the intent-driven query API.

Implementation lives under :mod:`pegasus_data._query_engine`; the explicit private
exports below preserve existing diagnostics and regression imports.
"""

from ._query_engine.core import (
    Adaptation,
    CrosswalkAmbiguityWarning,
    DimensionRequest,
    Geography,
    Period,
    QueryPlan,
    QueryReport,
    QuerySpec,
    SemanticFallbackWarning,
    StructuralSchemaWarning,
    TimeResolutionWarning,
    _apply_dimensions,
    _filter_source_period,
    _period,
    plan,
    query,
)  # compatibility re-exports are this module's purpose

__all__ = [
    "Adaptation", "CrosswalkAmbiguityWarning", "DimensionRequest", "Geography",
    "Period", "QueryPlan", "QueryReport", "QuerySpec", "SemanticFallbackWarning",
    "StructuralSchemaWarning", "TimeResolutionWarning",
    "_apply_dimensions", "_filter_source_period", "_period", "plan", "query",
]
