"""Race as each setting's classification of the same persons (theory §5, step T4).

Usage: python scripts/race_settings.py PERIOD GEO

1. Persons from the stored links (entities.py); each record's race from its
   dataset. SINASC's baby race is excluded: it is the mother's (EVALUATION
   2026-10-02, 100.0% equal), not a classification of the baby.
2. Dawid–Skene (annotators.py) with the systems as settings: each system's
   confusion matrix against the consensus.
3. The "asian" hypothesis: SIH records asian where the other systems record
   brown. If that is code mixing (SIM/SINASC's 4 = brown written into SIH's
   field, where 04 = asian), it concentrates in particular hospitals; if it is
   classification noise, it spreads with volume.

Writes data/probes/linkage/race_settings_<geo>_<period>.json.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import duckdb
import pyarrow as pa

from pegasus_data.linkage.annotators import fit
from pegasus_data.linkage.entities import build_entities
from pegasus_data.linkage.identity import record_ids as _ids
from pegasus_data.linkage.roles import role_table

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"
# (dataset, person role in entities, race role, extra roles)
SOURCES = [
    ("SINASC-DN", "mother", "mother.race", []),
    ("SIM-DO", "deceased", "deceased.race", []),
    ("SIH-RD", "patient", "patient.race", ["admission.facility"]),
]




def main(period: str, geo: str) -> None:
    warnings.simplefilter("ignore")
    ent = build_entities(period=period, geography=geo)
    con = duckdb.connect()
    con.register("nodes", ent.nodes)
    parts = []
    for ds, prole, rrole, extra in SOURCES:
        t = role_table(ds, period=period, geography=geo, roles=[rrole, *extra], allow_partial=True)
        cols = {"record": _ids(t), "race": t.column(rrole)}
        cols["facility"] = t.column("admission.facility") if extra else pa.nulls(t.num_rows, pa.string())
        name = ds.replace("-", "_")
        con.register(name, pa.table(cols))
        parts.append(f"""SELECT n.person, '{ds}' AS setting, x.race AS label, x.facility FROM nodes n
                         JOIN {name} x ON x.record = n.record WHERE n.dataset = '{ds}' AND n.role = '{prole}'""")
        print("loaded", ds, flush=True)
    con.execute("CREATE TABLE obs AS " + " UNION ALL ".join(parts))
    model = fit(con.execute("SELECT person, setting, label FROM obs").fetch_arrow_table())
    out = {"dawid_skene_by_system": model.summary()}
    print(json.dumps(out["dawid_skene_by_system"]["settings"], indent=1)[:3000], flush=True)
    # The asian hypothesis, by hospital: SIH says asian where SINASC or SIM (same person) says brown.
    con.execute("""CREATE TABLE pairs AS SELECT h.facility, h.label AS sih, o.label AS other FROM obs h
                   JOIN obs o ON o.person = h.person AND o.setting <> 'SIH-RD'
                   WHERE h.setting = 'SIH-RD' AND h.label IS NOT NULL AND o.label IS NOT NULL""")
    rows = con.execute("""SELECT facility, count(*) n, count(*) FILTER (WHERE other = 'brown') brown_elsewhere,
                          count(*) FILTER (WHERE other = 'brown' AND sih = 'asian') brown_as_asian
                          FROM pairs GROUP BY 1""").fetchall()
    total_brown = sum(r[2] for r in rows)
    total_asian = sum(r[3] for r in rows)
    ranked = sorted(rows, key=lambda r: -r[3])
    cum, top = 0, []
    for fac, n, brown, asian in ranked:
        cum += asian
        top.append({"facility": fac, "pairs": n, "brown_elsewhere": brown, "recorded_asian": asian,
                    "share_of_brown_recorded_asian": round(asian / brown, 4) if brown else None,
                    "cumulative_share_of_all_brown_as_asian": round(cum / total_asian, 4) if total_asian else None})
    hospitals_with_brown = sum(1 for r in rows if r[2] > 0)
    hospitals_with_any = sum(1 for r in rows if r[3] > 0)
    out["asian_by_hospital"] = {
        "brown_elsewhere": total_brown, "recorded_asian_in_sih": total_asian,
        "hospitals_with_brown_persons": hospitals_with_brown, "hospitals_recording_any_as_asian": hospitals_with_any,
        "top_hospitals": top[:40],
    }
    print(json.dumps({k: v for k, v in out["asian_by_hospital"].items() if k != "top_hospitals"}), flush=True)
    for row in top[:15]:
        print(row, flush=True)
    # Hierarchical: each SIH hospital is a setting, shrunk toward SIH as a whole.
    hosp = con.execute("""SELECT person, CASE WHEN setting = 'SIH-RD' THEN 'SIH:' || coalesce(facility, '?')
                          ELSE setting END AS setting, label FROM obs""").fetch_arrow_table()
    settings = set(hosp.column("setting").to_pylist())
    hm = fit(hosp, groups={x: "SIH-RD" for x in settings if x.startswith("SIH:")})
    cls = {c: i for i, c in enumerate(hm.classes)}
    rows = []
    for i, name in enumerate(hm.settings):
        if not name.startswith("SIH:"):
            continue
        rows.append({"facility": name[4:], "observations": int(hm.observations_per_setting[i]),
                     "asian_given_brown": round(float(hm.confusion[i, cls["brown"], cls["asian"]]), 4),
                     "brown_given_black": round(float(hm.confusion[i, cls["black"], cls["brown"]]), 4),
                     "white_given_brown": round(float(hm.confusion[i, cls["brown"], cls["white"]]), 4)})
    sih_level = {k: v for k, v in hm.summary()["settings"].items() if not k.startswith("SIH:")}
    out["hierarchical"] = {
        "consensus_prior": hm.summary()["consensus_prior"], "persons": hm.persons,
        "system_settings": sih_level,
        "hospitals": len(rows),
        "hospitals_asian_given_brown_over_50pct": sum(1 for r in rows if r["asian_given_brown"] > 0.5),
        "hospitals_brown_given_black_over_50pct": sum(1 for r in rows if r["brown_given_black"] > 0.5),
        "top_asian_given_brown": sorted(rows, key=lambda r: -r["asian_given_brown"])[:25],
        "top_brown_given_black": sorted([r for r in rows if r["observations"] >= 200],
                                        key=lambda r: -r["brown_given_black"])[:25],
    }
    print(json.dumps({k: v for k, v in out["hierarchical"].items() if not k.startswith("top_")}, indent=1)[:4000],
          flush=True)
    (OUT / f"race_settings_{geo}_{period}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                                           encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
