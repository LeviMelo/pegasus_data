"""ICD column quality and SIGTAP ingestion (§6).

The two rulings this pins are the ones with consequences. Exact-width matching
keeps a 3-character CBO-1994 code from being read as a truncated CBO-2002 one,
and the five-way quality classification keeps a valid code from a *different ICD
revision* from being filed as broken data — because the response to those is
different, and "malformed" invites someone to clean real records away.
"""

from __future__ import annotations

import io
import zipfile

import pyarrow as pa

from pegasus_data.catalog.store import Catalog
from pegasus_data.persist.reference import register_reference_tables, write_reference_tables
from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries
from pegasus_data.semantics.icd import (
    ColumnQuality,
    flag_suspect_bindings,
    infer_token_rule,
    measure_column,
)
from pegasus_data.sources.sigtap import (
    SigtapExport,
    entries_from_export,
    parse_layout,
    read_table,
)
from pegasus_data.view import _check_width, _labels_for, render_table


class TestTokenRuleInference:
    def test_a_single_code_column_infers_no_rule(self):
        assert infer_token_rule(["A419", "E119", "J189"]) == {}

    def test_the_sim_causal_chain_is_star_delimited(self):
        """Measured over the real data: '*'-separated four-character codes."""
        values = ["*I10X*I429*I219", "*R092*J189", "*P95X", "*R092*I509*I10X"]
        assert infer_token_rule(values) == {"delimiter": "*", "width": 4}

    def test_the_delimiter_is_chosen_by_coverage_not_by_order(self):
        """ATESTADO uses '/', and a fixed try-order picked '*' for it."""
        values = ["T71/X700", "S069/X954", "P209/P021", "J189/A419", "*I10X"]
        assert infer_token_rule(values)["delimiter"][0] == "/", "the heaviest leads"

    def test_a_column_that_mixes_separators_gets_both(self):
        """SIM's ATESTADO writes 'T07/X366*Y96' — one cell, two separators.

        Picking only the heavier one leaves the other inside a token, and the
        whole value then fails every shape check. 486 of ATESTADO's values read
        as malformed for exactly this reason.
        """
        values = ["T07/X366*Y96", "P209*P000", "S069/X954", "J189*A419", "T71/X700"]
        rule = infer_token_rule(values)
        assert set(rule["delimiter"]) == {"/", "*"}

    def test_a_multi_delimiter_rule_splits_on_any_of_them(self):
        from pegasus_data.view import _tokenize

        assert _tokenize("T07/X366*Y96", {"delimiter": "/*"}) == ["T07", "X366", "Y96"]

    def test_fixed_width_packing_without_a_delimiter(self):
        values = ["A419E119", "J189A419", "E119J189", "A419"]
        assert infer_token_rule(values) == {"width": 4}

    def test_sentinels_do_not_drive_the_inference(self):
        assert infer_token_rule(["0000", "0000", "", "A419"]) == {}


class TestQualityClassification:
    def test_a_sentinel_is_not_malformed(self):
        """DIAG_SECUN is dead, not dirty, and the report has to say which."""
        q = measure_column(["0000"] * 5, system="SIHSUS", field_name="DIAG_SECUN")
        assert q.sentinel == 5
        assert q.malformed == 0

    def test_icd9_is_a_different_revision_not_broken_data(self):
        """SIM ran on CID-9 until 1996 and those years are still on the tree."""
        q = measure_column(["7999", "7680", "8199"], system="SIM", field_name="CAUSABAS")
        assert q.other_revision == 3
        assert q.malformed == 0

    def test_genuinely_malformed_values_are_counted_and_kept(self):
        q = measure_column(["065099", "!!!!"], system="SIHSUS", field_name="DIAG_PRINC")
        assert q.malformed == 2
        assert "065099" in q.examples_malformed, "flagged, never dropped (§13)"

    def test_several_codes_in_one_cell(self):
        q = measure_column(
            ["*I10X*I429", "*R092*J189", "*A419*E119", "*J189*A419"],
            system="SIM", field_name="LINHAA",
        )
        assert q.several_codes == 4
        assert q.multi_valued

    def test_valid_but_absent_from_the_vintage_is_its_own_class(self):
        q = measure_column(
            ["A419", "Z999"], system="SIM", field_name="CAUSABAS",
            known_codes={"A419": "Septicemia"},
        )
        assert q.valid_but_absent == 1
        assert q.malformed == 0


