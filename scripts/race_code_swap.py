"""Is SIH's "asian" in certain hospitals SIM/SINASC's code for brown? (theory §5, T4)

Usage: python scripts/race_code_swap.py PERIOD [CNES ...]

SIM and SINASC number race 1 white, 2 black, 3 asian, 4 brown, 5 indigenous;
SIH numbers it 01 white, 02 black, 03 brown, 04 asian, 05 indigenous. A
hospital whose software writes the SIM numbering into SIH's field records
brown persons as 04 (read "asian") and asian persons as 03 (read "brown").
Classification noise would do neither systematically.

For each hospital: the raw RACA_COR distribution of all its admissions, by
month; and, for the persons linked to SIM (deaths) or SINASC (deliveries),
the SIH code against the race the other system records. The swap predicts
04 for persons brown elsewhere AND 03 for persons asian elsewhere.

Run under the data home that holds the links. Writes
data/probes/linkage/race_code_swap_<period>.json.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import duckdb
import pyarrow as pa

from pegasus_data import link
from pegasus_data.config import load_settings
from pegasus_data.linkage.roles import record_ids, role_table

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"
DEFAULT = ["2499363", "7866801", "2705982", "7254628", "8015899", "2473046", "2362821", "2006197"]
LINKS = {  # spec -> (SIH side, other dataset, the other side's race role)
    "sih_deaths_to_sim": ("l", "SIM-DO", "deceased.race"),
    "sinasc_births_to_delivery_admission": ("r", "SINASC-DN", "mother.race"),
}


def main(period: str, hospitals: list[str]) -> None:
    warnings.simplefilter("ignore")
    hospitals = hospitals or DEFAULT
    lake = load_settings().lake_dir
    con = duckdb.connect()
    con.execute(f"""CREATE VIEW sih AS SELECT * FROM read_parquet('{lake.as_posix()}/SIHSUS/*/*/uf=*/year={period}/*.parquet',
                    union_by_name=true, hive_partitioning=true)""")
    listed = ", ".join(f"'{h}'" for h in hospitals)
    out: dict = {"monthly": [list(r) for r in con.execute(f"""
        SELECT CNES, substr(CAST(DT_SAIDA AS VARCHAR), 1, 6) AS month, count(*) AS n,
               round(100.0 * count(*) FILTER (WHERE RACA_COR = '03') / count(*), 1) AS sih_03,
               round(100.0 * count(*) FILTER (WHERE RACA_COR = '04') / count(*), 1) AS sih_04
        FROM sih WHERE CNES IN ({listed}) GROUP BY ALL ORDER BY 1, 2""").fetchall()]}
    adm = role_table("SIH-RD", period=period, geography="BR", roles=["admission.facility"], allow_partial=True)
    con.register("adm", pa.table({"id": record_ids(adm), "cnes": adm.column("admission.facility")}))
    con.execute(f"""CREATE TEMP TABLE code AS SELECT {_raw_id()} AS id, RACA_COR AS code FROM
                    (SELECT *, row_number() OVER (PARTITION BY _source_path, _record_key ORDER BY _row) AS _dup FROM sih)
                    WHERE CNES IN ({listed})""")
    rows = []
    for spec, (side, other_ds, race_role) in LINKS.items():
        pairs = link(spec, period=period, geography="BR", method="probabilistic", allow_partial=True,
                     allow_not_viable=True).pairs
        other = role_table(other_ds, period=period, geography="BR", roles=[race_role], allow_partial=True)
        con.register("p", pairs.select(["l", "r"]))
        con.register("o", pa.table({"id": record_ids(other), "race": other.column(race_role)}))
        sih_side, other_side = (side, "r" if side == "l" else "l")
        rows += con.execute(f"""SELECT '{spec}', a.cnes, o.race, c.code, count(*)
            FROM p JOIN adm a ON a.id = p.{sih_side} JOIN code c ON c.id = p.{sih_side}
            JOIN o ON o.id = p.{other_side} WHERE a.cnes IN ({listed}) GROUP BY ALL ORDER BY 2, 3, 4""").fetchall()
    out["linked"] = [list(r) for r in rows]
    con.register("lk", pa.table({"spec": [r[0] for r in rows], "cnes": [r[1] for r in rows],
                                 "race": [r[2] for r in rows], "code": [r[3] for r in rows],
                                 "n": [r[4] for r in rows]}))
    out["by_hospital"] = [list(r) for r in con.execute("""
        SELECT cnes,
          sum(n) FILTER (WHERE race = 'brown') AS brown_elsewhere,
          sum(n) FILTER (WHERE race = 'brown' AND code = '04') AS brown_as_04,
          sum(n) FILTER (WHERE race = 'asian') AS asian_elsewhere,
          sum(n) FILTER (WHERE race = 'asian' AND code = '03') AS asian_as_03,
          sum(n) FILTER (WHERE race = 'asian' AND code = '04') AS asian_as_04,
          sum(n) FILTER (WHERE race = 'white') AS white_elsewhere,
          sum(n) FILTER (WHERE race = 'white' AND code = '01') AS white_as_01,
          sum(n) FILTER (WHERE race = 'black') AS black_elsewhere,
          sum(n) FILTER (WHERE race = 'black' AND code = '02') AS black_as_02
        FROM lk GROUP BY 1 ORDER BY 2 DESC""").fetchall()]
    for r in out["by_hospital"]:
        print(r, flush=True)
    (OUT / f"race_code_swap_{period}.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print("DONE", flush=True)


def _raw_id() -> str:
    from pegasus_data.linkage.roles import RECORD_ID_SQL

    return RECORD_ID_SQL


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
