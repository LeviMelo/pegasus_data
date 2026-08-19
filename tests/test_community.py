"""Community transcriptions: useful, attributed, and never authoritative.

Some columns are documented nowhere DATASUS publishes — CNES most of all, where
163 columns are categorical and the codings live off the tree. People who work
with these files have written them down, and refusing to read that leaves
columns blank that everyone in the field can already read.

What these tests pin is the price of accepting it: every entry names the repo and
the commit it came from, and no entry can outrank a first-party table. A
transcription without a version is a rumour; one that can overwrite a .CNV is a
liability.
"""

from __future__ import annotations

from pegasus_data.catalog.store import Catalog
from pegasus_data.semantics.dictionary import (
    SOURCE_AUTHORITY,
    DictionaryEntry,
    persist_entries,
)
from pegasus_data.sources.community import (
    CommunitySource,
    entries_from_source,
    ingest,
    parse_r_recodes,
)

SIA_R = r'''
    # PA_FLIDADE
    if ("PA_FLIDADE" %in% variables_names) {
      data <- data %>%
        dplyr::mutate(
          PA_FLIDADE = dplyr::recode_values(
            .data$PA_FLIDADE,
            "0" ~ "IDADE NÃO EXIGIDA",
            "1" ~ "IDADE COMPATIVEL COM O SIGTAP",
            default = .data$PA_FLIDADE
          )
        )
    }

    # PA_SEXO
    if ("PA_SEXO" %in% variables_names) {
      data <- data %>%
        dplyr::mutate(
          PA_SEXO = dplyr::recode_values(
            .data$PA_SEXO,
            "M" ~ "Masculino",
            "F" ~ "Feminino",
            default = .data$PA_SEXO
          )
        )
    }
'''

CASE_MATCH_R = r'''
    if ("TPUPS" %in% variables_names) {
      data <- data %>%
        dplyr::mutate(TPUPS = dplyr::case_match(
          .data$TPUPS,
          "01" = "POSTO DE SAUDE",
          "02" = "CENTRO DE SAÚDE"
        ))
    }
'''


def _source(**files: str) -> CommunitySource:
    return CommunitySource(repo="https://github.com/rfsaldanha/microdatasus",
                           commit="7109ec2c42cf674ba453e0d7a20d2f464890b543", files=files)


class TestParsing:
    def test_it_reads_code_label_pairs(self):
        found = list(parse_r_recodes(SIA_R))
        assert ("PA_SEXO", "M", "Masculino") in found
        assert ("PA_SEXO", "F", "Feminino") in found

    def test_unicode_escapes_become_the_characters_they_name(self):
        """R writes accented Portuguese as \\uXXXX; a raw read gives mojibake."""
        found = {code: label for f, code, label in parse_r_recodes(SIA_R) if f == "PA_FLIDADE"}
        assert found["0"] == "IDADE NÃO EXIGIDA"

    def test_pairs_are_attributed_to_the_field_whose_block_they_sit_in(self):
        """Scanning without the bracketing smears every column's codes onto every other."""
        by_field: dict[str, set[str]] = {}
        for field_name, code, _label in parse_r_recodes(SIA_R):
            by_field.setdefault(field_name, set()).add(code)
        assert by_field["PA_SEXO"] == {"M", "F"}
        assert by_field["PA_FLIDADE"] == {"0", "1"}

    def test_the_case_match_form_is_read_too(self):
        found = list(parse_r_recodes(CASE_MATCH_R))
        assert ("TPUPS", "01", "POSTO DE SAUDE") in found
        assert ("TPUPS", "02", "CENTRO DE SAÚDE") in found

    def test_the_default_arm_is_not_a_value(self):
        """`default = .data$X` is control flow, not a coding."""
        assert all(code != ".data" and not label.startswith(".data")
                   for _f, code, label in parse_r_recodes(SIA_R))

    def test_a_file_with_no_recodes_yields_nothing(self):
        assert list(parse_r_recodes("# just a comment\n")) == []


