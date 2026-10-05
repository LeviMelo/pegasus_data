"""The population account: a cohort-component account of every municipality, 2000 onward (modelled tier).

Person-years by place × single year of age × sex between censuses are not observed. They are
accounted for here, in the demographic sense:

    P(t+1, a+1) = P(t, a) − deaths(t, a)·(1+λ) + net migration(t, a)        (a > 0)
    P(t+1, 0)   = births(t)·(1+κ) − deaths(t, 0)·(1+λ) + ...

with the vital events from SIM and SINASC, steps from one census reference date (1 August) to the
next (Lexis: half of the deaths at age a leave the cohort aged a at the step's start, half the cohort
aged a−1). Three things in it are estimated, none assumed:

* **registration completeness**, ``κ`` for births and ``λ`` for deaths: the share of events the
  systems did not register, per municipality, shrunk to micro-region, state and nation;
* **net migration**, a smooth age profile (B-splines) per sex whose coefficients are a national
  mean plus state, micro-region and municipal effects (a Gaussian hierarchy sampled by Gibbs);
* **the census's own error**, as observation noise of a size that is estimated from the residuals.

The estimates are *trained* on one intercensal period (the intercensal residual is the data) and
*predict* the next with no information from its closing census; ``score`` compares that prediction
with the census and with POPSVS. Draws of the parameters are propagated through the account, so
every estimate carries an interval (PegaSUS P8). A municipality created after the training
period's start is estimated inside its *comparable area* (IPEA's AMC, extended to the five
post-2010 creations by their parents) and forecast with that area's parameters.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

#: Single years 0..79 and an open 80+ (SIM's and POPSVS's closure).
A = 81
#: Census reference date is 1 August: a step from year t carries 5/12 of year t's events and 7/12 of t+1's.
W_FIRST, W_SECOND = 5 / 12, 7 / 12
#: Share of deaths the systems did not register, assumed over 2000–2010 (SIM's coverage was about 85–94% by the
#: Ministry of Health's and IBGE's estimates). It is an input, not an estimate: against the cohorts alone it cannot be
#: told from net migration at the oldest ages (it removes people in proportion to old-age mortality, as migration
#: out does), and left free the data put it at nonsense (λ < 0).
DEATH_SHORTFALL = 0.10
#: Hand-checked lineage of the five municipalities created after the 2010 census (IBGE, Lei estadual 2013):
#: they belong to no published comparable area, so each joins its parents'.
POST_2010_CREATIONS = {
    1504752: [1506807],                      # Mojuí dos Campos <- Santarém
    4212650: [4209409],                      # Pescaria Brava <- Laguna
    4220000: [4207007],                      # Balneário Rincão <- Içara
    4314548: [4302105, 4307906, 4305959],    # Pinto Bandeira <- Bento Gonçalves, Farroupilha, Cotiporã
    5006275: [5003256, 5002951, 5000203],    # Paraíso das Águas <- Costa Rica, Chapadão do Sul, Água Clara
}


# --------------------------------------------------------------------------------------- geography

@dataclass
class Places:
    """The municipalities, their estimation units and their forecast entities.

    A *unit* is a comparable area (estimation: 2000 and 2010 are on the same boundaries there). An
    *entity* is what is forecast and reported: the municipality, except inside a unit touched by a post-2010
    creation, where the whole unit is one entity (the child has no 2010 base of its own).
    """

    municipalities: list[int]                  # 7-digit codes, the current 5,570
    unit_of: dict[int, int]                    # municipality -> unit index
    entity_of: dict[int, int]                  # municipality -> entity index
    entity_members: list[list[int]]
    entity_unit: np.ndarray                    # entity -> unit
    unit_uf: np.ndarray                        # unit -> state code (int)
    unit_micro: np.ndarray                     # unit -> micro-region index
    unit_labels: list[str] = field(default_factory=list)

    @property
    def n_units(self) -> int:
        return len(self.unit_uf)

    @property
    def n_entities(self) -> int:
        return len(self.entity_members)


def build_places(municipalities: list[int]) -> Places:
    """Units from IPEA's 2000–2010 comparable areas plus the post-2010 creations' parents."""
    import pegasus_data as pg

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    area: dict[int, str] = {}
    micro: dict[int, str] = {}
    for m in municipalities:
        ms = pg.memberships(str(m))
        a = ms.get("comparable_area_2000_2010")
        area[m] = f"amc:{a.member_code}" if a else f"new:{m}"
        mr = ms.get("ibge_microregion")
        micro[m] = mr.member_code if mr else f"uf:{str(m)[:2]}"
        find(area[m])
    touched: set[str] = set()
    for child, parents in POST_2010_CREATIONS.items():
        if child not in area:
            continue
        for p in parents:
            union(area[child], area[p])
        touched.add(area[child])
    root_of = {m: find(area[m]) for m in municipalities}
    roots = sorted(set(root_of.values()))
    unit_index = {r: i for i, r in enumerate(roots)}
    unit_of = {m: unit_index[root_of[m]] for m in municipalities}
    touched_units = {unit_index[find(t)] for t in touched}
    entity_members: list[list[int]] = []
    entity_of: dict[int, int] = {}
    entity_unit: list[int] = []
    by_unit: dict[int, list[int]] = defaultdict(list)
    for m in municipalities:
        by_unit[unit_of[m]].append(m)
    for u in sorted(by_unit):
        groups = [by_unit[u]] if u in touched_units else [[m] for m in by_unit[u]]
        for g in groups:
            for m in g:
                entity_of[m] = len(entity_members)
            entity_members.append(g)
            entity_unit.append(u)
    micros = sorted(set(micro.values()))
    micro_index = {m: i for i, m in enumerate(micros)}
    unit_micro = np.zeros(len(roots), dtype=int)
    unit_uf = np.zeros(len(roots), dtype=int)
    for m in municipalities:
        unit_micro[unit_of[m]] = micro_index[micro[m]]
        unit_uf[unit_of[m]] = int(str(m)[:2])
    return Places(municipalities, unit_of, entity_of, entity_members, np.array(entity_unit), unit_uf, unit_micro, roots)


# ------------------------------------------------------------------------------------------ inputs

def load_census(root: str | Path, year: int, places: Places, by: str = "unit") -> np.ndarray:
    """The census by (unit or entity) × sex × age 0..79,80+ — a gap (``None``) is not zero: a municipality
    without a value (created after the census) must lie inside a unit whose other members have one."""
    import pegasus_data as pg

    t = pg.load_population(series="CENSO", years=[year], by=("municipality", "year", "sex", "age"), root=root)
    n = places.n_units if by == "unit" else places.n_entities
    index = places.unit_of if by == "unit" else places.entity_of
    out = np.zeros((n, 2, A))
    seen = np.zeros(n, dtype=bool)
    for m, s, a, p in zip(t["municipality"].to_pylist(), t["sex"].to_pylist(), t["age"].to_pylist(),
                          t["population"].to_pylist(), strict=True):
        i = index.get(int(m))
        if i is None:
            continue
        if p is None:
            continue                      # a recorded gap: never counted as zero
        out[i, int(s) - 1, min(int(a), A - 1)] += p
        seen[i] = True
    if not seen.all() and by == "unit":
        raise ValueError(f"census {year}: {int((~seen).sum())} units have no value at all")
    return out


def collect_events(root: str | Path, years: range | list[int], events_dir: str | Path, log=print) -> None:
    """Deaths (residence × sex × age in years) and births (residence × sex) per year, through the public
    API into ``events_dir`` as parquet of raw codes; a year already collected is not fetched again."""
    import warnings

    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    import pegasus_data as pg

    out = Path(events_dir)
    out.mkdir(parents=True, exist_ok=True)
    for y in years:
        for name, dataset, event, by in (("deaths", "SIM.DO", "death", ["CODMUNRES", "SEXO", "IDADE_anos"]),
                                         ("births", "SINASC-DN", "birth", ["CODMUNRES", "SEXO"])):
            f = out / f"{name}_{y}.parquet"
            if f.exists():
                continue
            t0 = time.time()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tab = pg.count_events(dataset, event, period=y, geography="BR", by=by, root=root,
                                      allow_partial=False, max_download=8 * 1024**3)
            tab = pa.table({c: pc.cast(tab[c], pa.string()) for c in by} | {"events": tab["events"]})
            pq.write_table(tab, f)
            log(f"{name} {y}: {tab.num_rows} rows, {pc.sum(tab['events']).as_py()} events, {time.time() - t0:.0f}s")


def _place(codes: list[str | None], keys: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Index of each residence code's first six digits among the sorted municipality ``keys`` (-1: not a current municipality)."""
    c6 = np.array([int(c[:6]) if c and c[:6].isdigit() else -1 for c in codes])
    pos = np.clip(np.searchsorted(keys, c6), 0, len(keys) - 1)
    return np.where(keys[pos] == c6, targets[pos], -1)


