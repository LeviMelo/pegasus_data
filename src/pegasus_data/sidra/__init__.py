"""The general SIDRA interface: IBGE's aggregates as a registry, a request planner and a long fact store.

``Sidra`` (session.py) is the door; `client` is the only code that talks to the server (ADR-0141).
"""

from __future__ import annotations

from .planner import ALL, Chunk, PlanError, Selection
from .session import Sidra

__all__ = ["ALL", "Chunk", "PlanError", "Selection", "Sidra"]
