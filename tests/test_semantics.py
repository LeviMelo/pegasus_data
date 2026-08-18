"""The semantic layer: .CNV and .DEF grammars, kits, dictionary merge, ledger."""

from __future__ import annotations

import io
import zipfile

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.semantics.cnv_parser import expand_expression, parse_cnv_bytes
from pegasus_data.semantics.def_parser import parse_def_bytes
from pegasus_data.semantics.dictionary import (
    codelists_for,
    entries_from_kit,
    lookup,
    most_granular_codelist,
    persist_bindings,
    persist_entries,
)
from pegasus_data.semantics.tabkit import kit_validity, parse_kit, persist_kit
from tests.conftest import make_dbf

# Verbatim from TAB_SIH_199201-199712.zip.
SEXO_CNV = (
    b"3 1\r\n"
    b"      3  Ignorado                                           0-9\r\n"
    b"      1  Masculino                                          1\r\n"
    b"      2  Feminino                                           2,3\r\n"
)

CID10CAP_CNV = (
    b"2 3\r\n"
    b"    001  I.   Algumas doencas infecciosas e parasitarias    A00-B99\r\n"
    b"    002  II.  Neoplasias (tumores)                          C00-D48\r\n"
)

RD_DEF = (
    b";Movimento de AIH - Arquivos Reduzidos - Brasil\r\n"
    b";\r\n"
    b"A..\\DADOS\\RD_AIH_Reduzida\\RD*.DBC\r\n"
    b"?\\TAB\\RD.HLP\r\n"
    b"IValor Total       ,VAL_TOT\r\n"
    b"I\xd3bitos            ,MORTE\r\n"
    b"LSexo              ,SEXO      ,1         ,SEXO.CNV\r\n"
    b"SSexo              ,SEXO      ,1         ,SEXO.CNV\r\n"
    b"LHospital BR (CNES),CNES      ,RAZAO     ,TCNESBR.DBF\r\n"
    b"QUnknown marker\r\n"
)


class TestCnv:
    def test_header_and_categories(self):
        cnv = parse_cnv_bytes(SEXO_CNV, name="SEXO.CNV", source_ref="kit!SEXO.CNV")
        assert cnv.declared_categories == 3
        assert cnv.code_width == 1
        assert cnv.category_count == 3
        assert [c.label for c in cnv.categories] == ["Ignorado", "Masculino", "Feminino"]

    def test_last_match_wins(self):
        """The catch-all is listed first and overridden; first-match-wins is wrong."""
        mapping = parse_cnv_bytes(SEXO_CNV, name="SEXO.CNV", source_ref="x").mapping()
        labels = {k: v[0] for k, v in mapping.items()}
        assert labels["1"] == "Masculino"
        assert labels["2"] == "Feminino"
        assert labels["3"] == "Feminino"
        assert labels["0"] == "Ignorado"
        assert labels["9"] == "Ignorado"

    def test_provenance_reaches_the_line(self):
        cnv = parse_cnv_bytes(SEXO_CNV, name="SEXO.CNV", source_ref="kit!SEXO.CNV")
        _, category = cnv.mapping()["1"]
        assert category.line_no == 3
        assert category.expression == "1"

    def test_alphanumeric_range_needs_a_universe(self):
        cnv = parse_cnv_bytes(CID10CAP_CNV, name="CID10CAP.CNV", source_ref="x")
        assert cnv.mapping() == {}
        rules = cnv.rules()
        assert {expr for expr, _ in rules} == {"A00-B99", "C00-D48"}

    def test_alphanumeric_range_expands_against_a_universe(self):
        universe = frozenset({"A00", "A001", "B99", "C00", "D480", "Z99"})
        cnv = parse_cnv_bytes(
            CID10CAP_CNV, name="CID10CAP.CNV", source_ref="x", universe=universe
        )
        labels = {k: v[0] for k, v in cnv.mapping().items()}
        assert set(labels) == {"A00", "A001", "B99", "C00", "D480"}
        assert labels["A001"].startswith("I.")
        assert labels["C00"].startswith("II.")
        assert "Z99" not in labels


