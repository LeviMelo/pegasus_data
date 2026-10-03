"""pegasus_data: Brazil's DATASUS public health data, with its meaning attached.

One door for data, and one per question about it (ADR-0073):

    from pegasus_data import query, info, explore, search

    table = query("SIH.RD", period=2023, geography="AL")   # labelled Arrow table
    df = table.to_pandas()
    info("SIH.RD")                 # what this dataset is
    explore("SIH.RD")              # what the server has for it, offline
    search("raça")                 # which columns and codes mean what

``query`` chooses the source (a lake you built, or the FTP server) and keeps
every raw code beside its label. The names are resolved lazily, so ``import
pegasus_data`` does not pay for pyarrow and duckdb when the caller wanted only
:class:`Settings`.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from .config import Settings, load_settings

try:
    # The installed distribution metadata is the release authority. Keeping a
    # second literal here made it possible for the wheel filename, PyPI and the
    # runtime API to report different versions after an otherwise valid build.
    __version__ = version("pegasus-data")
except PackageNotFoundError:  # pragma: no cover - direct, uninstalled source checkout
    __version__ = "0+unknown"

#: Public name -> the module it lives in. Kept as data so ``__all__``, the lazy
#: loader and ``dir()`` cannot disagree about what the package exports.
_EXPORTS: dict[str, str] = {
    "describe": ".api",
    "load_population": ".api",
    "load_reference": ".api",
    "FieldDescription": ".api",
    "MissingColumnError": ".api",
    "LabelUnavailable": ".api",
    "RenderReport": ".api",
    "explore": "._explore",
    "info": "._info",
    "Info": "._info",
    "Ontology": ".ontology",
    "Exploration": "._explore",
    "translate": "._translate",
    "TranslationImpossible": "._translate",
    "availability": "._availability",
    "field_available": "._availability",
    "field_coverage": "._availability",
    "Availability": "._availability",
    "FieldWindow": "._availability",
    "gaps": "._unknowns",
    "questions": "._unknowns",
    "Gaps": "._unknowns",
    "OpenQuestions": "._unknowns",
    "DataDictionary": "._dictionary",
    "aggregate": "._aggregate",
    "build_aggregate": "._aggregate",
    "AggregateSpec": "._aggregate",
    "AggregateReport": "._aggregate",
    "memberships": ".geography",
    "MembershipSet": ".geography",
    "Membership": ".geography",
    "compendium": "._compendium",
    "CompendiumReport": "._compendium",
    "search": "._search",
    "resource_manager": "._resources",
    "ResourceManager": "._resources",
    "ResourceStatus": "._resources",
    "query": "._query_engine",
    "plan": "._query_engine",
    "QuerySpec": "._query_engine",
    "QueryPlan": "._query_engine",
    "QueryReport": "._query_engine",
    "Period": "._query_engine",
    "Geography": "._query_engine",
    "TimeResolutionWarning": "._query_engine",
    "StructuralSchemaWarning": "._query_engine",
    "PartialSourceWarning": "._query_engine",
    "SemanticFallbackWarning": "._query_engine",
    "CrosswalkAmbiguityWarning": "._query_engine",
    "enrichment": ".crosswalk",
    "EnrichmentRequest": ".crosswalk",
    "DatasetUnknown": ".retrieve",
    "NothingPublished": ".retrieve",
    "PublishedEmpty": ".retrieve",
    "DownloadBudgetExceeded": ".retrieve",
    "FilterHasNoAxis": ".retrieve",
    "link": ".linkage.engine",
    "LinkResult": ".linkage.engine",
    "LinkNotViable": ".linkage.engine",
    "role_table": ".linkage.roles",
    "discover_links": ".linkage.discover",
    "build_entities": ".linkage.entities",
    "person_pairs": ".linkage.entities",
    "link_draws": ".linkage.uncertainty",
}

__all__ = ["Settings", "load_settings", "__version__", *sorted(_EXPORTS)]

if TYPE_CHECKING:  # pragma: no cover - for type checkers and editors only
    # Re-exported through __getattr__ at runtime; `__all__` is built from
    # _EXPORTS, which a linter cannot follow.
    # ruff: noqa: F401
    from ._aggregate import (
        AggregateReport,
        AggregateSpec,
        aggregate,
        build_aggregate,
    )
    from ._compendium import CompendiumReport, compendium
    from ._dictionary import DataDictionary
    from ._explore import Exploration, explore
    from ._info import Info, info
    from ._query_engine import (
        CrosswalkAmbiguityWarning,
        Geography,
        PartialSourceWarning,
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
    from ._resources import ResourceManager, ResourceStatus, resource_manager
    from ._translate import TranslationImpossible, translate
    from .api import (
        FieldDescription,
        LabelUnavailable,
        MissingColumnError,
        RenderReport,
        describe,
        load_population,
        load_reference,
    )
    from .crosswalk import EnrichmentRequest, enrichment
    from .geography import Membership, MembershipSet, memberships
    from .ontology import Ontology
    from .retrieve import (
        DatasetUnknown,
        DownloadBudgetExceeded,
        FilterHasNoAxis,
        NothingPublished,
        PublishedEmpty,
    )


def __getattr__(name: str) -> Any:
    """Resolve an export on first use, then cache it in this module's globals.

    The implementation modules are PRIVATE — ``_explore``, ``_translate``,
    ``_info`` — and that is not a style choice. A module named ``explore.py``
    exporting a function named ``explore`` collide as attributes of this
    package: importing the submodule binds it over the function, after which
    ``from pegasus_data import explore`` hands back a module and calling it
    raises ``'module' object is not callable``. Renaming the module removes the
    ambiguity instead of arbitrating it, and keeps ``import
    pegasus_data._explore`` working for anyone who wants the module itself.
    """
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