class TestProvenance:
    def test_every_entry_names_the_repo_the_commit_and_the_file(self):
        entries = entries_from_source(_source(**{"process_sia.R": SIA_R}))
        assert entries
        for entry in entries:
            assert entry.source == "community"
            assert "microdatasus" in entry.source_ref
            assert "7109ec2c42cf" in entry.source_ref, "the commit, not just the repo"
            assert "process_sia.R" in entry.source_ref

    def test_the_file_decides_the_system(self):
        entries = entries_from_source(_source(**{"process_sia.R": SIA_R}))
        assert {e.system for e in entries} == {"SIASUS"}

    def test_an_unknown_file_is_ignored_rather_than_guessed_at(self):
        assert entries_from_source(_source(**{"process_mystery.R": SIA_R})) == []

    def test_systems_can_be_filtered(self):
        source = _source(**{"process_sia.R": SIA_R, "process_cnes.R": CASE_MATCH_R})
        assert {e.system for e in entries_from_source(source, systems=["CNES"])} == {"CNES"}


class TestItCannotOutrankFirstParty:
    def test_community_ranks_below_every_datasus_source(self):
        for first_party in ("cnv", "def", "sigtap", "dbf_lookup", "demas_api", "pdf"):
            assert SOURCE_AUTHORITY[first_party] < SOURCE_AUTHORITY["community"]

    def test_it_still_beats_a_guess(self):
        assert SOURCE_AUTHORITY["community"] < SOURCE_AUTHORITY["inferred"]

    def test_a_cnv_label_survives_a_contradicting_community_one(self, catalog: Catalog):
        """The whole safety argument, exercised rather than asserted."""
        persist_entries(catalog, [
            DictionaryEntry(system="SIASUS", value_raw="M", value_label="Masculino",
                            source="cnv", source_ref="TAB.zip!SEXO.CNV:2",
                            confidence=0.95, value_group="PA_SEXO", field_name="PA_SEXO"),
        ])
        persist_entries(catalog, [
            DictionaryEntry(system="SIASUS", value_raw="M", value_label="WRONG",
                            source="community", source_ref="repo@abc!x.R#PA_SEXO",
                            confidence=0.4, value_group="PA_SEXO", field_name="PA_SEXO"),
        ])
        labels = [
            r["value_label"]
            for r in catalog.query(
                "SELECT value_label FROM dictionary WHERE value_group='PA_SEXO' AND value_raw='M'"
            )
        ]
        assert labels == ["Masculino"], "the .CNV holds; the community reading loses"


class TestIngest:
    def test_it_persists_entries_and_binds_the_fields(self, catalog: Catalog):
        result = ingest(catalog, source=_source(**{"process_sia.R": SIA_R}))
        assert result["pairs"] == 4
        assert catalog.count("dictionary", "source = 'community'") == 4
        bound = {
            r["field_name"]
            for r in catalog.query("SELECT field_name FROM field_codelists WHERE source='community'")
        }
        assert bound == {"PA_SEXO", "PA_FLIDADE"}

    def test_the_binding_carries_the_commit_too(self, catalog: Catalog):
        ingest(catalog, source=_source(**{"process_sia.R": SIA_R}))
        row = catalog.query("SELECT source_ref FROM field_codelists WHERE source='community'")[0]
        assert "7109ec2c42cf" in row["source_ref"]

    def test_reingesting_the_same_commit_is_idempotent(self, catalog: Catalog):
        source = _source(**{"process_sia.R": SIA_R})
        ingest(catalog, source=source)
        ingest(catalog, source=source)
        assert catalog.count("dictionary", "source = 'community'") == 4

    def test_it_reports_what_it_took_from_where(self, catalog: Catalog):
        result = ingest(catalog, source=_source(**{"process_sia.R": SIA_R}))
        assert result["by_system"] == {"SIASUS": 4}
        assert result["commit"].startswith("7109ec2c")
