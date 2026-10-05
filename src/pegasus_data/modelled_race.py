"""Race misclassification between systems: the infant confusion matrix (modelled tier, ``race_confusion_infant``).

The same person's race/colour differs across DATASUS systems. For infants it is measured: the stored
probabilistic link ``sim_infant_deaths_to_sinasc`` pairs the death certificate (SIM) with the birth
record (SINASC), whose race is the *mother's declaration* (RACACOR equals RACACORMAE in every pair
where both are known), the same self-declaration the Census collects. The product is

    C(k | j, x) = P(race recorded in SIM = k | race declared at birth = j, state, municipality, age at death)

a hierarchical multinomial logit:

* a logit per (j, k) with k the five colours and "blank", j the five colours and "unknown" (a SINASC
  blank), Branca the reference outcome;
* region and state effects, shrunk (region effects sum to zero over regions, state effects within
  their region, so the intercept alone carries the level);
* the municipality's racial composition (shares of Branca, Preta, Parda, Indígena among its births,
  smoothed to the state, and log10 births): SIM records toward the local majority;
* the age band at death (0-6 d, 7-27 d, 28-364 d);
* pairs are weighted by the inverse probability of being linked given (state, age band, recorded race),
  so the estimate describes all infant deaths and not only the linkable ones (deaths recorded as
  indigenous link 65% of the time against 81% for the rest).

The prior scales of the four groups of effects are chosen on held-out data (train on one year, score
the other, both ways), then the posterior is sampled by NUTS (numpyro) with the inverse Hessian at the
mode as mass matrix. The uncertainty of the scales is not propagated. Covariates were chosen on the
2021 -> 2022 held-out log score; ten other SIM fields (place of death, certifier, mother's education,
birth weight, ...) added at most 0.01 nat per record together and are left out, since PegaSUS's lattice
does not carry them (docs/evaluation/2026-10-05-race-bridge-model.md).

The product is written through ``modelled.write_modelled`` with its version, 5%/95% posterior
intervals and validation evidence; the parameter draws ship beside it (``draws.npz``) so a consumer can
propagate the uncertainty. **Predictive** counts (what a state's cross-tab will be) are wider than the
posterior of C: validated out of sample, their sd must be multiplied by ``PREDICTIVE_DISPERSION``.

``reclassify`` is the use: SIM deaths by recorded race to deaths by declared race (the denominators'
race, SINASC or Census), by a Poisson deconvolution that borrows strength across states through
race-specific rate ratios. It is validated on the linked deaths, whose declared race is known.
Applying a fitted product needs only numpy; fitting needs the ``modelled`` extra (jax, numpyro, scikit-learn).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

MODEL_VERSION = "race-confusion-infant-1"
#: Factor on the sd of a simulated state x recorded-race count for 90% predictive coverage out of sample
#: (measured: z-scores of 2021->2022 and 2022->2021 had sd 1.52 and 1.60).
PREDICTIVE_DISPERSION = 1.5

#: Colour codes shared by SINASC and SIM (RACACOR): 1 Branca, 2 Preta, 3 Amarela, 4 Parda, 5 Indígena.
RACES = ("Branca", "Preta", "Amarela", "Parda", "Indígena")
#: Declared classes (rows of C): the five colours and "unknown" (a blank in SINASC).
DECLARED = (*RACES, "Ignorado")
#: Recorded classes (columns of C): the five colours and "blank" (a blank in SIM).
RECORDED = (*RACES, "Ignorado")
CODE = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4}
UNKNOWN = 5
AGE_BANDS = ("0-6 d", "7-27 d", "28-364 d")
#: Age bands (years) of the women 15-49 product; the model is the same, the bands are the population's.
WOMEN_AGE_BANDS = ("15-24 y", "25-34 y", "35-49 y")
WOMEN_AGE_EDGES = (25, 35)
UF_CODES = (11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53)
#: Pseudo-count that smooths a municipality's racial shares toward its state's.
KAPPA = 20.0
#: Composition covariates: shares of Branca, Preta, Parda, Indígena and log10 births.
Z_NAMES = ("share_Branca", "share_Preta", "share_Parda", "share_Indigena", "log10_births")


# --------------------------------------------------------------------------------------- inputs

def encode_race(codes: Any) -> np.ndarray:
    """RACACOR codes ('1'..'5', null or anything else) to 0..4, 5 for a blank."""
    return np.array([CODE.get(None if c is None else str(c).strip().lstrip("0"), UNKNOWN) for c in codes], dtype=np.int8)


def age_band(days: np.ndarray) -> np.ndarray:
    """Age at death in days to the band index 0 (0-6 d), 1 (7-27 d), 2 (28-364 d)."""
    d = np.asarray(days)
    return np.where(d < 7, 0, np.where(d < 28, 1, 2)).astype(np.int8)


def age_band_years(years: np.ndarray) -> np.ndarray:
    """Age in years to the women product's band index 0 (15-24), 1 (25-34), 2 (35-49)."""
    return np.searchsorted(np.asarray(WOMEN_AGE_EDGES), np.asarray(years), side="right").astype(np.int8)