def load_events(events_dir: str | Path, years: list[int], places: Places, by: str = "unit") -> dict[str, Any]:
    """Deaths ``[Y, n, 2, A]`` and births ``[Y, n, 2]`` per year, with what could not be placed counted, not dropped.

    Deaths of unknown sex or age are spread over the known cells of the same unit and year, in proportion
    (the totals are kept; the allocation is a documented choice); an event whose residence is not a current
    municipality is reported as unplaced."""
    import pyarrow.parquet as pq

    n = places.n_units if by == "unit" else places.n_entities
    index = places.unit_of if by == "unit" else places.entity_of
    order = sorted(index, key=lambda m: int(str(m)[:6]))
    keys = np.array([int(str(m)[:6]) for m in order])
    targets = np.array([index[m] for m in order])
    sex_code = {"1": 0, "M": 0, "2": 1, "F": 1}
    deaths = np.zeros((len(years), n, 2, A))
    births = np.zeros((len(years), n, 2))
    report: dict[str, dict[str, int]] = {}
    for k, y in enumerate(years):
        t = pq.read_table(Path(events_dir) / f"deaths_{y}.parquet")
        i = _place(t["CODMUNRES"].to_pylist(), keys, targets)
        sx = np.array([sex_code.get((s or "").strip().upper(), -1) for s in t["SEXO"].to_pylist()])
        ag = np.array([-1.0 if a is None else float(a) for a in t["IDADE_anos"].to_pylist()])
        age = np.where(ag >= 0, np.minimum(np.floor(ag), A - 1), -1).astype(int)
        e = np.array(t["events"].to_pylist(), dtype=float)
        placed = i >= 0
        rep = {"deaths_total": int(e.sum()), "deaths_unplaced": int(e[~placed].sum()),
               "deaths_sex_unknown": int(e[placed & (sx < 0)].sum()), "deaths_age_unknown": int(e[placed & (age < 0)].sum())}
        full = placed & (sx >= 0) & (age >= 0)
        np.add.at(deaths[k], (i[full], sx[full], age[full]), e[full])
        known = deaths[k].copy()
        m = placed & (sx >= 0) & (age < 0)                 # unknown age: over that sex's ages in the unit
        unk = np.zeros((n, 2))
        np.add.at(unk, (i[m], sx[m]), e[m])
        for s in range(2):
            tot = known[:, s].sum(1)
            share = np.divide(known[:, s], tot[:, None], out=np.full((n, A), 1 / A), where=tot[:, None] > 0)
            deaths[k, :, s] += unk[:, s, None] * share
        m = placed & (sx < 0) & (age >= 0)                  # unknown sex: over the sexes at that age
        unk = np.zeros((n, A))
        np.add.at(unk, (i[m], age[m]), e[m])
        tot = known.sum(1)
        for s in range(2):
            share = np.divide(known[:, s], tot, out=np.full((n, A), 0.5), where=tot > 0)
            deaths[k, :, s] += unk * share
        m = placed & (sx < 0) & (age < 0)                   # unknown both: over the unit's cells
        unk = np.zeros(n)
        np.add.at(unk, i[m], e[m])
        tot = known.sum((1, 2))
        share = np.divide(known, tot[:, None, None], out=np.full((n, 2, A), 1 / (2 * A)), where=tot[:, None, None] > 0)
        deaths[k] += unk[:, None, None] * share
        t = pq.read_table(Path(events_dir) / f"births_{y}.parquet")
        i = _place(t["CODMUNRES"].to_pylist(), keys, targets)
        sx = np.array([sex_code.get((s or "").strip().upper(), -1) for s in t["SEXO"].to_pylist()])
        e = np.array(t["events"].to_pylist(), dtype=float)
        placed = i >= 0
        rep |= {"births_total": int(e.sum()), "births_unplaced": int(e[~placed].sum()),
                "births_sex_unknown": int(e[placed & (sx < 0)].sum())}
        np.add.at(births[k], (i[placed & (sx >= 0)], sx[placed & (sx >= 0)]), e[placed & (sx >= 0)])
        known = births[k].copy()
        unk = np.zeros(n)
        m = placed & (sx < 0)
        np.add.at(unk, i[m], e[m])
        tot = known.sum(1)
        births[k] += unk[:, None] * np.divide(known, tot[:, None], out=np.full((n, 2), 0.5), where=tot[:, None] > 0)
        report[str(y)] = rep
    return {"deaths": deaths, "births": births, "report": report, "years": years}


