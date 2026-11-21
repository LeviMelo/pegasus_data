"""Every number of the manuscript, computed from the study's artefacts into one file (results.json).

Artefacts (made by the probes named in docs/evaluation/2026-11-21-race-own-birth.md):
  data/probes/race_own_birth/  candidates_package.parquet, infant_candidates.parquet, infant_truth.parquet,
                               candidates_old.parquet, candidates_old_deaths.parquet, births_by_cohort.npz
  data/probes/race_chain/      women.parquet, B_2015..B_2022.parquet, A_2022.parquet
  the data home                the SINASC lake, population-account-9

    python papers/race_at_death/analysis/results.py
"""
import glob
import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from pegasus_data.config import load_settings
from pegasus_data.studies import modelled_race as mr

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[3]
OB, CH = ROOT / "data/probes/race_own_birth", ROOT / "data/probes/race_chain"
settings = load_settings()
LAKE = Path(settings.lake_dir).as_posix()
con = duckdb.connect()
con.execute("PRAGMA disable_progress_bar; SET memory_limit='6GB'")
R: dict = {}
IDX = {"Branca": 0, "Preta": 1, "Parda": 3, "Indigena": 4}        # the model's class order (Amarela is 2)
SIZES = [(0, 400, "<400"), (400, 1600, "400-1,599"), (1600, 6400, "1,600-6,399"), (6400, 25600, "6,400-25,599"), (25600, 10**9, ">=25,600"), (0, 10**9, "all")]


def est(value, se=None, **more):
    out = {"est": float(value)}
    if se is not None:
        out["se"] = float(se)
    return out | {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in more.items()}


# ---- 1. what the birth record's colour is, by year
rows = con.execute(f"""SELECT year, count(*) n,
    avg((RACACORMAE IS NOT NULL AND trim(RACACORMAE) <> '')::INT) mae,
    avg((trim(RACACOR) = '1')::INT) FILTER (trim(RACACOR) IN ('1','2','3','4','5')) branca,
    avg((trim(RACACOR) = '2')::INT) FILTER (trim(RACACOR) IN ('1','2','3','4','5')) preta,
    avg((trim(RACACOR) = '4')::INT) FILTER (trim(RACACOR) IN ('1','2','3','4','5')) parda,
    avg((trim(RACACOR) = trim(RACACORMAE))::INT) FILTER (trim(RACACOR) <> '' AND trim(RACACORMAE) <> '') same
    FROM read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)
    WHERE year BETWEEN 2000 AND 2024 GROUP BY 1 ORDER BY 1""").fetchall()
R["form"] = [{"year": int(y), "births": int(n), "mother_field": float(m or 0), "branca": float(b), "preta": float(p), "parda": float(pd),
              "equal": (None if s is None else float(s))} for y, n, m, b, p, pd, s in rows]


# ---- helpers over a candidates table
def diff_table(c, mask):
    T, S, deaths = mr.candidate_difference(c, mask)
    row = T.sum(1)
    cells = {name: est(T[i, i] / row[i], S[i, i] / abs(row[i]), declared_deaths=row[i]) for name, i in IDX.items() if row[i] > 0}
    moves = {"Preta>Parda": est(T[1, 3] / row[1], S[1, 3] / abs(row[1])), "Parda>Branca": est(T[3, 0] / row[3], S[3, 0] / abs(row[3])),
             "Branca>Parda": est(T[0, 3] / row[0], S[0, 3] / abs(row[0]))}
    mix = {name: float(row[i] / row[[0, 1, 3, 4]].sum()) for name, i in IDX.items()}
    cand = float(pc.sum(pc.filter(c["n"], pc.fill_null(pc.and_(mask, pc.equal(c["control"], False)), False))).as_py() or 0)
    return {"deaths": float(deaths), "found": float(T.sum() / deaths), "candidates_per_death": cand / deaths, "stays": cells, "moves": moves, "declared_mix": mix}


def size_mask(c, lo, hi):
    return pc.and_(pc.greater_equal(c["births"], lo), pc.less(c["births"], hi))


# ---- 2. validation on infants
c, t = pq.read_table(OB / "infant_candidates.parquet"), pq.read_table(OB / "infant_truth.parquet")
size = {}
for m, b in zip(c["mun"].to_pylist(), c["births"].to_pylist(), strict=True):
    if b is not None:
        size[m] = max(size.get(m, 0), b)
