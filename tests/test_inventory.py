"""Filename grammar, date-convention inference, strata and families (D2, D3)."""

from __future__ import annotations

import pytest

from pegasus_data.inventory.families import (
    Family,
    family_id_for,
    schema_signature,
)
from pegasus_data.inventory.naming import (
    apply_convention,
    infer_date_convention,
    infer_two_digit_epoch,
    parse_filename,
    role_from_path,
    strip_container_suffixes,
    system_from_path,
)
from pegasus_data.inventory.strata import build_strata


class TestFilenameGrammar:
    @pytest.mark.parametrize(
        ("filename", "prefix", "geo", "date"),
        [
            ("RDAL2401.dbc", "RD", "AL", "2401"),
            ("DOAL2001.dbc", "DO", "AL", "2001"),
            ("RDAC9201.dbc", "RD", "AC", "9201"),
            ("ACAC0202.EXE", "AC", "AC", "0202"),      # APAC table + UF + competência
            ("DENGBR20.csv.zip", "DENG", "BR", "20"),  # Dados_Abertos is classic
        ],
    )
    def test_classic_convention(self, filename, prefix, geo, date):
        parsed = parse_filename(filename)
        assert (parsed.series_prefix, parsed.geo_code, parsed.date_code) == (prefix, geo, date)

    def test_composite_suffix_is_what_defeated_the_prior_parser(self):
        """The 82 'UNPARSED' Dados_Abertos families were a suffix bug, not a grammar."""
        stem, suffix, container = strip_container_suffixes("DENGBR20.csv.zip")
        assert (stem, suffix, container) == ("DENGBR20", ".csv.zip", "zip")
        assert parse_filename("DENGBR20.csv.zip").grammar == "classic"

    def test_descriptive_tail_has_its_own_grammar(self):
        assert parse_filename("siasus_pa_ac.duck").grammar == "descriptive_uf"
        assert parse_filename("apac_atd.duck.zip").grammar == "descriptive"

    def test_geo_token_outside_the_closed_set_is_rejected(self):
        parsed = parse_filename("XXZZ2401.dbc")
        assert parsed.geo_code is None

    def test_system_from_path(self):
        assert system_from_path("/dissemin/publicos/SIHSUS/200801_/Dados/RDAL2401.dbc") == "SIHSUS"

    @pytest.mark.parametrize(
        ("path", "role"),
        [
            ("/dissemin/publicos/PNI/AUXILIARES/ANO.CNV", "dictionary"),
            ("/dissemin/publicos/SIHSUS/200801_/Auxiliar/TAB_SIH.zip", "dictionary"),
            ("/dissemin/publicos/SIM/Doc/manual.pdf", "documentation"),
            ("/dissemin/publicos/SIHSUS/200801_/Dados/RDAL2401.dbc", "data"),
            # .exe is data: excluding it by extension is exactly defect D1.
            ("/dissemin/publicos/SIASUS/APAC/2002/acac0202.exe", "data"),
        ],
    )
    def test_role_never_excludes_a_data_file(self, path, role):
        assert role_from_path(path) == role


class TestDateConvention:
    def test_monthly_directory(self):
        codes = [f"20{m:02d}" for m in range(1, 13)]
        keys = [("RD", "AL")] * 12
        assert infer_date_convention(codes, group_keys=keys) == "monthly"

    def test_annual_directory(self):
        codes = ["1996", "1997", "2001", "2013", "2023"]
        keys = [("DO", "AL")] * 5
        assert infer_date_convention(codes, group_keys=keys) == "annual"

    def test_multiplicity_decides_the_genuinely_ambiguous_case(self):
        """Same (series, geo, century) more than once means months, not years."""
        codes = ["2001", "2002", "2003"]
        assert infer_date_convention(codes, group_keys=[("RD", "AL")] * 3) == "monthly"
        assert (
            infer_date_convention(codes, group_keys=[("DO", "AL"), ("DO", "BA"), ("DO", "CE")])
            == "annual"
        )

    def test_the_case_the_brief_calls_undecidable(self):
        parsed = parse_filename("RDAL2001.dbc")
        assert apply_convention(parsed, "monthly").normalized_date == 202001
        assert apply_convention(parse_filename("DOAL2001.dbc"), "annual").year == 2001

    def test_ambiguous_leaves_the_year_null_rather_than_guessing(self):
        parsed = apply_convention(parse_filename("DOAL2001.dbc"), "ambiguous")
        assert parsed.year is None
        assert parsed.date_format == "ambiguous"

    def test_two_digit_epoch_is_inferred_from_contiguity(self):
        """IBGE/projpop runs PROJUF00…PROJUF70 — projections to 2070, not to 1970."""
        assert infer_two_digit_epoch([f"{i:02d}" for i in range(71)]) == "century_2000"
        assert infer_two_digit_epoch(["96", "97", "98", "99", "00", "23"]) == "pivot"
        parsed = apply_convention(parse_filename("PROJUF70.dbf"), "annual", epoch="century_2000")
        assert parsed.year == 2070


