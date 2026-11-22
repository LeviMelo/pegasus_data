"""Paper 3, review 2026-11-22 (3.2, 3.3, 3.4): is the birth record's "declaration" the mother's, where is the hospital's practice, and whom
does the comparison leave out?

3.2 The birth record and the admission are both written in the delivery hospital. If the birth record's race were the mother's own answer,
    a hospital's share of mothers declared Black would follow the population it serves, whatever the hospital's admission practice. Per
    delivery hospital (births of 2012-2023 linked to their delivery admissions, data/deliveries/), the observed share of mothers declared Black
    on the birth record against the share expected from the 2022 Census (women aged 15-49 who declared themselves Black in each mother's
    municipality of residence, IBGE table 9606), set against the hospital's admission practice (the share of its birth-record-Black mothers
    the admission records as Black, shrunk toward the national rate). A positive slope means hospitals that rarely record Black on the
    admission also record fewer Black mothers on the birth record than their population holds: the "declaration" there is partly the hospital's.
    Rival: hospitals of one municipality serve different mothers (schooling held; the expected share uses the municipality of residence).
3.3 The admission practice by state, with intervals from a bootstrap over hospitals.
3.4 Whom the linked deliveries (public-system admissions) leave out: all SINASC births of 2016 and 2021 by the mother's schooling and race,
    against the linked ones.

    python papers/race_at_death/analysis/hospital_declaration.py   -> results/hospital_declaration.json
"""
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from pegasus_data.config import load_settings

HERE = Path(__file__).resolve().parents[1]
LAKE = Path(load_settings().lake_dir).as_posix()
OUT = HERE / "results" / "hospital_declaration.json"
con = duckdb.connect()
con.execute("PRAGMA disable_progress_bar; SET memory_limit='1500MB'; SET threads=2")
DEL = (HERE / "data" / "deliveries" / "*.parquet").as_posix()
UF = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
      "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
      "51": "MT", "52": "GO", "53": "DF"}

# census 2022: the share Black (and White) among women aged 15-49, by municipality
CW = pd.read_parquet(HERE / "data" / "census2022_women_15_49_race.parquet")
CW = CW[CW.c86.isin([2776, 2777, 2778, 2779, 2780])]
CW["mun"] = CW.locality.astype(str).str[:6]
t = CW.pivot_table(index="mun", columns="c86", values="value", aggfunc="sum").fillna(0)
cen = pd.DataFrame({"mun": t.index, "cen_black": (t[2777] / t.sum(1)).to_numpy(), "cen_white": (t[2776] / t.sum(1)).to_numpy()})
con.register("cen", cen)
print(con.execute(f"SELECT DISTINCT racacormae, patient_race FROM '{DEL}' LIMIT 20").fetchall(), flush=True)

# per hospital: mothers, declared Black on the birth record, expected Black from the census, and the admission practice
H = con.execute(f"""SELECT admission_facility h, left(any_value(codmunres), 2) uf, count(*) n,
                           sum((racacormae = '2')::INT) dn_black, sum(c.cen_black) exp_black,
                           sum((racacormae = '1')::INT) dn_white, sum(c.cen_white) exp_white,
                           sum((racacormae = '2' AND patient_race IS NOT NULL)::INT) black_known,
                           sum((racacormae = '2' AND patient_race = 'black')::INT) black_rec_black,
                           avg((escmae IN ('4', '5'))::INT) school_8plus
                    FROM '{DEL}' d JOIN cen c ON c.mun = left(d.codmunres, 6)
                    WHERE admission_facility IS NOT NULL AND racacormae IN ('1', '2', '3', '4', '5') GROUP BY 1""").df()
