# ruff: noqa: F405 - the names come from common
"""The numbers of paper 6 (the estimator) that results.py does not hold: both validations with the variance linearised over
municipalities (`modelled_race.candidate_estimates`), the second validation pair (admissions that ended in death against
their certificates, `analysis/pair.py`), and the rate ratios' variance with their denominator.

    python papers/race_at_death/analysis/estimator.py   -> results/estimator.json   (a few minutes)
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
               "colour_known": {side: float(con.execute(f"SELECT avg(({col} IN ('white','black','brown','indigenous','asian'))::INT) FROM pair_truth WHERE linked").fetchone()[0])
                                for side, col in (("admission", "recorded"), ("certificate", "declared"))}}
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

OUT["variance_approximated"] = sorted(APPROX)
(PAPER / "results" / "estimator.json").write_text(json.dumps(OUT, indent=1), encoding="utf-8")
print(json.dumps({"infants": [(b["size"], b["against_linkage"]) for b in OUT["infants"]], "ratios": OUT["ratios"]["1-4|all"]}, indent=0)[:3000])
print("DONE", flush=True)
