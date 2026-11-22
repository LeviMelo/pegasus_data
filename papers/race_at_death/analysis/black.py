"""Paper 3, the Black category: who records a Black person as Black, the hospital's practice against the certificate's, and the mother's own
hospital record against her infant's certificate. Into results/black.json.

Inputs: data/infant_linkage_delivery.parquet and data/delivery_by_facility.parquet (counts.py delivery), results/results.json and
results/spatial.json (results.py, spatial.py), the census mother-child pairs.

    python papers/race_at_death/analysis/black.py      (about a minute)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).parent))
PAPER = Path(__file__).resolve().parents[1]
DATA, RES = PAPER / "data", PAPER / "results"
R = json.loads((RES / "results.json").read_text(encoding="utf-8"))
SP = json.loads((RES / "spatial.json").read_text(encoding="utf-8"))
CODE = {"1": "white", "2": "black", "3": "asian", "4": "brown", "5": "indigenous"}
WORD = {"white": "white", "black": "black", "brown": "brown", "indigenous": "indigenous", "asian": "asian"}
B: dict = {}


def prop(k, n):
    p = k / n
    return {"est": float(p), "se": float(np.sqrt(max(p * (1 - p), 1e-12) / n)), "n": int(n)}


# ------------------------------------------------------------------ 1. the hospital at delivery records the mother herself
F = pd.read_parquet(DATA / "delivery_by_facility.parquet").rename(columns={"admission.facility": "fac", "mother.race": "dec", "patient.race": "hosp", "l_count": "n"})
F["dec"], F["hosp"] = F.dec.map(lambda v: WORD.get(v, v)), F.hosp.map(lambda v: WORD.get(v, v))
# a hospital whose records are over a tenth "asian" writes a default, not a race (ADR-0128): left out
share_asian = F[F.hosp.notna()].groupby("fac").apply(lambda d: d.n[d.hosp == "asian"].sum() / d.n.sum())
bad = set(share_asian[share_asian > 0.10].index)
F = F[~F.fac.isin(bad)]
known = F[F.hosp.isin(["white", "black", "brown", "indigenous", "asian"]) & F.dec.isin(["white", "black", "brown", "indigenous"])]
B["hospital"] = {"facilities_left_out": len(bad), "pairs_with_both": int(known.n.sum())}
B["hospital"]["matrix"] = {j: {h: prop(known[(known.dec == j) & (known.hosp == h)].n.sum(), known[known.dec == j].n.sum()) for h in ("white", "black", "brown")}
                           for j in ("white", "black", "brown")}
B["hospital"]["black_by_year"] = {int(y): prop(d[(d.dec == "black") & (d.hosp == "black")].n.sum(), d[d.dec == "black"].n.sum())
                                  for y, d in known.groupby("birth_year")}
B["hospital"]["blank_black"] = prop(F[(F.dec == "black") & F.hosp.isna()].n.sum(), F[F.dec == "black"].n.sum())
# each facility's practice: the share of Black mothers it records as Black (facilities with 30 or more Black mothers, pooled over years)
fb = known[known.dec == "black"].groupby("fac").apply(lambda d: pd.Series({"k": d.n[d.hosp == "black"].sum(), "n": d.n.sum()}))
fb = fb[fb.n >= 30]
fb["rate"] = fb.k / fb.n
B["hospital"]["facilities"] = {"n": int(len(fb)), "p10": float(fb.rate.quantile(0.1)), "p50": float(fb.rate.median()), "p90": float(fb.rate.quantile(0.9))}

# ------------------------------------------------------------------ 2. the infant's certificate against the hospital's record of the same infant's mother
I = pd.read_parquet(DATA / "infant_linkage_delivery.parquet")
I["dec"], I["rec"] = I.declared.map(CODE), I.recorded.map(CODE)
I["mh"] = I.mother_hospital_race.map(lambda v: WORD.get(v, v))
I = I[I.linked & I.dec.isin(["white", "black", "brown"])]
B["individual"] = {"linked": int(len(I)), "with_hospital_record": int(I.mh.notna().sum()),
                   "with_hospital_record_black": int((I.mh.notna() & (I.dec == "black")).sum())}
blk = I[(I.dec == "black") & I.mh.isin(["white", "black", "brown"])]
B["individual"]["black_mother_by_hospital"] = {h: {c: prop((d.rec == c).sum(), len(d)) for c in ("white", "black", "brown")} for h, d in blk.groupby("mh")}
brn = I[(I.dec == "brown") & I.mh.isin(["white", "black", "brown"])]
B["individual"]["brown_mother_by_hospital"] = {h: {c: prop((d.rec == c).sum(), len(d)) for c in ("white", "black", "brown")} for h, d in brn.groupby("mh")}
# the facility's practice against the certificate where the infant died, Black mothers' infants who died in a facility with a measured practice
I["death_estab"] = I.death_estab.astype(str).str.strip()
D = blk.merge(fb[["rate", "n"]].rename(columns={"n": "fac_black_mothers"}), left_on="death_estab", right_index=True, how="inner") if len(blk) else blk
Dall = I[I.dec == "black"].merge(fb[["rate"]], left_on=I[I.dec == "black"].death_estab.astype(str).str.strip(), right_index=True, how="inner")
Dall["y"] = (Dall.rec == "black").astype(int)
Dall["lrate"] = np.log((Dall.rate + 0.01) / (1 - Dall.rate + 0.01))
mc = pd.read_parquet(RES / "municipal_estimates.parquet")[["mun", "white_share"]]
Dall["mun6"] = Dall.mun.astype(str).str[:6]
Dall = Dall.merge(mc, left_on="mun6", right_on="mun", how="left", suffixes=("", "_m"))
Dall["lws"] = np.log(Dall.white_share.clip(0.005, 0.995) / (1 - Dall.white_share.clip(0.005, 0.995)))
Dall["region"] = (Dall.uf // 10).astype(str)
Dall = Dall.dropna(subset=["lws"])
B["facility_model"] = {"deaths": int(len(Dall)), "facilities": int(Dall.death_estab.nunique())}
for lab, f in (("practice", "y ~ lrate"), ("practice_composition", "y ~ lrate + bs(lws, df=3)"), ("practice_composition_region_year", "y ~ lrate + bs(lws, df=3) + C(region) + year")):
    m = smf.glm(f, data=Dall, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(Dall.mun6)[0]})
    b, se = m.params["lrate"], m.bse["lrate"]
    B["facility_model"][lab] = {"coef": float(b), "se": float(se), "or_per_logit": float(np.exp(b))}
# facility level: the certificate's rate for Black mothers' infants who died there against the facility's practice
g = Dall.groupby("death_estab").agg(cert=("y", "mean"), deaths=("y", "size"), rate=("rate", "first"))
g10 = g[g.deaths >= 10]
B["facility_level"] = {"facilities": int(len(g10)), "corr": float(np.corrcoef(g10.rate, g10.cert)[0, 1]),
                       "wcorr": float(np.cov(g10.rate, g10.cert, aweights=g10.deaths)[0, 1] / np.sqrt(np.cov(g10.rate, aweights=g10.deaths) * np.cov(g10.cert, aweights=g10.deaths)))}
g10.reset_index().to_parquet(RES / "black_facilities.parquet", index=False)

# ------------------------------------------------------------------ 3. the ladder: who records a Black person as Black
IL = R["infants"]["linkage"]["rows"]["Preta"]
CB = R["infants"]["cluster_bootstrap"]["Preta>Preta"]
B["ladder"] = {
    "family_child_0": R["census"]["by_age"]["0"]["Preta"]["Preta"]["est"],
    "family_child_1_4": R["census"]["by_band"]["1-4"]["Preta"]["Preta"]["est"],
    "family_child_5_9": R["census"]["by_band"]["5-9"]["Preta"]["Preta"]["est"],
    "certificate_infant": CB,
    "certificate_1_4": R["children"]["1-4"]["without_large"]["matrix"]["rows"]["Preta"]["Preta"],
    "certificate_5_9": R["children"]["5-9"]["without_large"]["matrix"]["rows"]["Preta"]["Preta"],
    "hospital_mother_delivery": B["hospital"]["matrix"]["black"]["black"],
    "hospital_adult_women_death": R["triples"]["by_declared"]["Preta"]["hospital"],
    "certificate_adult_women": R["triples"]["by_declared"]["Preta"]["certificate"],
    "infant_certified_brown": IL["Parda"], "infant_certified_white": IL["Branca"]}
B["births_black_share"] = {r["year"]: r["preta"] for r in R["form"] if r["year"] >= 2012}

# ------------------------------------------------------------------ audit 1 of paper 3
from statsmodels.stats.contingency_tables import StratifiedTable  # noqa: E402

# net counts: how many each record calls Black against how many declared Black (admissions with a race; and with blanks counted as not Black)
allk = F[F.dec.isin(["white", "black", "brown", "indigenous"])]
withrace = allk[allk.hosp.isin(["white", "black", "brown", "indigenous", "asian"])]
B["net"] = {"hospital_recorded_black": int(withrace[withrace.hosp == "black"].n.sum()), "hospital_declared_black": int(withrace[withrace.dec == "black"].n.sum()),
            "hospital_blank_share": {j: float(allk[(allk.dec == j) & allk.hosp.isna()].n.sum() / allk[allk.dec == j].n.sum()) for j in ("white", "black", "brown")},
            "hospital_black_of_all_black_declared": float(allk[(allk.dec == "black") & (allk.hosp == "black")].n.sum() / allk[allk.dec == "black"].n.sum())}
B["net"]["hospital_ratio"] = B["net"]["hospital_recorded_black"] / B["net"]["hospital_declared_black"]
Iall = I.copy()
B["net"]["certificate_recorded_black"] = int((Iall.rec == "black").sum())
B["net"]["certificate_declared_black"] = int((Iall.dec == "black").sum())
B["net"]["certificate_ratio"] = B["net"]["certificate_recorded_black"] / B["net"]["certificate_declared_black"]
B["net"]["certificate_brown_to_black"] = prop(((Iall.dec == "brown") & (Iall.rec == "black")).sum(), (Iall.dec == "brown").sum())
# the hospital's classification of Black mothers with a bootstrap over hospitals
kb = known[known.dec == "black"].groupby(["fac", "hosp"]).n.sum().unstack(fill_value=0)
for c in ("white", "black", "brown"):
    if c not in kb:
        kb[c] = 0
tot = kb.sum(1).to_numpy()
rng = np.random.default_rng(3)
boot_ = {c: [] for c in ("white", "black", "brown")}
for _ in range(400):
    w = np.bincount(rng.integers(0, len(kb), len(kb)), minlength=len(kb))
    for c in boot_:
        boot_[c].append((kb[c].to_numpy() * w).sum() / (tot * w).sum())
B["hospital"]["black_bootstrap"] = {c: {"est": float(kb[c].sum() / tot.sum()), "se": float(np.std(boot_[c]))} for c in boot_}
# the hospital's practice measured at the hospital where the mother delivered, and where the infant died
blkh = I[(I.dec == "black") & I.delivery_facility.notna()].copy()
blkh["delivery_facility"] = blkh.delivery_facility.astype(str).str.strip()
blkh["death_estab"] = blkh.death_estab.astype(str).str.strip()
B["individual"]["died_where_delivered"] = float((blkh.delivery_facility == blkh.death_estab).mean())
blkh = blkh[~blkh.delivery_facility.isin(bad)]
B["individual"]["black_mothers_excluded_hospitals"] = int(((I.dec == "black") & I.delivery_facility.astype(str).str.strip().isin(bad)).sum())
Dd = blkh.merge(fb[["rate"]], left_on="delivery_facility", right_index=True, how="inner")
Dd["y"] = (Dd.rec == "black").astype(int)
Dd["lrate"] = np.log((Dd.rate + 0.01) / (1 - Dd.rate + 0.01))
Dd["mun6"] = Dd.mun.astype(str).str[:6]
Dd = Dd.merge(mc, left_on="mun6", right_on="mun", how="left", suffixes=("", "_m"))
Dd["lws"] = np.log(Dd.white_share.clip(0.005, 0.995) / (1 - Dd.white_share.clip(0.005, 0.995)))
Dd["region"] = (Dd.uf // 10).astype(str)
Dd = Dd.dropna(subset=["lws"])
B["facility_model_delivery"] = {"deaths": int(len(Dd)), "facilities": int(Dd.delivery_facility.nunique())}
for lab, f in (("practice", "y ~ lrate"), ("practice_composition_region_year", "y ~ lrate + bs(lws, df=3) + C(region) + year")):
    m = smf.glm(f, data=Dd, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(Dd.mun6)[0]})
    B["facility_model_delivery"][lab] = {"coef": float(m.params["lrate"]), "se": float(m.bse["lrate"]), "or_per_logit": float(np.exp(m.params["lrate"]))}
# person against place: within the same delivery hospital, the infant certified Black by whether the hospital recorded the mother Black (Mantel-Haenszel)
tabs = []
for _, d_ in blkh[blkh.mh.isin(["white", "black", "brown"])].groupby("delivery_facility"):
    a = ((d_.mh == "black") & (d_.rec == "black")).sum()
    b = ((d_.mh == "black") & (d_.rec != "black")).sum()
    c = ((d_.mh != "black") & (d_.rec == "black")).sum()
    e = ((d_.mh != "black") & (d_.rec != "black")).sum()
    if (a + b) > 0 and (c + e) > 0:
        tabs.append(np.array([[a, b], [c, e]], float))
st = StratifiedTable(tabs)
lo, hi = st.oddsratio_pooled_confint()
B["individual"]["within_hospital_or"] = {"est": float(st.oddsratio_pooled), "lo": float(lo), "hi": float(hi), "hospitals": len(tabs)}
# selection: Black mothers' infants with and without a delivery record
B["individual"]["black_with_record"] = prop(((I.dec == "black") & I.mh.notna() & (I.rec == "black")).sum(), ((I.dec == "black") & I.mh.notna()).sum())
B["individual"]["black_without_record"] = prop(((I.dec == "black") & I.mh.isna() & (I.rec == "black")).sum(), ((I.dec == "black") & I.mh.isna()).sum())
# the infant share in the municipalities the estimator covers after infancy (fewer than 25,600 births a year)
mby = pd.read_parquet(RES / "municipal_estimates.parquet")[["mun", "births_year"]]
Ib = I.assign(mun6=I.mun.astype(str).str[:6]).merge(mby, left_on="mun6", right_on="mun", how="left", suffixes=("", "_y"))
sm_ = Ib[(Ib.dec == "black") & (Ib.births_year < 25600)]
B["ladder"]["certificate_infant_below_25600"] = prop((sm_.rec == "black").sum(), len(sm_))
# the hospital's trend in log-odds per decade (yearly counts)
hy = pd.DataFrame([{"year": int(y), "k": v["est"] * v["n"], "n": v["n"]} for y, v in B["hospital"]["black_by_year"].items()])
mt = smf.glm("p ~ yc", data=hy.assign(p=hy.k / hy.n, yc=(hy.year - 2018) / 10), family=sm.families.Binomial(), var_weights=hy.n).fit(scale="X2")
B["hospital"]["trend_per_decade"] = {"est": float(mt.params.iloc[1]), "se": float(mt.bse.iloc[1])}

# the delivery linkage's own reports, births of 2012-2023
import glob  # noqa: E402

from pegasus_data.config import load_settings  # noqa: E402

rep_ = {}
for f in sorted(glob.glob(f"{load_settings().lake_dir}/links/sinasc_births_to_delivery_admission/probabilistic_BR_20*_*.json")):
    yr = int(Path(f).name.split("_")[2])
    if 2012 <= yr <= 2023:
        r = json.loads(Path(f).read_text(encoding="utf-8"))
        rep_[yr] = {"linked_share": r["linked_share"], "fdr_percent": r["estimated_fdr_percent"],
                    "obstetric": r["validations"]["obstetric diagnosis (ICD-10 chapter XV)"]["agreement_percent"], "residence": r["validations"]["residence agrees"]["agreement_percent"]}
B["delivery_link"] = rep_


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    return o


(RES / "black.json").write_text(json.dumps(clean(B), indent=1), encoding="utf-8")
print(json.dumps(clean({k: v for k, v in B.items() if k in ("hospital", "individual", "facility_model", "facility_level")}), indent=1)[:4000])