class TestSuspectBindings:
    def test_a_near_zero_match_rate_is_reported_as_a_finding(self, catalog: Catalog):
        """IBGE's IDADE holds age bands and was bound to CID10 by a shape detector."""
        q = measure_column(
            ["2559", "1524", "2559", "1524"], system="IBGE", field_name="IDADE"
        )
        assert flag_suspect_bindings(catalog, [q]) == 1
        row = catalog.query(
            "SELECT * FROM open_questions WHERE key LIKE 'semantics.suspect_icd_binding%'"
        )[0]
        assert "IDADE" in row["question"]

    def test_a_healthy_column_is_not_flagged(self, catalog: Catalog):
        q = measure_column(["A419", "E119"], system="SIM", field_name="CAUSABAS")
        assert flag_suspect_bindings(catalog, [q]) == 0

    def test_an_empty_measurement_is_not_flagged(self, catalog: Catalog):
        assert flag_suspect_bindings(catalog, [ColumnQuality("SIM", "X")]) == 0


class TestWidthRuling:
    """§6.2 — exact width or no match. Never pad, never truncate."""

    MIXED = {"223": "Ocupação CBO-1994", "223505": "Médico clínico CBO-2002"}

    def test_a_short_code_never_matches_a_long_entry(self):
        labels = _labels_for(pa.array(["223"]), self.MIXED)
        assert labels.to_pylist() == ["Ocupação CBO-1994"]

    def test_a_long_code_never_matches_a_short_entry(self):
        labels = _labels_for(pa.array(["223505"]), self.MIXED)
        assert labels.to_pylist() == ["Médico clínico CBO-2002"]

    def test_a_padded_code_is_not_silently_stripped(self):
        """'000223' is not '223'. Zero-padding is part of the code."""
        assert _labels_for(pa.array(["000223"]), self.MIXED).to_pylist() == [None]

    def test_a_mixed_width_table_is_reported(self):
        message = _check_width("SP_PF_CBO", "CBO", pa.array(["223505"]), self.MIXED)
        assert message and "mixes code widths" in message

    def test_a_single_width_table_says_nothing(self):
        assert _check_width("X", "Y", pa.array(["A419"]), {"A419": "Septicemia"}) is None


class TestMultipleCodelistsPerField:
    """SP_ATOPROF is 8 characters in one era and 10 in another."""

    def test_both_tables_label_their_own_width(self, settings, catalog: Catalog):
        persist_entries(
            catalog,
            [
                DictionaryEntry(system="SIASUS", value_raw="12345678", value_label="Old-era procedure",
                                source="cnv", source_ref="a", confidence=0.95, value_group="TPROC"),
                DictionaryEntry(system="SIASUS", value_raw="87654321", value_label="Another old one",
                                source="cnv", source_ref="a", confidence=0.95, value_group="TPROC"),
                DictionaryEntry(system="SIASUS", value_raw="0301010012", value_label="New-era procedure",
                                source="cnv", source_ref="b", confidence=0.95, value_group="TPROC10"),
                DictionaryEntry(system="SIASUS", value_raw="0301010020", value_label="Another new one",
                                source="cnv", source_ref="b", confidence=0.95, value_group="TPROC10"),
            ],
        )
        register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
            "VALUES ('SIASUS','SP_ATOPROF','external','TPROC,TPROC10','manual')"
        )
        for codelist in ("TPROC", "TPROC10"):
            catalog.execute(
                "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
                "source_ref, confidence) VALUES ('SIASUS','','SP_ATOPROF',?,'manual','c',1.0)",
                (codelist,),
            )
        table = pa.table({"SP_ATOPROF": pa.array(["12345678", "0301010012"])})
        out, _ = render_table(
            table, store=catalog, lake_root=settings.lake_dir, system="SIASUS"
        )
        assert out.column("SP_ATOPROF_label").to_pylist() == [
            "Old-era procedure",
            "New-era procedure",
        ], "binding either table alone leaves half the history unlabelled"


