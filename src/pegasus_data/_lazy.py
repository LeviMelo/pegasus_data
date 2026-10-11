"""A module imported on its first use, for heavy imports a command may never need."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any


class LazyModule:
    """``pyarrow.dataset`` initialises pandas when imported (0.6 s); at module level in the lake and the API it made
    every command start pay it, `--help` included (2026-10-11). Imported on the first attribute read instead."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._module: ModuleType | None = None

    def __getattr__(self, attr: str) -> Any:
        if self._module is None:
            self._module = importlib.import_module(self._name)
        return getattr(self._module, attr)
