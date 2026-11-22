"""Who records what: the tests the reviews of papers 1 and 3 asked for, on the linked infants and the linked deliveries.

Part 1 (data/infant_linkage_delivery.parquet; no new extraction):
  copy      does the certificate copy the birth record? Agreement with the mother's race, and the composition gradient, among deaths in the
            establishment of birth within a day of it (where the birth record lies at hand) against all others.
  black     paper 3: the hospital's record of the mother and the certificate within delivery hospitals (Mantel-Haenszel with Breslow-Day, and
            conditional logistic models adjusted for the mother and the child), separately for infants who died where they were delivered
            and elsewhere (death-establishment strata: a chart the certifier could not read); the delivery hospital's practice rebuilt
            (leave-one-out, empirical-Bayes shrunk, clustered by hospital); net ratios with bootstrap intervals; blank bounds; the rise of the
            certificate standardised for who the Black mothers were; the hospital and the certificate in one model on the same infants.
  cells     paper 1: the symmetric cells against composition (White mothers' infants certified Brown, Black mothers' infants certified Brown)
            and the composition at which the certificate and the family cross, with a bootstrap interval over municipalities.
Part 2 (data/infant_linkage_mechanism.parquet and data/deliveries/, from `counts.py mechanism`), when present:
  filler    the mother's race on the birth record and its agreement with the hospital by who filled the birth record (TPFUNCRESP)
  physician crossed random effects of the certifying physician (CRM, 2014-2018), the death establishment and the municipality
  occurrence deaths outside the municipality of residence: composition of residence against composition of occurrence
  movers    the same mother across births and hospitals: mother and hospital effects in the hospital's record of her race

    python papers/race_at_death/analysis/mechanism.py      -> results/mechanism.json
"""
import json
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.discrete.conditional_models import ConditionalLogit
from statsmodels.stats.contingency_tables import StratifiedTable

warnings.simplefilter("ignore")
HERE = Path(__file__).resolve().parents[1]
DATA, RES = HERE / "data", HERE / "results"
OUT = RES / "mechanism.json"
M = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
rng = np.random.default_rng(7)
RACE = {"1": "white", "2": "black", "3": "asian", "4": "brown", "5": "indigenous"}


def prop(k, n):
    p = k / n if n else float("nan")
    return {"est": float(p), "se": float(math.sqrt(p * (1 - p) / n)) if n else float("nan"), "n": int(n)}


def boot_mun(df, num, den, b=400):
    """A ratio of two counts (boolean columns ``num``, ``den`` of ``df``) and its standard error from a bootstrap over municipalities."""
    a = df.groupby("mun6")[[num, den]].sum()
    x, y = a[num].to_numpy(float), a[den].to_numpy(float)
    reps = []
    for _ in range(b):
        w = np.bincount(rng.integers(0, len(a), len(a)), minlength=len(a))
        reps.append((x * w).sum() / (y * w).sum())
    return {"est": float(x.sum() / y.sum()), "se": float(np.std(reps))}


# ------------------------------------------------------------------ the infants
D = pd.read_parquet(DATA / "infant_linkage_delivery.parquet")
D = D[D.linked & (D.age_days >= 0)].copy()
D["mun6"] = D.mun.astype(str).str[:6]
D["dec"], D["rec"] = D.declared.map(RACE), D.recorded.map(RACE)
D["mh"] = D.mother_hospital_race
E = pd.read_parquet(RES / "municipal_estimates.parquet")[["mun", "white_share", "births_year"]]
D = D.reset_index().merge(E, left_on="mun6", right_on="mun", how="left", suffixes=("", "_e")).set_index("index")
D["lws"] = np.log(D.white_share.clip(0.005, 0.995) / (1 - D.white_share.clip(0.005, 0.995)))
D["region"] = (D.uf // 10).astype(str)
for c in ("birth_estab", "death_estab", "delivery_facility"):
    D[c] = D[c].astype(str).str.strip().replace({"None": None, "nan": None, "": None})
D["same_estab"] = D.birth_estab.notna() & (D.birth_estab == D.death_estab)
D["early"] = D.age_days <= 1
D["stratum"] = np.where(D.same_estab & D.early, "birth establishment, 0-1 day",
                        np.where(D.same_estab, "birth establishment, 2-364 days", "elsewhere"))
K = D[D.dec.isin(["white", "brown", "black"])].copy()

# ------------------------------------------------------------------ copy: is the certificate the birth record copied?
copy = {"agreement": {}, "gradient_PW": {}, "PW": {}, "KK": {}}
for s, g in K.groupby("stratum"):
    copy["agreement"][s] = boot_mun(g.assign(a=g.rec == g.dec, one=True), "a", "one") | {"n": int(len(g))}
    pw = g[g.dec == "brown"].dropna(subset=["lws"])
    copy["PW"][s] = prop(int((pw.rec == "white").sum()), len(pw))
    kk = g[g.dec == "black"]
    copy["KK"][s] = prop(int((kk.rec == "black").sum()), len(kk))
    m = smf.glm("y ~ lws", data=pw.assign(y=(pw.rec == "white").astype(int)), family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(pw.mun6)[0]})
    copy["gradient_PW"][s] = {"coef": float(m.params["lws"]), "se": float(m.bse["lws"])}
