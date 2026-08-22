"""ME-14 and the reference-fallback items: which vintage answered, and said so.

`read_reference_table(year=...)` matched any window overlapping the calendar
year, so a codelist revised in July was two windows inside one year and `year=`
could not choose. When nothing matched at all it returned the WHOLE table —
every historical window at once — which is the one thing the no-year branch
exists to prevent: merging windows that disagree manufactures a contradiction
out of ordinary editorial drift.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from pegasus_data.persist.reference import (
    collecting,
    read_reference_table,
)

# Two windows inside 2015: revised in July. This is the case `year=` cannot
# answer and `competencia=` can.
ROWS = [
    ("1", "Um antigo", "201501", "201506"),
    ("1", "Um revisto", "201507", "201512"),
    ("2", "Dois", "201501", "201506"),
    ("2", "Dois revisto", "201507", "201512"),
]


@pytest.fixture
def lake(tmp_path: Path) -> Path:
    base = tmp_path / "reference" / "TESTCL"
    base.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "code": [r[0] for r in ROWS],
                "label": [r[1] for r in ROWS],
                "valid_from": [r[2] for r in ROWS],
                "valid_to": [r[3] for r in ROWS],
            }
        ),
        base / "part-0.parquet",
    )
    return tmp_path


class TestCompetencia:
    def test_it_picks_one_window_where_a_year_cannot(self, lake):
        first = read_reference_table(lake, "TESTCL", competencia=201503)
        second = read_reference_table(lake, "TESTCL", competencia=201509)
        assert first.column("label").to_pylist() == ["Um antigo", "Dois"]
        assert second.column("label").to_pylist() == ["Um revisto", "Dois revisto"]

    def test_a_year_still_matches_every_window_it_overlaps(self, lake):
        """Documented behaviour, not a bug — but it is why competencia exists."""
        whole = read_reference_table(lake, "TESTCL", year=2015)
        assert whole.num_rows == 4

    def test_a_boundary_month_belongs_to_exactly_one_window(self, lake):
        assert read_reference_table(lake, "TESTCL", competencia=201506).column(
            "label"
        ).to_pylist() == ["Um antigo", "Dois"]
        assert read_reference_table(lake, "TESTCL", competencia=201507).column(
            "label"
        ).to_pylist() == ["Um revisto", "Dois revisto"]


class TestUnresolvedIsNotMerged:
    def test_a_year_no_window_covers_returns_nothing_rather_than_everything(self, lake):
        """It used to return all four rows: two labels for code '1' at once."""
        with collecting() as collected:
            got = read_reference_table(lake, "TESTCL", year=1995)
        assert got.num_rows == 0, "merging disagreeing windows manufactures a contradiction"
        assert ("TESTCL", "1995", "unresolved") in collected["fallback"]

    def test_the_schema_survives_an_unresolved_answer(self, lake):
        got = read_reference_table(lake, "TESTCL", year=1995)
        assert "code" in got.schema.names and "label" in got.schema.names

    def test_an_open_ended_table_stands_in_and_is_recorded(self, tmp_path):
        base = tmp_path / "reference" / "OPENCL"
        base.mkdir(parents=True)
        pq.write_table(
            pa.table(
                {
                    "code": ["1", "2"],
                    "label": ["Um", "Dois"],
                    "valid_from": [None, None],
                    "valid_to": [None, None],
                }
            ),
            base / "part-0.parquet",
        )
        with collecting() as collected:
            got = read_reference_table(tmp_path, "OPENCL", year=1995)
        assert got.num_rows == 2, "today's table is a real answer"
        assert ("OPENCL", "1995", "current") in collected["fallback"], (
            "and an undisclosed one until now"
        )


class TestTheCollectorIsPerCall:
    def test_a_second_identical_call_reports_it_again(self, lake):
        """The process-lifetime set cannot answer this: adding a member that is
        already present does not change it, so a diff sees nothing the second
        time and the disclosure silently stops after the first render."""
        with collecting() as first:
            read_reference_table(lake, "TESTCL", year=1995)
        with collecting() as second:
            read_reference_table(lake, "TESTCL", year=1995)
        assert first["fallback"] == second["fallback"] != set()

    def test_nothing_leaks_between_collections(self, lake):
        with collecting() as first:
            read_reference_table(lake, "TESTCL", year=1995)
        with collecting() as second:
            read_reference_table(lake, "TESTCL", competencia=201503)
        assert first["fallback"] and not second["fallback"]

    def test_recording_outside_a_collection_is_harmless(self, lake):
        read_reference_table(lake, "TESTCL", year=1995)
