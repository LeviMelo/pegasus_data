"""CNES professional groups nest (ADR-0215): a specialist counts in its own group and among physicians, and the
2231-era code of a specialist counts in its group."""
import pyarrow as pa

from pegasus_data.sources import cnes


def test_groups_nest_and_carry_their_2231_codes():
    jobs = pa.table({"municipality": ["1", "1", "1"], "cbo": ["225265", "223144", "225125"],
                     "hours": [40, 20, 40], "hours_sus": [40, 0, 40], "jobs": [1, 1, 1]})
    people = pa.table({"municipality": ["1", "1", "1"], "cbo": ["225265", "223144", "225125"], "cns": ["a", "b", "c"]})
    out = {r["group"]: r for r in cnes._pf_groups(jobs, people).to_pylist()}
    assert out["ophthalmologists"]["professionals"] == 2 and out["ophthalmologists"]["hours"] == 60
    assert out["physicians"]["professionals"] == 3 and out["physicians"]["hours"] == 100
