"""Paper 2, the review's analyses: what the reversal of the infant ratios is made of.

1. The 2 x 2: numerator (deaths by the mother's race through the linkage, or certified deaths) by denominator (births by the mother's race, or
   births by the child's race as households classify children under one year of mothers of each race, census 2010 flows by region).
2. The waterfall: from the mother's ratio to the certified-over-births ratio, each flow of the deaths switched on in turn.
3. Intervals by a delete-one-state jackknife for every ratio; the linked deaths scaled to all deaths by certified race (so the Indigenous
   deaths, linked less often, are scaled by their own factor).
4. Region-standardised ratios (Mantel-Haenszel over the five regions); neonatal and post-neonatal; cause groups; each year.
5. Absolute measures: rate differences per 1,000 and the deaths that would not have occurred at the White mothers' rate.

    python papers/race_at_death/analysis/indicators2.py      -> results/indicators2.json
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
R = json.loads((HERE / "results" / "results.json").read_text(encoding="utf-8"))
z = np.load(ROOT / "data" / "probes" / "race_own_birth" / "births_by_cohort.npz")
muns, births = z["muns"], z["births"]                    # cohorts 2012..2023 x municipalities x [White, Black, Yellow, Brown, Indigenous, none]
RACE = {"1": "white", "2": "black", "4": "brown", "5": "indigenous"}
RACES = ["white", "black", "brown", "indigenous"]
BIDX = {"white": 0, "black": 1, "brown": 3, "indigenous": 4}
REGION = {1: "North", 2: "Northeast", 3: "Southeast", 4: "South", 5: "Centre-West"}
CEN_KEY = {"white": "Branca", "black": "Preta", "brown": "Parda", "indigenous": "Indigena"}

L = pd.read_parquet(HERE / "data" / "infant_linkage_context.parquet", columns=["year", "uf", "age_days", "recorded", "linked", "declared", "cause"])
L = L[L.age_days >= 0].copy()
L["rec"], L["dec"] = L.recorded.map(RACE), L.declared.map(RACE)
L["region"] = (L.uf // 10).map(REGION)
L["period"] = np.where(L.age_days <= 27, "neonatal", "post-neonatal")
c1 = L.cause.astype(str).str[:1]
L["cause_group"] = np.select([c1.isin(["P"]), c1.isin(["Q"]), c1.isin(["V", "W", "X", "Y"]), c1.isin(["A", "B", "J"]), c1.isin(["R"])],
                             ["perinatal", "congenital", "external", "infectious or respiratory", "ill-defined"], "other")
bstate = (muns // 10000).astype(int)
byear = {y: births[y - 2012] for y in range(2013, 2024)}


def births_by(sel_state=None, region=None, years=range(2013, 2024)):
    """Births by the mother's race over ``years``, optionally for one state left out or one region."""
    keep = np.ones(len(muns), bool)
    if sel_state is not None:
        keep &= bstate != sel_state
    if region is not None:
        keep &= (bstate // 10) == region
    tot = sum(byear[y][keep].sum(0) for y in years)
    return {r: float(tot[BIDX[r]]) for r in RACES}


def flows(region=None):
    """Households' classification of children under one year by the mother's race (census 2010), nationally or for a region."""
    src = R["census"]["by_band"]["0"] if region is None else R["census"]["by_region"][region]["0"]
    return {m: {c: src[CEN_KEY[m]][CEN_KEY[c]]["est"] for c in RACES if CEN_KEY[c] in src[CEN_KEY[m]]} for m in RACES if CEN_KEY[m] in src}


def counts(D, b, region=None):
    """The four numerators and denominators: deaths by the mother's race (linked, scaled to all deaths by certified race), certified deaths;
    births by the mother's race and by the child's race through the households' flows."""
    scale = {r: len(D[D.rec == r]) / max(len(D[(D.rec == r) & D.linked & D.dec.notna()]), 1) for r in RACES}
    lk = D[D.linked & D.dec.notna()]
    d_mother = {r: float(sum(((lk.dec == r) & (lk.rec == k)).sum() * scale[k] for k in RACES)
                         + ((lk.dec == r) & ~lk.rec.isin(RACES)).sum() * len(D) / max(len(lk), 1)) for r in RACES}
    d_cert = {r: float((D.rec == r).sum()) for r in RACES}
    fl = flows(region)
    b_child = {c: sum(b[m] * fl.get(m, {}).get(c, 0.0) for m in RACES) for c in RACES}
    return d_mother, d_cert, b, b_child


def ratios(d, b, ref="brown"):
    return {r: (d[r] / b[r]) / (d[ref] / b[ref]) for r in RACES if r != ref}


def four(D, b, region=None):
    dm, dc, bm, bc = counts(D, b, region)
    return {"mother_over_mother": ratios(dm, bm), "certified_over_mother": ratios(dc, bm), "certified_over_child": ratios(dc, bc),
            "mother_over_child": ratios(dm, bc), "rates": {"mother": {r: 1e3 * dm[r] / bm[r] for r in RACES}, "certified": {r: 1e3 * dc[r] / bm[r] for r in RACES},
                                                         "certified_over_child": {r: 1e3 * dc[r] / bc[r] for r in RACES}}}


def jack(fn):
    """Estimate and delete-one-state jackknife standard error of every ratio in fn(states_left_out)."""
    full = fn(None)
    reps = [fn(u) for u in sorted(set(bstate))]
    out = {}
    for k, v in full.items():
        if k == "rates":
            out[k] = v
            continue
        out[k] = {}
        for r, x in v.items():
            vals = np.array([rep[k][r] for rep in reps])
            out[k][r] = {"est": float(x), "se": float(np.sqrt((len(vals) - 1) / len(vals) * ((vals - vals.mean()) ** 2).sum()))}
    return out


OUT = {}
OUT["national"] = jack(lambda u: four(L if u is None else L[L.uf != u], births_by(u)))
# the waterfall: start from deaths and births by the mother's race; switch on, one at a time, the certificate's flows out of each race
dm, dc, bm, bc = counts(L, births_by())
lk = L[L.linked & L.dec.notna()]
M = pd.crosstab(lk.dec, lk.rec.fillna("none")).reindex(index=RACES, columns=RACES + ["none"], fill_value=0)
P = M.div(M.sum(1), axis=0)
steps, cur = [], {r: dm[r] for r in RACES}
steps.append(("deaths and births by the mother's race", ratios(cur, bm)))
for a, b_, lab in (("brown", "white", "Brown mothers' infants certified White"), ("white", "brown", "White mothers' infants certified Brown"),
                   ("black", "brown", "Black mothers' infants certified Brown"), ("brown", "black", "Brown mothers' infants certified Black"),
                   ("indigenous", "brown", "Indigenous mothers' infants certified Brown")):
    moved = dm[a] * P.loc[a, b_]
    cur[a] -= moved
    cur[b_] += moved
    steps.append((lab, ratios(cur, bm)))
steps.append(("all flows and deaths with no race (certified deaths over births by the mother's race)", ratios(dc, bm)))
steps.append(("certified deaths over births by the child's race (households' flows)", ratios(dc, bc)))
OUT["waterfall"] = [{"step": s, "ratios": r} for s, r in steps]

# the same change shared by all orders (Shapley values on the log ratio): each named flow, the other flows, and the deaths with no race on the
# certificate are players; the rest of the gap to the certified ratio (the linked deaths' scaling) is reported as a residual. Jackknife by state.
import itertools  # noqa: E402

FLOWS = [("brown", "white", "Brown mothers' infants certified White"), ("white", "brown", "White mothers' infants certified Brown"),
         ("black", "brown", "Black mothers' infants certified Brown"), ("brown", "black", "Brown mothers' infants certified Black"),
         ("indigenous", "brown", "Indigenous mothers' infants certified Brown")]
PLAYERS = [f[2] for f in FLOWS] + ["the other flows", "deaths with no race on the certificate"]


def shapley(Lx, bx):
    dmx, dcx, bmx, _ = counts(Lx, bx)
    lkx = Lx[Lx.linked & Lx.dec.notna()]
    Mx = pd.crosstab(lkx.dec, lkx.rec.fillna("none")).reindex(index=RACES, columns=RACES + ["none"], fill_value=0)
    Px = Mx.div(Mx.sum(1), axis=0)
    named = {(a_, b_) for a_, b_, _ in FLOWS}

    def value(S):
        cur = {r: dmx[r] for r in RACES}
        for i, (a_, b_, _) in enumerate(FLOWS):
            if i in S:
                mv = dmx[a_] * Px.loc[a_, b_]
                cur[a_] -= mv
                cur[b_] += mv
        if 5 in S:
            for a_ in RACES:
                for b_ in RACES:
                    if a_ != b_ and (a_, b_) not in named:
                        mv = dmx[a_] * Px.loc[a_, b_]
                        cur[a_] -= mv
                        cur[b_] += mv
        if 6 in S:
            for a_ in RACES:
                cur[a_] -= dmx[a_] * Px.loc[a_, "none"]
        r_ = ratios(cur, bmx)
        return {k: np.log(v) for k, v in r_.items()}

    n = len(PLAYERS)
    vals = {S: value(set(S)) for k in range(n + 1) for S in itertools.combinations(range(n), k)}
    out = {}
    for t in ("white", "black"):
        phi = []
        for i in range(n):
            tot = 0.0
            for k in range(n):
                for S in itertools.combinations([j for j in range(n) if j != i], k):
                    w = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
                    tot += w * (vals[tuple(sorted(S + (i,)))][t] - vals[S][t])
            phi.append(tot)
        full = vals[tuple(range(n))][t]
        out[t] = {"players": dict(zip(PLAYERS, phi, strict=True)), "start": float(vals[()][t]), "all_players": float(full),
                  "certified": float(np.log(ratios(dcx, bmx)[t])), "residual_scaling": float(np.log(ratios(dcx, bmx)[t]) - full)}
    return out


sh0 = shapley(L, births_by())
reps = [shapley(L[L.uf != u], births_by(u)) for u in sorted(set(bstate))]
for t in ("white", "black"):
    for pl in PLAYERS + ["residual_scaling"]:
        get = (lambda x, pl=pl, t=t: x[t]["players"][pl] if pl in x[t]["players"] else x[t][pl])
        v = np.array([get(r_) for r_ in reps])
        se = float(np.sqrt((len(v) - 1) / len(v) * ((v - v.mean()) ** 2).sum()))
        if pl in sh0[t]["players"]:
            sh0[t]["players"][pl] = {"est": float(sh0[t]["players"][pl]), "se": se}
        else:
            sh0[t][pl] = {"est": float(sh0[t][pl]), "se": se}
OUT["shapley"] = sh0
# region-standardised: Mantel-Haenszel rate ratios over regions, each classification
mh = {}
for k in ("mother_over_mother", "certified_over_mother", "certified_over_child"):
    mh[k] = {}
    for r in ("white", "black"):
        num, den = 0.0, 0.0
        for rg_code, rg in REGION.items():
            D = L[L.region == rg]
            b = births_by(region=rg_code)
            dmr, dcr, bmr, bcr = counts(D, b, rg)
            d_, bb = {"mother_over_mother": (dmr, bmr), "certified_over_mother": (dcr, bmr), "certified_over_child": (dcr, bcr)}[k]
            T = bb[r] + bb["brown"]
            num += d_[r] * bb["brown"] / T
            den += d_["brown"] * bb[r] / T
        mh[k][r] = num / den
OUT["region_standardised"] = mh
OUT["by_region"] = {rg: four(L[L.region == rg], births_by(region=c), rg) for c, rg in REGION.items()}
# neonatal and post-neonatal, cause groups, years (births of the same years as denominators)
OUT["by_period"] = {p: four(L[L.period == p], births_by()) for p in ("neonatal", "post-neonatal")}
OUT["by_cause"] = {c: four(L[L.cause_group == c], births_by()) for c in sorted(L.cause_group.unique())}
OUT["by_year"] = {int(y): four(L[L.year == y], births_by(years=[y])) for y in range(2013, 2024)}
# the same strata with delete-one-state jackknife errors (the point estimates above are unchanged)
OUT["by_year_jack"] = {int(y): jack(lambda u, y=y: four(L[L.year == y] if u is None else L[(L.year == y) & (L.uf != u)], births_by(u, years=[y])))
                       for y in range(2013, 2024)}
OUT["by_period_jack"] = {p_: jack(lambda u, p_=p_: four(L[L.period == p_] if u is None else L[(L.period == p_) & (L.uf != u)], births_by(u)))
                         for p_ in ("neonatal", "post-neonatal")}
OUT["by_cause_jack"] = {c: jack(lambda u, c=c: four(L[L.cause_group == c] if u is None else L[(L.cause_group == c) & (L.uf != u)], births_by(u)))
                        for c in sorted(L.cause_group.unique())}
# absolute measures, by the mother's race and certified
ab = {}
for k, d_ in (("mother", dm), ("certified", dc)):
    rw = d_["white"] / bm["white"]
    ab[k] = {r: {"difference_per_1000": 1e3 * (d_[r] / bm[r] - rw), "excess_deaths": float(d_[r] - rw * bm[r])} for r in RACES if r != "white"}
OUT["absolute"] = ab
OUT["linked_scale"] = {r: len(L[L.rec == r]) / max(len(L[(L.rec == r) & L.linked & L.dec.notna()]), 1) for r in RACES}
OUT["no_race_share"] = float((~L.rec.isin(RACES)).mean())
(HERE / "results" / "indicators2.json").write_text(json.dumps(OUT, indent=1, default=float), encoding="utf-8")
print(json.dumps({k: OUT["national"][k] for k in ("mother_over_mother", "certified_over_mother", "certified_over_child", "mother_over_child")}, indent=0)[:1500])
print("waterfall", [(s["step"][:40], round(s["ratios"]["white"], 3), round(s["ratios"]["black"], 3)) for s in OUT["waterfall"]])
print("standardised", mh)
