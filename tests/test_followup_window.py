"""A follow-up window is known only when the data cover it: a death and a survival alike (ABNc, 2026-11-24)."""
import datetime

import pyarrow as pa

from pegasus_data.linkage.followup import Followup


def _fu(end):
    origin = pa.array([datetime.date(2024, 1, 1), datetime.date(2024, 12, 1), datetime.date(2024, 12, 1)], pa.date32())
    t = pa.table({"origin": origin, "days_to_death": pa.array([10, 5, None], pa.int64())})
    q = {"death_data_end": end, "horizons": [{"days": 30, "verdict": "viable", "chance_percent": 1.0, "control_pairs": 0}],
         "link": "x", "window_days": 365}
    return Followup(table=t, quality=q, pairs=pa.table({}), report={})


def test_uncovered_window_is_unknown_for_deaths_and_survivors():
    # the second person died 5 days after an origin whose 30 days pass the data's end: unknown, as the third (alive)
    assert _fu("2024-12-20").died_within(30).to_pylist() == [True, None, None]
    m = _fu("2024-12-20").mortality(30)
    assert (m["followed"], m["died"]) == (1, 1)


def test_covered_window_and_unknown_end():
    assert _fu("2025-06-30").died_within(30).to_pylist() == [True, True, False]
    assert _fu(None).died_within(30).to_pylist() == [None, None, None]


def test_event_link_reads_its_own_data_end():
    fu = _fu(None)
    fu.quality.pop("death_data_end")
    fu.quality["event_data_end"] = "2025-06-30"
    assert fu.died_within(30).to_pylist() == [True, True, False]


def test_horizon_past_the_reach_is_unknown():
    fu = _fu("2025-06-30")
    fu.quality["passes"] = [{"name": "year pass", "kept": True, "reach_days": 20}, {"name": "discharge day", "kept": True}]
    assert fu.reach_days == 20
    assert fu.died_within(30).to_pylist() == [None, None, None]
    fu.quality["horizons"].insert(0, {"days": 7, "verdict": "viable", "chance_percent": 1.0, "control_pairs": 0})
    assert fu.died_within(7).to_pylist() == [False, True, False]
