"""Every number of the manuscript, computed from the study's data into results/results.json.

Inputs
  papers/race_at_death/data/   children_counts, youth_counts, infants_counts (candidate counts, `analysis/counts.py`),
                               infant_linkage (the one-to-one linkage of infant deaths, 2013-2023)
  data/probes/census2010/      mother_child.parquet, persons.parquet (2010 Census sample, `mother_child.py`)
  data/probes/race_own_birth/  births_by_cohort.npz (live births by municipality, cohort and mother's race)
  data/probes/race_chain/      women.parquet, B_*.parquet, A_2022.parquet (three readings of race)
  the data home                the SINASC lake, population-account-9

    python papers/race_at_death/analysis/results.py
"""
import glob
import json

import pyarrow as pa
import pyarrow.parquet as pq

from pegasus_data.studies import modelled_race as mr
from common import *  # noqa: F403 - the shared machinery: con, R, births, comp, diff, matrix, rates, L, LL, link_matrix


# ------------------------------------------------------------------ 1. what the birth record's colour is, by year
rows = con.execute(f"""SELECT year, count(*) n, avg((RACACORMAE IS NOT NULL AND trim(RACACORMAE) <> '')::INT) mae,
    avg((trim(RACACOR) = '1')::INT) FILTER (trim(RACACOR) IN ('1','2','3','4','5')) branca, avg((trim(RACACOR) = '2')::INT) FILTER (trim(RACACOR) IN ('1','2','3','4','5')) preta,
    avg((trim(RACACOR) = '4')::INT) FILTER (trim(RACACOR) IN ('1','2','3','4','5')) parda
    FROM read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true) WHERE year BETWEEN 2000 AND 2024 GROUP BY 1 ORDER BY 1""").fetchall()
R["form"] = [{"year": int(y), "births": int(n), "mother_field": float(m or 0), "branca": float(b), "preta": float(p), "parda": float(pd_)} for y, n, m, b, p, pd_ in rows]

# ------------------------------------------------------------------ 2. infants: the one-to-one linkage, 2013-2023, and the validation
R["infants"] = {"certificates": int(len(L)), "linked": int(L.linked.sum()), "linked_with_race": int(len(LL)), "years": [int(L.year.min()), int(L.year.max())],
                "linkage": link_matrix(LL), "candidates": matrix("infants"),
                "by_year": {int(y): link_matrix(g) for y, g in LL.groupby("year")},
                "by_region": {REGION[int(r)]: link_matrix(g) for r, g in LL.groupby("region") if int(r) in REGION},
                "by_state": {UF[int(u)]: link_matrix(g) for u, g in LL.groupby("uf") if int(u) in UF},
                "by_age": {lab: link_matrix(LL[(LL.age_days >= lo) & (LL.age_days < hi)]) for lab, lo, hi in (("0-6 d", 0, 7), ("7-27 d", 7, 28), ("28-364 d", 28, 365))}}
# validation: candidates against linkage by size class (the linkage's deaths classed by the municipality's births a year)
R["validation"] = []
for lo, hi, label in [*SIZES, (0, 10**9, "all")]:
    m = matrix("infants", f"births >= {lo} AND births < {hi}")
    g = LL[(LL.births_year >= lo) & (LL.births_year < hi)]
    R["validation"].append({"size": label, "candidates": m, "linkage": link_matrix(g)})
# the gradient with the local mix: by decile of the municipality's share of White births
LL = LL.assign(bin=pd.cut(LL.white_share, [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0], labels=False, include_lowest=True))
R["gradient_infants"] = [{"bin": int(b), "white_share": float(g.white_share.mean()), "matrix": link_matrix(g)} for b, g in LL.groupby("bin")]

# ------------------------------------------------------------------ 3. children 1-9 (mother's race): candidates
R["children"] = {}
for label, lo, hi in (("1-4", 1, 4), ("5-9", 5, 9), ("1-9", 1, 9)):
    w = f"age BETWEEN {lo} AND {hi}"
    yrs, ages = range(2013, 2025), range(lo, hi + 1)
    block = {"matrix": matrix("children", w), "rates": rates("children", w, ages, yrs),
             "by_size": [{"size": s} | matrix("children", f"{w} AND births >= {a} AND births < {b}") for a, b, s in SIZES],
             "without_large": {"matrix": matrix("children", f"{w} AND births_year < 25600"), "rates": rates("children", f"{w} AND births_year < 25600", ages, yrs, comp.births_year.to_numpy() < 25600)},
             "by_sex": {s: matrix("children", f"{w} AND sex = '{s}' AND births_year < 25600") for s in ("M", "F")},
             "by_kind": {k: matrix("children", f"{w} AND births_year < 25600 AND " + ("kind = 'natural'" if k == "natural" else "kind <> 'natural'")) for k in ("natural", "external")},
             "by_period": {p: matrix("children", f"{w} AND births_year < 25600 AND year BETWEEN {a} AND {b}") for p, a, b in (("2013-2018", 2013, 2018), ("2019-2024", 2019, 2024))},
             "by_region": {}, "by_state": {}, "gradient": []}
    for r, rn in REGION.items():
        block["by_region"][rn] = {"matrix": matrix("children", f"{w} AND region = {r} AND births_year < 25600"),
                                  "rates": rates("children", f"{w} AND region = {r}", ages, yrs, bregion == r)}
    for u, un in UF.items():
        block["by_state"][un] = {"rates": rates("children", f"{w} AND uf = {u}", ages, yrs, bstate == u), "matrix": matrix("children", f"{w} AND uf = {u} AND births_year < 25600")}
    for b in range(10):
        ww = f"{w} AND births_year < 25600 AND white_share >= {b / 10} AND white_share < {(b + 1) / 10 + (1e-9 if b == 9 else 0)}"
        share = con.execute(f"SELECT sum(white_share * n) / sum(n) FROM children WHERE control IS NULL AND {ww}").fetchone()[0]
        if share is not None:
            block["gradient"].append({"bin": b, "white_share": float(share), "matrix": matrix("children", ww)})
    # delete-one-state jackknife of the national rate ratios
    full = block["rates"]["ratio_mother"]
    loo = {k: [] for k in full}
    for u in UF:
        rr = rates("children", f"{w} AND uf <> {u}", ages, yrs, bstate != u)["ratio_mother"]
        for k in full:
            loo[k].append(rr[k]["est"])
    for k in full:
        v = np.array(loo[k])
        full[k] |= {"se_jackknife": float(np.sqrt((len(v) - 1) / len(v) * ((v - v.mean()) ** 2).sum())), "loo_min": float(v.min()), "loo_max": float(v.max())}
        full[k]["se_counts"] = full[k]["se"]
        full[k]["se"] = max(full[k]["se"], full[k]["se_jackknife"])
    R["children"][label] = block
