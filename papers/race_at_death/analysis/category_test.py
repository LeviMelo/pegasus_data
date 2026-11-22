"""Test C (review 2026-11-22): is the Brown category the same population everywhere?

If families in whiter places report the children of a Brown mother and a Brown father as White more often, part of the
certificate's gradient with the local composition (paper 1) belongs to the category, not to the certifier. If the share
is flat, families carry no regional Brown category. The family map of paper 1 mixes this with the partner mix, which also
varies with composition; here the couple type is held fixed and the gradient decomposed.

Census 2010 sample (municipality held), couples' children aged 0-9 and 0-24; 2022 public sample (state only) for the
state comparison. Composition: the municipality's share of White births, SINASC 2012-2023 (the certificate gradient's
axis), and the 2010 census share of White residents. Standard errors cluster on the municipality (households nest in it).

    python papers/race_at_death/analysis/category_test.py   -> results/category_test.json
"""
import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm

warnings.simplefilter("ignore")
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
CEN = ROOT / "data" / "probes" / "census2022"
OUT = HERE / "results" / "category_test.json"
con = duckdb.connect()
con.execute("PRAGMA disable_progress_bar; SET memory_limit='1500MB'")
RC = {"1": "W", "2": "K", "4": "P"}                       # White, Black (preta), Brown (parda)

# composition: SINASC births 2012-2023 by the mother's colour (the certificate gradient's axis), and census 2010
z = np.load(ROOT / "data" / "probes" / "race_own_birth" / "births_by_cohort.npz")
tot = z["births"].sum(0)
comp = pd.DataFrame({"mun6": [str(int(m)) for m in z["muns"]], "white_births": tot[:, 0] / np.maximum(tot[:, :5].sum(1), 1)})
ctx = pd.read_parquet(HERE / "data" / "municipal_context.parquet", columns=["mun", "census_white"]).rename(columns={"mun": "mun6"})
comp = comp.merge(ctx, on="mun6", how="outer")


def load(year, ages):
    cols = "uf, mun, hh, w, age, sex, race, mother_race, partner_race, mother_instruction, rel" if year == 2010 else \
           "uf, NULL mun, hh, w, age, sex, race, mother_race, partner_race, mother_instruction, rel"
    # the 2022 public file gives five-year age groups only (1: 0-4 ... 5: 20-24)
    agesel = f"age BETWEEN {ages[0]} AND {ages[1]}" if year == 2010 else f"age_group BETWEEN {ages[0] // 5 + 1} AND {ages[1] // 5 + 1}"
    d = con.execute(f"""SELECT {cols} FROM '{(CEN / f'pairs2_{year}.parquet').as_posix()}'
                        WHERE rule = 'couple' AND {agesel} AND mother_race IN ('1', '2', '4')""").df()
    d["m"], d["f"] = d.mother_race.map(RC), d.partner_race.map(RC).fillna("o")
    d["cW"], d["cK"], d["cP"] = (d.race == "1").astype(float), (d.race == "2").astype(float), (d.race == "4").astype(float)
    if year == 2010:
        d["mun6"] = d.uf + d.mun.str[:4]
        d = d.merge(comp, on="mun6", how="left")
    return d


def share(d, y):
    """Weighted share with a linearised standard error clustered on the municipality (or household in 2022)."""
    cl = "mun6" if "mun6" in d and d.mun6.notna().all() else "hh"
    w = d.w.to_numpy()
    p = float((w * d[y]).sum() / w.sum())
    u = pd.Series(w * (d[y].to_numpy() - p)).groupby(d[cl].to_numpy()).sum()
    se = float(np.sqrt(len(u) / max(len(u) - 1, 1) * (u ** 2).sum()) / w.sum())
    return {"est": p, "se": se, "records": int(len(d))}


BINS = [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001]
logit = lambda p: np.log(np.clip(p, .005, .995) / (1 - np.clip(p, .005, .995)))  # noqa: E731


def gradient(d, y, x):
    """Shares by tenth of composition and the slope on the logit scale (weighted binomial GLM, municipality-clustered SE),
    raw and with the child's age and sex and the mother's instruction held."""
    dd = d[d[x].notna()].copy()
    dd["bin"] = pd.cut(dd[x], BINS, labels=False, right=False)
    bins = [{"bin": int(b), "x": float(np.average(g[x], weights=g.w)), **share(g, y)} for b, g in dd.groupby("bin") if len(g) >= 30]
    dd["lx"] = logit(dd[x])
    out = {"bins": bins}
    wbar = dd.w.mean()
    for nm, extra in (("raw", []), ("adjusted", ["age", "sex", "mother_instruction"])):
        # the same likelihood on cells (municipality x covariates x outcome) with summed weights: far fewer rows than children
        g = dd.groupby(["mun6", "lx", *extra, y], observed=True, dropna=False).w.sum().reset_index()
        X = sm.add_constant(pd.get_dummies(g[["lx"] + extra].astype(dict.fromkeys(extra, str)), drop_first=True, dtype=float))
        m = sm.GLM(g[y], X, family=sm.families.Binomial(), freq_weights=g.w / wbar).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.mun6)[0]})
        out[nm] = {"slope": float(m.params["lx"]), "se": float(m.bse["lx"])}
    return out


