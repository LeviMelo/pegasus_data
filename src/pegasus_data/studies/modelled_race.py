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
from typing import Any, cast

import numpy as np
import pyarrow as pa

from .._age import bands
from ..config import UF_NUMERIC
from ..ontology import dataset_key

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
CODE: dict[str | None, int] = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4}
UNKNOWN = 5
AGE_BANDS = ("0-6 d", "7-27 d", "28-364 d")
#: Age bands (years) of the women 15-49 product; the model is the same, the bands are the population's.
WOMEN_AGE_BANDS = ("15-24 y", "25-34 y", "35-49 y")
WOMEN_AGE_EDGES = (25, 35)
CHILD_AGE_BANDS = ("1-4 y", "5-9 y", "10-14 y")
CHILD_AGE_EDGES = (1, 5, 10)
UF_CODES = tuple(sorted(int(code) for code in UF_NUMERIC))


def race_parameter(name: str) -> float:
    """One analytic choice of the race model (``parameters:`` of ``race_confusion_infant`` in `curation/products.yml`, which
    ``race_confusion_women`` repeats: the one model, with the reason beside each): ``kappa``, the pseudo-count that smooths a
    municipality's racial shares toward its state's; ``alpha_sd``, the prior scale of the intercepts."""
    from ..modelled import product_parameters

    return float(product_parameters("race_confusion_infant")[name])


#: Composition covariates: shares of Branca, Preta, Parda, Indígena and log10 births.
Z_NAMES = ("share_Branca", "share_Preta", "share_Parda", "share_Indigena", "log10_births")


# --------------------------------------------------------------------------------------- inputs

def encode_race(codes: Any) -> np.ndarray:
    """RACACOR codes ('1'..'5', null or anything else) to 0..4, 5 for a blank. The code is matched at its width (RACACOR
    is one digit): '01' is not '1', it is a code the codelist does not hold, so it is unknown."""
    return np.array([CODE.get(None if c is None else str(c).strip(), UNKNOWN) for c in codes], dtype=np.int8)


def age_band(days: np.ndarray) -> np.ndarray:
    """Age at death in days to the band index 0 (0-6 d), 1 (7-27 d), 2 (28-364 d); -1 where the age is not known (no band:
    the model leaves such a death out, `prepare`)."""
    return bands(days, (0, 7, 28)).astype(np.int8)


def age_band_years(years: np.ndarray) -> np.ndarray:
    """Age in years to the women product's band index 0 (15-24), 1 (25-34), 2 (35-49); -1 where not known or under 15."""
    return bands(years, (15, *WOMEN_AGE_EDGES)).astype(np.int8)


def age_band_child(years: np.ndarray) -> np.ndarray:
    """Age in years to the children's product's band index 0 (1-4), 1 (5-9), 2 (10-14); -1 where not known or under one
    year (the product's deaths stop at its declared ``max_age``)."""
    return bands(years, CHILD_AGE_EDGES).astype(np.int8)


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
CHILD = Population("race_confusion_child", "race-confusion-child-1", CHILD_AGE_BANDS, "age_years", age_band_child,
                   "sim_deaths_to_own_birth")


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
        shares[rows] = (known[:, sel] + race_parameter("kappa") * state_share) / (tot + race_parameter("kappa"))
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
    #: Share of false links in each pair's class, and per pair (n, 6) the recorded-class distribution of an unrelated
    #: pair. A false partner is another record of the same municipality (the key holds the residence), so given the
    #: municipality its declared race says nothing of the recorded one, and a pair's recorded class has probability
    #: (1 - phi) C(k | j) + phi r(k), r the recorded colours of the population's deaths in that municipality: the
    #: contamination measured by the link's negative control. Until 2026-11-21 r was the state's: municipalities differ
    #: within a state (an indigenous municipality's false pairs agree as its true ones do), so the state's r took too
    #: little out of the diagonal (the children's Indígena row came out at 1.09).
    phi: np.ndarray | None = None
    r: np.ndarray | None = None


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


def _effects(raw: dict[str, Any], scales: dict[str, float], reg_of_uf: np.ndarray, xp):
    """Parameters from their standard-normal raw values: scaled, region effects summing to zero over
    regions and state effects to zero within their region, so the intercept alone carries the level."""
    member = xp.asarray(np.eye(5)[reg_of_uf])                                              # (27, 5)
    region = raw["region"] * scales["region"]
    region = region - region.mean(axis=1, keepdims=True)
    state = raw["state"] * scales["state"]
    by_region = xp.einsum("ur,jvk->jrk", member, state) / member.sum(0)[None, :, None]
    state = state - xp.einsum("ur,jrk->juk", member, by_region)
    return {"alpha": raw["alpha"] * race_parameter("alpha_sd"), "region": region, "state": state,
            "beta": raw["beta"] * scales["beta"], "age": raw["age"] * scales["age"]}


def _raw_shapes(nz: int, n_age: int = 3) -> dict[str, tuple[int, ...]]:
    return {"alpha": (6, 5), "region": (6, 5, 5), "state": (6, len(UF_CODES), 5), "beta": (6, nz, 5), "age": (6, n_age - 1, 5)}


