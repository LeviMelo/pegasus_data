"""Paper 5: labelling at death or selection in life? The race a hospital recorded for a young person at an earlier admission, against the race
on the same person's death certificate, by cause of death.

Units: deaths at 15-24 years in 2015-2024 of people born in 2000-2009, residents of municipalities with fewer than 1,600 live births a year
(where the candidate estimator holds; ADR-0229, ADR-0233). Register: SIH admissions of 2010-2024 of people born in 2000-2009 that ended at
least 30 days before the death and not in death. Candidates: admissions with the death's birth date, sex and municipality of residence;
control: admissions with the same birth date and municipality and the other sex, scaled by the ratio of the two sexes' admissions in the
municipality and birth year. N(j, k) = candidates - scaled control, for hospital race j and certified race k, by cause of death; standard
errors by a bootstrap over municipalities.

Readings. Labelling at death: the hospital recorded future homicide victims White as often as other young people of the same certified race
less often, i.e. the certificate departs from the earlier record more for homicides. Selection in life: the earlier record already shows the
victims as Brown or Black, as the certificate does, so the departure from the birth record happened before death.

    python papers/race_at_death/analysis/violence.py      -> results/violence.json
"""
import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pegasus_data.config import load_settings

warnings.simplefilter("ignore")
HERE = Path(__file__).resolve().parents[1]
LAKE = Path(load_settings().lake_dir).as_posix()
con = duckdb.connect(str(HERE / "data" / "violence.duckdb"))
con.execute("PRAGMA disable_progress_bar; SET memory_limit='8GB'")
SIM = f"read_parquet('{LAKE}/SIM/SIM_DO_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
SIH = f"read_parquet('{LAKE}/SIHSUS/SIHSUS_RD_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
SN = f"read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
RACES = ["white", "black", "brown"]
SIMR = {"1": "white", "2": "black", "4": "brown"}
SIHR = {"01": "white", "02": "black", "03": "brown"}   # SIH RACA_COR: 01 branca, 02 preta, 03 parda, 04 amarela, 05 indigena

con.execute(f"""CREATE OR REPLACE TABLE small AS SELECT left(trim(CODMUNRES), 6) mun FROM {SN} WHERE year BETWEEN 2000 AND 2009
                GROUP BY 1 HAVING count(*) / 10.0 < 1600""")
con.execute(f"""CREATE OR REPLACE TABLE deaths AS SELECT strptime(trim(DTNASC), '%d%m%Y') dn, trim(SEXO) sex, left(trim(CODMUNRES), 6) mun,
                trim(RACACOR) k, strptime(trim(DTOBITO), '%d%m%Y') dd, trim(CAUSABAS) cause
                FROM {SIM} WHERE year BETWEEN 2015 AND 2024 AND trim(IDADE) BETWEEN '415' AND '424' AND trim(SEXO) IN ('1', '2')
                AND try_strptime(trim(DTNASC), '%d%m%Y') BETWEEN DATE '2000-01-01' AND DATE '2009-12-31'
                AND try_strptime(trim(DTOBITO), '%d%m%Y') IS NOT NULL AND left(trim(CODMUNRES), 6) IN (SELECT mun FROM small)""")
con.execute("""ALTER TABLE deaths ADD COLUMN kind VARCHAR; UPDATE deaths SET kind = CASE
                WHEN cause BETWEEN 'X93' AND 'X95ZZ' THEN 'assault by firearm' WHEN cause BETWEEN 'X85' AND 'Y09ZZ' THEN 'other assault'
                WHEN cause BETWEEN 'Y35' AND 'Y36ZZ' THEN 'legal intervention' WHEN cause BETWEEN 'X60' AND 'X84ZZ' THEN 'suicide'
                WHEN cause BETWEEN 'V01' AND 'V99ZZ' THEN 'transport' WHEN left(cause, 1) IN ('V', 'W', 'X', 'Y') THEN 'other external'
                ELSE 'natural' END""")
con.execute(f"""CREATE OR REPLACE TABLE adm AS SELECT CAST(NASC AS VARCHAR) nasc, CASE trim(SEXO) WHEN '1' THEN '1' WHEN '3' THEN '2' WHEN '2' THEN '2' END sex,
                left(trim(MUNIC_RES), 6) mun, trim(RACA_COR) j, try_strptime(CAST(DT_SAIDA AS VARCHAR), '%Y%m%d') ds, year
                FROM {SIH} WHERE year BETWEEN 2010 AND 2024 AND NASC BETWEEN '20000101' AND '20091231' AND coalesce(trim(MORTE), '0') <> '1'
                AND left(trim(MUNIC_RES), 6) IN (SELECT mun FROM small)""")
