"""pegasus_data — a queryable, self-describing data lake over DATASUS.

The intent-driven front door chooses the source mechanics for you:

    from pegasus_data import query
    df = query("SIH-RD", period=2023, geography="AL")

The lower-level source-specific services remain available:

    from pegasus_data import fetch
    df = fetch("SIH-RD", uf="AL", years=2023)      # nothing local; go and get it

    from pegasus_data import load
    df = load("SIHSUS", "RD", uf="AL", years=2023)  # read a lake you built

    from pegasus_data import describe
    describe("SIHSUS", "RD", field="DIAG_PRINC")    # what does this variable mean

The names are resolved lazily. ``import pegasus_data`` should not pay for
pyarrow and duckdb when all the caller wanted was :class:`Settings`, and the CLI
imports this package on every invocation.
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
    "Catalog": ".api",
    "describe": ".api",
    "load": ".api",
    "scan": ".api",
    "LakeScan": ".api",
    "load_population": ".api",
    "load_reference": ".api",
    "open_lake": ".api",
    "export": ".api",
    "FieldDescription": ".api",
    "MissingColumnError": ".api",
    "LabelUnavailable": ".api",
    "RenderReport": ".api",
    "PROFILES": ".api",
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
    "memberships": ".geography",
    "MembershipSet": ".geography",
    "Membership": ".geography",
    "compendium": "._compendium",
    "CompendiumReport": "._compendium",
    "search": ".docsgen",
    "fetch": ".retrieve",
    "FetchReport": ".retrieve",
    "resource_manager": "._resources",
    "ResourceManager": "._resources",
    "ResourceStatus": "._resources",
    "query": "._query",
    "plan": "._query",
    "QuerySpec": "._query",
    "QueryPlan": "._query",
    "QueryReport": "._query",
    "Period": "._query",
    "Geography": "._query",
    "TimeResolutionWarning": "._query",
    "StructuralSchemaWarning": "._query",
    "SemanticFallbackWarning": "._query",
    "CrosswalkAmbiguityWarning": "._query",
    "enrichment": ".crosswalk",
    "EnrichmentRequest": ".crosswalk",
    "DatasetUnknown": ".retrieve",
    "NothingPublished": ".retrieve",
    "FilterHasNoAxis": ".retrieve",
    "pack": ".bundle",
    "unpack": ".bundle",
    "read_manifest": ".bundle",
    "BundleError": ".bundle",
}

__all__ = ["Settings", "load_settings", "__version__", *sorted(_EXPORTS)]

if TYPE_CHECKING:  # pragma: no cover - for type checkers and editors only
    # Re-exported through __getattr__ at runtime; `__all__` is built from
    # _EXPORTS, which a linter cannot follow.
    # ruff: noqa: F401
    from ._compendium import CompendiumReport, compendium
    from ._dictionary import DataDictionary
    from ._explore import Exploration, explore
    from ._info import Info, info
    from ._query import (
        CrosswalkAmbiguityWarning,
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
    from ._resources import ResourceManager, ResourceStatus, resource_manager
    from ._translate import TranslationImpossible, translate
    from .api import (
        PROFILES,
        Catalog,
        FieldDescription,
        LabelUnavailable,
        LakeScan,
        MissingColumnError,
        RenderReport,
        describe,
        export,
        load,
        load_population,
        load_reference,
        open_lake,
        scan,
    )
    from .bundle import BundleError, pack, read_manifest, unpack
    from .crosswalk import EnrichmentRequest, enrichment
    from .geography import Membership, MembershipSet, memberships
    from .ontology import Ontology
    from .retrieve import (
        DatasetUnknown,
        FetchReport,
        FilterHasNoAxis,
        NothingPublished,
        fetch,
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
