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

    This is now a safety net rather than a working rule, and the distinction is
    worth stating. Measured over the full catalog, the number of codes carrying
    two labels within one system and one validity window is **zero** — every
    apparent contradiction came from merging thirteen systems' SEXO.CNV into one
    table, or from merging vintages whose wording drifted. Both are fixed at the
    source: reference tables are scoped by system, and a read with no year asked
    for returns the current vintage instead of all of them.

    What remains is the case neither of those can rule out — a single .CNV that
    genuinely contradicts itself. Refusing there is still right: labelling a
    column from a lookup that cannot decide is how a large share of admissions
    would silently get the wrong sex.
    """

    def _reference_with_conflict(self, settings, catalog: Catalog):
        """Write the reference table directly: the dictionary cannot hold this.

        `persist_entries` keys on (system, group, field, code, window), so it
        physically cannot store one code twice in one window — which is why the
        real data has none. Constructing it here tests the guard, not the data.
        """
        import pyarrow.parquet as pq

        directory = settings.lake_dir / "reference" / "SEXO" / "system=SIHSUS" / "window=current"
        directory.mkdir(parents=True, exist_ok=True)
        pq.write_table(
            pa.table(
                {
                    "code": pa.array(["1", "1", "2"]),
                    "label": pa.array(["Masculino", "Feminino", "Feminino"]),
                    "source": pa.array(["cnv"] * 3),
                    "source_ref": pa.array(["a.cnv"] * 3),
                    "confidence": pa.array([0.95] * 3, type=pa.float32()),
                    "code_width": pa.array([1, 1, 1], type=pa.int8()),
                    "valid_from": pa.array([None, None, None], type=pa.string()),
                    "valid_to": pa.array([None, None, None], type=pa.string()),
                }
            ),
            directory / "part-00000.parquet",
        )
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
            "VALUES ('SIHSUS','SEXO','internal','SEXO','manual')"
        )
        return pa.table({"SEXO": pa.array(["1", "2"])})

    def test_it_refuses_to_label_and_names_the_disagreement(self, settings, catalog: Catalog):
        table = self._reference_with_conflict(settings, catalog)
        with pytest.warns(UserWarning, match="sources disagree"):
            out, report = render_table(
                table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS"
            )
        assert out.column("SEXO").to_pylist() == ["1", "2"], "raw codes survive"
        assert "SEXO" in report.unlabelled
        assert any("Feminino" in w and "Masculino" in w for w in report.warnings)

    def test_strict_raises(self, settings, catalog: Catalog):
        table = self._reference_with_conflict(settings, catalog)
        with pytest.raises(LabelUnavailable, match="disagree"):
            render_table(
                table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS", strict=True
            )

    def test_a_code_that_is_not_observed_does_not_block_the_column(
        self, settings, catalog: Catalog
    ):
        """Only contradictions on codes the data actually contains matter."""
        self._reference_with_conflict(settings, catalog)
        out, report = render_table(
            pa.table({"SEXO": pa.array(["2"])}),
            store=catalog, lake_root=settings.lake_dir, system="SIHSUS",
        )
        assert out.column("SEXO").to_pylist() == ["Feminino"]
        assert "SEXO" not in report.unlabelled


class TestSystemScoping:
    """The contradiction was manufactured by merging systems (§C root cause)."""

    def _two_systems(self, settings, catalog: Catalog):
        from pegasus_data.persist.reference import (
            register_reference_tables,
            write_reference_tables,
        )
        from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries

        persist_entries(
            catalog,
            [
                # SIHSUS codes sex 1/3; SINASC codes it 1/2. Both internally
                # consistent, and irreconcilable if merged.
                DictionaryEntry(system="SIHSUS", value_raw="1", value_label="Masculino",
                                source="cnv", source_ref="sih", confidence=0.95, value_group="SEXO"),
                DictionaryEntry(system="SIHSUS", value_raw="3", value_label="Feminino",
                                source="cnv", source_ref="sih", confidence=0.95, value_group="SEXO"),
                DictionaryEntry(system="SINASC", value_raw="1", value_label="Masculino",
                                source="cnv", source_ref="dn", confidence=0.95, value_group="SEXO"),
                DictionaryEntry(system="SINASC", value_raw="2", value_label="Feminino",
                                source="cnv", source_ref="dn", confidence=0.95, value_group="SEXO"),
            ],
        )
        register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))
        for system in ("SIHSUS", "SINASC"):
            catalog.execute(
                "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
                "VALUES (?,'SEXO','internal','SEXO','manual')",
                (system,),
            )

    def test_each_system_decodes_against_its_own_copy(self, settings, catalog: Catalog):
        self._two_systems(settings, catalog)
        sih, _ = render_table(
            pa.table({"SEXO": pa.array(["3"])}),
            store=catalog, lake_root=settings.lake_dir, system="SIHSUS",
        )
        dn, _ = render_table(
            pa.table({"SEXO": pa.array(["2"])}),
            store=catalog, lake_root=settings.lake_dir, system="SINASC",
        )
        assert sih.column("SEXO").to_pylist() == ["Feminino"], "SIH codes sex 1/3"
        assert dn.column("SEXO").to_pylist() == ["Feminino"], "SINASC codes sex 1/2"

    def test_the_other_systems_codes_do_not_leak_in(self, settings, catalog: Catalog):
        """SIHSUS has no '2', and must not borrow SINASC's meaning for it."""
        self._two_systems(settings, catalog)
        out, report = render_table(
            pa.table({"SEXO": pa.array(["2"])}),
            store=catalog, lake_root=settings.lake_dir, system="SIHSUS",
        )
        # The raw code survives — better unlabelled than mislabelled — and the
        # point is what it is NOT: SINASC's "Feminino" never reaches a SIH row.
        assert out.column("SEXO").to_pylist() == ["2"]
        assert "SEXO" in report.unlabelled
        # A single-valued column that decodes to nothing is named as such, and
        # stays in `unlabelled` so this guard cannot be weakened by that.
        assert report.constant.get("SEXO") == "2"

    def test_a_borrowed_table_is_used_when_the_system_ships_none(
        self, settings, catalog: Catalog
    ):
        """A gap is worse than a neighbour's table; the guard still applies."""
        self._two_systems(settings, catalog)
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
            "VALUES ('CIHA','SEXO','internal','SEXO','manual')"
        )
        out, report = render_table(
            pa.table({"SEXO": pa.array(["3"])}),
            store=catalog, lake_root=settings.lake_dir, system="CIHA",
        )
        assert out.num_rows == 1


