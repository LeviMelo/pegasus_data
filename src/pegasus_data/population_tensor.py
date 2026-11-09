"""The population account refined to every municipality, every single year of age and every race (modelled tier).

``population_account.py`` estimates comparable areas and five-year bands. This module takes that account to the
resolution the Census publishes:

* **Municipalities.** A comparable area (2000-2010) or a composite entity (2010-2023, the five post-2010 creations joined to
  their parents) is split into its municipalities. The split is a *share*: each member's census count at the earliest
  census that counts it (the 2007 Contagem where every member has one), moved backward by half of the member's 2010-2022
  growth differential. The estimator and its error law are calibrated on pairs of ordinary neighbouring municipalities,
  whose shares are known in the 2000 census and the 2007 Contagem, and checked on the real creations against the Contagem
  (``calibrate_split``); the error enters every member's interval. Registered births by residence, tried as the indicator
  of a member's share, did worse than a constant share (evaluation entry 2026-10-05-population-account-3).
* **Single years of age.** The account's own single-year path (0-79, 80+) is kept; the open class is split into 80-99 and
  100+ by the state's census shape.
* **Race.** Five declared races by cohort composition (``race_shares``).

Every function takes arrays; the build is ``build_tensor``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .population_account import BANDS, Places, load_census, to_bands

YEARS = np.arange(2000, 2031)
NY = len(YEARS)
#: log-share spread classes: the member's census population at its anchor.
MEMBER_CUTS = (2_000, 5_000, 20_000)
Z = {0.8: 1.2816, 0.95: 1.96}


# ------------------------------------------------------------------------------------- member inputs

def member_inputs(root: str | Path, places: Places) -> dict[str, np.ndarray]:
    """Per municipality (``places.municipalities`` order): the raw census by sex
    and single age 2010 and 2022 (a zero row where the municipality did not exist yet), the census-2000 total (NaN where
    it did not exist) and the Contagem-2007 total (NaN where absent)."""
    from .cubes import cube
    from .population_account import _settings, census_table

    ms = places.municipalities
    out = {"c10": load_census(root, 2010, places, "member"), "c22": load_census(root, 2022, places, "member")}
    d = census_table(root, 2000, ["municipality", "population"]).to_pandas()
    tot = d.groupby("municipality").population.sum(min_count=1)
    out["t00"] = np.array([tot.get(m, np.nan) for m in ms], dtype=float)
    rows = {r["place"]: r["value"] for r in cube("sidra:793/93", labels=False, settings=_settings(root)).to_pylist()
            if r["value"] is not None}
    out["t07"] = np.array([rows.get(m, np.nan) for m in ms], dtype=float)
    return out


# ---------------------------------------------------------------------------------- the split estimator

#: Share of a member's 2010-2022 growth differential carried back before the anchor (0.5 beat 0, 0.25 and 1 on the pairs).
SLOPE_WEIGHT = 0.5


def log_trajectory(tot10: np.ndarray, tot22: np.ndarray, t07: np.ndarray, anchor: int):
    """Members' log-size trajectory ℓ (24, M) up to a common additive term per year, and each year's distance in years to
    the nearest census or Contagem that counts them (``dist`` (24,)).

    ``anchor`` 2010: ℓ(2010) = log census 2010; 2007 (when every member has a Contagem count) is log Contagem 2007 and the
    years between are linear in ℓ; before the earliest anchor ℓ moves by ``SLOPE_WEIGHT`` of the member's own growth
    between 2010 and 2022. ``anchor`` 2022: ℓ is the 2022 census, constant (no second count exists for a new municipality)."""
    y = YEARS.astype(float)
    if anchor == 2022:
        return np.tile(np.log(np.maximum(tot22, 1.0)), (len(y), 1)), np.abs(y - 2022)
    l10 = np.log(np.maximum(tot10, 1.0))
    g = np.where((tot10 > 0) & (tot22 > 0), (np.log(np.maximum(tot22, 1.0)) - l10) / 12, 0.0)
    if np.all(np.isfinite(t07)):
        l07 = np.log(np.maximum(t07, 1.0))
        ell = np.where(y[:, None] >= 2007, l07 + (l10 - l07) * ((y[:, None] - 2007) / 3).clip(0, 1),
                       l07 + SLOPE_WEIGHT * g * (y[:, None] - 2007))
        dist = np.where(y < 2007, 2007 - y, np.where(y <= 2010, np.minimum(y - 2007, 2010 - y), y - 2010))
    else:
        ell = l10 + SLOPE_WEIGHT * g * (y[:, None] - 2010) * (y[:, None] < 2010)
        dist = np.abs(y - 2010)
    return ell, dist


def member_shares(P: np.ndarray, ell: np.ndarray, ell_anchor: np.ndarray) -> np.ndarray:
    """Shares (24, M, …) of the area's members: each member's anchor counts ``P`` (M, …) times exp(ℓ(t) − ℓ(anchor))."""
    d = ell - ell_anchor[None]
    w = np.maximum(P, 0)[None] * np.exp(d).reshape(d.shape + (1,) * (P.ndim - 1)) + 1e-9
    return w / w.sum(1, keepdims=True)


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _mad(x):
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def calibrate_split(places: Places, mi: dict[str, np.ndarray], seed: int = 1) -> dict:
    """Error law of the share estimator, measured on pairs of ordinary neighbouring municipalities.

    A pair is a small and a larger municipality of one micro-region that never changed boundary, sized like a child and its
    parent (3 to 60 times). Anchored on the 2010 census with the half growth differential of 2010-2022, the estimator
    predicts the small one's share of the pair in the 2007 Contagem (3 years) and in the 2000 census (10 years). The spread
    (MAD) of the logit-share error by class of the small member gives σ² = σ₀² + k·distance per class. Returns the
    parameters ``(σ₀², k, n)`` per class, the errors, and the error of the share held constant for comparison."""
    rng = np.random.default_rng(seed)
    ms = np.array(places.municipalities)
    units = np.array([places.unit_of[m] for m in ms])
    size_u = np.bincount(units, minlength=places.n_units)
    comp = [m for mem in places.entity_members if len(mem) > 1 for m in mem]
    micro = np.array([places.unit_micro[places.unit_of[m]] for m in ms])
    p10, p22 = mi["c10"].sum((1, 2)), mi["c22"].sum((1, 2))
    ok = (size_u[units] == 1) & ~np.isin(ms, comp) & np.isfinite(mi["t00"]) & np.isfinite(mi["t07"]) & (p10 > 0) & (p22 > 0)
    pairs = []
    for j in np.flatnonzero(ok & (p10 >= 1000) & (p10 <= 40000)):
        big = np.flatnonzero(ok & (micro == micro[j]) & (p10 >= 3 * p10[j]) & (p10 <= 60 * p10[j]))
        if len(big):
            pairs.append((j, int(rng.choice(big))))
    e = {"e00": [], "e07": [], "c00": [], "c07": [], "k10": [], "k00": []}
    size = []
    for j, i in pairs:
        tot10, tot22 = p10[[j, i]], p22[[j, i]]
        ell, _ = log_trajectory(tot10, tot22, np.full(2, np.nan), 2010)
        sh = member_shares(tot10, ell, ell[10])
        for k, yi, tot in (("00", 0, mi["t00"]), ("07", 7, mi["t07"])):
            o = _logit(tot[j] / (tot[j] + tot[i]))
            e["e" + k].append(o - _logit(sh[yi, 0]))
            e["c" + k].append(o - _logit(tot10[0] / tot10.sum()))
        s22 = _logit(p22[j] / (p22[j] + p22[i]))              # a creation known only in 2022: the share held constant
        e["k10"].append(_logit(p10[j] / (p10[j] + p10[i])) - s22)
        e["k00"].append(_logit(mi["t00"][j] / (mi["t00"][j] + mi["t00"][i])) - s22)
        size.append(p10[j])
    arr = {k: np.array(v) for k, v in e.items()}
    cls = np.digitize(np.array(size), MEMBER_CUTS)
    par = []
    for c in range(len(MEMBER_CUTS) + 1):
        m = cls == c
        s00, s07 = _mad(arr["e00"][m]) ** 2, _mad(arr["e07"][m]) ** 2
        k = max((s00 - s07) / 7, 1e-5)
        par.append((max(s07 - 3 * k, 1e-4), k, int(m.sum())))
    # anchored on 2022 alone (the five post-2010 creations): σ = k₂₂·distance, from the spreads at 12 and 22 years
    k22 = float(np.mean([_mad(arr["k10"]) / 12, _mad(arr["k00"]) / 22]))
    cal = {"params": np.array(par), "pairs": len(pairs), "errors": arr, "classes": cls, "k22": k22}
    z = np.concatenate([np.abs(arr["e00"]) / split_sigma(cal, np.array(size), 10.0), np.abs(arr["e07"]) / split_sigma(cal, np.array(size), 3.0)])
    cal["zq"] = {lv: float(np.quantile(z, lv)) for lv in (0.8, 0.95)}      # the standardized errors' own quantiles
    return cal


def split_sigma(cal: dict, member_pop: np.ndarray, dist: np.ndarray, *, census_year: np.ndarray | bool = False) -> np.ndarray:
    """Logit-share sd of members with anchor populations ``member_pop`` at ``dist`` years from their nearest count:
    σ² = k·dist (+ σ₀², the noise of a count that is not the census itself). Beyond the 12 years the calibration reaches,
    the random-walk term simply continues."""
    c = np.digitize(member_pop, MEMBER_CUTS)
    s0, k = cal["params"][c, 0], cal["params"][c, 1]
    return np.sqrt(k * dist + np.where(census_year, 0.0, s0))


# ------------------------------------------------------------------------------- single years of age

#: Single ages of the account's open class: 80..99 and 100+.
OLD = 21
AGES = 101


def fit_spread(e: np.ndarray, u: np.ndarray, bins: int = 12) -> tuple[float, float]:
    """(a², b²) of var(e) = a² + b²·u, from the robust (MAD) spread of ``e`` in ``bins`` quantile bins of ``u``.
    ``u`` is the multinomial term (1−p)/(p·N) of a share p out of N people; a² is the part counts cannot explain."""
    ok = np.isfinite(e) & np.isfinite(u) & (u > 0)
    e, u = e[ok], u[ok]
    edges = np.quantile(u, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, u, side="right") - 1, 0, bins - 1)
    v = np.array([(1.4826 * np.median(np.abs(e[idx == b]))) ** 2 for b in range(bins) if (idx == b).sum() > 30])
    ub = np.array([u[idx == b].mean() for b in range(bins) if (idx == b).sum() > 30])
    X = np.stack([np.ones_like(ub), ub], 1)
    coef = np.linalg.lstsq(X / np.sqrt(ub)[:, None], v / np.sqrt(ub), rcond=None)[0]
    return float(max(coef[0], 1e-6)), float(max(coef[1], 1e-6))


def census_old(root: str | Path, year: int, places: Places) -> np.ndarray:
    """Raw census counts at ages 80..99 and 100+ by municipality × sex, (n, 2, 21)."""
    from .population_account import census_table

    d = census_table(root, year, ["municipality", "sex", "age", "population"]).to_pandas()
    d = d[d.age >= 80].dropna()
    idx = {m: i for i, m in enumerate(places.municipalities)}
    out = np.zeros((len(idx), 2, OLD))
    i = d.municipality.astype(int).map(idx)
    ok = i.notna().to_numpy()
    np.add.at(out, (i[ok].astype(int).to_numpy(), d.sex.astype(int).to_numpy()[ok] - 1, np.minimum(d.age.to_numpy()[ok] - 80, OLD - 1)),
              d.population.to_numpy()[ok])
    return out


def state_shapes(old: dict[int, np.ndarray], state: np.ndarray, states: np.ndarray) -> dict[int, np.ndarray]:
    """Shares of each of the 21 old ages within 80+, by state × sex, at each census year."""
    out = {}
    for y, o in old.items():
        s = np.stack([o[state == u].sum(0) for u in states])
        out[y] = s / np.maximum(s.sum(-1, keepdims=True), 1)
    return out


def shape_at(shapes: dict[int, np.ndarray], t: float) -> np.ndarray:
    """The state shapes at year ``t``: linear between censuses, held at the last one."""
    ys = sorted(shapes)
    if t >= ys[-1]:
        return shapes[ys[-1]]
    hi = next(y for y in ys if y >= t)
    lo = ys[max(ys.index(hi) - 1, 0)]
    if lo == hi:
        return shapes[hi]
    k = (t - lo) / (hi - lo)
    return (1 - k) * shapes[lo] + k * shapes[hi]


def calibrate_shape(inp, root: str | Path, mi: dict, old: dict[int, np.ndarray], states: np.ndarray) -> dict:
    """Spread (a², b²) of the log share of a single age within its band, measured out of sample.

    * ages 0-79: the vital account's own within-band shares at the end of an intercensal period (from the reconciled
      census that opened it, ten and twelve years of deaths and births) against the closing census's;
    * ages 80-99, 100+: the state shape interpolated to 2010 from the 2000 and 2022 censuses against each municipality's
      2010 shares within 80+ (the nearest thing to an interior test the census offers).
    A cell's variance is (a² + b²·u)·f with u = (1−p)/(p·N): p the share, N the band, f the bridge factor of the cell's year."""
    out = {}
    es, us = [], []
    for path, close in ((inp.path_a[-1], inp.close_a), (inp.path_b[-1], inp.close_b)):
        for g in range(16):
            sl = slice(5 * g, 5 * g + 5)
            for x in range(2):
                V, C = path[:, x, sl], close[:, x, sl]
                nb = C.sum(1)
                ok = (nb >= 20) & (V.sum(1) > 0)
                pv = V[ok] / V[ok].sum(1, keepdims=True)
                pc = C[ok] / nb[ok][:, None]
                good = (pv > 0) & (pc > 0)
                es.append(np.log(pc[good] / pv[good]))
                us.append(((1 - pc) / (pc * nb[ok][:, None]))[good])
    out["young"] = fit_spread(np.concatenate(es), np.concatenate(us))
    # old ages
    ms = np.array(inp.places.municipalities)
    state = np.array([int(str(m)[:2]) for m in ms])
    shp = shape_at({2000: state_shapes({2000: old[2000]}, state, states)[2000], 2022: state_shapes({2022: old[2022]}, state, states)[2022]}, 2010)
    st_idx = np.searchsorted(states, state)
    pred = shp[st_idx]
    n80 = old[2010].sum(-1)
    pc = old[2010] / np.maximum(n80[..., None], 1)
    ok = (n80 >= 20)[..., None] & (pc > 0) & (pred > 0)
    e = np.log(np.where(ok, pc, 1) / np.where(ok, pred, 1))[ok]
    u = ((1 - pc) / (pc * np.maximum(n80[..., None], 1)))[ok]
    out["old"] = fit_spread(e, u)
    return out


# ------------------------------------------------------------------------------------------------ race

#: A cohort's log race share moves at most this much a year (≈ one log unit in twelve years). The 2010 and 2022 Censuses
#: counted Asian-descent people differently (2.1M against 0.85M); the cap keeps that instrument change from being extrapolated.
MAX_RATE = 0.08
#: A log-variance beyond this (a share of under one expected person) carries no information: the interval is capped at e^±2.
MAX_VAR = 1.0
RACES = ("branca", "preta", "amarela", "parda", "indigena")
_RACE_OF = {"white": 0, "black": 1, "asian": 2, "brown": 3, "indigenous": 4}
#: The 2000 sample publishes race by these age bands (first age of each).
BANDS_2000 = ((0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, 100))


def load_race(root: str | Path, places: Places) -> dict[int, np.ndarray]:
    """Self-declared race by municipality × sex × age × race (5): the 2010 and 2022 universe by single age 0..100 (SIDRA table
    9606) and the 2000 sample by IBGE's bands spread flat over the band's ages (table 2093). A cell IBGE did not publish is
    counted 0 and tallied in ``loss`` (the five races miss the people with no declared race: a few thousand a census)."""
    from .sidra.series import build_series
    from .sidra.session import Sidra

    s = Sidra(root)
    idx = {m: i for i, m in enumerate(places.municipalities)}
    n = len(idx)
    out = {y: np.zeros((n, 2, AGES, 5), dtype=np.float32) for y in (2000, 2010, 2022)}
    t = build_series(s, "population_race_sex_age").select(["locality", "period", "age", "race_color", "sex", "value"]).to_pandas()
    t = t[t.value.notna()]
    i = t.locality.astype(int).map(idx)
    ok = i.notna().to_numpy()
    t = t[t.race_color.isin(list(_RACE_OF))]
    i = t.locality.astype(int).map(idx)
    ok = i.notna().to_numpy()
    r = t.race_color.map(_RACE_OF).to_numpy().astype(int)
    x = (t.sex == "female").to_numpy().astype(int)
    for y in (2010, 2022):
        m = ok & (t.period == str(y)).to_numpy()
        np.add.at(out[y], (i[m].astype(int).to_numpy(), x[m], t.age.to_numpy()[m], r[m]), t.value.to_numpy()[m])
    b = build_series(s, "population_race_sex_ageband").select(["locality", "period", "age_band", "race_color", "sex", "value"]).to_pandas()
    b = b[(b.period == "2000") & b.value.notna() & b.race_color.isin(list(_RACE_OF))
          & b.age_band.isin([f"{lo}-{hi}" if hi < 80 else "80+" for lo, hi in BANDS_2000])]
    i = b.locality.astype(int).map(idx).to_numpy()
    ok = ~np.isnan(i)
    rb = b.race_color.map(_RACE_OF).to_numpy().astype(int)
    xb = (b.sex == "female").to_numpy().astype(int)
    lab = {(f"{lo}-{hi}" if hi < 80 else "80+"): (lo, hi) for lo, hi in BANDS_2000}
    for key, (lo, hi) in lab.items():
        m = ok & (b.age_band == key).to_numpy()
        per_age = (b.value.to_numpy()[m] / (hi - lo + 1)).astype(np.float32)
        for a in range(lo, hi + 1):
            np.add.at(out[2000], (i[m].astype(int), xb[m], a, rb[m]), per_age)
    return out


def smooth_shares(R: np.ndarray, state: np.ndarray, states: np.ndarray, alpha: float, half: int = 2) -> np.ndarray:
    """Log race shares (n, 2, 101, 5) of a census: counts pooled over ±``half`` ages, ``alpha`` people of the state's own
    shares added (a Dirichlet prior), so a small municipality's single age is not read from three people."""
    c = np.cumsum(np.pad(R, ((0, 0), (0, 0), (half + 1, half), (0, 0))), axis=2)
    pooled = c[:, :, 2 * half + 1:AGES + 2 * half + 1] - c[:, :, 0:AGES]
    st = np.stack([R[state == u].sum(0) for u in states])
    cs = np.cumsum(np.pad(st, ((0, 0), (0, 0), (half + 1, half), (0, 0))), axis=2)
    pst = cs[:, :, 2 * half + 1:AGES + 2 * half + 1] - cs[:, :, 0:AGES]
    pst = (pst + 1e-3) / (pst + 1e-3).sum(-1, keepdims=True)
    k = np.searchsorted(states, state)
    p = (pooled + alpha * pst[k]) / (pooled.sum(-1, keepdims=True) + alpha)
    return np.log(p)


