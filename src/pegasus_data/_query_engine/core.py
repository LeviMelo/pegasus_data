"""Compatibility exports for the split query engine."""

from .executor import _final_projection, query
from .filters import _filter_source_period, _with_competence
from .model import (
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
    _period,
)
from .planner import plan
from .semantics import _apply_dimensions

__all__ = [
    "Adaptation", "CrosswalkAmbiguityWarning", "DimensionRequest", "Geography",
    "Period", "QueryPlan", "QueryReport", "QuerySpec", "SemanticFallbackWarning",
    "StructuralSchemaWarning", "TimeResolutionWarning",
    "_apply_dimensions", "_filter_source_period",
    "_final_projection", "_period", "_with_competence",
    "plan", "query",
]
