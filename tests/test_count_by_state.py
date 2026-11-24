"""count_events read one state at a time: which events may be split (`_state_reads`) and how the pieces are summed
(`_summed`). Equality with the whole read on real data: SIH-RD 2019 by residence, sex and diagnosis (12,181,726 events
in 2,571,887 cells either way, peak 1.2 GB against 3.6 GB) and SIH-SP 2023 in AL and SE (2026-11-24)."""
import dataclasses
import json

import pyarrow as pa

from pegasus_data.conditions import CONDITION_META
from pegasus_data.semantics import event_types as et


def _event(**kw):
    base = et.EventType(dataset="X", system="SIH", series="RD", name="e", kind="hospitalisation", grain=None)
    return dataclasses.replace(base, **kw)


def test_unsplittable_events_are_read_whole():
    chain = object()
    assert et._state_reads("X", _event(chain=chain), 2019, "BR", {}) is None                 # a transfer crosses states
    assert et._state_reads("X", _event(duplicates_except=("A",)), 2019, "BR", {}) is None    # whole-row comparison
    assert et._state_reads("X", _event(consolidation_key=("NU_NOTIFIC",)), 2019, "BR", {}) is None   # not state-local


def test_pieces_sum_counts_and_reports():
    def part(codes, events, satisfied, unknown):
        t = pa.table({"code": codes, "events": events, "unknown": [0] * len(codes)})
        report = {"clauses": [["x"]], "satisfied": satisfied, "unknown": unknown, "unit": "events"}
        return t.replace_schema_metadata({et.UNKEYED: b"2", CONDITION_META: json.dumps(report).encode()})

    out = et._summed([part(["a", "b"], [1, 2], 3, 1), part(["b", "c"], [5, 7], 12, 4)], ["code"])
    got = dict(zip(out.column("code").to_pylist(), out.column("events").to_pylist()))
    assert got == {"a": 1, "b": 7, "c": 7}
    meta = out.schema.metadata
    assert meta[et.UNKEYED] == b"4"
    rep = json.loads(meta[CONDITION_META])
    assert rep["satisfied"] == 15 and rep["unknown"] == 5 and rep["clauses"] == [["x"]]
    total = et._summed([pa.table({"events": [1]}), pa.table({"events": [2]})], None)
    assert total.column("events").to_pylist() == [3]
