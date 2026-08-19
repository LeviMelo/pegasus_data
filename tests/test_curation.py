"""The curated variable dictionary: the door for human judgement (§4).

The point of these tests is that the door is *load-bearing*. A curated entry has
to outrank extracted sources, survive a reload, disappear when deleted from the
file, and refuse to pretend an inference is documentation.
"""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.semantics.curation import (
    CurationError,
    coverage_by_rung,
    load_curation,
    load_variable_docs,
)

SIH = """
system: SIHSUS
asserted_by: tester
variables:
  DIAG_PRINC:
    official_name: Codigo do diagnostico principal
    description: CID-10 code, stored without the dot.
    code_system: external
    codelist: CID10
    source: layout_doc
    source_ref: IT_SIHSUS_1603.pdf
  IDADE:
    official_name: Idade
    code_system: none
    depends_on: [COD_IDADE]
    derived:
      - name: IDADE_anos
        from: [IDADE, COD_IDADE]
        rule: convert to years using COD_IDADE as the unit
    source: layout_doc
  COD_IDADE:
    official_name: Unidade de medida da idade
    code_system: internal
    modifies: IDADE
    source: layout_doc
"""


def _write(tmp_path, name: str, body: str):
    directory = tmp_path / "curation" / "variables"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(body, encoding="utf-8")
    return tmp_path / "curation"


class TestLoading:
    def test_it_loads_variables_and_their_relationships(self, catalog: Catalog, tmp_path):
        root = _write(tmp_path, "sihsus_rd.yml", SIH)
        result = load_curation(catalog, root)
        assert result["variables"] == 3
        docs = load_variable_docs(catalog, "SIHSUS")
        assert docs["IDADE"].depends_on == ["COD_IDADE"]
        assert docs["COD_IDADE"].modifies == "IDADE"
        assert docs["IDADE"].derived[0]["name"] == "IDADE_anos"

    def test_a_curated_codelist_binds_at_full_authority(self, catalog: Catalog, tmp_path):
        """SOURCE_AUTHORITY['manual'] = 0 was unreachable before this."""
        load_curation(catalog, _write(tmp_path, "sihsus_rd.yml", SIH))
        row = catalog.query("SELECT * FROM field_codelists WHERE field_name = 'DIAG_PRINC'")[0]
        assert row["source"] == "manual"
        assert row["confidence"] == 1.0
        assert row["codelist"] == "CID10"

    def test_reloading_is_idempotent(self, catalog: Catalog, tmp_path):
        root = _write(tmp_path, "sihsus_rd.yml", SIH)
        load_curation(catalog, root)
        load_curation(catalog, root)
        assert catalog.count("variable_docs") == 3
        assert catalog.count("field_codelists", "source = 'manual'") == 1

    def test_deleting_an_entry_removes_it(self, catalog: Catalog, tmp_path):
        """The file is the source of truth, not a set of suggestions."""
        root = _write(tmp_path, "sihsus_rd.yml", SIH)
        load_curation(catalog, root)
        trimmed = SIH.split("  IDADE:")[0]
        _write(tmp_path, "sihsus_rd.yml", trimmed)
        load_curation(catalog, root)
        assert set(load_variable_docs(catalog)) == {"DIAG_PRINC"}

    def test_an_absent_directory_is_not_an_error(self, catalog: Catalog, tmp_path):
        result = load_curation(catalog, tmp_path / "nope")
        assert result["variables"] == 0

    def test_prefix_overrides_reach_the_learned_map(self, catalog: Catalog, tmp_path):
        root = tmp_path / "curation"
        root.mkdir()
        (root / "systems.yml").write_text("prefix_systems:\n  CM: SISCAN\n", encoding="utf-8")
        load_curation(catalog, root)
        row = catalog.query("SELECT * FROM prefix_systems WHERE series_prefix = 'CM'")[0]
        assert row["system"] == "SISCAN"
        assert row["agreement"] == 1.0

    def test_dataset_prose_is_loaded(self, catalog: Catalog, tmp_path):
        root = tmp_path / "curation"
        root.mkdir()
        (root / "datasets.yml").write_text(
            "datasets:\n  SIHSUS_RD:\n    what_one_row_is: one billing episode (AIH)\n"
            "    gotchas:\n      - one patient readmitted three times is three rows\n",
            encoding="utf-8",
        )
        load_curation(catalog, root)
        row = catalog.query("SELECT * FROM dataset_docs")[0]
        assert row["what_one_row_is"] == "one billing episode (AIH)"


