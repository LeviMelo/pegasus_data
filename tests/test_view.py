"""The rendering model (§5).

The governing goal is that a user should never see an untranslated internal code
and should never need an external table to understand what they are looking at.
These tests pin the parts of that which are easy to regress: the axis that
decides replace-vs-accompany, the read-time join that used to not exist, and the
rule that a label which cannot be produced is *named* rather than dropped.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.persist.reference import register_reference_tables, write_reference_tables
from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries
from pegasus_data.view import (
    PROFILES,
    LabelUnavailable,
    RenderProfile,
    _tokenize,
    column_kind,
    render_table,
    resolve_profile,
)


@pytest.fixture
def rendered(settings, catalog: Catalog):
    """A catalog with SEXO (internal), CID10 (external) and a unit column."""
    persist_entries(
        catalog,
        [
            DictionaryEntry(system="SIHSUS", value_raw="1", value_label="Masculino",
                            source="cnv", source_ref="a:1", confidence=0.95, value_group="SEXO"),
            DictionaryEntry(system="SIHSUS", value_raw="2", value_label="Feminino",
                            source="cnv", source_ref="a:2", confidence=0.95, value_group="SEXO"),
            DictionaryEntry(system="SIHSUS", value_raw="A419", value_label="Septicemia não especificada",
                            source="cnv", source_ref="b:1", confidence=0.95, value_group="CID10"),
            DictionaryEntry(system="SIHSUS", value_raw="E119", value_label="Diabetes mellitus tipo 2",
                            source="cnv", source_ref="b:2", confidence=0.95, value_group="CID10"),
            DictionaryEntry(system="SIHSUS", value_raw="3", value_label="Meses",
                            source="cnv", source_ref="c:1", confidence=0.95, value_group="UNIDIDADE"),
            DictionaryEntry(system="SIHSUS", value_raw="4", value_label="Anos",
                            source="cnv", source_ref="c:2", confidence=0.95, value_group="UNIDIDADE"),
        ],
    )
    register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))
    catalog.executemany(
        """INSERT INTO variable_docs (system, field_name, code_system, codelist, multi_valued,
           token_rule, depends_on, derived, translated_name, source, asserted_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            ("SIHSUS", "SEXO", "internal", "SEXO", 0, None, None, None, "Sex", "manual", "t"),
            ("SIHSUS", "DIAG_PRINC", "external", "CID10", 0, '{"width": 4}', None, None,
             "Principal diagnosis", "manual", "t"),
            ("SIHSUS", "LINHAA", "external", "CID10", 1, '{"width": 4}', None, None,
             "Certificate line A", "manual", "t"),
            ("SIHSUS", "COD_IDADE", "internal", "UNIDIDADE", 0, None, None, None,
             "Age unit", "manual", "t"),
            ("SIHSUS", "IDADE", "none", None, 0, None, '["COD_IDADE"]',
             '[{"name": "IDADE_anos", "from": ["IDADE", "COD_IDADE"], "rule": "years"}]',
             "Age", "manual", "t"),
            ("SIHSUS", "VAL_TOT", "none", None, 0, None, None, None, "Total value", "manual", "t"),
        ],
    )
    table = pa.table(
        {
            "SEXO": pa.array(["1", "2", "1"]),
            "DIAG_PRINC": pa.array(["A419", "E119", "Z999"]),
            "LINHAA": pa.array(["A419E119", "E119", None]),
            "IDADE": pa.array(["30", "67", "12"]),
            "COD_IDADE": pa.array(["3", "4", "4"]),
            "VAL_TOT": pa.array([100.0, 200.0, 300.0]),
            "MUNIC_RES": pa.array(["270430", "270430", "280030"]),
            "MUNIC_RES_uf": pa.array(["AL", "AL", "SE"]),
        }
    )
    return settings, catalog, table


def _render(rendered, **kw):
    settings, catalog, table = rendered
    return render_table(
        table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS", **kw
    )


class TestTheAxis:
    """§5.2 — internal vs external governs replace vs accompany."""

    def test_internal_labels_replace_the_code(self, rendered):
        out, _ = _render(rendered)
        assert out.column("SEXO").to_pylist() == ["Masculino", "Feminino", "Masculino"]
        assert "SEXO_label" not in out.schema.names

    def test_external_keeps_both(self, rendered):
        out, _ = _render(rendered)
        assert out.column("DIAG_PRINC").to_pylist() == ["A419", "E119", "Z999"]
        assert out.column("DIAG_PRINC_label").to_pylist()[:2] == [
            "Septicemia não especificada",
            "Diabetes mellitus tipo 2",
        ]

    def test_code_system_none_is_left_alone(self, rendered):
        out, _ = _render(rendered)
        assert out.column("VAL_TOT").to_pylist() == [100.0, 200.0, 300.0]

    def test_an_unmatched_external_code_keeps_a_null_label(self, rendered):
        """Z999 is not in the table; the row survives, the label is null."""
        out, _ = _render(rendered)
        assert out.column("DIAG_PRINC_label").to_pylist()[2] is None
        assert out.column("DIAG_PRINC").to_pylist()[2] == "Z999"


