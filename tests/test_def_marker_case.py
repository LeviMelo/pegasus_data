"""A `.DEF` line's marker is case-insensitive, and 881 lines said so.

TabWin writes the usage marker in either case, and the case is a display
preference — lower means the axis exists but is not offered by default — not a
different kind of statement. The parser matched only upper case and recorded
everything else as `unrecognised marker`, which silently dropped 881 of the
22,675 variable lines in the shipped tab kits.

What went with them was the bindings those lines declared. `AGRAVDROGA` is bound
to `SIM_NAO.CNV` on exactly such a line, `ELISA1` to `reagente.cnv`,
`TP_SISTEMA` to `TIPOSISTEMA.CNV` — so those columns read as having no codelist
at all, and were counted as gaps needing a source that had been on disk the
whole time.
"""

from __future__ import annotations

import pytest

from pegasus_data.semantics.def_parser import USAGE_LABELS, parse_def_bytes

UPPER = b"""; Titulo
A DADOS\\*.DBF
LSexo, CS_SEXO, 1, SEXO.CNV
"""
LOWER = b"""; Titulo
A DADOS\\*.DBF
xDrogas ilicitas, AGRAVDROGA, 1, SIM_NAO.CNV
"""


def parse(data: bytes):
    return parse_def_bytes(data, name="t.def", source_ref="t")


class TestBothCasesAreStatements:
    def test_a_lowercase_marker_yields_a_variable(self) -> None:
        got = parse(LOWER)
        assert len(got.variables) == 1, (
            f"the lowercase line was dropped: {got.warnings}"
        )
        v = got.variables[0]
        assert v.field_name == "AGRAVDROGA"
        assert v.lookup_ref == "SIM_NAO.CNV"

    def test_the_usage_is_normalised_to_upper(self) -> None:
        """Downstream compares against USAGE_LABELS and ADDITIVE_USAGE, which
        are upper case; leaving the raw case would move the bug rather than fix
        it."""
        v = parse(LOWER).variables[0]
        assert v.usage in USAGE_LABELS
        assert v.usage.isupper()

    def test_the_case_itself_is_preserved_as_a_flag(self) -> None:
        """Lower case means TabWin does not offer the axis by default. That is
        worth keeping — it just is not a reason to discard the binding."""
        assert parse(LOWER).variables[0].shown_by_default is False
        assert parse(UPPER).variables[0].shown_by_default is True

    def test_an_uppercase_line_is_unchanged(self) -> None:
        got = parse(UPPER)
        assert len(got.variables) == 1
        assert got.variables[0].field_name == "CS_SEXO"
        assert got.variables[0].usage == "L"

    def test_a_genuinely_unknown_marker_is_still_reported(self) -> None:
        """The fix must not turn the grammar into a shrug: a marker that is not
        a usage in either case is still a gap worth seeing."""
        got = parse(b"; T\nQnot a usage, FIELD, 1, X.CNV\n")
        assert not got.variables
        assert any("unrecognised marker" in w for w in got.warnings)

    @pytest.mark.parametrize("marker", ["l", "c", "s", "x", "i"])
    def test_every_usage_works_in_lower_case(self, marker) -> None:
        line = f"{marker}Rotulo, CAMPO, 1, T.CNV\n".encode()
        got = parse(b"; T\n" + line)
        assert len(got.variables) == 1, f"marker {marker!r} was dropped"
        assert got.variables[0].usage == marker.upper()


class TestTheShippedKitsBenefit:
    def test_the_recovered_lines_are_a_real_share(self) -> None:
        """Guards the size of the fix: if a refactor re-drops lower-case lines
        this ratio collapses, and the gap measurement quietly grows again."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "sources"
        if not root.is_dir():
            pytest.skip("sources/ is not vendored in this checkout")
        defs = sorted(set(list(root.rglob("*.def")) + list(root.rglob("*.DEF"))))[:40]
        if not defs:
            pytest.skip("no .DEF files vendored")
        lower = total = 0
        for d in defs:
            try:
                parsed = parse_def_bytes(d.read_bytes(), name=d.name, source_ref=str(d))
            except Exception:  # noqa: BLE001
                continue
            total += len(parsed.variables)
            lower += sum(1 for v in parsed.variables if not v.shown_by_default)
        assert total, "no variables parsed from any vendored .DEF"
        assert lower > 0, (
            "no lower-case-marker variables were parsed at all, which is what "
            "the defect looked like"
        )
