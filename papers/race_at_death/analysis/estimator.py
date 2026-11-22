# ruff: noqa: F405 - the names come from common
"""The numbers of paper 6 (the estimator) that results.py does not hold: both validations with the variance linearised over
municipalities (`modelled_race.candidate_estimates`), the second validation pair (admissions that ended in death against
their certificates, `analysis/pair.py`), and the rate ratios' variance with their denominator; and (review 2) the estimator on exactly the linked and the unlinked units, with the key date shifted
(placebo), by sex, with the control scaled by state and nation, three comparators, who shares the key (A1), and the births' dispersion and the
classification's heterogeneity that the simulation takes from the data.

    python papers/race_at_death/analysis/estimator.py   -> results/estimator.json   (a few minutes; sections 4-6 need data/infant_units.parquet and
    data/key_cache/* from analysis/infant_findable.py and `analysis/pair.py units`)
"""
import json

import pyarrow.parquet as pq
from common import *  # noqa: F403 - con, RACES, NAME, SIZES, births, muns, BIDX, LL, link_matrix, DATA, PAPER

from pegasus_data.studies import modelled_race as mr

OUT: dict = {}
COLS = [*RACES, "other"]
APPROX: set = set()


def arrays(table, where="TRUE", years=None, ages=None):
    """Per municipality: candidates less control T (M, 4, 5), candidates plus control V, deaths, and (``years``, ``ages``
    given) person-years by the mother's declared class from the births of the cohorts exposed, the control C, the cells'
    model and chance variances (the counts' columns v and w, ADR-0233) and the candidates alone (no control)."""
    names = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
    v, w = ("v", "w") if "v" in names else ("n", "n")       # a table counted before the columns: one unit a key, scale one
    APPROX.add(table) if v == "n" else None
    rows = con.execute(f"""SELECT mun, declared, recorded, sum(n) FILTER (control = false), sum(n) FILTER (control),
                                  sum({v}) FILTER (control = false), sum({v}) FILTER (control), sum({w}) FILTER (control)
                           FROM {table} WHERE control IS NOT NULL AND ({where}) GROUP BY ALL""").fetchall()
    dead = dict(con.execute(f"SELECT mun, sum(n) FROM {table} WHERE control IS NULL AND ({where}) GROUP BY 1").fetchall())
    ids = sorted({r[0] for r in rows} | set(dead))
    at = {m: i for i, m in enumerate(ids)}
    T, V, C, VM, VC, A = (np.zeros((len(ids), 4, 5)) for _ in range(6))
    D = np.zeros(len(ids))
    for m, j, k, real, ctl, vr, vc, wc in rows:
        if j in RACES:
            c = RACES.index(k) if k in RACES else 4
            T[at[m], RACES.index(j), c] += (real or 0) - (ctl or 0)
            V[at[m], RACES.index(j), c] += (real or 0) + (ctl or 0)
            C[at[m], RACES.index(j), c] += ctl or 0
            VM[at[m], RACES.index(j), c] += (vr or 0) + (vc or 0)
            VC[at[m], RACES.index(j), c] += (vc or 0) + (wc or 0)
            A[at[m], RACES.index(j), c] += real or 0
    for m, n in dead.items():
        D[at[m]] = n
    E = None
    if years is not None:
        pos = {str(int(x)): i for i, x in enumerate(muns)}
        E = np.zeros((len(ids), 4))
        for y in years:
            for a in ages:
                if 2012 <= y - a <= 2023:
                    b = births[y - a - 2012][:, BIDX]
                    for m, i in at.items():
                        if m in pos:
                            E[i] += b[pos[m]]
    return T, V, D, E, C, VM, VC, A


def summary(est, cells=((0, 0), (1, 1), (1, 2), (2, 2), (2, 0), (3, 3))):
    return {f"{NAME[RACES[a]]}|{NAME[RACES[b]]}": e(est["p"][a, b], est["p_se"][a, b], se_poisson=float(est["p_se_poisson"][a, b]),
                                                    se_chance=float(est["p_se_chance"][a, b]), se_model=float(est["p_se_model"][a, b])) for a, b in cells}


def estimate(table, where="TRUE", years=None, ages=None, ref=0):
    """The estimator with its errors, and as a baseline the candidates without the control (``p_nocontrol``)."""
    T, V, D, E, C, VM, VC, A = arrays(table, where, years, ages)
    est = mr.candidate_estimates(T, V, D, E, ref=ref, control=C, var_model=VM, var_chance=VC)
    a = A.sum(0)
    est["p_nocontrol"] = a / a.sum(1, keepdims=True)
    return est, len(D)


def compare(est, truth):
    """Every cell of the 4 x 5 matrix: the candidates' estimate less the linked answer, in units of each standard error."""
    d, d0, out = [], [], {"cells": 0, "outside_cluster": 0, "outside_poisson": 0, "outside_chance": 0, "outside_model": 0}
    for a, j in enumerate(RACES):
        if NAME[j] not in truth["rows"] or truth["rows"][NAME[j]].get("n", 0) < 30:
            continue
        for b, k in enumerate(COLS):
            diff = est["p"][a, b] - truth["rows"][NAME[j]][NAME.get(k, "other")]["est"]
            d.append(abs(diff))
            out["cells"] += 1
            out["outside_cluster"] += int(abs(diff) > 1.96 * est["p_se"][a, b])
            out["outside_poisson"] += int(abs(diff) > 1.96 * est["p_se_poisson"][a, b])
            out["outside_chance"] += int(abs(diff) > 1.96 * est["p_se_chance"][a, b])
            out["outside_model"] += int(abs(diff) > 1.96 * est["p_se_model"][a, b])
            d0.append(abs(est["p_nocontrol"][a, b] - truth["rows"][NAME[j]][NAME.get(k, "other")]["est"]))
    return out | {"mean_abs_diff": float(np.mean(d)), "max_abs_diff": float(np.max(d)),
                  "nocontrol_mean_abs_diff": float(np.mean(d0)), "nocontrol_max_abs_diff": float(np.max(d0)),
                  "se_ratio_median": float(np.nanmedian(est["p_se"] / est["p_se_poisson"])),
                  "chance_ratio_median": float(np.nanmedian(est["p_se_chance"] / est["p_se_poisson"])),
                  "model_ratio_median": float(np.nanmedian(est["p_se_model"] / est["p_se_poisson"]))}


