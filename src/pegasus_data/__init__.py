"""pegasus_data — a queryable, self-describing data lake over DATASUS.

Three ways in, in order of how much you already have:

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

from typing import TYPE_CHECKING, Any

from .config import Settings, load_settings

__version__ = "0.1.0"

#: Public name -> the module it lives in. Kept as data so ``__all__``, the lazy
#: loader and ``dir()`` cannot disagree about what the package exports.
_EXPORTS: dict[str, str] = {
    "Catalog": ".api",
    "describe": ".api",
    "load": ".api",
    "load_population": ".api",
    "load_reference": ".api",
    "open_lake": ".api",
    "export": ".api",
    "FieldDescription": ".api",
    "MissingColumnError": ".api",
    "LabelUnavailable": ".api",
    "RenderReport": ".api",
    "PROFILES": ".api",
    "explore": ".explore",
    "info": ".info",
    "Info": ".info",
    "Ontology": ".ontology",
    "Exploration": ".explore",
    "translate": ".translate",
    "TranslationImpossible": ".translate",
    "search": ".docsgen",
    "fetch": ".retrieve",
    "FetchReport": ".retrieve",
    "DatasetUnknown": ".retrieve",
    "NothingPublished": ".retrieve",
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
    from .info import Info, info
    from .ontology import Ontology
    from .api import (
        PROFILES,
        Catalog,
        FieldDescription,
        LabelUnavailable,
        MissingColumnError,
        RenderReport,
        describe,
        export,
        load,
        load_population,
        load_reference,
        open_lake,
    )
    from .bundle import BundleError, pack, read_manifest, unpack
    from .explore import Exploration, explore
    from .retrieve import DatasetUnknown, FetchReport, NothingPublished, fetch
    from .translate import TranslationImpossible, translate


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(module_name, __name__), name)


def __dir__() -> list[str]:
    return sorted(__all__)
