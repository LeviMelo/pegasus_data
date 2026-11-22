"""Paper 5, review 2026-11-22 (5.1, 5.2, 5.5): is the cause contrast at death a finding about the death, or paper 1's finding about the
place where the death is certified?

The same deaths and birth candidates as analysis/violence.py (results/violence.json, birth_cert), with the death certificate's municipality
of occurrence (CODMUNOCOR) and place of death (LOCOCOR: 1 hospital, 2 other health facility, 3 home, 4 public road, 5 other, 6 indigenous
village) added. For each split, the birth-to-certificate shift in the share White (certified less at birth) by cause group, and the
difference from natural causes and from transport deaths, with 500 bootstrap replicates over municipalities of residence:
  - died in the municipality of residence, or elsewhere;
  - by the composition of the municipality of occurrence (the share of White births there, SINASC 2012-2023), in thirds, and the cause
    contrast standardised to the composition of the place of occurrence (each cause's shift averaged over the thirds with the weights of
    all deaths);
  - within external causes, died in hospital against elsewhere (the proxy for a family present before the death is certified).

    python papers/race_at_death/analysis/violence_place.py   -> results/violence_place.json
"""
import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pegasus_data.config import load_settings

warnings.simplefilter("ignore")
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
LAKE = Path(load_settings().lake_dir).as_posix()
con = duckdb.connect(str(HERE / "data" / "violence.duckdb"))
con.execute("PRAGMA disable_progress_bar; SET memory_limit='1500MB'; SET threads=2")
SIM = f"read_parquet('{LAKE}/SIM/SIM_DO_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
RACES = ["white", "black", "brown"]
SIMR = BR = {"1": "white", "2": "black", "4": "brown"}
rng = np.random.default_rng(23)

if "deaths_place" not in {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}:
    con.execute(f"""CREATE TABLE deaths_place AS SELECT strptime(trim(DTNASC), '%d%m%Y') dn, trim(SEXO) sex, left(trim(CODMUNRES), 6) mun,
                    trim(RACACOR) k, trim(CAUSABAS) cause, left(trim(CODMUNOCOR), 6) occ, trim(LOCOCOR) loc
                    FROM {SIM} WHERE year BETWEEN 2015 AND 2024 AND trim(IDADE) BETWEEN '415' AND '424' AND trim(SEXO) IN ('1', '2')
                    AND try_strptime(trim(DTNASC), '%d%m%Y') BETWEEN DATE '2000-01-01' AND DATE '2009-12-31'
                    AND try_strptime(trim(DTOBITO), '%d%m%Y') IS NOT NULL AND left(trim(CODMUNRES), 6) IN (SELECT mun FROM small)""")
con.execute("""CREATE OR REPLACE TEMP TABLE dp AS SELECT row_number() OVER () id, *, CASE
                WHEN cause BETWEEN 'X93' AND 'X95ZZ' THEN 'assault by firearm' WHEN cause BETWEEN 'X85' AND 'Y09ZZ' THEN 'other assault'
                WHEN cause BETWEEN 'Y35' AND 'Y36ZZ' THEN 'legal intervention' WHEN cause BETWEEN 'X60' AND 'X84ZZ' THEN 'suicide'
                WHEN cause BETWEEN 'Y10' AND 'Y34ZZ' THEN 'undetermined intent'
                WHEN cause BETWEEN 'V01' AND 'V99ZZ' THEN 'transport' WHEN left(cause, 1) IN ('V', 'W', 'X', 'Y', 'S', 'T') THEN 'other external'
                ELSE 'natural' END kind FROM deaths_place""")
n_old, n_new = con.execute("SELECT (SELECT count(*) FROM deaths), (SELECT count(*) FROM dp)").fetchone()
assert n_old == n_new, f"the deaths differ from violence.py's ({n_old} against {n_new})"
con.execute("""CREATE OR REPLACE TEMP TABLE bscale AS SELECT mun, year(dn) by_, sum(n) FILTER (sex = '1') m, sum(n) FILTER (sex = '2') f FROM births GROUP BY 1, 2""")
bd = con.execute("""SELECT d.id, b.b, sum(CASE WHEN b.sex = d.sex THEN b.n ELSE 0 END) cand, sum(CASE WHEN b.sex <> d.sex THEN b.n ELSE 0 END) ctrl,
                    any_value(s.m) m, any_value(s.f) f, any_value(d.sex) sex
                    FROM dp d JOIN births b ON b.dn = d.dn AND b.mun = d.mun LEFT JOIN bscale s ON s.mun = d.mun AND s.by_ = year(d.dn)
                    GROUP BY 1, 2""").df()