R["children_by_age"] = {int(a): matrix("children", f"age = {a} AND births_year < 25600") for a in range(1, 13)}

# infant mortality by mother's race (per 1,000 live births), from the candidate counts of infants over the births of the same years
ti, vi, di = diff("infants")
rowi = ti.sum(1)
bi = np.zeros(4)
for y in range(2013, 2024):
    bi += births[y - 2012].sum(0)[BIDX]
ci = certified("infants")[:4]
R["infant_rates"] = {"deaths": di, "births": {NAME[j]: float(bi[i]) for i, j in enumerate(RACES)},
                     "by_mother": {NAME[j]: e(1e3 * di * rowi[i] / rowi.sum() / bi[i], 1e3 * di * np.sqrt(vi.sum(1)[i]) / rowi.sum() / bi[i]) for i, j in enumerate(RACES)},
                     "by_certificate": {NAME[j]: e(1e3 * ci[i] / bi[i], 1e3 * np.sqrt(ci[i]) / bi[i]) for i, j in enumerate(RACES)}}
for i, j in enumerate(RACES):
    if j != "brown":
        r = (rowi[i] / bi[i]) / (rowi[2] / bi[2])
        rc = (ci[i] / bi[i]) / (ci[2] / bi[2])
        R["infant_rates"].setdefault("ratio_mother", {})[NAME[j]] = e(r, r * np.sqrt(vi.sum(1)[i] / rowi[i] ** 2 + vi.sum(1)[2] / rowi[2] ** 2))
        R["infant_rates"].setdefault("ratio_certificate", {})[NAME[j]] = e(rc, rc * np.sqrt(1 / ci[i] + 1 / ci[2]))

# ------------------------------------------------------------------ 4. the family's classification of the child: Census 2010
P = f"'{(CEN / 'mother_child.parquet').as_posix()}'"
Q = f"'{(CEN / 'persons.parquet').as_posix()}'"
BAND = "CASE WHEN age = 0 THEN '0' WHEN age < 5 THEN '1-4' WHEN age < 10 THEN '5-9' WHEN age < 15 THEN '10-14' WHEN age < 20 THEN '15-19' ELSE '20-24' END"
CR = {"1": "white", "2": "black", "4": "brown", "5": "indigenous"}


def census_matrix(where="TRUE"):
    out, raw = {}, {}
    for m, c, n, rec in con.execute(f"SELECT mother_race, race, sum(n), sum(records) FROM {P} WHERE {where} GROUP BY 1, 2").fetchall():
        if m in CR:
            raw.setdefault(CR[m], {}).setdefault(CR.get(c, "other"), [0.0, 0])
            raw[CR[m]][CR.get(c, "other")][0] += n
            raw[CR[m]][CR.get(c, "other")][1] += rec
    for m, cells in raw.items():
        tot, recs = sum(v[0] for v in cells.values()), sum(v[1] for v in cells.values())
        out[NAME[m]] = {(NAME[c] if c in NAME else "other"): e(v[0] / tot, np.sqrt(max(v[0] / tot * (1 - v[0] / tot), 1e-12) / max(recs, 1))) for c, v in cells.items()}
        out[NAME[m]]["children"], out[NAME[m]]["records"] = float(tot), int(recs)
    return out


R["census"] = {"persons": float(con.execute(f"SELECT sum(n) FROM {Q}").fetchone()[0]), "records": int(con.execute(f"SELECT sum(records) FROM {Q}").fetchone()[0]),
               "pairs_records": int(con.execute(f"SELECT sum(records) FROM {P}").fetchone()[0]),
               "with_mother": {b: float(s) for b, s in con.execute(f"SELECT {BAND} b, sum(with_mother) / sum(n) FROM {Q} WHERE age < 25 GROUP BY 1").fetchall()},
               "by_band": {b: census_matrix(f"{BAND} = '{b}'") for b in ("0", "1-4", "5-9", "10-14", "15-19", "20-24")},
               "by_age": {int(a): census_matrix(f"age = {a}") for a in range(0, 25)},
               "by_region": {rn: {b: census_matrix(f"{BAND} = '{b}' AND left(uf, 1) = '{r}'") for b in ("0", "1-4", "5-9")} for r, rn in REGION.items()},
               "by_state": {un: census_matrix(f"age BETWEEN 1 AND 9 AND uf = '{u}'") for u, un in UF.items()}}


