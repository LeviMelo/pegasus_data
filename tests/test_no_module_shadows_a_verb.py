"""A public verb must not be shadowed by the module it lives in.

`pegasus_data.availability` was both a function and a module. Python resolves
the attribute normally before `__getattr__` runs, so once anything imported the
submodule the package attribute WAS the module and calling it raised
`'module' object is not callable`.

What made it survive review is that it is order-dependent, so it never failed
for whoever wrote the code:

    pg.field_available(...)   # fine — and imports .availability
    pg.availability(...)      # TypeError

`field_available` lives in the same module, so touching it is enough. §14.5
already prescribed the `_module.py` convention for exactly this and it had been
applied to `_explore`, `_info` and `_translate` but not to `availability` or
`compendium`.

These tests run in subprocesses because the shadowing is a property of a fresh
interpreter's import order, and pytest will already have imported half the
package by the time a normal test body runs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

#: verb -> a sibling name in the same module, whose use imports that module
SIBLINGS = {
    "availability": "field_available",
    "compendium": "CompendiumReport",
    "explore": "Exploration",
    "info": "Info",
    "translate": "TranslationImpossible",
}


def run(code: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={"PYTHONPATH": str(SRC), "PATH": ""},
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    return proc.stdout.strip()


@pytest.mark.parametrize("verb,sibling", sorted(SIBLINGS.items()))
def test_touching_a_sibling_does_not_shadow_the_verb(verb, sibling) -> None:
    got = run(
        "import pegasus_data as pg\n"
        f"_ = pg.{sibling}\n"
        f"print(type(pg.{verb}).__name__)\n"
    )
    assert got == "function", (
        f"pg.{verb} became a {got} after touching pg.{sibling}; the module is "
        f"shadowing the verb and calling it raises 'module' object is not callable"
    )


@pytest.mark.parametrize("verb", sorted(SIBLINGS))
def test_importing_the_submodule_directly_does_not_shadow_it(verb) -> None:
    """The blunter form of the same collision."""
    got = run(
        f"import pegasus_data._{verb}\n"
        "import pegasus_data as pg\n"
        f"print(type(pg.{verb}).__name__)\n"
    )
    assert got == "function", f"pg.{verb} resolved to a {got}"


def test_no_public_verb_shares_a_name_with_a_module() -> None:
    """The general rule, so a new verb cannot reintroduce this."""
    import pegasus_data as pg

    modules = {p.stem for p in (SRC / "pegasus_data").glob("*.py")}
    verbs = {n for n in pg.__all__ if n[0].islower()}
    clash = sorted(verbs & modules)
    assert not clash, (
        f"these are both a public verb and a module, so the module shadows the "
        f"verb once imported: {clash}. Rename the module with a leading "
        f"underscore, as §14.5 prescribes."
    )