def full(est, truth):
    """The whole 4 x 5 matrix of the estimate, its two errors and the known answer, for the figures (rows with fewer than 30 known pairs: null)."""
    known = [[truth["rows"][NAME[j]][NAME.get(k, "other")]["est"] for k in COLS] if truth["rows"].get(NAME[j], {}).get("n", 0) >= 30 else None for j in RACES]
    return {"p": est["p"].tolist(), "p_se": est["p_se"].tolist(), "p_se_chance": est["p_se_chance"].tolist(), "p_se_model": est["p_se_model"].tolist(),
            "truth": known}


# ------------------------------------------------------------------ 1. infants: candidates against the one-to-one linkage, by size
# the linked pairs whose birth record shares the estimator's key (analysis/infant_findable.py), in the linkage's row order
F = pq.read_table(DATA / "infant_findable.parquet").to_pandas()
assert len(F) == len(L) and (F.year.to_numpy() == L.year.to_numpy()).all(), "infant_findable.parquet is not aligned with the linkage"
L["findable"] = F.findable.to_numpy()
LF = L[L.findable & L.dec.isin(RACES)]
OUT["infants"] = []
for lo, hi, label in [*SIZES, (0, 25600, "<25,600"), (0, 10**9, "all")]:
    est, _ = estimate("infants", f"births >= {lo} AND births < {hi}")
    sel = (LL.births_year >= lo) & (LL.births_year < hi)
    link, linkf = link_matrix(LL[sel]), link_matrix(LF[(LF.births_year >= lo) & (LF.births_year < hi)])
    deaths = L[(L.births_year >= lo) & (L.births_year < hi)]
    OUT["infants"].append({"size": label, "municipalities": int(con.execute(f"SELECT count(DISTINCT mun) FROM infants WHERE births >= {lo} AND births < {hi}").fetchone()[0]),
                           "found": e(est["found"], est["found_se"], se_chance=float(est["found_se_chance"])), "cells": summary(est), "against_linkage": compare(est, link),
                           "against_findable": compare(est, linkf), "linked_share": float(deaths.linked.mean()), "findable_share": float(deaths.findable.mean()),
                           "full": full(est, link), "full_findable": full(est, linkf)})
OUT["infants_births_share"] = {"below_25600": float(comp.loc[comp.births_year < 25600, "births_year"].sum() / comp.births_year.sum())}

# ------------------------------------------------------------------ 2. the second pair: admissions that ended in death to their certificates
PSIZES = [(0, 100, "<100"), (100, 400, "100-399"), (400, 1600, "400-1,599"), (1600, 6400, "1,600-6,399"), (6400, 10**9, ">=6,400")]
for scale in ("mun", "uf"):
    con.execute(f"CREATE OR REPLACE TABLE pair_{scale} AS SELECT * FROM '{(DATA / f'pair_counts_{scale}.parquet').as_posix()}'")
con.execute(f"""CREATE OR REPLACE TABLE pair_truth AS SELECT t.*, s.births FROM '{(DATA / 'pair_truth.parquet').as_posix()}' t
                LEFT JOIN (SELECT DISTINCT born AS year, mun, births FROM pair_mun WHERE control IS NULL) s USING (year, mun)""")
years = [int(y) for y, in con.execute("SELECT DISTINCT year FROM pair_truth ORDER BY 1").fetchall()]


def truth_matrix(where):
    m = {"pairs": 0, "rows": {}}
    rows = con.execute(f"SELECT declared, recorded, count(*) FROM pair_truth WHERE {where} GROUP BY ALL").fetchall()
    for j in RACES:
        tot = sum(n for a, _, n in rows if a == j)
        if tot:
            m["rows"][NAME[j]] = {NAME.get(k, "other"): e(sum(n for a, b, n in rows if a == j and (b == k or (k == "other" and b not in RACES))) / tot) for k in COLS}
            m["rows"][NAME[j]]["n"] = int(tot)
            m["pairs"] += tot
    return m


units = con.execute("SELECT count(*), sum(linked::INT), sum(findable::INT) FROM pair_truth").fetchone()
OUT["pair"] = {"years": years, "units": int(units[0]), "linked": int(units[1]), "findable": int(units[2]), "by_size": [],
               "colour_known": {side: float(con.execute(f"SELECT avg(coalesce({col} IN ('white','black','brown','indigenous','asian'), false)::INT) FROM pair_truth WHERE linked").fetchone()[0])
                                for side, col in (("admission", "recorded"), ("certificate", "declared"))}}   # a missing colour counts as unknown (NULL IN (...) is NULL and avg skipped it)