tm = np.array([size.get(m, 0) for m in t["mun"].to_pylist()])
rec, dec = mr.encode_race(t["recorded"].to_pylist()), mr.encode_race(t["declared"].to_pylist())
linked = np.asarray(t["linked"].to_numpy(zero_copy_only=False), dtype=bool)
R["validation"] = {"certificates_in_system": int(t.num_rows), "rows": []}
for lo, hi, label in SIZES:
    d = diff_table(c, size_mask(c, lo, hi))
    m = linked & (dec < 5) & (tm >= lo) & (tm < hi)
    L = np.zeros((6, 6))
    np.add.at(L, (dec[m], rec[m]), 1.0)
    lrow = L.sum(1)
    d["link"] = {name: float(L[i, i] / lrow[i]) for name, i in IDX.items()}
    d["link_mix"] = {name: float(lrow[i] / lrow[[0, 1, 3, 4]].sum()) for name, i in IDX.items()}
    d["linked_deaths"] = int(m.sum())
    R["validation"]["rows"].append({"size": label} | d)

# ---- 3. children: the matrix by size, the rates for the country
c = pq.read_table(OB / "candidates_package.parquet")
z = np.load(OB / "births_by_cohort.npz")
muns, births = z["muns"], z["births"]
cstate = np.array([int(m[:2]) if m else 0 for m in c["mun"].to_pylist()])
bstate = muns // 10000
# the largest municipalities (25,600 births a year or more, by the mean of the cohorts' years), for the sensitivity analysis
blarge = births.sum(2).mean(0) >= 25600
large_set = {str(int(m)) for m in muns[blarge]}
clarge = np.array([m in large_set for m in c["mun"].to_pylist()])
R["children"] = {}
for label, lo_a, hi_a in (("1-4", 1, 4), ("5-9", 5, 9)):
    band = pc.and_(pc.greater_equal(c["age"], lo_a), pc.less_equal(c["age"], hi_a))
    bandn = np.asarray(band.to_numpy(zero_copy_only=False))
    block = {"by_size": [{"size": s} | diff_table(c, pc.and_(band, size_mask(c, lo, hi))) for lo, hi, s in SIZES]}

    def ratios(leave=None, without_large=False):
        keep = bandn if leave is None else bandn & (cstate != leave)
        sel = np.ones(len(muns), bool) if leave is None else bstate != leave
        if without_large:
            keep, sel = keep & ~clarge, sel & ~blarge
        T, S, deaths = mr.candidate_difference(c, pa.array(keep))
        expo = np.zeros(6)
        for y in range(2013, 2025):
            for a in range(lo_a, hi_a + 1):
                if 2012 <= y - a <= 2023:
                    expo += births[y - a - 2012][sel].sum(0)
        d, v = T.sum(1), (S**2).sum(1)
        r = (d / expo) / (d[3] / expo[3])
        cert = T.sum(0)                                  # the certificate's classes among the found: not the certificate's rate
        return r, r * np.sqrt(v / d**2 + v[3] / d[3] ** 2), expo, deaths

    full, se_c, expo, deaths = ratios()
    loo = np.array([ratios(s)[0] for s in sorted(set(bstate.tolist()))])
    se_j = np.sqrt((len(loo) - 1) / len(loo) * ((loo - loo.mean(0)) ** 2).sum(0))
    # the certificate's own ratio: every death by its recorded class over the same births
    dk = np.zeros(6)
    drows = c.filter(pc.and_(band, pc.is_null(c["control"])))
    np.add.at(dk, mr.encode_race(mr._codes(drows["recorded"])), np.asarray(drows["n"].to_numpy(zero_copy_only=False), dtype=float))
    cert = (dk / expo) / (dk[3] / expo[3])
    cert_se = cert * np.sqrt(1 / np.maximum(dk, 1) + 1 / dk[3])            # Poisson counts of certified deaths
    r2, s2, _, d2 = ratios(without_large=True)
    block["rate_ratio"] = {name: est(full[i], max(se_c[i], se_j[i]), se_counts=se_c[i], se_jackknife=se_j[i], certificate=cert[i],
                                     certificate_se=cert_se[i], loo_min=loo[:, i].min(), loo_max=loo[:, i].max()) for name, i in IDX.items() if name != "Parda"}
    block["rate_ratio_without_large"] = {name: est(r2[i], s2[i]) for name, i in IDX.items() if name != "Parda"}
    block["deaths_without_large"] = float(d2)
    block["deaths"], block["person_years"] = float(deaths), {name: float(expo[i]) for name, i in IDX.items()}
    block["certificate_deaths"] = {name: float(dk[i]) for name, i in IDX.items()} | {"none": float(dk[5])}
    R["children"][label] = block