# ------------------------------------------------------------------------------- the account itself

def step_terms(N: np.ndarray, D: np.ndarray, B: np.ndarray):
    """One step's pieces. ``dr`` is each starting age's share of the step's deaths (Lexis), ``dr0`` the newborns'."""
    dr = np.zeros_like(N)
    dr[..., :A - 2] = 0.5 * (D[..., :A - 2] + D[..., 1:A - 1])
    dr[..., A - 2] = 0.5 * D[..., A - 2]
    dr[..., A - 1] = D[..., A - 1]
    return dr, 0.5 * D[..., 0]


def advance(N, D, B, mig=None):
    """One step: ``N`` at the start (…, A) to the end; ``mig`` is the annual net migration rate by starting age."""
    dr, dr0 = step_terms(N, D, B)
    surv = N - dr
    if mig is not None:
        surv = surv + N * mig
    nxt = np.zeros_like(N)
    nxt[..., 1:A] = surv[..., 0:A - 1]
    nxt[..., A - 1] += surv[..., A - 1]
    nxt[..., 0] = B - dr0
    return nxt


def step_events(deaths, births, k, weights=(W_FIRST, W_SECOND)):
    return weights[0] * deaths[k] + weights[1] * deaths[k + 1], weights[0] * births[k] + weights[1] * births[k + 1]


def run_account(N0, deaths, births, steps, mig=None, kappa=None, lam=None, keep_path=False):
    """Project from the starting census through ``steps`` steps.

    ``mig`` is the annual net migration rate by starting age, (n,2,A), or a callable (k, N) -> rates;
    ``kappa`` (steps,n,2) and ``lam`` (n,2) are the shares of births and of deaths the systems did not register."""
    N = N0.copy()
    path = [N]
    for k in range(steps):
        D, B = step_events(deaths, births, k)
        if lam is not None:
            D = D * (1 + lam)[:, :, None]
        if kappa is not None:
            B = B * (1 + kappa[k])
        m = mig(k, N) if callable(mig) else mig
        N = advance(N, D, B, m)
        path.append(N)
    return (N, path) if keep_path else N


def basis(knots: tuple[float, ...] = (0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90)) -> np.ndarray:
    """Cubic B-spline basis of the migration age profile, evaluated at the age-in-step midpoints (a+0.5; the open
    class at 85). Returns (A, J)."""
    from scipy.interpolate import BSpline

    k = 3
    inner = list(knots)
    t = np.r_[[inner[0]] * k, inner, [inner[-1]] * k]
    J = len(t) - k - 1
    ages = np.r_[np.arange(A - 1) + 0.5, 85.0]
    out = np.zeros((A, J))
    for j in range(J):
        c = np.zeros(J)
        c[j] = 1
        out[:, j] = BSpline(t, c, k, extrapolate=False)(np.clip(ages, inner[0], inner[-1] - 1e-9))
    return np.nan_to_num(out)


def responses(path, deaths, births, steps, phi, kappa_split: int | None = None,
              weights=(W_FIRST, W_SECOND)) -> np.ndarray:
    """The linear response of the closing cohorts to each parameter, along a given path: shape (n, 2, P, A) where
    P = J migration coefficients, then κ₁ and κ₂ (births not registered in the first and second part of the period,
    so completeness may improve within it).

    Migration at rate φ_j(age) adds ``N_k(a) φ_j`` to the cohort and the cohort then ages and survives like the
    population; κ adds that step's births."""
    J = phi.shape[1]
    n = path[0].shape[0]
    split = steps // 2 if kappa_split is None else kappa_split
    delta = np.zeros((n, 2, J + 2, A))
    for k in range(steps):
        N = path[k]
        D, B = step_events(deaths, births, k, weights)
        dr, dr0 = step_terms(N, D, B)
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(N > 0, 1 - dr / np.maximum(N, 1e-9), 1.0)
        s = np.clip(s, 0.0, 1.0)
        moved = delta * s[:, :, None, :]
        nxt = np.zeros_like(delta)
        nxt[..., 1:A] = moved[..., 0:A - 1]
        nxt[..., A - 1] += moved[..., A - 1]
        src = N[:, :, None, :] * phi.T[None, None, :, :]            # (n,2,J,A) migrants by starting age
        nxt[:, :, :J, 1:A] += src[..., 0:A - 1]
        nxt[:, :, :J, A - 1] += src[..., A - 1]
        nxt[:, :, J + (0 if k < split else 1), 0] += B               # κ
        delta = nxt
    return delta


# ------------------------------------------------------------------------------ the fit (hierarchy)

@dataclass
class Fit:
    """Posterior draws of the parameters: ``mu`` (S,P), ``a`` (S,F,P), ``b`` (S,M,P), ``d`` (S,U,P), and the
    variances of the three effects (S,3,P). P = 2J + 2: the migration coefficients of men then women, then the
    births shortfalls κ₁, κ₂ (first and second part of the period), shared by the sexes."""

    mu: np.ndarray
    a: np.ndarray
    b: np.ndarray
    d: np.ndarray
    var: np.ndarray
    uf_of: np.ndarray
    micro_of: np.ndarray

    def beta(self, rho: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0), draws: slice | np.ndarray = slice(None),
             n_migration: int | None = None, rng: np.random.Generator | None = None) -> np.ndarray:
        """Unit parameters (S,U,P). ``rho`` = (national mean of the migration coefficients, state, micro-region,
        municipal deviations) carried into another period: 1 = persists as estimated, 0 = gone. The births
        shortfalls (the last two coefficients) keep their estimate; the forecast lets a positive one close.

        With ``rng`` the next period's parameters are *drawn*: what persists is ρ times the estimate, and the rest
        is new, with the variance the fit estimated for that level (so a deviation that does not persist
        is not predicted as zero but as unknown). The national mean's new part is scaled by the size of its own
        estimate, the only scale the fit offers."""
        mu, a, b, d = self.mu[draws].copy(), self.a[draws], self.b[draws], self.d[draws]
        var = self.var[draws]
        if n_migration is not None:
            mu[:, :n_migration] *= rho[0]
        if rng is None:
            return mu[:, None, :] + rho[1] * a[:, self.uf_of, :] + rho[2] * b[:, self.micro_of, :] + rho[3] * d
        S = mu.shape[0]
        P = mu.shape[1]
        new = lambda r: np.sqrt(max(1.0 - r * r, 0.0))               # noqa: E731
        if n_migration is not None:
            mu[:, :n_migration] += new(rho[0]) * np.abs(self.mu[draws][:, :n_migration]) * rng.standard_normal((S, n_migration))
        ua = np.unique(self.uf_of).size
        ub = np.unique(self.micro_of).size
        a = rho[1] * a + new(rho[1]) * np.sqrt(var[:, 0, None, :]) * rng.standard_normal((S, ua, P))
        b = rho[2] * b + new(rho[2]) * np.sqrt(var[:, 1, None, :]) * rng.standard_normal((S, ub, P))
        d = rho[3] * d + new(rho[3]) * np.sqrt(var[:, 2, None, :]) * rng.standard_normal(d.shape)
        return mu[:, None, :] + a[:, self.uf_of, :] + b[:, self.micro_of, :] + d


