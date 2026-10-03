"""Where a field's values cannot be taken at face value, measured from the data.

``race_reliability`` flags the SIH race code per hospital and month (OQ-66).
In SIH, ``RACA_COR`` 04 ("amarela") is the code people of Asian origin are
recorded under. They are about 0.4% of Brazil's population (Census 2022), and
the median SIH hospital-month records none. Yet some hospitals record most of
their admissions as 04:
- **as a default**, whites and blacks included (CNES 2499363 CE, 90–97% every
  month of 2022);
- **as SIM's code for brown**, written into SIH's field, where SIM numbers
  brown 4 (CNES 2705982 SP until 2022-08, then fixed).

Linked to SIM and SINASC, those hospitals' 04 is brown or anything else, not
Asian (EVALUATION 2026-10-03). Nothing is relabelled: the flag says which
hospital-months to read with care, and the raw code stays.
"""

from __future__ import annotations

import pyarrow as pa

#: A hospital-month with fewer admissions is not judged.
MIN_ADMISSIONS = 30

__all__ = ["MIN_ADMISSIONS", "race_reliability"]


def race_reliability(table: pa.Table, *, race: str = "RACA_COR", facility: str = "CNES",
                     month: str = "DT_SAIDA") -> pa.Table:
    """Add ``<race>_reliability`` to an SIH table, judged per (hospital, month).

    - ``unreliable``: code 04 is over half the hospital-month (a default), or
      brown (03) is under 1% while 04 is over 10% (brown written as SIM's 4).
    - ``suspect``: 04 between 10% and 50% otherwise. Demographically
      implausible anywhere in Brazil, but not a pattern measured as one of
      the two mechanisms.
    - ``ok``: neither.
    - ``too_few``: fewer than MIN_ADMISSIONS admissions in the hospital-month.

    SIH publishes by the hospital's state and month, so a query of a state's
    months holds each hospital-month whole. Measured on SIH-RD 2022 (43,945
    hospital-months of 30+ admissions): 329 unreliable in 64 hospitals (89,003
    admissions); 1,297 suspect in 278.
    """
    import duckdb

    for name in (race, facility, month):
        if name not in table.column_names:
            raise KeyError(f"{name}: required column for race_reliability is absent")
    con = duckdb.connect()
    # An explicit position, not row_number() OVER (): a parallel scan does not
    # promise to keep the input order, and the flags must land on their rows.
    con.register("t", table.select([race, facility, month]).append_column(
        "_i", pa.array(range(table.num_rows), pa.int64())))
    flags = con.execute(f"""
        WITH r AS (SELECT _i AS i, CAST("{race}" AS VARCHAR) AS code,
                          CAST("{facility}" AS VARCHAR) AS cnes,
                          substr(regexp_replace(CAST("{month}" AS VARCHAR), '[^0-9]', '', 'g'), 1, 6) AS ym
                   FROM t),
             hm AS (SELECT cnes, ym, count(*) AS n, avg((code = '04')::INT) AS asian,
                           avg((code = '03')::INT) AS brown FROM r GROUP BY ALL)
        SELECT CASE WHEN hm.n < {MIN_ADMISSIONS} THEN 'too_few'
                    WHEN hm.asian > 0.5 OR (hm.brown < 0.01 AND hm.asian > 0.10) THEN 'unreliable'
                    WHEN hm.asian > 0.10 THEN 'suspect'
                    ELSE 'ok' END AS flag
        FROM r JOIN hm USING (cnes, ym) ORDER BY r.i""").fetch_arrow_table().column("flag")
    return table.append_column(f"{race}_reliability", flags)
