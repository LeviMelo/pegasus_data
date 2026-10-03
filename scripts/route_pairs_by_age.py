"""Admission–baby pairs of one person, by route and by the baby's age at admission.

Usage: python scripts/route_pairs_by_age.py PERIOD GEO

The entities (build_entities) join an SIH admission and a SINASC birth when
they are one person: directly through the newborn link, or through other links
(an admission that ended in death, its certificate, the birth that
certificate links to). The routes added pairs the newborn spec does not
draw. Are those newborns its 28-day filter left out, or older infants? Each
pair is counted by route and by the days from birth to admission.

Run under the data home that holds the links. Writes
data/probes/linkage/route_pairs_by_age_<geo>_<period>.json.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import duckdb
import pyarrow as pa

from pegasus_data import link
from pegasus_data.linkage.entities import build_entities, person_pairs
from pegasus_data.linkage.roles import record_ids, role_table

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"
BANDS = """CASE WHEN days IS NULL THEN 'unknown' WHEN days < 0 THEN 'admitted before birth (error)'
    WHEN days <= 6 THEN '0-6 days' WHEN days <= 27 THEN '7-27 days' WHEN days <= 364 THEN '28-364 days'
    ELSE '1 year or more' END"""


def main(period: str, geo: str) -> None:
    warnings.simplefilter("ignore")
    ent = build_entities(period=period, geography=geo)
    pairs = person_pairs(ent, ("SIH-RD", "patient"), ("SINASC-DN", "baby"))
    direct = link("sih_neonatal_admissions_to_sinasc", period=period, geography=geo, method="probabilistic",
                  allow_not_viable=True, allow_partial=True).pairs
    sih = role_table("SIH-RD", period=period, geography=geo, roles=["admission.start", "admission.death"],
                     allow_partial=True)
    births = role_table("SINASC-DN", period=period, geography=geo, roles=["baby.birth_date"], allow_partial=True)
    con = duckdb.connect()
    con.register("p", pairs)
    con.register("d", direct.select(["l", "r"]))
    con.register("s", pa.table({"id": record_ids(sih), "start": sih.column("admission.start"),
                                "death": sih.column("admission.death")}))
    con.register("b", pa.table({"id": record_ids(births), "born": births.column("baby.birth_date")}))
    # Entity nodes are "dataset|role|record"; the record id is the last part.
    con.execute("""CREATE TEMP TABLE j AS
        SELECT split_part(p.l, '|', 3) AS l, split_part(p.r, '|', 3) AS r,
               d.l IS NOT NULL AS direct, s.death = '1' AS ended_in_death,
               CAST(s.start - b.born AS INTEGER) AS days
        FROM p LEFT JOIN d ON d.l = split_part(p.l, '|', 3) AND d.r = split_part(p.r, '|', 3)
        LEFT JOIN s ON s.id = split_part(p.l, '|', 3) LEFT JOIN b ON b.id = split_part(p.r, '|', 3)""")
    total = con.execute("SELECT count(*), count(*) FILTER (WHERE direct) FROM j").fetchone()
    rows = con.execute(f"""SELECT CASE WHEN direct THEN 'direct' ELSE 'through other links' END AS route,
            {BANDS} AS age, ended_in_death, count(*) FROM j GROUP BY ALL ORDER BY 1, 2, 3""").fetchall()
    out = {"pairs": total[0], "direct": total[1], "direct_link_pairs": direct.num_rows,
           "by_route_age_death": [list(r) for r in rows]}
    for r in rows:
        print(r, flush=True)
    print("TOTAL", json.dumps({k: out[k] for k in ("pairs", "direct", "direct_link_pairs")}), flush=True)
    (OUT / f"route_pairs_by_age_{geo}_{period}.json").write_text(json.dumps(out, indent=1, default=str),
                                                                 encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
