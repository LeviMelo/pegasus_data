"""Paper 5: labelling at death or selection in life? The race recorded for young people at birth, at earlier hospital admissions and at the
admission in which they died, against the race on their death certificate, by cause of death.

Units: deaths at 15-24 years in 2015-2024 of people born in 2000-2009, residents of municipalities with fewer than 1,600 live births a year
(mean of 2000-2009), where the candidate estimator holds (ADR-0229, ADR-0233). Register: SIH admissions of 2010-2024 of people born in
2000-2009. For each death and hospital race j: candidates, the admissions with its birth date, sex and municipality; control, those of the
other sex, scaled by the ratio of the two sexes' admissions in the municipality and birth year.

Measures, each as N(j, k) = candidates - scaled control summed over the deaths of a group, with k the certified race:
  person    whether the person had any earlier admission recorded j (ending 30 or more days before the death, not in death): one per person
  person180 the same with 180 days
  admission each such admission (weighted by the number of admissions)
  terminal  the admission that ended in death within a day of the death (the record of the dying person)
  placebo   'person' with the admissions' birth dates moved by seven days (the person cannot be among them; N should be near 0)
Groups: cause of death; men only. Margins: among the deaths with an earlier admission, the shares White in hospital and on the
certificate. Intervals: 1,000 bootstrap replicates over municipalities.

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
con.execute("PRAGMA disable_progress_bar; SET memory_limit='1500MB'; SET threads=2")
SIM = f"read_parquet('{LAKE}/SIM/SIM_DO_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
SIH = f"read_parquet('{LAKE}/SIHSUS/SIHSUS_RD_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
SN = f"read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
RACES = ["white", "black", "brown"]
SIMR = {"1": "white", "2": "black", "4": "brown"}
SIHR = {"01": "white", "02": "black", "03": "brown"}   # SIH RACA_COR: 01 branca, 02 preta, 03 parda, 04 amarela, 05 indigena

tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
if "deaths" not in tables:
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
if "adm" not in tables:
    con.execute(f"""CREATE OR REPLACE TABLE adm AS SELECT try_strptime(CAST(NASC AS VARCHAR), '%Y%m%d') dn,
                    CASE trim(SEXO) WHEN '1' THEN '1' WHEN '3' THEN '2' WHEN '2' THEN '2' END sex,
                    left(trim(MUNIC_RES), 6) mun, trim(RACA_COR) j, try_strptime(CAST(DT_SAIDA AS VARCHAR), '%Y%m%d') ds, coalesce(trim(MORTE), '0') = '1' died
                    FROM {SIH} WHERE year BETWEEN 2010 AND 2024 AND NASC BETWEEN '20000101' AND '20091231'
                    AND left(trim(MUNIC_RES), 6) IN (SELECT mun FROM (SELECT DISTINCT mun FROM deaths))""")
n = con.execute("SELECT (SELECT count(*) FROM deaths), (SELECT count(*) FROM adm)").fetchone()
print("deaths", n[0], "admissions", n[1], flush=True)
con.execute("""CREATE OR REPLACE TABLE scale AS SELECT mun, year(dn) by_, count(*) FILTER (sex = '1') m, count(*) FILTER (sex = '2') f FROM adm GROUP BY 1, 2""")
con.execute("CREATE OR REPLACE TABLE d AS SELECT row_number() OVER () id, * FROM deaths")


def per_death(shift_days=0, window="before30"):
    """Per death and hospital race: candidates and controls (admissions and persons) for the admission window."""
    cond = {"before30": "a.ds < d.dd - INTERVAL 30 DAY AND NOT a.died", "before180": "a.ds < d.dd - INTERVAL 180 DAY AND NOT a.died",
            "terminal": "a.died AND abs(date_diff('day', a.ds, d.dd)) <= 1"}[window]
    return con.execute(f"""
        WITH hits AS (SELECT d.id, a.j, (a.sex = d.sex)::INT same FROM d JOIN adm a ON a.dn = d.dn + INTERVAL {shift_days} DAY AND a.mun = d.mun AND {cond}),
        agg AS (SELECT id, j, sum(same) cand, sum(1 - same) ctrl, max(same) cand_any, max(1 - same) ctrl_any FROM hits GROUP BY 1, 2)
        SELECT d.id, d.mun, d.sex, d.k, d.kind, s.m, s.f, agg.j, agg.cand, agg.ctrl, agg.cand_any, agg.ctrl_any
        FROM agg JOIN d ON agg.id = d.id LEFT JOIN scale s ON s.mun = d.mun AND s.by_ = year(d.dn)""").df()


GROUPS = {"natural": ["natural"], "transport": ["transport"], "suicide": ["suicide"], "other external": ["other external"],
          "assault by firearm": ["assault by firearm"], "other assault": ["other assault"], "legal intervention": ["legal intervention"],
          "all external, not assault": ["transport", "suicide", "other external"], "all assault": ["assault by firearm", "other assault", "legal intervention"]}
deaths = con.execute("SELECT kind, k, sex, count(*) n FROM deaths GROUP BY 1, 2, 3").df()
rng = np.random.default_rng(11)


def prepare(df, person=True):
    df = df.copy()
    df["c"] = np.where(df.sex == "1", df.m / df.f.clip(lower=1), df.f / df.m.clip(lower=1)).astype(float)
    df["est"] = (df.cand_any - df.c * df.ctrl_any) if person else (df.cand - df.c * df.ctrl)
    df["kk"], df["jj"] = df.k.map(SIMR), df.j.map(SIHR)
    return df[df.kk.isin(RACES) & df.jj.isin(RACES)]


def summarise(df, kinds, sex=None):
    sub = df[df.kind.isin(kinds) & ((df.sex == sex) if sex else True)]
    # municipality x (hospital race, certified race) table; bootstrap by resampling municipalities with weights
    cube = sub.groupby(["mun", "jj", "kk"]).est.sum().unstack(["jj", "kk"], fill_value=0.0)
    cols = [(j, k) for j in RACES for k in RACES]
    cube = cube.reindex(columns=pd.MultiIndex.from_tuples(cols), fill_value=0.0)
    A = cube.to_numpy()
    W = np.vstack([np.ones(len(A))] + [np.bincount(rng.integers(0, len(A), len(A)), minlength=len(A)) for _ in range(1000)])
    T = W @ A                                                    # replicates x 9 cells
    T = T.reshape(-1, 3, 3)                                      # [replicate, hospital j, certified k]
    out = {"n_est": float(T[0].sum()), "cells": {}}
    for a, j in enumerate(RACES):
        row = T[:, a, :].sum(1)
        for b, k in enumerate(RACES):
            v = T[:, a, b] / np.where(row > 0, row, np.nan)
            out["cells"][f"hospital {j}|certified {k}"] = {"est": float(v[0]), "se": float(np.nanstd(v[1:])), "lo": float(np.nanpercentile(v[1:], 2.5)),
                                                         "hi": float(np.nanpercentile(v[1:], 97.5))}
    for b, k in enumerate(RACES):
        col = T[:, :, b].sum(1)
        for a, j in enumerate(RACES):
            v = T[:, a, b] / np.where(col > 0, col, np.nan)
            out["cells"][f"certified {k}|hospital {j}"] = {"est": float(v[0]), "se": float(np.nanstd(v[1:]))}
    tot = T.sum((1, 2))
    hw, cw = T[:, 0, :].sum(1) / tot, T[:, :, 0].sum(1) / tot
    out["margins"] = {"hospital_white": {"est": float(hw[0]), "se": float(np.std(hw[1:]))}, "certified_white": {"est": float(cw[0]), "se": float(np.std(cw[1:]))},
                      "net_shift": {"est": float(cw[0] - hw[0]), "se": float(np.std(cw[1:] - hw[1:]))}}
    return out


OUT = {"deaths": {g: {r: int(deaths[deaths.kind.isin(v) & (deaths.k.map(SIMR) == r)].n.sum()) for r in RACES} for g, v in GROUPS.items()},
       "deaths_total": {g: int(deaths[deaths.kind.isin(v)].n.sum()) for g, v in GROUPS.items()}}
raw = per_death()
for label, person in (("person", True), ("admission", False)):
    df = prepare(raw, person)
    OUT[label] = {g: summarise(df, v) for g, v in GROUPS.items()}
    OUT[f"{label}_men"] = {g: summarise(df, v, "1") for g, v in GROUPS.items()}
    print(label, {g: round(OUT[label][g]["cells"]["hospital white|certified white"]["est"], 3) for g in ("natural", "assault by firearm", "transport")}, flush=True)
# admissions per death and the share of deaths with an earlier admission (persons, estimated)
pp = prepare(raw, True)
OUT["with_admission"] = {g: float(pp[pp.kind.isin(v)].groupby("id").est.sum().clip(lower=0).sum() / max(OUT["deaths_total"][g], 1)) for g, v in GROUPS.items()}
aa = prepare(raw, False)
OUT["admissions_per_death"] = {g: float(aa[aa.kind.isin(v)].est.sum() / max(OUT["deaths_total"][g], 1)) for g, v in GROUPS.items()}
del raw, pp, aa
OUT["person180"] = {g: summarise(prepare(per_death(window="before180"), True), v) for g, v in GROUPS.items()}
OUT["terminal"] = {g: summarise(prepare(per_death(window="terminal"), True), v) for g, v in GROUPS.items()}
pl = prepare(per_death(shift_days=7), True)
OUT["placebo"] = {g: {"n_est": float(pl[pl.kind.isin(v)].est.sum()), "n_candidates": float(pl[pl.kind.isin(v)].cand_any.sum())} for g, v in GROUPS.items()}
print("terminal", {g: round(OUT["terminal"][g]["cells"]["hospital white|certified white"]["est"], 3) for g in ("natural", "assault by firearm")}, flush=True)
print("placebo", {g: round(OUT["placebo"][g]["n_est"]) for g in ("natural", "assault by firearm")}, flush=True)
(HERE / "results" / "violence.json").write_text(json.dumps(OUT, indent=1), encoding="utf-8")
print("written")