for lo, hi, label in [*PSIZES, (0, 10**9, "all")]:
    w = f"births >= {lo} AND births < {hi}"
    block = {"size": label, "municipality_years": int(con.execute(f"SELECT count(*) FROM (SELECT DISTINCT born, mun FROM pair_mun WHERE control IS NULL AND {w})").fetchone()[0])}
    chance = con.execute(f"SELECT sum(n) FILTER (control), sum(n) FILTER (control IS NULL) FROM pair_mun WHERE {w}").fetchone()
    block["chance_per_unit"] = float(chance[0] / chance[1])
    for scale in ("mun", "uf"):
        est, _ = estimate(f"pair_{scale}", w)
        block[scale] = {"found": e(est["found"], est["found_se"], se_chance=float(est["found_se_chance"])), "cells": summary(est)}
        tl, tf = truth_matrix(f"linked AND {w}"), truth_matrix(f"findable AND {w}")
        block[scale]["against_linked"], block[scale]["against_findable"] = compare(est, tl), compare(est, tf)
        block[scale]["full_linked"], block[scale]["full_findable"] = full(est, tl), full(est, tf)
    block["linked"], block["findable"] = tl, tf
    block["linked_share"] = float(con.execute(f"SELECT avg(linked::INT) FROM pair_truth WHERE {w}").fetchone()[0])
    block["findable_share"] = float(con.execute(f"SELECT avg(findable::INT) FROM pair_truth WHERE {w}").fetchone()[0])
    OUT["pair"]["by_size"].append(block)
# the stored link's own quality, year by year (its report beside the pairs)
from pegasus_data.linkage import store  # noqa: E402

OUT["pair"]["link_quality"] = {}
for y in years:
    rep = json.loads(sorted((store.links_dir(settings) / "sih_deaths_to_sim").glob(f"probabilistic_BR_{y}_*.json"), key=lambda f: f.stat().st_mtime)[-1].read_text(encoding="utf-8"))
    OUT["pair"]["link_quality"][y] = {"fdr_percent": rep["estimated_fdr_percent"], "fdr_upper95_percent": rep["fdr_upper95_percent"],
                                      "linked_share": rep["linked_share"], "died_in_hospital": rep["validations"]["died in hospital"]["agreement_percent"]}
# assumption A2 in a register of deaths: the composition by race and the number of the two sexes at the same age (certificates of one year)
from pegasus_data.linkage import engine  # noqa: E402

spec = engine.load_links()["sih_deaths_to_sim"]
reg = engine._side_table(spec.right, ["deceased.sex", "deceased.race", "deceased.age_years"], period=2019, geography="BR", root=settings.root)
con.register("reg", reg)
OUT["pair"]["register_by_sex"] = {f"{a}|{s_}": {"deaths": int(n), "white": float(w), "brown": float(br), "black": float(bl)} for a, s_, n, w, br, bl in con.execute("""
    SELECT CASE WHEN "deceased.age_years" BETWEEN 15 AND 29 THEN '15-29' WHEN "deceased.age_years" >= 60 THEN '60+' ELSE 'other' END, "deceased.sex", count(*),
           avg(("deceased.race" = 'white')::INT), avg(("deceased.race" = 'brown')::INT), avg(("deceased.race" = 'black')::INT)
    FROM reg WHERE "deceased.sex" IN ('M', 'F') GROUP BY 1, 2""").fetchall()}
# what the found are: the linked units whose certificate does not share their birth date, sex and residence, against those that do
OUT["pair"]["unfindable"] = truth_matrix("linked AND NOT findable")

# ------------------------------------------------------------------ 3. the rate ratios by the mother's race with the denominator's variance
OUT["ratios"] = {}
for label, lo, hi in (("1-4", 1, 4), ("5-9", 5, 9), ("1-9", 1, 9)):
    for where, tag in ((f"age BETWEEN {lo} AND {hi}", "all"), (f"age BETWEEN {lo} AND {hi} AND births_year < 25600", "below_25600")):
        est, n_mun = estimate("children", where, range(2013, 2025), range(lo, hi + 1), ref=2)
        OUT["ratios"][f"{label}|{tag}"] = {NAME[RACES[i]]: e(est["ratio"][i], est["ratio_se"][i], se_poisson=float(est["ratio_se_poisson"][i]),
                                                             se_chance=float(est["ratio_se_chance"][i])) for i in (0, 1, 3)} | {
            "found": e(est["found"], est["found_se"]), "municipalities": int(n_mun)}

# ------------------------------------------------------------------ 4. like for like, placebo, comparators (review 2, section 5)
# The estimator is run on exactly the units whose answer is known (the linked), and on the others; with the key date shifted (placebo); on boys and on
# girls; with the control scaled within the state or the nation; and three comparators on the same units: the unique-key link, the uniform attribution
# (1/c to each of c candidates) and Goodman's regression of the deaths of a class on the births of each class over the key cells. Everything is
# counted here from the units (data/infant_units.parquet, data/key_cache/*), so that deaths sharing a key cell are counted together whatever their
# class and the covariances of the cells of a row are in the variance (`exact`; the package's `v` column groups by class, age, cause and year).
import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

KC = DATA / "key_cache"
rk = duckdb.connect()
rk.execute("PRAGMA disable_progress_bar; SET memory_limit='1500MB'; SET threads=3")
SCALES = {"mun": "{m}", "uf": "substr({m}, 1, 2)", "br": "'BR'"}
VARIANTS = {"all": ("TRUE", 0, "mun"), "linked": ("linked", 0, "mun"), "unlinked": ("NOT linked", 0, "mun"), "findable": ("findable", 0, "mun"),
            "boys": ("sex = 'M'", 0, "mun"), "girls": ("sex = 'F'", 0, "mun"), "scale_uf": ("TRUE", 0, "uf"), "scale_br": ("TRUE", 0, "br"),
            **{f"shift{s:+d}": ("TRUE", s, "mun") for s in (-14, -7, 7, 14)}}
