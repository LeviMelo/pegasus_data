"""Where a field's values cannot be taken at face value, measured from the data.

``race_reliability`` flags the SIH race code per hospital and month (OQ-66).
In SIH, the race code whose label is "amarela" is the one people of Asian origin are
recorded under. They are about 0.4% of Brazil's population (Census 2022), and
the median SIH hospital-month records none. Yet some hospitals record most of
their admissions under it:
- **as a default**, whites and blacks included (CNES 2499363 CE, 90–97% every
  month of 2022);
- **as SIM's code for brown**, written into SIH's field, where SIM numbers
  brown 4 (CNES 2705982 SP until 2022-08, then fixed).

Linked to SIM and SINASC, those hospitals' amarela is brown or anything else, not
Asian (EVALUATION 2026-10-03). Nothing is relabelled: the flag says which
hospital-months to read with care, and the raw code stays.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from .duckdb_session import connect as duck_connect

__all__ = ["race_reliability"]


def race_reliability(table: pa.Table, *, root: str | Path | None = None) -> pa.Table:
    """Add ``<race>_reliability`` to an SIH table, judged per (hospital, month).

    The columns are the roles the check declares (``curation/quality.yml``: the race, the hospital, the month of
    discharge), the two codes tested are the ones whose label in that year's codelist is the roles file's ``asian`` and
    ``brown`` category (``curation/roles/SIH-RD.yml``, ``patient.race``), and the thresholds are the declared parameters:

    - ``unreliable``: asian is over half the hospital-month (a default), or brown is under 1% while asian is over 10%
      (brown written as SIM's 4).
    - ``suspect``: asian between 10% and 50% otherwise. Demographically implausible anywhere in Brazil, but not a
      pattern measured as one of the two mechanisms.
    - ``ok``: neither.
    - ``too_few``: fewer than ``min_admissions`` admissions in the hospital-month.
    - ``unplaced``: no hospital or no month on the row, so it belongs to no hospital-month and is not judged (it is
      kept, flagged, not dropped).

    SIH publishes by the hospital's state and month, so a query of a state's months holds each hospital-month whole.
    Measured on SIH-RD 2022 (43,945 hospital-months of 30+ admissions): 329 unreliable in 64 hospitals (89,003
    admissions); 1,297 suspect in 278.
    """

    from .config import curation_root
    from .linkage.roles import dataset_roles
    from .semantics.categories import code_labels
    from .semantics.column_roles import column_of
    from .semantics.curation import read_yaml

    spec = read_yaml(curation_root() / "quality.yml", shared=True)["race_reliability"]
    dataset = str(spec["dataset"])
    race, facility, month = (column_of(dataset, str(spec[k])) for k in ("race", "facility", "month"))
    for name in (race, facility, month):
        if name not in table.column_names:
            raise KeyError(f"{name}: required column for race_reliability is absent")
    categories = dict(dataset_roles(dataset).roles[str(spec["race"])].categories)
    con = duck_connect()
    try:
        # An explicit position, not row_number() OVER (): a parallel scan does not
        # promise to keep the input order, and the flags must land on their rows.
        con.register("t", table.select([race, facility, month]).append_column(
            "_i", pa.array(range(table.num_rows), pa.int64())))
        con.execute(f"""CREATE VIEW r AS SELECT _i AS i, CAST("{race}" AS VARCHAR) AS code,
                              NULLIF(trim(CAST("{facility}" AS VARCHAR)), '') AS cnes,
                              NULLIF(substr(regexp_replace(CAST("{month}" AS VARCHAR), '[^0-9]', '', 'g'), 1, 6), '') AS ym
                       FROM t""")
        # The meaning of a code is its label in the year's codelist: which codes are asian and brown is read per year.
        meaning: list[tuple[str, str, str]] = []
        for (year,) in con.execute("SELECT DISTINCT substr(ym, 1, 4) FROM r WHERE ym IS NOT NULL").fetchall():
            codes = [c for (c,) in con.execute(
                "SELECT DISTINCT code FROM r WHERE code IS NOT NULL AND substr(ym, 1, 4) = ?", [year]).fetchall()]
            for code, label in code_labels(dataset, race, int(year), codes, root).items():
                category = categories.get(label.strip().lower())
                if category in (spec["asian"], spec["brown"]):
                    meaning.append((year, code, "asian" if category == spec["asian"] else "brown"))
        con.register("m", pa.table({"yr": pa.array([m[0] for m in meaning], pa.string()),
                                    "code": pa.array([m[1] for m in meaning], pa.string()),
                                    "cat": pa.array([m[2] for m in meaning], pa.string())}))
        # A row with no hospital or month is in no hospital-month: it stays out of the grouping and is left-joined,
        # so it keeps its place in the result.
        flags = con.execute(f"""
            WITH c AS (SELECT r.*, m.cat FROM r LEFT JOIN m ON m.yr = substr(r.ym, 1, 4) AND m.code = r.code),
                 hm AS (SELECT cnes, ym, count(*) AS n, avg(coalesce(cat = 'asian', false)::INT) AS asian,
                               avg(coalesce(cat = 'brown', false)::INT) AS brown FROM c
                         WHERE cnes IS NOT NULL AND ym IS NOT NULL GROUP BY ALL)
            SELECT CASE WHEN hm.n IS NULL THEN 'unplaced'
                        WHEN hm.n < {int(spec['min_admissions'])} THEN 'too_few'
                        WHEN hm.asian > {float(spec['unreliable_asian_share'])}
                             OR (hm.brown < {float(spec['swapped_brown_share'])}
                                 AND hm.asian > {float(spec['suspect_asian_share'])}) THEN 'unreliable'
                        WHEN hm.asian > {float(spec['suspect_asian_share'])} THEN 'suspect'
                        ELSE 'ok' END AS flag
            FROM c LEFT JOIN hm ON c.cnes = hm.cnes AND c.ym = hm.ym ORDER BY c.i""").to_arrow_table().column("flag")
    finally:
        con.close()
    return table.append_column(f"{race}_reliability", flags)
