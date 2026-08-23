"""`describe()` answers "what does this column mean". It could not.

Two defects met in one place and made the whole curation layer invisible.

`describe()` read `official_name` from the ledger, then `field_documentation`,
then `def_variables`, and never consulted `variable_docs` — so 4,534 curated
descriptions, the layer §9 exists to provide and that ARCHITECTURE §14 lists as
backing this very function, reached no caller through it. `FieldDescription`
did not even carry a `description` field for one to go in.

And `_resolve_family` filtered `families.system = ?` with the caller's spelling
while the table holds the CRAWLED name, so `describe("SIH", "RD")` raised
DatasetUnknown where `describe("SIHSUS", "RD")` worked — against §14.5's
promise that "SIH and SIHSUS are the same node" and against `fetch("SIH-RD")`,
which resolved through the ontology and worked all along.

Together they are why a column could be carefully described and still answer a
user with a null name and no prose.
"""

from __future__ import annotations

import pytest

from pegasus_data.api import _system_spellings
from pegasus_data.semantics.curation import system_spellings


class TestASystemAnswersToEveryNameItHas:
    def test_the_institutional_name_reaches_the_crawled_one(self) -> None:
        assert "SIHSUS" in _system_spellings("SIH")
        assert "SIH" in _system_spellings("SIHSUS")

    def test_it_works_for_the_other_renamed_system(self) -> None:
        assert "SIASUS" in _system_spellings("SIA")
        assert "SIA" in _system_spellings("SIASUS")

    def test_a_system_with_one_name_is_unchanged(self) -> None:
        assert _system_spellings("CNES") == ["CNES"]

    def test_an_unknown_name_is_returned_as_asked(self) -> None:
        """A name the declaration does not know must not become empty — the
        caller gets the plain match rather than silently nothing."""
        assert _system_spellings("NOSUCHSYSTEM") == ["NOSUCHSYSTEM"]

    def test_case_does_not_matter(self) -> None:
        assert _system_spellings("sih") == _system_spellings("SIH")

    def test_the_curation_loader_agrees(self) -> None:
        """Both resolvers must expand the same way, or the family is found and
        its docs are not — which is the state that produced a null name."""
        assert set(system_spellings("SIH")) == set(_system_spellings("SIH"))


class TestCuratedDocsReachTheLoader:
    def test_docs_filed_under_the_crawled_name_are_found_by_the_declared_one(
        self, settings
    ) -> None:
        from pegasus_data.catalog.store import Catalog
        from pegasus_data.semantics.curation import load_variable_docs

        store = Catalog(settings.catalog_path)
        try:
            store.execute(
                "INSERT INTO variable_docs (system, field_name, official_name,"
                " translated_name, description, code_system, source, asserted_by)"
                " VALUES ('SIHSUS','ZZ_TEST','Campo de teste','Test field',"
                "'What it means.','none','manual','tests')"
            )
            asked_declared = load_variable_docs(store, "SIH")
            asked_crawled = load_variable_docs(store, "SIHSUS")
        finally:
            store.close()

        assert "ZZ_TEST" in asked_crawled
        assert "ZZ_TEST" in asked_declared, (
            "a doc filed under SIHSUS was invisible to a caller who said SIH, "
            "which is the spelling the public API documents"
        )
        assert asked_declared["ZZ_TEST"].description == "What it means."

    def test_an_unknown_system_returns_nothing_rather_than_everything(
        self, settings
    ) -> None:
        """The expansion must not degrade into an unfiltered query — that would
        hand SINASC's meaning to a SIH column."""
        from pegasus_data.catalog.store import Catalog
        from pegasus_data.semantics.curation import load_variable_docs

        store = Catalog(settings.catalog_path)
        try:
            store.execute(
                "INSERT INTO variable_docs (system, field_name, description, source,"
                " asserted_by) VALUES ('SIHSUS','ZZ_TEST','x','manual','tests')"
            )
            assert load_variable_docs(store, "NOSUCHSYSTEM") == {}
        finally:
            store.close()


class TestTheDescriptionTravelsWithItsEvidence:
    def test_field_description_carries_the_prose_and_the_rung(self) -> None:
        """An inferred description read as a documented one is the failure the
        rungs exist to prevent, so the rung cannot stay behind in the YAML."""
        from pegasus_data.api import FieldDescription

        d = FieldDescription(
            system="SIH",
            series="RD",
            family_id="f",
            field_name="ANO_CMPT",
            official_name="Ano de processamento da AIH",
            semantic_type=None,
            semantic_confidence=None,
            semantic_evidence={},
            aggregation="non_summable",
            unit=None,
            dictionary_coverage=0.0,
            distinct_observed=0,
            distinct_decoded=0,
            sentinel_values=[],
            translated_name="Processing year",
            description="Four-digit year of the competência.",
            code_system="none",
            description_source="layout_doc",
            description_source_ref="[IT-SIHSUS] ...",
        )
        got = d.as_dict()
        assert got["translated_name"] == "Processing year"
        assert got["description"] == "Four-digit year of the competência."
        assert got["code_system"] == "none"
        assert got["description_source"] == "layout_doc"
        assert got["description_source_ref"] == "[IT-SIHSUS] ..."

    @pytest.mark.parametrize(
        "key",
        ["translated_name", "description", "code_system", "description_source"],
    )
    def test_the_keys_are_always_present(self, key) -> None:
        """Absent from as_dict() is indistinguishable from undescribed, and a
        caller branching on the key would read one as the other."""
        from pegasus_data.api import FieldDescription

        d = FieldDescription(
            system="X", series=None, family_id="f", field_name="F",
            official_name=None, semantic_type=None, semantic_confidence=None,
            semantic_evidence={}, aggregation="non_summable", unit=None,
            dictionary_coverage=0.0, distinct_observed=0, distinct_decoded=0,
            sentinel_values=[],
        )
        assert key in d.as_dict()
        assert d.as_dict()[key] is None