class TestExpandExpression:
    def test_single_code(self):
        assert expand_expression("1", width=1) == (["1"], [])

    def test_comma_list(self):
        codes, rest = expand_expression("2,3", width=1)
        assert codes == ["2", "3"] and rest == []

    def test_numeric_range_pads_to_declared_width(self):
        codes, _ = expand_expression("0-9", width=3)
        assert codes[0] == "000" and codes[-1] == "009"

    def test_mixed_range_and_list(self):
        codes, _ = expand_expression("100-102,400", width=3)
        assert codes == ["100", "101", "102", "400"]

    def test_unpadded_alias_is_not_emitted(self):
        """'0' must not become an alias for '000000' — it would mislabel data."""
        codes, _ = expand_expression("000000-000002", width=6)
        assert codes == ["000000", "000001", "000002"]

    def test_oversized_range_stays_a_rule(self):
        codes, rest = expand_expression("0-999999", width=6, max_expansion=100)
        assert codes == [] and rest == ["0-999999"]


class TestDef:
    def test_parses_every_line_kind(self):
        parsed = parse_def_bytes(RD_DEF, name="RD.DEF", source_ref="kit!RD.DEF")
        assert parsed.title.startswith("Movimento de AIH")
        assert parsed.data_glob.endswith("RD*.DBC")
        assert parsed.file_pattern() == "RD*.DBC"
        assert parsed.help_ref.endswith("RD.HLP")
        assert len(parsed.variables) == 5

    def test_incremento_marks_the_ministrys_own_measures(self):
        parsed = parse_def_bytes(RD_DEF, name="RD.DEF", source_ref="x")
        measures = {v.field_name for v in parsed.measures}
        assert measures == {"VAL_TOT", "MORTE"}

    def test_lookup_binding_and_kind(self):
        parsed = parse_def_bytes(RD_DEF, name="RD.DEF", source_ref="x")
        assert parsed.lookups_for("SEXO") == ["SEXO.CNV"]
        cnes = next(v for v in parsed.variables if v.field_name == "CNES")
        assert cnes.lookup_kind == "dbf"
        assert cnes.category_arg == "RAZAO"

    def test_official_name_prefers_the_shortest_label(self):
        parsed = parse_def_bytes(RD_DEF, name="RD.DEF", source_ref="x")
        assert parsed.official_names()["SEXO"] == "Sexo"

    def test_unknown_marker_is_recorded_not_dropped(self):
        parsed = parse_def_bytes(RD_DEF, name="RD.DEF", source_ref="x")
        assert any("unrecognised marker" in w for w in parsed.warnings)

    def test_accented_labels_decode(self):
        parsed = parse_def_bytes(RD_DEF, name="RD.DEF", source_ref="x")
        assert any("bitos" in v.display_name for v in parsed.measures)


