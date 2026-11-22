"""Paper 3, review 3: the practice effect per standard deviation and through the mother's record; the hospital's record within region; the
association where a shared upstream record is least likely (no prenatal visits, deaths at home); the certificate's and the hospital's trends
without 2023, when the hospital's race field changed. Adds the key "review3" to results/mechanism.json (part 1 data only, light).

    python papers/race_at_death/analysis/mechanism3.py
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.contingency_tables import StratifiedTable

warnings.simplefilter("ignore")
HERE = Path(__file__).resolve().parents[1]
DATA, RES = HERE / "data", HERE / "results"
OUT = RES / "mechanism.json"
M = json.loads(OUT.read_text(encoding="utf-8"))
RACE = {"1": "white", "2": "black", "3": "asian", "4": "brown", "5": "indigenous"}
REG = {"1": "North", "2": "Northeast", "3": "Southeast", "4": "South", "5": "Centre-West"}

D = pd.read_parquet(DATA / "infant_linkage_delivery.parquet")
D = D[D.linked & (D.age_days >= 0)].copy()
D["mun6"] = D.mun.astype(str).str[:6]
D["dec"], D["rec"] = D.declared.map(RACE), D.recorded.map(RACE)
D["mh"] = D.mother_hospital_race
D["region"] = (D.uf // 10).astype(str)
for c in ("death_estab", "delivery_facility"):
    D[c] = D[c].astype(str).str.strip().replace({"None": None, "nan": None, "": None})
B = D[(D.dec == "black") & D.mh.isin(["white", "brown", "black"]) & D.delivery_facility.notna()].copy()
B["y"] = (B.rec == "black").astype(int)
B["hb"] = (B.mh == "black").astype(int)
out = {"n": int(len(B)), "hospital_black_same_infants": float(B.hb.mean()), "certified_black_same_infants": float(B.y.mean())}


def mh(df, strata):
    tabs = []
    for _, d_ in df.groupby(strata):
        t = np.array([[((d_.hb == 1) & (d_.y == 1)).sum(), ((d_.hb == 1) & (d_.y == 0)).sum()],
                      [((d_.hb == 0) & (d_.y == 1)).sum(), ((d_.hb == 0) & (d_.y == 0)).sum()]], float)
        if t[0].sum() > 0 and t[1].sum() > 0 and t[:, 0].sum() > 0 and t[:, 1].sum() > 0:
            tabs.append(t)
    if not tabs:
        return None
    st = StratifiedTable(tabs)
    lo, hi = st.oddsratio_pooled_confint()
    return {"est": float(st.oddsratio_pooled), "lo": float(lo), "hi": float(hi), "strata": len(tabs), "deaths": int(sum(t.sum() for t in tabs))}


# 1. the hospital's record within region: the three cells standardised to the regions of all these infants, and the MH odds ratio over regions
wr = B.region.value_counts(normalize=True)
cell = {}
for h, g in B.groupby("mh"):
    r_ = g.groupby("region").y.agg(["mean", "size"])
    common = r_.index.intersection(wr.index)
    cell[h] = {"crude": float(g.y.mean()), "region_standardised": float((r_.loc[common, "mean"] * wr[common]).sum() / wr[common].sum()), "n": int(len(g)),
               "south_share": float((g.region == "4").mean())}
out["by_hospital_record_region_standardised"] = cell
out["mh_over_regions"] = mh(B, "region")
# 2. where a shared upstream record is least likely: no prenatal visit (no prenatal card), deaths at home, within the delivery hospital
B["visits_"] = B.visits.astype(str).str.strip()
out["within_hospital_by_visits"] = {"none": mh(B[B.visits_ == "1"], "delivery_facility"), "1-6": mh(B[B.visits_.isin(["2", "3"])], "delivery_facility"),
                                    "7 or more": mh(B[B.visits_ == "4"], "delivery_facility")}
out["home_deaths"] = {"by_record": {h: {"y": float(g.y.mean()), "n": int(len(g))} for h, g in B[B.death_place.astype(str).str.strip() == "3"].groupby("mh")},
                      "mh_over_regions": mh(B[B.death_place.astype(str).str.strip() == "3"], "region")}
# 3. the practice effect: per standard deviation of the shrunk practice, total (without the mother's record) and direct (with it)
fit = M["black"]["practice_loo_eb"]
prior = M["black"]["practice_prior"]
a_, b_ = prior["alpha"], prior["beta"]
rng = np.random.default_rng(3)
sd_logit = float(np.std(np.log((x := rng.beta(a_, b_, 200000).clip(1e-4, 1 - 1e-4)) / (1 - x))))
F = pd.read_parquet(DATA / "delivery_by_facility.parquet").rename(columns={"admission.facility": "fac", "mother.race": "dec", "patient.race": "hosp", "l_count": "n"})
F["fac"] = F.fac.astype(str).str.strip()
fb = F[(F.dec == "black") & F.hosp.isin(["white", "brown", "black", "indigenous", "asian"])].groupby("fac").n.sum()
fk = F[(F.dec == "black") & (F.hosp == "black")].groupby("fac").n.sum()
eb = ((fk.reindex(fb.index).fillna(0) + a_) / (fb + a_ + b_))[fb >= 30]
sd_hosp = float(np.std(np.log(eb / (1 - eb))))
per = {}
for k in ("practice", "practice_composition_region_year", "practice_person"):
    c, s = fit[k]["coef"], fit[k]["se"]
    per[k] = {"or_per_sd": float(np.exp(c * sd_hosp)), "lo": float(np.exp((c - 1.96 * s) * sd_hosp)), "hi": float(np.exp((c + 1.96 * s) * sd_hosp))}
out["practice_per_sd"] = per | {"sd_logit_hospitals": sd_hosp, "sd_logit_prior": sd_logit,
                                "share_through_mothers_record": float(1 - fit["practice_person"]["coef"] / fit["practice_composition_region_year"]["coef"])}
# 4. the trends without 2023 (the hospital's race field was filled from 2023), on the same infants
J = B[B.year <= 2022][["y", "hb", "year"]].reset_index().rename(columns={"index": "infant"})
two = pd.concat([J.assign(record="certificate", z=J.y), J.assign(record="hospital", z=J.hb)])
two["t"] = (two.year - 2018) / 10
mm = smf.glm("z ~ C(record) * t", data=two, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": two.infant})
out["joint_trend_2013_2022"] = {"certificate_per_decade": float(mm.params["t"]), "certificate_se": float(mm.bse["t"]),
                                "hospital_minus_certificate": float(mm.params["C(record)[T.hospital]:t"]),
                                "difference_se": float(mm.bse["C(record)[T.hospital]:t"]), "n_infants": int(len(J))}
std = M["black"]["certificate_by_year_standardised"]
xs = np.array([int(y) for y in std if int(y) <= 2022], float)
ys = np.array([std[str(int(y))]["standardised_2013"] for y in xs])
out["standardised_slope_2013_2022_per_decade_points"] = float(np.polyfit(xs, ys, 1)[0] * 1000)
# 5. the informative deaths of the elsewhere stratum
els = B[(B.delivery_facility != B.death_estab) & B.death_estab.notna()]
out["elsewhere_informative"] = mh(els, "death_estab")
# 6. infants of Black mothers certified Black by region and year (all linked deaths with the mother's race; binomial errors)
KB = D[D.dec == "black"].assign(y=lambda x: (x.rec == "black").astype(int))
out["by_region_year"] = {f"{REG[r]}|{int(y)}": {"est": float(g.y.mean()), "se": float(np.sqrt(g.y.mean() * (1 - g.y.mean()) / len(g))), "n": int(len(g))}
                         for (r, y), g in KB.groupby(["region", "year"])}
M["review3"] = out
OUT.write_text(json.dumps(M, indent=1, default=float), encoding="utf-8")
print(json.dumps(out, indent=1, default=float)[:3500])