# ---- 4. ages 15-24 by kind of death (old-form cohorts)
acc, dc = f"'{(OB / 'candidates_old.parquet').as_posix()}'", f"'{(OB / 'candidates_old_deaths.parquet').as_posix()}'"
RC = ["white", "black", "brown"]


def old_row(where):
    T, V = np.zeros((3, 3)), np.zeros((3, 3))
    for j, k, real, ctl in con.execute(f"SELECT j, k, sum(n) FILTER (NOT ctl), sum(n) FILTER (ctl) FROM {acc} WHERE {where} AND j IS NOT NULL AND k IS NOT NULL GROUP BY 1, 2").fetchall():
        if j in RC and k in RC:
            T[RC.index(j), RC.index(k)], V[RC.index(j), RC.index(k)] = (real or 0) - (ctl or 0), (real or 0) + (ctl or 0)
    row = T.sum(1)
    deaths = con.execute(f"SELECT sum(n) FROM {dc} WHERE {where}").fetchone()[0] or 0
    s = lambda a, b: float(np.sqrt(V[a, b]) / abs(row[a]))  # noqa: E731
    return {"deaths": float(deaths), "found": float(T.sum() / deaths),
            "Branca stays": est(T[0, 0] / row[0], s(0, 0)), "Branca>Parda": est(T[0, 2] / row[0], s(0, 2)),
            "Parda stays": est(T[2, 2] / row[2], s(2, 2)), "Preta stays": est(T[1, 1] / row[1], s(1, 1))}


R["kinds"] = {}
for kind in ("natural", "transport", "other external", "assault"):
    R["kinds"][kind] = {"small": old_row(f"band = 1 AND kind = '{kind}' AND NOT big"), "large": old_row(f"band = 1 AND kind = '{kind}' AND big"),
                        "small_men": old_row(f"band = 1 AND kind = '{kind}' AND NOT big AND sex = 'M'"),
                        "small_women": old_row(f"band = 1 AND kind = '{kind}' AND NOT big AND sex = 'F'")}
R["kinds_5_14"] = {kind: old_row(f"band = 0 AND kind = '{kind}' AND NOT big") for kind in ("natural", "assault")}

