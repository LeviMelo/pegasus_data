"""How do the systems record race for the same person? (linked pairs, held out of linking)

Usage: python scripts/race_across_systems.py PERIOD GEO

1. SINASC: the baby's race against the mother's, row by row and by state
   (is the baby's field a copy?).
2. For every stored probabilistic link of the scope whose two sides carry
   race, the cross-tabulation of one system's race against the other's for
   the same person. No link uses race, so the pairs are not selected for
   agreeing on it.

Run under the data home that holds the links. Writes
data/probes/linkage/race_across_systems_<geo>_<period>.json.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc

from pegasus_data.config import load_settings
from pegasus_data.linkage.roles import role_table

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"
ROLES = {
    "SINASC-DN": ["baby.race", "mother.race", "mother.residence"],
    "SIM-DO": ["deceased.race"],
    "SIH-RD": ["patient.race"],
}
# spec -> (left dataset, left race role, right dataset, right race role, whose race)
LINKS = {
    "sinasc_births_to_delivery_admission": ("SINASC-DN", "mother.race", "SIH-RD", "patient.race", "the mother"),
    "sih_deaths_to_sim": ("SIH-RD", "patient.race", "SIM-DO", "deceased.race", "the deceased"),
    "sim_infant_deaths_to_sinasc": ("SIM-DO", "deceased.race", "SINASC-DN", "baby.race", "the baby"),
    "sim_infant_deaths_to_sinasc/mother": ("SIM-DO", "deceased.race", "SINASC-DN", "mother.race", "baby (SIM) vs mother (SINASC)"),
    "sih_neonatal_admissions_to_sinasc": ("SIH-RD", "patient.race", "SINASC-DN", "baby.race", "the baby"),
    "sim_maternal_deaths_to_admission": ("SIM-DO", "deceased.race", "SIH-RD", "patient.race", "the mother"),
}


def _ids(t: pa.Table) -> pa.Array:
    return pc.binary_join_element_wise(pc.cast(t.column("_blob_sha256"), pa.string()),
                                       pc.cast(t.column("_row"), pa.string()), ":")


def _tab(con: duckdb.DuckDBPyConnection, a: str, b: str, src: str) -> dict:
    rows = con.execute(f'SELECT "{a}", "{b}", count(*) FROM {src} GROUP BY 1, 2 ORDER BY 3 DESC').fetchall()
    both = [(x, y, n) for x, y, n in rows if x is not None and y is not None]
    n_both = sum(n for *_, n in both)
    return {
        "pairs": sum(n for *_, n in rows),
        "left_filled": sum(n for x, _, n in rows if x is not None),
        "right_filled": sum(n for _, y, n in rows if y is not None),
        "both_filled": n_both,
        "agree_percent": round(100 * sum(n for x, y, n in both if x == y) / n_both, 2) if n_both else None,
        "crosstab": [[x, y, n] for x, y, n in rows],
    }


def main(period: str, geo: str) -> None:
    warnings.simplefilter("ignore")
    con = duckdb.connect()
    for ds, roles in ROLES.items():
        t = role_table(ds, period=period, geography=geo, roles=roles, allow_partial=True, max_download=10**8)
        con.register(ds.replace("-", "_"), pa.table({"id": _ids(t), **{r: t.column(r) for r in roles}}))
        print(f"loaded {ds}", flush=True)
    out: dict = {}
    out["sinasc_baby_vs_mother"] = _tab(con, "baby.race", "mother.race", "SINASC_DN")
    out["sinasc_baby_vs_mother_by_state"] = [
        list(r) for r in con.execute("""SELECT substr("mother.residence", 1, 2) uf, count(*),
            count(*) FILTER (WHERE "baby.race" IS NOT NULL AND "mother.race" IS NOT NULL),
            round(100.0 * count(*) FILTER (WHERE "baby.race" = "mother.race")
                  / nullif(count(*) FILTER (WHERE "baby.race" IS NOT NULL AND "mother.race" IS NOT NULL), 0), 2)
            FROM SINASC_DN GROUP BY 1 ORDER BY 1""").fetchall()]
    print("sinasc", json.dumps({k: v for k, v in out["sinasc_baby_vs_mother"].items() if k != "crosstab"}), flush=True)
    lake = load_settings().lake_dir / "links"
    for name, (left, lrole, right, rrole, whose) in LINKS.items():
        spec = name.split("/")[0]
        runs = sorted((lake / spec).glob(f"probabilistic_{geo}_{period}_*.parquet"))
        if not runs:
            continue
        con.execute(f"""CREATE OR REPLACE TEMP TABLE j AS SELECT l."{lrole}" AS "left", r."{rrole}" AS "right"
            FROM '{runs[-1]}' p JOIN {left.replace("-", "_")} l ON p.l = l.id
            JOIN {right.replace("-", "_")} r ON p.r = r.id""")
        res = {"whose": whose, "left": f"{left} {lrole}", "right": f"{right} {rrole}", **_tab(con, "left", "right", "j")}
        out[name] = res
        print(name, json.dumps({k: v for k, v in res.items() if k != "crosstab"}), flush=True)
    (OUT / f"race_across_systems_{geo}_{period}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                                                  encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
