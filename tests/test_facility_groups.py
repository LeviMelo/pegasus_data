"""CNES facility groups: mobile prehospital (42) and emergency units (20, 21, 73) are groups of their own, so the
'other' fields no longer hold them (ABNc t06, 2026-11-24)."""
from pathlib import Path

import yaml

CUR = Path(__file__).resolve().parents[1] / "src" / "pegasus_data" / "curation" / "fields.yml"


def test_emergency_groups_declared_with_both_sectors():
    d = yaml.safe_load(CUR.read_text(encoding="utf-8"))
    flat = {}
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "facility_groups":
                    flat.update(v)
                walk(v)
    walk(d)
    assert flat["mobile_emergency"] == ["42"] and flat["emergency_unit"] == ["20", "21", "73"]
    text = CUR.read_text(encoding="utf-8")
    for g in ("mobile_emergency", "emergency_unit"):
        for sec in ("sus", "nonsus"):
            assert f"  cnes_facilities_{g}_{sec}:" in text
