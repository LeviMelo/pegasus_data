"""A corrected meaning has to reach a catalog that already exists.

Curation was loaded when ``variable_docs`` was EMPTY, which is true exactly once
in a catalog's life. Everything the shipped YAML gained or corrected afterwards
was therefore invisible to anyone who had run the package before — the wheel
carried the right answer and the catalog kept serving the old one, with nothing
saying so.

The case that found it: 30 CNES columns were curated onto the COMPOSITE table
that encodes a whole 7x6 service/payer grid at once, rather than onto their own
single-flag table. The composite is a different code width and decodes none of
the column's values, so those columns came back as raw codes. Correcting the
YAML fixed new catalogs and would have left every existing one wrong for ever.
"""

from __future__ import annotations

import pytest
import yaml

from pegasus_data.catalog.store import Catalog
from pegasus_data.ontology import CURATION
from pegasus_data.semantics.curation import (
    curation_fingerprint,
    curation_is_current,
    load_curation,
    note_curation_loaded,
)


@pytest.fixture
def curation_copy(tmp_path):
    """A writable copy of the shipped curation."""
    import shutil

    dest = tmp_path / "curation"
    shutil.copytree(CURATION, dest)
    return dest


class TestTheFingerprint:
    def test_it_is_stable_when_nothing_changes(self, curation_copy) -> None:
        assert curation_fingerprint(curation_copy) == curation_fingerprint(curation_copy)

    def test_it_changes_when_a_meaning_changes(self, curation_copy, tmp_path) -> None:
        """Content, not mtime: the YAML ships in a wheel and its timestamps say
        when it was unpacked, not whether anyone edited it."""
        import shutil

        before = curation_fingerprint(curation_copy)
        target = next(iter(sorted(curation_copy.glob("variables/*/*.yml"))))
        target.write_text(
            target.read_text(encoding="utf-8") + "\n# a changed meaning\n", encoding="utf-8"
        )
        other = tmp_path / "curation2"
        shutil.copytree(curation_copy, other)
        assert curation_fingerprint(other) != before

    def test_the_shipped_curation_has_one(self) -> None:
        assert len(curation_fingerprint(CURATION)) == 32


class TestItReloadsOnlyWhenItShould:
    def test_a_fresh_catalog_is_not_current(self, tmp_path) -> None:
        store = Catalog(tmp_path / "c.sqlite")
        try:
            assert curation_is_current(store, CURATION) is False
        finally:
            store.close()

    def test_after_loading_it_is_current(self, tmp_path) -> None:
        store = Catalog(tmp_path / "c.sqlite")
        try:
            load_curation(store, CURATION)
            note_curation_loaded(store, CURATION)
            assert curation_is_current(store, CURATION) is True
        finally:
            store.close()

    def test_a_changed_curation_is_no_longer_current(self, tmp_path, curation_copy) -> None:
        """The whole point: an existing catalog notices new meanings."""
        store = Catalog(tmp_path / "c.sqlite")
        try:
            load_curation(store, curation_copy)
            note_curation_loaded(store, curation_copy)
            assert curation_is_current(store, curation_copy) is True

            target = sorted(curation_copy.glob("variables/*/*.yml"))[0]
            target.write_text(
                target.read_text(encoding="utf-8") + "\n# corrected\n", encoding="utf-8"
            )
            curation_fingerprint.cache_clear() if hasattr(
                curation_fingerprint, "cache_clear"
            ) else None
            from pegasus_data.semantics import curation as _c

            _c._fingerprint.cache_clear()
            assert curation_is_current(store, curation_copy) is False
        finally:
            store.close()

    def test_noting_twice_keeps_one_row(self, tmp_path) -> None:
        store = Catalog(tmp_path / "c.sqlite")
        try:
            note_curation_loaded(store, CURATION)
            note_curation_loaded(store, CURATION)
            rows = store.query("SELECT COUNT(*) AS n FROM curation_state")
            assert int(rows[0]["n"]) == 1, "the state row must be a singleton"
        finally:
            store.close()


class TestTheCorrectedBindingsStayCorrected:
    """A guard on the DATA, so the 30 corrections cannot be silently reverted.

    Each of these columns is a single yes/no flag. Binding it to the composite
    grid table is not a near-miss — the composite is a different width and
    decodes none of the flag's values (§6.2 matches widths exactly and never
    pads), so the column comes back raw.
    """

    WRONG = {
        "AP01CV01": "ATPRES01",
        "AP01CV03": "ATPRES1X",
        "AP07CV01": "ATPRES07",
        "GESPRG2E": "GESPROG2",
        "GESPRG6E": "GESPROG6",
        "SERAP01P": "SRV_AP01",
        "SERAP11P": "SRV_AP11",
    }

    @pytest.fixture(scope="class")
    def cnes_variables(self):
        merged: dict[str, dict] = {}
        for path in sorted((CURATION / "variables" / "cnes").glob("*.yml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for name, body in (doc.get("variables") or {}).items():
                if isinstance(body, dict):
                    merged.setdefault(str(name).upper(), body)
        return merged

    @pytest.mark.parametrize("column", sorted(WRONG))
    def test_the_column_is_bound_to_its_own_table(self, cnes_variables, column) -> None:
        body = cnes_variables.get(column)
        assert body is not None, f"{column} is no longer curated at all"
        named = [str(c).upper() for c in (body.get("codelists") or [])]
        if body.get("codelist"):
            named.insert(0, str(body["codelist"]).upper())
        assert named == [column], (
            f"{column} is bound to {named}; it is a single yes/no flag and must "
            f"use its own table, not the composite grid {self.WRONG[column]!r}"
        )
