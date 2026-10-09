"""The missing-codes sweep (work plan P1): `propose_missing.py --write` over every dataset with an event type whose
reviewed category or measurement columns declare neither ``missing`` nor ``missing_unknown``.

    python scripts/sweep_missing.py [DATASET ...]

Each dataset's undeclared columns are covered greedily by years: the year inside the most of their spans first, then
the year inside the most of those left, so every column is read in a year it exists. SIA's production files are read
on one state-month (`--sample SP:YYYY-01`): a national year is hundreds of millions of rows. A column the proposer
cannot decide gets its reason written (`missing_unknown`); one with no value in the year read is left for the next.
"""
from __future__ import annotations

import subprocess
import sys
from collections import Counter

from pegasus_data.semantics import column_roles, event_types

SAMPLED = {"SIASUS-PA", "SIASUS-BI", "SIASUS-PS", "SIASUS-SAD"}
LAST = 2023                 # the years the lake holds; the FTP was unreachable when this ran (2026-10-09)


def undeclared(key: str) -> list[column_roles.ColumnRole]:
    return [r for r in column_roles.load_column_roles().get(key, ())
            if r.reviewed and not r.derived and r.missing is None and r.missing_unknown is None
            and r.model in ("mark", "dimension")
            and (r.kind == "category" or (r.kind == "number" and r.measure))]


def cover(rows: list[column_roles.ColumnRole]) -> list[int]:
    left, years = list(rows), []
    while left:
        votes = Counter(y for r in left for y in range(max(r.years[0] or 2010, 2007), min(r.years[1] or LAST, LAST) + 1))
        if not votes:
            break
        best = max(votes, key=lambda y: (votes[y], y))
        years.append(best)
        left = [r for r in left if not ((r.years[0] or 0) <= best <= (r.years[1] or 9999))]
    return years


def main(only: list[str]) -> None:
    keys = sorted(only or event_types.load_event_types())
    for key in keys:
        rows = undeclared(key)
        if not rows:
            continue
        for year in cover(rows):
            cmd = [sys.executable, "scripts/propose_missing.py", key, str(year), "--write"]
            if key in SAMPLED:
                cmd += ["--sample", f"SP:{year}-01"]
            print(f"== {key} {year}: {len(rows)} undeclared", flush=True)
            done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            lines = [ln for ln in (done.stdout + done.stderr).splitlines() if "[fetch]" not in ln and "Warn" not in ln]
            print("\n".join(lines[-40:]), flush=True)
            column_roles.load_column_roles.cache_clear()
            rows = undeclared(key)
            if not rows:
                break


if __name__ == "__main__":
    main(sys.argv[1:])