class TestKit:
    def _kit(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("SEXO.CNV", SEXO_CNV)
            z.writestr("RD.DEF", RD_DEF)
            z.writestr(
                "CID10.DBF",
                make_dbf([("CID10", "C", 4, 0), ("DESCR", "C", 20, 0)], [["A00", "Colera"]]),
            )
        return buf.getvalue()

    def test_validity_from_filename(self):
        assert kit_validity("/x/TAB_SIH_199201-199712.zip") == ("199201", "199712")
        assert kit_validity("/x/TAB_SIH.zip") == (None, None)

    def test_parses_all_member_kinds(self):
        kit = parse_kit(self._kit(), kit_path="/x/TAB_TEST.zip", system="SIHSUS")
        assert set(kit.cnvs) == {"SEXO.CNV"}
        assert set(kit.defs) == {"RD.DEF"}
        assert kit.code_tables["CID10"] == [("A00", "Colera", {})]

    def test_entries_bindings_and_rules(self):
        kit = parse_kit(self._kit(), kit_path="/x/TAB_TEST.zip", system="SIHSUS")
        entries, bindings, _rules = entries_from_kit(kit)
        assert {e.value_group for e in entries} == {"SEXO", "CID10"}
        assert all(e.field_name is None for e in entries)  # codelists, not columns
        assert ("SEXO", "SEXO") in {(b.field_name, b.codelist) for b in bindings}

    def test_persist_then_lookup_through_the_binding(self, catalog: Catalog):
        kit = parse_kit(self._kit(), kit_path="/x/TAB_TEST.zip", system="SIHSUS")
        entries, bindings, _ = entries_from_kit(kit)
        persist_kit(catalog, kit)
        persist_entries(catalog, entries)
        persist_bindings(catalog, bindings)
        assert codelists_for(catalog, system="SIHSUS", field_name="SEXO") == ["SEXO"]
        labels = lookup(catalog, system="SIHSUS", field_name="SEXO")
        assert labels["1"] == "Masculino" and labels["2"] == "Feminino"


class TestDictionaryMerge:
    def test_conflicting_claims_are_recorded_not_resolved(self, catalog: Catalog):
        from pegasus_data.semantics.dictionary import DictionaryEntry

        a = DictionaryEntry(
            system="SIHSUS", value_raw="1", value_label="Masculino", source="cnv",
            source_ref="kitA!SEXO.CNV:2", confidence=0.95, value_group="SEXO",
        )
        b = DictionaryEntry(
            system="SIHSUS", value_raw="1", value_label="Homem", source="pdf",
            source_ref="doc.pdf", confidence=0.5, value_group="SEXO",
        )
        persist_entries(catalog, [a])
        result = persist_entries(catalog, [b])
        assert result["conflicts"] == 1
        # The higher-authority claim stands; the disagreement is on record.
        conflict = catalog.query("SELECT claim_a, claim_b FROM dictionary_conflicts")[0]
        assert {conflict["claim_a"], conflict["claim_b"]} == {"Masculino", "Homem"}

    def test_different_eras_coexist_without_conflict(self, catalog: Catalog):
        from pegasus_data.semantics.dictionary import DictionaryEntry

        old = DictionaryEntry(
            system="SIHSUS", value_raw="530010", value_label="Brasilia", source="cnv",
            source_ref="old!MUNICBR.CNV:1", confidence=0.95, value_group="MUNICBR",
            valid_from="199201", valid_to="199712",
        )
        new = DictionaryEntry(
            system="SIHSUS", value_raw="530010", value_label="Brasília", source="cnv",
            source_ref="new!MUNICBR.CNV:1", confidence=0.95, value_group="MUNICBR",
        )
        persist_entries(catalog, [old])
        result = persist_entries(catalog, [new])
        assert result["conflicts"] == 0
        assert catalog.count("dictionary") == 2

    def test_granular_codelist_beats_a_specialised_subset(self, catalog: Catalog):
        from pegasus_data.semantics.dictionary import DictionaryEntry

        broad = [
            DictionaryEntry(
                system="S", value_raw=f"{i:06d}", value_label=f"Municipio {i}", source="cnv",
                source_ref="x", confidence=0.95, value_group="MUNICBR",
            )
            for i in range(50)
        ]
        narrow = [
            DictionaryEntry(
                system="S", value_raw=f"{i:06d}", value_label=f"Regiao {i}", source="cnv",
                source_ref="x", confidence=0.95, value_group="DISTRFEDERAL",
            )
            for i in range(3)
        ]
        persist_entries(catalog, broad + narrow)
        observed = {f"{i:06d}": 100 for i in range(50)}
        chosen = most_granular_codelist(
            catalog, ["MUNICBR", "DISTRFEDERAL"], system="S", observed=observed
        )
        assert chosen == "MUNICBR"


class TestLedger:
    def test_incremento_makes_a_field_additive(self, catalog: Catalog):
        from pegasus_data.semantics.ledger import build_ledger, persist_ledger

        catalog.executemany(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) VALUES (?,?,?,?,?)",
            [("F1", "SIHSUS", "RD", "sig1", 2)],
        )
        catalog.executemany(
            """INSERT INTO variable_profiles (family_id, field_name, schema_signature, semantic_type,
               semantic_confidence, distinct_count) VALUES (?,?,?,?,?,?)""",
            [
                ("F1", "VAL_TOT", "sig1", "money", 0.9, 500),
                ("F1", "DIAG_PRINC", "sig1", "icd10", 0.8, 400),
            ],
        )
        catalog.executemany(
            """INSERT INTO def_variables (def_path, system, usage, display_name, field_name, line_no)
               VALUES (?,?,?,?,?,?)""",
            [("d", "SIHSUS", "I", "Valor Total", "VAL_TOT", 1)],
        )
        entries = build_ledger(catalog)
        persist_ledger(catalog, entries)
        by_field = {e.field_name: e for e in entries}
        assert by_field["VAL_TOT"].aggregation == "additive"
        assert by_field["VAL_TOT"].official_name == "Valor Total"
        # A diagnosis code is never summable, whatever its distribution looks like.
        assert by_field["DIAG_PRINC"].aggregation == "non_summable"

    def test_sentinels_come_from_the_field_not_a_global_rule(self, catalog: Catalog):
        from pegasus_data.semantics.dictionary import DictionaryEntry
        from pegasus_data.semantics.ledger import _sentinels_for

        persist_entries(
            catalog,
            [
                DictionaryEntry(
                    system="S", value_raw="9", value_label="Ignorado", source="cnv",
                    source_ref="x", confidence=0.95, value_group="SEXO",
                ),
                DictionaryEntry(
                    system="S", value_raw="9", value_label="Nove anos", source="cnv",
                    source_ref="x", confidence=0.95, value_group="ESCOLARIDADE",
                ),
            ],
        )
        from pegasus_data.semantics.dictionary import CodelistBinding

        persist_bindings(
            catalog,
            [
                CodelistBinding("S", "SEXO", "SEXO", "def", "x", 0.9),
                CodelistBinding("S", "ESCOLARIDADE", "ESCOLARIDADE", "def", "x", 0.9),
            ],
        )
        assert _sentinels_for(catalog, "S", "SEXO") == ["9"]
        assert _sentinels_for(catalog, "S", "ESCOLARIDADE") == []