def pair_drift(zs: np.ndarray, ze: np.ndarray, gap: int, state: np.ndarray, states: np.ndarray, pop_s: np.ndarray,
               pop_e: np.ndarray) -> np.ndarray:
    """Per-year change of the log race shares of a cohort, by state × sex × age at the start × race: the state's shares at
    the later census at age a+gap against the earlier at age a. This is the reclassification term — what composition
    change a cohort shows net of everything the state's census can see — and it is identified only if the cohort's migration
    does not differ by race inside the state, which is the assumption (a state's net migration is small against its
    cohort; the municipal deviation from the state drift is carried as spread)."""
    def agg(z, pop):
        w = np.exp(z) * pop[..., None]
        sw = np.stack([w[state == u].sum(0) for u in states])
        return np.log(np.maximum(sw / np.maximum(sw.sum(-1, keepdims=True), 1e-9), 1e-9))
    a, b = agg(zs, pop_s), agg(ze, pop_e)
    d = np.zeros_like(a)
    d[:, :, :AGES - gap] = (b[:, :, gap:] - a[:, :, :AGES - gap]) / gap
    d[:, :, AGES - gap:] = d[:, :, AGES - gap - 1:AGES - gap]
    return d


def z_at(t: int, anchors: dict[int, np.ndarray], rho_back: dict[int, np.ndarray] | None, drift_fwd: np.ndarray | None,
         k_state: np.ndarray, rho_age: int = 5):
    """Log race shares (n, 2, 101, 5) at year ``t`` by cohort, and the variance factor of each age (101,) and kind.

    A cohort aged a at t was aged a−(t−L) at the census L < t and will be a+(U−t) at U > t. Alive at both, its log shares
    are linear between the two (``kind`` 1, factor κ(1−κ)/κ₀(1−κ₀) with κ₀ the 2010 position in 2000-2022). Alive only at U
    (born after L), they are those at U moved back by the state's per-year reclassification rate ``rho_back[U]`` for the
    cohorts' first years (``kind`` 2, factor years/12). After the last census (``drift_fwd`` per year at the cohort's age,
    ``kind`` 3, factor years/12). A census year returns the census (factor 0)."""
    Ys = sorted(anchors)
    n = next(iter(anchors.values())).shape[0]
    if t in anchors:
        return anchors[t], np.zeros(AGES), np.zeros(AGES, int)
    ages = np.arange(AGES)
    L = max([y for y in Ys if y < t], default=None)
    U = min([y for y in Ys if y > t], default=None)
    z = np.zeros((n, 2, AGES, 5), dtype=np.float32)
    f = np.zeros(AGES)
    kind = np.zeros(AGES, int)
    aU = np.minimum(ages + (U - t), AGES - 1) if U else None
    if L is not None:
        aL = ages - (t - L)
        has_L = aL >= 0
    if U is None:                                            # after the last census
        zl = anchors[L][:, :, np.clip(aL, 0, AGES - 1)]
        dr = drift_fwd[k_state][:, :, np.clip(aL, 0, AGES - 1)] if drift_fwd is not None else 0.0
        z = zl + dr * (t - L)
        # a newborn since L: the youngest cohort of the last census, unmoved
        z = np.where(has_L[None, None, :, None], z, anchors[L][:, :, :1])
        return z, np.full(AGES, (t - L) / 10.0), np.full(AGES, 3)
    zu = anchors[U][:, :, aU]
    if L is None:
        has_L = np.zeros(AGES, bool)
        aL = np.zeros(AGES, int)
    zl = anchors[L][:, :, np.clip(aL, 0, AGES - 1)] if L is not None else zu
    kappa = (t - L) / (U - L) if L is not None else 0.0
    z = np.where(has_L[None, None, :, None], (1 - kappa) * zl + kappa * zu, zu)
    k0 = 10 / 22
    f = np.where(has_L, kappa * (1 - kappa) / (k0 * (1 - k0)), (U - t) / 12.0)
    kind = np.where(has_L, 1, 2)
    if rho_back is not None and U in rho_back:
        back = np.where(has_L, 0.0, 1.0)[None, None, :, None] * (U - t) * rho_back[U][k_state][:, :, None, :]
        z = z - back
    return z, f, kind


def softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


def fill_missing(R: np.ndarray, places: Places) -> np.ndarray:
    """A municipality with no people at a census (it did not exist yet) takes its comparable area's pooled composition there:
    the new territory was part of the area, so the area's mix is the best prior for it."""
    out = R.copy()
    n = R.shape[0]
    unit = np.array([places.unit_of[m] for m in places.municipalities])
    empty = R.sum((1, 2, 3)) == 0
    for u in np.unique(unit[empty]):
        mem = np.flatnonzero(unit == u)
        pooled = R[mem[~empty[mem]]].sum(0)
        for i in mem[empty[mem]]:
            out[i] = pooled
    assert out.shape[0] == n
    return out


def race_context(R: dict[int, np.ndarray], places: Places) -> dict:
    """Smoothed log shares at each census, the state-level reclassification rates between them, and the state index."""
    ms = np.array(places.municipalities)
    state = np.array([int(str(m)[:2]) for m in ms])
    states = np.unique(state)
    R = {y: fill_missing(r, places) for y, r in R.items()}
    Z = {2000: smooth_shares(R[2000], state, states, 10.0), 2010: smooth_shares(R[2010], state, states, 3.0),
         2022: smooth_shares(R[2022], state, states, 3.0)}
    P = {y: r.sum(-1) for y, r in R.items()}
    d0010 = pair_drift(Z[2000], Z[2010], 10, state, states, P[2000], P[2010])
    d1022 = pair_drift(Z[2010], Z[2022], 12, state, states, P[2010], P[2022])
    d0010, d1022 = np.clip(d0010, -MAX_RATE, MAX_RATE), np.clip(d1022, -MAX_RATE, MAX_RATE)
    return {"R": R, "Z": Z, "state": state, "states": states, "k_state": np.searchsorted(states, state),
            "drift": {(2000, 2010): d0010, (2010, 2022): d1022},
            "rho": {2010: d0010[:, :, :5].mean(2), 2022: d1022[:, :, :5].mean(2)}}