def weights_for(cohort: np.ndarray, s1: float, s2: float) -> np.ndarray:
    """Inverse variance of a closing cohort's residual: Poisson-like ``s1·N`` plus a coverage/reporting term ``s2·N²``."""
    return 1.0 / (s1 * np.maximum(cohort, 1.0) + s2 * cohort**2)


def sufficient(X: np.ndarray, y: np.ndarray, W: np.ndarray):
    """Per unit: X'WX (U,P,P), X'Wy (U,P), y'Wy (U,). ``X`` is (U,P,A), ``y`` and ``W`` (U,A)."""
    XW = X * W[:, None, :]
    return np.einsum("upa,uqa->upq", XW, X), np.einsum("upa,ua->up", XW, y), np.einsum("ua,ua->u", W * y, y)


def _seg_sum(values: np.ndarray, index: np.ndarray, n: int) -> np.ndarray:
    out = np.zeros((n,) + values.shape[1:])
    np.add.at(out, index, values)
    return out


def fit_hierarchy(XtWX: np.ndarray, XtWy: np.ndarray, uf_of: np.ndarray, micro_of: np.ndarray, *,
                  sweeps: int = 600, burn: int = 200, thin: int = 4, seed: int = 0,
                  prior_shape: float = 1.0, prior_scale: float = 1e-9,
                  mu_prior: tuple[np.ndarray, np.ndarray] | None = None,
                  fixed_var: np.ndarray | None = None, log=print) -> Fit:
    """Gibbs sampling of ``β_u = μ + a_uf + b_micro + d_u`` (all Gaussian, diagonal variances) given each unit's
    sufficient statistics. Exact conditionals, no approximation beyond the Gaussian likelihood.

    ``mu_prior`` = (mean, precision matrix) of the national mean: flat when absent. A death-shaped column (the shortfall λ) and a
    smooth migration profile at the oldest ages are nearly collinear, and the data alone put the national
    mean wherever they cancel; the prior is what keeps each where it can be. ``fixed_var`` (3, P) holds the
    variance of the state / micro-region / municipal effects of a coefficient constant where it is not NaN (the
    data cannot estimate the spread of a coefficient they barely identify)."""
    rng = np.random.default_rng(seed)
    U, P, _ = XtWX.shape
    uf_ids, uf_idx = np.unique(uf_of, return_inverse=True)
    mi_ids, mi_idx = np.unique(micro_of, return_inverse=True)
    F, M = len(uf_ids), len(mi_ids)
    ridge = 1e-12 * np.maximum(np.einsum("upp->up", XtWX).mean(0), 1e-30)
    mu = np.zeros(P)
    a = np.zeros((F, P))
    b = np.zeros((M, P))
    d = np.zeros((U, P))
    lv = np.tile(np.array([1e-4, 1e-4, 1e-4])[:, None], (1, P))     # variances of a, b, d
    if fixed_var is not None:
        lv = np.where(np.isnan(fixed_var), lv, fixed_var)
    keep: dict[str, list[np.ndarray]] = {k: [] for k in ("mu", "a", "b", "d", "var")}
    S_all = XtWX.sum(0)

    def draw(prec: np.ndarray, rhs: np.ndarray) -> np.ndarray:
        L = np.linalg.cholesky(prec)
        mean = np.linalg.solve(prec, rhs[..., None])[..., 0]
        z = rng.standard_normal(rhs.shape)
        return mean + np.linalg.solve(np.swapaxes(L, -1, -2), z[..., None])[..., 0]

    t0 = time.time()
    for it in range(sweeps):
        # municipal effects
        prior_mean = mu + a[uf_idx] + b[mi_idx]
        prec = XtWX + np.diag(1 / lv[2] + ridge)[None]
        rhs = XtWy - np.einsum("upq,uq->up", XtWX, prior_mean)
        d = draw(prec, rhs)
        # micro-region effects
        resid = XtWy - np.einsum("upq,uq->up", XtWX, mu + a[uf_idx] + d)
        Sm = _seg_sum(XtWX, mi_idx, M)
        prec = Sm + np.diag(1 / lv[1] + ridge)[None]
        b = draw(prec, _seg_sum(resid, mi_idx, M))
        # state effects
        resid = XtWy - np.einsum("upq,uq->up", XtWX, mu + b[mi_idx] + d)
        Sf = _seg_sum(XtWX, uf_idx, F)
        prec = Sf + np.diag(1 / lv[0] + ridge)[None]
        a = draw(prec, _seg_sum(resid, uf_idx, F))
        # national mean (flat prior)
        resid = XtWy - np.einsum("upq,uq->up", XtWX, a[uf_idx] + b[mi_idx] + d)
        if mu_prior is None:
            mu = draw(S_all + np.diag(ridge), resid.sum(0))
        else:
            pm, Q = mu_prior
            mu = draw(S_all + np.diag(ridge) + Q, resid.sum(0) + Q @ pm)
        # variances
        for lvl, x in enumerate((a, b, d)):
            n = x.shape[0]
            new = (prior_scale + 0.5 * (x**2).sum(0)) / rng.gamma(prior_shape + n / 2, size=P)
            lv[lvl] = new if fixed_var is None else np.where(np.isnan(fixed_var[lvl]), new, fixed_var[lvl])
        if it >= burn and (it - burn) % thin == 0:
            for k, v in (("mu", mu), ("a", a), ("b", b), ("d", d), ("var", lv)):
                keep[k].append(v.copy())
        if it % 100 == 0:
            log(f"  gibbs {it}/{sweeps} ({time.time() - t0:.0f}s)")
    return Fit(np.array(keep["mu"]), np.array(keep["a"]), np.array(keep["b"]), np.array(keep["d"]),
               np.array(keep["var"]), uf_idx, mi_idx)


