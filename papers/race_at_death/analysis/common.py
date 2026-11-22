"""What every analysis of the paper shares: the connection, the births and the municipal composition, the candidate counts
as tables, the estimator's matrices and rates, and the one-to-one infant linkage (`L`, `LL`). Imported by results.py and
spatial.py, so that the estimator exists once.
"""
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from pegasus_data.config import load_settings

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[3]
PAPER = Path(__file__).resolve().parents[1]
DATA, OB, CH, CEN = PAPER / "data", ROOT / "data/probes/race_own_birth", ROOT / "data/probes/race_chain", ROOT / "data/probes/census2010"
settings = load_settings()
LAKE = Path(settings.lake_dir).as_posix()
con = duckdb.connect()
con.execute("PRAGMA disable_progress_bar; SET memory_limit='8GB'")
R: dict = {}
RACES = ["white", "black", "brown", "indigenous"]                    # order of every matrix here
NAME = {"white": "Branca", "black": "Preta", "brown": "Parda", "indigenous": "Indigena"}
CODE = {"1": "white", "2": "black", "4": "brown", "5": "indigenous", "3": "asian"}
REGION = {1: "North", 2: "Northeast", 3: "Southeast", 4: "South", 5: "Centre-West"}
UF = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE",
      29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}
SIZES = [(0, 400, "<400"), (400, 1600, "400-1,599"), (1600, 6400, "1,600-6,399"), (6400, 25600, "6,400-25,599"), (25600, 10**9, ">=25,600")]
KIND = """CASE WHEN cause IS NULL OR left(cause, 1) NOT IN ('V','W','X','Y') THEN 'natural' WHEN left(cause, 1) = 'V' THEN 'transport'
          WHEN cause BETWEEN 'X60' AND 'X84' THEN 'suicide' WHEN cause BETWEEN 'X93' AND 'X95' THEN 'assault by firearm'
          WHEN cause BETWEEN 'X85' AND 'X92' OR cause BETWEEN 'X96' AND 'Y09' THEN 'other assault' WHEN cause IN ('Y35', 'Y36') THEN 'legal intervention'
          ELSE 'other external' END"""


def e(value, se=None, **more):
    out = {"est": float(value)}
    if se is not None:
        out["se"] = float(se)
    return out | more


# ------------------------------------------------------------------ births: exposure and municipal composition
z = np.load(OB / "births_by_cohort.npz")
muns, births = z["muns"], z["births"]                                 # (cohorts 2012..2023, municipalities, [Branca, Preta, Amarela, Parda, Indigena, none])
BIDX = [0, 1, 3, 4]                                                   # RACES in the births array
total = births.sum(0)
comp = pd.DataFrame({"mun": [str(int(m)) for m in muns], "white_share": total[:, 0] / np.maximum(total[:, :5].sum(1), 1),
                     "births_year": births.sum(2).mean(0)})
con.register("comp", comp)
bstate, bregion = muns // 10000, muns // 100000


def exposure(ages, years, sel=None):
    """Person-years by mother's race: births of each cohort counted once per (death year, age) it is exposed in."""
    out = np.zeros(4)
    b = births if sel is None else births[:, sel]
    for y in years:
        for a in ages:
            if 2012 <= y - a <= 2023:
                out += b[y - a - 2012].sum(0)[BIDX]
    return out


# ------------------------------------------------------------------ candidate counts as tables
for label in ("children", "youth", "infants"):
    con.execute(f"""CREATE TABLE {label} AS SELECT c.*, CAST(substr(c.mun, 1, 2) AS INT) uf, CAST(substr(c.mun, 1, 1) AS INT) region, {KIND} AS kind,
                    comp.white_share, comp.births_year FROM '{(DATA / f'{label}_counts.parquet').as_posix()}' c LEFT JOIN comp ON comp.mun = c.mun""")


def diff(table, where="TRUE"):
    """Candidates less control: T[declared, recorded] over RACES (recorded gets a fifth column: any other or none), its
    Poisson variance, and the deaths of the group."""
    T, V = np.zeros((4, 5)), np.zeros((4, 5))
    for j, k, real, ctl in con.execute(f"""SELECT declared, recorded, sum(n) FILTER (control = false), sum(n) FILTER (control)
                                           FROM {table} WHERE control IS NOT NULL AND ({where}) GROUP BY 1, 2""").fetchall():
        if j in RACES:
            col = RACES.index(k) if k in RACES else 4
            T[RACES.index(j), col] += (real or 0) - (ctl or 0)
            V[RACES.index(j), col] += (real or 0) + (ctl or 0)
    deaths = con.execute(f"SELECT coalesce(sum(n), 0) FROM {table} WHERE control IS NULL AND ({where})").fetchone()[0]
    return T, V, float(deaths)