class TestSigtapParsing:
    LAYOUT = (
        "Coluna,Tamanho,Inicio,Fim,Tipo\n"
        "CO_OCUPACAO,6,1,6,CHAR\n"
        "NO_OCUPACAO,20,7,26,VARCHAR2\n"
    )

    def test_the_layout_file_drives_the_positions(self):
        columns = parse_layout(self.LAYOUT)
        assert [c.name for c in columns] == ["CO_OCUPACAO", "NO_OCUPACAO"]
        assert columns[1].slice("223505MEDICO CLINICO    ") == "MEDICO CLINICO"

    def test_the_header_row_is_not_data(self):
        assert all(c.name != "COLUNA" for c in parse_layout(self.LAYOUT))

    def _archive(self) -> zipfile.ZipFile:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("tb_ocupacao_layout.txt", self.LAYOUT)
            z.writestr("tb_ocupacao.txt", "223505MEDICO CLINICO    \n225125CIRURGIAO        \n")
        return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))

    def test_rows_are_read_by_offset(self):
        rows = list(read_table(self._archive(), "tb_ocupacao"))
        assert rows[0] == {"CO_OCUPACAO": "223505", "NO_OCUPACAO": "MEDICO CLINICO"}
        assert len(rows) == 2

    def test_a_missing_table_yields_nothing_rather_than_raising(self):
        assert list(read_table(self._archive(), "tb_nonexistent")) == []

    def test_entries_carry_the_vintage_and_the_alias(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("tb_ocupacao_layout.txt", self.LAYOUT)
            z.writestr("tb_ocupacao.txt", "223505MEDICO CLINICO    \n")
        export = SigtapExport(filename="TabelaUnificada_202608_v1.zip",
                              competencia="202608", size=1)
        entries = entries_from_export(buffer.getvalue(), export, valid_to=None)
        groups = {e.value_group for e in entries}
        assert groups == {"CBO", "SIGTAP_OCUPACAO"}, (
            "SIGTAP rows land under the codelist name fields are already bound to"
        )
        assert all(e.source == "sigtap" for e in entries)
        assert all(e.valid_from == "202608" for e in entries)


class TestSourceAuthority:
    def test_sigtap_outranks_a_lookup_dbf_but_never_a_cnv(self):
        from pegasus_data.semantics.dictionary import SOURCE_AUTHORITY

        assert SOURCE_AUTHORITY["cnv"] < SOURCE_AUTHORITY["sigtap"]
        assert SOURCE_AUTHORITY["def"] < SOURCE_AUTHORITY["sigtap"]
        assert SOURCE_AUTHORITY["sigtap"] < SOURCE_AUTHORITY["dbf_lookup"]

    def test_community_never_overrides_a_first_party_table(self):
        from pegasus_data.semantics.dictionary import SOURCE_AUTHORITY

        for first_party in ("cnv", "def", "sigtap", "dbf_lookup", "demas_api", "pdf"):
            assert SOURCE_AUTHORITY[first_party] < SOURCE_AUTHORITY["community"]

    def test_community_still_beats_a_guess(self):
        from pegasus_data.semantics.dictionary import SOURCE_AUTHORITY

        assert SOURCE_AUTHORITY["community"] < SOURCE_AUTHORITY["inferred"]


class TestCepIsSettled:
    def test_the_ruling_is_recorded_as_resolved_not_open(self, catalog: Catalog, tmp_path):
        """A settled 'no' that keeps showing as unfinished work is worse than no answer."""
        from pegasus_data.semantics.curation import load_curation

        load_curation(catalog, tmp_path / "empty")
        row = catalog.query(
            "SELECT * FROM open_questions WHERE key = 'semantics.cep_decoding'"
        )[0]
        assert row["status"] == "resolved"
        assert "município" in row["resolution"]

    def test_cod_idade_stays_open_with_what_would_close_it(self, catalog: Catalog, tmp_path):
        from pegasus_data.semantics.curation import load_curation

        load_curation(catalog, tmp_path / "empty")
        row = catalog.query(
            "SELECT * FROM open_questions WHERE key = 'semantics.cod_idade_units'"
        )[0]
        assert row["status"] == "open"
        assert row["verification_procedure"]
        assert "IDADEPUB" in row["verification_procedure"], (
            "the record must say why the .DEF bindings do not answer it"
        )