# ----------------------------------------------------------------------------------- training period

@dataclass
class Trained:
    """What training on one intercensal period leaves: the fit, the migration basis, the noise model."""

    fit: Fit
    phi: np.ndarray
    s1: float
    s2: float
    steps: int
    kappa_split: int
    diagnostics: dict[str, Any] = field(default_factory=dict)
    tau: float = 0.0                # unit-level coverage error shared by all of a unit's cells (relative)


def split_params(beta: np.ndarray, J: int):
    """Unit parameters (…, 2J+2) -> migration coefficients (…, 2, J), κ₁, κ₂ (each (…,))."""
    theta = np.stack([beta[..., :J], beta[..., J:2 * J]], axis=-2)
    return theta, beta[..., 2 * J], beta[..., 2 * J + 1]


def _noise_from_residuals(e: np.ndarray, cohort: np.ndarray) -> tuple[float, float]:
    """Moment estimate of ``var = s1·N + s2·N²`` from residuals (cells grouped in log-size bins)."""
    x, r2 = cohort.ravel(), (e**2).ravel()
    edges = np.unique(np.quantile(x[x > 0], np.linspace(0, 1, 41)))
    idx = np.clip(np.digitize(x, edges) - 1, 0, len(edges) - 2)
    cnt = np.bincount(idx, minlength=len(edges) - 1).astype(float)
    ok = cnt > 50
    mx = np.bincount(idx, x, len(edges) - 1)[ok] / cnt[ok]
    mv = np.bincount(idx, r2, len(edges) - 1)[ok] / cnt[ok]
    from scipy.optimize import nnls

    design = np.c_[mx, mx**2] / mv[:, None]                    # relative errors, so small cells are not ignored
    (s1, s2), _ = nnls(design, np.ones_like(mv))
    return float(s1), float(s2)


def _forward_with(params: np.ndarray, c0, deaths, births, steps, phi, split, lam0=DEATH_SHORTFALL, keep_path=True):
    """The nonlinear account at given unit parameters (U, 2J+2) — used to re-expand the response around the fit."""
    J = phi.shape[1]
    theta, k1, k2 = split_params(params, J)
    lam = np.full(len(k1), lam0)
    mig = np.einsum("aj,usj->usa", phi, theta)
    kap = np.zeros((steps,) + c0.shape[:1] + (2,))
    for k in range(steps):
        kap[k] = (k1 if k < split else k2)[:, None]
    return run_account(c0, deaths, births, steps, mig=mig, kappa=kap, lam=np.repeat(lam[:, None], 2, axis=1),
                       keep_path=keep_path)


def default_priors(phi: np.ndarray, kappa_sd: float = 0.10, young_sd: float = 0.05, old_sd: float = 0.01,
                   old_from: float = 60.0, smooth_sd: float = 0.03, unidentified_from: float = 75.0):
    """Priors of the national mean and the fixed spreads of the oldest coefficients.

    Net migration is a rate near zero (loose below ``old_from``, tight above, where migration is small), and its
    age profile is smooth: neighbouring coefficients differ by about ``smooth_sd`` (a first-difference penalty;
    without it the youngest coefficients ring, +0.04 then -0.04, against the births shortfall). The births
    shortfalls are learned from the data, loosely centred on zero. The oldest coefficients (peaking at
    ``unidentified_from`` or later, where cells are few) have effect spreads the data cannot estimate: those are
    held fixed (state / micro-region / municipality: 0.01, 0.005, 0.005)."""
    J = phi.shape[1]
    peak = np.arange(A)[np.argmax(phi, axis=0)]
    mig_sd = np.where(peak >= old_from, old_sd, young_sd)
    P = 2 * J + 2
    Q = np.zeros((P, P))
    Q[np.arange(2 * J), np.arange(2 * J)] = np.r_[1 / mig_sd**2, 1 / mig_sd**2]
    Q[2 * J:, 2 * J:] = np.eye(2) / kappa_sd**2
    for sx in range(2):
        for j in range(J - 1):
            i0, i1 = sx * J + j, sx * J + j + 1
            Q[i0, i0] += 1 / smooth_sd**2
            Q[i1, i1] += 1 / smooth_sd**2
            Q[i0, i1] -= 1 / smooth_sd**2
            Q[i1, i0] -= 1 / smooth_sd**2
    fixed = np.full((3, P), np.nan)
    old = np.r_[peak >= unidentified_from, peak >= unidentified_from, [False, False]]
    for lvl, v in enumerate((0.01, 0.005, 0.005)):
        fixed[lvl, old] = v**2
    return (np.zeros(P), Q), fixed