@dataclass(frozen=True)
class Population:
    """What a confusion product is about: the stored link that gives the reference, the age bands, the table's name."""

    product: str
    version: str
    age_bands: tuple[str, ...]
    age_column: str                    # column of ``deaths`` holding age (days for infants, years for women)
    band: Any                          # age column -> band index
    link: str


INFANT = Population("race_confusion_infant", MODEL_VERSION, AGE_BANDS, "age_days", age_band, "sim_infant_deaths_to_sinasc")
WOMEN = Population("race_confusion_women", "race-confusion-women-1", WOMEN_AGE_BANDS, "age_years", age_band_years,
                   "sim_women_deaths_to_sinasc_mothers")


@dataclass(frozen=True)
class Composition:
    """The racial composition of each municipality's births (the model's municipal covariate)."""

    mun: np.ndarray            # 6-digit municipality codes
    z_raw: np.ndarray          # (n, 5) shares and log10 size
    mean: np.ndarray           # standardisation, fixed at fit time
    sd: np.ndarray

    def z(self, mun: np.ndarray) -> np.ndarray:
        """Standardised covariates for ``mun`` (6-digit codes); unseen municipalities get the mean."""
        idx = {int(m): i for i, m in enumerate(self.mun)}
        raw = np.array([self.z_raw[idx[int(m)]] if int(m) in idx else self.mean for m in mun])
        return (raw - self.mean) / self.sd


def composition(births: pa.Table, *, standardise: tuple[np.ndarray, np.ndarray] | None = None) -> Composition:
    """Municipal composition from births counted by (municipality, race code): columns ``mun``, ``race``, ``n``."""
    mun = np.array([int(m) for m in births["mun"].to_pylist()])
    race = encode_race(births["race"].to_pylist())
    n = np.asarray(births["n"].to_numpy(zero_copy_only=False), dtype=float)
    muns = np.unique(mun)
    pos = {int(m): i for i, m in enumerate(muns)}
    counts = np.zeros((len(muns), 6))
    for m, r, c in zip(mun, race, n, strict=True):
        counts[pos[int(m)], r] += c
    uf = muns // 10000
    shares = np.zeros((len(muns), 4))
    sel = [0, 1, 3, 4]
    for u in np.unique(uf):
        rows = uf == u
        known = counts[rows][:, :5]
        state_share = known.sum(0)[sel] / max(known.sum(), 1.0)
        tot = known.sum(1, keepdims=True)
        shares[rows] = (known[:, sel] + KAPPA * state_share) / (tot + KAPPA)
    size = np.log10(np.maximum(counts.sum(1), 1.0))
    z_raw = np.column_stack([shares, size])
    mean, sd = standardise if standardise else (z_raw.mean(0), z_raw.std(0))
    return Composition(muns, z_raw, mean, sd)


@dataclass(frozen=True)
class Pairs:
    """Linked (declared, recorded) pairs with their covariates, as plain arrays."""

    j: np.ndarray       # declared class 0..5
    k: np.ndarray       # recorded class 0..5
    uf: np.ndarray      # index into UF_CODES
    age: np.ndarray     # 0..2
    z: np.ndarray       # (n, 5) standardised composition
    w: np.ndarray       # weights, mean 1
    n_age: int = 3      # number of age bands (the population's)
    #: Share of false links in each pair's class, and the recorded-class distribution of an unrelated pair, by state
    #: (27, 6). A false pair's declared race is unrelated to the recorded one, so a pair's recorded class has
    #: probability (1 - phi) C(k | j) + phi r(k): the contamination measured by the link's negative control.
    phi: np.ndarray | None = None
    r_state: np.ndarray | None = None


def uf_index(uf_codes: np.ndarray) -> np.ndarray:
    lookup = {c: i for i, c in enumerate(UF_CODES)}
    return np.array([lookup[int(c)] for c in uf_codes], dtype=np.int16)