def _data(pairs: Pairs):
    """Pairs aggregated into cells (declared class, state, age band, municipality covariates), sorted by
    declared class: per cell the weighted count of each recorded class. Returns the blocks of cells per
    declared class (static slices) and the arrays, which makes the likelihood a few small matrix products."""
    import jax.numpy as jnp  # noqa: PLC0415

    phi = np.zeros(len(pairs.j)) if pairs.phi is None else np.asarray(pairs.phi)
    r = np.full((len(pairs.j), 6), 1 / 6) if pairs.r is None else np.asarray(pairs.r)
    key = np.column_stack([pairs.j, pairs.uf, pairs.age, phi, r, pairs.z])
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    counts = np.zeros((len(uniq), 6))
    np.add.at(counts, (inv.ravel(), pairs.k), pairs.w)
    bounds = np.searchsorted(uniq[:, 0], np.arange(7))
    return {"blocks": [(int(bounds[j]), int(bounds[j + 1])) for j in range(6)], "uf": jnp.asarray(uniq[:, 1].astype(int)),
            "age": jnp.asarray(uniq[:, 2].astype(int)), "phi": jnp.asarray(uniq[:, 3]), "r": jnp.asarray(uniq[:, 4:10]),
            "z": jnp.asarray(uniq[:, 10:]), "counts": jnp.asarray(counts)}


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
    if pairs.phi is not None and pairs.r is not None:
        p = (1 - pairs.phi[:, None]) * p + pairs.phi[:, None] * pairs.r
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
                            age_bands=np.array(self.age_bands), **self.draws)  # type: ignore[arg-type]  # numpy stub: **kwargs checked against savez_compressed's bool parameters

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
    ``births`` may be (n, age bands, 6) where the population at risk differs by band (children of several cohorts).
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
            contrib = np.einsum("snjk,nj->snkj", c, births[sl] if births.ndim == 2 else births[sl, a])
            for u in np.unique(uf[sl]):
                out[:, u, a] += contrib[:, uf[sl] == u].sum(1)
    return out