RL = ", ".join(f"'{r}'" for r in RACES)
SEX = (("M", "m"), ("F", "f"))
BPIV = ", ".join([f"coalesce(sum(n) FILTER (sex = '{sx}' AND j = '{c}'), 0) AS b{t}{i}" for sx, t in SEX for i, c in enumerate(RACES)]
                 + [f"coalesce(sum(n) FILTER (sex = '{sx}'), 0) AS bt{t}" for sx, t in SEX])
GPIV = ", ".join([f"coalesce(sum(n) FILTER (sex = '{sx}' AND k = '{c}'), 0) AS g{t}{i}" for sx, t in SEX for i, c in enumerate(RACES)]
                 + [f"coalesce(sum(n) FILTER (sex = '{sx}' AND (k IS NULL OR k NOT IN ({RL}))), 0) AS g{t}4" for sx, t in SEX])
KEEP = ", ".join([f"coalesce(bk.b{t}{i}, 0) AS b{t}{i}" for t in "mf" for i in range(4)] + [f"coalesce(bk.bt{t}, 0) AS bt{t}" for t in "mf"])
GSEL = ", ".join(f"uk.g{t}{i}" for t in "mf" for i in range(5))


class Acc:
    """What one variant accumulates over the periods: per municipality T, V, C, VM, VC, A (candidates alone) and the units; per size class the quadratic
    forms M of the exact variance, the unique-key and the uniform-attribution tables."""

    def __init__(self, nm, nc):
        self.T, self.V, self.C, self.VM, self.VC, self.A = (np.zeros((nm, 4, 5)) for _ in range(6))
        self.D = np.zeros(nm)
        self.M = np.zeros((nc, 4, 5, 5))
        self.U, self.W = np.zeros((nc, 4, 5)), np.zeros((nc, 4, 5))

    def add(self, df, at, cls):
        for i in range(0, max(len(df), 1), 60000):
            self._add(df.iloc[i:i + 60000], at, cls)

    def _add(self, df, at, cls):
        idx = df["mun"].map(at).to_numpy()
        ok = ~pd.isna(idx)
        df, idx = df[ok], idx[ok].astype(int)
        gM, gF = (df[[f"g{t}{i}" for i in range(5)]].to_numpy(float) for t in "mf")
        cM, cF = (df[[f"b{t}{i}" for i in range(4)]].to_numpy(float) for t in "mf")
        tM, tF = df["btm"].to_numpy(float), df["btf"].to_numpy(float)
        nm, nf = df["nm"].to_numpy(float), df["nf"].to_numpy(float)
        beta = np.where((nm > 0) & (nf > 0), nm / np.where(nf > 0, nf, 1), 1.0)[:, None]
        x, y = gM - gF / beta, gF - beta * gM                           # the coefficients of the boys' and the girls' candidates in T
        cube = {"T": cM[:, :, None] * x[:, None, :] + cF[:, :, None] * y[:, None, :],
                "V": cM[:, :, None] * (gM + gF / beta)[:, None, :] + cF[:, :, None] * (gF + beta * gM)[:, None, :],
                "C": cM[:, :, None] * (gF / beta)[:, None, :] + cF[:, :, None] * (beta * gM)[:, None, :],
                "VM": cM[:, :, None] * (gM ** 2 + (gF / beta) ** 2)[:, None, :] + cF[:, :, None] * (gF ** 2 + (beta * gM) ** 2)[:, None, :],
                "VC": cF[:, :, None] * (gM ** 2 * (beta + beta ** 2))[:, None, :] + cM[:, :, None] * (gF ** 2 * (1 / beta + 1 / beta ** 2))[:, None, :],
                "A": cM[:, :, None] * gM[:, None, :] + cF[:, :, None] * gF[:, None, :]}
        for name, arr in cube.items():
            tgt = getattr(self, name)
            for j in range(4):
                for k in range(5):
                    tgt[:, j, k] += np.bincount(idx, weights=arr[:, j, k], minlength=len(self.D))
        self.D += np.bincount(idx, weights=gM.sum(1) + gF.sum(1), minlength=len(self.D))
        c = cls[idx]
        uM, uF = (tM == 1)[:, None], (tF == 1)[:, None]
        wM, wF = (cM / np.maximum(tM, 1)[:, None]), (cF / np.maximum(tF, 1)[:, None])
        for ci in np.unique(c):
            m = c == ci
            for j in range(4):
                self.M[ci, j] += (x[m] * cM[m, j:j + 1]).T @ x[m] + (y[m] * cF[m, j:j + 1]).T @ y[m]
            self.U[ci] += np.einsum("nj,nk->jk", cM[m] * uM[m], gM[m]) + np.einsum("nj,nk->jk", cF[m] * uF[m], gF[m])
            self.W[ci] += np.einsum("nj,nk->jk", wM[m], gM[m]) + np.einsum("nj,nk->jk", wF[m], gF[m])


