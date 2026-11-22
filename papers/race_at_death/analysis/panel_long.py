"""Paper 1: the long panel. Does a municipality's death certificate follow its population when that population changes?

Unit: municipality-year, 2000-2023. Outcome: the certificate's excess White, logit(share certified White among infant deaths with a race)
minus logit(share White among the year's live births with a race). The birth record classified the newborn by observation until 2010 and
records the mother's declaration from 2012 (2011 is the transition and is left out), so the two periods are fitted apart. Exposure: the
census share of White residents (2000, 2010, 2022, IBGE universe and sample tables held by pegasus_data), interpolated on the logit scale
between censuses. Models: municipality fixed effects and state-by-year effects, weighted by infant deaths, errors clustered by immediate
region; a placebo with the composition four years ahead (lead), which a certificate following its present population should not need.

    python papers/race_at_death/analysis/panel_long.py     -> results/panel_long.json
"""
import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyfixest as pf

from pegasus_data.config import load_settings
from pegasus_data.fields import load_field

warnings.simplefilter("ignore")
HERE = Path(__file__).resolve().parents[1]
LAKE = Path(load_settings().lake_dir).as_posix()
con = duckdb.connect()
con.execute("PRAGMA disable_progress_bar; SET memory_limit='6GB'")
SIM = f"read_parquet('{LAKE}/SIM/SIM_DO_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
SN = f"read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
INF = "(left(trim(IDADE), 1) IN ('0', '1', '2') OR trim(IDADE) BETWEEN '300' AND '399')"
deaths = con.execute(f"""SELECT left(trim(CODMUNRES), 6) mun, CAST(year AS INT) AS "year", count(*) FILTER (trim(RACACOR) IN ('1','2','3','4','5')) d,
                         count(*) FILTER (trim(RACACOR) = '1') dw FROM {SIM} WHERE year BETWEEN 2000 AND 2023 AND {INF} GROUP BY 1, 2""").df()
births = con.execute(f"""SELECT left(trim(CODMUNRES), 6) mun, CAST(year AS INT) AS "year",
                         count(*) FILTER (trim(CASE WHEN year <= 2010 THEN RACACOR ELSE RACACORMAE END) IN ('1','2','3','4','5')) b,
                         count(*) FILTER (trim(CASE WHEN year <= 2010 THEN RACACOR ELSE RACACORMAE END) = '1') bw
                         FROM {SN} WHERE year BETWEEN 2000 AND 2023 GROUP BY 1, 2""").df()
C = {}
for nm in ("population_white", "population_race_universe"):
    t = load_field(nm, years=[2000, 2010, 2022]).to_pandas()
    t = t[t.status.isin(["value", "ok"])]
    C[nm] = t.groupby(["municipality", "year"]).value.sum()
C = pd.DataFrame(C).reset_index().rename(columns={"municipality": "mun"})
C["lc"] = np.log((C.population_white / C.population_race_universe).clip(0.005, 0.995) / (1 - (C.population_white / C.population_race_universe).clip(0.005, 0.995)))
CW = C.pivot(index="mun", columns="year", values="lc").dropna()


def interp(row, y):
    if y <= 2010:
        a, b, y0, y1 = row[2000], row[2010], 2000, 2010
    else:
        a, b, y0, y1 = row[2010], row[2022], 2010, 2022
    return a + (b - a) * (min(y, y1) - y0) / (y1 - y0) if y <= y1 else b + (b - a) * (y - y1) / (y1 - y0)


P = deaths.merge(births, on=["mun", "year"]).query("d >= 5 and b >= 30 and dw > 0 and dw < d and bw > 0 and bw < b")
P = P[P.mun.isin(CW.index)]
P["lc"] = [interp(CW.loc[m], y) for m, y in zip(P.mun, P.year, strict=True)]
P["lc_lead"] = [interp(CW.loc[m], min(y + 4, 2022 if y > 2010 else 2010)) for m, y in zip(P.mun, P.year, strict=True)]
P["excess"] = np.log(P.dw / (P.d - P.dw)) - np.log(P.bw / (P.b - P.bw))
P["uf"] = P.mun.str[:2]
imm = pd.read_parquet(HERE / "data" / "municipal_context.parquet", columns=["mun", "immediate"])
P = P.merge(imm, on="mun", how="left")
P["uf_year"] = P.uf + "_" + P.year.astype(str)
out = {}
for lab, sub in (("2000-2010 (newborn observed)", P[P.year <= 2010]), ("2012-2023 (mother declared)", P[P.year >= 2012])):
    r = {"unit_years": int(len(sub)), "municipalities": int(sub.mun.nunique()),
         "sd_within_lc": float((sub.lc - sub.groupby("mun").lc.transform("mean")).std()), "sd_between_lc": float(sub.groupby("mun").lc.mean().std())}
    for name, f in (("within", "excess ~ lc | mun + uf_year"), ("within_with_lead", "excess ~ lc + lc_lead | mun + uf_year"),
                    ("between", "excess ~ lc | uf_year")):
        m = pf.feols(f, data=sub, weights="d", vcov={"CRV1": "immediate"})
        r[name] = {t: {"est": float(m.coef()[t]), "se": float(m.se()[t])} for t in m.coef().index}
    out[lab] = r
    print(lab, json.dumps(r)[:600], flush=True)
(HERE / "results" / "panel_long.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("written")