# the family's classification by the municipality's share of White births (the same bins as the certificates' gradient)
con.execute(f"""CREATE TABLE cen AS SELECT c.*, comp.white_share FROM {P} c LEFT JOIN comp ON comp.mun = c.uf || substr(c.mun, 1, 4)""")
P_ALL, P = P, "cen"
GB = {"0": "age = 0", "1-4": "age BETWEEN 1 AND 4", "5-9": "age BETWEEN 5 AND 9", "1-9": "age BETWEEN 1 AND 9"}
BINS = [(b / 10, (b + 1) / 10 + (1e-9 if b == 9 else 0)) for b in range(10)]
R["census"]["gradient"] = {band: [{"bin": b, "white_share": float(con.execute(f"SELECT sum(white_share * n) / sum(n) FROM cen WHERE {w} AND white_share >= {lo} AND white_share < {hi}").fetchone()[0] or 0),
                                     "matrix": census_matrix(f"{w} AND white_share >= {lo} AND white_share < {hi}")} for b, (lo, hi) in enumerate(BINS)]
                            for band, w in GB.items()}
# how the family's classification is formed: the mother's partner (the man she heads the household with) and her instruction
PARTNER = {"1": "White", "2": "Black", "4": "Brown"}
INSTR = {"1": "none or incomplete primary", "2": "primary", "3": "secondary", "4": "higher"}
R["census"]["partner_identified"] = float(con.execute("SELECT sum(n) FILTER (partner_race IS NOT NULL) / sum(n) FROM cen WHERE age BETWEEN 0 AND 9").fetchone()[0])
R["census"]["by_partner"] = {lab: census_matrix(f"age BETWEEN 0 AND 9 AND partner_race = '{c}'") for c, lab in PARTNER.items()}
R["census"]["by_partner"]["none identified"] = census_matrix("age BETWEEN 0 AND 9 AND partner_race IS NULL")
R["census"]["by_instruction"] = {lab: census_matrix(f"age BETWEEN 0 AND 9 AND mother_instruction = '{c}'") for c, lab in INSTR.items()}
R["census"]["by_instruction_partner"] = {lab: {pl: census_matrix(f"age BETWEEN 0 AND 9 AND mother_instruction = '{c}' AND partner_race = '{pc}'") for pc, pl in PARTNER.items()}
                                         for c, lab in INSTR.items()}
R["census"]["matched_municipality"] = float(con.execute("SELECT sum(n) FILTER (white_share IS NOT NULL) / sum(n) FROM cen").fetchone()[0])


def household_rates(rt, band):
    """What the rate ratio would be if deaths and births were classified as the family classifies the child (Census 2010):
    deaths and births by mother's race are passed through P(child's race | mother's race)."""
    cm = R["census"]["by_band"][band]
    d, x = np.array(rt["_d_decl"]), np.array(rt["_expo"])
    T = np.array([[cm[NAME[m]].get(NAME[c], {"est": 0.0})["est"] for c in RACES] for m in RACES])
    dc, xc = d @ T, x @ T
    return {NAME[c]: float((dc[i] / xc[i]) / (dc[2] / xc[2])) for i, c in enumerate(RACES) if c != "brown"}


for label, band in (("1-4", "1-4"), ("5-9", "5-9")):
    R["children"][label]["ratio_household"] = household_rates(R["children"][label]["rates"], band)
    for rn in REGION.values():
        R["children"][label]["by_region"][rn]["ratio_household"] = household_rates(R["children"][label]["by_region"][rn]["rates"], band)
R["infant_rates"]["ratio_household"] = household_rates({"_d_decl": (di * rowi / rowi.sum()).tolist(), "_expo": bi.tolist()}, "0")
# the three classifications side by side (mother's race -> child's class): family (census), certificate (children), certificate (infants, linkage)
R["decomposition"] = {}
for label, band, cert_m in (("0", "0", R["infants"]["linkage"]["rows"]), ("1-4", "1-4", R["children"]["1-4"]["without_large"]["matrix"]["rows"]),
                            ("5-9", "5-9", R["children"]["5-9"]["without_large"]["matrix"]["rows"])):
    R["decomposition"][label] = {m: {c: {"family": R["census"]["by_band"][band][m].get(c, {"est": 0.0})["est"], "certificate": cert_m[m][c]["est"],
                                         "certificate_se": cert_m[m][c]["se"]} for c in ("Branca", "Preta", "Parda", "Indigena")}
                                 for m in ("Branca", "Preta", "Parda", "Indigena") if m in cert_m}

# ------------------------------------------------------------------ 5. ages 15-24 (the newborn's colour), by cause
SMALL = "births < 1600"
R["youth"] = {"birth_years": [int(x) for x in con.execute("SELECT min(born), max(born) FROM youth WHERE control IS NULL AND age >= 15").fetchone()],
              "death_years": [int(x) for x in con.execute("SELECT min(year), max(year) FROM youth WHERE control IS NULL AND age >= 15").fetchone()],
              "by_kind": {}, "by_kind_sex": {}, "by_kind_large": {}, "by_kind_region": {}, "by_age": {}, "by_kind_period": {}}
for k in ("natural", "transport", "suicide", "other external", "other assault", "assault by firearm", "legal intervention"):
    w = f"age BETWEEN 15 AND 24 AND kind = '{k}'"
    R["youth"]["by_kind"][k] = matrix("youth", f"{w} AND {SMALL}")
    R["youth"]["by_kind_large"][k] = matrix("youth", f"{w} AND NOT ({SMALL})")
    R["youth"]["by_kind_sex"][k] = {s: matrix("youth", f"{w} AND {SMALL} AND sex = '{s}'") for s in ("M", "F")}
