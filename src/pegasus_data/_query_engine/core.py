"""Compatibility exports for the split query engine."""

from .executor import _final_projection, query
from .filters import (
    _competence_value,
    _filter_geography,
    _filter_period,
    _with_competence,
    _with_row_competence,
)
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
    UnresolvedTimeWarning,
    _period,
)
from .planner import plan
from .semantics import _apply_dimensions

__all__ = [
    "Adaptation", "CrosswalkAmbiguityWarning", "DimensionRequest", "Geography",
    "Period", "QueryPlan", "QueryReport", "QuerySpec", "SemanticFallbackWarning",
    "StructuralSchemaWarning", "TimeResolutionWarning", "UnresolvedTimeWarning",
    "_apply_dimensions", "_competence_value", "_filter_geography", "_filter_period",
    "_final_projection", "_period", "_with_competence", "_with_row_competence",
    "plan", "query",
]