import sys  # noqa: E402

ONLY_COUPLES = len(sys.argv) > 1 and sys.argv[1] == "couples"   # rerun only the couple model, keeping the rest of the results
R = json.loads(OUT.read_text(encoding="utf-8")) if ONLY_COUPLES else {}
for ages in (() if ONLY_COUPLES else ((0, 9), (0, 24))):
    d = load(2010, ages)
    key = f"{ages[0]}-{ages[1]}"
    R[key] = {"municipalities": int(d.mun6.nunique()), "matched": float(d.white_births.notna().mean())}
    for x in ("white_births", "census_white"):
        R[key][x] = {
            "PP_white": gradient(d[(d.m == "P") & (d.f == "P")], "cW", x),       # the test: a Brown couple's child reported White
            "PP_black": gradient(d[(d.m == "P") & (d.f == "P")], "cK", x),
            "WW_brown": gradient(d[(d.m == "W") & (d.f == "W")], "cP", x),
            "KK_black": gradient(d[(d.m == "K") & (d.f == "K")], "cK", x),
            "P_any_white": gradient(d[d.m == "P"], "cW", x),                     # paper 1's family map: the Brown mother, any partner
            "PW_white": gradient(d[(d.m == "P") & (d.f == "W")], "cW", x),
        }
    # decomposition of the Brown mother's gradient: partner mix against the rate within couple type, by tenth of composition
    dd = d[(d.m == "P") & d.white_births.notna()].copy()
    dd["bin"] = pd.cut(dd.white_births, BINS, labels=False, right=False)
    nat_mix = dd.groupby("f").w.sum() / dd.w.sum()
    nat_rate = dd.groupby("f").apply(lambda g: np.average(g.cW, weights=g.w))
    rows = []
    for b, g in dd.groupby("bin"):
        mix = g.groupby("f").w.sum() / g.w.sum()
        rate = g.groupby("f").apply(lambda h: np.average(h.cW, weights=h.w))
        rate = rate.reindex(nat_mix.index).fillna(nat_rate)
        mix = mix.reindex(nat_mix.index).fillna(0)
        rows.append({"bin": int(b), "x": float(np.average(g.white_births, weights=g.w)), "observed": float((mix * rate).sum()),
                     "mix_held": float((nat_mix * rate).sum()), "rate_held": float((mix * nat_rate).sum()),
                     "partner_white": float(mix.get("W", 0)), "partner_brown": float(mix.get("P", 0))})
    R[key]["decomposition_brown_mother"] = rows

# by state, both censuses: fixed couple types
S = R.get("by_state", {})
for year in (() if ONLY_COUPLES else (2010, 2022)):
    d = load(year, (0, 9))
    S[year] = {uf: {"PP_white": share(g[(g.m == "P") & (g.f == "P")], "cW"), "WW_brown": share(g[(g.m == "W") & (g.f == "W")], "cP"),
                    "KK_black": share(g[(g.m == "K") & (g.f == "K")], "cK"), "PW_white": share(g[(g.m == "P") & (g.f == "W")], "cW"),
                    "P_any_white": share(g[g.m == "P"], "cW")}
               for uf, g in d.groupby("uf")}
    S[year]["BR"] = {"PP_white": share(d[(d.m == "P") & (d.f == "P")], "cW"), "WW_brown": share(d[(d.m == "W") & (d.f == "W")], "cP")}
R["by_state"] = S
if ONLY_COUPLES:
    pass
# the certificate's gradient on the same axis (paper 1, results.json): Brown mothers' infants certified White, by tenth
RES = json.loads((HERE / "results" / "results.json").read_text(encoding="utf-8"))
cert = [{"bin": g["bin"], "x": g["white_share"], "est": g["matrix"]["rows"]["Parda"]["Branca"]["est"], "n": g["matrix"]["rows"]["Parda"]["n"]}
        for g in RES["gradient_infants"]]