class TestBindingChoiceIsDeterministic:
    """Six .DEF bindings at identical confidence, and one has to win reproducibly.

    CNES's NAT_JUR is bound to NATJUR, NATJURC, ESFERAJUR, ESFERAJURC, ATJURC
    and RETENCAO, all at 0.9. With nothing to break the tie, SQLite returned
    them in whatever order it liked and the renderer picked a different table
    between runs. A column whose label depends on row order is not reproducible,
    and on a real catalog it picked ATJURC — a truncated neighbour with no
    reference table at all.
    """

    def _bind(self, catalog: Catalog, *codelists: str) -> None:
        for codelist in codelists:
            catalog.execute(
                "INSERT INTO field_codelists (system, family_id, field_name, codelist, "
                "source, source_ref, confidence) VALUES ('CNES','','NAT_JUR',?,'def','d',0.9)",
                (codelist,),
            )

    def test_the_same_catalog_always_yields_the_same_binding(self, catalog: Catalog):
        from pegasus_data.view import _bindings

        self._bind(catalog, "RETENCAO", "ATJURC", "NATJURC", "ESFERAJUR", "NATJUR")
        picks = {tuple(_bindings(catalog, "CNES", None)["NAT_JUR"]) for _ in range(8)}
        assert len(picks) == 1

    def test_the_field_s_own_table_wins_the_tie(self, catalog: Catalog):
        """NAT_JUR's table is NATJUR; the rest are roll-ups and neighbours."""
        from pegasus_data.view import _bindings

        self._bind(catalog, "RETENCAO", "ATJURC", "NATJURC", "ESFERAJUR", "NATJUR")
        assert _bindings(catalog, "CNES", None)["NAT_JUR"][0] == "NATJUR"

    def test_confidence_still_outranks_a_name_match(self, catalog: Catalog):
        """Affinity breaks ties; it does not overturn a better source."""
        from pegasus_data.view import _bindings

        self._bind(catalog, "NAT_JUR")
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
            "source_ref, confidence) VALUES ('CNES','','NAT_JUR','CURATED','manual','c',1.0)"
        )
        assert _bindings(catalog, "CNES", None)["NAT_JUR"][0] == "CURATED"


