"""Reading a schema from a file's header instead of its payload.

The census exists because decoding one file per stratum costs 183 GiB and 63% of
strata hold a single file, so there is no cheaper member to pick. A DBF states
its whole schema in a few hundred bytes and a .dbc keeps that header
uncompressed, so the same answer costs about 17 MB.

What these tests protect is the honesty of that shortcut: the header must give
*exactly* the columns a full decode gives, and must refuse rather than guess when
the prefix is too short — a half-read descriptor array produces plausible field
names that are not the file's columns, which is worse than admitting the prefix
was short.
"""

from __future__ import annotations

import struct

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.decode.header import (
    HeaderUnreadable,
    prefix_bytes_needed,
    read_table_header,
)
from pegasus_data.inventory.schemas import persist_header, run_census


def make_header(fields: list[tuple[str, str, int, int]], *, records: int = 10) -> bytes:
    """A minimal but real DBF header: 32-byte preamble, descriptors, terminator."""
    header_length = 32 + 32 * len(fields) + 1
    record_length = sum(w for _, _, w, _ in fields) + 1
    out = bytearray(b"\x03\x7c\x01\x01")
    out += struct.pack("<IHH", records, header_length, record_length)
    out += b"\x00" * 20
    for name, type_code, width, decimals in fields:
        out += name.encode("latin-1")[:11].ljust(11, b"\x00")
        out += type_code.encode("latin-1")
        out += b"\x00" * 4
        out += bytes([width, decimals])
        out += b"\x00" * 14
    out += b"\x0d"
    return bytes(out)


SIH_LIKE = [
    ("UF_ZI", "C", 2, 0),
    ("ANO_CMPT", "C", 4, 0),
    ("N_AIH", "C", 13, 0),
    ("DIAG_PRINC", "C", 4, 0),
    ("VAL_TOT", "N", 14, 2),
]


class TestReadingAHeader:
    def test_it_reads_names_types_widths_and_decimals(self):
        header = read_table_header(make_header(SIH_LIKE))
        assert header.field_names == ["UF_ZI", "ANO_CMPT", "N_AIH", "DIAG_PRINC", "VAL_TOT"]
        val_tot = header.fields[-1]
        assert (val_tot.type_code, val_tot.width, val_tot.decimals) == ("N", 14, 2)

    def test_widths_that_sum_to_the_record_length_are_consistent(self):
        assert read_table_header(make_header(SIH_LIKE)).consistent

    def test_an_inconsistent_record_length_is_reported_not_hidden(self):
        """The signal that the descriptors were misread — worth recording."""
        data = bytearray(make_header(SIH_LIKE))
        data[10:12] = struct.pack("<H", 999)
        assert not read_table_header(bytes(data)).consistent

    def test_the_declared_record_count_is_carried_but_not_trusted(self):
        header = read_table_header(make_header(SIH_LIKE, records=41234))
        assert header.declared_records == 41234

    def test_trailing_bytes_after_the_terminator_are_ignored(self):
        data = make_header(SIH_LIKE) + b"\xff" * 4096
        assert len(read_table_header(data).fields) == 5


class TestItRefusesRatherThanGuesses:
    def test_a_truncated_prefix_raises(self):
        """A half-read descriptor array is worse than no answer."""
        full = make_header(SIH_LIKE)
        with pytest.raises(HeaderUnreadable, match="need"):
            read_table_header(full[:96])

    def test_a_file_that_is_not_a_dbf_raises(self):
        with pytest.raises(HeaderUnreadable):
            read_table_header(b"PK\x03\x04" + b"\x00" * 200)

    def test_something_far_too_short_raises(self):
        with pytest.raises(HeaderUnreadable, match="too short"):
            read_table_header(b"\x03\x00\x00")

    def test_a_bogus_type_code_stops_the_scan(self):
        """Garbage in the descriptor slot means the offsets are wrong."""
        data = bytearray(make_header(SIH_LIKE))
        data[32 + 11] = ord("Z")  # not a DBF field type
        with pytest.raises(HeaderUnreadable):
            read_table_header(bytes(data))

    def test_the_header_states_how_much_is_needed(self):
        """Lets a caller fetch small and widen only when the file says so."""
        assert prefix_bytes_needed(make_header(SIH_LIKE)) == 32 + 32 * 5 + 1