def calibrate_race(ctx: dict) -> dict:
    """Spread (a², b²) of the race shares for the three kinds of cohort path, measured out of sample on the 2010 census:

    * ``bridge`` — 2010 by log-linear interpolation between 2000 and 2022, ages 10-79 (a cohort alive at both);
    * ``back`` — 2010 for ages 0-9 from 2022 alone, moved back by the *other* decade's reclassification rate;
    * ``fwd`` — 2010 from 2000 alone, moved forward by the *other* decade's drift (a ten-year forecast).
    The error is scored at the 5-year bands of age (cells of ≥ 200 people), not centred: a bias is part of the spread."""
    R, Z, k_state = ctx["R"], ctx["Z"], ctx["k_state"]
    N10 = R[2010].sum(-1)
    d1022, rho0010 = ctx["drift"][(2010, 2022)], ctx["rho"][2010]

    def run(z, lo, hi):
        cnt = N10[..., None] * softmax(z)
        sh = lambda x: x[:, :, lo:hi].reshape(x.shape[0], 2, (hi - lo) // 5, 5, 5).sum(3)      # noqa: E731
        po, pp = sh(R[2010]), sh(cnt)
        nb = po.sum(-1)
        so, sp = po / np.maximum(nb[..., None], 1), pp / np.maximum(pp.sum(-1, keepdims=True), 1e-9)
        ok = (nb >= 200)[..., None] & (so > 0) & (sp > 0)
        e = np.log(np.where(ok, so, 1) / np.where(ok, sp, 1))[ok]
        u = ((1 - sp) / (np.maximum(sp, 1e-9) * np.maximum(nb[..., None], 1)))[ok]
        return e, u
    out = {}
    z, _, _ = z_at(2010, {2000: Z[2000], 2022: Z[2022]}, None, None, k_state)
    out["bridge"] = run(z, 10, 80)
    z, _, _ = z_at(2010, {2022: Z[2022]}, {2022: rho0010}, None, k_state)
    out["back"] = run(z, 0, 10)
    z, _, _ = z_at(2010, {2000: Z[2000]}, None, d1022, k_state)
    out["fwd"] = run(z, 10, 80)
    return {k: fit_spread(*v, bins=12) for k, v in out.items()} | {"cells": {k: int(len(v[0])) for k, v in out.items()}}


# ----------------------------------------------------------------------------------------- the tensor

BASIS = ("census", "intercensal", "backcast", "forecast")
RACE_LEVELS = ("total", *RACES)
BANDS101 = np.minimum(np.arange(AGES) // 5, 16)


def account_arrays(inp, cal, fc: dict) -> dict:
    """The account's single-age paths and the log offsets of its band intervals, for the three blocks: comparable areas
    2000-2010, municipalities 2010-2022 and the forecast ``fc`` (``population_forecast.forecast_account``, 2023-2030)."""
    from .population_account import (
        LEVELS,
        distribute_residual,
        interval,
        migration_schedule,
        schedule_rates,
        to_bands,
    )

    sched = migration_schedule(inp)
    Xa = distribute_residual(inp.path_a, inp.close_a, schedule_rates(sched, inp.close_a.sum((1, 2))))
    Xb = distribute_residual(inp.path_b, inp.close_b, schedule_rates(sched, inp.close_b.sum((1, 2))))
    off = {}
    for name, P, X, T in (("A", inp.A, Xa, 10), ("B", inp.B, Xb, 12)):
        bands = np.stack([to_bands(x) for x in X])
        c = np.log(np.maximum(bands, 1e-9))
        for lv in LEVELS:
            lo, hi = zip(*(interval(P, cal, bands[k], float(k), lv, total=False, timing=k / T) for k in range(T + 1)), strict=True)
            off[name, lv] = (c - np.array(lo), np.array(hi) - c)
    for lv in LEVELS:
        off["P", lv] = fc["off"][lv]
    return {"Xa": Xa, "Xb": Xb, "Xf": fc["X"], "off": off, "levels": LEVELS}


def group_shares(places: Places, mi: dict, split_cal: dict) -> dict[int, dict]:
    """For each unit with several municipalities, every member's band shares at the 24 years, the logit-share sd and the
    first year the shares are anchored at (the year the area is a census count of the member itself)."""
    from .population_account import to_bands

    ms = places.municipalities
    members: dict[int, list[int]] = {}
    for i, m in enumerate(ms):
        members.setdefault(places.unit_of[m], []).append(i)
    composite = {places.unit_of[mem[0]] for mem in places.entity_members if len(mem) > 1}
    out = {}
    for u, mem in members.items():
        if len(mem) < 2:
            continue
        anchor = 2022 if u in composite else 2010
        c = mi["c22"] if anchor == 2022 else mi["c10"]
        P = to_bands(c[mem])
        tot10, tot22 = mi["c10"][mem].sum((1, 2)), mi["c22"][mem].sum((1, 2))
        ell, dist = log_trajectory(tot10, tot22, mi["t07"][mem], anchor)
        ai = int(np.flatnonzero(anchor == YEARS)[0])
        S = member_shares(P, ell, ell[ai])
        pop = np.maximum(tot22 if anchor == 2022 else tot10, 1.0)
        if anchor == 2022:
            sig = np.repeat((split_cal["k22"] * dist)[:, None], len(mem), 1)
        else:
            sig = split_sigma(split_cal, pop[None, :], dist[:, None], census_year=(anchor == YEARS)[:, None])
        if anchor == 2010:                                  # from 2010 on a member is its own entity: no split
            S[ai:], sig[ai:] = 1.0, 0.0
        else:
            sig[ai] = 0.0
        out[u] = {"members": mem, "S": S, "sig": sig, "anchor": ai}
    return out


def age_cells(Xarea: np.ndarray, sh: np.ndarray, sg: np.ndarray, fs: np.ndarray, ft: np.ndarray, shape_cal: dict):
    """One municipality's years: the area's bands (Y, 2, 81) times the member's band shares ``sh`` (Y, 2, 17) with sd ``sg``
    (Y,), to single ages 0..100 (Y, 2, 101) (80+ split by the state's shape ``fs`` (Y, 2, 21)); also the split's sd per age and the
    log-variance of the age's share inside its band, times the year's bridge factor ``ft`` (Y,)."""
    Xm = Xarea * sh[:, :, BANDS]
    sdsplit = ((1 - sh) * sg[:, None, None])[..., BANDS]                                              # (Y, 2, 81)
    X80 = Xm[..., 80]
    X = np.concatenate([Xm[..., :80], X80[..., None] * fs], -1)
    sdsplit = np.concatenate([sdsplit[..., :80], np.repeat(sdsplit[..., 80:81], OLD, -1)], -1)
    bs = X[..., :80].reshape(len(X), 2, 16, 5).sum(-1)
    p = X[..., :80] / np.maximum(np.repeat(bs, 5, -1), 1e-9)
    uy = (1 - p) / np.maximum(p * np.repeat(bs, 5, -1), 1e-9)
    po = fs
    uo = (1 - po) / np.maximum(po * X80[..., None], 1e-9)
    var_sh = np.concatenate([np.minimum((shape_cal["young"][0] + shape_cal["young"][1] * uy) * ft[:, None, None], MAX_VAR),
                             np.minimum((shape_cal["old"][0] + shape_cal["old"][1] * uo) * (4 * ft)[:, None, None], MAX_VAR)], -1)
    return X, sdsplit, var_sh


def year_frames(ctx: dict, old: dict) -> tuple[np.ndarray, np.ndarray]:
    """The state's census shape of the open age class at each of the 31 years, ``(NY, S, 2, 21)``, and the bridge factor of
    the single-age share errors, ``(NY,)`` (zero at the 2010 census, rising between the censuses)."""
    shapes = state_shapes(old, ctx["state"], ctx["states"])
    fshape = np.stack([shape_at(shapes, float(y)) for y in YEARS])
    k = np.arange(NY)
    ft = np.where(k < 10, (k / 10) * (1 - k / 10), np.where(k == 10, 0.0, np.where(k < 22, ((k - 10) / 12) * (1 - (k - 10) / 12),
                                                                                    np.minimum((k - 22) / 10, 1.0))))
    return fshape, ft


def member_cells(i: int, places: Places, acc: dict, groups: dict, fshape: np.ndarray, ft: np.ndarray, ctx: dict, shape_cal: dict):
    """One municipality's single-age populations over the 31 years, ``(NY, 2, 101)``, with the split's sd, the log-variance of
    the age shares, and the year its area is its own census count (None: the municipality is its area)."""
    m = places.municipalities[i]
    u, e = places.unit_of[m], places.entity_of[m]
    Xarea = np.concatenate([acc["Xa"][:10, u], acc["Xb"][:, e], acc["Xf"][:, e]])             # (NY, 2, 81)
    g = groups.get(u)
    if g is None:
        sh, sg, ai = np.ones((NY, 2, 17)), np.zeros(NY), None
    else:
        mem = g["members"].index(i)
        sh, sg, ai = g["S"][:, mem], g["sig"][:, mem], g["anchor"]
    X, sdsplit, var_sh = age_cells(Xarea, sh, sg, fshape[:, ctx["k_state"][i]], ft, shape_cal)
    return X, sdsplit, var_sh, ai


def census_ages(inp, acc: dict, groups: dict, ctx: dict, old: dict, shape_cal: dict, years: tuple[int, ...]) -> dict[int, np.ndarray]:
    """Per municipality, sex and single age (0..79 and 80+, ``(M, 2, 81)``) the product's population at ``years``, as the
    product holds it (float32 cells, the ages from 80 added): the municipal anchors of the split before 2000."""
    places = inp.places
    fshape, ft = year_frames(ctx, old)
    at = [int(np.flatnonzero(y == YEARS)[0]) for y in years]
    out = {y: np.zeros((len(places.municipalities), 2, 81)) for y in years}
    for i in range(len(places.municipalities)):
        X = member_cells(i, places, acc, groups, fshape, ft, ctx, shape_cal)[0].astype(np.float32).astype(float)
        for y, k in zip(years, at, strict=True):
            out[y][i, :, :80] = X[k, :, :80]
            out[y][i, :, 80] = X[k, :, 80:].sum(-1)
    return out


def tensor_tables(inp, cal, fc: dict, mi: dict, split_cal: dict, shape_cal: dict, ctx: dict, race_cal: dict, old: dict, *, chunk: int = 120,
                  only: tuple[int, ...] | None = None, acc: dict | None = None, groups: dict | None = None, log=print):
    """Yield the product as pyarrow tables of ``chunk`` municipalities: municipality × year × sex × age (0..100) × race
    (total and five), with the 80% and 95% interval of each cell and the basis of the year. ``acc`` (`account_arrays`) and
    ``groups`` (`group_shares`) are computed when not given."""
    import pyarrow as pa

    from .population_account import LEVELS

    places = inp.places
    ms = np.array(places.municipalities)
    acc = account_arrays(inp, cal, fc) if acc is None else acc
    groups = group_shares(places, mi, split_cal) if groups is None else groups
    fshape, ft = year_frames(ctx, old)
    zq = split_cal["zq"]
    rho_back = {2010: ctx["rho"][2010], 2022: ctx["rho"][2022]}
    a2 = np.array([0.0, race_cal["bridge"][0], race_cal["back"][0], race_cal["fwd"][0]])
    b2 = np.array([0.0, race_cal["bridge"][1], race_cal["back"][1], race_cal["fwd"][1]])
    cens = np.isin(YEARS, (2000, 2010, 2022))
    for st in ctx["states"]:
        if only is not None and int(st) not in only:
            continue
        idx = np.flatnonzero(ctx["state"] == st)
        anchors = {y: ctx["Z"][y][idx] for y in ctx["Z"]}
        ks = ctx["k_state"][idx]
        pi, fr, kd = [], [], []
        for t in YEARS:
            z, f, kk = z_at(int(t), anchors, rho_back, ctx["drift"][(2010, 2022)], ks)
            pi.append(softmax(z).astype(np.float32))
            fr.append(f)
            kd.append(kk)
        pi, fr, kd = np.stack(pi), np.stack(fr), np.stack(kd)                            # (NY, n, 2, 101, 5), (NY, 101)
        A2, B2 = a2[kd], b2[kd]
        for c0 in range(0, len(idx), chunk):
            sel = idx[c0:c0 + chunk]
            n = len(sel)
            out = {key: np.zeros((n, NY, 2, AGES, 6), dtype=np.float32) for key in ("pop", "lo", "hi", "lo95", "hi95")}
            basis = np.zeros((n, NY), dtype=np.int8)
            for j, i in enumerate(sel):
                u, e = places.unit_of[ms[i]], places.entity_of[ms[i]]
                offs = {lv: tuple(np.concatenate([acc["off"]["A", lv][s][:10, u], acc["off"]["B", lv][s][:, e],
                                                  acc["off"]["P", lv][s][:, e]]) for s in (0, 1)) for lv in LEVELS}
                X, sdsplit, var_sh, ai = member_cells(i, places, acc, groups, fshape, ft, ctx, shape_cal)
                npool = np.cumsum(np.pad(X, ((0, 0), (0, 0), (3, 2))), -1)
                npool = npool[..., 5:AGES + 5] - npool[..., 0:AGES]
                pr = pi[:, c0 + j]                                                                                    # (NY, 2, 101, 5)
                ur = (1 - pr) / np.maximum(pr * npool[..., None], 1e-9)
                var_r = np.minimum((A2[:, None, :, None] + B2[:, None, :, None] * ur) * fr[:, None, :, None], MAX_VAR)
                pop = np.concatenate([X[..., None], X[..., None] * pr], -1)                                      # (NY, 2, 101, 6)
                out["pop"][j] = pop
                for lv, nm in zip(LEVELS, ("", "95"), strict=True):
                    zl = Z[lv]
                    lo_b, hi_b = offs[lv][0][..., BANDS101], offs[lv][1][..., BANDS101]
                    extra = np.minimum((zq[lv] * sdsplit) ** 2 + zl**2 * var_sh, 4.0)
                    ex = np.concatenate([extra[..., None], extra[..., None] + zl**2 * var_r], -1)
                    out["lo" + nm][j] = pop * np.exp(-np.sqrt(lo_b[..., None] ** 2 + ex))
                    out["hi" + nm][j] = pop * np.exp(np.sqrt(hi_b[..., None] ** 2 + ex))
                b = np.full(NY, 1, dtype=np.int8)                                                               # intercensal
                b[cens] = 0
                b[23:] = 3
                if ai is not None:
                    b[:ai] = 2
                    b[ai] = 0
                basis[j] = b
            size = n * NY * 2 * AGES * 6
            rep = lambda v, r, t_=1: np.tile(np.repeat(v, r), t_)      # noqa: E731
            cols = {
                "municipality": pa.array(np.repeat(ms[sel].astype(np.int32), NY * 2 * AGES * 6)),
                "year": pa.array(rep(YEARS.astype(np.int16), 2 * AGES * 6, n)),
                "sex": pa.array(rep(np.array([1, 2], np.int8), AGES * 6, n * NY)),
                "age": pa.array(rep(np.arange(AGES, dtype=np.int16), 6, n * NY * 2)),
                "race": pa.DictionaryArray.from_arrays(pa.array(np.tile(np.arange(6, dtype=np.int8), size // 6)),
                                                       pa.array(RACE_LEVELS)),
                "population": pa.array(out["pop"].ravel()), "population_lo": pa.array(out["lo"].ravel()),
                "population_hi": pa.array(out["hi"].ravel()), "population_lo95": pa.array(out["lo95"].ravel()),
                "population_hi95": pa.array(out["hi95"].ravel()),
                "basis": pa.DictionaryArray.from_arrays(pa.array(np.repeat(basis.ravel(), 2 * AGES * 6)), pa.array(BASIS)),
            }
            yield pa.table(cols)
        log(f"state {st}: {len(idx)} municipalities")


def build_population_account(settings, *, version: str, validation: str, only: tuple[int, ...] | None = None, log=print) -> dict:
    """Build and write the ``population_account`` modelled product from the data home alone: municipality × year 1991-2030 ×
    sex × single age 0..100 × race (total and five, total only before 2000), with 80% and 95% intervals and the basis of
    each year (census, intercensal, backcast, forecast).

    The steps, each computed here from the home (``settings.root``) and nothing else:

    1. the events: deaths (SIM-DO, SIM-DOR to 1995) and births (SINASC-DN from 1994) by residence, sex and age for 1991-2023,
       read from the records cube (`population_account.vital_events`);
    2. the vital account of comparable areas and entities between the censuses, its calibration, and the forecast to 2030;
    3. the municipal split, the race composition and the single-age shapes (`member_inputs` ... `calibrate_shape`);
    4. the migration schedule that carries each intercensal residual along the cohorts, and the account before 2000
       (`population_backcast`), split with the municipal estimate of 2000 and 2010 this build holds;
    5. the rows of 1991-1999, then 2000-2030, written as one version, never over a stored one.

    ``only`` restricts the 2000-2030 rows to states (a development run: the product is then partial)."""
    from . import __version__
    from . import population_backcast as pb
    from .modelled import ModelledManifest, write_modelled
    from .population_account import (
        assemble,
        fit_calibration,
        migration_schedule,
        widen_to_nominal,
    )
    from .population_forecast import EVENT_SD_PER_YEAR, forecast_account

    root = settings.root
    log("events 1991-2023")
    inp = assemble(settings, log)
    places = inp.places
    log("calibration of the account's bands")
    cal = widen_to_nominal(fit_calibration([inp.A, inp.B]), [inp.A, inp.B])
    log("forecast")
    fc = forecast_account(inp, cal, settings)
    log("members, split error, race, ages")
    mi = member_inputs(root, places)
    split_cal = calibrate_split(places, mi)
    ctx = race_context(load_race(root, places), places)
    race_cal = calibrate_race(ctx)
    old = {y: census_old(root, y, places) for y in (2000, 2010, 2022)}
    shape_cal = calibrate_shape(inp, root, mi, old, ctx["states"])
    acc = account_arrays(inp, cal, fc)
    groups = group_shares(places, mi, split_cal)

    log("the account before 2000")
    pre = pb.Pre(settings, places, log)
    pre.use_schedule(migration_schedule(inp))
    ages = census_ages(inp, acc, groups, ctx, old, shape_cal, (2000, 2010))
    index = {m: i for i, m in enumerate(places.municipalities)}
    sig00 = np.zeros(len(index))
    for g in groups.values():
        for j, i in enumerate(g["members"]):
            sig00[i] = g["sig"][0, j]
    by_area: dict[int, list[int]] = {}
    for m in places.municipalities:
        by_area.setdefault(pre.area_of[m], []).append(index[m])
    S = pb.split_shares(pre, by_area, pb.member_totals(root, places.municipalities), to_bands(ages[2000]), ages[2010].sum((1, 2)),
                        split_cal, sig00, use96=True)
    back = pb.backcast_tables(pre, cal, S, shape_cal, ctx, old, log=log)
    tail = tensor_tables(inp, cal, fc, mi, split_cal, shape_cal, ctx, race_cal, old, only=only, acc=acc, groups=groups, log=log)

    par = split_cal["params"]
    manifest = ModelledManifest(
        product="population_account", version=version,
        model="population_account.py v2 (the vital cohort-component account, migration regression, calibrated band intervals) and population_forecast.py (births and deaths from their trends) "
              "refined by population_tensor.py: municipal split by the 2007 Contagem and the 2010-2022 growth differential, single "
              "years of age from the account's own path (80+ by the state's census shape), race by cohort composition between "
              "the censuses with a state reclassification rate" + pb.MODEL +
              "; the intercensal residual is carried along the cohorts by an age schedule of migration",
        estimates={"population": ["population_lo", "population_hi", "population_lo95", "population_hi95"]},
        place="municipality", period="year", strata=["sex", "age", "race"], additive=["population"],
        inputs={"population-account-2 inputs": "see that version's manifest (census 2000/2010/2022, SIM, SINASC, PES, POPSVS, SIDRA 200)",
                "CENSO 2010, 2022 race by single age": "SIDRA table 9606", "CENSO 2000 race by age band (sample)": "SIDRA table 2093",
                "Contagem 2007 (municipal totals, the split's second anchor)": "SIDRA table 793",
                "SINASC births by residence": f"pegasus_data {__version__} (tried as a split indicator and discarded)", **pb.INPUTS},
        validation=validation,
        notes=["Reference date 1 August of `year`. `race` is `total` (all declared races, the account's own estimate) or one of "
               "branca, preta, amarela, parda, indigena; the five add up to the total (people with no declared race, 0.003-0.006% "
               "of a census, are in the total).",
               "`basis`: `census` (a census year, a count of that municipality), `intercensal` (between two censuses that both count "
               "the municipality), `backcast` (before the earliest census or Contagem that counts the municipality itself: the "
               "area it belongs to is estimated and the municipality is its split), `forecast` (2023-2030, after the last census).",
               "Totals by band equal population-account-2's: single ages 0-79 are the account's own path, 80+ is split into 80-99 and "
               "100+ by the state's census shape (linear in time between censuses, held after 2022); an area's municipalities add "
               "to the area.",
               "Municipal split (areas of several municipalities): share anchored on the census that counts every member (2010, "
               "2022 for the five post-2010 creations), the Contagem 2007 where every member has one, moved back by "
               f"{SLOPE_WEIGHT} of the member's 2010-2022 growth differential. Logit-share sd per size class: σ₀² "
               + ", ".join(f"{p[0]:.4f}" for p in par) + "; k per year " + ", ".join(f"{p[1]:.4f}" for p in par)
               + f" (classes of the member's population: <{MEMBER_CUTS[0]}, <{MEMBER_CUTS[1]}, <{MEMBER_CUTS[2]}, above); quantiles of "
               f"its standardized errors {split_cal['zq'][0.8]:.2f} (80%) and {split_cal['zq'][0.95]:.2f} (95%).",
               "Forecast (2023-2030): the vital account from the PES-corrected 2022 census with the SINASC and SIM events to 2023 and "
               "projected births and deaths after (national death rate by sex and band and births per woman 15-44, log-linear over ten "
               "non-COVID years; each municipality's level from the three reference years), moved by the migration regression at "
               f"the horizon; interval: the account's at the horizon plus {EVENT_SD_PER_YEAR} per year (the measured spread of the "
               "event projection). Pseudo-forecasts from 2000 and 2010 in the evaluation entry.",
               "Single-age intervals: the band's interval of the account, in quadrature with the share of the age inside its band "
               f"(a², b² = {shape_cal['young'][0]:.4f}, {shape_cal['young'][1]:.3f} for 0-79; {shape_cal['old'][0]:.4f}, "
               f"{shape_cal['old'][1]:.3f} for 80+, times the bridge factor of the year).",
               "Race intervals: the cell's interval in quadrature with the race share's, (a² + b²·(1−π)/(π n)) times the path factor; "
               "a², b² (bridge, back, forward) = " + "; ".join(f"{k}: {race_cal[k][0]:.4f}, {race_cal[k][1]:.3f}"
                                                              for k in ("bridge", "back", "fwd")) + ".",
               "Race is not fixed: shares move along each birth cohort between censuses (log-linear), and a cohort born after a "
               "census is moved back from the next one by the state's per-year reclassification rate from the previous decade. "
               "Identification: the state's cohort composition change net of nothing else; municipal deviations from it are spread.",
               "A municipality with no people at a census takes its area's composition there. 2000 race is the IBGE sample, spread "
               "flat inside its age bands.",
               *pb.NOTES,
               "Interior timing: the residual of each intercensal period (and of 1991-2000) is carried along the cohorts by an age "
               "schedule of net migration (population_account.fit_schedule: yearly rates by age, per sex and size class, fitted on the "
               "cohort residuals of 2000-2010 and 2010-2022; mostly ages 15-27) instead of evenly through the years; censuses and bands "
               "at the census years are unchanged, the interior years differ from an even carrying (women 20-44 of small places by up "
               "to 2-3%)."])

    def chain():
        yield from back
        yield from tail

    log("writing")
    out = write_modelled(chain(), manifest, settings=settings)
    return {"path": str(out), "split_cal": split_cal["params"].tolist(), "race_cal": race_cal, "shape_cal": shape_cal}