def region_of_uf() -> np.ndarray:
    """Macro-region index (0 North .. 4 Centre-West) of each entry of ``UF_CODES``."""
    return np.array([c // 10 - 1 for c in UF_CODES], dtype=np.int8)


def link_weights(uf: np.ndarray, age: np.ndarray, recorded: np.ndarray, year: np.ndarray, linked: np.ndarray,
                 extra: np.ndarray | None = None, n_age: int = 3) -> np.ndarray:
    """Inverse probability of being linked, from all deaths of the population (linked or not).

    The probability is a logistic regression on state, age band, recorded race, age band × recorded
    race and year (a one-hot per year when there are several), plus ``extra`` columns (the women
    product adds the municipality's size class), so weights depend only on what every death carries.
    """
    from sklearn.linear_model import LogisticRegression  # noqa: PLC0415 - fitting-time dependency

    years = np.unique(year)
    cols = [np.eye(len(UF_CODES))[uf], np.eye(n_age)[age], np.eye(6)[recorded],
            (np.eye(n_age)[age][:, :, None] * np.eye(6)[recorded][:, None, :]).reshape(len(uf), -1),
            (year == year.max())[:, None].astype(float) if len(years) <= 2 else (year[:, None] == years[None, 1:]).astype(float)]
    if extra is not None:
        cols.append(np.asarray(extra, dtype=float))
    x = np.hstack(cols)
    p = LogisticRegression(C=1.0, max_iter=2000).fit(x, linked).predict_proba(x)[:, 1]
    return np.where(linked, 1.0 / p, 0.0)


# --------------------------------------------------------------------------------------- the model

def _logits(p: dict[str, Any], j, uf, reg_of_uf, age, z, xp):
    """Logits of the five non-reference recorded classes for each row; ``p`` holds one parameter set."""
    eta = p["alpha"][j] + p["region"][j, reg_of_uf[uf]] + p["state"][j, uf]
    eta = eta + xp.einsum("nz,nzk->nk", z, p["beta"][j])
    eta = eta + xp.where((age > 0)[:, None], p["age"][j, xp.maximum(age - 1, 0)], 0.0)
    return eta


#: Prior scales of the four groups of effects (state, region, composition, age); chosen on held-out data.
SCALE_NAMES = ("state", "region", "beta", "age")
ALPHA_SD = 3.0


def _effects(raw: dict[str, Any], scales: dict[str, float], reg_of_uf: np.ndarray, xp):
    """Parameters from their standard-normal raw values: scaled, region effects summing to zero over
    regions and state effects to zero within their region, so the intercept alone carries the level."""
    member = xp.asarray(np.eye(5)[reg_of_uf])                                              # (27, 5)
    region = raw["region"] * scales["region"]
    region = region - region.mean(axis=1, keepdims=True)
    state = raw["state"] * scales["state"]
    by_region = xp.einsum("ur,jvk->jrk", member, state) / member.sum(0)[None, :, None]
    state = state - xp.einsum("ur,jrk->juk", member, by_region)
    return {"alpha": raw["alpha"] * ALPHA_SD, "region": region, "state": state,
            "beta": raw["beta"] * scales["beta"], "age": raw["age"] * scales["age"]}


def _raw_shapes(nz: int, n_age: int = 3) -> dict[str, tuple[int, ...]]:
    return {"alpha": (6, 5), "region": (6, 5, 5), "state": (6, len(UF_CODES), 5), "beta": (6, nz, 5), "age": (6, n_age - 1, 5)}


def _data(pairs: Pairs):
    """Pairs aggregated into cells (declared class, state, age band, municipality covariates), sorted by
    declared class: per cell the weighted count of each recorded class. Returns the blocks of cells per
    declared class (static slices) and the arrays, which makes the likelihood a few small matrix products."""
    import jax.numpy as jnp  # noqa: PLC0415

    phi = np.zeros(len(pairs.j)) if pairs.phi is None else np.asarray(pairs.phi)
    key = np.column_stack([pairs.j, pairs.uf, pairs.age, phi, pairs.z])
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    counts = np.zeros((len(uniq), 6))
    np.add.at(counts, (inv.ravel(), pairs.k), pairs.w)
    bounds = np.searchsorted(uniq[:, 0], np.arange(7))
    r_state = np.full((len(UF_CODES), 6), 1 / 6) if pairs.r_state is None else np.asarray(pairs.r_state)
    return {"blocks": [(int(bounds[j]), int(bounds[j + 1])) for j in range(6)], "uf": jnp.asarray(uniq[:, 1].astype(int)),
            "age": jnp.asarray(uniq[:, 2].astype(int)), "phi": jnp.asarray(uniq[:, 3]), "r": jnp.asarray(r_state[uniq[:, 1].astype(int)]),
            "z": jnp.asarray(uniq[:, 4:]), "counts": jnp.asarray(counts)}


def _log_lik(par, data, reg_of_uf):
    import jax.numpy as jnp  # noqa: PLC0415

    reg = jnp.asarray(reg_of_uf)
    total = 0.0
    for j, (lo, hi) in enumerate(data["blocks"]):
        if hi == lo:
            continue
        uf, age, z = data["uf"][lo:hi], data["age"][lo:hi], data["z"][lo:hi]
        eta = par["alpha"][j] + par["region"][j][reg[uf]] + par["state"][j][uf] + z @ par["beta"][j]
        eta = eta + jnp.where((age > 0)[:, None], par["age"][j][jnp.maximum(age - 1, 0)], 0.0)
        full = jnp.concatenate([jnp.zeros((hi - lo, 1)), eta], axis=1)
        p = jnp.exp(full - jnp.log(jnp.sum(jnp.exp(full), axis=1, keepdims=True)))
        phi = data["phi"][lo:hi, None]
        total = total + jnp.sum(data["counts"][lo:hi] * jnp.log((1 - phi) * p + phi * data["r"][lo:hi]))
    return total


def map_fit(pairs: Pairs, scales: dict[str, float], *, maxiter: int = 400) -> dict[str, np.ndarray]:
    """Penalised maximum likelihood (the posterior mode) for fixed prior scales: the raw effects."""
    import jax  # noqa: PLC0415
    import jax.numpy as jnp  # noqa: PLC0415
    from jax.flatten_util import ravel_pytree  # noqa: PLC0415
    from scipy.optimize import minimize  # noqa: PLC0415

    reg = region_of_uf()
    data = _data(pairs)
    raw0 = {n: jnp.zeros(s) for n, s in _raw_shapes(pairs.z.shape[1], pairs.n_age).items()}
    flat0, unravel = ravel_pytree(raw0)

    def objective(f):
        raw = unravel(f)
        return -(_log_lik(_effects(raw, scales, reg, jnp), data, reg) - 0.5 * sum(jnp.sum(v * v) for v in raw.values()))

    vg = jax.jit(jax.value_and_grad(objective))
    res = minimize(lambda f: tuple(np.asarray(x, dtype=float) for x in vg(jnp.asarray(f))), np.asarray(flat0, dtype=float),
                   jac=True, method="L-BFGS-B", options={"maxiter": maxiter, "maxfun": maxiter * 2})
    return {n: np.asarray(v) for n, v in unravel(jnp.asarray(res.x)).items()}


def mean_log_loss(par: dict[str, np.ndarray], pairs: Pairs) -> float:
    """Mean negative log probability of the recorded class under parameters ``par`` (weighted by ``pairs.w``)."""
    eta = _logits(par, pairs.j, pairs.uf, region_of_uf(), pairs.age, pairs.z, np)
    full = np.concatenate([np.zeros((len(pairs.j), 1)), eta], axis=1)
    full -= full.max(1, keepdims=True)
    p = np.exp(full - np.log(np.exp(full).sum(1, keepdims=True)))
    if pairs.phi is not None and pairs.r_state is not None:
        p = (1 - pairs.phi[:, None]) * p + pairs.phi[:, None] * pairs.r_state[pairs.uf]
    return float(-np.average(np.log(p[np.arange(len(pairs.j)), pairs.k]), weights=pairs.w))


def select_scales(train: Pairs, test: Pairs, grid: dict[str, tuple[float, ...]] | None = None) -> tuple[dict[str, float], list[dict]]:
    """The prior scales with the best held-out log loss on a small grid (no scale is a constant of the model)."""
    import itertools  # noqa: PLC0415

    grid = grid or {"state": (0.15, 0.4, 1.0), "region": (0.3, 1.0), "beta": (0.15, 0.5, 1.5), "age": (0.15, 0.5, 1.5)}
    table = []
    reg = region_of_uf()
    for values in itertools.product(*(grid[n] for n in SCALE_NAMES)):
        sc = dict(zip(SCALE_NAMES, values, strict=True))
        par = {k: np.asarray(v) for k, v in _effects(map_fit(train, sc), sc, reg, np).items()}
        table.append({**sc, "held_out_log_loss": mean_log_loss(par, test)})
    best = min(table, key=lambda r: r["held_out_log_loss"])
    return {n: best[n] for n in SCALE_NAMES}, table


def _numpyro_model(pairs: Pairs, reg_of_uf: np.ndarray, scales: dict[str, float]):
    import jax.numpy as jnp  # noqa: PLC0415
    import numpyro  # noqa: PLC0415
    import numpyro.distributions as dist  # noqa: PLC0415

    raw = {n: numpyro.sample(n, dist.Normal(0.0, 1.0).expand(list(s)).to_event(len(s)))
           for n, s in _raw_shapes(pairs.z.shape[1], pairs.n_age).items()}
    par = _effects(raw, scales, reg_of_uf, jnp)
    numpyro.factor("lik", _log_lik(par, _data(pairs), reg_of_uf))
    for n, v in par.items():
        numpyro.deterministic("eff_" + n, v)


@dataclass
class Fit:
    """Posterior draws of the confusion model's parameters, with what is needed to apply them."""

    draws: dict[str, np.ndarray]   # alpha (S,6,5), region (S,6,5,5), state (S,6,27,5), beta (S,6,nz,5), age (S,6,2,5)
    z_mean: np.ndarray
    z_sd: np.ndarray
    n_pairs: int
    diagnostics: dict[str, Any]
    version: str = MODEL_VERSION
    age_bands: tuple[str, ...] = AGE_BANDS

    def save(self, path: Path) -> None:
        np.savez_compressed(path, z_mean=self.z_mean, z_sd=self.z_sd, n_pairs=self.n_pairs,
                            diagnostics=json.dumps(self.diagnostics), version=self.version,
                            age_bands=np.array(self.age_bands), **self.draws)

    @classmethod
    def load(cls, path: Path) -> Fit:
        f = np.load(path, allow_pickle=False)
        draws = {k: f[k] for k in ("alpha", "region", "state", "beta", "age")}
        bands = tuple(str(b) for b in f["age_bands"]) if "age_bands" in f.files else AGE_BANDS
        return cls(draws, f["z_mean"], f["z_sd"], int(f["n_pairs"]), json.loads(str(f["diagnostics"])), str(f["version"]), bands)


def fit(pairs: Pairs, scales: dict[str, float], *, z_mean: np.ndarray, z_sd: np.ndarray, num_warmup: int = 300,
        num_samples: int = 400, num_chains: int = 2, keep: int = 200, seed: int = 0,
        age_bands: tuple[str, ...] = AGE_BANDS, version: str = MODEL_VERSION) -> Fit:
    """NUTS posterior of the confusion model for the prior scales ``scales`` (requires the ``modelled`` extra).

    The scales are fixed (``select_scales``), so the posterior is log-concave and well conditioned; the
    uncertainty of the scales themselves is not propagated.
    """
    import jax  # noqa: PLC0415
    import jax.numpy as jnp  # noqa: PLC0415
    from jax.flatten_util import ravel_pytree  # noqa: PLC0415
    from numpyro.diagnostics import summary  # noqa: PLC0415
    from numpyro.infer import MCMC, NUTS, init_to_value  # noqa: PLC0415

    reg = region_of_uf()
    start = map_fit(pairs, scales)
    # The posterior is close to Gaussian, so the inverse Hessian at the mode is the right mass matrix: a
    # diagonal one (adapted) needs trees of ~500 steps because the data pin some directions 100x tighter
    # than the prior pins others.
    data = _data(pairs)
    flat0, unravel = ravel_pytree({n: jnp.asarray(v) for n, v in start.items()})

    def objective(f):
        raw = unravel(f)
        return -(_log_lik(_effects(raw, scales, reg, jnp), data, reg) - 0.5 * sum(jnp.sum(v * v) for v in raw.values()))

    hessian = np.asarray(jax.hessian(objective)(flat0), dtype=float)
    inv_mass = np.linalg.inv((hessian + hessian.T) / 2 + 1e-6 * np.eye(len(hessian)))
    kernel = NUTS(lambda: _numpyro_model(pairs, reg, scales), target_accept_prob=0.85, init_strategy=init_to_value(values=start),
                  dense_mass=True, inverse_mass_matrix=inv_mass, adapt_mass_matrix=False)
    mcmc = MCMC(kernel, num_warmup=num_warmup, num_samples=num_samples, num_chains=num_chains, chain_method="sequential",
                progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed), extra_fields=("num_steps", "diverging"))
    grouped = mcmc.get_samples(group_by_chain=True)
    stats = summary({k: grouped["eff_" + k] for k in ("alpha", "region", "state", "beta", "age")}, group_by_chain=True)
    rhat = max(float(np.nanmax(np.asarray(v["r_hat"]))) for v in stats.values())
    ess = min(float(np.nanmin(np.asarray(v["n_eff"]))) for v in stats.values())
    flat = mcmc.get_samples()
    n = flat["eff_alpha"].shape[0]
    take = np.linspace(0, n - 1, min(keep, n)).astype(int)
    draws = {k: np.asarray(flat["eff_" + k])[take].astype(np.float32) for k in ("alpha", "region", "state", "beta", "age")}
    extra = mcmc.get_extra_fields()
    diag = {"max_rhat": rhat, "min_ess": ess, "divergences": int(np.sum(np.asarray(extra["diverging"]))),
            "mean_leapfrog_steps": float(np.mean(np.asarray(extra["num_steps"]))), "num_warmup": num_warmup,
            "num_samples": num_samples, "num_chains": num_chains, "kept_draws": int(len(take)), "scales": scales}
    return Fit(draws, np.asarray(z_mean), np.asarray(z_sd), int(len(pairs.j)), diag, version, age_bands)

def confusion(model: Fit, uf: np.ndarray, age: np.ndarray, z: np.ndarray, draws: slice | np.ndarray | None = None) -> np.ndarray:
    """C draws for each row: array (S, n, 6 declared, 6 recorded); ``uf`` indexes ``UF_CODES``, ``z`` is standardised."""
    d = {k: v if draws is None else v[draws] for k, v in model.draws.items()}
    reg = region_of_uf()
    n = len(uf)
    out = np.empty((d["alpha"].shape[0], n, 6, 6), dtype=np.float32)
    for s in range(out.shape[0]):
        par = {k: v[s] for k, v in d.items()}
        for j in range(6):
            eta = _logits(par, np.full(n, j), uf, reg, age, z, np)
            full = np.concatenate([np.zeros((n, 1)), eta], axis=1)
            full -= full.max(1, keepdims=True)
            e = np.exp(full)
            out[s, :, j, :] = e / e.sum(1, keepdims=True)
    return out


def confusion_row(model: Fit, j: np.ndarray, uf: np.ndarray, age: np.ndarray, z: np.ndarray,
                  draws: slice | np.ndarray | None = None) -> np.ndarray:
    """P(recorded = k | declared = j[i], covariates[i]) for each row i: array (S, n, 6)."""
    d = {k: v if draws is None else v[draws] for k, v in model.draws.items()}
    reg = region_of_uf()
    out = np.empty((d["alpha"].shape[0], len(j), 6), dtype=np.float32)
    for s in range(out.shape[0]):
        eta = _logits({k: v[s] for k, v in d.items()}, j, uf, reg, age, z, np)
        full = np.concatenate([np.zeros((len(j), 1)), eta], axis=1)
        full -= full.max(1, keepdims=True)
        e = np.exp(full)
        out[s] = e / e.sum(1, keepdims=True)
    return out


# --------------------------------------------------------------------------------------- the use

def expected_matrix(model: Fit, comp: Composition, mun: np.ndarray, births: np.ndarray,
                    draws: slice | np.ndarray | None = None, chunk: int = 1500) -> np.ndarray:
    """``A[s, u, a, k, j]``: recorded-k deaths expected per unit death rate among the births declared j.

    ``mun`` are 6-digit municipality codes and ``births`` (n, 6) their births by declared class, so
    that ``A`` sums C(k | j, municipality, age band) × births over each state ``u`` (index of ``UF_CODES``).
    """
    uf = uf_index(np.asarray(mun) // 10000)
    z = comp.z(np.asarray(mun))
    s_n = (model.draws["alpha"] if draws is None else model.draws["alpha"][draws]).shape[0]
    n_age = len(model.age_bands)
    out = np.zeros((s_n, len(UF_CODES), n_age, 6, 6))
    for a in range(n_age):
        for lo in range(0, len(mun), chunk):
            sl = slice(lo, lo + chunk)
            c = confusion(model, uf[sl], np.full(len(uf[sl]), a), z[sl], draws)      # (S, n, j, k)
            contrib = np.einsum("snjk,nj->snkj", c, births[sl])
            for u in np.unique(uf[sl]):
                out[:, u, a] += contrib[:, uf[sl] == u].sum(1)
    return out


def reclassify(a_mat: np.ndarray, deaths: np.ndarray, births: np.ndarray, *, tau: float = 0.5, laplace: int = 3,
               seed: int = 0) -> np.ndarray:
    """Deaths by declared race from deaths by recorded race: draws of shape (T, 27, 3, 6).

    ``deaths[u, a, k]`` are SIM deaths by state, age band and recorded class, ``births[u, j]`` the
    births by declared class of the same year, ``a_mat`` from ``expected_matrix`` (one slice per draw
    of C). For each draw of C the recorded counts are Poisson with mean

        sum_j A[u, a, k, j] * r[u, a] * exp(rho[j] + delta[region(u), j])      (rho[Branca] = delta[., Branca] = 0)

    a rate per state and age band times a race-specific rate ratio, national plus a regional departure
    (prior sd ``tau`` on the log scale): the ratios are what the differing composition of the states
    identifies. The mode and a Laplace approximation of that Poisson model give ``laplace`` draws of the
    parameters for each draw of C, so the intervals carry both the uncertainty of C and the Poisson noise;
    the deaths by declared race are births x rate x ratio. Requires the ``modelled`` extra (jax).
    """
    import jax  # noqa: PLC0415
    import jax.numpy as jnp  # noqa: PLC0415
    from jax.flatten_util import ravel_pytree  # noqa: PLC0415
    from scipy.optimize import minimize  # noqa: PLC0415

    reg = jnp.asarray(region_of_uf())
    d = jnp.asarray(deaths)
    b = jnp.asarray(births)
    r0 = np.log(np.maximum(deaths.sum(-1), 1.0) / np.maximum(births.sum(-1), 1.0)[:, None])
    template = {"log_r": jnp.asarray(r0), "rho": jnp.zeros(5), "delta": jnp.zeros((5, 5))}
    flat0, unravel = ravel_pytree(template)
    rng = np.random.default_rng(seed)

    def lam(par):
        rho = jnp.concatenate([jnp.zeros(1), par["rho"] + 0.0])                       # (6,) Branca = 0
        delta = jnp.concatenate([jnp.zeros((5, 1)), par["delta"]], axis=1)             # (5 regions, 6)
        return jnp.exp(par["log_r"][:, :, None] + (rho[None, :] + delta[reg])[:, None, :])    # (27, 3, 6)

    @jax.jit
    def objective(f, a):
        par = unravel(f)
        mean = jnp.einsum("uakj,uaj->uak", a, lam(par))
        nll = jnp.sum(mean - d * jnp.log(mean + 1e-9))
        return nll + 0.5 * jnp.sum(par["rho"] ** 2) / 4.0 + 0.5 * jnp.sum(par["delta"] ** 2) / tau**2 + 0.5 * jnp.sum(par["log_r"] ** 2) * 1e-6

    vg = jax.jit(jax.value_and_grad(objective))
    hess = jax.jit(jax.hessian(objective))
    out = []
    for i in range(a_mat.shape[0]):
        a_i = jnp.asarray(a_mat[i])
        res = minimize(lambda f, a_i=a_i: tuple(np.asarray(x, dtype=float) for x in vg(jnp.asarray(f), a_i)),
                       np.asarray(flat0, dtype=float), jac=True, method="L-BFGS-B", options={"maxiter": 300})
        h = np.asarray(hess(jnp.asarray(res.x), a_i), dtype=float)
        evals, evecs = np.linalg.eigh((h + h.T) / 2)
        chol = evecs / np.sqrt(np.maximum(evals, 1e-3))                       # covariance factor; flat directions clipped
        for _ in range(laplace):
            f = res.x + chol @ rng.standard_normal(len(res.x))
            out.append(np.asarray(lam(unravel(jnp.asarray(f))) * b[:, None, :]))
    return np.stack(out)


# --------------------------------------------------------------------------------------- the product

def summarise(model: Fit, comp: Composition, mun: np.ndarray, births: np.ndarray) -> pa.Table:
    """The shipped table: C(k | j) per state and age band, births-weighted over the state's municipalities.

    ``mun`` (6-digit codes) and ``births`` (n, 6, by declared class) are the reference year's. A row
    ``uf = 0`` is Brazil. Columns: uf, age_band, declared, recorded, p, p_lo, p_hi (5% and 95%).
    """
    a = expected_matrix(model, comp, mun, births)                                    # (S, 27, 3, k, j)
    uf = uf_index(np.asarray(mun) // 10000)
    b_state = np.zeros((len(UF_CODES), 6))
    np.add.at(b_state, uf, births)
    cols: dict[str, list] = {n: [] for n in ("uf", "age_band", "declared", "recorded", "p", "p_lo", "p_hi")}
    for u in range(len(UF_CODES) + 1):
        num = a.sum(1) if u == len(UF_CODES) else a[:, u]                             # (S, 3, k, j)
        den = b_state.sum(0) if u == len(UF_CODES) else b_state[u]                    # (j,)
        for ai in range(len(model.age_bands)):
            c = num[:, ai] / np.maximum(den, 1.0)[None, None, :]                      # (S, k, j)
            for j in range(6):
                if den[j] <= 0:
                    continue
                for k in range(6):
                    x = c[:, k, j]
                    for name, val in zip(cols, (0 if u == len(UF_CODES) else UF_CODES[u], model.age_bands[ai], DECLARED[j], RECORDED[k],
                                                float(x.mean()), float(np.quantile(x, 0.05)), float(np.quantile(x, 0.95))), strict=True):
                        cols[name].append(val)
    return pa.table(cols)


def prepare(deaths: pa.Table, comp: Composition, population: Population = INFANT) -> tuple[np.ndarray, np.ndarray, Any]:
    """Arrays of a deaths table (see ``build``): the year, the linked mask and ``pairs(mask)``, the weighted ``Pairs``
    of the deaths in a mask (weights are per year, inverse linkage probability, mean 1 among the linked)."""
    year = np.asarray(deaths["year"].to_numpy(zero_copy_only=False))
    uf = uf_index(np.asarray(deaths["uf"].to_numpy(zero_copy_only=False)))
    age = population.band(np.asarray(deaths[population.age_column].to_numpy(zero_copy_only=False)))
    n_age = len(population.age_bands)
    stratum = (np.eye(int(deaths["stratum"].to_numpy().max()) + 1)[deaths["stratum"].to_numpy()]
               if "stratum" in deaths.column_names else None)
    rec = encode_race(deaths["recorded"].to_pylist())
    dec = encode_race(deaths["declared"].to_pylist())
    linked = np.asarray(deaths["linked"].to_numpy(zero_copy_only=False), dtype=bool)
    z = comp.z(np.asarray([int(m) for m in deaths["mun"].to_pylist()]))
    w = np.zeros(len(year))
    for y in np.unique(year):
        s = year == y
        wy = link_weights(uf[s], age[s], rec[s], year[s], linked[s], None if stratum is None else stratum[s], n_age)
        w[s] = wy / wy[linked[s]].mean()

    phi = np.asarray(deaths["phi"].to_numpy(zero_copy_only=False), dtype=float) if "phi" in deaths.column_names else None
    r_state = None
    if phi is not None:
        r_state = np.zeros((len(UF_CODES), 6))
        np.add.at(r_state, (uf, rec), 1.0)
        r_state = (r_state + 0.5) / (r_state + 0.5).sum(1, keepdims=True)

    def pairs(mask):
        return Pairs(dec[mask], rec[mask], uf[mask], age[mask], z[mask], w[mask], n_age,
                     None if phi is None else phi[mask], r_state)

    return year, linked, pairs


def build(deaths: pa.Table, births: pa.Table, reference_births: pa.Table, *, settings: Any,
          validation: str, population: Population = INFANT, seed: int = 0, notes: tuple[str, ...] = (),
          scales: dict[str, float] | None = None) -> Path:
    """Fit a race confusion model on the stored links and write it to the modelled tier.

    ``deaths``: every SIM death of the population in the fitted years, columns ``year``, ``uf`` (code),
    the population's age column (``age_days`` or ``age_years``), ``recorded`` (RACACOR code or null),
    ``mun`` (CODMUNRES), ``linked`` (bool), ``declared`` (the linked reference race code, null if
    unlinked or blank), optionally ``stratum`` (int: a class of the link's reliability that also
    drives linkability, entered in the linkage weights) and ``phi`` (the share of false links in the
    death's stratum, measured by the link's negative control; see ``Pairs.phi``). ``births``: SINASC births by
    (``mun``, ``race``, ``n``) that define the municipal composition. ``reference_births`` the same for
    the year the table is expressed on. Needs the ``modelled`` extra.
    """
    from .modelled import ModelledManifest, write_modelled  # noqa: PLC0415

    comp = composition(births)
    year, linked, pairs = prepare(deaths, comp, population)
    years = sorted(np.unique(year))
    mean_table: list[dict] = []
    if scales is None:
        # train on one year, score the other, both ways (the first and last years of a longer span)
        tables = []
        for a, b in ([(years[0], years[-1]), (years[-1], years[0])] if len(years) > 1 else [(years[0], years[0])]):
            _, t = select_scales(pairs(linked & (year == a)), pairs(linked & (year == b)))
            tables.append(t)
        mean_table = [{**{n: r[n] for n in SCALE_NAMES}, "held_out_log_loss": float(np.mean([t[i]["held_out_log_loss"] for t in tables]))}
                      for i, r in enumerate(tables[0])]
        best = min(mean_table, key=lambda r: r["held_out_log_loss"])
        scales = {n: best[n] for n in SCALE_NAMES}
    model = fit(pairs(linked), scales, z_mean=comp.mean, z_sd=comp.sd, seed=seed, age_bands=population.age_bands,
                version=population.version)

    ref = reference_births
    rmun = np.array([int(m) for m in ref["mun"].to_pylist()])
    rrace = encode_race(ref["race"].to_pylist())
    rn = np.asarray(ref["n"].to_numpy(zero_copy_only=False), dtype=float)
    muns = np.unique(rmun)
    pos = {int(m): i for i, m in enumerate(muns)}
    mat = np.zeros((len(muns), 6))
    for m, r, c in zip(rmun, rrace, rn, strict=True):
        mat[pos[int(m)], r] += c
    keep = np.isin(muns // 10000, UF_CODES)
    table = summarise(model, comp, muns[keep], mat[keep])
    manifest = ModelledManifest(
        product=population.product, version=population.version, model=__doc__.split("\n")[0], estimates={"p": ["p_lo", "p_hi"]},
        inputs={f"link:{population.link}": "stored links, see lake/links",
                "SIM.DO": f"RACACOR, CODMUNRES, DTNASC, DTOBITO; years {years}", "SINASC-DN": "RACACOR, CODMUNRES (declared race, composition)"},
        validation=validation,
        notes=[f"{model.n_pairs} linked pairs weighted by inverse linkage probability; scales {scales}; diagnostics {model.diagnostics}",
               "p is C(recorded | declared) averaged over the state's municipalities by their births; draws.npz holds the parameter draws",
               "declared race is the reference declaration of the linked SINASC record; the Census self-declaration is assumed the same quantity",
               *notes])
    target = write_modelled(table, manifest, settings=settings)
    model.save(target / "draws.npz")
    (target / "scales_table.json").write_text(json.dumps(mean_table, indent=1), encoding="utf-8")
    return target
