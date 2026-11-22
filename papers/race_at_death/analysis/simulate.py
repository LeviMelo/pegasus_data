"""Simulation study of the candidate estimator (paper 6): bias and coverage under movers, twins, unequal found shares
and municipality size, with the package's estimator (`modelled_race.candidate_estimates`) applied as to the real data.

The world is built from the real data, not invented: the 2018 birth cohort of every municipality by declared colour
(data/probes/race_own_birth/births_by_cohort.npz), spread over the days of the year with a weekday and seasonal pattern
(stronger on weekdays for White births, as scheduled caesareans are); the colour each death is certified with drawn from
the one-to-one infant linkage's matrix for the decile of the municipality's White share where it is certified
(results.json `gradient_infants`); mortality by declared colour in the ratios estimated at 1-9 years (White 0.66, Black
1.1, Indigenous 4.1 to Brown), scaled to the 77,693 deaths at 1-9 of 2013-2024, all drawn from one cohort so that a
day's chance candidates are as many as in one real cohort. A mover dies resident in another municipality of the state,
chosen in proportion to its births, and is certified there; he is then not among his candidates.

Scenarios: `ideal` (no movers, no twins); `twins` (2% of births twins, two thirds of them of the same sex, dying at twice
the rate); `movers` (28% movers, as many as the 0.72 found share implies); `unequal` (twins, and movers 22% of White, 30%
of Black and Brown, 34% of Indigenous children: the found share differs by eight points); `selective` (twins, movers 22%,
and 12 points more among the children certified in a class other than the declared one: the found are not like the rest);
`sparse` (as `ideal`, with a twelfth of the deaths: one cohort's own deaths, so that deaths sharing a day are as rare as
in the data); `a2` (as `ideal`, with boys 52.5% of White births and 50.5% of Black and Indigenous ones: the two sexes
of a day no longer share their composition, assumption A2 broken).

Two answers are known: the cross-classification of all the deaths of a group of municipalities (`truth`, the estimand),
and of those of its deaths that are among their candidates, the children still resident where they were born
(`truth_found`): the estimator's bias against the second, and the movers' selection between the two.

    python papers/race_at_death/analysis/simulate.py [replicates]   -> results/simulation.json   (about 3 s a replicate)
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from pegasus_data.studies import modelled_race as mr

PAPER = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
R = json.loads((PAPER / "results" / "results.json").read_text(encoding="utf-8"))

# ------------------------------------------------------------------ the world: births by municipality and declared class
z = np.load(ROOT / "data/probes/race_own_birth/births_by_cohort.npz")
raw = z["births"][6]                                                   # cohort 2018: (municipality, [Branca, Preta, Amarela, Parda, Indigena, none])
B5 = np.stack([raw[:, 0], raw[:, 1], raw[:, 3], raw[:, 4], raw[:, 2] + raw[:, 5]], 1).astype(float)   # White, Black, Brown, Indigenous, other
CLASSES = ["Branca", "Preta", "Parda", "Indigena"]
M, J = B5.shape
size = B5.sum(1)
state = (z["muns"] // 10000).astype(int)
white_share = B5[:, 0] / np.maximum(B5[:, :4].sum(1), 1)

# the colour certified given the declared one, by decile of the White share of the place of certification (linked infants)
nat = R["infants"]["linkage"]["rows"]
G = np.zeros((10, J, 5))
for b, g in enumerate(R["gradient_infants"]):
    rows = g["matrix"]["rows"]
    for j, c in enumerate([*CLASSES, "Parda"]):                        # a declared 'other' (Amarela, blank) is certified as Brown children are
        src = rows[c] if c in rows and rows[c]["n"] >= 50 else nat[c]
        G[b, j] = [src[k]["est"] for k in [*CLASSES, "other"]]
G /= G.sum(2, keepdims=True)
decile = np.minimum((white_share * 10).astype(int), 9)

# days: weekday and season; White births more concentrated on weekdays
day = np.arange(365)
week = np.array([1.06, 1.08, 1.07, 1.06, 1.04, 0.88, 0.81])[day % 7]
amp = np.array([1.5, 1.0, 1.0, 0.8, 1.0])
W = (1 + amp[None] * (week[:, None] - 1)) * (1 + 0.05 * np.cos(2 * np.pi * (day[:, None] - 60) / 365))
W /= W.sum(0, keepdims=True)                                           # (day, class)
P_MALE = np.full(5, 0.512)
RR = np.array([0.66, 1.1, 1.0, 4.1, 1.0])                              # mortality to Brown, by declared class
Q = R["children"]["1-9"]["matrix"]["deaths"] / (B5 * RR).sum() * RR   # one cohort carries the twelve cohorts' deaths (sparse: its own)

# destinations of movers: a municipality of the same state, in proportion to its births
by_state = {s: np.flatnonzero(state == s) for s in np.unique(state)}
cum = {s: np.cumsum(size[i]) / size[i].sum() for s, i in by_state.items()}

SIZES = [(0, 400, "<400"), (400, 1600, "400-1,599"), (1600, 6400, "1,600-6,399"), (6400, 25600, "6,400-25,599"), (25600, 10**9, ">=25,600"), (0, 10**9, "all")]
SCEN = {
    "ideal": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0},
    "twins": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.02, "twin_rr": 2.0},
    "movers": {"move": [0.28] * 5, "selective": 0.0, "twins": 0.0, "twin_rr": 1.0},
    "unequal": {"move": [0.22, 0.30, 0.30, 0.34, 0.28], "selective": 0.0, "twins": 0.02, "twin_rr": 2.0},
    "selective": {"move": [0.22] * 5, "selective": 0.12, "twins": 0.02, "twin_rr": 2.0},
    "sparse": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "deaths": 1 / 12},
    "a2": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "male": [0.525, 0.505, 0.512, 0.505, 0.512]},
}


def destination(rng, origin):
    out = origin.copy()
    for s, idx in by_state.items():
        sel = np.flatnonzero(state[origin] == s)
        if len(sel):
            out[sel] = idx[np.minimum(np.searchsorted(cum[s], rng.random(len(sel))), len(idx) - 1)]
    return out


def replicate(rng, sc):
    """One national cohort and its deaths; returns per municipality T, V, deaths, exposure and the truth's counts."""
    lam = B5[:, None, :] * W[None]                                    # (M, day, class) expected births
    male = np.array(sc.get("male", P_MALE))
    single = rng.poisson(lam[:, :, None, :] * (1 - sc["twins"]) * np.stack([male, 1 - male])[None, None])   # (M, day, sex, class)
    pairs = lam * sc["twins"] / 2
    mm, ff = rng.poisson(pairs * 2 / 3 * male), rng.poisson(pairs * 2 / 3 * (1 - male))
    mf = rng.poisson(pairs / 3)
    N = single.copy()
    N[:, :, 0] += 2 * mm + mf
    N[:, :, 1] += 2 * ff + mf
    twins = np.stack([2 * mm + mf, 2 * ff + mf], 2)
    q = Q * sc.get("deaths", 1.0)
    dead = rng.binomial(single, q[None, None, None]) + rng.binomial(twins, np.minimum(q * sc["twin_rr"], 1)[None, None, None])
    m, d, s, j = np.nonzero(dead)
    rep = dead[m, d, s, j]
    m, d, s, j = (np.repeat(a, rep) for a in (m, d, s, j))
    n = len(m)
    # certified where they die; movers die elsewhere
    k_home = (rng.random(n)[:, None] > np.cumsum(G[decile[m], j], 1)).sum(1)
    p_move = np.array(sc["move"])[j] + sc["selective"] * (k_home != np.minimum(j, 4))
    moved = rng.random(n) < p_move
    r = np.where(moved, destination(rng, m), m)
    moved &= r != m                                                    # a draw of the own municipality is no move
    k = np.where(moved & (sc["selective"] == 0), (rng.random(n)[:, None] > np.cumsum(G[decile[r], j], 1)).sum(1), k_home)
    k = np.minimum(k, 4)
    # candidates: the births of the death's day and sex where it is resident; control: the other sex, scaled. Deaths that
    # share their key and certified class are one cell, as in the SQL (`modelled_race._candidates`): g of them share
    # their candidates, so the cell's variances carry g squared
    S = N.sum((1, 3)).astype(float)                                    # (M, sex)
    cell, g = np.unique(((r * 365 + d) * 2 + s) * 5 + k, return_counts=True)
    gk, rest = cell % 5, cell // 5
    gs, rest = rest % 2, rest // 2
    gd, gr = rest % 365, rest // 365
    g = g.astype(float)[:, None]
    cand = N[gr, gd, gs].astype(float)                                 # (cells, class)
    with np.errstate(divide="ignore", invalid="ignore"):
        scale = np.where(S[gr, 1 - gs] > 0, S[gr, gs] / S[gr, 1 - gs], 0.0)[:, None]
    opp = N[gr, gd, 1 - gs].astype(float)
    T, V, C, VM, VC = (np.zeros((M, J, 5)) for _ in range(5))
    at = (gr, slice(None), gk)
    np.add.at(T, at, g * (cand - opp * scale))
    np.add.at(V, at, g * (cand + opp * scale))
    np.add.at(C, at, g * opp * scale)
    np.add.at(VM, at, g ** 2 * (cand + opp * scale ** 2))
    np.add.at(VC, at, g ** 2 * opp * (scale + scale ** 2))
    deaths = np.bincount(r, minlength=M).astype(float)
    truth, found = np.zeros((M, J, 5)), np.zeros((M, J, 5))
    np.add.at(truth, (r, j, k), 1.0)
    np.add.at(found, (r[~moved], j[~moved], k[~moved]), 1.0)
    return T, V, C, VM, VC, deaths, N.sum((1, 2)).astype(float), truth, found