for k, cond in (("natural", "kind = 'natural'"), ("assault", "kind IN ('other assault', 'assault by firearm', 'legal intervention')"), ("external", "kind <> 'natural'")):
    R["youth"]["by_kind_region"][k] = {rn: matrix("youth", f"age BETWEEN 15 AND 24 AND {cond} AND {SMALL} AND region = {r}") for r, rn in REGION.items()}
    R["youth"]["by_kind_period"][k] = {p: matrix("youth", f"age BETWEEN 15 AND 24 AND {cond} AND {SMALL} AND year BETWEEN {a} AND {b}") for p, a, b in (("to 2019", 2014, 2019), ("2020-2024", 2020, 2024))}
    R["youth"]["by_age"][k] = {int(a): matrix("youth", f"age = {a} AND {cond} AND {SMALL}") for a in range(5, 25)}

# ------------------------------------------------------------------ 8. who certified, where the death occurred, the schooling of the mother
CERT = """CASE certifier WHEN '3' THEN 'medical examiner' WHEN '4' THEN 'death verification service' WHEN '1' THEN 'physician' WHEN '2' THEN 'physician'
          WHEN '5' THEN 'physician' ELSE 'not recorded' END"""
SCHOOL = "CASE WHEN schooling IN ('1', '2') THEN '0-3' WHEN schooling = '3' THEN '4-7' WHEN schooling = '4' THEN '8-11' WHEN schooling = '5' THEN '12 or more' ELSE 'not recorded' END"
PLACE = "CASE WHEN death_place IN ('hospital', 'other health facility') THEN 'health facility' WHEN death_place = 'home' THEN 'home' WHEN death_place = 'street' THEN 'street' ELSE 'other or not recorded' END"
for label in ("children_context", "youth_context"):
    con.execute(f"""CREATE TABLE {label} AS SELECT c.*, CAST(substr(c.mun, 1, 2) AS INT) uf, CAST(substr(c.mun, 1, 1) AS INT) region, {KIND} AS kind, {CERT} AS certifier_kind,
                    {SCHOOL} AS school, {PLACE} AS place, comp.white_share, comp.births_year
                    FROM '{(DATA / f'{label}_counts.parquet').as_posix()}' c LEFT JOIN comp ON comp.mun = c.mun""")
CAUSES3 = {"natural": "kind = 'natural'", "external, not assault": "kind IN ('transport', 'suicide', 'other external')",
           "assault": "kind IN ('other assault', 'assault by firearm', 'legal intervention')"}
CERTS, PLACES, SCHOOLS = ["physician", "medical examiner", "death verification service"], ["health facility", "home", "street"], ["0-3", "4-7", "8-11", "12 or more"]
yw, cw = f"age BETWEEN 15 AND 24 AND {SMALL}", "age BETWEEN 1 AND 9 AND births_year < 25600"
R["context"] = {
    "death_place_values": {str(k): float(n) for k, n in con.execute("SELECT death_place, sum(n) FROM youth_context WHERE control IS NULL GROUP BY 1").fetchall()},
    "youth": {"certifier_share": {k: {c: float(n) for c, n in con.execute(f"SELECT certifier_kind, sum(n) FROM youth_context WHERE control IS NULL AND {yw} AND {w} GROUP BY 1").fetchall()}
                                  for k, w in CAUSES3.items()},
              "by_certifier": {k: {c: matrix("youth_context", f"{yw} AND {w} AND certifier_kind = '{c}'") for c in CERTS} for k, w in CAUSES3.items()},
              "by_place": {k: {c: matrix("youth_context", f"{yw} AND {w} AND place = '{c}'") for c in PLACES} for k, w in CAUSES3.items()},
              "by_schooling": {k: {c: matrix("youth_context", f"{yw} AND {w} AND school = '{c}'") for c in SCHOOLS} for k, w in (("all", "TRUE"), *CAUSES3.items())},
              "by_composition": {k: [{"white_share": [lo, hi], "matrix": matrix("youth_context", f"{yw} AND {w} AND white_share >= {lo} AND white_share < {hi}")}
                                     for lo, hi in ((0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01))] for k, w in CAUSES3.items()}},
    "children": {"by_certifier": {c: matrix("children_context", f"{cw} AND certifier_kind = '{c}'") for c in CERTS},
                 "by_place": {c: matrix("children_context", f"{cw} AND place = '{c}'") for c in PLACES},
                 "by_schooling": {c: matrix("children_context", f"{cw} AND school = '{c}'") for c in SCHOOLS}}}


# cause of death at equal municipal composition: each cause's proportions in the five classes of composition, averaged with the weights
# of the natural deaths of the same class at birth (direct standardisation)
COMP5 = ((0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01))
R["context"]["youth"]["standardised"] = {}
for k in CAUSES3:
    R["context"]["youth"]["standardised"][k] = {}
    for a in ("Branca", "Parda"):
        ref = [x["matrix"]["rows"].get(a, {}).get("declared_deaths", 0.0) for x in R["context"]["youth"]["by_composition"]["natural"]]
        wts = np.array(ref) / sum(ref)
        cells = [x["matrix"]["rows"].get(a) for x in R["context"]["youth"]["by_composition"][k]]
        R["context"]["youth"]["standardised"][k][a] = {c: e(sum(w * r[c]["est"] for w, r in zip(wts, cells, strict=True)), np.sqrt(sum((w * r[c]["se"]) ** 2 for w, r in zip(wts, cells, strict=True))))
                                                      for c in ("Branca", "Parda")} if all(cells) else None