def exact_p_se(Ts, Mg):
    """The model standard error of every proportion with the covariances of the cells of a row: a' M_j a / T_j+^2, a = e_k - p_jk."""
    row = Ts.sum(1)
    out = np.full((4, 5), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = Ts / row[:, None]
        for j in range(4):
            for k in range(5):
                a = np.full(5, -p[j, k])
                a[k] += 1.0
                out[j, k] = np.sqrt(max(a @ Mg[j] @ a, 0.0)) / abs(row[j])
    return out


def truth_from(df, mask=None):
    """The known table of the units of ``df`` (columns declared, k, n) that ``mask`` keeps, rows with their pairs."""
    d = df if mask is None else df[mask]
    d = d[d.declared.isin(RACES)]
    m = {"pairs": int(d.n.sum()), "rows": {}}
    for j in RACES:
        s = d[d.declared == j]
        tot = s.n.sum()
        if tot:
            m["rows"][NAME[j]] = {NAME.get(k, "other"): e(s.n[(s.k == k) if k != "other" else ~s.k.isin(RACES)].sum() / tot) for k in COLS}
            m["rows"][NAME[j]]["n"] = int(tot)
    return m


def compare3(p, ses, truth):
    """The estimate's 4 x 5 table against the known one: differences, and each standard error's cells outside 1.96 of it and the sd of the z-scores."""
    d, z = [], {k: [] for k in ses}
    for a, j in enumerate(RACES):
        if NAME[j] not in truth["rows"] or truth["rows"][NAME[j]].get("n", 0) < 30:
            continue
        for b, k in enumerate(COLS):
            diff = p[a, b] - truth["rows"][NAME[j]][NAME.get(k, "other")]["est"]
            d.append(diff)
            for key, se in ses.items():
                z[key].append(diff / se[a, b] if se[a, b] > 0 else (0.0 if diff == 0 else np.inf))
    d = np.array(d)
    out = {"cells": len(d), "mean_abs_diff": float(np.mean(np.abs(d))), "max_abs_diff": float(np.max(np.abs(d))), "rmse": float(np.sqrt(np.mean(d ** 2)))}
    for key, v in z.items():
        v = np.array(v)
        fin = v[np.isfinite(v)]
        out[f"outside_{key}"] = int((np.abs(v) > 1.96).sum())
        out[f"z_sd_{key}"] = float(np.std(fin)) if len(fin) > 1 else None
    return out


def drive(periods, load, cls_of, labels, groups, truth_df, born_filter):
    """The loop over periods (birth years for the infants, years for the admissions): load(period) registers the tables ``units`` and ``b`` in ``rk``."""
    muns_ = sorted(cls_of)
    at = {m: i for i, m in enumerate(muns_)}
    cls = np.array([labels.index(cls_of[m]) for m in muns_])
    rk.register("mcls", pd.DataFrame({"mun": muns_, "cls": cls}))
    accs = {v: Acc(len(muns_), len(labels)) for v in VARIANTS}
    sxx = np.zeros((len(labels), 4, 4))
    for per in periods:
        load(per)
        rk.execute(f"CREATE OR REPLACE TEMP TABLE bk AS SELECT dn, mun, {BPIV} FROM b GROUP BY dn, mun")
        for sc, expr in SCALES.items():
            rk.execute(f"""CREATE OR REPLACE TEMP TABLE bs_{sc} AS SELECT s, yb, sum(n) FILTER (sex = 'M') nm, sum(n) FILTER (sex = 'F') nf
                           FROM (SELECT {expr.format(m='mun')} s, year(dn) yb, sex, n FROM b) GROUP BY s, yb""")
        pairs = [(i, j) for i in range(4) for j in range(i, 4)]
        row = rk.execute(f"""SELECT mcls.cls, {', '.join(f'sum(bm{i} * bm{j} + bf{i} * bf{j})' for i, j in pairs)} FROM bk JOIN mcls USING (mun) GROUP BY 1""").fetchall()
        for r_ in row:
            for n_, (i, j) in enumerate(pairs):
                sxx[r_[0], i, j] += r_[1 + n_]
                if i != j:
                    sxx[r_[0], j, i] += r_[1 + n_]
        for v, (where, shift, scale) in VARIANTS.items():
            born = f"AND year(dn + ({shift})) = {per}" if born_filter else ""
            df = rk.execute(f"""WITH d AS (SELECT dn + ({shift}) AS dn, mun, sex, k, sum(n) AS n FROM units WHERE ({where}) {born} GROUP BY ALL),
                                uk AS (SELECT dn, mun, {GPIV} FROM d GROUP BY dn, mun)
                                SELECT uk.mun, {GSEL}, {KEEP}, bs.nm, bs.nf FROM uk LEFT JOIN bk ON bk.dn = uk.dn AND bk.mun = uk.mun
                                LEFT JOIN bs_{scale} bs ON bs.s = {SCALES[scale].format(m='uk.mun')} AND bs.yb = year(uk.dn)""").df()
            accs[v].add(df, at, cls)
        print("  period", per, flush=True)
    res = {"groups": {}}
    for gl, gc in groups:
        gi = [labels.index(c) for c in gc]
        block = {"variants": {}, "full": {}}
        for v, a in accs.items():
            sel = np.isin(cls, gi) & (a.D > 0)
            if not sel.any():
                continue
            est = mr.candidate_estimates(a.T[sel], a.V[sel], a.D[sel], None, ref=0, control=a.C[sel], var_model=a.VM[sel], var_chance=a.VC[sel])
            Ts, Mg = a.T[sel].sum(0), a.M[gi].sum(0)
            est["p_se_exact"] = exact_p_se(Ts, Mg)
            rec = {"units": float(a.D[sel].sum()), "municipalities": int(sel.sum()), "found": e(est["found"], est["found_se"], se_chance=float(est["found_se_chance"])),
                   "row_sums": Ts.sum(1).tolist(), "p": est["p"].tolist(), "p_se_exact": est["p_se_exact"].tolist(),
                   "chance_per_unit": float(a.C[sel].sum() / a.D[sel].sum())}
            ses = {"cluster": est["p_se"], "poisson": est["p_se_poisson"], "model": est["p_se_model"], "exact": est["p_se_exact"], "chance": est["p_se_chance"]}
            if v in ("all", "linked", "findable", "scale_uf", "scale_br"):
                for tn, tmask in (("linked", truth_df.linked), ("findable", truth_df.findable)):
                    tr = truth_from(truth_df[truth_df.cls.isin(gc)], tmask[truth_df.cls.isin(gc)])
                    rec[f"against_{tn}"] = compare3(est["p"], ses, tr)
                    rec[f"against_{tn}"]["nocontrol_mean_abs_diff"] = float(np.mean([abs((a.A[sel].sum(0)[j] / a.A[sel].sum(0)[j].sum())[k] - tr["rows"][NAME[RACES[j]]][NAME.get(COLS[k], "other")]["est"])
                                                                                    for j in range(4) if NAME[RACES[j]] in tr["rows"] and tr["rows"][NAME[RACES[j]]]["n"] >= 30 for k in range(5)]))
                    if v == "linked" and tn == "linked":
                        block["full"] = {"p": est["p"].tolist(), "p_se_model": est["p_se_model"].tolist(), "p_se_exact": est["p_se_exact"].tolist(), "p_se_chance": est["p_se_chance"].tolist(),
                                         "truth": [[tr["rows"][NAME[j]][NAME.get(c, "other")]["est"] for c in COLS] if tr["rows"].get(NAME[j], {}).get("n", 0) >= 30 else None for j in RACES]}
            if v.startswith("shift"):
                with np.errstate(divide="ignore", invalid="ignore"):
                    zc = Ts / np.sqrt(np.stack([Mg[j].diagonal() for j in range(4)]))
                rec["placebo"] = {"z_mean": float(np.nanmean(zc)), "z_sd": float(np.nanstd(zc)), "share_outside": float(np.nanmean(np.abs(zc) > 1.96)),
                                  "T_over_deaths": float(Ts.sum() / a.D[sel].sum())}
            if v == "all":
                U, W = a.U[gi].sum(0), a.W[gi].sum(0)
                Sxy = a.A[np.isin(cls, gi)].sum(0)                         # (4, 5): the sum over the key cells of births of class j times deaths of class k
                bet = np.linalg.solve(sxx[gi].sum(0) + 1e-9 * np.eye(4), Sxy)
                comp_ = {"unique": U, "uniform": W, "goodman": bet}
                tr = truth_from(truth_df[truth_df.cls.isin(gc)], truth_df.linked[truth_df.cls.isin(gc)])
                rec["comparators"] = {}
                for cn, mat in comp_.items():
                    rs = mat.sum(1)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        pc_ = mat / rs[:, None]
                    rec["comparators"][cn] = compare3(np.nan_to_num(pc_, nan=0.0), {}, tr) | {"units_used": float(mat.sum())}
            block["variants"][v] = rec
        vs = block["variants"]
        for a_, b_, name in (("boys", "girls", "sex_split"), ("unlinked", "linked", "unlinked_vs_linked")):
            if a_ in vs and b_ in vs:      # A2 tested directly (the sexes' tables should agree); the unlinked against the linked units (do they differ?)
                pa_, pb_, sa_, sb_ = (np.array(vs[v_][k_], float) for v_, k_ in ((a_, "p"), (b_, "p"), (a_, "p_se_exact"), (b_, "p_se_exact")))
                ok_ = ((np.array(vs[a_]["row_sums"]) >= 50) & (np.array(vs[b_]["row_sums"]) >= 50))[:, None] & np.isfinite(sa_) & np.isfinite(sb_)
                zz = ((pa_ - pb_) / np.sqrt(sa_ ** 2 + sb_ ** 2))[ok_]
                block[name] = {"cells": int(ok_.sum()), "mean_abs_diff": float(np.abs(pa_ - pb_)[ok_].mean()) if ok_.any() else None,
                               "z_mean": float(zz.mean()) if len(zz) else None, "z_sd": float(zz.std()) if len(zz) > 1 else None,
                               "share_outside": float((np.abs(zz) > 1.96).mean()) if len(zz) else None}
        res["groups"][gl] = block
    return res


def groups_of(labels_, extra):
    return [(lb, [lb]) for lb in labels_] + extra


# ---- infants: units in the linkage's order with the key and the stored link's flags
U_ = pq.read_table(DATA / "infant_units.parquet").to_pandas()
assert len(U_) == len(L) and (U_.year.to_numpy() == L.year.to_numpy()).all(), "infant_units.parquet is not aligned with the linkage"
IU = pd.DataFrame({"dn": U_.dn, "sex": U_.sex, "mun": U_.res.astype(str).str[:6], "k": L.rec.astype(object).where(L.rec.notna(), None).to_numpy(),
                   "declared": L.dec.astype(object).where(L.dec.notna(), None).to_numpy(), "linked": L.linked.to_numpy(),
                   "findable": L.findable.to_numpy(), "n": 1})
IU = IU[IU.sex.isin(["M", "F"]) & IU.dn.notna() & IU.mun.notna() & (IU.mun != "None")]
bysize = comp.set_index("mun").births_year


def size_label(b):
    return np.nan if pd.isna(b) else next(lb for lo, hi, lb in SIZES if lo <= b < hi)


IU["cls"] = IU.mun.map(bysize).map(size_label)
IU = IU[IU.cls.notna()]
icls = {m: c for m, c in IU.drop_duplicates("mun")[["mun", "cls"]].itertuples(index=False)}
births_mun = set()
for y in range(2012, 2024):
    births_mun |= set(rk.execute(f"SELECT DISTINCT substr(mun, 1, 6) FROM read_parquet('{(KC / f'births_{y}.parquet').as_posix()}')").df().iloc[:, 0])
for m in births_mun:
    if m in bysize.index and not pd.isna(bysize[m]):
        icls.setdefault(m, size_label(bysize[m]))


def to_arrow(df):
    """A DuckDB-ready table; the birth dates stay dates (some are far outside pandas' range)."""
    import pyarrow as pa

    return pa.Table.from_pandas(df.drop(columns="dn"), preserve_index=False).append_column("dn", pa.array(df.dn.tolist(), pa.date32()))


rk.register("iu", to_arrow(IU))


def load_inf(born):
    rk.execute("CREATE OR REPLACE TEMP TABLE units AS SELECT * REPLACE (CAST(dn AS DATE) AS dn) FROM iu")
    rk.execute(f"CREATE OR REPLACE TEMP TABLE b AS SELECT dn, sex, substr(mun, 1, 6) mun, j, n FROM read_parquet('{(KC / f'births_{born}.parquet').as_posix()}')")


print("like for like: infants", flush=True)
ilabels = [lb for _, _, lb in SIZES]
OUT["like_infants"] = drive(range(2012, 2024), load_inf, icls, ilabels,
                            groups_of(ilabels, [("<25,600", ilabels[:4]), ("all", ilabels)]), IU, True)
OUT["like_infants"]["units"] = int(len(IU))
OUT["like_infants"]["unit_shares"] = {"linked": float(IU.linked.mean()), "findable": float(IU.findable.mean())}

# ---- admissions
PU = pd.concat([pq.read_table(KC / f"pair_units_{y}.parquet").to_pandas().assign(year=y) for y in years], ignore_index=True)
reg_n = pd.concat([rk.execute(f"SELECT substr(mun, 1, 6) mun, sum(n) n FROM read_parquet('{(KC / f'pair_reg_{y}.parquet').as_posix()}') GROUP BY 1").df() for y in years])
reg_n = reg_n.groupby("mun").n.sum() / len(years)


def psize(b):
    return next(lb for lo, hi, lb in PSIZES if lo <= b < hi)


PU["mun"] = PU.mun.astype(str).str[:6]
PU["k"] = PU.k.astype(object).where(PU.k.notna(), None)
pcls = {m: psize(v) for m, v in reg_n.items()}
PU["cls"] = PU.mun.map(pcls)
PU = PU[PU.cls.notna()]


def load_pair(year):
    rk.register("pu_year", to_arrow(PU[PU.year == year][["dn", "sex", "mun", "k", "linked", "findable", "n"]]))
    rk.execute("CREATE OR REPLACE TEMP TABLE units AS SELECT * REPLACE (CAST(dn AS DATE) AS dn) FROM pu_year")
    rk.execute(f"CREATE OR REPLACE TEMP TABLE b AS SELECT dn, sex, substr(mun, 1, 6) mun, j, n FROM read_parquet('{(KC / f'pair_reg_{year}.parquet').as_posix()}')")


print("like for like: admissions", flush=True)
plabels = [lb for _, _, lb in PSIZES]
OUT["like_pair"] = drive(years, load_pair, pcls, plabels, groups_of(plabels, [("all", plabels)]), PU, False)
OUT["like_pair"]["units"] = int(PU.n.sum())
OUT["like_pair"]["unit_shares"] = {"linked": float(PU.n[PU.linked].sum() / PU.n.sum()), "findable": float(PU.n[PU.findable].sum() / PU.n.sum())}

# ------------------------------------------------------------------ 5. A1 diagnostics: who shares the key, among the linked (review 2, sections 1.6 and 2)
a1 = {}
ls = L[L.linked & L.dec.isin(RACES)]
a1["infants"] = {"by_declared": {NAME[j]: float(ls[ls.dec == j].findable.mean()) for j in RACES},
                 "by_declared_recorded": {f"{NAME[j]}|{NAME.get(k, 'other')}": {"t": float(g.findable.mean()), "n": int(len(g))} for j in RACES
                                          for k, g in ls[ls.dec == j].assign(rk_=lambda x: x.rec.where(x.rec.isin(RACES), "other")).groupby("rk_")}}
pt = con.execute("""SELECT declared, CASE WHEN recorded IN ('white','black','brown','indigenous') THEN recorded WHEN recorded IS NULL THEN 'missing' ELSE 'other' END AS rec,
                           CASE WHEN age IS NULL THEN 'unknown' WHEN age < 1 THEN '<1' WHEN age < 15 THEN '1-14' WHEN age < 60 THEN '15-59' ELSE '60+' END AS ageband, findable::INT AS f, count(*) AS n
                    FROM pair_truth WHERE linked AND declared IS NOT NULL GROUP BY ALL""").df()
fa = lambda d_: float((d_.f * d_.n).sum() / d_.n.sum())  # noqa: E731
a1["pair"] = {"by_declared": {NAME[j]: fa(pt[pt.declared == j]) for j in RACES if (pt.declared == j).any()},
              "by_declared_recorded": {f"{NAME[j]}|{r_}": {"t": fa(g), "n": int(g.n.sum())} for j in RACES for r_, g in pt[pt.declared == j].groupby("rec")},
              "by_age": {a_: fa(g) for a_, g in pt.groupby("ageband")}}
tj = [a1["pair"]["by_declared"][NAME[j]] for j in RACES]
a1["key_error_by_class"] = [1 - tj[0], 1 - tj[1], 1 - tj[2], 1 - tj[3], 1 - tj[2]]       # a declared 'other' as Brown, as in the simulation
a1["rate_ratio_distortion"] = {f"{NAME[RACES[i]]}/Brown": tj[i] / tj[2] for i in (0, 1, 3)}
OUT["a1_findability"] = a1
# the hospital's race missing, by findability (the units of the second validation that are linked): the share of the cell 'other' that is missing
miss = con.execute("""SELECT declared, findable, count(*) n, avg((recorded IS NULL)::INT) miss, avg(coalesce(recorded IN ('white','black','brown','indigenous'), false)::INT) four,
                             avg((recorded = 'white')::INT) FILTER (recorded IS NOT NULL) white_given_known
                      FROM pair_truth WHERE linked AND declared IN ('white','black','brown','indigenous') GROUP BY ALL""").df()
OUT["pair"]["missing_race"] = {f"{NAME[d_]}|{'findable' if f_ else 'unfindable'}": {"n": int(n_), "missing": float(m_), "four_classes": float(f4), "white_given_known": float(wk)}
                               for d_, f_, n_, m_, f4, wk in miss.itertuples(index=False)}

# ------------------------------------------------------------------ 6. what the simulation needs from the real data: the births' dispersion and the classification's heterogeneity
bd = rk.execute(f"SELECT substr(mun, 1, 6) mun, (dn - DATE '2018-01-01') AS day, sex, sum(n) n FROM read_parquet('{(KC / 'births_2018.parquet').as_posix()}') GROUP BY ALL").df()
bd = bd[(bd.day >= 0) & (bd.day < 364) & bd.sex.isin(["M", "F"])]
bm_ = sorted(set(bd.mun))
bat = {m: i for i, m in enumerate(bm_)}
Z = np.zeros((len(bm_), 364, 2))
np.add.at(Z, (bd.mun.map(bat).to_numpy(), bd.day.to_numpy(), (bd.sex == "F").to_numpy().astype(int)), bd.n.to_numpy())
Z = Z.reshape(len(bm_), 52, 7, 2)                                       # municipality, week, weekday, sex: the expectation is the weekday's mean within the year
mu, s2 = Z.mean(1), Z.var(1, ddof=1)
cv = ((Z[..., 0] - mu[:, None, :, 0]) * (Z[..., 1] - mu[:, None, :, 1])).sum(1) / 51
den = np.maximum(mu ** 2 - s2 / 52, 1e-9)
den_x = np.maximum(mu[..., 0] * mu[..., 1] - cv / 52, 1e-9)
bcls = np.array([size_label(bysize.get(m, np.nan)) if m in bysize.index else None for m in bm_], dtype=object)
disp = {}
for lb, selm in [*[(lb, bcls == lb) for lb in ilabels], ("all", np.ones(len(bm_), bool))]:
    if selm.sum():
        disp[lb] = {"phi": float(((s2 - mu)[selm].sum()) / den[selm].sum()), "psi": float(cv[selm].sum() / den_x[selm].sum()), "municipalities": int(selm.sum())}
disp["phi"], disp["psi"] = disp["all"]["phi"], disp["all"]["psi"]
OUT["births_dispersion"] = disp
# the municipalities' own classification beyond the binomial and the decile gradient: DerSimonian-Laird on the logit of being certified the declared class
het = {}
tau2, wts = [], []
for j in ("white", "black", "brown"):
    d_ = LL[LL.dec == j].assign(hit=lambda x, j=j: (x.rec == j).astype(int)).groupby(["mun6", "dec"]).agg(x=("hit", "sum"), n=("hit", "size")).reset_index()
    d_ = d_.merge(comp[["mun", "white_share"]], left_on="mun6", right_on="mun", how="left").query("n >= 30")
    d_["y"] = np.log((d_.x + 0.5) / (d_.n - d_.x + 0.5))
    d_["v"] = 1 / (d_.x + 0.5) + 1 / (d_.n - d_.x + 0.5)
    d_["dec_"] = np.minimum((d_.white_share * 10).fillna(0).astype(int), 9)
    t2, kk = [], []
    for _, g in d_.groupby("dec_"):
        if len(g) < 5:
            continue
        w = 1 / g.v
        ybar = (w * g.y).sum() / w.sum()
        qq = (w * (g.y - ybar) ** 2).sum()
        t2.append(max(0.0, (qq - (len(g) - 1)) / (w.sum() - (w ** 2).sum() / w.sum())))
        kk.append(len(g))
    het[j] = {"tau": float(np.sqrt(np.average(t2, weights=kk))) if t2 else None, "municipalities": int(sum(kk))}
    if t2:
        tau2.append(np.average(t2, weights=kk))
        wts.append(sum(kk))
het["tau"] = float(np.sqrt(np.average(tau2, weights=wts)))
OUT["classification_heterogeneity"] = het

OUT["variance_approximated"] = sorted(APPROX)
(PAPER / "results" / "estimator.json").write_text(json.dumps(OUT, indent=1), encoding="utf-8")
print(json.dumps({"infants": [(b["size"], b["against_linkage"]) for b in OUT["infants"]], "ratios": OUT["ratios"]["1-4|all"]}, indent=0)[:3000])
print("DONE", flush=True)
