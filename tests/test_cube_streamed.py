"""A year of a dataset's rows reduced in parts equals the year reduced at once (`cubes._count_span_streamed`).

The parts' reductions are merged by `cubes._merge_partials`: sums, counts and moments add, an extreme is the extreme
of the parts', a distinct count keeps its (cell, value) pairs to the end. A national year read whole took 3 to more
than 10 GB (2026-11-27); these tests hold the merge to the answer the whole read gives, on rows built here."""
from __future__ import annotations

import random

import pyarrow as pa
import pytest

from pegasus_data import cubes

CELL = ["PLACE", "__uf", "YEAR", "SEX"]


def _strata(**kw) -> cubes._Strata:
    base = dict(exact={}, after={}, bands={}, group=["PLACE", "YEAR", "SEX"], cell=CELL, extra={}, distinct=None,
                numbered=None, summed=None, extreme=None, moment=None, argument="")
    base.update(kw)
    return cubes._Strata(**base)


def _rows(n: int = 5000, seed: int = 7) -> pa.Table:
    rng = random.Random(seed)
    places = [3550308, 2704302, 1302603, None]
    value = [None if rng.random() < 0.1 else str(round(rng.uniform(-5, 50), 2)) for _ in range(n)]
    return pa.table({
        "PLACE": pa.array([rng.choice(places) for _ in range(n)], pa.int64()),
        "__uf": pa.array([rng.choice([35, 27, 13]) for _ in range(n)], pa.int64()),
        "YEAR": pa.array(["2019"] * n),
        "SEX": pa.array([rng.choice(["1", "2", None]) for _ in range(n)]),
        "V": pa.array(value),
        "W": pa.array([None if rng.random() < 0.5 else str(rng.randint(0, 9)) for _ in range(n)]),
        "PERSON": pa.array([rng.choice([" a1", "b2 ", "c3", "", None, "d4", "e5"]) for _ in range(n)]),
    })


def _sorted(table: pa.Table) -> list[tuple]:
    rows = [tuple(r[c] for c in [*CELL, "events"]) for r in table.to_pylist()]
    return sorted(rows, key=lambda r: tuple("" if v is None else str(v) for v in r[:-1]))


def _in_parts(table: pa.Table, s: cubes._Strata, summed: list[str], size: int) -> pa.Table:
    parts = [cubes._reduce_rows(table.slice(i, size), s, summed, "PLACE", partial=True) for i in range(0, table.num_rows, size)]
    while len(parts) > 3:   # merged before the end as well, as a long year is
        parts = [cubes._merge_partials(parts[:3], s), *parts[3:]]
    return cubes._merge_partials(parts, s, final=True)


CASES = {
    "every row": (dict(), []),
    "a sum": (dict(summed="V"), ["V"]),
    "a sum of two columns": (dict(summed="V+W"), ["V", "W"]),
    "a count of numbers": (dict(numbered="V"), []),
    "a minimum": (dict(extreme="min", argument="V"), []),
    "a maximum": (dict(extreme="max", argument="V"), []),
    "a sum of squares": (dict(moment="sumsq", argument="V"), []),
    "a sum of logs": (dict(moment="sumlog", argument="V"), []),
    "distinct values": (dict(distinct="PERSON"), []),
}


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("size", [1, 37, 1000, 5000])
def test_parts_equal_the_whole(case: str, size: int) -> None:
    options, summed = CASES[case]
    s = _strata(**options)
    table = _rows()
    whole = _sorted(cubes._reduce_rows(table, s, summed, "PLACE"))
    parts = _sorted(_in_parts(table, s, summed, size))
    assert [r[:-1] for r in parts] == [r[:-1] for r in whole]
    for a, b in zip(parts, whole, strict=True):
        assert (a[-1] is None) == (b[-1] is None)
        if a[-1] is not None:
            assert a[-1] == pytest.approx(b[-1], rel=1e-9, abs=1e-9)


def test_a_distinct_value_in_two_parts_counts_once() -> None:
    s = _strata(distinct="PERSON")
    table = pa.table({"PLACE": pa.array([1, 1], pa.int64()), "__uf": pa.array([35, 35], pa.int64()), "YEAR": ["2019", "2019"],
                      "SEX": ["1", "1"], "PERSON": ["a", "a"]})
    assert _in_parts(table, s, [], 1).column("events").to_pylist() == [1]