R["context"]["youth"]["by_schooling_composition"] = {
    f"{lo:.1f}-{min(hi, 1):.1f}": {c: matrix("youth_context", f"{yw} AND school = '{c}' AND white_share >= {lo} AND white_share < {hi}") for c in SCHOOLS}
    for lo, hi in ((0, 0.3), (0.3, 0.6), (0.6, 1.01))}
R["context"]["children"]["by_schooling_composition"] = {
    f"{lo:.1f}-{min(hi, 1):.1f}": {c: matrix("children_context", f"{cw} AND school = '{c}' AND white_share >= {lo} AND white_share < {hi}") for c in SCHOOLS}
    for lo, hi in ((0, 0.3), (0.3, 0.6), (0.6, 1.01))}


# ------------------------------------------------------------------ 9. a model of the certifier: the family's classification mixed with the local composition
# C_b(m -> c) = (1 - lam_m) F_b(m -> c) + lam_m pi_b(c) over the bins b of the municipality's share of White births: F the family's
# classification (census), pi the composition a certifier who knew nothing of the child would draw from. Two candidates for pi: the
# mothers of the bin's live births, and the certified races of the bin's deaths at the same ages.
def bin_births(lo, hi):
    m = (comp.white_share.to_numpy() >= lo) & (comp.white_share.to_numpy() < hi)
    v = total[m][:, BIDX].sum(0)
    return v / v.sum()


def mixture(cert_bins, family_bins, table, where):
    """cert_bins: [{bin, matrix rows {m: {c: {est, se}}}}]; family_bins: the census gradient over the same bins."""
    fam = {b["bin"]: b["matrix"] for b in family_bins}
    out = {}
    for prior in ("births", "certified"):
        out[prior] = {}
        for m in ("Branca", "Parda", "Preta"):
            xs, ys, ws, cells = [], [], [], []
            for b in cert_bins:
                rows = b["matrix"]["rows"]
                if m not in rows or m not in fam.get(b["bin"], {}):
                    continue
                lo, hi = BINS[b["bin"]]
                if prior == "births":
                    pi = bin_births(lo, hi)
                else:
                    cd = certified(table, f"({where}) AND white_share >= {lo} AND white_share < {hi}")[:4]
                    pi = cd / max(cd.sum(), 1)
                for i, c in enumerate(RACES):
                    cell = rows[m][NAME[c]]
                    if cell.get("se") is None or cell["se"] > 0.25:
                        continue
                    f = fam[b["bin"]][m].get(NAME[c], {"est": 0.0})["est"]
                    xs.append(pi[i] - f)
                    ys.append(cell["est"] - f)
                    ws.append(1 / max(cell["se"] ** 2, 1e-8))
                    cells.append((b["bin"], NAME[c], cell["est"], f, float(pi[i])))
            x, y, v = np.array(xs), np.array(ys), 1 / np.array(ws)

            def fit(tau2):
                w_ = 1 / (v + tau2)
                lam = (w_ * x * y).sum() / (w_ * x * x).sum()
                return lam, w_, (w_ * (y - lam * x) ** 2).sum()

            lo, hi = 0.0, 1.0                                          # between-cell variance: the residual chi-square equals its degrees of freedom
            if fit(0.0)[2] > len(x) - 1:
                for _ in range(60):
                    mid = (lo + hi) / 2
                    lo, hi = (mid, hi) if fit(mid)[2] > len(x) - 1 else (lo, mid)
            tau2 = hi if fit(0.0)[2] > len(x) - 1 else 0.0
            lam, w_, _ = fit(tau2)
            out[prior][m] = {"lambda": e(lam, np.sqrt(1 / (w_ * x * x).sum())), "cells": len(x), "tau": float(np.sqrt(tau2)),
                             "rms_family_only": float(np.sqrt((y * y).mean())), "rms_mixture": float(np.sqrt(((y - lam * x) ** 2).mean())),
                             "fit": [{"bin": c[0], "class": c[1], "certificate": c[2], "family": c[3], "prior": c[4], "model": (1 - lam) * c[3] + lam * c[4]} for c in cells]}
    return out


def as_cert_bins(link_bins):
    """The gradient of the infants' linkage in the candidates' shape (each row's error is its binomial error)."""
    return [{"bin": b["bin"], "matrix": {"rows": {m: r for m, r in b["matrix"]["rows"].items() if r["n"] >= 50}}} for b in link_bins]


con.register("L_all", L[["recorded", "white_share"]])
con.execute("""CREATE TABLE infant_deaths AS SELECT CASE recorded WHEN '1' THEN 'white' WHEN '2' THEN 'black' WHEN '4' THEN 'brown' WHEN '5' THEN 'indigenous' ELSE 'other' END recorded,
               CAST(NULL AS BOOLEAN) control, white_share, CAST(1 AS DOUBLE) n FROM L_all""")
R["mixture"] = {"infants": mixture(as_cert_bins(R["gradient_infants"]), R["census"]["gradient"]["0"], "infant_deaths", "TRUE"),
                "children 1-9": mixture(R["children"]["1-9"]["gradient"], R["census"]["gradient"]["1-9"], "children", "age BETWEEN 1 AND 9 AND births_year < 25600")}