# ---- 5. the same cohorts at birth and at three censuses
M = f"'{LAKE}/modelled/population_account/population-account-9/estimates.parquet'"
rows = con.execute(f"""SELECT ((year - age) // 5) * 5 cohort, year,
    sum(population) FILTER (race = 'branca') / sum(population), sum(population) FILTER (race = 'parda') / sum(population),
    sum(population) FILTER (race = 'preta') / sum(population), sum(population)
    FROM {M} WHERE year IN (2000, 2010, 2022) AND race <> 'total' AND age <= 90 AND year - age BETWEEN 1940 AND 2009 GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
R["cohorts"] = [{"cohort": int(c0), "year": int(y), "branca": float(b), "parda": float(pd), "preta": float(p), "people": float(n)} for c0, y, b, pd, p, n in rows]
falls = [(a["cohort"], a["year"], b["year"], b["branca"] < a["branca"]) for a in R["cohorts"] for b in R["cohorts"]
         if a["cohort"] == b["cohort"] and (a["year"], b["year"]) in ((2000, 2010), (2010, 2022))]
R["cohort_falls"] = {"intervals": len(falls), "white_fell": sum(f[3] for f in falls), "exceptions": [[f[0], f[1], f[2]] for f in falls if not f[3]]}
R["old_cohort_death_years"] = [int(x) for x in con.execute(f"SELECT min(born), max(born) FROM {dc} WHERE band = 1").fetchone()]
R["cohorts_birth"] = [{"cohort": int(c0), "branca": float(b), "parda": float(pd), "preta": float(p)} for c0, b, pd, p in con.execute(f"""
    SELECT (year // 5) * 5, avg((trim(RACACOR) = '1')::INT), avg((trim(RACACOR) = '4')::INT), avg((trim(RACACOR) = '2')::INT)
    FROM read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)
    WHERE trim(RACACOR) IN ('1','2','3','4','5') AND year BETWEEN 2000 AND 2009 GROUP BY 1 ORDER BY 1""").fetchall()]

# ---- 6. three readings of the same woman
RACES5 = ["white", "black", "brown", "indigenous", "asian"]
CODE = {"1": 0, "2": 1, "4": 2, "5": 3, "3": 4}
Bf = "[" + ", ".join(f"'{p.replace(chr(92), '/')}'" for p in sorted(glob.glob(str(CH / "B_*.parquet")))) + "]"
ix = "CASE {c} " + " ".join(f"WHEN '{r}' THEN {i}" for i, r in enumerate(RACES5)) + " END"
w = pq.read_table(CH / "women.parquet")
comp = mr.composition(pq.read_table(OB / "births_2020_2021.parquet"))
year, linkedw, pairs = mr.prepare(w, comp, mr.WOMEN)
bandw = mr.age_band_years(np.asarray(w["age_years"].to_numpy(zero_copy_only=False), dtype=float))
sel = linkedw & (bandw >= 0)
pr = pairs(linkedw)
decw = np.array([CODE.get(v, -1) for v in np.asarray(w["declared"].to_pylist(), dtype=object)[sel]])
regw = (np.asarray(w["uf"].to_pylist())[sel] // 10).astype(int)
con.register("wl", pa.table({"id": np.asarray(w["id"].to_pylist(), dtype=object)[sel].tolist(), "j": decw.tolist(), "phi": pr.phi.tolist(), "region": regw.tolist()}))
tt = con.execute(f"""SELECT wl.j, {ix.format(c='b."patient.race"')} h, {ix.format(c='b."deceased.race"')} k, wl.phi, wl.region
                     FROM wl JOIN read_parquet({Bf}) b ON b.r = wl.id""").df().dropna()
tt = tt[tt.j >= 0].astype({"j": int, "h": int, "k": int, "region": int})
pif = np.zeros((6, 5))
for r in range(1, 6):
    m = (regw == r) & (decw >= 0)
    pif[r] = np.bincount(decw[m], minlength=5) / max(m.sum(), 1)
T3 = np.zeros((5, 5, 5))
np.add.at(T3, (tt.j.to_numpy(), tt.h.to_numpy(), tt.k.to_numpy()), 1.0)
hk = np.zeros((6, 5, 5))
np.add.at(hk, (tt.region.to_numpy(), tt.h.to_numpy(), tt.k.to_numpy()), tt.phi.to_numpy())
T3 = np.maximum(T3 - np.einsum("rj,rhk->jhk", pif, hk), 0)
N3 = ["Branca", "Preta", "Parda"]
R["triples"] = {"women_deaths": int(w.num_rows), "linked": int(linkedw.sum()), "with_three": int(len(tt)), "false_share": float(tt.phi.mean()),
                "hospital_as_declared": {N3[j]: float(T3[j, j].sum() / T3[j].sum()) for j in range(3)},
                "certificate_as_declared": {N3[j]: float(T3[j, :, j].sum() / T3[j].sum()) for j in range(3)},
                "certificate_given_hospital": {N3[j]: {N3[h]: float(T3[j, h, j] / T3[j, h].sum()) for h in range(3)} for j in range(3)},
                "agree": {"certificate=declared": float((tt.k == tt.j).mean()), "hospital=declared": float((tt.h == tt.j).mean()),
                          "certificate=hospital": float((tt.k == tt.h).mean())}}
a = con.execute(f"""SELECT {ix.format(c='"mother.race"')} j, {ix.format(c='"patient.race"')} h, count(*) FROM '{(CH / "A_2022.parquet").as_posix()}'
                    GROUP BY 1, 2 HAVING j IS NOT NULL AND h IS NOT NULL""").fetchall()
A2 = np.zeros((5, 5))
for j, h, n in a:
    A2[int(j), int(h)] = n
R["delivery"] = {"pairs": float(A2.sum()), "hospital_as_declared": {N3[j]: float(A2[j, j] / A2[j].sum()) for j in range(3)}}

out = Path(__file__).resolve().parents[1] / "results" / "results.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(R, indent=1), encoding="utf-8")
print("written", out, "keys", list(R))
