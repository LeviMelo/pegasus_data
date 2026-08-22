"""How datasets join, declared as keys rather than guessed by every script.

This knowledge already existed as prose inside gotchas — "Joins to SIH.RD on the
AIH number", "Only meaningful joined to CNES.ST on the CNES code and
competência". A human reading the docs could find it; nothing else could, and a
research group asked for join primitives because they could not.

The two things a declaration has to carry, or it is worse than nothing:

``rows_per_key``
    SIH.RD is one row per AIH and SIH.SP is many. Join them and count rows and
    you have counted professional acts while believing you counted admissions.

``as_of``
    CNES is versioned by competence. Joining a 2015 admission to today's CNES
    answers what the hospital is now, not what it was when the patient was
    treated, and nothing about the result says so.
"""

from __future__ import annotations

from pegasus_data.ontology import Ontology


class TestTheKeysAreDeclared:
    def test_the_aih_key_names_both_spellings(self) -> None:
        """SIH.RD calls it N_AIH and SIH.SP calls it SP_NAIH."""
        keys = Ontology.load().keys
        assert keys["AIH"].column_for("SIH.RD") == "N_AIH"
        assert keys["AIH"].column_for("SIH.SP") == "SP_NAIH"

    def test_sia_names_the_cnes_code_differently(self) -> None:
        """PA_CODUNI is the CNES code. This is what the file exists to say."""
        keys = Ontology.load().keys
        assert keys["CNES"].column_for("SIA.PA") == "PA_CODUNI"
        assert keys["CNES"].column_for("CNES.ST") == "CNES"

    def test_a_dataset_lists_every_key_it_participates_in(self) -> None:
        names = {k.name for k in Ontology.load().keys_of("SIH.RD")}
        assert names == {"AIH", "CNES"}

    def test_a_dataset_in_no_key_gets_an_empty_list(self) -> None:
        assert Ontology.load().keys_of("SIM.DO") == []


class TestTheGrainIsCarried:
    def test_the_fan_out_side_is_flagged(self) -> None:
        """The one fact that stops a join from silently multiplying a count."""
        keys = Ontology.load().keys
        assert "SIH.SP" in keys["AIH"].fans_out()
        assert "SIH.RD" not in keys["AIH"].fans_out()

    def test_the_hub_of_the_cnes_key_is_one_row_per_key(self) -> None:
        cnes = Ontology.load().keys["CNES"]
        hub = next(m for m in cnes.members if m.dataset == "CNES.ST")
        assert hub.rows_per_key == "one"

    def test_an_unmeasured_grain_says_so_rather_than_guessing(self) -> None:
        apac = Ontology.load().keys["APAC"]
        assert all(m.rows_per_key == "unmeasured" for m in apac.members)
        assert apac.fans_out() == []


class TestTimeVersionedKeys:
    def test_cnes_is_marked_as_of_competence(self) -> None:
        assert Ontology.load().keys["CNES"].as_of == "competence"

    def test_a_stable_key_is_not(self) -> None:
        assert Ontology.load().keys["AIH"].as_of is None


class TestWhatIsNotEstablished:
    def test_the_siscan_patient_join_is_recorded_as_absent(self) -> None:
        """CO_PACIENTE exists only in SISCAN.PACNT, not in any exam dataset.

        Asserting this join would produce a cohort rather than an error, so the
        finding is recorded instead of the join.
        """
        found = [u for u in Ontology.load().unestablished if "SISCAN" in (u.finding or "")]
        assert found and "CO_PACIENTE" in (found[0].proposed_key or "")

    def test_record_linkage_is_named_and_excluded(self) -> None:
        wants = " ".join(u.want + " " + (u.finding or "") for u in Ontology.load().unestablished)
        assert "SINASC" in wants
        assert "re-identification" in wants or "linkage" in wants


class TestInfoShowsThem:
    def test_a_dataset_reports_how_it_joins(self, tmp_path) -> None:
        from pegasus_data._info import Info

        info = Info(kind="dataset", code="SIH.RD", joins=[
            {"key": "AIH", "column": "N_AIH", "as_of": None, "rows_per_key": "one",
             "with": [{"dataset": "SIH.SP", "column": "SP_NAIH", "rows_per_key": "many"}],
             "caveats": []},
        ])
        text = repr(info)
        assert "joins via" in text
        assert "AIH on N_AIH" in text
        assert "one row per key" in text
        assert "SIH.SP.SP_NAIH" in text

    def test_an_as_of_key_is_marked_in_the_output(self) -> None:
        from pegasus_data._info import Info

        info = Info(kind="dataset", code="SIH.RD", joins=[
            {"key": "CNES", "column": "CNES", "as_of": "competence",
             "rows_per_key": "many", "with": [], "caveats": []},
        ])
        assert "AS-OF competence" in repr(info)
