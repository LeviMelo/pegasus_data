"""The portable map of DATASUS.

What this file protects is the *shape* of the answer. A compendium exists to be
opened by someone deciding whether DATASUS can answer their question at all,
usually before anything is downloaded — so the core has to carry coverage,
meaning and schema change, and it has to stay small enough to send in an email.

The artefact this replaces got that backwards: 57 MB, of which the bulk was
124,810 rows of raw file listing and per-file percentiles, while carrying no
descriptions at all. Every test here is a guard against drifting back.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.compendium import compendium
from pegasus_data.config import Settings


def _seed(catalog: Catalog) -> None:
    """A minimal SIH-shaped catalog: two generations, two states, two years."""
    sig_a, sig_b = "a" * 64, "b" * 64
    catalog.upsert_files(
        [
            {"path": f"/dissemin/publicos/SIHSUS/RD{uf}{yy}01.dbc", "directory": "/d",
             "filename": f"RD{uf}{yy}01.dbc", "extension": ".dbc", "size": 100}
            for uf in ("AC", "AL")
            for yy in ("22", "23")
        ]
    )
    for uf in ("AC", "AL"):
        for yy, year, sig in (("22", 2022, sig_a), ("23", 2023, sig_b)):
            catalog.execute(
                "INSERT OR REPLACE INTO file_facts (path, system, series_prefix, geo_code,"
                " year, role) VALUES (?,?,?,?,?,?)",
                (f"/dissemin/publicos/SIHSUS/RD{uf}{yy}01.dbc", "SIHSUS", "RD", uf, year, "data"),
            )
    for sig, year, fields in ((sig_a, 2022, ["N_AIH", "SEXO"]), (sig_b, 2023, ["N_AIH", "SEXO", "IDADE"])):
        catalog.execute(
            "INSERT OR REPLACE INTO strata (stratum_id, system, series, year,"
            " schema_signature, file_count) VALUES (?,?,?,?,?,?)",
            (f"s{year}", "SIHSUS", "RD", year, sig, 2),
        )
        catalog.execute(
            "INSERT OR REPLACE INTO families (family_id, system, series, schema_signature,"
            " field_count, time_min, time_max, file_count) VALUES (?,?,?,?,?,?,?,?)",
            (f"f{year}", "SIHSUS", "RD", sig, len(fields), year, year, 2),
        )
        for order, name in enumerate(fields):
            catalog.execute(
                "INSERT INTO schema_presence (schema_signature, field_name, field_order)"
                " VALUES (?,?,?)",
                (sig, name, order),
            )
    catalog.execute(
        "INSERT INTO variable_docs (system, field_name, description, translated_name,"
        " code_system, source) VALUES (?,?,?,?,?,?)",
        ("SIHSUS", "SEXO", "Patient sex as recorded on the admission form.", "Sex",
         "internal", "manual"),
    )


@pytest.fixture
def seeded(settings: Settings) -> Settings:
    store = Catalog(settings.catalog_path)
    try:
        _seed(store)
    finally:
        store.close()
    return settings


def _open(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


class TestItAnswersThePlanningQuestions:
    def test_it_says_which_years_and_states_exist(self, seeded, tmp_path) -> None:
        """The feasibility question, and the one the old artefact could not answer."""
        out = tmp_path / "c.sqlite"
        compendium(out, settings=seeded)
        conn = _open(out)
        rows = {
            (r["year"], r["uf"]): r["files"]
            for r in conn.execute("SELECT year, uf, files FROM coverage WHERE dataset='SIH.RD'")
        }
        assert rows == {(2022, "AC"): 1, (2022, "AL"): 1, (2023, "AC"): 1, (2023, "AL"): 1}

    def test_it_says_when_the_columns_changed(self, seeded, tmp_path) -> None:
        """"113 columns" is not useful; "+1 IDADE at this boundary" decides a design."""
        out = tmp_path / "c.sqlite"
        compendium(out, settings=seeded)
        conn = _open(out)
        gens = list(
            conn.execute(
                "SELECT year_min, field_count, added FROM schema_generations"
                " WHERE dataset='SIH.RD' ORDER BY year_min"
            )
        )
        assert [g["field_count"] for g in gens] == [2, 3]
        assert json.loads(gens[1]["added"]) == ["IDADE"]

    def test_it_carries_meaning_not_just_structure(self, seeded, tmp_path) -> None:
        """The old compendium had no descriptions at all — only guessed types."""
        out = tmp_path / "c.sqlite"
        compendium(out, settings=seeded)
        conn = _open(out)
        row = conn.execute(
            "SELECT description, translated_name FROM variables"
            " WHERE system='SIHSUS' AND name='SEXO'"
        ).fetchone()
        assert "sex" in (row["description"] or "").lower()
        assert row["translated_name"] == "Sex"

    def test_a_dataset_knows_what_one_row_is(self, seeded, tmp_path) -> None:
        """Resolved through the ontology: the row says SIHSUS_RD, the code is SIH.RD."""
        out = tmp_path / "c.sqlite"
        compendium(out, settings=seeded)
        conn = _open(out)
        row = conn.execute("SELECT code, system FROM datasets WHERE code='SIH.RD'").fetchone()
        assert row is not None and row["system"] == "SIH"


class TestTheTogglesAreTheDesign:
    def test_the_core_carries_no_codes(self, seeded, tmp_path) -> None:
        out = tmp_path / "c.sqlite"
        report = compendium(out, settings=seeded)
        conn = _open(out)
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "codes" not in tables
        assert "codes" in report.skipped

    def test_asking_for_files_adds_them(self, seeded, tmp_path) -> None:
        out = tmp_path / "c.sqlite"
        report = compendium(out, files=True, settings=seeded)
        assert report.rows["files"] == 4
        conn = _open(out)
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 4

    def test_an_unknown_scope_suggests_rather_than_empties(self, seeded, tmp_path) -> None:
        """Scoping to a typo must not quietly produce an empty file."""
        with pytest.raises(ValueError, match="Did you mean"):
            compendium(tmp_path / "c.sqlite", systems=["SIHH"], settings=seeded)

    def test_a_bad_codes_mode_is_refused(self, seeded, tmp_path) -> None:
        with pytest.raises(ValueError, match="codes must be"):
            compendium(tmp_path / "c.sqlite", codes="everything", settings=seeded)


class TestItSaysWhatItIs:
    def test_meta_records_the_options_it_was_built_with(self, seeded, tmp_path) -> None:
        """A file someone emails you has to be placeable in time and scope."""
        out = tmp_path / "c.sqlite"
        compendium(out, files=True, settings=seeded)
        conn = _open(out)
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
        assert "generated_at" in meta
        assert json.loads(meta["options"])["files"] is True

    def test_it_carries_what_is_not_known(self, seeded, tmp_path) -> None:
        """Open questions travel with the map, rather than being left behind."""
        out = tmp_path / "c.sqlite"
        compendium(out, settings=seeded)
        conn = _open(out)
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "open_questions" in tables