QUANT = {"p_white_white": ("p", 0, 0), "p_black_black": ("p", 1, 1), "p_black_brown": ("p", 1, 2), "p_brown_brown": ("p", 2, 2),
         "p_brown_white": ("p", 2, 0), "p_indigenous_indigenous": ("p", 3, 3), "mix_white": ("mix", 0, None), "mix_black": ("mix", 1, None),
         "ratio_white": ("ratio", 0, None), "ratio_black": ("ratio", 1, None), "ratio_indigenous": ("ratio", 3, None), "found": ("found", None, None)}


def pick(est, name, which):
    key, a, b = QUANT[name]
    v = est[key + which]
    return float(v if a is None else (v[a] if b is None else v[a, b]))


def truth_of(truth, expo):
    tr = truth[:, :4].sum(0)
    rate = tr.sum(1) / expo[:, :4].sum(0)
    return {"p": tr / tr.sum(1, keepdims=True), "mix": tr.sum(1) / tr.sum(), "ratio": rate / rate[2], "found": np.nan}


out = {"replicates": REPS, "scenarios": SCEN, "deaths_target": R["children"]["1-9"]["matrix"]["deaths"],
       "municipalities": {lab: int(((size >= lo) & (size < hi)).sum()) for lo, hi, lab in SIZES}, "results": {}}