class TestItRefusesToLaunder:
    """An inferred description presented as documented is the failure mode."""

    def test_inferred_without_reasoning_is_rejected(self, catalog: Catalog, tmp_path):
        root = _write(
            tmp_path,
            "x.yml",
            "system: SIM\nvariables:\n  LINHAA:\n    description: causal chain\n"
            "    source: inferred\n    asserted_by: tester\n",
        )
        with pytest.raises(CurationError, match="reasoning"):
            load_curation(catalog, root)

    def test_inferred_with_reasoning_is_accepted(self, catalog: Catalog, tmp_path):
        root = _write(
            tmp_path,
            "x.yml",
            "system: SIM\nvariables:\n  LINHAA:\n    source: inferred\n"
            "    asserted_by: tester\n    reasoning: measured over 7823 values\n",
        )
        load_curation(catalog, root)
        assert load_variable_docs(catalog)["LINHAA"].reasoning.startswith("measured")

    def test_an_assertion_needs_an_author(self, catalog: Catalog, tmp_path):
        root = _write(tmp_path, "x.yml", "system: SIM\nvariables:\n  FOO:\n    source: manual\n")
        with pytest.raises(CurationError, match="asserted_by"):
            load_curation(catalog, root)

    def test_multi_valued_needs_a_token_rule(self, catalog: Catalog, tmp_path):
        root = _write(
            tmp_path,
            "x.yml",
            "system: SIM\nvariables:\n  LINHAA:\n    multi_valued: true\n    source: layout_doc\n",
        )
        with pytest.raises(CurationError, match="token_rule"):
            load_curation(catalog, root)

    def test_an_unknown_source_is_rejected(self, catalog: Catalog, tmp_path):
        root = _write(tmp_path, "x.yml", "system: SIM\nvariables:\n  FOO:\n    source: vibes\n")
        with pytest.raises(CurationError, match="vibes"):
            load_curation(catalog, root)

    def test_a_bad_code_system_is_rejected(self, catalog: Catalog, tmp_path):
        root = _write(
            tmp_path,
            "x.yml",
            "system: SIM\nvariables:\n  FOO:\n    code_system: sort-of\n    source: layout_doc\n",
        )
        with pytest.raises(CurationError, match="code_system"):
            load_curation(catalog, root)

    def test_a_broken_file_loads_nothing(self, catalog: Catalog, tmp_path):
        """All or nothing: a half-applied file describes a state no file describes."""
        root = _write(tmp_path, "a.yml", SIH)
        _write(tmp_path, "b.yml", "system: SIM\nvariables:\n  FOO:\n    source: vibes\n")
        with pytest.raises(CurationError):
            load_curation(catalog, root)
        assert catalog.count("variable_docs") == 0


class TestCoverage:
    def test_coverage_counts_only_observed_fields(self, catalog: Catalog, tmp_path):
        """A document describing columns nobody has seen is not coverage."""
        catalog.execute(
            "INSERT INTO families (family_id, system, series, schema_signature) "
            "VALUES ('f','SIHSUS','RD','sig')"
        )
        for name in ("DIAG_PRINC", "IDADE", "UNDOCUMENTED"):
            catalog.execute(
                "INSERT INTO variable_profiles (family_id, field_name, schema_signature) "
                "VALUES ('f',?,'sig')",
                (name,),
            )
        load_curation(catalog, _write(tmp_path, "sihsus_rd.yml", SIH))
        row = next(r for r in coverage_by_rung(catalog) if r["system"] == "SIHSUS")
        assert row["observed_fields"] == 3
        assert row["documented"] == 2, "COD_IDADE is curated but never observed"
        assert row["via_layout_doc"] == 2

    def test_every_rung_is_a_column_even_at_zero(self, catalog: Catalog):
        catalog.execute(
            "INSERT INTO families (family_id, system, series, schema_signature) "
            "VALUES ('f','SIM','DO','sig')"
        )
        catalog.execute(
            "INSERT INTO variable_profiles (family_id, field_name, schema_signature) "
            "VALUES ('f','CAUSABAS','sig')"
        )
        row = coverage_by_rung(catalog)[0]
        assert row["via_inferred"] == 0 and row["via_manual"] == 0