bd["c"] = np.where(bd.sex == "1", bd.m / bd.f.clip(lower=1), bd.f / bd.m.clip(lower=1)).astype(float)
bd["bhat"] = bd.cand - bd.c * bd.ctrl
bd["bb"] = bd.b.map(BR)
Bw = bd[bd.bb.isin(RACES)].pivot_table(index="id", columns="bb", values="bhat", aggfunc="sum", fill_value=0.0).reindex(columns=RACES, fill_value=0.0)
meta = con.execute("SELECT id, mun, occ, loc, k, kind, cause FROM dp").df().set_index("id")
meta["kk"] = meta.k.map(SIMR)
meta = meta[meta.kk.isin(RACES)].join(Bw, how="inner")
z = np.load(ROOT / "data" / "probes" / "race_own_birth" / "births_by_cohort.npz")
tot = z["births"].sum(0)
comp = pd.Series(tot[:, 0] / np.maximum(tot[:, :5].sum(1), 1), index=[str(int(m)) for m in z["muns"]])
meta["occ_white"] = meta.occ.map(comp)
meta["res_white"] = meta.mun.map(comp)
meta["away"] = meta.occ != meta.mun
meta["hospital"] = meta["loc"].isin(["1", "2"])
q = meta.occ_white.quantile([1 / 3, 2 / 3]).to_numpy()
meta["occ_third"] = np.digitize(meta.occ_white, q)
MUN = pd.factorize(meta.mun)[0]
NM = MUN.max() + 1
WB = np.vstack([np.ones(NM)] + [np.bincount(rng.integers(0, NM, NM), minlength=NM) for _ in range(500)])   # replicates x municipalities


def cube(mask):
    """Municipality x birth x certificate of the deaths in ``mask``, then bootstrap totals: replicates x birth x certificate."""
    m_ = meta[mask]
    c = np.zeros((NM, 3, 3))
    kk = m_.kk.map({r: i for i, r in enumerate(RACES)}).to_numpy()
    for i_k in range(3):
        sel = kk == i_k
        np.add.at(c[:, :, i_k], MUN[mask.to_numpy()][sel], m_[RACES].to_numpy()[sel])
    return np.einsum("rm,mbk->rbk", WB, c)


def shift(T):
    t = T.sum((1, 2))
    return T[:, :, 0].sum(1) / t - T[:, 0, :].sum(1) / t, t[0]          # certified White less White at birth, per replicate


KINDS = {"natural": ["natural"], "transport": ["transport"], "all assault": ["assault by firearm", "other assault", "legal intervention"],
         "assault by firearm": ["assault by firearm"], "all external, not assault": ["transport", "suicide", "other external"],
         "suicide": ["suicide"]}


def contrasts(base_mask):
    out, sh = {}, {}
    for g, v in KINDS.items():
        s_, n_ = shift(cube(base_mask & meta.kind.isin(v)))
        sh[g] = s_
        out[g] = {"shift": float(s_[0]), "se": float(np.nanstd(s_[1:])), "deaths_found": float(n_)}
    for g in KINDS:
        for ref in ("natural", "transport"):
            if g != ref:
                d_ = sh[g] - sh[ref]
                out[g][f"minus_{ref}"] = {"est": float(d_[0]), "lo": float(np.nanpercentile(d_[1:], 2.5)), "hi": float(np.nanpercentile(d_[1:], 97.5))}
    return out


ALL = pd.Series(True, index=meta.index)
R = {"deaths_found": float(meta[RACES].to_numpy().sum()), "away_share": {g: float(np.average(meta.away[meta.kind.isin(v)], weights=meta[RACES].sum(1)[meta.kind.isin(v)]))
                                                                        for g, v in KINDS.items()},
     "hospital_share": {g: float(np.average(meta.hospital[meta.kind.isin(v)], weights=meta[RACES].sum(1)[meta.kind.isin(v)])) for g, v in KINDS.items()},
     "occ_white_mean": {g: float(np.average(meta.occ_white[meta.kind.isin(v)].fillna(meta.res_white), weights=meta[RACES].sum(1)[meta.kind.isin(v)]))
                        for g, v in KINDS.items()},
     "res_white_mean": {g: float(np.average(meta.res_white[meta.kind.isin(v)], weights=meta[RACES].sum(1)[meta.kind.isin(v)])) for g, v in KINDS.items()},
     "thirds_cut": q.tolist()}
R["all"] = contrasts(ALL)
R["died_at_home_municipality"] = contrasts(~meta.away)
R["died_elsewhere"] = contrasts(meta.away)
R["by_occurrence_third"] = {str(t): contrasts(meta.occ_third == t) for t in range(3)}
# standardised to the composition of the place of occurrence: each cause's shift averaged over the thirds with all deaths' weights
wt = np.array([meta[RACES].sum(1)[meta.occ_third == t].sum() for t in range(3)])
wt = wt / wt.sum()
stdz = {}
for g, v in KINDS.items():
    s3 = np.stack([shift(cube((meta.occ_third == t) & meta.kind.isin(v)))[0] for t in range(3)])
    stdz[g] = (wt[:, None] * s3).sum(0)