def train(c0: np.ndarray, c1: np.ndarray, deaths: np.ndarray, births: np.ndarray, places: Places, *,
          steps: int = 10, passes: int = 2, noise: tuple[float, float] = (2.0, 4e-4), sweeps: int = 800,
          burn: int = 200, thin: int = 4, seed: int = 0, log=print) -> Trained:
    """Fit the account to one intercensal period: ``c0``→``c1`` (units × 2 × A) with the period's events
    (``steps``+1 years). Each pass expands the account's response around the previous pass's fit (the account is
    only nearly linear in its parameters), then samples the hierarchy; the noise model is re-estimated from the
    residuals between passes. Both sexes are fitted together so the shortfalls are shared."""
    phi = basis()
    J = phi.shape[1]
    P = 2 * J + 2
    split = steps // 2
    s1, s2 = noise
    U = c0.shape[0]
    params = np.zeros((U, P))
    prior, fixed = default_priors(phi)
    fit = None
    for p in range(passes):
        N_end, path = _forward_with(params, c0, deaths, births, steps, phi, split)
        X = responses(path, deaths * (1 + DEATH_SHORTFALL), births, steps, phi, split)   # (U,2,J+2,A)
        Xj = np.zeros((U, P, 2 * A))
        for sx in range(2):
            Xj[:, sx * J:(sx + 1) * J, sx * A:(sx + 1) * A] = X[:, sx, :J]
            Xj[:, 2 * J:, sx * A:(sx + 1) * A] = X[:, sx, J:]
        lin = np.einsum("upa,up->ua", Xj, params)                               # response at the previous fit
        y = (c1 - N_end).reshape(U, 2 * A) + lin                                # linearised around it
        cohort = np.maximum((c1 + N_end) / 2, 0)
        if p > 0:
            s1, s2 = _noise_from_residuals(c1 - N_end, cohort)
            log(f"pass {p}: noise s1={s1:.3f} s2={s2:.2e}")
        W = weights_for(cohort, s1, s2).reshape(U, 2 * A)
        XtWX, XtWy, _ = sufficient(Xj, y, W)
        log(f"pass {p}: sampling")
        fit = fit_hierarchy(XtWX, XtWy, places.unit_uf, places.unit_micro, sweeps=sweeps, burn=burn, thin=thin,
                            seed=seed + 13 * p, mu_prior=prior, fixed_var=fixed, log=log)
        params = fit.beta().mean(0)
    N_end, _ = _forward_with(params, c0, deaths, births, steps, phi, split)
    cohort = np.maximum((c1 + N_end) / 2, 0)
    s1, s2 = _noise_from_residuals(c1 - N_end, cohort)
    # the coverage error shared by a unit's cells: what the unit totals' residual adds to the cells' own noise
    tot = (c1 - N_end).sum((1, 2))
    expect = (s1 * np.maximum(cohort, 1) + s2 * cohort**2).sum((1, 2))
    big = cohort.sum((1, 2)) > 20_000
    tau2 = max(float(np.mean((tot[big] ** 2 - expect[big]) / cohort.sum((1, 2))[big] ** 2)), 0.0)
    return Trained(fit, phi, s1, s2, steps, split, {"lam0": DEATH_SHORTFALL, "noise_final": (s1, s2), "tau": float(np.sqrt(tau2)),
                                                    "fit_total_error": float((N_end - c1).sum())}, float(np.sqrt(tau2)))


# ---------------------------------------------------------------------------------------- the forecast

def completeness_decay(mu_kappa: np.ndarray, mode: str) -> np.ndarray:
    """Per draw, the factor by which the registration shortfall shrinks every five years after the training
    period (r in [0,1]): the ratio of the national second-half to first-half births shortfall (κ₂/κ₁).
    ``mode``: ``decay`` (that ratio), ``none`` (the shortfall closes at once: r=0), ``carry`` (it stays: r=1);
    ``same`` (used by ``forecast`` for the period the parameters were fitted on) leaves the shortfalls as fitted."""
    if mode in ("same", "carry"):
        return np.ones(len(mu_kappa))
    if mode == "none":
        return np.zeros(len(mu_kappa))
    k1, k2 = mu_kappa[:, 0], mu_kappa[:, 1]
    return np.clip(np.divide(k2, k1, out=np.zeros_like(k1), where=k1 > 1e-6), 0.0, 1.0)