con.execute("ALTER TABLE adm ADD COLUMN dn DATE; UPDATE adm SET dn = try_strptime(nasc, '%Y%m%d')")
n = con.execute("SELECT (SELECT count(*) FROM deaths), (SELECT count(*) FROM adm), (SELECT count(*) FROM small)").fetchone()
print("deaths", n[0], "admissions", n[1], "small municipalities", n[2], flush=True)
# the scale of the control: admissions of the same sex over admissions of the other sex, by municipality and birth year
con.execute("""CREATE OR REPLACE TABLE scale AS SELECT mun, year(dn) by_, count(*) FILTER (sex = '1') m, count(*) FILTER (sex = '2') f FROM adm GROUP BY 1, 2""")
cells = con.execute("""
    WITH d AS (SELECT row_number() OVER () id, * FROM deaths),
    hits AS (SELECT d.id, a.j, (a.sex = d.sex)::INT same FROM d JOIN adm a ON a.dn = d.dn AND a.mun = d.mun AND a.ds < d.dd - INTERVAL 30 DAY),
    agg AS (SELECT id, j, sum(same) cand, sum(1 - same) ctrl FROM hits GROUP BY 1, 2)
    SELECT d.id, d.mun, d.sex, d.k, d.kind, s.m, s.f, agg.j, coalesce(agg.cand, 0) cand, coalesce(agg.ctrl, 0) ctrl
    FROM d LEFT JOIN agg ON agg.id = d.id LEFT JOIN scale s ON s.mun = d.mun AND s.by_ = year(d.dn)""").df()
cells = cells.dropna(subset=["id"])
cells["c"] = np.where(cells.sex == "1", cells.m / cells.f.clip(lower=1), cells.f / cells.m.clip(lower=1)).astype(float)
cells["est"] = cells.cand - cells.c * cells.ctrl
cells["kk"] = cells.k.map(SIMR)
cells["jj"] = cells.j.map(SIHR)
deaths = con.execute("SELECT kind, k, count(*) n FROM deaths GROUP BY 1, 2").df()
GROUPS = {"natural": ["natural"], "transport": ["transport"], "suicide": ["suicide"], "assault by firearm": ["assault by firearm"],
          "other assault": ["other assault"], "legal intervention": ["legal intervention"], "all assault": ["assault by firearm", "other assault", "legal intervention"]}


def table(df):
    t = df[df.kk.isin(RACES) & df.jj.isin(RACES)].groupby(["jj", "kk"]).est.sum().unstack(fill_value=0.0).reindex(index=RACES, columns=RACES, fill_value=0.0)
    return t


out = {"deaths": {k: {r: int(deaths[(deaths.kind.isin(v)) & (deaths.k.map(SIMR) == r)].n.sum()) for r in RACES} for k, v in GROUPS.items()}}
rng = np.random.default_rng(11)
muns = cells.mun.unique()
bym = {m_: g for m_, g in cells.groupby("mun")}
for g, kinds in GROUPS.items():
    sub = cells[cells.kind.isin(kinds)]
    t = table(sub)
    found = {r: float(sub[sub.kk == r].groupby("id").est.sum().clip(lower=0).sum() / max(out["deaths"][g][r], 1)) for r in RACES}
    reps = []
    groups = {m_: x for m_, x in sub.groupby("mun")}
    keys = np.array(list(groups))
    for _ in range(200):
        reps.append(table(pd.concat([groups[m_] for m_ in rng.choice(keys, len(keys))])))
    res = {"records_found": found, "cells": {}}
    for k in RACES:            # among deaths certified k, the race the earlier admission recorded
        col = t[k].sum()
        for j in RACES:
            vals = [r_[k][j] / r_[k].sum() if r_[k].sum() > 0 else np.nan for r_ in reps]
            res["cells"][f"certified {k}|hospital {j}"] = {"est": float(t[k][j] / col) if col > 0 else None, "se": float(np.nanstd(vals)), "n_est": float(col)}
    for j in RACES:            # among earlier admissions recorded j, the race certified at death
        row = t.loc[j].sum()
        for k in RACES:
            vals = [r_.loc[j][k] / r_.loc[j].sum() if r_.loc[j].sum() > 0 else np.nan for r_ in reps]
            res["cells"][f"hospital {j}|certified {k}"] = {"est": float(t.loc[j][k] / row) if row > 0 else None, "se": float(np.nanstd(vals)), "n_est": float(row)}
    out[g] = res
    print(g, {k_: (round(v["est"], 3) if v["est"] is not None else None, round(v["se"], 3)) for k_, v in res["cells"].items() if k_.startswith("hospital white")}, flush=True)
(HERE / "results" / "violence.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("written")