def reclassify(a_mat: np.ndarray, deaths: np.ndarray, births: np.ndarray, *, tau: float = 0.5, laplace: int = 3,
               seed: int = 0) -> np.ndarray:
    """Deaths by declared race from deaths by recorded race: draws of shape (T, 27, age bands, 6).

    ``deaths[u, a, k]`` are SIM deaths by state, age band and recorded class, ``births[u, j]`` the
    births by declared class of the same year (or ``births[u, a, j]``, the population at risk of each band, as
    ``expected_matrix`` takes it), ``a_mat`` from ``expected_matrix`` (one slice per draw
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
    by_band = np.asarray(births) if np.ndim(births) == 3 else np.repeat(np.asarray(births)[:, None, :], deaths.shape[1], axis=1)
    b = jnp.asarray(by_band)
    r0 = np.log(np.maximum(deaths.sum(-1), 1.0) / np.maximum(by_band.sum(-1), 1.0))
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
            out.append(np.asarray(lam(unravel(jnp.asarray(f))) * b))
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
    # a death of no known age has no band: it is left out of the weights and the pairs (an index of -1 would read as the
    # last band, as a missing age once did)
    known = age >= 0
    w, found = np.zeros(len(year)), np.ones(len(year))
    for y in np.unique(year):
        s = (year == y) & known
        wy = link_weights(uf[s], age[s], rec[s], year[s], linked[s], None if stratum is None else stratum[s], n_age)
        found[s] = np.where(linked[s], 1.0 / np.maximum(wy, 1e-12), 1.0)        # each linked death's probability of a pair
        w[s] = wy / wy[linked[s]].mean()

    phi, r = None, None
    if "chance" in deaths.column_names:
        # each pair's own share of false links: the chance rate of its cell and its own probability of being found
        phi = _false_share(np.asarray(deaths["chance"].to_numpy(zero_copy_only=False), dtype=float), found)
        # the recorded colours of the population's deaths in each death's municipality, drawn toward the state's by
        # ``kappa`` deaths (a municipality of three deaths says little of its own)
        r_state = np.zeros((len(UF_CODES), 6))
        np.add.at(r_state, (uf, rec), 1.0)
        r_state = (r_state + 0.5) / (r_state + 0.5).sum(1, keepdims=True)
        _, place = np.unique(np.asarray(deaths["mun"].to_pylist(), dtype=str), return_inverse=True)
        counts = np.zeros((int(place.max()) + 1, 6))
        np.add.at(counts, (place, rec), 1.0)
        kappa = race_parameter("kappa")
        r = ((counts[place] + kappa * r_state[uf]) / (counts[place].sum(1, keepdims=True) + kappa))

    def pairs(mask):
        mask = mask & known
        return Pairs(dec[mask], rec[mask], uf[mask], age[mask], z[mask], w[mask], n_age,
                     None if phi is None else phi[mask], None if r is None else r[mask])

    return year, linked, pairs


def build(deaths: pa.Table, births: pa.Table, reference_births: pa.Table, *, settings: Any,
          validation: str, population: Population = INFANT, seed: int = 0, notes: tuple[str, ...] = (),
          scales: dict[str, float] | None = None, selection: tuple[list[int], list[int]] | None = None) -> Path:
    """Fit a race confusion model on the stored links and write it to the modelled tier.

    ``deaths``: every SIM death of the population in the fitted years, columns ``year``, ``uf`` (code),
    the population's age column (``age_days`` or ``age_years``), ``recorded`` (RACACOR code or null),
    ``mun`` (CODMUNRES), ``linked`` (bool), ``declared`` (the linked reference race code, null if
    unlinked or blank), optionally ``stratum`` (int: a class of the link's reliability that also
    drives linkability, entered in the linkage weights) and ``chance`` (the rate at which a death of its cell pairs by
    chance, measured by the link's negative control: with the death's own probability of being linked it gives the
    pair's share of false links, `_false_share`, ``Pairs.phi``). ``births``: SINASC births by
    (``mun``, ``race``, ``n``) that define the municipal composition. ``reference_births`` the same for
    the year the table is expressed on. ``selection`` = (train years, score years) of the scale selection, declared
    by the product; without it the first year is trained against the last and back. Needs the ``modelled`` extra.
    """
    from ..modelled import ModelledManifest, write_modelled  # noqa: PLC0415

    comp = composition(births)
    year, linked, pairs = prepare(deaths, comp, population)
    years = sorted(np.unique(year))
    mean_table: list[dict] = []
    if scales is None:
        # the declared selection, or one year against the other, both ways (the first and last years of a longer span)
        tables = []
        if selection is not None:
            folds = [(np.isin(year, selection[0]), np.isin(year, selection[1]))]
        else:
            folds = [(year == a, year == b) for a, b in
                     ([(years[0], years[-1]), (years[-1], years[0])] if len(years) > 1 else [(years[0], years[0])])]
        for tr, te in folds:
            _, t = select_scales(pairs(linked & tr), pairs(linked & te))
            tables.append(t)
        mean_table = [{**{n: r[n] for n in SCALE_NAMES}, "held_out_log_loss": float(np.mean([t[i]["held_out_log_loss"] for t in tables]))}
                      for i, r in enumerate(tables[0])]
        best = min(mean_table, key=lambda r: r["held_out_log_loss"])
        scales = {n: best[n] for n in SCALE_NAMES}
    model = fit(pairs(linked), scales, z_mean=comp.mean, z_sd=comp.sd, seed=seed, age_bands=population.age_bands,
                version=population.version)
    diag = model.diagnostics
    if diag["divergences"] > 0 or diag["max_rhat"] > 1.1:
        # a sampler that diverged (the women's check build of 2026-11-09: 800 of 800, one leapfrog step) describes nothing
        raise RuntimeError(f"{population.product}: the sampler did not converge, nothing written ({diag})")

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
        place="uf", strata=["age_band", "declared", "recorded"],
        inputs={f"link:{population.link}": "stored links, see lake/links",
                dataset_key("SIM.DO"): f"RACACOR, CODMUNRES, DTNASC, DTOBITO; years {years}", dataset_key("SINASC.DN"): "RACACOR, CODMUNRES (declared race, composition)"},
        validation=validation,
        notes=[f"{model.n_pairs} linked pairs weighted by inverse linkage probability; scales {scales}; diagnostics {model.diagnostics}",
               "p is C(recorded | declared) averaged over the state's municipalities by their births; draws.npz holds the parameter draws",
               "declared race is the reference declaration of the linked SINASC record; the Census self-declaration is assumed the same quantity",
               *notes])
    target = write_modelled(table, manifest, settings=settings)
    model.save(target / "draws.npz")
    (target / "scales_table.json").write_text(json.dumps(mean_table, indent=1), encoding="utf-8")
    return target


def held_out(deaths: pa.Table, births: pa.Table, population: Population, train: list[int], test: list[int], *,
             transported: dict[str, tuple[Fit, int]] | None = None, subsets: dict[str, np.ndarray] | None = None) -> dict[str, Any]:
    """How well the model fitted on the ``train`` years predicts the recorded colour of the linked pairs of the ``test``
    years, beside what it has to beat: one national matrix, a matrix per state, recorded = declared, and each
    ``transported`` fit (another population's product read at one of its age bands). Every candidate is scored under the
    link's contamination (``(1 - phi) C + phi r``), so the comparison is on what the pairs can show. Per candidate the
    mean log loss and the absolute error of the state x recorded counts as a share of the pairs (cells of five expected
    or more). The prior scales are chosen inside the training years (first half against second), never on the test.
    ``subsets`` (name -> a mask over ``deaths``) scores the fitted model on parts of the test pairs (a sex, an age band)
    against the national matrix of the same part of the training pairs: where a part's own matrix beats the model, the
    model misses something that part carries."""
    comp = composition(births)
    year, linked, pairs = prepare(deaths, comp, population)
    tr, te = pairs(linked & np.isin(year, train)), pairs(linked & np.isin(year, test))
    half = np.isin(year, train[:max(1, len(train) // 2)])
    scales, _ = select_scales(pairs(linked & np.isin(year, train) & half), pairs(linked & np.isin(year, train) & ~half))
    reg = region_of_uf()
    par = {k: np.asarray(v) for k, v in _effects(map_fit(tr, scales), scales, reg, np).items()}

    def model(pr: Pairs) -> np.ndarray:
        full = np.concatenate([np.zeros((len(pr.j), 1)), _logits(par, pr.j, pr.uf, reg, pr.age, pr.z, np)], axis=1)
        e = np.exp(full - full.max(1, keepdims=True))
        return e / e.sum(1, keepdims=True)

    def empirical(key: np.ndarray, pr: Pairs, n: int) -> np.ndarray:
        counts = np.zeros((n, 6, 6))
        np.add.at(counts, (key, pr.j, pr.k), pr.w)
        return (counts + 0.5) / (counts + 0.5).sum(2, keepdims=True)

    def score(prob: np.ndarray, pr: Pairs) -> dict[str, float]:
        prob = np.clip(prob, 1e-6, 1)
        prob = prob / prob.sum(1, keepdims=True)
        if pr.phi is not None and pr.r is not None:
            prob = (1 - pr.phi[:, None]) * prob + pr.phi[:, None] * pr.r
        expected, observed = np.zeros((len(UF_CODES), 6)), np.zeros((len(UF_CODES), 6))
        np.add.at(expected, pr.uf, prob * pr.w[:, None])
        np.add.at(observed, (pr.uf, pr.k), pr.w)
        cells = expected >= 5
        return {"log_loss": float(-np.average(np.log(prob[np.arange(len(pr.k)), pr.k]), weights=pr.w)),
                "count_error": float(np.abs(expected - observed)[cells].sum() / max(observed[cells].sum(), 1e-9))}

    national, by_state = empirical(np.zeros(len(tr.k), int), tr, 1)[0], empirical(tr.uf, tr, len(UF_CODES))
    out: dict[str, Any] = {"train": [int(y) for y in train], "test": [int(y) for y in test], "scales": scales,
                           "pairs": {"train": int(len(tr.k)), "test": int(len(te.k))},
                           "candidates": {"model": score(model(te), te), "one national matrix": score(national[te.j], te),
                                          "a matrix per state": score(by_state[te.uf, te.j], te),
                                          "recorded = declared": score(np.eye(6)[te.j], te)}}
    for name, (other, band) in (transported or {}).items():
        prob = confusion_row(other, te.j, te.uf, np.full(len(te.j), band, np.int8), te.z, np.arange(0, 200, 10)).mean(0)
        out["candidates"][f"transported: {name}"] = score(prob, te)
    for name, mask in (subsets or {}).items():
        a, b = pairs(linked & np.isin(year, train) & mask), pairs(linked & np.isin(year, test) & mask)
        if len(a.k) and len(b.k):
            own = empirical(np.zeros(len(a.k), int), a, 1)[0]
            out.setdefault("subsets", {})[name] = {"pairs": int(len(b.k)), "model": score(model(b), b)["log_loss"],
                                                   "national matrix": score(national[b.j], b)["log_loss"],
                                                   "the part's own matrix": score(own[b.j], b)["log_loss"]}
    return out


# --------------------------------------------------------------------------------------- the products' inputs
#
# What `pegasus-data model-build race_confusion_infant|race_confusion_women` assembles from the data home before it calls
# `build`: the deaths of the years declared in the product's ``inputs:`` (`curation/products.yml`) with the colour the linked
# birth declares, and the births by municipality and colour. Records come as role tables, links from the stored runs.

#: the race roles' labels (SIM ``deceased.race``, SINASC ``baby.race``/``mother.race``) to the RACACOR codes `encode_race` reads
RACE_LABEL_CODE = {"white": "1", "black": "2", "asian": "3", "brown": "4", "indigenous": "5"}


def _declaration(product: str) -> dict[str, Any]:
    from ..semantics.curation import products

    return dict((products().get(product) or {}).get("inputs") or {})


def _codes(labels: Any) -> list[str | None]:
    """Role labels of a race column to RACACOR codes; anything but the five colours is a blank (None)."""
    return [RACE_LABEL_CODE.get(v) for v in labels.to_pylist()]


def _residence(settings: Any, dataset: str, role: str, table: pa.Table, ids: list[str], year: int) -> pa.Array:
    """The residence role of ``table`` as text, a null filled from the column the role is read from: the role leaves out the
    state's "ignored" municipality (xx0000), whose deaths and births still belong to their state (a null's UF is unknown)."""
    import pyarrow.compute as pc

    from .. import query
    from ..linkage.identity import record_ids
    from ..semantics.column_roles import column_of

    value = table[role].cast(pa.string())
    gaps = pc.is_null(value)
    if not pc.any(gaps).as_py():
        return value
    column = column_of(dataset, role)
    raw = cast("pa.Table", query(dataset, period=year, geography="BR", select=[column], present="codes", provenance="all", root=settings.root))
    found = dict(zip(record_ids(raw).to_pylist(), raw[column].cast(pa.string()).to_pylist(), strict=True))
    return pa.array([v if v is not None else found.get(i) for v, i in zip(value.to_pylist(), ids, strict=True)], pa.string())


def births_by_race(settings: Any, years: list[int]) -> pa.Table:
    """SINASC births of ``years`` by the mother's residence (``mun``) and the baby's colour code (``race``, null if blank):
    the municipal composition, and the year the product is expressed on. Columns ``mun``, ``race``, ``n``."""
    from ..linkage.identity import record_ids
    from ..linkage.roles import role_table

    parts = []
    for year in years:
        t = role_table("SINASC-DN", period=year, geography="BR", roles=["mother.residence", "baby.race"], root=settings.root)
        mun = _residence(settings, "SINASC-DN", "mother.residence", t, record_ids(t).to_pylist(), year)
        parts.append(pa.table({"mun": mun, "race": pa.array(_codes(t["baby.race"]), pa.string())}))
    g = pa.concat_tables(parts).group_by(["mun", "race"]).aggregate([([], "count_all")])
    return g.select(["mun", "race", "count_all"]).rename_columns(["mun", "race", "n"])


def _stored_pairs(settings: Any, name: str, year: int, notes: list[str]) -> tuple[pa.Table, dict[str, Any]]:
    """A probabilistic link's stored pairs for ``year``. A run stored before fingerprints existed reads as stale; it is used
    (the link takes hours and is not this build's to rerun) and the reason goes into the manifest's notes."""
    from ..linkage import engine, store

    key = engine.stored_key(name, engine.link_method(name), year, "BR")
    found = store.load(settings, key, allow_stale=True)
    if found is None:
        raise FileNotFoundError(f"{name} for {year} is not stored ({key.stem}): run the link first (`pegasus-data link {name}`)")
    pairs, report = found
    if report.get("stale"):
        notes.append(f"link {name} {year} ({key.stem}): stored run read although {report['stale']}")
    return pairs, report


def infant_deaths(settings: Any, name: str, years: list[int], notes: list[str]) -> pa.Table:
    """Every SIM death before one year of age in ``years`` (the link's own left side): the colour code recorded, the age in
    days, the residence, whether the stored link found its birth, and the colour that birth declares."""
    import pyarrow.compute as pc

    from ..linkage import engine
    from ..linkage.identity import record_ids
    from ..linkage.roles import role_table

    spec = engine.load_links()[name]
    out = []
    for year in years:
        pairs, report = _stored_pairs(settings, name, year, notes)
        left = role_table(spec.left.dataset, period=year, geography="BR", where=spec.left.where, root=settings.root,
                          roles=["deceased.race", "deceased.residence", "deceased.birth_date", "death.date"])
        right = role_table(spec.right.dataset, period=engine.padded_period(year, spec.right), geography="BR",
                           roles=["baby.race"], root=settings.root)
        if left.num_rows != report["left_records"]:
            raise ValueError(f"{name} {year}: the stored run linked {report['left_records']} deaths, the data now holds {left.num_rows}")
        declared = dict(zip(record_ids(right).to_pylist(), _codes(right["baby.race"]), strict=True))
        partner = dict(zip(pairs["l"].to_pylist(), pairs["r"].to_pylist(), strict=True))
        lid = record_ids(left).to_pylist()
        residence = _residence(settings, spec.left.dataset, "deceased.residence", left, lid, year)
        out.append(pa.table({
            "year": pa.array([year] * left.num_rows, pa.int64()),
            "uf": pc.cast(pc.utf8_slice_codeunits(residence, 0, 2), pa.int64()),
            "age_days": pc.days_between(left["deceased.birth_date"], left["death.date"]).cast(pa.int64()),
            "recorded": pa.array(_codes(left["deceased.race"]), pa.string()),
            "mun": residence,
            "linked": pa.array([i in partner for i in lid], pa.bool_()),
            "declared": pa.array([declared.get(partner.get(i)) for i in lid], pa.string()),
        }))
    return pa.concat_tables(out)


def _false_share(chance: Any, found: Any) -> Any:
    """The probability that a found pair is false, from the ``chance`` rate c at which a record of its cell pairs with an
    unrelated partner (the pairs the moved key makes, per record) and the probability f that such a record is ``found``
    paired at all. A record with a true partner (probability t) pairs with it, one without pairs by chance: f = t +
    (1 - t) c, so the false pairs are (1 - t) c = c (1 - f) / (1 - c) of the records and that over f of the pairs.
    ``found`` is a cell's linked share or one record's fitted probability (`link_weights`): a group that links more
    often at the same chance rate (Indígena deaths: 35% against 17%) has fewer false pairs. Capped at 0.95."""
    chance, found = np.asarray(chance, dtype=float), np.asarray(found, dtype=float)
    return np.minimum(chance * (1 - found) / np.maximum((1 - chance) * found, 1e-12), 0.95)


def _pass_and_control(con: Any, spec: Any, shifts: list[int],
                      keep: str = "TRUE") -> tuple[pa.Table, dict[int, dict[tuple[int, int], int]]]:
    """The first pass of a keyed link over the prepared sides ``L`` and ``R``, and its negative control read by size and
    age. The caller has made ``lpop`` (one row per left record: ``l``, ``mun``, ``uf``, ``age``, ``rec`` and whatever
    else it wants back), ``ng`` (``mun``, ``ng``: the partners a municipality holds, on which chance agreement grows)
    and ``rr`` (``r``, ``declared``: the partner's colour). ``keep`` is a condition a pair must meet (over ``l.*``,
    ``r.*``), applied to the control too. Returns every left record with ``ng``, ``linked`` and ``declared``, and the
    pairs the same keys make when the control role is moved by each of ``shifts`` days round the shared range
    (`placebo.rotation`), as ``{shift: {(ng, age): pairs}}``."""
    from ..linkage import engine, placebo

    con.execute("CREATE TEMP TABLE linked(l VARCHAR, r VARCHAR, pass VARCHAR)")
    keys = spec.passes[0].keys
    con.execute(f"""CREATE TEMP TABLE real AS SELECT p.l, p.r FROM ({engine._join(keys, {})}) p JOIN L l ON l._id = p.l
                    JOIN R r ON r._id = p.r WHERE {keep}""")
    control = sorted({k for p in spec.passes for k in p.keys if k[0] == spec.control_role})
    controls: dict[int, dict[tuple[int, int], int]] = {}
    for d in shifts:
        moved = {k: sql for k in control if (sql := placebo.rotation(k[0], placebo.shared_range(con, [k[0]], [k[1]]), d))}
        con.execute("CREATE OR REPLACE TEMP TABLE ctl AS " + engine._join(keys, moved))
        rows = con.execute(f"""SELECT coalesce(ng.ng, 0), coalesce(CAST(lpop.age AS INTEGER), -1), count(*) FROM (SELECT c.l
                               FROM ctl c JOIN L l ON l._id = c.l JOIN R r ON r._id = c.r WHERE {keep}) c JOIN lpop USING (l)
                               LEFT JOIN ng USING (mun) GROUP BY 1, 2""").fetchall()
        controls[d] = {(int(a), int(b)): int(n) for a, b, n in rows}
    out = con.execute("""SELECT lpop.*, coalesce(ng.ng, 0) AS ng, real.r IS NOT NULL AS linked, rr.declared
                         FROM lpop LEFT JOIN ng USING (mun) LEFT JOIN real USING (l) LEFT JOIN rr ON rr.r = real.r""").to_arrow_table()
    return out, controls


def _women_year(settings: Any, name: str, year: int, first_year: int, shifts: list[int],
                log: Any) -> tuple[pa.Table, dict[int, dict[tuple[int, int], int]]]:
    """One death year of the women's link: every eligible death with the mother groups of its municipality (``ng``), the
    partner mother's colour where the spec's pass finds one (a partner born after the death is no partner: the spec's
    validation), and the control read per municipality size: the pairs the same keys make when the death's birth date is
    moved by each of ``shifts`` days round the shared range (`placebo.rotation`), as ``{shift: {ng: pairs}}``. The births
    are those of ``first_year`` to ``year``. The pass is run here, not read from `engine.link`: with 85-90% of its pairs
    reproduced by the control the engine drops the pass (``chance_drop``) and stores none, while this product keeps the
    pairs and prices their false share by municipality size."""
    import time

    from ..linkage import engine
    from ..linkage.identity import connect

    t0 = time.time()
    spec = engine.load_links()[name]
    period = (str(first_year), str(year))
    left = engine._side_table(spec.left, sorted({*engine._roles_needed(spec, "left"), "deceased.race"}), period=year,
                              geography="BR", root=settings.root)
    right = engine._side_table(spec.right, sorted({*engine._roles_needed(spec, "right"), "mother.race"}), period=period,
                               geography="BR", root=settings.root)
    con = connect()
    engine._prepare(con, "L", left, spec.left)
    engine._prepare(con, "R", right, spec.right)
    del left, right
    keep = next(v.sql for v in spec.validations if v.sql)           # death on or after the latest birth
    con.execute('CREATE TEMP TABLE ng AS SELECT "mother.residence" AS mun, count(*) AS ng FROM R GROUP BY 1')
    con.execute("""CREATE TEMP TABLE lpop AS SELECT _id AS l, "deceased.residence" AS mun, "deceased.age_years" AS age,
                   "deceased.race" AS rec, substr("deceased.residence", 1, 2) AS uf FROM L""")
    con.execute('CREATE TEMP TABLE rr AS SELECT DISTINCT ON (_id) _id AS r, "mother.race" AS declared FROM R')
    out, controls = _pass_and_control(con, spec, shifts, keep)
    log(f"{name} {year}: {out.num_rows} deaths, {sum(out['linked'].to_pylist())} linked, {round(time.time() - t0)} s")
    return out, controls


def women_deaths(settings: Any, name: str, years: list[int], decl: dict[str, Any], log: Any) -> pa.Table:
    """The women's deaths table of ``build``: the recorded colour and the partner mother's, whether linked, the death's
    municipality class (``stratum``: the mother groups the births hold, by ``class_edges``) and ``chance``, the rate at which
    a death of its (year, class) pairs by chance: the control's pairs (mean over the declared shifts) per death. `prepare`
    turns it into each pair's share of false links. Classes up to ``max_class``."""
    import pyarrow.compute as pc

    edges, max_class = np.asarray(decl["class_edges"]), int(decl["max_class"])
    parts = []
    for year in years:
        t, controls = _women_year(settings, name, year, int(decl["births_from"]), [int(s) for s in decl["control_shifts"]], log)
        t = t.filter(pc.is_valid(t["uf"]))
        klass = np.digitize(np.asarray(t["ng"].to_numpy(zero_copy_only=False)), edges)
        chance_of = {}
        for c in range(max_class + 1):
            n_c = int((klass == c).sum())
            if n_c == 0:
                continue
            p = sum(n for shift in controls.values() for (ng, _age), n in shift.items()
                    if int(np.digitize(ng, edges)) == c) / len(controls)
            chance_of[c] = p / n_c
        mask = pa.array(klass <= max_class)
        t = t.filter(mask)
        k = klass[klass <= max_class]
        parts.append(pa.table({
            "chance": [chance_of.get(int(c), 0.0) for c in k], "year": np.full(len(k), year, dtype=np.int64),
            "uf": pc.cast(t["uf"], pa.int64()), "age_years": t["age"],
            "recorded": pa.array([RACE_LABEL_CODE.get(v) for v in t["rec"].to_pylist()], pa.string()),
            "mun": t["mun"], "linked": t["linked"],
            "declared": pa.array([RACE_LABEL_CODE.get(v) for v in t["declared"].to_pylist()], pa.string()),
            "stratum": k.astype(np.int64)}))
    return pa.concat_tables(parts)


def _own_birth_cohort(settings: Any, spec: Any, born: int, deaths: pa.Table, shifts: list[int],
                      log: Any) -> tuple[pa.Table, dict[int, dict[tuple[int, int], int]]]:
    """One birth cohort of the own-birth link: the eligible deaths of people born in ``born`` (``deaths``, the left side's
    role table) against that year's births. A municipality's ``ng`` is its births of the year: the chance that another
    child of the same sex was born there on the same day grows with it. The pass is run here for the reason `_women_year`
    gives (the engine drops a pass its control reproduces), and by cohort because a death year's partners span every
    birth year of its ages, which no one read holds."""
    import time

    import pyarrow.compute as pc

    from ..linkage import engine
    from ..linkage.identity import connect

    t0 = time.time()
    left = deaths.filter(pc.equal(pc.year(deaths["deceased.birth_date"]), born))
    right = engine._side_table(spec.right, sorted({*engine._roles_needed(spec, "right"), "baby.race"}), period=born,
                               geography="BR", root=settings.root)
    con = connect()
    engine._prepare(con, "L", left, spec.left)
    engine._prepare(con, "R", right, spec.right)
    del left, right
    con.execute('CREATE TEMP TABLE ng AS SELECT "mother.residence" AS mun, count(*) AS ng FROM R GROUP BY 1')
    con.execute("""CREATE TEMP TABLE lpop AS SELECT _id AS l, "deceased.residence" AS mun, "deceased.age_years" AS age,
                   "deceased.race" AS rec, substr("deceased.residence", 1, 2) AS uf, "deceased.sex" AS sex,
                   year("death.date") AS year FROM L""")
    con.execute('CREATE TEMP TABLE rr AS SELECT DISTINCT ON (_id) _id AS r, "baby.race" AS declared FROM R')
    out, controls = _pass_and_control(con, spec, shifts)
    log(f"{spec.name} born {born}: {out.num_rows} deaths, {sum(out['linked'].to_pylist())} linked, {round(time.time() - t0)} s")
    return out, controls


def own_birth_deaths(settings: Any, population: Population, years: list[int], decl: dict[str, Any], log: Any) -> pa.Table:
    """The deaths table of ``build`` for a population linked to its own birth record: every death of ``years`` up to
    ``max_age`` of a person born in ``births_from`` to ``births_to`` (the cohorts whose birth record declares the same
    thing: see the product), the colour recorded and the colour the linked birth declares, the class of the municipality
    (``stratum``: its births in the person's birth year, by ``class_edges``; classes up to ``max_class``), and ``chance``,
    the rate at which a death of its (class, age band) pairs by chance over every cohort: the control's pairs per death.
    `prepare` turns it into each pair's share of false links. Carries ``sex`` as well."""
    import pyarrow.compute as pc

    from ..linkage import engine

    spec = engine.load_links()[population.link]
    edges, max_class = np.asarray(decl["class_edges"]), int(decl["max_class"])
    shifts = [int(s) for s in decl["control_shifts"]]
    last_cohort = min(int(decl.get("births_to") or years[-1]), years[-1] - 1)
    roles = sorted({*engine._roles_needed(spec, "left"), *engine.where_roles(spec.left), "deceased.race", "death.date"})
    deaths = engine._side_table(spec.left, roles, period=(str(years[0]), str(years[-1])), geography="BR", root=settings.root)
    deaths = deaths.filter(pc.less_equal(deaths["deceased.age_years"], int(decl["max_age"])))
    parts, control = [], np.zeros((len(edges) + 1, len(population.age_bands)))
    for born in range(int(decl["births_from"]), last_cohort + 1):
        t, controls = _own_birth_cohort(settings, spec, born, deaths, shifts, log)
        for shift in controls.values():
            for (ng, age), n in shift.items():
                b = int(population.band(np.array([age]))[0])
                if b >= 0:
                    control[int(np.digitize(ng, edges)), b] += n / len(controls)
        parts.append(t)
    t = pa.concat_tables(parts)
    t = t.filter(pc.is_valid(t["uf"]))
    klass = np.digitize(np.asarray(t["ng"].to_numpy(zero_copy_only=False)), edges)
    band = population.band(np.asarray(t["age"].to_numpy(zero_copy_only=False), dtype=float))
    chance = np.zeros(t.num_rows)
    for c in range(max_class + 1):
        for b in range(len(population.age_bands)):
            cell = (klass == c) & (band == b)
            if cell.any():
                chance[cell] = control[c, b] / cell.sum()
    keep = (klass <= max_class) & (band >= 0)
    t = t.filter(pa.array(keep))
    return pa.table({
        "chance": chance[keep], "year": pc.cast(t["year"], pa.int64()), "uf": pc.cast(t["uf"], pa.int64()), "age_years": t["age"],
        "recorded": pa.array([RACE_LABEL_CODE.get(v) for v in t["rec"].to_pylist()], pa.string()),
        "mun": t["mun"], "linked": t["linked"],
        "declared": pa.array([RACE_LABEL_CODE.get(v) for v in t["declared"].to_pylist()], pa.string()),
        "stratum": klass[keep].astype(np.int64), "sex": t["sex"]})


def _build_product(population: Population, settings: Any, version: str, validation: str, log: Any) -> dict[str, Any]:
    from dataclasses import replace

    from ..fields import _years

    decl = _declaration(population.product)
    years = _years(decl["years"])
    notes: list[str] = []
    if population is INFANT:
        deaths = infant_deaths(settings, population.link, years, notes)
    elif population is CHILD:
        deaths = own_birth_deaths(settings, population, years, decl, log)
        notes += [f"links: the pass of {population.link} run one birth cohort at a time over the births of {decl['births_from']} "
                  f"on; only municipalities with fewer than {int(decl['class_edges'][int(decl['max_class'])])} births in the "
                  f"person's birth year (class <= {decl['max_class']}) are used; pairs carry the measured share of false links phi "
                  "of their class and age band (negative control), entered in the likelihood as (1 - phi) C + phi r(municipality)",
                  "population: deaths at ages 1-14 of children born in the years read who died resident in the municipality their "
                  "mother lived in at the birth",
                  "reference: the colour on the birth record, which from the 2011 form on is the mother's own declaration (the "
                  "infant product's reference); births before 2012 declare the newborn's colour on the old form and are not read"]
    else:
        deaths = women_deaths(settings, population.link, years, decl, log)
        notes += [f"links: runs of {population.link}, one per death year, over the births {decl['births_from']} to that year; only "
                  f"municipalities with fewer than {int(decl['class_edges'][int(decl['max_class'])])} mother groups (class <= "
                  f"{decl['max_class']}) are used; pairs carry the measured share of false links phi (negative control), entered in "
                  "the likelihood as (1 - phi) C + phi r(municipality)",
                  "population: women dying aged 15-49 who were mothers of a SINASC birth in the years read and kept their municipality; "
                  "transport to women who never gave birth, to men and to older ages is not validated"]
    log(f"{population.product}: {deaths.num_rows} deaths, {sum(deaths['linked'].to_pylist())} linked, years {years}")
    sel = decl.get("scale_selection")
    selection = None if sel is None else (_years(sel["train"]), _years(sel["score"]))
    target = build(deaths, births_by_race(settings, _years(decl["composition_years"])),
                   births_by_race(settings, [int(decl["reference_year"])]), settings=settings, validation=validation,
                   population=replace(population, version=version), notes=tuple(notes), selection=selection)
    return {"product": population.product, "version": version, "path": str(target), "deaths": deaths.num_rows}


def build_infant_product(settings: Any, *, version: str, validation: str, log: Any = print) -> dict[str, Any]:
    """``model-build race_confusion_infant``: the infant deaths with the colour of their linked birth, then `build`."""
    return _build_product(INFANT, settings, version, validation, log)


def build_child_product(settings: Any, *, version: str, validation: str, log: Any = print) -> dict[str, Any]:
    """``model-build race_confusion_child``: deaths at ages 1-14 with the colour their own birth record declares, then `build`."""
    return _build_product(CHILD, settings, version, validation, log)


def build_women_product(settings: Any, *, version: str, validation: str, log: Any = print) -> dict[str, Any]:
    """``model-build race_confusion_women``: women's deaths with the colour their mother's birth record declares, then `build`."""
    return _build_product(WOMEN, settings, version, validation, log)
