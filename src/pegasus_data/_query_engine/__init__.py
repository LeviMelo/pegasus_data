"""``query()`` and ``plan()``: source intent before source mechanics.

``model`` holds the request, plan and report types; ``planner`` turns a request
into a retrieval plan (lake, fetch or a year-level hybrid); ``executor`` runs
it; ``filters`` and ``semantics`` are its period filter and its dimension and
enrichment steps; ``capabilities`` says what each dataset can be asked.
"""

from .executor import query
from .model import (
    Adaptation,
    CrosswalkAmbiguityWarning,
    DimensionRequest,
    Geography,
    PartialSourceWarning,
    Period,
    QueryPlan,
    QueryReport,
    QuerySpec,
    SemanticFallbackWarning,
    StructuralSchemaWarning,
    TimeResolutionWarning,
)
from .planner import plan

__all__ = [
    "Adaptation", "CrosswalkAmbiguityWarning", "DimensionRequest", "Geography",
    "Period", "QueryPlan", "QueryReport", "QuerySpec", "SemanticFallbackWarning",
    "StructuralSchemaWarning", "TimeResolutionWarning", "PartialSourceWarning",
    "plan", "query",
]