copy["birth_establishment_share"] = float(K.same_estab.mean())
M["copy"] = copy
print("copy", json.dumps(copy["agreement"], indent=0)[:400], flush=True)

# ------------------------------------------------------------------ paper 3: the hospital's record of the mother and the certificate
B = K[(K.dec == "black") & K.mh.isin(["white", "brown", "black"]) & K.delivery_facility.notna()].copy()
B["y"] = (B.rec == "black").astype(int)
B["hb"] = (B.mh == "black").astype(int)
B["died_there"] = B.delivery_facility == B.death_estab
black = {"n": int(len(B))}


def mh(df, strata):
    tabs = []
    for _, d_ in df.groupby(strata):
        t = np.array([[((d_.hb == 1) & (d_.y == 1)).sum(), ((d_.hb == 1) & (d_.y == 0)).sum()],
                      [((d_.hb == 0) & (d_.y == 1)).sum(), ((d_.hb == 0) & (d_.y == 0)).sum()]], float)
        if t[0].sum() > 0 and t[1].sum() > 0 and t[:, 0].sum() > 0 and t[:, 1].sum() > 0:
            tabs.append(t)
    st = StratifiedTable(tabs)
    lo, hi = st.oddsratio_pooled_confint()
    bd = st.test_equal_odds()
    return {"est": float(st.oddsratio_pooled), "lo": float(lo), "hi": float(hi), "strata": len(tabs),
            "deaths": int(sum(t.sum() for t in tabs)), "breslow_day_p": float(bd.pvalue)}


black["mh_delivery_hospital"] = mh(B, "delivery_facility")
for lab, sub in (("died_where_delivered", B[B.died_there]), ("died_elsewhere", B[~B.died_there & B.death_estab.notna()])):
    black[f"mh_death_estab_{lab}"] = mh(sub, "death_estab")
    black[f"n_{lab}"] = int(len(sub))


def clogit(df, group, terms):
    X = pd.get_dummies(df[terms], drop_first=True, dtype=float)
    X = X.loc[:, X.std() > 0]
    r = ConditionalLogit(df.y.to_numpy(), X, groups=pd.factorize(df[group])[0]).fit(disp=0)
    return {"or": float(np.exp(r.params["hb"])), "lo": float(np.exp(r.params["hb"] - 1.96 * r.bse["hb"])),
            "hi": float(np.exp(r.params["hb"] + 1.96 * r.bse["hb"])), "n": int(len(df))}


Ba = B.assign(school=B.schooling.fillna("9").astype(str), age_mother=pd.cut(pd.to_numeric(B.mother_age, errors="coerce"), [0, 19, 34, 99]).astype(str),
              lbw=(pd.to_numeric(B.weight, errors="coerce") < 2500).astype(int), year_=B.year.astype(str), age_death=pd.cut(B.age_days, [-1, 6, 27, 364]).astype(str))
black["clogit_delivery_hospital_adjusted"] = clogit(Ba, "delivery_facility", ["hb", "school", "age_mother", "lbw", "year_", "age_death"])
black["clogit_death_estab_elsewhere"] = clogit(Ba[~Ba.died_there & Ba.death_estab.notna()], "death_estab", ["hb", "school", "age_mother", "lbw", "year_"])
black["clogit_death_estab_died_there"] = clogit(Ba[Ba.died_there], "death_estab", ["hb", "school", "age_mother", "lbw", "year_"])
# the non-monotone cell (mothers the hospital recorded White) by region
black["by_hospital_race_region"] = {f"{r}|{h}": prop(int(g.y.sum()), len(g)) for (r, h), g in K[(K.dec == "black") & K.mh.isin(["white", "brown", "black"])].assign(
    y=lambda x: (x.rec == "black").astype(int)).groupby(["region", "mh"])}