class TestProfiles:
    def test_codes_renders_nothing(self, rendered):
        out, _ = _render(rendered, profile="codes")
        assert out.column("SEXO").to_pylist() == ["1", "2", "1"]
        assert "DIAG_PRINC_label" not in out.schema.names

    def test_audit_shows_internal_codes_too(self, rendered):
        out, _ = _render(rendered, profile="audit")
        assert out.column("SEXO").to_pylist() == ["1", "2", "1"]
        assert out.column("SEXO_label").to_pylist()[0] == "Masculino"

    def test_a_per_column_override_beats_the_profile(self, rendered):
        out, _ = _render(rendered, profile="analysis", render={"SEXO": "both"})
        assert out.column("SEXO").to_pylist() == ["1", "2", "1"]
        assert "SEXO_label" in out.schema.names

    def test_an_unknown_profile_raises(self, rendered):
        with pytest.raises(KeyError, match="nonsense"):
            _render(rendered, profile="nonsense")

    def test_every_named_profile_resolves(self):
        for name in PROFILES:
            assert isinstance(resolve_profile(name), RenderProfile)

    def test_companions_can_be_switched_off(self, rendered):
        out, report = _render(rendered, companions=False)
        assert "MUNIC_RES_uf" not in out.schema.names
        assert "MUNIC_RES_uf" in report.companions_dropped

    def test_companions_are_kept_by_default(self, rendered):
        out, _ = _render(rendered)
        assert "MUNIC_RES_uf" in out.schema.names


class TestMultiValued:
    """§5.7 — concatenate, in order, never dropping a token."""

    def test_tokens_are_labelled_and_joined_in_order(self, rendered):
        out, _ = _render(rendered)
        assert out.column("LINHAA_label").to_pylist()[0] == (
            "A419 Septicemia não especificada | E119 Diabetes mellitus tipo 2"
        )

    def test_an_unmatched_token_passes_through_as_its_code(self, rendered):
        settings, catalog, table = rendered
        table = table.set_column(
            table.schema.get_field_index("LINHAA"), "LINHAA",
            pa.array(["A419Z999", None, None]),
        )
        out, report = render_table(
            table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS"
        )
        assert out.column("LINHAA_label").to_pylist()[0] == (
            "A419 Septicemia não especificada | Z999"
        )
        assert report.tokens_unmatched["LINHAA"] == 1

    def test_it_reports_the_companions(self, rendered):
        out, _ = _render(rendered)
        assert out.column("LINHAA_codes").to_pylist()[0] == ["A419", "E119"]
        assert out.column("LINHAA_unmatched").to_pylist()[0] == 0

    def test_fixed_width_tokenising(self):
        assert _tokenize("A419E119", {"width": 4}) == ["A419", "E119"]

    def test_delimiter_tokenising_keeps_order(self):
        assert _tokenize("*I10X*I429*I219", {"delimiter": "*"}) == ["I10X", "I429", "I219"]

    def test_a_delimiter_rule_wins_over_width(self):
        """SIM packs '*'-separated 4-char codes; splitting on width would shift."""
        assert _tokenize("*I10X*I429", {"delimiter": "*", "width": 4}) == ["I10X", "I429"]


class TestDerived:
    """§5.3 — resolve multi-column semantics into one usable value."""

    def test_age_is_resolved_against_its_unit(self, rendered):
        out, report = _render(rendered)
        assert "IDADE_anos" in report.derived_added
        years = out.column("IDADE_anos").to_pylist()
        assert years[0] == pytest.approx(2.5), "30 months is two and a half years"
        assert years[1] == pytest.approx(67.0)

    def test_derived_can_be_switched_off(self, rendered):
        out, _ = _render(rendered, derived=False)
        assert "IDADE_anos" not in out.schema.names

    def test_the_codes_profile_omits_it(self, rendered):
        out, _ = _render(rendered, profile="codes")
        assert "IDADE_anos" not in out.schema.names


class TestItNeverSilentlyReturnsUnlabelled:
    """§5.4 — a requested label that cannot be produced raises or warns BY NAME."""

    def test_strict_raises_naming_the_field(self, rendered):
        with pytest.raises(LabelUnavailable, match="VAL_TOT"):
            _render(rendered, render={"VAL_TOT": "label"}, strict=True)

    def test_non_strict_warns_naming_the_field(self, rendered):
        with pytest.warns(UserWarning, match="VAL_TOT"):
            _, report = _render(rendered, render={"VAL_TOT": "label"})
        assert "VAL_TOT" in report.unlabelled

    def test_a_missing_reference_table_is_reported(self, settings, catalog: Catalog):
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
            "VALUES ('SIHSUS','SEXO','internal','NOT_MATERIALISED','manual')"
        )
        table = pa.table({"SEXO": pa.array(["1"])})
        with pytest.raises(LabelUnavailable, match="NOT_MATERIALISED"):
            render_table(
                table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS", strict=True
            )