cx, cy, cn = (np.array([c[k] for c in cert]) for k in ("x", "est", "n"))
m = sm.GLM(np.column_stack([cy * cn, (1 - cy) * cn]).round(), sm.add_constant(logit(cx)), family=sm.families.Binomial()).fit()
R["certificate"] = {"bins": cert, "slope_bins": float(m.params[1])}
# the family's slopes on the same binned basis, for a like-for-like comparison with the certificate
for nm in ("PP_white", "P_any_white"):
    b = R["0-9"]["white_births"][nm]["bins"]
    bx, by, bn = (np.array([v[k] for v in b], dtype=float) for k in ("x", "est", "records"))
    mm = sm.GLM(np.column_stack([by * bn, (1 - by) * bn]).round(), sm.add_constant(logit(bx)), family=sm.families.Binomial()).fit()
    R["0-9"]["white_births"][nm]["slope_bins"] = float(mm.params[1])
OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
c = R["0-9"]["white_births"]
print("certificate slope (bins)", round(R["certificate"]["slope_bins"], 3))
for k in ("PP_white", "P_any_white", "WW_brown", "KK_black", "PP_black"):
    print(k, {a: round(c[k][a]["slope"], 3) for a in ("raw", "adjusted")}, [round(v["est"], 3) for v in c[k]["bins"]], c[k].get("slope_bins"))

# Review point 4.2: the nine couple types (mother and father White, Brown or Black; children aged 0-9 of both) with a category term, a mother term and a
# father term. Log-linear (multinomial) form on the weighted counts of child class c in couple (m, f):
#   log mu(m, f, c) = couple(m, f) + alpha_c + gamma_M [c = m] + gamma_F [c = f]
# alpha_c is the pull toward each class whatever the parents; gamma_M and gamma_F the weight of taking the mother's and the
# father's class. Intervals: 200 bootstrap replicates resampling clusters (municipality in 2010, household in 2022).
import itertools  # noqa: E402

CL = ["W", "P", "K"]


def couple_fit(counts):
    """counts: array [m, f, c] of weighted children. Returns alpha (W and K against P), gamma_M, gamma_F."""
    rows = [(m, f, c, counts[i, j, k]) for (i, m), (j, f), (k, c) in itertools.product(enumerate(CL), enumerate(CL), enumerate(CL))]
    t = pd.DataFrame(rows, columns=["m", "f", "c", "n"])
    X = pd.get_dummies(t.m + t.f, prefix="cp", drop_first=True, dtype=float)
    X["aW"], X["aK"] = (t.c == "W").astype(float), (t.c == "K").astype(float)
    X["gM"], X["gF"] = (t.c == t.m).astype(float), (t.c == t.f).astype(float)
    res = sm.GLM(t.n, sm.add_constant(X), family=sm.families.Poisson()).fit()
    return {k: float(res.params[k]) for k in ("aW", "aK", "gM", "gF")}


C2 = {}
for year in (2010, 2022):
    d = load(year, (0, 9))                                 # children aged 0-9 of both members of the couple: the partner is the father
    d = d[d.m.isin(CL) & d.f.isin(CL) & (d.race.isin(["1", "2", "4"])) & d.w.notna() & (d.rel == "04")][["m", "f", "race", "w", "hh"] + (["mun6"] if year == 2010 else [])].copy()
    d["c"] = d.race.map(RC)
    cl = d.mun6 if year == 2010 else d.hh
    cid, _ = pd.factorize(cl)
    cell = (d.m.map(CL.index) * 9 + d.f.map(CL.index) * 3 + d.c.map(CL.index)).to_numpy().astype(np.int64)
    base = np.bincount(cell, weights=d.w, minlength=27).reshape(3, 3, 3)
    est = couple_fit(base)
    rng = np.random.default_rng(2026)
    reps = []
    for _ in range(200):
        wc = rng.poisson(1.0, cid.max() + 1)[cid]
        reps.append(couple_fit(np.bincount(cell, weights=d.w * wc, minlength=27).reshape(3, 3, 3)))
    reps = pd.DataFrame(reps)
    C2[year] = {k: {"est": v, "lo": float(reps[k].quantile(.025)), "hi": float(reps[k].quantile(.975))} for k, v in est.items()}
    C2[year]["gM_minus_gF"] = {"est": est["gM"] - est["gF"], "lo": float((reps.gM - reps.gF).quantile(.025)), "hi": float((reps.gM - reps.gF).quantile(.975))}
    # the observed table of the nine couple types (share of children in each class), for the paper's table
    C2[year]["table"] = {m + f: {c: float(base[i, j, k] / base[i, j].sum()) for k, c in enumerate(CL)} | {"children": float(base[i, j].sum())}
                         for (i, m), (j, f) in itertools.product(enumerate(CL), enumerate(CL))}
R["couples"] = C2
OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
for y in (2010, 2022):
    print(y, {k: (round(v["est"], 2), round(v["lo"], 2), round(v["hi"], 2)) for k, v in C2[y].items() if k != "table"})