class TestCensus:
    def _stratum(self, catalog: Catalog, path="/a/RDAC1401.dbc"):
        catalog.execute(
            "INSERT INTO strata (stratum_id, system, series, year, file_count, sampled_path, "
            "sample_status) VALUES ('S1','SIHSUS','RD',2014,1,?, 'pending')",
            (path,),
        )
        return {"stratum_id": "S1", "path": path, "extension": ".dbc", "size": 1000}

    def test_a_census_records_the_schema_and_its_fields(self, catalog: Catalog):
        target = self._stratum(catalog)
        data = make_header(SIH_LIKE)
        census = run_census(catalog, lambda _p, _n: data, [target])
        assert census.read == 1 and census.unreadable == 0
        assert catalog.count("schema_header_facts") == 5
        assert catalog.count("schema_presence") == 5

    def test_it_shares_the_signature_the_families_stage_uses(self, catalog: Catalog):
        """The census must land on the same family a profiled sample would."""
        from pegasus_data.inventory.families import schema_signature

        target = self._stratum(catalog)
        run_census(catalog, lambda _p, _n: make_header(SIH_LIKE), [target])
        expected = schema_signature([f[0] for f in SIH_LIKE])
        row = catalog.query("SELECT schema_signature FROM strata WHERE stratum_id='S1'")[0]
        assert row["schema_signature"] == expected

    def test_it_widens_the_request_once_when_the_header_says_so(self, catalog: Catalog):
        target = self._stratum(catalog)
        # Wider than FIRST_PREFIX (8 KB), so the first ask genuinely cannot
        # hold the descriptor array and the file's own header_length is what
        # tells the census how much more to request.
        full = make_header([(f"F{i}", "C", 4, 0) for i in range(300)])
        assert len(full) > 8192
        asked: list[int] = []

        def fetch(_path: str, n: int) -> bytes:
            asked.append(n)
            return full[:n]

        census = run_census(catalog, fetch, [target])
        assert census.read == 1
        assert census.widened == 1
        assert len(asked) == 2 and asked[1] > asked[0], "asked again, larger"

    def test_a_non_header_format_is_counted_apart_from_a_failure(self, catalog: Catalog):
        """A CSV is not a broken DBF; it just needs a different route."""
        target = {**self._stratum(catalog), "extension": ".csv"}
        census = run_census(catalog, lambda _p, _n: b"a,b,c\n", [target])
        assert census.not_header_readable == 1
        assert census.unreadable == 0 and census.read == 0

    def test_one_unreadable_file_does_not_end_the_census(self, catalog: Catalog):
        catalog.execute(
            "INSERT INTO strata (stratum_id, system, series, year, file_count, sampled_path, "
            "sample_status) VALUES ('S2','SIHSUS','RD',2015,1,'/a/b.dbc','pending')"
        )
        targets = [
            self._stratum(catalog),
            {"stratum_id": "S2", "path": "/a/b.dbc", "extension": ".dbc", "size": 1},
        ]
        good = make_header(SIH_LIKE)

        def fetch(path: str, _n: int) -> bytes:
            return good if path.endswith("RDAC1401.dbc") else b"PK\x03\x04not a dbf"

        census = run_census(catalog, fetch, targets)
        assert census.read == 1 and census.unreadable == 1
        assert census.errors and "/a/b.dbc" in census.errors[0][0]

    def test_the_census_reports_what_it_cost(self, catalog: Catalog):
        target = self._stratum(catalog)
        data = make_header(SIH_LIKE)
        census = run_census(catalog, lambda _p, n: data[:n], [target])
        assert census.bytes_fetched == len(data)
        assert census.as_dict()["distinct_signatures"] == 1

    def test_a_header_read_does_not_claim_the_stratum_was_profiled(self, catalog: Catalog):
        """'We know the columns' must never read as 'we know the values'."""
        target = self._stratum(catalog)
        run_census(catalog, lambda _p, _n: make_header(SIH_LIKE), [target])
        status = catalog.query("SELECT sample_status FROM strata WHERE stratum_id='S1'")[0]
        assert status["sample_status"] == "header", "not 'ok' — nothing was decoded"
        assert catalog.count("variable_profiles") == 0


class TestPersistHeaderIsIdempotent:
    def test_reading_the_same_header_twice_changes_nothing(self, catalog: Catalog):
        catalog.execute(
            "INSERT INTO strata (stratum_id, system, series, year, file_count, sampled_path, "
            "sample_status) VALUES ('S1','SIHSUS','RD',2014,1,'/a/x.dbc','pending')"
        )
        header = read_table_header(make_header(SIH_LIKE))
        for _ in range(3):
            persist_header(catalog, stratum_id="S1", path="/a/x.dbc", header=header)
        assert catalog.count("schema_header_facts") == 5
        assert catalog.count("schema_presence") == 5


class TestTheCensusDoesNotDisableProfiling:
    """The cheap stage must not cancel the expensive one that knows more."""

    def test_a_census_read_stratum_is_still_waiting_to_be_profiled(self, catalog: Catalog):
        from pegasus_data.inventory.strata import sample_plan

        catalog.execute(
            "INSERT INTO strata (stratum_id, system, series, year, file_count, sampled_path, "
            "sample_status) VALUES ('S1','SIHSUS','RD',2014,1,'/a/x.dbc','pending')"
        )
        target = {"stratum_id": "S1", "path": "/a/x.dbc", "extension": ".dbc", "size": 10}
        run_census(catalog, lambda _p, _n: make_header(SIH_LIKE), [target])

        outstanding = [row["stratum_id"] for row in sample_plan(catalog)]
        assert outstanding == ["S1"], (
            "reading a header is not profiling; the stratum still needs its data read"
        )

    def test_a_profiled_stratum_is_not_reoffered(self, catalog: Catalog):
        from pegasus_data.inventory.strata import sample_plan

        catalog.execute(
            "INSERT INTO strata (stratum_id, system, series, year, file_count, sampled_path, "
            "sample_status) VALUES ('S1','SIHSUS','RD',2014,1,'/a/x.dbc','ok')"
        )
        assert sample_plan(catalog) == []