def forecast(trained: Trained, c_start: np.ndarray, deaths: np.ndarray, births: np.ndarray, steps: int,
             entity_unit: np.ndarray, *, rho=(1.0, 1.0, 1.0, 1.0), completeness: str = "decay", chunk: int = 400,
             draws: int | None = None, seed: int = 0, noise: bool = True, innovation: bool = True,
             log=print) -> dict[str, np.ndarray]:
    """Project the next period from its opening census, one draw of the parameters at a time.

    ``c_start`` is (E,2,A) at the entities; an entity takes its unit's parameters. ``rho`` = (national mean of the
    migration profile, state, micro-region, municipal deviations) is how much of what was estimated persists.
    Returns, per step, the draws of each entity's 5-year-band populations and their total (with the observation
    noise of a census added if ``noise``)."""
    J = trained.phi.shape[1]
    E = c_start.shape[0]
    f = trained.fit
    S = len(f.mu) if draws is None else min(draws, len(f.mu))
    rng = np.random.default_rng(seed)
    beta = f.beta(rho, slice(0, S), 2 * J, rng if innovation else None)             # (S,U,P)
    r = completeness_decay(f.mu[:S, 2 * J:2 * J + 2], completeness)              # (S,)
    lam0 = trained.diagnostics.get("lam0", DEATH_SHORTFALL)
    bands = np.minimum(np.arange(A) // 5, 16)
    out_total = np.zeros((steps + 1, S, E))
    out_bands = np.zeros((steps + 1, S, E, 2, 17))
    for lo in range(0, E, chunk):
        sl = slice(lo, min(E, lo + chunk))
        n = sl.stop - sl.start
        theta, k1, k2 = split_params(beta[:, entity_unit[sl]], J)                 # (S,n,2,J), (S,n), (S,n)
        mig = np.einsum("aj,snxj->snxa", trained.phi, theta)
        N = np.broadcast_to(c_start[sl], (S, n, 2, A)).copy()

        def record(k_out, N, sl=sl, n=n):
            if noise:                                  # what a census of this population would have counted
                tau = rng.standard_normal((S, n, 1, 1)) * trained.tau
                N = np.maximum(N * (1 + tau) + rng.standard_normal(N.shape) * np.sqrt(
                    trained.s1 * np.maximum(N, 1) + trained.s2 * N**2), 0)
            out_total[k_out, :, sl] = N.sum((2, 3))
            for g in range(17):
                out_bands[k_out, :, sl, :, g] = N[..., bands == g].sum(-1)

        record(0, N)
        for k in range(steps):
            D, B = step_events(deaths[:, sl], births[:, sl], k)
            T = trained.steps                          # the shortfalls were measured at 3/4 and 1/2 of the training period
            closing = r[:, None] ** ((T + 0.5 + k - 0.75 * T) / 5)
            # a births shortfall closes as registration improves; a surplus (more births registered than the census
            # found children) cannot be unregistered births: it is the census's coverage of children, and stays
            kap = np.where(k2 > 0, k2 * closing, k2)
            lam = lam0 * r[:, None] ** ((T + 0.5 + k - 0.5 * T) / 5)               # deaths shortfall, closing
            if completeness == "same":                    # the period the parameters were fitted on: as fitted
                kap, lam = (k1 if k < trained.kappa_split else k2), np.full_like(r[:, None], lam0)
            N = advance(N, D * (1 + lam)[..., None, None], B * (1 + kap)[..., None], mig)
            N = np.maximum(N, 0)
            record(k + 1, N)
        log(f"  forecast entities {sl.stop}/{E}")
    return {"total": out_total, "bands": out_bands}


# ------------------------------------------------------------------------------------------ coverage

BANDS = np.minimum(np.arange(A) // 5, 16)
BAND_LABELS = [f"{5 * g}-{5 * g + 4}" for g in range(16)] + ["80+"]


def to_bands(x: np.ndarray) -> np.ndarray:
    """(…, A) single ages to (…, 17) five-year bands (the last open at 80)."""
    return np.stack([x[..., g == BANDS].sum(-1) for g in range(17)], axis=-1)


def reconciled_coverage(population_root: str | Path, year: int, census: np.ndarray, state_of: np.ndarray) -> np.ndarray:
    """Coverage factors of a census as IBGE's reconciliation implies them: POPSVS / raw count, by state × sex × band,
    expanded to single ages (n, 2, A) for units whose state is ``state_of``. The reconciliation was made with the 2022
    PES, so an account that uses these for 2000 and 2010 is a *sensitivity*, not a hold-out; and POPSVS is modelled,
    not observed."""
    import pegasus_data as pg

    t = pg.load_population(series="POPSVS", years=[year], by=("municipality", "year", "sex", "age"), root=population_root)
    states = sorted(set(int(u) for u in state_of))
    index = {u: i for i, u in enumerate(states)}
    svs = np.zeros((len(states), 2, 17))
    for m, s, a, n in zip(t["municipality"].to_pylist(), t["sex"].to_pylist(), t["age"].to_pylist(),
                          t["population"].to_pylist(), strict=True):
        svs[index[int(str(m)[:2])], int(s) - 1, BANDS[min(int(a), A - 1)]] += n
    raw = np.zeros_like(svs)
    cb = to_bands(census)
    for i, u in enumerate(state_of):
        raw[index[int(u)]] += cb[i]
    g = svs / raw
    return g[[index[int(u)] for u in state_of]][:, :, BANDS]


def pes_coverage(raw_entity: np.ndarray, entity_state: np.ndarray) -> np.ndarray:
    """Coverage factors (corrected / raw) of the 2022 Census by entity × sex × age, from IBGE's PES margins raked onto
    cells (``sources.pes.corrected_census``), applied to the single ages of each band in proportion."""
    from .sources.pes import corrected_census

    rb = to_bands(raw_entity)
    corrected = corrected_census(rb, entity_state)
    return (corrected / np.maximum(rb, 1e-9))[:, :, BANDS]


# ---------------------------------------------------------------------------------------- the product

#: How much of what was estimated in one period carries into the next: (national mean profile, state, micro-region,
#: municipality). Fixed before the 2022 hold-out was scored, from how net-migration deviations of ages 25-54 in
#: 1991-2000 predicted those of 2000-2010 (SIDRA table 200; slopes 0.69 for states, 0.43 for micro-regions, 0.15-0.29 for
#: municipalities, the latter attenuated by sampling noise); the national mean carries nothing, because internal
#: migration sums to zero and what is left nationally (international migration, a change in census coverage) is not
#: a regularity of places.
PERSISTENCE = (0.0, 0.7, 0.45, 0.3)


def _quantiles(draws: np.ndarray, level: float = 0.8):
    """Mean and central interval over the draws axis of a (T+1, S, E, 2, 17) path."""
    lo, hi = np.percentile(draws, [50 * (1 - level), 50 * (1 + level)], axis=1)
    return draws.mean(1), lo, hi


def _bridge(path: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Close a projected path (T+1, S, E, 2, 17) onto the census that ends it: the mean path is moved by the
    share of the gap that has elapsed, and the spread of the draws narrows to nothing at the census."""
    T = path.shape[0] - 1
    mean = path.mean(1, keepdims=True)
    k = (np.arange(T + 1) / T).reshape(-1, 1, 1, 1, 1)
    out = mean + k * (target[None, None] - mean[-1:]) + (1 - k) * (path - mean)
    return np.maximum(out, 0)


def build_account(root: str | Path, population_root: str | Path, events_dir: str | Path, *, version: str,
                  validation: str, sweeps: int = 800, draws: int = 100, seed: int = 0, log=print) -> dict[str, Any]:
    """Fit the two intercensal periods and extend one year, then write the ``population_account`` and
    ``registration_completeness`` modelled products.

    The censuses are brought to the true population before anything is fitted: 2022 by IBGE's PES (published
    margins, raked onto cells), 2000 and 2010 by IBGE's own reconciliation (POPSVS / raw), the latter two being a
    sensitivity assumption (the reconciliation used the 2022 PES). Net migration is therefore learned net of
    coverage. Rows: municipalities (or, inside a unit touched by a post-2010 creation, the group of them) 2010-2023,
    and comparable areas 2000-2010; ages in five-year bands; the point estimate is the mean of the draws and the
    interval their 10th-90th percentiles."""
    from types import SimpleNamespace

    import pyarrow as pa
    import pyarrow.parquet as pq

    from .modelled import ModelledManifest, write_modelled

    t22 = pq.read_table(Path(root) / "lake" / "population" / "CENSO" / "censo_2022.parquet", columns=["municipality"])
    places = build_places(sorted(set(int(m) for m in t22["municipality"].to_pylist())))
    lake_root = str(root)
    c00u = load_census(lake_root, 2000, places)
    c10u = load_census(lake_root, 2010, places)
    c10e = load_census(lake_root, 2010, places, "entity")
    c22e = load_census(lake_root, 2022, places, "entity")
    ent_state = np.array([int(str(m[0])[:2]) for m in places.entity_members])
    log("coverage")
    g00 = reconciled_coverage(population_root, 2000, c00u, places.unit_uf)
    g10u = reconciled_coverage(population_root, 2010, c10u, places.unit_uf)
    g10e = reconciled_coverage(population_root, 2010, c10e, ent_state)
    g22e = pes_coverage(c22e, ent_state)
    c22e_true = c22e * g22e
    c22u_true = np.zeros_like(c10u)
    np.add.at(c22u_true, places.entity_unit, c22e_true)
    truth22_b = to_bands(c22e_true)
    ev0 = load_events(events_dir, list(range(2000, 2011)), places, "unit")
    ev1u = load_events(events_dir, list(range(2010, 2023)), places, "unit")
    ev1e = load_events(events_dir, list(range(2010, 2023)), places, "entity")
    ev2e = load_events(events_dir, [2022, 2023], places, "entity")
    tables: list[dict[str, Any]] = []
    completeness: list[dict[str, Any]] = []

    def rows(path_b, kind, place_of, years, period, basis):
        mean, lo, hi = _quantiles(path_b)
        for k, y in enumerate(years):
            for e in range(path_b.shape[2]):
                for s in range(2):
                    for g in range(17):
                        tables.append({"place": place_of(e), "place_kind": kind, "year": y, "sex": s + 1,
                                       "age_band": BAND_LABELS[g], "population": float(mean[k, e, s, g]),
                                       "population_lo": float(lo[k, e, s, g]), "population_hi": float(hi[k, e, s, g]),
                                       "period": period, "basis": basis})

    def births_completeness(fit: Trained, period: str, years):
        J = fit.phi.shape[1]
        beta = fit.fit.beta(draws=slice(0, draws))
        half = len(years) // 2
        for h, (y0, y1) in enumerate(((years[0], years[half - 1]), (years[half], years[-1]))):
            kap = beta[:, :, 2 * J + h]                                  # (S,U)
            for uf in sorted(set(int(u) for u in places.unit_uf)):
                sel = places.unit_uf == uf
                w = c10u.sum((1, 2))[sel]
                est = 1 / (1 + (kap[:, sel] * w).sum(1) / w.sum())
                completeness.append({"uf": uf, "system": "SINASC", "period": f"{y0}-{y1}", "census_basis": period,
                                     "completeness": float(est.mean()), "completeness_lo": float(np.percentile(est, 10)),
                                     "completeness_hi": float(np.percentile(est, 90))})

    log("period A: 2000-2010 (comparable areas)")
    a = train(c00u * g00, c10u * g10u, ev0["deaths"], ev0["births"], places, steps=10, sweeps=sweeps, burn=sweeps // 4,
              thin=max(1, (sweeps - sweeps // 4) // 150), seed=seed, log=log)
    pa_ = forecast(a, c00u * g00, ev0["deaths"], ev0["births"], 10, np.arange(places.n_units), rho=(1, 1, 1, 1),
                   draws=draws, noise=False, innovation=False, completeness="same", log=log)["bands"]
    pa_ = _bridge(pa_, to_bands(c10u * g10u))
    rows(pa_, "comparable_area", lambda e: places.unit_labels[e], range(2000, 2011), "2000-2010", "intercensal")
    births_completeness(a, "reconciled 2000 and 2010", range(2000, 2010))
    log("period B: 2010-2022 (municipalities)")
    b = train(c10u * g10u, c22u_true, ev1u["deaths"], ev1u["births"], places, steps=12, sweeps=sweeps, burn=sweeps // 4,
              thin=max(1, (sweeps - sweeps // 4) // 150), seed=seed + 1, log=log)
    pb = forecast(b, c10e * g10e, ev1e["deaths"], ev1e["births"], 12, places.entity_unit, rho=(1, 1, 1, 1), draws=draws,
                  noise=False, innovation=False, completeness="same", log=log)["bands"]
    pb = _bridge(pb, truth22_b)
    members = places.entity_members
    rows(pb, "municipality", lambda e: "+".join(str(m) for m in members[e]), range(2010, 2023), "2010-2022", "intercensal")
    births_completeness(b, "reconciled 2010 and PES 2022", range(2010, 2022))
    log("extension: 2022-2023")
    ext = forecast(b, c22e_true, ev2e["deaths"], ev2e["births"], 1, places.entity_unit, rho=PERSISTENCE, draws=draws,
                   noise=False, innovation=True, completeness="decay", seed=seed + 2, log=log)["bands"]
    rows(ext[1:], "municipality", lambda e: "+".join(str(m) for m in members[e]), [2023], "2022-2023", "extension")
    table = pa.Table.from_pylist(tables)
    settings = SimpleNamespace(lake_dir=Path(root) / "lake")
    from . import __version__

    inputs = {"CENSO 2000 (raw)": "SIDRA table 1552", "CENSO 2010 (raw)": "SIDRA table 1378",
              "CENSO 2022 (raw)": "SIDRA table 9514",
              "SIM.DO deaths 2000-2023": f"pegasus_data {__version__}",
              "SINASC-DN births 2000-2023": f"pegasus_data {__version__}",
              "PES 2022 net-error margins": "IBGE liv102110 (sources/pes.py)",
              "POPSVS 2000 and 2010 (modelled; coverage prior)": "RIPSA/MoH = IBGE Projeções Revisão 2024",
              "comparable areas 2000-2010": "IPEA geobr AMC + the five post-2010 creations by their parents"}
    manifest = ModelledManifest(
        product="population_account", version=version,
        model="cohort-component account with Gibbs-sampled hierarchical net migration (B-spline age profile per sex; "
              "national + state + micro-region + municipal effects) and births-registration shortfalls; "
              "population_account.py v1",
        estimates={"population": ["population_lo", "population_hi"]}, inputs=inputs, validation=validation,
        notes=["Reference date 1 August of `year` (the census date). Interval: 10th-90th percentile of the draws.",
               "Population is the TRUE population: censuses are brought to coverage by the 2022 PES (published margins, "
               "raked) and, for 2000 and 2010, by IBGE's reconciliation (a sensitivity assumption, itself made with the PES).",
               "Death registration is not estimated: a 10% shortfall is assumed for 2000-2010 (it cannot be told from net "
               "migration at old ages) and closes after.",
               "Intercensal rows are anchored to the census that ends them, so their interval narrows to nothing there; the "
               "2023 row (extension) carries the next period's uncertainty.",
               "Rows are municipalities, except `+`-joined groups inside a comparable area touched by a post-2010 creation, and "
               "`comparable_area` rows for 2000-2010."])
    out = write_modelled(table, manifest, settings=settings)
    comp = pa.Table.from_pylist(completeness)
    manifest2 = ModelledManifest(
        product="registration_completeness", version=version,
        model="births-registration shortfall κ of the population account, by state and half-period (completeness = 1/(1+κ))",
        estimates={"completeness": ["completeness_lo", "completeness_hi"]}, inputs=inputs, validation=validation,
        notes=["Net of the census coverage assumed for the period's two censuses: with other coverage, other completeness.",
               "A value above 1 is not registration: it says the census counted fewer children than the registered births "
               "imply, that is, a census undercount of children that the coverage assumed did not remove.",
               "SIM (deaths) completeness is not estimated (see population_account)."])
    out2 = write_modelled(comp, manifest2, settings=settings)
    return {"population_account": str(out), "registration_completeness": str(out2), "rows": table.num_rows}