# ------------------------------------------------------------------ 6. the same cohorts at birth and at three censuses
M = f"'{LAKE}/modelled/population_account/population-account-9/estimates.parquet'"
rows = con.execute(f"""SELECT ((year - age) // 5) * 5 cohort, year, sum(population) FILTER (race = 'branca') / sum(population), sum(population) FILTER (race = 'parda') / sum(population),
    sum(population) FILTER (race = 'preta') / sum(population), sum(population)
    FROM {M} WHERE year IN (2000, 2010, 2022) AND race <> 'total' AND age <= 90 AND year - age BETWEEN 1940 AND 2009 GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
R["cohorts"] = [{"cohort": int(c0), "year": int(y), "branca": float(b), "parda": float(pd_), "preta": float(p), "people": float(n)} for c0, y, b, pd_, p, n in rows]
falls = [(a["cohort"], a["year"], b["year"], b["branca"] < a["branca"]) for a in R["cohorts"] for b in R["cohorts"]
         if a["cohort"] == b["cohort"] and (a["year"], b["year"]) in ((2000, 2010), (2010, 2022))]
R["cohort_falls"] = {"intervals": len(falls), "white_fell": sum(f[3] for f in falls), "exceptions": [[f[0], f[1], f[2]] for f in falls if not f[3]]}
R["cohorts_birth"] = [{"cohort": int(c0), "branca": float(b), "parda": float(pd_), "preta": float(p)} for c0, b, pd_, p in con.execute(f"""
    SELECT (year // 5) * 5, avg((trim(RACACOR) = '1')::INT), avg((trim(RACACOR) = '4')::INT), avg((trim(RACACOR) = '2')::INT)
    FROM read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)
    WHERE trim(RACACOR) IN ('1','2','3','4','5') AND year BETWEEN 2000 AND 2009 GROUP BY 1 ORDER BY 1""").fetchall()]

# ------------------------------------------------------------------ 7. three readings of the same woman, with bootstrap intervals
RACES5 = ["white", "black", "brown", "indigenous", "asian"]
C5 = {"1": 0, "2": 1, "4": 2, "5": 3, "3": 4}
Bf = "[" + ", ".join(f"'{p.replace(chr(92), '/')}'" for p in sorted(glob.glob(str(CH / "B_*.parquet")))) + "]"
ix = "CASE {c} " + " ".join(f"WHEN '{r}' THEN {i}" for i, r in enumerate(RACES5)) + " END"
w = pq.read_table(CH / "women.parquet")
comp_w = mr.composition(pq.read_table(OB / "births_2020_2021.parquet"))
year, linkedw, pairs = mr.prepare(w, comp_w, mr.WOMEN)
bandw = mr.age_band_years(np.asarray(w["age_years"].to_numpy(zero_copy_only=False), dtype=float))
sel = linkedw & (bandw >= 0)
pr = pairs(linkedw)
decw = np.array([C5.get(v, -1) for v in np.asarray(w["declared"].to_pylist(), dtype=object)[sel]])
regw = (np.asarray(w["uf"].to_pylist())[sel] // 10).astype(int)
con.register("wl", pa.table({"id": np.asarray(w["id"].to_pylist(), dtype=object)[sel].tolist(), "j": decw.tolist(), "phi": pr.phi.tolist(), "region": regw.tolist()}))
tt = con.execute(f"""SELECT wl.j, {ix.format(c='b."patient.race"')} h, {ix.format(c='b."deceased.race"')} k, wl.phi, wl.region
                     FROM wl JOIN read_parquet({Bf}) b ON b.r = wl.id""").df().dropna()
tt = tt[tt.j >= 0].astype({"j": int, "h": int, "k": int, "region": int})
pif = np.zeros((6, 5))
for r in range(1, 6):
    m = (regw == r) & (decw >= 0)
    pif[r] = np.bincount(decw[m], minlength=5) / max(m.sum(), 1)


def three(d):
    T3 = np.zeros((5, 5, 5))
    np.add.at(T3, (d.j.to_numpy(), d.h.to_numpy(), d.k.to_numpy()), 1.0)
    hk = np.zeros((6, 5, 5))
    np.add.at(hk, (d.region.to_numpy(), d.h.to_numpy(), d.k.to_numpy()), d.phi.to_numpy())
    T3 = np.maximum(T3 - np.einsum("rj,rhk->jhk", pif, hk), 0)
    out = []
    for j in range(3):
        out += [T3[j, j].sum() / T3[j].sum(), T3[j, :, j].sum() / T3[j].sum()] + [T3[j, h, j] / max(T3[j, h].sum(), 1e-9) for h in range(3)]
    return np.array(out)


point = three(tt)
rng = np.random.default_rng(0)
boot = np.array([three(tt.iloc[rng.integers(0, len(tt), len(tt))]) for _ in range(400)])
se3 = boot.std(0)
N3 = ["Branca", "Preta", "Parda"]
R["triples"] = {"women_deaths": int(w.num_rows), "linked": int(linkedw.sum()), "with_three": int(len(tt)), "false_share": float(tt.phi.mean()), "by_declared": {}}
for j in range(3):
    o = j * 5
    R["triples"]["by_declared"][N3[j]] = {"hospital": e(point[o], se3[o]), "certificate": e(point[o + 1], se3[o + 1]),
                                          "certificate_given_hospital": {N3[h]: e(point[o + 2 + h], se3[o + 2 + h]) for h in range(3)}}
a = con.execute(f"""SELECT {ix.format(c='"mother.race"')} j, {ix.format(c='"patient.race"')} h, count(*) FROM '{(CH / "A_2022.parquet").as_posix()}'
                    GROUP BY 1, 2 HAVING j IS NOT NULL AND h IS NOT NULL""").fetchall()
A2 = np.zeros((5, 5))
for j, h, n in a:
    A2[int(j), int(h)] = n
R["delivery"] = {"pairs": float(A2.sum()), "hospital_as_declared": {N3[j]: e(A2[j, j] / A2[j].sum(), np.sqrt(A2[j, j] / A2[j].sum() * (1 - A2[j, j] / A2[j].sum()) / A2[j].sum())) for j in range(3)}}


# ------------------------------------------------------------------ 10. reporting the linkage (RECORD 12, STROBE 12-14): flow, linked against unlinked,
# missing race, cluster bootstrap by municipality, and the rate under the conventional denominator
SIMQ = f"read_parquet('{LAKE}/SIM/SIM_DO_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
flow = con.execute(f"""WITH d AS (SELECT SEXO, CODMUNRES, try_strptime(trim(DTNASC), '%d%m%Y') b, try_strptime(trim(DTOBITO), '%d%m%Y') o FROM {SIMQ}
                       WHERE year BETWEEN 2013 AND 2023)
                       SELECT count(*) FILTER (date_diff('day', b, o) BETWEEN 0 AND 364),
                              count(*) FILTER (date_diff('day', b, o) BETWEEN 0 AND 364 AND trim(SEXO) IN ('1', '2') AND substr(trim(CODMUNRES), 3, 4) <> '0000'),
                              count(*) FILTER (date_diff('day', b, o) BETWEEN 0 AND 364 AND (trim(SEXO) NOT IN ('1', '2') OR SEXO IS NULL)),
                              count(*) FILTER (date_diff('day', b, o) BETWEEN 0 AND 364 AND substr(trim(CODMUNRES), 3, 4) = '0000') FROM d""").fetchone()
R["infants"]["flow"] = {"lake_infant_deaths": int(flow[0]), "with_sex_and_municipality": int(flow[1]), "no_sex": int(flow[2]), "no_municipality": int(flow[3]),
                        "candidate_deaths": float(R["infant_rates"]["deaths"]), "linked_no_mother_race": int(L.linked.sum() - len(LL))}
Lx = L.assign(size=pd.cut(L.births_year, [s[0] for s in SIZES] + [10**9], labels=[s[2] for s in SIZES], right=False))
R["infants"]["linked_share"] = {
    "by_certified": {(NAME.get(k, "other")): float(x.linked.mean()) for k, x in Lx.assign(rc=Lx.rec.where(Lx.rec.isin(RACES), "other")).groupby("rc")},
    "by_size": {str(k): float(x.linked.mean()) for k, x in Lx.groupby("size", observed=True)},
    "by_year": {int(k): float(x.linked.mean()) for k, x in Lx.groupby("year")},
    "by_region": {REGION[int(k)]: float(x.linked.mean()) for k, x in Lx.groupby("region") if int(k) in REGION},
    "by_age": {lab: float(Lx[(Lx.age_days >= lo) & (Lx.age_days < hi)].linked.mean()) for lab, lo, hi in (("0-6 d", 0, 7), ("7-27 d", 7, 28), ("28-364 d", 28, 365))}}
# the certified race left blank, by mother's race (linked deaths); and the certified rate ratio when a blank certificate takes the mother's race
blank = LL[~LL.rec.isin(RACES)]
R["infants"]["blank_by_mother"] = {NAME[j]: float((~LL[LL.dec == j].rec.isin(RACES)).mean()) for j in ("white", "brown", "black")}
ci_imp = certified("infants")[:4].copy()
ci_imp += np.array([(blank.dec == j).sum() for j in RACES], float) / max(len(blank), 1) * float((~L.rec.isin(RACES)).sum())
R["infant_rates"]["ratio_certificate_blank_as_mother"] = float((ci_imp[0] / bi[0]) / (ci_imp[2] / bi[2]))
# the linkage's proportions with a bootstrap over municipalities (pairs cluster by place): 400 resamples
cells_ = [("white", "white"), ("brown", "brown"), ("black", "black"), ("brown", "white"), ("black", "brown"), ("white", "brown")]
mun_ids = LL.mun6.astype(str).to_numpy()
codes, inv_ = np.unique(mun_ids, return_inverse=True)
den = {j: np.bincount(inv_, weights=(LL.dec == j).to_numpy(float), minlength=len(codes)) for j in ("white", "brown", "black")}
num = {(j, k): np.bincount(inv_, weights=((LL.dec == j) & (LL.rec == k)).to_numpy(float), minlength=len(codes)) for j, k in cells_}
rng2 = np.random.default_rng(1)
bs = {c: [] for c in cells_}
for _ in range(400):
    pick = np.bincount(rng2.integers(0, len(codes), len(codes)), minlength=len(codes))
    for j, k in cells_:
        bs[(j, k)].append((num[(j, k)] * pick).sum() / (den[j] * pick).sum())
R["infants"]["cluster_bootstrap"] = {f"{NAME[j]}>{NAME[k]}": {"est": float(num[(j, k)].sum() / den[j].sum()), "se": float(np.std(bs[(j, k)])),
                                                               "se_binomial": float(np.sqrt(num[(j, k)].sum() / den[j].sum() * (1 - num[(j, k)].sum() / den[j].sum()) / den[j].sum()))}
                                     for j, k in cells_}
# the conventional rate at 1-4 years: certified deaths over the population by race (population account, the census's classification), years in
# which every child aged 1-4 was born from 2012, against the same deaths over births by mother's race and against the mother's race
POPA = f"'{LAKE}/modelled/population_account/population-account-9/estimates.parquet'"
pop14 = dict(con.execute(f"SELECT race, sum(population) FROM {POPA} WHERE year BETWEEN 2016 AND 2024 AND age BETWEEN 1 AND 4 GROUP BY 1").fetchall())
w16 = "age BETWEEN 1 AND 4 AND year >= 2016"
r16 = rates("children", w16, range(1, 5), range(2016, 2025))
c16 = certified("children", w16)[:4]
pyr = np.array([pop14["branca"], pop14["preta"], pop14["parda"], pop14["indigena"]])
R["children"]["1-4"]["conventional_2016_2024"] = {
    "ratio_mother": r16["ratio_mother"]["Branca"], "ratio_certificate_births": r16["ratio_certificate"]["Branca"],
    "ratio_certificate_population": float((c16[0] / pyr[0]) / (c16[2] / pyr[2])),
    "rate_certificate_population": {NAME[j]: float(1e5 * c16[i] / pyr[i]) for i, j in enumerate(RACES)},
    "population_person_years": {NAME[j]: float(pyr[i]) for i, j in enumerate(RACES)}, "births_person_years": r16["person_years"], "deaths": r16["deaths"]}
# the same comparison for infants: certified deaths over the population under one year by race in the population account
pop0 = dict(con.execute(f"SELECT race, sum(population) FROM {POPA} WHERE year BETWEEN 2013 AND 2023 AND age = 0 GROUP BY 1").fetchall())
p0 = np.array([pop0["branca"], pop0["preta"], pop0["parda"], pop0["indigena"]])
R["infant_rates"]["ratio_certificate_population"] = float((ci[0] / p0[0]) / (ci[2] / p0[2]))
# a linked cohort with the same design (Reboucas et al. 2022, Table 2): crude rates per 100,000 person-years by mother's race, births 2012-2018
REB = {"1-4": (38.24, 55.19), "under 1": (950.98, 1201.0)}
R["reboucas"] = {k: {"white": a, "brown": b, "ratio": a / b} for k, (a, b) in REB.items()}

# the estimator assumes that the deceased is found among the candidates (t) equally often whatever the mother's race; the White to Brown ratio
# by the mother's race scales by t(Brown) / t(White) when it does not: the ratio for found shares differing by up to 10 points either way
r14m = R["children"]["1-4"]["rates"]["ratio_mother"]["Branca"]["est"]
t0_ = R["children"]["1-4"]["matrix"]["found"]
R["children"]["1-4"]["t_sensitivity"] = {f"{tw:.2f}|{tp:.2f}": r14m * tp / tw for tw, tp in ((t0_ - 0.1, t0_), (t0_, t0_ - 0.1), (t0_ + 0.05, t0_ - 0.05), (t0_ - 0.05, t0_ + 0.05))}

# ------------------------------------------------------------------ 11. audit 4: the infant ratio by mother's race from the linkage itself, with a delete-one-state
# jackknife; the stored linkage's quality per year (threshold, estimated false discoveries, agreement on fields not used to link)
lk_births = births[1:12].sum(0)                                         # cohorts 2013-2023: (municipality, races)
lk_state = (muns // 10000).astype(int)


def link_ratio(drop_uf=None):
    sel = LL if drop_uf is None else LL[LL.uf != drop_uf]
    bm = lk_births if drop_uf is None else lk_births[lk_state != drop_uf]
    n = {j: (sel.dec == j).sum() for j in ("white", "brown", "black", "indigenous")}
    b = {"white": bm[:, 0].sum(), "black": bm[:, 1].sum(), "brown": bm[:, 3].sum(), "indigenous": bm[:, 4].sum()}
    return {j: (n[j] / b[j]) / (n["brown"] / b["brown"]) for j in ("white", "black", "indigenous")}


full_lr = link_ratio()
loo_lr = [link_ratio(u) for u in UF]
R["infant_rates"]["ratio_mother_linkage"] = {}
for j in ("white", "black", "indigenous"):
    v = np.array([x[j] for x in loo_lr])
    R["infant_rates"]["ratio_mother_linkage"][NAME[j]] = {"est": float(full_lr[j]), "se": float(np.sqrt((len(v) - 1) / len(v) * ((v - v.mean()) ** 2).sum())),
                                                          "loo_min": float(v.min()), "loo_max": float(v.max())}
# the candidate estimator's infant ratio with the same jackknife
loo_c = []
for u in UF:
    t_, v_, d_ = diff("infants", f"uf <> {u}")
    rw = t_.sum(1)
    bm = lk_births[lk_state != u]
    bb = np.array([bm[:, 0].sum(), bm[:, 1].sum(), bm[:, 3].sum(), bm[:, 4].sum()])
    loo_c.append((rw[0] / bb[0]) / (rw[2] / bb[2]))
v = np.array(loo_c)
R["infant_rates"]["ratio_mother"]["Branca"]["se_jackknife"] = float(np.sqrt((len(v) - 1) / len(v) * ((v - v.mean()) ** 2).sum()))
R["infant_rates"]["ratio_mother"]["Branca"]["se_counts"] = R["infant_rates"]["ratio_mother"]["Branca"]["se"]
R["infant_rates"]["ratio_mother"]["Branca"]["se"] = max(R["infant_rates"]["ratio_mother"]["Branca"]["se"], R["infant_rates"]["ratio_mother"]["Branca"]["se_jackknife"])
quality = {}
for yr in range(2013, 2024):
    _, rep = mr._stored_pairs(settings, "sim_infant_deaths_to_sinasc", yr, [])
    quality[yr] = {"threshold_bits": rep.get("threshold_bits"), "fdr_percent": rep.get("estimated_fdr_percent"), "fdr_upper95_percent": rep.get("fdr_upper95_percent"),
                   "linked_share": rep.get("linked_share"), "method": rep.get("method"),
                   "validations": {k: v["agreement_percent"] for k, v in (rep.get("validations") or {}).items()}}
R["infants"]["link_quality"] = quality


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return float(o)
    return o


out = PAPER / "results" / "results.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(clean(R), indent=1), encoding="utf-8")
print("written", out, "keys", list(R))
