"""A dataset's roles' declared years against what its columns fill (OPEN_QUESTIONS 71; `pegasus_data.field_fill`).

    python scripts/audit_role_years.py DATASET YEAR [YEAR ...]

Prints every column whose declared years hold a year where it fills no record (presence is not fill), and every
column filled in a year outside its declared span. Reads the years nationally, through the lake.
"""
import sys
import warnings

import pegasus_data as pg
from pegasus_data.semantics import column_roles

warnings.simplefilter("ignore")
dataset, years = sys.argv[1], [int(y) for y in sys.argv[2:]]
rows = [r for r in column_roles.load_column_roles()[dataset.upper().replace(".", "-")]
        if not r.derived and r.model not in ("excluded",)]
fill = pg.field_fill(dataset, [r.column for r in rows], years, geography="BR").to_pylist()
by = {(f["field"], f["year"]): f for f in fill}
for r in rows:
    lo, hi = r.years[0] or 0, r.years[1] or 9999
    for y in years:
        f = by.get((r.column, y))
        if f is None:
            continue
        if f["records"] is None:
            print(f"{r.column}: {y} could not be read (a gap, not an absence)")
            continue
        inside = lo <= y <= hi
        if inside and f["filled"] == 0:
            print(f"{r.column}: declared {lo}-{hi}, fills no record in {y} ({f['records']:,} records)")
        elif not inside and f["filled"] > 0:
            print(f"{r.column}: declared {lo}-{hi}, fills {f['filled']:,} of {f['records']:,} in {y}")
