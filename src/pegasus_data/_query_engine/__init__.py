"""Internal query planning and execution package."""

from .core import (
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
    plan,
    query,
)

__all__ = [
    "Adaptation", "CrosswalkAmbiguityWarning", "DimensionRequest", "Geography",
    "Period", "QueryPlan", "QueryReport", "QuerySpec", "SemanticFallbackWarning",
    "StructuralSchemaWarning", "TimeResolutionWarning",
    "plan", "query",
]