def certified(table, where="TRUE"):
    """Deaths of the group by the race on the certificate (RACES, then other or none)."""
    out = np.zeros(5)
    for k, n in con.execute(f"SELECT recorded, sum(n) FROM {table} WHERE control IS NULL AND ({where}) GROUP BY 1").fetchall():
        out[RACES.index(k) if k in RACES else 4] += n
    return out


def matrix(table, where="TRUE"):
    """Proportions of each declared class by certified class, with standard errors; the share found; the declared mix."""
    T, V, deaths = diff(table, where)
    row = T.sum(1)
    out = {"deaths": deaths, "found": float(T.sum() / deaths) if deaths else None, "rows": {}}
    for i, j in enumerate(RACES):
        if row[i] <= 0:
            continue
        out["rows"][NAME[j]] = {(NAME[k] if k in NAME else "other"): e(T[i, c] / row[i], np.sqrt(V[i, c]) / row[i]) for c, k in enumerate([*RACES, "other"])}
        out["rows"][NAME[j]]["declared_deaths"] = float(row[i] / T.sum() * deaths)
    mix = row / row.sum()
    vrow = V.sum(1)
    out["declared_mix"] = {NAME[j]: e(mix[i], np.sqrt(vrow[i]) / row.sum()) for i, j in enumerate(RACES)}
    return out


def rates(table, where, ages, years, sel=None, per=1e5):
    """Mortality by mother's race (deaths of the group by declared mix over the cohorts' births) and by certified race over
    the same births; ratios to Brown. Standard errors: Poisson, on the declared mix and on the certified counts."""
    T, V, deaths = diff(table, where)
    row, vrow = T.sum(1), V.sum(1)
    expo = exposure(ages, years, sel)
    mix = row / row.sum()
    d_decl = deaths * mix
    se_decl = deaths * np.sqrt(vrow) / row.sum()
    cert = certified(table, where)[:4]
    out = {"deaths": deaths, "person_years": {NAME[j]: float(expo[i]) for i, j in enumerate(RACES)}, "by_mother": {}, "by_certificate": {}, "ratio_mother": {}, "ratio_certificate": {}}
    for i, j in enumerate(RACES):
        out["by_mother"][NAME[j]] = e(per * d_decl[i] / expo[i], per * se_decl[i] / expo[i])
        out["by_certificate"][NAME[j]] = e(per * cert[i] / expo[i], per * np.sqrt(max(cert[i], 1)) / expo[i])
        if j != "brown":
            r = (d_decl[i] / expo[i]) / (d_decl[2] / expo[2])
            out["ratio_mother"][NAME[j]] = e(r, r * np.sqrt(vrow[i] / row[i] ** 2 + vrow[2] / row[2] ** 2))
            rc = (cert[i] / expo[i]) / (cert[2] / expo[2])
            out["ratio_certificate"][NAME[j]] = e(rc, rc * np.sqrt(1 / max(cert[i], 1) + 1 / max(cert[2], 1)))
    out["_d_decl"], out["_expo"] = d_decl.tolist(), expo.tolist()
    return out



# ------------------------------------------------------------------ 2. infants: the one-to-one linkage, 2013-2023, and the validation
L = pq.read_table(DATA / "infant_linkage.parquet").to_pandas()
L["rec"] = L["recorded"].map(CODE)
L["dec"] = L["declared"].map(CODE)
L["mun6"] = L["mun"].astype(str).str[:6]
L = L.merge(comp, left_on="mun6", right_on="mun", how="left", suffixes=("", "_c"))
L["region"] = L["uf"] // 10
LL = L[L.linked & L.dec.isin(RACES)]


def link_matrix(d):
    out = {"pairs": int(len(d)), "rows": {}}
    for j in RACES:
        s = d[d.dec == j]
        if len(s) == 0:
            continue
        out["rows"][NAME[j]] = {(NAME[k] if k in NAME else "other"): e((s.rec == k).mean() if k != "other" else (~s.rec.isin(RACES)).mean(),
                                                                         np.sqrt(max((s.rec == k).mean() * (1 - (s.rec == k).mean()), 1e-9) / len(s)) if k != "other" else 0.0)
                            for k in [*RACES, "other"]}
        out["rows"][NAME[j]]["n"] = int(len(s))
    return out