class TestReadingAReferenceTableThatFiltersToNothing:
    """An empty filter result must be an empty table, not a crash.

    ``pa.array([])`` infers the null type, and ``Table.filter`` rejects a
    non-boolean mask — so every one of these narrowings blew up with
    ``ArrowNotImplementedError`` the moment it was handed a table whose rows all
    fell outside the requested window. Found by fetching a real SIH-RD file
    against a codelist whose only vintage predated the year asked for; the
    labelling gap it should have reported came back as a traceback instead.
    """

    def _one_window(self, settings, catalog: Catalog):
        """One codelist published in one window, long before the year asked for."""
        persist_entries(
            catalog,
            [
                DictionaryEntry(
                    system="SIHSUS", value_raw=code, value_label=label,
                    source="cnv", source_ref=f"a:{code}", confidence=0.9,
                    value_group="SEXO", valid_from="200001", valid_to="200012",
                )
                for code, label in (("1", "Masculino"), ("2", "Feminino"))
            ],
        )
        register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))

    def test_a_year_outside_every_window_falls_back_instead_of_raising(
        self, settings, catalog: Catalog
    ):
        from pegasus_data.persist.reference import read_reference_table

        self._one_window(settings, catalog)
        table = read_reference_table(settings.lake_dir, "SEXO", system="SIHSUS", year=2023)
        assert table.num_rows >= 0

    def test_a_code_width_nothing_matches_yields_an_empty_table(
        self, settings, catalog: Catalog
    ):
        from pegasus_data.persist.reference import read_reference_table

        self._one_window(settings, catalog)
        table = read_reference_table(
            settings.lake_dir, "SEXO", system="SIHSUS", code_width=17
        )
        assert table.num_rows == 0

    def test_two_narrowings_where_the_first_empties_the_table(
        self, settings, catalog: Catalog
    ):
        """The exact crash: an empty table makes an empty mask, and an empty
        Python list infers the *null* type, which ``filter`` refuses. Every
        narrowing after a narrowing that matched nothing hit this."""
        from pegasus_data.persist.reference import read_reference_table

        self._one_window(settings, catalog)
        table = read_reference_table(
            settings.lake_dir, "SEXO", system="SIHSUS", code_width=17, year=2023
        )
        assert table.num_rows == 0

    def test_an_unpublished_window_yields_an_empty_table(self, settings, catalog: Catalog):
        from pegasus_data.persist.reference import read_reference_table

        self._one_window(settings, catalog)
        table = read_reference_table(
            settings.lake_dir, "SEXO", system="SIHSUS", valid_from="199001"
        )
        assert table.num_rows == 0


class TestADeadBindingLosesToAWorkingOne:
    """`.DEF` cannot tell a code system from a tabulation axis derived from the
    column, so a date arrives bound to ANOMES and an age to a table of age
    bands. 35.2% of measurable bindings decode none of their column's observed
    values. Where a working table also exists, the dead one must not win.

    Deprioritised rather than excluded: the measurement is taken against what
    the profiler saw, and another partition could hold values it did not.
    """

    def _bind(self, catalog, field, codelist, *, confidence, decodes):
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, "
            "source, source_ref, confidence, decodes_observed) "
            "VALUES ('SIHSUS','',?,?,'def','RD.DEF',?,?)",
            (field, codelist, confidence, decodes),
        )

    def test_the_working_table_wins_even_at_lower_confidence(self, catalog: Catalog):
        # ANOMES is the tabulation axis .DEF declared, at full confidence.
        self._bind(catalog, "DT_INTER", "ANOMES", confidence=0.9, decodes=0.0)
        self._bind(catalog, "DT_INTER", "DTINTER", confidence=0.5, decodes=0.8)
        from pegasus_data.view import _bindings

        assert _bindings(catalog, "SIHSUS", None)["DT_INTER"][0] == "DTINTER"

    def test_a_dead_binding_is_still_offered_when_nothing_else_is(self, catalog: Catalog):
        """Excluding it would be a stronger claim than the measurement supports."""
        self._bind(catalog, "DT_INTER", "ANOMES", confidence=0.9, decodes=0.0)
        from pegasus_data.view import _bindings

        assert _bindings(catalog, "SIHSUS", None)["DT_INTER"][0] == "ANOMES"

    def test_an_unmeasured_binding_is_not_treated_as_dead(self, catalog: Catalog):
        self._bind(catalog, "SEXO", "SEXO", confidence=0.9, decodes=None)
        self._bind(catalog, "SEXO", "OTHER", confidence=0.4, decodes=0.9)
        from pegasus_data.view import _bindings

        assert _bindings(catalog, "SIHSUS", None)["SEXO"][0] == "SEXO"


