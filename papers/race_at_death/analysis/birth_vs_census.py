"""Test B (review 2026-11-22): does the birth record's race of the mother bend toward the local majority?

The mother's colour on SINASC 2021-2023 (RACACOR, the mother's from 2012) against the self-declared colour of women aged
15-49 in the 2022 Census (IBGE table 9606, universe, fetched by pegasus_data into data/census2022_women_15_49_race.parquet),
by municipality. If the birth record follows the census along the whole range of composition, the slope of
logit(share on the birth record) on logit(share in the census) is 1: a constant offset is what fertility differences
between classes give. A slope above 1 means whiter places record their mothers whiter (and browner places browner) than
the women declare themselves: the birth record itself bends toward the local majority.

Rival readings named in the output: fertility differences between classes that vary with composition (checked with the
women aged 20-34, within region and within state), and small-number noise (the binomial GLM weights by births; errors
are quasi-binomial, and a measurement-error correction is not needed for the census, which is a count of the universe).

    python papers/race_at_death/analysis/birth_vs_census.py   -> results/birth_vs_census.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / "results" / "birth_vs_census.json"
RACE = {2776: "W", 2777: "K", 2778: "A", 2779: "P", 2780: "I"}
AGES_PEAK = {93087, 93088, 93089}                      # 20-34

z = np.load(ROOT / "data" / "probes" / "race_own_birth" / "births_by_cohort.npz")
b = z["births"][9:12].sum(0)                           # cohorts 2021-2023 (array starts at 2012): [W, K, A, P, I, none]
S = pd.DataFrame({"mun6": [str(int(m)) for m in z["muns"]], "bW": b[:, 0], "bK": b[:, 1], "bP": b[:, 3], "bdecl": b[:, :5].sum(1), "ball": b.sum(1)})

CN = pd.read_parquet(HERE / "data" / "census2022_women_15_49_race.parquet")
CN = CN[CN.c86.isin(RACE)]
CN["mun6"] = CN.locality.astype(str).str[:6]
CN["r"] = CN.c86.map(RACE)


def census(sel):
    t = CN[sel].pivot_table(index="mun6", columns="r", values="value", aggfunc="sum").fillna(0)
    return pd.DataFrame({"cW": t.W / t.sum(1), "cK": t.K / t.sum(1), "cP": t.P / t.sum(1), "women": t.sum(1)})


D = {}
for nm, sel in (("15-49", CN.c287.notna()), ("20-34", CN.c287.isin(AGES_PEAK))):
    D[nm] = S.merge(census(sel), left_on="mun6", right_index=True, how="inner")
lg = lambda p: np.log(np.clip(p, .002, .998) / (1 - np.clip(p, .002, .998)))  # noqa: E731
R = {"municipalities": int(len(D["15-49"])), "births_declared": int(D["15-49"].bdecl.sum()),
     "blank_share": float(1 - D["15-49"].bdecl.sum() / D["15-49"].ball.sum())}
BINS = [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001]
for cls, num in (("W", "bW"), ("K", "bK"), ("P", "bP")):
    R[cls] = {}
    for nm, d in D.items():
        d = d[d.bdecl > 0].copy()
        d["y"], d["lx"] = d[num] / d.bdecl, lg(d[f"c{cls}"])
        d["uf"], d["region"] = d.mun6.str[:2], d.mun6.str[0]
        out = {"national_birth": float(d[num].sum() / d.bdecl.sum()), "national_census": float((d[f"c{cls}"] * d.women).sum() / d.women.sum())}
        for fe in ("", " + C(region)", " + C(uf)"):
            m = smf.glm(f"y ~ lx{fe}", data=d, family=sm.families.Binomial(), freq_weights=d.bdecl).fit(scale="X2")
            # the quasi-binomial scale above is per birth; the municipality is the unit of dependence, so cluster on it too
            mc = smf.glm(f"y ~ lx{fe}", data=d, family=sm.families.Binomial(), var_weights=d.bdecl).fit(cov_type="HC1")
            out[f"slope{fe.replace(' + C(', '_').replace(')', '') or '_none'}"] = {"slope": float(m.params["lx"]), "se_quasi": float(m.bse["lx"]),
                                                                                 "se_robust": float(mc.bse["lx"]), "intercept": float(m.params["Intercept"])}
        d["bin"] = pd.cut(d[f"c{cls}"], BINS, labels=False, right=False)
        out["bins"] = [{"bin": int(k), "census": float(np.average(g[f"c{cls}"], weights=g.women)), "birth": float(g[num].sum() / g.bdecl.sum()),
                        "municipalities": int(len(g)), "births": int(g.bdecl.sum())} for k, g in d.groupby("bin")]
        # departure from the diagonal at the ends of the range, after the national offset (fertility) is removed
        off = lg(out["national_birth"]) - lg(out["national_census"])
        d["pred"] = 1 / (1 + np.exp(-(d.lx + off)))
        out["departure_by_bin"] = [{"bin": int(k), "observed_less_constant_offset": float(g[num].sum() / g.bdecl.sum() - np.average(g.pred, weights=g.bdecl))}
                                   for k, g in d.groupby("bin")]
        out["corr"] = float(np.corrcoef(d.y, d[f"c{cls}"])[0, 1])
        R[cls][nm] = out
OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
for cls in ("W", "K", "P"):
    o = R[cls]["15-49"]
    print(cls, "nat", round(o["national_birth"], 3), round(o["national_census"], 3), {k: (round(v["slope"], 3), round(v["se_robust"], 3)) for k, v in o.items() if k.startswith("slope")},
          "20-34:", round(R[cls]["20-34"]["slope_none"]["slope"], 3))
    print("   bins", [(round(v["census"], 2), round(v["birth"], 2)) for v in o["bins"]])

# The fertility rival: compare mothers with mothers. Census 2010 sample, the co-resident mothers of children aged 0-2
# (born 2008-2010) by municipality, against SINASC 2012-2013 mothers (the first cohorts with the mother's colour). If
# the steep slope above were fertility differing between classes, it would vanish here, where both sides are mothers.
import duckdb  # noqa: E402

M = duckdb.connect().execute(f"""SELECT uf || substr(mun, 1, 4) mun6, mother_race, sum(n) n FROM '{(ROOT / "data/probes/census2010/mother_child.parquet").as_posix()}'
                                 WHERE age BETWEEN 0 AND 2 AND mother_race IN ('1', '2', '3', '4', '5') GROUP BY 1, 2""").df()
M = M.pivot_table(index="mun6", columns="mother_race", values="n", aggfunc="sum").fillna(0)
cm = pd.DataFrame({"cW": M["1"] / M.sum(1), "cK": M["2"] / M.sum(1), "cP": M["4"] / M.sum(1), "women": M.sum(1)})
b2 = z["births"][0:2].sum(0)
S2 = pd.DataFrame({"mun6": [str(int(m)) for m in z["muns"]], "bW": b2[:, 0], "bK": b2[:, 1], "bP": b2[:, 3], "bdecl": b2[:, :5].sum(1)})
d0 = S2.merge(cm, left_on="mun6", right_index=True)
R["mothers_2010"] = {"municipalities": int(len(d0))}
for cls, num in (("W", "bW"), ("K", "bK"), ("P", "bP")):
    d = d0[(d0.bdecl > 0) & (d0.women > 0)].copy()
    d["y"], d["lx"], d["region"], d["uf"] = d[num] / d.bdecl, lg(d[f"c{cls}"]), d.mun6.str[0], d.mun6.str[:2]
    o = {"national_birth": float(d[num].sum() / d.bdecl.sum()), "national_census_mothers": float((d[f"c{cls}"] * d.women).sum() / d.women.sum())}
    for fe in ("", " + C(region)", " + C(uf)"):
        # the census side is a sample (about 10% of households): its error attenuates the slope, so the slope of the
        # census on the birth record is also given (attenuated the other way); the truth lies between the two
        m = smf.glm(f"y ~ lx{fe}", data=d, family=sm.families.Binomial(), var_weights=d.bdecl).fit(cov_type="HC1")
        o[f"slope{fe.replace(' + C(', '_').replace(')', '') or '_none'}"] = {"slope": float(m.params["lx"]), "se_robust": float(m.bse["lx"])}
    big = d[d.women >= 300]                                # municipalities where the census sample of mothers is large
    m = smf.glm("y ~ lx", data=big, family=sm.families.Binomial(), var_weights=big.bdecl).fit(cov_type="HC1")
    o["slope_large_samples"] = {"slope": float(m.params["lx"]), "se_robust": float(m.bse["lx"]), "municipalities": int(len(big))}
    d["ly"] = lg(d.y)
    r = smf.wls("lx ~ ly", data=big.assign(ly=lg(big[num] / big.bdecl), lx=lg(big[f"c{cls}"])), weights=big.bdecl).fit()
    o["reverse_slope_large_samples"] = {"slope_census_on_birth": float(r.params["ly"]), "implied_upper": float(1 / r.params["ly"])}
    d["bin"] = pd.cut(d[f"c{cls}"], BINS, labels=False, right=False)
    o["bins"] = [{"bin": int(k), "census": float(np.average(g[f"c{cls}"], weights=g.women)), "birth": float(g[num].sum() / g.bdecl.sum()),
                  "municipalities": int(len(g))} for k, g in d.groupby("bin")]
    R["mothers_2010"][cls] = o
OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
for cls in ("W", "K", "P"):
    o = R["mothers_2010"][cls]
    print("mothers2010", cls, round(o["national_birth"], 3), round(o["national_census_mothers"], 3), {k: round(v["slope"], 3) for k, v in o.items() if k.startswith("slope")},
          "reverse-implied", round(o["reverse_slope_large_samples"]["implied_upper"], 3))
    print("   bins", [(round(v["census"], 2), round(v["birth"], 2)) for v in o["bins"]])
