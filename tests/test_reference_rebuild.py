"""HI-13's scoped rebuild, which had no test at all.

Materialising EVERY code table for every system is a build-stage side effect,
and it used to fire from inside an ordinary interactive fetch: a request for
SIH sex and age rebuilt the codelists of all twenty systems first. Scoping it
fixed that — and introduced the branch that must never swap the whole tree,
because doing so would silently delete every table outside the scope.
"""

from __future__ import annotations

from pegasus_data.persist.reference import write_reference_tables
from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries


def _seed(catalog):
    """Three systems that disagree about SEXO — the real reason tables are scoped."""
    persist_entries(
        catalog,
        [
            DictionaryEntry(system="SIHSUS", value_raw="1", value_label="Masculino",
                            source="cnv", source_ref="a:1", confidence=0.95, value_group="SEXO"),
            DictionaryEntry(system="SIHSUS", value_raw="3", value_label="Feminino",
                            source="cnv", source_ref="a:2", confidence=0.95, value_group="SEXO"),
            DictionaryEntry(system="SINASC", value_raw="1", value_label="Masculino",
                            source="cnv", source_ref="b:1", confidence=0.95, value_group="SEXO"),
            DictionaryEntry(system="SINASC", value_raw="2", value_label="Feminino",
                            source="cnv", source_ref="b:2", confidence=0.95, value_group="SEXO"),
            DictionaryEntry(system="SIM", value_raw="A419", value_label="Septicemia",
                            source="cnv", source_ref="c:1", confidence=0.95, value_group="CID10"),
            DictionaryEntry(system="SIM", value_raw="1", value_label="Masculino",
                            source="cnv", source_ref="c:2", confidence=0.95, value_group="SEXO"),
        ],
    )


def _tables(root):
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


class TestScopedRebuild:
    def test_a_full_rebuild_writes_every_system(self, catalog, settings):
        _seed(catalog)
        written = write_reference_tables(catalog, settings.lake_dir)
        assert written, "the fixture seeds three systems' codelists"
        assert {t.system for t in written} >= {"SIHSUS", "SINASC", "SIM"}

    def test_a_scoped_rebuild_does_not_delete_the_systems_it_skipped(
        self, catalog, settings
    ):
        """Swapping the tree here would drop every codelist outside the scope,
        and the trigger is an ordinary labelled fetch."""
        _seed(catalog)
        write_reference_tables(catalog, settings.lake_dir)
        root = settings.lake_dir / "reference"
        before = _tables(root)
        assert before, "something was written to preserve"

        write_reference_tables(catalog, settings.lake_dir, systems=["SIHSUS"])
        assert _tables(root) == before, (
            "a rebuild scoped to SIHSUS deleted codelists belonging to other systems"
        )

    def test_a_scoped_rebuild_still_refreshes_what_it_was_asked_for(
        self, catalog, settings
    ):
        _seed(catalog)
        write_reference_tables(catalog, settings.lake_dir)
        written = write_reference_tables(catalog, settings.lake_dir, systems=["SIHSUS"])
        assert written, "the scope was rebuilt, not skipped"
        assert {t.system for t in written} == {"SIHSUS"}

    def test_no_staging_or_backup_directories_survive(self, catalog, settings):
        _seed(catalog)
        write_reference_tables(catalog, settings.lake_dir)
        write_reference_tables(catalog, settings.lake_dir, systems=["SIHSUS"])
        leftovers = [
            p.name
            for p in settings.lake_dir.iterdir()
            if "__staging__" in p.name or "__previous__" in p.name
        ]
        assert leftovers == []

    def test_each_systems_table_keeps_its_own_answer(self, catalog, settings):
        """SIHSUS codes sex as 1/3 and SINASC as 1/2. Merging them made '1' mean
        Masculino AND Feminino, and any label drawn from it a coin toss."""
        from pegasus_data.persist.reference import read_reference_table

        _seed(catalog)
        write_reference_tables(catalog, settings.lake_dir)
        sih = read_reference_table(settings.lake_dir, "SEXO", system="SIHSUS")
        codes = dict(zip(sih.column("code").to_pylist(), sih.column("label").to_pylist(), strict=True))
        assert codes.get("3") == "Feminino", "SIHSUS's own table, not the union"
        assert "2" not in codes