class TestStrata:
    def test_grouped_by_system_series_year(self):
        rows = [
            {"path": "/x/RDAL2401.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2024},
            {"path": "/x/RDAL2402.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2024},
            {"path": "/x/RDBA2401.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2024},
            {"path": "/x/RDAL9201.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 1992},
        ]
        strata = build_strata(rows)
        assert len(strata) == 2, "schema varies with time and system, not with state or month"
        by_year = {s.year: s for s in strata}
        assert by_year[2024].file_count == 3
        assert by_year[1992].file_count == 1

    def test_undated_files_still_get_a_stratum(self):
        rows = [{"path": "/x/weird.dbc", "system": "X", "series_prefix": None, "year": None}]
        strata = build_strata(rows)
        assert len(strata) == 1 and strata[0].year is None

    def test_sample_is_deterministic(self):
        rows = [
            {"path": p, "system": "S", "series_prefix": "A", "year": 2020}
            for p in ["/x/c.dbc", "/x/a.dbc", "/x/b.dbc"]
        ]
        assert build_strata(rows)[0].sample_path() == "/x/a.dbc"


class TestFamilies:
    def test_signature_depends_on_order(self):
        assert schema_signature(["A", "B"]) != schema_signature(["B", "A"])
        assert schema_signature(["a", "b"]) == schema_signature(["A", "B"])

    def test_family_id_is_derivable_before_families_are_built(self):
        sig = schema_signature(["A", "B"])
        assert family_id_for("SIHSUS", "RD", sig) == f"SIHSUS_RD_{sig[:10]}"

    def test_format_is_an_attribute_not_part_of_the_key(self):
        """The same records in four containers are one family (D3)."""
        sig = schema_signature(["A", "B"])
        family = Family(system="SIHSUS", series="RD", schema_signature=sig, field_count=2)
        family.paths = [("/x/a.dbc", ""), ("/x/a.dbf", ""), ("/x/a.xml", ""), ("/x/a.csv", "")]
        family.formats = {"dbc": 1, "dbf": 1, "xml": 1, "csv": 1}
        assert family.preferred_representation() == "csv", "cheapest to decode wins"

    def test_different_fields_cannot_collapse(self):
        assert schema_signature(["A", "B"]) != schema_signature(["A", "B", "C"])


class TestConventionOutliers:
    """One odd file must not redefine a directory of 22,807."""

    def test_a_single_annual_bundle_does_not_flip_a_monthly_directory(self):
        # Measured: SIHSUS/200801_/Dados holds monthly files plus one annual
        # bundle, RDAC2017.zip. Treating any out-of-range tail as proof of an
        # annual directory dated CHBR1901.dbc to the year 1901.
        codes = [f"{yy:02d}{mm:02d}" for yy in range(8, 27) for mm in range(1, 13)]
        keys = [("RD", "AC")] * len(codes)
        codes.append("2017")
        keys.append(("RD", "AC"))
        assert infer_date_convention(codes, group_keys=keys) == "monthly"

    def test_the_outlier_itself_is_left_undated(self):
        parsed = apply_convention(parse_filename("RDAC2017.zip"), "monthly")
        assert parsed.year is None
        assert parsed.date_format == "ambiguous"

    def test_its_neighbours_are_dated_correctly(self):
        parsed = apply_convention(parse_filename("CHBR1901.dbc"), "monthly")
        assert parsed.year == 2019
        assert parsed.normalized_date == 201901

    def test_a_genuinely_annual_directory_is_still_annual(self):
        codes = ["1996", "1997", "2001", "2013", "2020", "2023"]
        assert infer_date_convention(codes, group_keys=[("DO", "AL")] * 6) == "annual"


class TestStrataIdempotence:
    """Re-running inventory must replace derived state, not accumulate it."""

    def _persist(self, catalog, rows):
        from pegasus_data.inventory.strata import build_strata, persist_strata, prune_orphan_strata

        strata = build_strata(rows)
        prune_orphan_strata(catalog, {s.stratum_id for s in strata})
        persist_strata(catalog, strata)
        return strata

    def test_membership_is_replaced_when_a_file_changes_stratum(self, catalog):
        # A date correction moves RDAC2008 from the 2008 stratum to 2020.
        before = [
            {"path": "/x/RDAC2008.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2008},
        ]
        after = [
            {"path": "/x/RDAC2008.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2020},
            {"path": "/x/RDAC0801.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2008},
        ]
        self._persist(catalog, before)
        self._persist(catalog, after)
        members = {
            (r["stratum_id"], r["path"])
            for r in catalog.query("SELECT stratum_id, path FROM stratum_members")
        }
        by_year = {
            r["year"]: r["stratum_id"]
            for r in catalog.query("SELECT year, stratum_id FROM strata")
        }
        assert (by_year[2008], "/x/RDAC2008.dbc") not in members, "the stale membership survived"
        assert (by_year[2020], "/x/RDAC2008.dbc") in members
        assert (by_year[2008], "/x/RDAC0801.dbc") in members

    def test_a_stale_sample_is_invalidated_not_inherited(self, catalog):
        """A stratum whose sample moved away must re-derive its schema."""
        self._persist(
            catalog,
            [{"path": "/x/RDAC2008.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2008}],
        )
        catalog.execute(
            "UPDATE strata SET schema_signature='sig113', field_count=113, sample_status='ok'"
        )
        catalog.conn.commit()
        self._persist(
            catalog,
            [
                {"path": "/x/RDAC2008.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2020},
                {"path": "/x/RDAC0801.dbc", "system": "SIHSUS", "series_prefix": "RD", "year": 2008},
            ],
        )
        row = catalog.query("SELECT * FROM strata WHERE year = 2008")[0]
        assert row["schema_signature"] is None
        assert row["sample_status"] == "pending"
        assert row["sampled_path"] == "/x/RDAC0801.dbc"

    def test_orphan_strata_are_pruned(self, catalog):
        self._persist(
            catalog,
            [{"path": "/x/a.dbc", "system": "S", "series_prefix": "A", "year": 1901}],
        )
        assert catalog.count("strata") == 1
        self._persist(
            catalog,
            [{"path": "/x/a.dbc", "system": "S", "series_prefix": "A", "year": 2019}],
        )
        rows = catalog.query("SELECT year FROM strata")
        assert [r["year"] for r in rows] == [2019]
