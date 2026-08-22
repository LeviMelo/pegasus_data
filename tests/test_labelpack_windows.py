"""The shipped pack must be able to answer a historical vintage.

The pack is what makes `fetch(labels=True)` work on a fresh install — the
labels otherwise live only in a catalog nobody has a reason to build. It carried
`(system, codelist, code, label, width)` and no validity window, so the
fallback could not honour `year=1995` even in principle: it returned whatever
row survived, which in practice is the current vintage, and nothing said so.

The warehouse keeps windows apart precisely because the same codelist genuinely
changes meaning across eras. A fallback that cannot express that cannot honour
the same contract.
"""

from __future__ import annotations

import pyarrow.parquet as pq
import pytest

from pegasus_data.labelpack import build_label_pack, covers
from pegasus_data.persist.reference import collecting
from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries


def _seed(catalog):
    """One codelist, two eras, genuinely different labels for the same code."""
    persist_entries(
        catalog,
        [
            DictionaryEntry(
                system="SIHSUS", value_raw="1", value_label="Um antigo",
                source="cnv", source_ref="a:1", confidence=0.95,
                value_group="TESTCL", valid_from="199201", valid_to="199712",
            ),
            DictionaryEntry(
                system="SIHSUS", value_raw="1", value_label="Um moderno",
                source="cnv", source_ref="a:2", confidence=0.95,
                value_group="TESTCL", valid_from="199801", valid_to="202512",
            ),
            DictionaryEntry(
                system="SIHSUS", value_raw="2", value_label="Dois sempre",
                source="cnv", source_ref="a:3", confidence=0.95,
                value_group="TESTCL",
            ),
        ],
    )


class TestTheWindowSurvivesTheBuild:
    def test_the_pack_carries_valid_from_and_valid_to(self, catalog, tmp_path):
        _seed(catalog)
        out = tmp_path / "labels.parquet"
        build_label_pack(catalog, out=out, only_bound=False)
        schema = pq.ParquetFile(out).schema_arrow
        assert "valid_from" in schema.names and "valid_to" in schema.names

    def test_two_eras_of_one_code_stay_two_rows(self, catalog, tmp_path):
        """Collapsing them is the contradiction the warehouse exists to avoid."""
        _seed(catalog)
        out = tmp_path / "labels.parquet"
        build_label_pack(catalog, out=out, only_bound=False)
        table = pq.read_table(out)
        rows = [
            (r["code_lo"], r["label"], r["valid_from"])
            for r in table.to_pylist()
            if r["codelist"] == "TESTCL" and r["code_lo"] == "1"
        ]
        assert len(rows) == 2, f"one code, two eras, got {rows}"
        assert {r[1] for r in rows} == {"Um antigo", "Um moderno"}


class TestReadingAtAVintage:
    @pytest.fixture
    def packed(self, catalog, tmp_path, monkeypatch):
        _seed(catalog)
        out = tmp_path / "labels.parquet"
        build_label_pack(catalog, out=out, only_bound=False)
        import pegasus_data.labelpack as lp

        monkeypatch.setattr(lp, "_dataset", lambda: __import__(
            "pyarrow.dataset", fromlist=["dataset"]
        ).dataset(out, format="parquet"))
        return lp

    def test_a_historical_year_gets_the_historical_label(self, packed):
        table = packed.read_packed("TESTCL", year=1995)
        labels = dict(zip(table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True))
        assert labels["1"] == "Um antigo"

    def test_a_recent_year_gets_the_recent_label(self, packed):
        table = packed.read_packed("TESTCL", year=2020)
        labels = dict(zip(table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True))
        assert labels["1"] == "Um moderno"

    def test_a_competencia_selects_the_same_way(self, packed):
        early = packed.read_packed("TESTCL", competencia=199506)
        late = packed.read_packed("TESTCL", competencia=202006)
        assert dict(zip(early.column("code").to_pylist(), early.column("label").to_pylist(), strict=True))["1"] == "Um antigo"
        assert dict(zip(late.column("code").to_pylist(), late.column("label").to_pylist(), strict=True))["1"] == "Um moderno"

    def test_a_year_no_window_covers_falls_back_and_says_so(self, packed):
        with collecting() as collected:
            packed.read_packed("TESTCL", year=1980)
        assert any(t[0] == "TESTCL" and t[1] == "1980" for t in collected["fallback"])


class TestBackwardsCompatibility:
    def test_a_pack_without_windows_still_reads(self):
        """The artifact currently shipped has no window columns."""
        from pegasus_data.labelpack import read_packed

        table = read_packed("CID10")
        assert table.num_rows > 0

    def test_a_historical_request_against_it_is_recorded_not_silently_answered(self):
        """Answering 1995 with today's labels and saying nothing is the defect."""
        from pegasus_data.labelpack import read_packed

        with collecting() as collected:
            read_packed("CID10", year=1995)
        reasons = {t[2] for t in collected["fallback"] if t[0] == "CID10"}
        assert "unwindowed-pack" in reasons, (
            "a pack that cannot express windows must say so, so the remedy "
            "(rebuild the pack) is visible rather than the answer being trusted"
        )


class TestTheWindowRule:
    @pytest.mark.parametrize(
        "valid_from,valid_to,lo,hi,expected",
        [
            ("199201", "199712", 199501, 199512, True),
            ("199201", "199712", 199801, 199812, False),
            ("199801", "", 202001, 202012, True),
            ("", "", 199501, 199512, False),   # open-ended is not a dated match
            ("199201", "199712", 199712, 199712, True),
            ("199201", "199712", 199801, 199801, False),
        ],
    )
    def test_it_matches_read_reference_tables_rule(
        self, valid_from, valid_to, lo, hi, expected
    ):
        assert covers(valid_from, valid_to, lo, hi) is expected