# the delivery hospital's practice rebuilt: leave the infant's own mother out, shrink to the hospitals' distribution, cluster by hospital
F = pd.read_parquet(DATA / "delivery_by_facility.parquet")
F = F.rename(columns={"admission.facility": "fac", "mother.race": "dec", "patient.race": "hosp", "l_count": "n"})
F["fac"] = F.fac.astype(str).str.strip()
fb = F[(F.dec == "black") & F.hosp.isin(["white", "brown", "black", "indigenous", "asian"])].groupby("fac").apply(
    lambda g: pd.Series({"k": g.n[g.hosp == "black"].sum(), "n": g.n.sum()}))
yellow = F[F.hosp.notna()].groupby("fac").apply(lambda g: g.n[g.hosp == "asian"].sum() / g.n.sum())
fb = fb[~fb.index.isin(yellow[yellow > 0.1].index)]
p = (fb.k / fb.n)[fb.n >= 30]
m_, v_ = p.mean(), p.var()
ab = m_ * (m_ * (1 - m_) / v_ - 1)
bb = (1 - m_) * (m_ * (1 - m_) / v_ - 1)
black["practice_prior"] = {"alpha": float(ab), "beta": float(bb), "hospitals": int(len(p))}
P = B.merge(fb, left_on="delivery_facility", right_index=True, how="inner")
P = P[P.n >= 30]
P["k_loo"] = P.k - P.hb               # the infant's own mother out of her hospital's count
P["n_loo"] = P.n - 1
P["eb"] = (P.k_loo + ab) / (P.n_loo + ab + bb)
P["leb"] = np.log(P.eb / (1 - P.eb))
P = P.merge(pd.read_parquet(RES / "municipal_estimates.parquet")[["mun", "white_share"]].rename(columns={"white_share": "ws2"}), left_on="mun6", right_on="mun",
            how="left", suffixes=("", "_m"))
P["lws2"] = np.log(P.ws2.clip(0.005, 0.995) / (1 - P.ws2.clip(0.005, 0.995)))
P = P.dropna(subset=["lws2"])
fit = {}
for lab, f in (("practice", "y ~ leb"), ("practice_composition_region_year", "y ~ leb + bs(lws2, df=3) + C(region) + year"),
               ("practice_person", "y ~ leb + hb + bs(lws2, df=3) + C(region) + year")):
    mm = smf.glm(f, data=P, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(P.delivery_facility)[0]})
    fit[lab] = {"coef": float(mm.params["leb"]), "se": float(mm.bse["leb"]), "or_per_logit": float(np.exp(mm.params["leb"]))}
    if "hb" in mm.params:
        fit[lab]["hb_or"] = float(np.exp(mm.params["hb"]))
        fit[lab]["hb_se"] = float(mm.bse["hb"])
fit["deaths"], fit["hospitals"] = int(len(P)), int(P.delivery_facility.nunique())
black["practice_loo_eb"] = fit

# net ratios with bootstrap intervals; the hospital's blanks counted as Black or as Brown (bounds)
H = F[F.dec.isin(["white", "black", "brown", "indigenous"]) & ~F.fac.isin(yellow[yellow > 0.1].index)]
hf = H.groupby(["fac", "dec", "hosp"], dropna=False).n.sum().reset_index()
facs = hf.fac.unique()
byfac = {f_: g for f_, g in hf.groupby("fac")}


def hosp_net(df):
    wr = df[df.hosp.isin(["white", "black", "brown", "indigenous", "asian"])]
    return wr[wr.hosp == "black"].n.sum() / wr[wr.dec == "black"].n.sum()


reps = [hosp_net(pd.concat([byfac[f_] for f_ in rng.choice(facs, len(facs))])) for _ in range(200)]
blank_k = hf[hf.hosp.isna() & (hf.dec == "black")].n.sum()
withrace_k = hf[hf.hosp.notna() & (hf.dec == "black")].n.sum()
black["net"] = {"hospital_ratio": {"est": float(hosp_net(hf)), "se": float(np.std(reps))},
                "hospital_black_share_blank_as_black": float((hf[(hf.dec == "black") & (hf.hosp == "black")].n.sum() + blank_k) / (withrace_k + blank_k)),
                "hospital_black_share_blank_as_other": float(hf[(hf.dec == "black") & (hf.hosp == "black")].n.sum() / (withrace_k + blank_k))}
CK = K.copy()
black["net"]["certificate_ratio"] = boot_mun(CK.assign(a=CK.rec == "black", b_=CK.dec == "black"), "a", "b_")