class TestTheDataDecidesWhichTableIsRight:
    """Ranking gives a deterministic pick, not a correct one.

    `CNES` in SIH is bound by `.DEF` to 31 tables — TCNESBR, one per state, and
    three federal-hospital lists — all at confidence 0.9, none whose name
    resembles the field. Every tie-break fell through to alphabetical order, so
    the renderer chose HOSFEDRJ: six rows, federal hospitals in Rio de Janeiro.
    Acre's establishment codes matched none of them and the column came back
    raw, while TCNESBR sat in the same lake with 7,189 rows including every code
    in the file.

    The column's own values settle it, and they are already in memory.
    """

    @staticmethod
    def _load(tables):
        return lambda codelist: tables.get(codelist)

    def test_the_table_that_decodes_the_column_wins(self) -> None:
        from pegasus_data.view import _choose_binding

        tables = {
            "HOSFEDRJ": {"2269384": "Hospital federal"},
            "TCNESBR": {"2001578": "Hospital geral de Rio Branco"},
        }
        picked, share, _ = _choose_binding(
            "CNES", ["HOSFEDRJ", "TCNESBR"], {"2001578"}, self._load(tables)
        )
        assert picked == "TCNESBR"
        assert share == 1.0

    def test_a_table_missing_from_the_lake_simply_loses(self) -> None:
        """A candidate that cannot be read is not an error, it is a worse option."""
        from pegasus_data.view import _choose_binding

        tables = {"REAL": {"1": "Sim"}}
        picked, share, _ = _choose_binding(
            "X", ["ABSENT", "REAL"], {"1"}, self._load(tables)
        )
        assert (picked, share) == ("REAL", 1.0)

    def test_it_stops_once_a_table_decodes_everything(self) -> None:
        """114 tables are bound to DIAG_PRINC; reading them all costs more than it returns."""
        from pegasus_data.view import _choose_binding

        tables = {"GOOD": {"A": "a"}, "ALSO": {"A": "a"}}
        _, _, tried = _choose_binding("X", ["GOOD", "ALSO"], {"A"}, self._load(tables))
        assert tried == 1

    def test_it_weighs_no_more_than_the_cap(self) -> None:
        from pegasus_data.view import _MAX_CANDIDATES, _choose_binding

        names = [f"T{i}" for i in range(40)]
        _, _, tried = _choose_binding("X", names, {"zzz"}, lambda _cl: {"other": "x"})
        assert tried == _MAX_CANDIDATES

    def test_an_empty_column_does_not_drive_the_choice(self) -> None:
        """With nothing observed there is no evidence, so ranking stands."""
        from pegasus_data.view import _choose_binding

        picked, share, tried = _choose_binding("X", ["FIRST", "SECOND"], set(), lambda _cl: {})
        assert (picked, share, tried) == ("FIRST", 0.0, 0)

    def test_the_best_of_a_bad_set_is_reported_not_hidden(self) -> None:
        """PROC_REA: 12 tables bound, the best decodes 3%. That is a finding."""
        from pegasus_data.view import _TOO_WEAK, _choose_binding

        picked, share, _ = _choose_binding(
            "PROC_REA", ["A"], {"1", "2", "3", "4"}, lambda _cl: {"1": "one"}
        )
        assert picked == "A"
        assert share == 0.25
        assert share < _TOO_WEAK