R["standardised_to_occurrence"] = {g: {"shift": float(s[0]), "se": float(np.nanstd(s[1:]))} for g, s in stdz.items()}
for g in KINDS:
    for ref in ("natural", "transport"):
        if g != ref:
            d_ = stdz[g] - stdz[ref]
            R["standardised_to_occurrence"][g][f"minus_{ref}"] = {"est": float(d_[0]), "lo": float(np.nanpercentile(d_[1:], 2.5)), "hi": float(np.nanpercentile(d_[1:], 97.5))}
# within external causes: died in hospital (a family likely present) against elsewhere
ext = meta.kind != "natural"
R["external_hospital"] = contrasts(ext & meta.hospital)
R["external_not_hospital"] = contrasts(ext & ~meta.hospital)
# every cause by place of death: is the natural-external contrast the place (hospital, a family likely present) rather than the cause?
R["died_in_hospital"] = contrasts(meta.hospital)
R["died_out_of_hospital"] = contrasts(~meta.hospital)
# round 2, 5.2: the external causes standardised to the place-of-death distribution of natural deaths. Places: a health establishment (LOCOCOR
# 1-2), home (3), public road or elsewhere (4-6 or blank). Each cause's shift within each place, averaged with the natural deaths' weights
meta["place3"] = np.select([meta["loc"].isin(["1", "2"]), meta["loc"] == "3"], ["health establishment", "home"], "road or elsewhere")
PL3 = ["health establishment", "home", "road or elsewhere"]
wn = np.array([meta[RACES].sum(1)[(meta.kind == "natural") & (meta.place3 == q)].sum() for q in PL3])
wn = wn / wn.sum()
dist = {g: {q: float(meta[RACES].sum(1)[meta.kind.isin(v) & (meta.place3 == q)].sum() / meta[RACES].sum(1)[meta.kind.isin(v)].sum()) for q in PL3}
        for g, v in KINDS.items()}
st_place = {}
for g, v in KINDS.items():
    s3 = np.stack([shift(cube((meta.place3 == q) & meta.kind.isin(v)))[0] for q in PL3])
    st_place[g] = {"by_place": {q: {"shift": float(s3[i][0]), "se": float(np.nanstd(s3[i][1:]))} for i, q in enumerate(PL3)},
                   "_reps": (wn[:, None] * s3).sum(0)}
R["place_of_death_distribution"] = dist
R["standardised_to_natural_place"] = {}
raw_gap = shift(cube(meta.kind == "natural"))[0]
for g in KINDS:
    sr = st_place[g]["_reps"]
    d_ = sr - st_place["natural"]["_reps"]
    raw = shift(cube(meta.kind.isin(KINDS[g])))[0] - raw_gap
    R["standardised_to_natural_place"][g] = {"shift": float(sr[0]), "se": float(np.nanstd(sr[1:])), "by_place": st_place[g]["by_place"],
                                             "minus_natural": {"est": float(d_[0]), "lo": float(np.nanpercentile(d_[1:], 2.5)), "hi": float(np.nanpercentile(d_[1:], 97.5))},
                                             "raw_minus_natural": float(raw[0]), "share_remaining": float(d_[0] / raw[0]) if g != "natural" and raw[0] != 0 else None}
# 5.5 what the natural deaths at 15-24 are: ICD chapters of the deaths found
nat = meta[meta.kind == "natural"]
ch = nat.cause.str[0].map(lambda c: {"C": "neoplasms", "D": "neoplasms or blood", "G": "nervous system", "I": "circulatory", "J": "respiratory",
                                      "A": "infectious", "B": "infectious", "E": "endocrine", "K": "digestive", "N": "genitourinary", "O": "pregnancy",
                                      "Q": "congenital", "R": "ill-defined"}.get(c, "other"))
R["natural_chapters"] = (nat[RACES].sum(1).groupby(ch).sum() / nat[RACES].to_numpy().sum()).sort_values(ascending=False).to_dict()
(HERE / "results" / "violence_place.json").write_text(json.dumps(R, indent=1), encoding="utf-8")
for k in ("all", "died_at_home_municipality", "died_elsewhere", "standardised_to_occurrence", "external_hospital", "external_not_hospital", "died_in_hospital", "died_out_of_hospital"):
    print(k, {g: round(v["shift"], 3) for g, v in R[k].items()}, "assault-natural", R[k]["all assault"].get("minus_natural"))
print("away", {g: round(v, 3) for g, v in R["away_share"].items()}, "occ_white", {g: round(v, 3) for g, v in R["occ_white_mean"].items()})
print("standardised to natural place", {g: (round(v["minus_natural"]["est"], 3), round(v["raw_minus_natural"], 3), v["share_remaining"] and round(v["share_remaining"], 2)) for g, v in R["standardised_to_natural_place"].items()})
print("place dist", {g: {q: round(x, 2) for q, x in v.items()} for g, v in R["place_of_death_distribution"].items()})
print("chapters", {k: round(v, 3) for k, v in R["natural_chapters"].items()})