@pytest.mark.parametrize(
    ("codes", "expected"),
    [(["0-9"], 10), (["1"], 1), (["2,3"], 2)],
)
def test_expansion_counts(codes, expected):
    total = 0
    for expression in codes:
        got, _ = expand_expression(expression, width=1)
        total += len(got)
    assert total == expected


class TestPdfHarvest:
    """The lowest-authority source, and the one most able to inject noise."""

    LAYOUT = """
    Dicionario de dados - SIHSUS
    SEXO         1  C  Sexo do paciente
    SEXO:
    1 - Masculino
    3 - Feminino
    IDADE        3  N  Idade
    """

    DECREE = """
    O MINISTRO DE ESTADO DA SAUDE, no uso de suas atribuicoes,
    RESOLVE:
    I - A vigilancia das doencas transmissiveis;
    II - Coordenacao nacional das acoes;
    III - Execucao das acoes de Vigilancia em Saude;
    """

    def _harvest(self, monkeypatch, text: str, known):
        from pegasus_data.semantics import pdf_harvest

        monkeypatch.setattr(pdf_harvest, "extract_text", lambda data: iter([text]))
        return pdf_harvest.harvest_pdf(b"%PDF-", source_ref="/x/doc.pdf", known_fields=known)

    def test_reads_a_real_layout_table(self, monkeypatch):
        result = self._harvest(monkeypatch, self.LAYOUT, ["SEXO", "IDADE"])
        assert result.field_descriptions["SEXO"].startswith("Sexo do paciente")
        assert ("SEXO", "1", "Masculino") in result.value_labels
        assert ("SEXO", "3", "Feminino") in result.value_labels

    def test_a_decree_yields_nothing(self, monkeypatch):
        """Roman numerals in prose are not codes, however well-provenanced."""
        result = self._harvest(monkeypatch, self.DECREE, ["SEXO", "IDADE"])
        assert result.is_empty
        assert result.rejected >= 1

    def test_unknown_fields_are_refused(self, monkeypatch):
        """A PDF can only inform us about columns the catalog has actually seen."""
        result = self._harvest(monkeypatch, self.LAYOUT, ["OTHER_FIELD"])
        assert result.is_empty
        assert result.rejected >= 1

    def test_entries_are_lowest_authority(self, monkeypatch):
        from pegasus_data.semantics.pdf_harvest import entries_from_harvest

        result = self._harvest(monkeypatch, self.LAYOUT, ["SEXO", "IDADE"])
        entries = entries_from_harvest(result, system="SIHSUS")
        assert entries and all(e.source == "pdf" for e in entries)
        assert all(e.confidence < 0.6 for e in entries)
        assert all(e.authority > 0 for e in entries)

    def test_a_cnv_claim_beats_a_pdf_claim(self, catalog: Catalog, monkeypatch):
        from pegasus_data.semantics.dictionary import DictionaryEntry

        persist_entries(
            catalog,
            [
                DictionaryEntry(
                    system="SIHSUS", value_raw="1", value_label="Masculino", source="cnv",
                    source_ref="kit!SEXO.CNV:2", confidence=0.95, field_name="SEXO",
                )
            ],
        )
        result = persist_entries(
            catalog,
            [
                DictionaryEntry(
                    system="SIHSUS", value_raw="1", value_label="Homem", source="pdf",
                    source_ref="/x/doc.pdf", confidence=0.5, field_name="SEXO",
                )
            ],
        )
        assert result["conflicts"] == 1
        stored = catalog.query("SELECT value_label, source FROM dictionary WHERE value_raw='1'")[0]
        assert stored["value_label"] == "Masculino" and stored["source"] == "cnv"
