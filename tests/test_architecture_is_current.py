"""The architecture document is the bookkeeper, so drift in it is a defect.

This project lost track of itself twice in ways a reader could not detect. §21
read "1,572 described (34.7%)" while `docs/RESUME.md` read "4,528 (100%)", and
neither said when — so SIH-RD sat at 13% described under a heading claiming
completeness. And twelve modules, a catalog table, seven public entry points and
two source rungs existed in the code with no mention in the document that is
supposed to describe the code.

Both are the same failure: state kept by diligence rather than by a check. These
tests are the check. They do not police prose — a section can be as thin as its
author likes — only that nothing SHIPS unmentioned, which is the part a reader
cannot recover on their own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCH_PATH = ROOT / "pegasus_data_ARCHITECTURE.md"
SRC = ROOT / "src" / "pegasus_data"


@pytest.fixture(scope="module")
def arch() -> str:
    return ARCH_PATH.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end)]


class TestEveryModuleIsInTheLayout:
    """§3.1 lists the package. A module absent from it is one a reader has no
    way to learn exists short of listing the directory themselves."""

    def test_no_module_is_unlisted(self, arch) -> None:
        layout = _section(arch, "### 3.1 Package layout", "## 4. The catalog")
        modules = sorted(
            p.relative_to(SRC).as_posix()
            for p in SRC.rglob("*.py")
            if "__pycache__" not in p.parts and p.name != "__init__.py"
        )
        missing = [m for m in modules if Path(m).name not in layout]
        assert not missing, (
            f"{len(missing)} modules ship and §3.1 does not name them: {missing}"
        )

    def test_the_layout_names_no_module_that_is_gone(self, arch) -> None:
        """The inverse drift: a module deleted while the document still lists it
        sends a reader looking for something that is not there."""
        layout = _section(arch, "### 3.1 Package layout", "## 4. The catalog")
        on_disk = {p.name for p in SRC.rglob("*.py")}
        listed = set(re.findall(r"\b([a-z_][a-z0-9_]*\.py)\b", layout))
        assert not (listed - on_disk), f"§3.1 lists modules that no longer exist: {sorted(listed - on_disk)}"


class TestEveryCatalogTableIsDescribed:
    def test_no_table_is_unlisted(self, arch) -> None:
        schema = (SRC / "catalog" / "schema.sql").read_text(encoding="utf-8")
        tables = sorted(set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", schema)))
        section = _section(arch, "## 4. The catalog", "## 5. L0")
        missing = [t for t in tables if t not in section]
        assert not missing, f"§4 does not name these tables: {missing}"

    def test_the_count_matches(self, arch) -> None:
        """A stated count is a claim, and a wrong one is how a reader learns to
        distrust the rest of the table."""
        schema = (SRC / "catalog" / "schema.sql").read_text(encoding="utf-8")
        tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", schema))
        stated = re.search(r"(\d+) tables", _section(arch, "## 4. The catalog", "## 5. L0"))
        assert stated, "§4 no longer states a table count"
        assert int(stated.group(1)) == len(tables), (
            f"§4 says {stated.group(1)} tables; schema.sql defines {len(tables)}"
        )


class TestEveryPublicNameIsDocumented:
    def test_no_exported_verb_is_unmentioned(self, arch) -> None:
        init = (SRC / "__init__.py").read_text(encoding="utf-8")
        exported = set(re.findall(r'"(\w+)"', init[init.index("__all__") :]))
        section = _section(arch, "## 14. The public API", "## 15. Environment")
        missing = sorted(n for n in exported if n[0].islower() and n not in section)
        assert not missing, (
            f"these names are exported from the package and §14 does not mention "
            f"them: {missing}"
        )


class TestEverySourceRungIsInTheLadder:
    """§6.3's ladder decides which claim wins when two disagree. A rung that
    ships without appearing in it is a claim with no stated standing."""

    def test_no_binding_rung_is_missing(self, arch) -> None:
        pq = pytest.importorskip("pyarrow.parquet")
        pack = SRC / "resources" / "bindings.parquet"
        if not pack.exists():  # pragma: no cover - build without the pack
            pytest.skip("this build ships no binding pack")
        rungs = sorted(
            set(pq.read_table(pack, columns=["source"]).column("source").to_pylist())
        )
        ladder = _section(arch, "### 6.3", "### 6.4")
        missing = [r for r in rungs if r not in ladder]
        assert not missing, (
            f"bindings ship with rungs the §6.3 ladder does not rank: {missing}"
        )


class TestCountsLiveInOnePlace:
    """RESUME.md and CONFIDENCE.md carried their own state tables, disagreed
    with §21, and there was no way to tell which was current."""

    @pytest.mark.parametrize("doc", ["docs/RESUME.md", "docs/CONFIDENCE.md"])
    def test_no_second_state_table(self, doc) -> None:
        text = (ROOT / doc).read_text(encoding="utf-8")
        # a state table is a markdown table whose rows are `| label | 1,234 |`
        rows = re.findall(r"^\|[^|\n]+\|\s*\*{0,2}[\d,]{3,}\*{0,2}\s*\|", text, re.M)
        assert not rows, (
            f"{doc} has started keeping counts again ({len(rows)} rows); they belong "
            f"in ARCHITECTURE §21 so they cannot disagree: {rows[:3]}"
        )

    def test_architecture_still_states_it_owns_them(self, arch) -> None:
        assert "bookkeeper" in _section(arch, "## 21. Measured state", "### The tree"), (
            "§21 no longer claims to be the single place counts live, which is the "
            "convention the other documents defer to"
        )
