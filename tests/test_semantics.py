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
    supersede_source,
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


class TestUnrecognisedLookups:
    """A lookup table outside the known set is inferred, and says that it was."""

    def _kit_with_odd_lookup(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("SEXO.CNV", SEXO_CNV)
            # Columns deliberately ordered label-first, so "first two columns"
            # would take the description as the code.
            z.writestr(
                "WEIRDTAB.DBF",
                make_dbf(
                    [("DESCRICAO", "C", 30, 0), ("COD", "C", 4, 0), ("UF", "C", 2, 0)],
                    [
                        ["Hospital municipal central", "0001", "AL"],
                        ["Unidade basica de saude norte", "0002", "AL"],
                        ["Pronto socorro regional", "0003", "BA"],
                    ],
                ),
            )
        return buf.getvalue()

    def test_columns_are_inferred_not_positional(self):
        kit = parse_kit(self._kit_with_odd_lookup(), kit_path="/x/TAB_X.zip", system="S")
        assert kit.guessed_columns["WEIRDTAB"] == ("COD", "DESCRICAO")
        codes = {code for code, _label, _extra in kit.code_tables["WEIRDTAB"]}
        assert codes == {"0001", "0002", "0003"}

    def test_inferred_columns_lower_the_confidence_and_are_named(self):
        kit = parse_kit(self._kit_with_odd_lookup(), kit_path="/x/TAB_X.zip", system="S")
        entries, _bindings, _rules = entries_from_kit(kit)
        weird = [e for e in entries if e.value_group == "WEIRDTAB"]
        assert weird and all(e.confidence < 0.9 for e in weird)
        assert all("columns inferred" in e.source_ref for e in weird)

    def test_a_known_table_keeps_full_confidence(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(
                "CID10.DBF",
                make_dbf([("CID10", "C", 4, 0), ("DESCR", "C", 20, 0)], [["A00", "Colera"]]),
            )
        kit = parse_kit(buf.getvalue(), kit_path="/x/TAB_Y.zip", system="S")
        assert "CID10" not in kit.guessed_columns
        entries, _b, _r = entries_from_kit(kit)
        assert all(e.confidence >= 0.9 for e in entries if e.value_group == "CID10")


class TestLookupColumnInference:
    """Picking the code and label columns of an unrecognised DBF lookup.

    Both failures pinned here were found on real DATASUS tables, and they pull in
    opposite directions — which is why the rule is a gate plus a score rather
    than one weighted formula.
    """

    def _table(self, columns: dict[str, list[object]]):
        import pyarrow as pa

        return pa.table(columns)

    def test_a_mostly_blank_column_is_not_the_label(self):
        """CADMUN's OBSERV is a 50-char field, blank for 5,517 of 5,652 rows.

        Scoring on mean length after dropping blanks made it look like the most
        descriptive column in the table, and the municipality register decoded no
        municipalities.
        """
        from pegasus_data.semantics.tabkit import _infer_code_and_label

        table = self._table({
            "MUNCOD": [f"1100{i:02d}" for i in range(20)],
            "MUNNOME": [f"Cidade Numero {i}" for i in range(20)],
            "OBSERV": [None] * 19 + ["uma observacao bastante longa aqui"],
        })
        assert _infer_code_and_label(table) == ("MUNCOD", "MUNNOME")

    def test_a_sparse_unique_column_is_not_the_key(self):
        """CADMUN's MUNSIAFI is unique among the rows it has and absent from most."""
        from pegasus_data.semantics.tabkit import _infer_code_and_label

        table = self._table({
            "MUNCOD": [f"1100{i:02d}" for i in range(20)],
            "MUNSIAFI": [f"{i:04d}" for i in range(5)] + [None] * 15,
            "MUNNOME": [f"Cidade Numero {i}" for i in range(20)],
        })
        code, _label = _infer_code_and_label(table)
        assert code == "MUNCOD"

    def test_prose_is_never_the_key_however_unique_it_is(self):
        """TABOCUP: 3,564 occupation names, 99.9% unique; CODIGO repeats.

        Any score led by uniqueness picks the description as the code and files
        the code as its label — exactly backwards.
        """
        from pegasus_data.semantics.tabkit import _infer_code_and_label

        table = self._table({
            "CODIGO": [f"{i // 4:03d}" for i in range(40)],
            "DESCRICAO": [f"OCUPACAO DISTINTA NUMERO {i}" for i in range(40)],
        })
        assert _infer_code_and_label(table) == ("CODIGO", "DESCRICAO")

    def test_a_table_of_only_prose_still_answers(self):
        """The gate must not empty the candidate set."""
        from pegasus_data.semantics.tabkit import _infer_code_and_label

        table = self._table({
            "A": [f"valor com espacos {i}" for i in range(10)],
            "B": [f"outro valor bem mais longo aqui {i}" for i in range(10)],
        })
        assert _infer_code_and_label(table) is not None


class TestALabelCannotBecomeACode:
    """A long label overruns the expression column and is parsed as the code.

    `medico02.CNV` line 11 produced code `'XXXXXX                 vascular'`
    labelled `'MEDICO DE FAMILIA'`. That codelist decodes `CNES.CBOUNICO`, so
    the wrong thing was being matched against real establishment records — and
    it survived because a garbled code simply matches nothing, which looks
    exactly like a code that has no label.

    The expression column is inferred from the file as a whole, so any line
    whose label runs longer than the rest sets this trap. What makes it
    detectable rather than a judgement call is that a TabNet match expression is
    a code, a range or a comma list, and never contains free internal whitespace.
    """

    #: Where the match expressions sit in these fixtures.
    EXPR_COL = 50

    def _line(self, seq: int, label: str, expression: str) -> str:
        prefix = f"{seq:>5} "
        return prefix + label.ljust(self.EXPR_COL - len(prefix)) + expression

    def _cnv(self, *lines: str) -> bytes:
        return ("\n".join(lines) + "\n").encode("latin-1")

    def _medico02(self) -> bytes:
        # Enough well-formed lines for the expression column to be detected at
        # all — it is inferred from the file as a whole, so a two-line fixture
        # never reaches the branch this defends.
        lines = [self._line(i, f"OCUPACAO {i}", f"2251{i:02d}") for i in range(1, 6)]
        # The shape of the real defect: prose sitting past the expression
        # column, with internal whitespace.
        lines.append(self._line(6, "MEDICO DE FAMILIA", "XXXXXX          vascular"))
        return self._cnv("    6      80", *lines)

    def test_a_code_never_contains_whitespace(self):
        """The dangerous form. A code with spaces can match padded data by
        accident, and it reached the dictionary as
        `'XXXXXX                    vascular'` on a codelist decoding
        CNES.CBOUNICO."""
        parsed = parse_cnv_bytes(self._medico02(), name="medico02", source_ref="t")
        spaced = [c.expression for c in parsed.categories if " " in c.expression.strip()]
        assert spaced == [], f"prose survived as a code: {spaced}"

    def test_it_says_which_line_it_had_to_re_split(self):
        parsed = parse_cnv_bytes(self._medico02(), name="medico02", source_ref="t")
        assert any("not a match expression" in w for w in parsed.warnings), parsed.warnings

    def test_an_ordinary_file_is_untouched(self):
        raw = self._cnv(
            "    2      80",
            self._line(1, "Masculino", "1"),
            self._line(2, "Feminino", "3"),
        )
        parsed = parse_cnv_bytes(raw, name="sexo", source_ref="t")
        assert [c.expression for c in parsed.categories] == ["1", "3"]
        assert [c.label for c in parsed.categories] == ["Masculino", "Feminino"]

    def test_ranges_and_lists_still_parse(self):
        """The guard must not reject the expression forms TabNet really uses."""
        raw = self._cnv(
            "    3      80",
            self._line(1, "Faixa um", "1-5"),
            self._line(2, "Faixa dois", "6,7,8"),
            self._line(3, "Capitulo", "A00-B99"),
        )
        parsed = parse_cnv_bytes(raw, name="faixas", source_ref="t")
        assert [c.expression for c in parsed.categories] == ["1-5", "6,7,8", "A00-B99"]


class TestASourceSupersedesItsOwnReading:
    """A source disagreeing with *itself* is a re-reading, not a conflict.

    The dictionary merges claims from many sources by authority, which is right
    — two sources disagreeing is something to record, not overwrite. But nothing
    made a source's newer reading replace its older one, so a parser fix could
    not displace its own stale output.

    TABOCUP is the case: its code and label columns were inferred backwards,
    giving 2,780 rows whose "code" was an occupation description. The inference
    was fixed and the stage re-run — and because the corrected reading produces
    *different* codes, it inserted 406 correct rows beside the 2,868 wrong ones.
    The catalog held both readings of one file with nothing to say which was
    current.
    """

    def _row(self, catalog: Catalog, code: str, label: str, ref: str) -> None:
        catalog.execute(
            "INSERT INTO dictionary (system, value_group, field_name, value_raw, "
            "value_label, source, source_ref, confidence) "
            "VALUES ('SIM','TABOCUP','',?,?,'dbf_lookup',?,0.6)",
            (code, label, ref),
        )

    def test_a_re_read_removes_what_the_same_artifact_said_before(self, catalog: Catalog):
        self._row(catalog, "AUX. DE TEC. DE PECUARIA", "031", "kit.zip!TABOCUP (columns inferred: DESCRICAO->CODIGO)")
        assert supersede_source(catalog, ["kit.zip!TABOCUP"]) == 1
        assert catalog.count("dictionary") == 0

    def test_it_matches_the_artifact_not_the_whole_source_ref(self, catalog: Catalog):
        """The tail says HOW the columns were resolved, and that is exactly what
        changes when a parser improves. Keying on it makes every fix invisible."""
        self._row(catalog, "X", "1", "kit.zip!TABOCUP (columns inferred: DESCRICAO->CODIGO)")
        self._row(catalog, "Y", "2", "kit.zip!TABOCUP (columns inferred: CODIGO->DESCRICAO)")
        supersede_source(catalog, ["kit.zip!TABOCUP"])
        assert catalog.count("dictionary") == 0

    def test_a_different_artifact_is_left_alone(self, catalog: Catalog):
        self._row(catalog, "A", "1", "kit.zip!TABOCUP")
        self._row(catalog, "B", "2", "kit.zip!CID10")
        supersede_source(catalog, ["kit.zip!TABOCUP"])
        rows = catalog.query("SELECT source_ref FROM dictionary")
        assert [r["source_ref"] for r in rows] == ["kit.zip!CID10"]

    def test_a_table_whose_name_merely_starts_the_same_survives(self, catalog: Catalog):
        """TABOCUP must not take TABOCUPACAO with it."""
        self._row(catalog, "A", "1", "kit.zip!TABOCUP")
        self._row(catalog, "B", "2", "kit.zip!TABOCUPACAO")
        supersede_source(catalog, ["kit.zip!TABOCUP"])
        rows = catalog.query("SELECT source_ref FROM dictionary")
        assert [r["source_ref"] for r in rows] == ["kit.zip!TABOCUPACAO"]

    def test_nothing_to_supersede_is_not_an_error(self, catalog: Catalog):
        assert supersede_source(catalog, []) == 0
        assert supersede_source(catalog, ["never-read.zip!X"]) == 0

    def test_it_is_recorded_in_the_event_log(self, catalog: Catalog):
        self._row(catalog, "A", "1", "kit.zip!TABOCUP")
        supersede_source(catalog, ["kit.zip!TABOCUP"])
        assert catalog.count("events", "stage = 'semantics'") >= 1
