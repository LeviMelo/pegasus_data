"""How many linked pairs break a hard rule (ADR-0119 consequence)?

Usage: python scripts/link_impossibility.py PERIOD GEO

For each stored probabilistic link of the scope, counts pairs whose two
records cannot be the same person and event: a death before the admission
began, a birth after the event, a death recorded outside any health facility
matched to an admission that ended in death. Run under the data home that
holds the links. Writes data/probes/linkage/impossibility_<geo>_<period>.json.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import duckdb
import pyarrow as pa

from pegasus_data.config import load_settings
from pegasus_data.linkage.identity import record_ids as _ids
from pegasus_data.linkage.roles import role_table

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"
FACILITY_PLACES = "('hospital', 'other health facility')"

# spec -> (left dataset, right dataset, {rule name: SQL over l.* and r.*})
RULES = {
    "sih_deaths_to_sim": ("SIH-RD", "SIM-DO", {
        "death before admission": 'r."death.date" < l."admission.start"',
        "death outside a health facility": f'r."death.place" NOT IN {FACILITY_PLACES}',
        "born after the death": 'l."patient.birth_date" > r."death.date"',
    }),
    "ciha_deaths_to_sim": ("CIHA", "SIM-DO", {
        "death before admission": 'r."death.date" < l."admission.start"',
        "death outside a health facility": f'r."death.place" NOT IN {FACILITY_PLACES}',
    }),
    "sim_maternal_deaths_to_admission": ("SIM-DO", "SIH-RD", {
        "death before admission": 'l."death.date" < r."admission.start"',
        "death outside a health facility": f'l."death.place" NOT IN {FACILITY_PLACES}',
    }),
    "sim_infant_deaths_to_sinasc": ("SIM-DO", "SINASC-DN", {
        "born after the death": 'r."baby.birth_date" > l."death.date"',
    }),
    "sih_neonatal_admissions_to_sinasc": ("SIH-RD", "SINASC-DN", {
        "born after the admission began": 'r."baby.birth_date" > l."admission.start"',
    }),
}
ROLES = {
    "SIH-RD": ["admission.start", "patient.birth_date"],
    "CIHA": ["admission.start"],
    "SIM-DO": ["death.date", "death.place"],
    "SINASC-DN": ["baby.birth_date"],
}




def main(period: str, geo: str) -> None:
    warnings.simplefilter("ignore")
    lake = load_settings().lake_dir / "links"
    con = duckdb.connect()
    for ds, roles in ROLES.items():
        t = role_table(ds, period=period, geography=geo, roles=roles, allow_partial=True, max_download=10**8)
        con.register(ds.replace("-", "_"), pa.table({"id": _ids(t), **{r: t.column(r) for r in roles}}))
        print(f"loaded {ds}", flush=True)
    out = {}
    for spec, (left, right, rules) in RULES.items():
        runs = sorted((lake / spec).glob(f"probabilistic_{geo}_{period}_*.parquet"))
        if not runs:
            continue
        lcols = ", ".join(f'l."{c}" AS "l.{c}"' for c in ROLES[left])
        rcols = ", ".join(f'r."{c}" AS "r.{c}"' for c in ROLES[right])
        con.execute(f"""CREATE OR REPLACE TEMP TABLE j AS SELECT {lcols}, {rcols} FROM '{runs[-1]}' p
            JOIN {left.replace("-", "_")} l ON p.l = l.id JOIN {right.replace("-", "_")} r ON p.r = r.id""")
        res = {"run": runs[-1].name, "pairs": con.execute("SELECT count(*) FROM j").fetchone()[0]}
        for name, sql in rules.items():
            cond = sql.replace('l."', '"l.').replace('r."', '"r.')
            res[name] = con.execute(f"SELECT count(*) FROM j WHERE {cond}").fetchone()[0]
        out[spec] = res
        print(spec, json.dumps(res), flush=True)
    (OUT / f"impossibility_{geo}_{period}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