class TestHeadersAndValues:
    def test_translated_headers(self, rendered):
        out, _ = _render(rendered, headers="translated")
        assert "Sex" in out.schema.names
        assert "SEXO" not in out.schema.names

    def test_both_headers_keep_the_original(self, rendered):
        out, _ = _render(rendered, headers="both")
        assert "SEXO (Sex)" in out.schema.names

    def test_original_headers_are_the_default(self, rendered):
        out, _ = _render(rendered)
        assert "SEXO" in out.schema.names

    def test_combined_values(self, rendered):
        out, _ = _render(rendered, values="combined")
        assert out.column("DIAG_PRINC").to_pylist()[0] == "A419 – Septicemia não especificada"


class TestColumnKinds:
    def test_it_tells_a_label_from_a_companion(self):
        base = frozenset({"MUNIC_RES", "SEXO"})
        assert column_kind("SEXO", base) == "raw"
        assert column_kind("SEXO_label", base) == "label"
        assert column_kind("MUNIC_RES_uf", base) == "companion"

    def test_a_suffix_without_its_base_is_just_a_column(self):
        """ESTADO_label with no ESTADO column is a column named that, not a label."""
        assert column_kind("ESTADO_label", frozenset({"SEXO"})) == "raw"


class TestContradictoryCodelists:
    """A table that disagrees with itself cannot render a column (§5.2).

    The kits ship .CNV files from systems that encoded the same field
    differently, so the merged SEXO table contains both '1 -> Masculino' and
    '1 -> Feminino'. Last-write-wins is right *within* one .CNV and catastrophic
    across files that disagree: it would label a large share of Brazilian
    hospital admissions with the wrong sex and show nothing in the output.
    """

    def _catalog_with_conflict(self, settings, catalog: Catalog):
        from pegasus_data.persist.reference import (
            register_reference_tables,
            write_reference_tables,
        )
        from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries

        persist_entries(
            catalog,
            [
                # Different kit eras, which is how the real contradiction
                # arises: the dictionary key includes valid_from, so both
                # readings survive and the merged table holds two labels for '1'.
                DictionaryEntry(system="SIHSUS", value_raw="1", value_label="Masculino",
                                source="cnv", source_ref="a:1", confidence=0.95,
                                value_group="SEXO", valid_from="199201"),
                DictionaryEntry(system="SIHSUS", value_raw="1", value_label="Feminino",
                                source="cnv", source_ref="b:1", confidence=0.95,
                                value_group="SEXO", valid_from="200801"),
                DictionaryEntry(system="SIHSUS", value_raw="2", value_label="Feminino",
                                source="cnv", source_ref="a:2", confidence=0.95,
                                value_group="SEXO", valid_from="199201"),
                DictionaryEntry(system="SIHSUS", value_raw="2", value_label="Feminino",
                                source="cnv", source_ref="b:2", confidence=0.95,
                                value_group="SEXO", valid_from="200801"),
            ],
        )
        register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
            "VALUES ('SIHSUS','SEXO','internal','SEXO','manual')"
        )
        return pa.table({"SEXO": pa.array(["1", "2"])})

    def test_it_refuses_to_label_and_names_the_disagreement(self, settings, catalog: Catalog):
        table = self._catalog_with_conflict(settings, catalog)
        with pytest.warns(UserWarning, match="sources disagree"):
            out, report = render_table(
                table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS"
            )
        assert out.column("SEXO").to_pylist() == ["1", "2"], "raw codes survive"
        assert "SEXO" in report.unlabelled
        assert any("Feminino" in w and "Masculino" in w for w in report.warnings)

    def test_strict_raises(self, settings, catalog: Catalog):
        table = self._catalog_with_conflict(settings, catalog)
        with pytest.raises(LabelUnavailable, match="disagree"):
            render_table(
                table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS", strict=True
            )

    def test_a_code_that_is_not_observed_does_not_block_the_column(
        self, settings, catalog: Catalog
    ):
        """Only contradictions on codes the data actually contains matter."""
        self._catalog_with_conflict(settings, catalog)
        out, report = render_table(
            pa.table({"SEXO": pa.array(["2"])}),
            store=catalog, lake_root=settings.lake_dir, system="SIHSUS",
        )
        assert out.column("SEXO").to_pylist() == ["Feminino"]
        assert "SEXO" not in report.unlabelled
