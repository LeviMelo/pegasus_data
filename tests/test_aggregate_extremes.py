"""The `min`/`max` kinds, through the columnar build and finalize paths.

No shipped spec declares an extreme measure, which is exactly how all three of
these defects survived: the build's intra-chunk grouping summed every state
column regardless of kind (a min cell held a TOTAL), the lift filled blanks
with 0.0 rather than the identity (every minimum dragged to nought), and the
columnar finalize passed the identity through as literal Infinity — which JSON
cannot carry, so an unobserved cell crashed the response instead of nulling.

These tests pin the columnar spellings to the scalar `Kind` semantics, the way
`test_formula_matches_finalize` is described as doing for mean/ratio.
"""

from __future__ import annotations

import math

import pyarrow as pa
import pytest

from pegasus_data._aggregate import _accumulate, _finalize_column, _lift_columns
from pegasus_data.measures import MAX, MIN, Measure

pytestmark = pytest.mark.filterwarnings("ignore")


def _measure(kind, name="extreme"):
    return Measure(name=name, kind=kind, source_fields=("VALUE",), label=name, unit="unit")


class TestLift:
    def test_a_blank_lifts_to_the_identity_not_zero(self) -> None:
        table = pa.table({"VALUE": ["7", None, "3"]})
        out, _ = _lift_columns(table, [_measure(MIN)])
        assert out["extreme_min"].to_pylist() == [7.0, float("inf"), 3.0]
        out, _ = _lift_columns(table, [_measure(MAX)])
        assert out["extreme_max"].to_pylist() == [7.0, float("-inf"), 3.0]


class TestAccumulate:
    def _cells(self, kind, values):
        table = pa.table({"VALUE": values})
        keyed = {"geo": pa.array(["A"] * len(values)), "time": pa.array(["202201"] * len(values))}
        spec = type("Spec", (), {"measures": [_measure(kind)]})()
        cells: dict = {}
        _accumulate(cells, table, keyed, spec)
        return cells

    def test_min_reduces_by_min_not_sum(self) -> None:
        cells = self._cells(MIN, ["5", "2", "9"])
        assert cells[("A", "202201")]["extreme"] == (2.0,)

    def test_max_reduces_by_max_not_sum(self) -> None:
        cells = self._cells(MAX, ["5", "2", "9"])
        assert cells[("A", "202201")]["extreme"] == (9.0,)

    def test_all_blank_stays_the_identity(self) -> None:
        cells = self._cells(MIN, [None, None])
        assert cells[("A", "202201")]["extreme"] == (float("inf"),)


class TestFinalize:
    def test_the_identity_finalizes_to_null_like_the_scalar_path(self) -> None:
        state = (pa.array([float("inf"), 5.0]),)
        got = _finalize_column(_measure(MIN), state).to_pylist()
        assert got[0] is None, "an unobserved min is null, not Infinity"
        assert got[1] == 5.0
        assert MIN.finalize(MIN.identity()) is None, "the scalar semantics this mirrors"

    def test_max_identity_finalizes_to_null(self) -> None:
        state = (pa.array([float("-inf"), 4.0]),)
        got = _finalize_column(_measure(MAX), state).to_pylist()
        assert got == [None, 4.0]
        assert not any(v is not None and math.isinf(v) for v in got)