for name, sc in SCEN.items():
    rng = np.random.default_rng(20261121)
    acc = {lab: {q: {"est": [], "se": [], "se_poisson": [], "se_chance": [], "se_model": [], "truth": [], "truth_found": []} for q in QUANT} for _, _, lab in SIZES}
    invalid = {lab: 0 for _, _, lab in SIZES}
    deaths_seen, t0 = [], time.time()
    for _rep in range(REPS):
        T, V, C, VM, VC, deaths, expo, truth, found = replicate(rng, sc)
        deaths_seen.append(deaths.sum())
        for lo, hi, lab in SIZES:
            sel = (size >= lo) & (size < hi)
            est = mr.candidate_estimates(T[sel][:, :4], V[sel][:, :4], deaths[sel], expo[sel][:, :4], ref=2, control=C[sel][:, :4],
                                         var_model=VM[sel][:, :4], var_chance=VC[sel][:, :4])
            tru, trf = truth_of(truth[sel], expo[sel]), truth_of(found[sel], expo[sel])
            invalid[lab] += int((T[sel][:, :4].sum((0, 2)) <= 0).any())
            for q in QUANT:
                key, a, b = QUANT[q]
                acc[lab][q]["est"].append(pick(est, q, ""))
                acc[lab][q]["se"].append(pick(est, q, "_se"))
                acc[lab][q]["se_poisson"].append(pick(est, q, "_se_poisson") if key in ("p", "ratio") else np.nan)
                acc[lab][q]["se_chance"].append(pick(est, q, "_se_chance"))
                acc[lab][q]["se_model"].append(pick(est, q, "_se_model") if key in ("p", "mix", "ratio") else np.nan)
                tv = tru[key]
                acc[lab][q]["truth"].append(float(tv if a is None else (tv[a] if b is None else tv[a, b])))
                tv = trf[key]
                acc[lab][q]["truth_found"].append(float(tv if a is None else (tv[a] if b is None else tv[a, b])))
    res = {}
    for lab, qs in acc.items():
        res[lab] = {"_invalid": invalid[lab]}
        for q, v in qs.items():
            est, se, sp, sc_, sm, tr, tf = (np.array(v[x]) for x in ("est", "se", "se_poisson", "se_chance", "se_model", "truth", "truth_found"))
            sup = np.nanmean(tr)                                      # the system's classification: the truth's mean over replicates
            ok = np.isfinite(est)
            row = {"n": int(ok.sum()), "est": float(np.nanmean(est)), "median": float(np.nanmedian(est)), "sd": float(np.nanstd(est, ddof=1)),
                   "se": float(np.nanmean(se)), "se_median": float(np.nanmedian(se)), "se_chance": float(np.nanmean(sc_)), "se_model": float(np.nanmean(sm))}
            if q != "found":
                row |= {"truth": float(np.nanmean(tr)), "truth_found": float(np.nanmean(tf)), "bias": float(np.nanmean(est - tr)),
                        "bias_found": float(np.nanmean(est - tf)), "median_bias_found": float(np.nanmedian(est - tf)),
                        "mcse_bias": float(np.nanstd(est - tr, ddof=1) / np.sqrt(ok.sum())),
                        "mcse_bias_found": float(np.nanstd(est - tf, ddof=1) / np.sqrt(ok.sum())),
                        "sd_error_found": float(np.nanstd(est - tf, ddof=1)),
                        "cover": float(np.nanmean(np.abs(est - tr) <= 1.96 * se)), "cover_found": float(np.nanmean(np.abs(est - tf) <= 1.96 * se)),
                        "cover_super": float(np.nanmean(np.abs(est - sup) <= 1.96 * se)),
                        "cover_found_chance": float(np.nanmean(np.abs(est - tf) <= 1.96 * sc_)),
                        "cover_super_model": float(np.nanmean(np.abs(est - sup) <= 1.96 * sm)), "cover_model": float(np.nanmean(np.abs(est - tr) <= 1.96 * sm)),
                        "rmse": float(np.sqrt(np.nanmean((est - tr) ** 2)))}
                if np.isfinite(sp).any():
                    row |= {"se_poisson": float(np.nanmean(sp)), "cover_poisson": float(np.nanmean(np.abs(est - tr) <= 1.96 * sp)),
                            "cover_found_poisson": float(np.nanmean(np.abs(est - tf) <= 1.96 * sp)), "cover_super_poisson": float(np.nanmean(np.abs(est - sup) <= 1.96 * sp))}
            res[lab][q] = row
    out["results"][name] = res
    out["results"][name]["_deaths_mean"] = float(np.mean(deaths_seen))
    print(name, f"{time.time() - t0:.0f} s", "deaths", round(np.mean(deaths_seen)), "found", round(res["all"]["found"]["est"], 3),
          "W->W bias", round(res["<400"]["p_white_white"]["bias"], 4), "found-bias", round(res["<400"]["p_white_white"]["bias_found"], 4), "cover", res["<400"]["p_white_white"]["cover_found"],
          "ratio W bias", round(res["all"]["ratio_white"]["bias"], 3), flush=True)
(PAPER / "results" / "simulation.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("DONE", flush=True)
