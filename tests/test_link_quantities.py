"""followup.quantities on a synthetic run: the events the left records (outcome.known) are the truth subset, the
sensitivity counts only kept passes that can reach an unrecorded event, the chance share is taken over the link-only
events, and a run whose reaching passes were all dropped says so instead of correcting."""
from datetime import date
from types import SimpleNamespace

import pyarrow as pa
import pytest

from pegasus_data.linkage.followup import quantities

REACH, KNOWN = "birth date, sex, residence, day of death", "discharge day, hospital"
SPEC = SimpleNamespace(outcome=SimpleNamespace(known=("admission.death", "1", "admission.end")),
                       passes=[SimpleNamespace(name=REACH, known_only=False),
                               SimpleNamespace(name=KNOWN, known_only=True)])
O = date(2019, 1, 1)


def run():
    # 10 deaths in hospital by day 5 (8 linked by the reaching pass, 1 by the known-only one, 1 unlinked);
    # 6 deaths only the link finds by day 20; 4 persons with no death
    rows = ([(5, REACH, "1", date(2019, 1, 6))] * 8 + [(5, KNOWN, "1", date(2019, 1, 6))]
            + [(None, None, "1", date(2019, 1, 6))] + [(20, REACH, "0", date(2019, 1, 3))] * 6
            + [(None, None, "0", date(2019, 1, 3))] * 4)
    d, p, f, e = zip(*rows)
    return pa.table({"days_to_death": list(d), "link_pass": list(p), "origin": [O] * len(rows),
                     "admission.death": list(f), "admission.end": list(e)})


def test_sensitivity_on_known_and_chance_over_link_only():
    rep = {"horizons": [{"days": 30, "control_pairs": 2}],
           "passes": [{"name": REACH, "kept": True, "pairs": 14}, {"name": KNOWN, "kept": True, "pairs": 1}]}
    (q,) = quantities(run(), rep, SPEC)
    assert (q["pairs"], q["known"], q["known_linked"], q["link_only"]) == (15, 10, 9, 6)
    assert q["sensitivity"] == pytest.approx(0.8) and q["sensitivity_any_pass"] == pytest.approx(0.9)
    assert q["false_match_share_link_only"] == pytest.approx(2 / 6, abs=1e-4)
    assert q["corrected"] == pytest.approx(10 + (6 - 2) / 0.8)
    assert q["corrected_bounds"][0] < q["corrected"] < q["corrected_bounds"][1]
    assert "dropped_passes" not in q and "note" not in q


def test_dropped_reaching_pass_is_reported_not_corrected():
    rep = {"horizons": [{"days": 30, "control_pairs": 0}],
           "passes": [{"name": REACH, "kept": False, "pairs": 1668, "control_pairs": 881, "chance_percent": 52.8},
                      {"name": KNOWN, "kept": True, "pairs": 1}]}
    (q,) = quantities(run(), rep, SPEC)
    assert q["sensitivity"] == 0 and q["sensitivity_passes"] == [] and "corrected" not in q
    assert q["note"] and q["dropped_passes"][0]["control_pairs"] == 881


def test_spec_without_known_gives_pairs_and_chance_only():
    spec = SimpleNamespace(outcome=SimpleNamespace(known=None), passes=SPEC.passes)
    (q,) = quantities(run(), {"horizons": [{"days": 10, "control_pairs": 1}]}, spec)
    assert q["pairs"] == 9 and q["false_match_share"] == pytest.approx(1 / 9, abs=1e-4) and "sensitivity" not in q