# the rise of the certificate, standardised to the Black mothers of 2013 (region, schooling, mother's age); and the two records in one model
KB = K[K.dec == "black"].assign(y=lambda x: (x.rec == "black").astype(int), school=lambda x: x.schooling.fillna("9").astype(str),
                                agem=lambda x: pd.cut(pd.to_numeric(x.mother_age, errors="coerce"), [0, 19, 34, 99]).astype(str))
cellm = KB.groupby(["year", "region", "school", "agem"]).y.agg(["mean", "size"]).reset_index()
w13 = cellm[cellm.year == 2013].set_index(["region", "school", "agem"])["size"]
std = {}
for y_, g in cellm.groupby("year"):
    g = g.set_index(["region", "school", "agem"])
    common = g.index.intersection(w13.index)
    std[int(y_)] = {"crude": float(KB[KB.year == y_].y.mean()), "standardised_2013": float((g.loc[common, "mean"] * w13[common]).sum() / w13[common].sum())}
black["certificate_by_year_standardised"] = std
J = B[["y", "hb", "year", "mh"]].copy()
J = J.reset_index().rename(columns={"index": "infant"})
two = pd.concat([J.assign(record="certificate", z=J.y), J.assign(record="hospital", z=J.hb)])
two["t"] = (two.year - 2018) / 10
mm = smf.glm("z ~ C(record) * t", data=two, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": two.infant})
black["joint_trend_same_infants"] = {"certificate_per_decade": float(mm.params["t"]), "certificate_se": float(mm.bse["t"]),
                                     "hospital_minus_certificate": float(mm.params["C(record)[T.hospital]:t"]),
                                     "difference_se": float(mm.bse["C(record)[T.hospital]:t"]), "n_infants": int(len(J))}
hy = F[(F.dec == "black") & F.hosp.isin(["white", "black", "brown", "indigenous", "asian"])].groupby("birth_year").apply(lambda g: g.n.sum())
black["hospital_admissions_by_year"] = {int(k): int(v) for k, v in hy.items()}
M["black"] = black
print("black", json.dumps({k: v for k, v in black.items() if k.startswith(("mh", "clogit"))}, indent=0)[:1500], flush=True)

# ------------------------------------------------------------------ paper 1: the symmetric cells and the crossing with the family
cells = {}
for key, dec, rec in (("PW", "brown", "white"), ("WP", "white", "brown"), ("KP", "black", "brown"), ("KK", "black", "black")):
    g = K[K.dec == dec].dropna(subset=["lws"])
    g = g.assign(y=(g.rec == rec).astype(int))
    mm = smf.glm("y ~ lws", data=g, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.mun6)[0]})
    cells[key] = {"coef": float(mm.params["lws"]), "se": float(mm.bse["lws"]), "intercept": float(mm.params["Intercept"]), "n": int(len(g))}
# the Black category against the share of Brown births (a majority rule predicts Brown where Brown is the majority)
br = pd.read_parquet(RES / "municipal_estimates.parquet")[["mun", "nP", "n"]]
br["brown_share"] = br.nP / br.n
g = K[K.dec == "black"].merge(br[["mun", "brown_share"]], left_on="mun6", right_on="mun", how="left", suffixes=("", "_b")).dropna(subset=["brown_share"])
g["lbs"] = np.log(g.brown_share.clip(0.005, 0.995) / (1 - g.brown_share.clip(0.005, 0.995)))
mm = smf.glm("y ~ lbs", data=g.assign(y=(g.rec == "brown").astype(int)), family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.mun6)[0]})
cells["KP_on_brown_share"] = {"coef": float(mm.params["lbs"]), "se": float(mm.bse["lbs"])}
M["cells"] = cells
# the composition at which Brown mothers' infants are certified White as often as not, with a bootstrap over municipalities
pwd = K[K.dec == "brown"].dropna(subset=["lws"]).assign(y=lambda x: (x.rec == "white").astype(int))
agg = pwd.groupby("mun6").agg(y=("y", "sum"), n=("y", "size"), lws=("lws", "first")).reset_index()


def crossing(a):
    mm = sm.GLM(np.column_stack([a.y, a.n - a.y]), sm.add_constant(a.lws), family=sm.families.Binomial()).fit()
    x = -mm.params["const"] / mm.params["lws"]
    return 1 / (1 + np.exp(-x))


reps = [crossing(agg.iloc[rng.integers(0, len(agg), len(agg))]) for _ in range(300)]
M["cells"]["PW_half_white_share"] = {"est": float(crossing(agg)), "lo": float(np.percentile(reps, 2.5)), "hi": float(np.percentile(reps, 97.5))}

OUT.write_text(json.dumps(M, indent=1, default=float), encoding="utf-8")
print("written", OUT, flush=True)
