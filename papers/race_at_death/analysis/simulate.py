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

Review 2 upgrades (section 3.3 and 5.9): day-level overdispersion with a shared (sex-correlated) day factor, its size measured in the real
SINASC counts (`analysis/estimator.py`, results/estimator.json `births_dispersion`); key errors (a wrong birth date on the death record, at the
rates by class that the admissions' findability implies); twelve independent sparse cohorts pooled (the real regime: `pooled12`); a random
municipality effect in the classification (`munfx`, size measured in the linked infants) so that the cluster error is testable; an `application`
scenario with all of them; medians, the share of failed replicates (a row sum at or below zero) with the moments among the valid ones, the
variance ratio, Monte Carlo errors of every coverage, and the model variance with the covariances of deaths sharing a key cell (`se_exact`).
Rate-ratio truth by size class uses the deaths by municipality of birth over the births of the same municipality (matched), not the municipality
of residence at death over births.

    python papers/race_at_death/analysis/simulate.py [replicates [output name [scenarios, comma separated]]]   -> results/simulation.json
    (about 3 s a replicate and scenario; the pooled scenarios 12 times that)
"""
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

from pegasus_data.studies import modelled_race as mr

warnings.filterwarnings("ignore", category=RuntimeWarning)       # all-NaN slices (the share found has no truth) and 0/0 in the ratios of failed replicates
PAPER = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
OUTNAME = sys.argv[2] if len(sys.argv) > 2 else "simulation.json"
ONLY = sys.argv[3].split(",") if len(sys.argv) > 3 else None
R = json.loads((PAPER / "results" / "results.json").read_text(encoding="utf-8"))
_ef = PAPER / "results" / "estimator.json"
EJ = json.loads(_ef.read_text(encoding="utf-8")) if _ef.exists() else {}
# measured in the real data (analysis/estimator.py); the stated fallbacks only if that file lacks the key
DISP = EJ.get("births_dispersion", {})                                 # per size class: phi, the extra variance of a municipality-day's births relative to its mean squared,
                                                                       # and psi, the part shared by the two sexes (their covariance over the product of means)
TAU = EJ.get("classification_heterogeneity", {}).get("tau", 0.5)       # sd of the municipality effect on the logit of being certified the declared class
KEYERR = EJ.get("a1_findability", {}).get("key_error_by_class", [0.087, 0.104, 0.118, 0.193, 0.118])   # one minus the share findable among the linked, by declared class

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
PHI_M, PSI_M = np.full(M, 0.01), np.full(M, 0.007)
for lo_, hi_, lab_ in SIZES[:5]:
    if lab_ in DISP:
        in_ = (size >= lo_) & (size < hi_)
        PHI_M[in_], PSI_M[in_] = DISP[lab_]["phi"], min(DISP[lab_]["psi"], DISP[lab_]["phi"])
SCEN = {
    "ideal": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0},
    "twins": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.02, "twin_rr": 2.0},
    "movers": {"move": [0.28] * 5, "selective": 0.0, "twins": 0.0, "twin_rr": 1.0},
    "unequal": {"move": [0.22, 0.30, 0.30, 0.34, 0.28], "selective": 0.0, "twins": 0.02, "twin_rr": 2.0},
    "selective": {"move": [0.22] * 5, "selective": 0.12, "twins": 0.02, "twin_rr": 2.0},
    "sparse": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "deaths": 1 / 12},
    "a2": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "male": [0.525, 0.505, 0.512, 0.505, 0.512]},
    "overdisp": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "od": True},
    "keyerr": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "keyerr": KEYERR},
    "keyerr_k": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "keyerr": KEYERR, "keyerr_k": 0.045},
    "pooled12": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "deaths": 1 / 12, "pool": 12},
    "munfx": {"move": [0, 0, 0, 0, 0], "selective": 0.0, "twins": 0.0, "twin_rr": 1.0, "tau": TAU},
    "application": {"move": [0.28] * 5, "selective": 0.0, "twins": 0.02, "twin_rr": 2.0, "deaths": 1 / 12, "pool": 12, "od": True, "tau": TAU, "keyerr": KEYERR},
}


def destination(rng, origin):
    out = origin.copy()
    for s, idx in by_state.items():
        sel = np.flatnonzero(state[origin] == s)
        if len(sel):
            out[sel] = idx[np.minimum(np.searchsorted(cum[s], rng.random(len(sel))), len(idx) - 1)]
    return out


def certify(rng, jj, mun, u):
    """The class certified for children declared ``jj`` (0-3; others as Brown) resident in ``mun``: drawn from the linked infants' matrix for the decile
    of the municipality's White share, the odds of the declared class multiplied by exp(u[mun]) when a municipality effect ``u`` is given."""
    base = G[decile[mun], np.minimum(jj, J - 1)]                       # (n, 5)
    p = base.copy()
    if u is not None:
        sel = jj < 4
        rows = np.flatnonzero(sel)
        d = jj[sel]
        diag = base[rows, d]
        ex = np.exp(u[mun[sel]])
        odds = diag * ex / np.maximum(1 - diag + diag * ex, 1e-12)
        p[rows] = base[rows] * ((1 - odds) / np.maximum(1 - diag, 1e-12))[:, None]
        p[rows, d] = odds
    return np.minimum((rng.random(len(jj))[:, None] > np.cumsum(p, 1)).sum(1), 4)


def exact_forms(r, dk, s, k, N, S):
    """Per key cell (municipality, day) with deaths: the deaths of each sex by class (g), the cell's candidates of each sex by class, and the
    coefficients of a linear form in the cell's T: boys' deaths enter T with their own candidates less the girls' scaled by beta, girls' with the
    girls' less the boys' over beta, so that every class of death in the cell shares the same records (covariances between cells of a row)."""
    key = r * 365 + dk
    uk, inv = np.unique(key, return_inverse=True)
    ur, ud = uk // 365, uk % 365
    g = np.zeros((len(uk), 2, 5))
    np.add.at(g, (inv, s, k), 1.0)
    cM, cF = N[ur, ud, 0][:, :4].astype(float), N[ur, ud, 1][:, :4].astype(float)
    beta = np.where((S[ur, 0] > 0) & (S[ur, 1] > 0), S[ur, 0] / np.maximum(S[ur, 1], 1e-12), 1.0)[:, None]
    return ur, g[:, 0] - g[:, 1] / beta, g[:, 1] - beta * g[:, 0], cM, cF


def exact_se(forms, sel, Ts):
    """The model standard error of the proportions with all covariances, times the row sum: Var(T_j+ p_jk) = a' M_j a, a = e_k - p_jk, M_j the sum over
    key cells of x x' (candidates of boys of class j) + y y' (girls'), x and y from `exact_forms`."""
    ur, x, y, cM, cF = forms
    m = sel[ur]
    row = Ts.sum(1)
    out = np.full((4, 5), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = Ts / row[:, None]
        for j in range(4):
            Mj = (x[m] * cM[m, j:j + 1]).T @ x[m] + (y[m] * cF[m, j:j + 1]).T @ y[m]
            for k in range(5):
                a = np.full(5, -p[j, k])
                a[k] += 1.0
                out[j, k] = np.sqrt(max(a @ Mj @ a, 0.0))
    return out


def cohort(rng, sc, u):
    """One national cohort and its deaths: per municipality T, V, C, VM, VC, deaths, births, the truth's counts (by municipality of residence, of birth,
    and of the deaths found) and the key cells' forms for the exact variance."""
    lam = B5[:, None, :] * W[None]                                    # (M, day, class) expected births
    male = np.array(sc.get("male", P_MALE))
    sexp = np.stack([male, 1 - male])[None, None]                     # (1, 1, sex, class)
    if sc.get("od"):                                                  # a day factor shared by the sexes (their covariance) and one of each sex
        psi, own_v = np.maximum(PSI_M, 1e-6)[:, None], np.maximum(PHI_M - PSI_M, 1e-6)[:, None, None]
        shared = rng.gamma(1 / psi, psi, (M, 365))
        own = rng.gamma(1 / own_v, own_v, (M, 365, 2))
        fac = (shared[:, :, None] * own)[..., None]                   # (M, day, sex, 1)
    else:
        fac = 1.0
    single = rng.poisson(lam[:, :, None, :] * (1 - sc["twins"]) * sexp * fac)   # (M, day, sex, class)
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
    jj = np.minimum(j, 4)
    k_home = certify(rng, j, m, u)
    p_move = np.array(sc["move"])[j] + sc["selective"] * (k_home != jj)
    moved = rng.random(n) < p_move
    r = np.where(moved, destination(rng, m), m)
    moved &= r != m                                                    # a draw of the own municipality is no move
    k = np.where(moved & (sc["selective"] == 0), certify(rng, j, r, u), k_home)
    k = np.minimum(k, 4)
    # a wrong birth date on the death record (typo, swapped day and month): the person is not among the candidates of the recorded day
    dk = d
    err = np.zeros(n, bool)
    if sc.get("keyerr"):
        err = rng.random(n) < np.array(sc["keyerr"])[j] + sc.get("keyerr_k", 0.0) * (k != jj)
        dk = np.where(err, rng.integers(0, 365, n), d)
    lost = moved | err
    # candidates: the births of the death's day and sex where it is resident; control: the other sex, scaled. Deaths that
    # share their key and certified class are one cell, as in the SQL (`modelled_race._candidates`): g of them share
    # their candidates, so the cell's variances carry g squared
    S = N.sum((1, 3)).astype(float)                                    # (M, sex)
    cell, g = np.unique(((r * 365 + dk) * 2 + s) * 5 + k, return_counts=True)
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
    truth, found, origin = (np.zeros((M, J, 5)) for _ in range(3))
    np.add.at(truth, (r, j, k), 1.0)
    np.add.at(origin, (m, j, k), 1.0)
    np.add.at(found, (r[~lost], j[~lost], k[~lost]), 1.0)
    return dict(T=T, V=V, C=C, VM=VM, VC=VC, deaths=deaths, expo=N.sum((1, 2)).astype(float), truth=truth, found=found, origin=origin,
                forms=exact_forms(r, dk, s, k, N, S), lost=float(lost.mean()) if n else 0.0)


def replicate(rng, sc):
    """One replicate: ``pool`` independent cohorts (twelve for the pooled scenarios, each with a twelfth of the deaths) summed, with one municipality
    effect for the replicate; returns the sums per municipality and the key cells' forms of every cohort."""
    u = rng.normal(0, sc["tau"], M) if sc.get("tau") else None
    parts = [cohort(rng, sc, u) for _ in range(sc.get("pool", 1))]
    acc = {k: sum(p[k] for p in parts) for k in ("T", "V", "C", "VM", "VC", "deaths", "expo", "truth", "found", "origin")}
    acc["forms"] = [p["forms"] for p in parts]
    acc["lost"] = float(np.mean([p["lost"] for p in parts]))
    return acc


QUANT = {"p_white_white": ("p", 0, 0), "p_black_black": ("p", 1, 1), "p_black_brown": ("p", 1, 2), "p_brown_brown": ("p", 2, 2),
         "p_brown_white": ("p", 2, 0), "p_indigenous_indigenous": ("p", 3, 3), "mix_white": ("mix", 0, None), "mix_black": ("mix", 1, None),
         "ratio_white": ("ratio", 0, None), "ratio_black": ("ratio", 1, None), "ratio_indigenous": ("ratio", 3, None), "found": ("found", None, None)}


def pick(est, name, which):
    key, a, b = QUANT[name]
    v = est[key + which]
    return float(v if a is None else (v[a] if b is None else v[a, b]))


def truth_of(truth, expo, origin=None):
    """The known answers of a group of municipalities. Proportions and the mix: the deaths certified in the group (by municipality of residence at
    death). Rate ratios: the deaths by municipality of BIRTH over the births of the same municipalities (``origin``), so that numerator and
    denominator describe the same children; a mover's death certified elsewhere is still its birthplace's."""
    tr = truth[:, :4].sum(0)
    og = tr if origin is None else origin[:, :4].sum(0)
    rate = og.sum(1) / expo[:, :4].sum(0)
    return {"p": tr / tr.sum(1, keepdims=True), "mix": tr.sum(1) / tr.sum(), "ratio": rate / rate[2], "found": np.nan}


def mc_cover(c, n):
    return float(np.sqrt(c * (1 - c) / max(n, 1)))


out = {"replicates": REPS, "scenarios": {k: v for k, v in SCEN.items() if ONLY is None or k in ONLY}, "deaths_target": R["children"]["1-9"]["matrix"]["deaths"],
       "municipalities": {lab: int(((size >= lo) & (size < hi)).sum()) for lo, hi, lab in SIZES},
       "parameters": {"dispersion": DISP, "tau": TAU, "key_error_by_class": KEYERR}, "results": {}}
for name, sc in SCEN.items():
    if ONLY is not None and name not in ONLY:
        continue
    rng = np.random.default_rng(20261121)
    acc = {lab: {q: {"est": [], "se": [], "se_poisson": [], "se_chance": [], "se_model": [], "se_exact": [], "truth": [], "truth_found": []} for q in QUANT} for _, _, lab in SIZES}
    invalid = {lab: [] for _, _, lab in SIZES}
    deaths_seen, lost_seen, t0 = [], [], time.time()
    for _rep in range(REPS):
        x = replicate(rng, sc)
        T, V, C, VM, VC, deaths, expo, truth, found = (x[k] for k in ("T", "V", "C", "VM", "VC", "deaths", "expo", "truth", "found"))
        deaths_seen.append(deaths.sum())
        lost_seen.append(x["lost"])
        for lo, hi, lab in SIZES:
            sel = (size >= lo) & (size < hi)
            est = mr.candidate_estimates(T[sel][:, :4], V[sel][:, :4], deaths[sel], expo[sel][:, :4], ref=2, control=C[sel][:, :4],
                                         var_model=VM[sel][:, :4], var_chance=VC[sel][:, :4])
            Ts = T[sel][:, :4].sum(0)
            ex = sum((exact_se(f, sel, Ts) ** 2 for f in x["forms"]), np.zeros((4, 5)))   # cohorts are independent: variances add
            with np.errstate(divide="ignore", invalid="ignore"):
                est["p_se_exact"] = np.sqrt(ex) / np.abs(Ts.sum(1))[:, None]
            tru, trf = truth_of(truth[sel], expo[sel], x["origin"][sel]), truth_of(found[sel], expo[sel])
            invalid[lab].append(bool((Ts.sum(1) <= 0).any()))
            for q in QUANT:
                key, a, b = QUANT[q]
                acc[lab][q]["est"].append(pick(est, q, ""))
                acc[lab][q]["se"].append(pick(est, q, "_se"))
                acc[lab][q]["se_poisson"].append(pick(est, q, "_se_poisson") if key in ("p", "ratio") else np.nan)
                acc[lab][q]["se_chance"].append(pick(est, q, "_se_chance"))
                acc[lab][q]["se_model"].append(pick(est, q, "_se_model") if key in ("p", "mix", "ratio") else np.nan)
                acc[lab][q]["se_exact"].append(pick(est, q, "_se_exact") if key == "p" else np.nan)
                tv = tru[key]
                acc[lab][q]["truth"].append(float(tv if a is None else (tv[a] if b is None else tv[a, b])))
                tv = trf[key]
                acc[lab][q]["truth_found"].append(float(tv if a is None else (tv[a] if b is None else tv[a, b])))
    res = {}
    for lab, qs in acc.items():
        bad = np.array(invalid[lab])
        res[lab] = {"_invalid": int(bad.sum()), "_invalid_share": float(bad.mean())}
        for q, v in qs.items():
            est, se, sp, sc_, sm, sx, tr, tf = (np.array(v[x_]) for x_ in ("est", "se", "se_poisson", "se_chance", "se_model", "se_exact", "truth", "truth_found"))
            sup = np.nanmean(tr)                                      # the system's classification: the truth's mean over replicates
            ok = np.isfinite(est)
            n_ok = int(ok.sum())
            row = {"n": n_ok, "est": float(np.nanmean(est)), "median": float(np.nanmedian(est)), "sd": float(np.nanstd(est, ddof=1)),
                   "se": float(np.nanmean(se)), "se_median": float(np.nanmedian(se)), "se_chance": float(np.nanmean(sc_)), "se_model": float(np.nanmean(sm)),
                   "se_model_median": float(np.nanmedian(sm))}
            if q != "found":
                def cov(target, s_, est=est):
                    return float(np.nanmean(np.abs(est - target) <= 1.96 * s_))
                row |= {"truth": float(np.nanmean(tr)), "truth_found": float(np.nanmean(tf)), "bias": float(np.nanmean(est - tr)),
                        "median_bias": float(np.nanmedian(est - tr)), "bias_found": float(np.nanmean(est - tf)), "median_bias_found": float(np.nanmedian(est - tf)),
                        "mcse_bias": float(np.nanstd(est - tr, ddof=1) / np.sqrt(n_ok)),
                        "mcse_bias_found": float(np.nanstd(est - tf, ddof=1) / np.sqrt(n_ok)),
                        "sd_error_found": float(np.nanstd(est - tf, ddof=1)),
                        "cover": cov(tr, se), "cover_found": cov(tf, se), "cover_super": cov(sup, se),
                        "cover_found_chance": cov(tf, sc_), "cover_super_model": cov(sup, sm), "cover_model": cov(tr, sm),
                        "rmse": float(np.sqrt(np.nanmean((est - tr) ** 2))),
                        "var_ratio_model": float(np.nanmean(sm ** 2) / np.nanvar(est, ddof=1)), "var_ratio_cluster": float(np.nanmean(se ** 2) / np.nanvar(est, ddof=1))}
                if np.isfinite(sp).any():
                    row |= {"se_poisson": float(np.nanmean(sp)), "cover_poisson": cov(tr, sp), "cover_found_poisson": cov(tf, sp), "cover_super_poisson": cov(sup, sp)}
                if np.isfinite(sx).any():
                    row |= {"se_exact": float(np.nanmean(sx)), "se_exact_median": float(np.nanmedian(sx)), "cover_exact": cov(tr, sx), "cover_super_exact": cov(sup, sx),
                            "var_ratio_exact": float(np.nanmean(sx ** 2) / np.nanvar(est, ddof=1))}
                # Monte Carlo errors of every coverage, and the moments among the replicates whose row sums are all positive
                for key_ in [k_ for k_ in row if k_.startswith("cover")]:
                    row[key_ + "_mcse"] = mc_cover(row[key_], n_ok)
                valid = ok & ~bad
                if valid.sum() > 1:
                    row |= {"n_valid": int(valid.sum()), "bias_valid": float(np.mean((est - tr)[valid])), "mcse_bias_valid": float(np.std((est - tr)[valid], ddof=1) / np.sqrt(valid.sum())),
                            "cover_super_model_valid": float(np.mean((np.abs(est - sup) <= 1.96 * sm)[valid]))}
            res[lab][q] = row
    out["results"][name] = res
    out["results"][name]["_deaths_mean"] = float(np.mean(deaths_seen))
    out["results"][name]["_lost_mean"] = float(np.mean(lost_seen))
    print(name, f"{time.time() - t0:.0f} s", "deaths", round(np.mean(deaths_seen)), "found", round(res["all"]["found"]["est"], 3),
          "W->W bias", round(res["<400"]["p_white_white"]["bias"], 4), "found-bias", round(res["<400"]["p_white_white"]["bias_found"], 4), "cover", res["<400"]["p_white_white"]["cover_found"],
          "ratio W bias", round(res["all"]["ratio_white"]["bias"], 3), flush=True)
(PAPER / "results" / OUTNAME).write_text(json.dumps(out, indent=1), encoding="utf-8")
print("DONE", flush=True)