nat = H.black_rec_black.sum() / H.black_known.sum()
a0 = 10.0                                                        # prior strength of the shrinkage, in births
H["practice"] = (H.black_rec_black + a0 * nat) / (H.black_known + a0)
H = H[H.n >= 100].copy()
lg = lambda p: np.log(np.clip(p, 1e-3, 1 - 1e-3) / (1 - np.clip(p, 1e-3, 1 - 1e-3)))  # noqa: E731
H["oe_black"] = lg(H.dn_black / H.n) - lg(H.exp_black / H.n)
H["oe_white"] = lg(H.dn_white / H.n) - lg(H.exp_white / H.n)
H["lp"] = lg(H.practice)
H["region"] = H.uf.str[0]
R = {"hospitals": int(len(H)), "births": int(H.n.sum()), "national_practice": float(nat)}
for y in ("oe_black", "oe_white"):
    R[y] = {}
    for nm, f in (("raw", f"{y} ~ lp"), ("schooling", f"{y} ~ lp + school_8plus"), ("state", f"{y} ~ lp + school_8plus + C(uf)")):
        m = smf.wls(f, data=H, weights=H.n).fit(cov_type="HC1")
        R[y][nm] = {"slope": float(m.params["lp"]), "se": float(m.bse["lp"])}
H["q"] = pd.qcut(H.practice, 5, labels=False)
R["by_practice_fifth"] = [{"fifth": int(q), "practice": float(np.average(g.practice, weights=g.n)), "dn_black": float(g.dn_black.sum() / g.n.sum()),
                           "expected_black": float(g.exp_black.sum() / g.n.sum()), "dn_white": float(g.dn_white.sum() / g.n.sum()),
                           "expected_white": float(g.exp_white.sum() / g.n.sum()), "hospitals": int(len(g)), "births": int(g.n.sum())} for q, g in H.groupby("q")]
# 3.3 the admission practice by state (all hospitals), bootstrap over hospitals
Hall = con.execute(f"""SELECT admission_facility h, left(any_value(codmunres), 2) uf, sum((racacormae = '2' AND patient_race IS NOT NULL)::INT) k,
                              sum((racacormae = '2' AND patient_race = 'black')::INT) b FROM '{DEL}' WHERE admission_facility IS NOT NULL GROUP BY 1""").df()
rng = np.random.default_rng(5)
st = {}
for uf, g in Hall.groupby("uf"):
    if g.k.sum() < 50:
        continue
    k_, b_ = np.nan_to_num(g.k.to_numpy(dtype=float)), np.nan_to_num(g.b.to_numpy(dtype=float))
    reps = []
    for _ in range(500):
        i = rng.integers(0, len(g), len(g))
        reps.append(b_[i].sum() / max(k_[i].sum(), 1))
    st[UF.get(uf, uf)] = {"est": float(b_.sum() / k_.sum()), "lo": float(np.percentile(reps, 2.5)), "hi": float(np.percentile(reps, 97.5)),
                          "black_mothers": int(k_.sum()), "hospitals": int(len(g)), "region": uf[0]}
R["practice_by_state"] = st
# 3.4 whom the linked deliveries leave out: all births against the linked, by schooling and race (2016 and 2021)
SN = f"read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
cov = {}
for y in (2016, 2021):
    allb = con.execute(f"SELECT trim(ESCMAE) e, trim(RACACORMAE) r, count(*) n FROM {SN} WHERE year = {y} GROUP BY 1, 2").df()
    lnk = con.execute(f"SELECT escmae e, racacormae r, count(*) n FROM '{DEL}' WHERE birth_year = {y} GROUP BY 1, 2").df()
    m = allb.merge(lnk, on=["e", "r"], how="left", suffixes=("_all", "_linked")).fillna(0)
    cov[y] = {"linked_share": float(m.n_linked.sum() / m.n_all.sum()),
              "by_schooling": {e: float(g.n_linked.sum() / g.n_all.sum()) for e, g in m.groupby("e") if g.n_all.sum() > 1000},
              "by_race": {r: float(g.n_linked.sum() / g.n_all.sum()) for r, g in m.groupby("r") if g.n_all.sum() > 1000}}
R["coverage"] = cov
OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
print(json.dumps({k: R[k] for k in ("hospitals", "births", "national_practice", "oe_black", "oe_white")}, indent=0))
print([(round(b["practice"], 2), round(b["dn_black"], 3), round(b["expected_black"], 3), round(b["dn_white"], 3), round(b["expected_white"], 3)) for b in R["by_practice_fifth"]])
print(sorted([(k, round(v["est"], 2)) for k, v in st.items()], key=lambda x: x[1]))
print(json.dumps(cov, indent=0)[:1500])
