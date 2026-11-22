"""Space, time and context: the municipality (and the region-year) as the unit of the result.

    python papers/race_at_death/analysis/spatial.py      -> results/spatial.json, results/municipal_estimates.parquet

Stages
  1. the municipal table: linked infant deaths by mother's race and certified race, the family's classification of the
     municipality's children in the 2010 Census sample, deaths and births by race for mortality ratios, and the context
     (`context.py`); the contiguity graph of the IBGE 2022 mesh
  2. models.R (R-INLA, lme4): BYM2 small-area estimates, the spatial models with composition, state and context, the
     region-year panel of convergence, the mortality ratios by immediate region, and the individual multilevel models
  3. here again: Moran's I and local clusters, the border test, capitals and metropolitan regions, the consequences
     (where the certified inequality is most misstated), with ages 1-9 and 15-24 by context from the candidate counts
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import *  # noqa: E402,F403 - con, births, muns, comp, L, LL, matrix, RACES, NAME, CODE

import libpysal  # noqa: E402
from esda.moran import Moran, Moran_Local_Rate, Moran_Rate  # noqa: E402

from pegasus_data.geography import mesh  # noqa: E402

SP = DATA / "spatial"
SP.mkdir(exist_ok=True)
RSCRIPT = r"C:\Program Files\R\R-4.4.1\bin\Rscript.exe"
S: dict = {}
STAGE = sys.argv[1] if len(sys.argv) > 1 else "all"           # prep | models | post | all

# ------------------------------------------------------------------ 1. the municipal table
ctx = pd.read_parquet(DATA / "municipal_context.parquet").rename(columns={"deaths": "all_deaths"})
g = LL.assign(mun6=LL.mun6.astype(str))
cells = {"nW": ("Branca", None), "nP": ("Parda", None), "nK": ("Preta", None), "WW": ("Branca", "white"), "WP": ("Branca", "brown"),
         "PW": ("Parda", "white"), "PP": ("Parda", "brown"), "KK": ("Preta", "black"), "KP": ("Preta", "brown"), "KW": ("Preta", "white")}
inv = {v: k for k, v in NAME.items()}
cnt = {}
for key, (m, c) in cells.items():
    s = g[g.dec == inv[m]] if c is None else g[(g.dec == inv[m]) & (g.rec == c)]
    cnt[key] = s.groupby("mun6").size()
M = pd.DataFrame(cnt).fillna(0).astype(int)
M["n"] = g.groupby("mun6").size()
M["agree"] = g[g.dec == g.rec].groupby("mun6").size()
M = M.fillna(0)
# all infant deaths of the municipality (linked or not) by certified race, the linked share, and births by mother's race 2013-2023
La = L.assign(mun6=L.mun6.astype(str))
M = M.join(pd.DataFrame({"deaths": La.groupby("mun6").size(), "linked_any": La[La.linked].groupby("mun6").size(),
                         "certW": La[La.rec == "white"].groupby("mun6").size(), "certP": La[La.rec == "brown"].groupby("mun6").size(),
                         "certK": La[La.rec == "black"].groupby("mun6").size()}), how="outer").fillna(0)
b13 = births[1:12].sum(0)                                                # cohorts 2013..2023: (municipality, races)
bt = pd.DataFrame({"mun": [str(int(m)) for m in muns], "birthsW": b13[:, 0], "birthsK": b13[:, 1], "birthsP": b13[:, 3], "births_all": b13[:, :5].sum(1)})
M = M.reset_index(names="mun").merge(bt, on="mun", how="outer").merge(comp[["mun", "white_share", "births_year"]], on="mun", how="left")
# the family's classification of the municipality's children aged 0-9 (census 2010 sample: weighted shares, sample records)
fam = con.execute(f"""SELECT uf || substr(mun, 1, 4) mun, mother_race, race, sum(n) n, sum(records) rec FROM '{(CEN / "mother_child.parquet").as_posix()}'
                      WHERE age BETWEEN 0 AND 9 AND mother_race IN ('1', '2', '4') GROUP BY 1, 2, 3""").df()
ft = fam.groupby(["mun", "mother_race"]).agg(n=("n", "sum"), rec=("rec", "sum")).reset_index()
fx = fam.merge(ft, on=["mun", "mother_race"], suffixes=("", "_t"))
fx["share"] = fx.n / fx.n_t
for key, (mr_, cr) in {"famPW": ("4", "1"), "famKK": ("2", "2"), "famWW": ("1", "1"), "famPP": ("4", "4")}.items():
    v = fx[(fx.mother_race == mr_) & (fx.race == cr)].set_index("mun").share
    M = M.merge(v.rename(key), left_on="mun", right_index=True, how="left")
for key, mr_ in {"famP_rec": "4", "famK_rec": "2", "famW_rec": "1"}.items():
    M = M.merge(ft[ft.mother_race == mr_].set_index("mun").rec.rename(key), left_on="mun", right_index=True, how="left")
M = M.merge(ctx, on="mun", how="left")
M["lws_"] = np.log(M.white_share.clip(0.005, 0.995) / (1 - M.white_share.clip(0.005, 0.995)))
M = M[M.mun.str.len() == 6].fillna({c: 0 for c in ("n", "nW", "nP", "nK", "WW", "WP", "PW", "PP", "KK", "KP", "KW", "agree", "deaths")})
M["uf"] = M.mun.str[:2].astype(int)
M["region"] = M.uf // 10

# the contiguity graph (queen) of the 2022 mesh; a municipality with no neighbour (an island) joins its nearest
geo = mesh("municipality", "minima").assign(mun=lambda d: d.code.astype(str).str[:6])
geo = geo[geo.mun.isin(M.mun)].reset_index(drop=True)
W = libpysal.weights.Queen.from_dataframe(geo, use_index=False, silence_warnings=True)
neigh = {i: set(W.neighbors[i]) for i in range(len(geo))}
cent = geo.to_crs(5880).centroid
islands = [i for i, v in neigh.items() if not v]
for i in islands:
    d = cent.distance(cent.iloc[i])
    d.iloc[i] = np.inf
    j = int(d.values.argmin())
    neigh[i].add(j)
    neigh[j].add(i)
W = libpysal.weights.W({i: sorted(v) for i, v in neigh.items()}, silence_warnings=True)
geo["idx"] = np.arange(len(geo)) + 1                                  # INLA's node index
M = M.merge(geo[["mun", "idx"]], on="mun", how="inner").sort_values("idx").reset_index(drop=True)
assert (M.idx.to_numpy() == np.arange(1, len(M) + 1)).all()
edges = pd.DataFrame([(i + 1, j + 1) for i, v in neigh.items() for j in v if i < j], columns=["i", "j"])
edges["cross_state"] = M.uf.to_numpy()[edges.i - 1] != M.uf.to_numpy()[edges.j - 1]
S["graph"] = {"municipalities": int(len(M)), "edges": int(len(edges)), "cross_state_edges": int(edges.cross_state.sum()), "islands_joined": len(islands)}
if STAGE != "individual":
    M.to_parquet(SP / "municipal.parquet", index=False)
if STAGE != "individual":
    edges.to_parquet(SP / "edges.parquet", index=False)

# region-year and state-year panels of the linkage (time by place)
reg = M.set_index("mun")[["immediate", "intermediate"]]
G = g.merge(reg, left_on="mun6", right_index=True, how="left")
panel = (G.assign(agree=(G.dec == G.rec).astype(int), PW=((G.dec == "brown") & (G.rec == "white")).astype(int),
                  KK=((G.dec == "black") & (G.rec == "black")).astype(int), PP=((G.dec == "brown") & (G.rec == "brown")).astype(int),
                  WW=((G.dec == "white") & (G.rec == "white")).astype(int), isW=(G.dec == "white").astype(int),
                  isP=(G.dec == "brown").astype(int), isK=(G.dec == "black").astype(int))
         .groupby(["intermediate", "uf", "year"])[["agree", "PW", "KK", "PP", "WW", "isW", "isP", "isK"]].sum().reset_index())
panel["n"] = G.groupby(["intermediate", "uf", "year"]).size().to_numpy()
if STAGE != "individual":
    panel.to_parquet(SP / "panel.parquet", index=False)

# deaths and births by race for the mortality ratio by immediate region: by mother's race (linked, scaled to all deaths) and
# by certified race, over the same births by mother's race
ag = M.groupby("immediate").agg(nW=("nW", "sum"), nP=("nP", "sum"), nK=("nK", "sum"), n=("n", "sum"), deaths=("deaths", "sum"),
                                 certW=("certW", "sum"), certP=("certP", "sum"), certK=("certK", "sum"), birthsW=("birthsW", "sum"),
                                 birthsP=("birthsP", "sum"), birthsK=("birthsK", "sum"), uf=("uf", "first"), intermediate=("intermediate", "first")).reset_index()
scale = ag.deaths / ag.n.clip(lower=1)
for r in "WPK":
    ag[f"mothD{r}"] = ag[f"n{r}"] * scale
# the family's classification by intermediate region: P(child's race | mother's race) at age 0 in the census sample of the
# region, through which deaths and births by mother's race are passed (the counterfactual of results.py, made local)
cm = con.execute(f"""SELECT uf || substr(mun, 1, 4) mun, mother_race, race, sum(n) n FROM '{(CEN / "mother_child.parquet").as_posix()}'
                     WHERE age = 0 AND mother_race IN ('1', '2', '4') AND race IN ('1', '2', '4') GROUP BY 1, 2, 3""").df()
cm = cm.merge(reg.reset_index().rename(columns={"mun": "mun"}), on="mun", how="left").groupby(["intermediate", "mother_race", "race"]).n.sum().reset_index()
cm["p"] = cm.n / cm.groupby(["intermediate", "mother_race"]).n.transform("sum")
for lab, col in (("W", "1"), ("P", "4")):
    ag[f"famD{lab}"], ag[f"famB{lab}"] = 0.0, 0.0
for mlab, mcode in (("W", "1"), ("P", "4"), ("K", "2")):
    for clab, ccode in (("W", "1"), ("P", "4")):
        p = ag.intermediate.map(cm[(cm.mother_race == mcode) & (cm.race == ccode)].set_index("intermediate").p).fillna(0)
        ag[f"famD{clab}"] += p * ag[f"mothD{mlab}"]
        ag[f"famB{clab}"] += p * ag[f"births{mlab}"]
if STAGE != "individual":
    ag.to_parquet(SP / "immediate.parquet", index=False)
reg_edges = (edges.assign(a=M.immediate.to_numpy()[edges.i - 1], b=M.immediate.to_numpy()[edges.j - 1])
             .query("a != b")[["a", "b"]].drop_duplicates())
if STAGE != "individual":
    reg_edges.to_parquet(SP / "immediate_edges.parquet", index=False)

# the individual table for the multilevel models: each linked infant death with its own and its municipality's characteristics
IC = DATA / "infant_linkage_context.parquet"
if IC.exists():
    I = pd.read_parquet(IC)
    I["dec"], I["rec"] = I.declared.map(CODE), I.recorded.map(CODE)
    I = I[I.linked & I.dec.isin(["white", "brown", "black"])].copy()
    I["mun"] = I.mun.astype(str).str[:6]
    I["certifier"] = I.certifier.str.strip().map({"1": "attending physician", "2": "substitute physician", "3": "medical examiner (IML)",
                                                   "4": "death verification service", "5": "other"}).fillna("not recorded")
    I["death_place"] = I.death_place.str.strip().map({"1": "hospital", "2": "other health facility", "3": "home"}).fillna("other or not recorded")
    I["school"] = I.schooling.str.strip().map({"1": "0-3", "2": "0-3", "3": "4-7", "4": "8-11", "5": "12 or more"}).fillna("not recorded")
    age = pd.to_numeric(I.mother_age, errors="coerce")
    I["mother_age"] = pd.cut(age, [0, 19, 34, 99], labels=["<20", "20-34", "35+"]).astype(str).replace("nan", "not recorded")
    w_ = pd.to_numeric(I.weight, errors="coerce")
    I["low_weight"] = np.where(w_.isna() | (w_ <= 0), "not recorded", np.where(w_ < 2500, "<2500 g", ">=2500 g"))
    I["age_group"] = pd.cut(I.age_days, [-1, 6, 27, 400], labels=["0-6 days", "7-27 days", "28-364 days"]).astype(str)
    c1 = I.cause.str.strip().str[:1]
    I["cause_group"] = np.select([c1 == "P", c1 == "Q", c1.isin(list("VWXY"))], ["perinatal", "congenital", "external"], "other")
    I["y_white"], I["y_brown"], I["y_black"] = (I.rec == "white").astype(int), (I.rec == "brown").astype(int), (I.rec == "black").astype(int)
    I["y_agree"] = (I.rec == I.dec).astype(int)
    I = I.merge(M[["mun", "lws_", "gdp_pc", "illiterate", "urban", "pop2010", "capital", "metro", "physicians_1000", "natural_by_svo",
                   "external_by_iml", "died_hospital", "race_blank", "immediate", "intermediate", "region"]].rename(columns={"lws_": "lws"}),
                on="mun", how="inner")
    I["death_estab"] = I.death_estab.fillna("none").str.strip().replace("", "none")
    keep = ["year", "mun", "uf", "region", "immediate", "intermediate", "dec", "rec", "y_white", "y_brown", "y_black", "y_agree", "certifier", "death_place",
            "school", "mother_age", "low_weight", "age_group", "cause_group", "death_estab", "lws", "gdp_pc", "illiterate", "urban", "pop2010", "capital",
            "metro", "physicians_1000", "natural_by_svo", "external_by_iml", "died_hospital", "race_blank"]
    I[keep].to_parquet(SP / "individual.parquet", index=False)
    S["individual"] = {"deaths": int(len(I)), "by_mother": {k: int(v) for k, v in I.dec.value_counts().items()},
                       "certifier": {k: int(v) for k, v in I.certifier.value_counts().items()},
                       "death_place": {k: int(v) for k, v in I.death_place.value_counts().items()},
                       "school": {k: int(v) for k, v in I.school.value_counts().items()},
                       "establishments": int(I.death_estab[I.death_estab != "none"].nunique())}

if STAGE in ("prep", "individual"):
    print("prepared", S.get("individual"))
    sys.exit()

# ------------------------------------------------------------------ 2. the models, in R
if STAGE in ("all", "models"):
    r = subprocess.run([RSCRIPT, str(Path(__file__).parent / "models.R"), str(SP)], capture_output=True, text=True)
    print(r.stdout[-6000:], r.stderr[-4000:])
    assert r.returncode == 0, "models.R failed"
    if STAGE == "models":
        sys.exit()

# ------------------------------------------------------------------ 3. spatial structure, borders, places, consequences
import statsmodels.api as sm  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from scipy import stats  # noqa: E402

A = json.loads((SP / "areal.json").read_text(encoding="utf-8"))
if (SP / "ratio.json").exists():                                       # the ratios with linear combinations (models.R ratio)
    A["ratio"] = json.loads((SP / "ratio.json").read_text(encoding="utf-8"))["ratio"]
B = pd.read_parquet(SP / "bym2_estimates.parquet")
M = M.merge(B, on="mun", how="left")
S["bym2"] = A["bym2"]
S["panel"] = {k: {kk: vv for kk, vv in v.items() if kk != "regions"} for k, v in A["panel"].items()}
S["ratio"] = {k: {kk: vv for kk, vv in v.items() if kk != "regions"} for k, v in A["ratio"].items()}
S["models_seconds"] = A["seconds"]
OUTC = {"PW": ("PW", "nP"), "KK": ("KK", "nK"), "disagree": ("disagree", "n"), "WP": ("WP", "nW"), "famPW": ("famPW_y", "famP_rec")}
M["disagree"] = M.n - M.agree
M["famPW_y"] = (M.famPW.fillna(0) * M.famP_rec.fillna(0)).round()
M["famP_rec"] = M.famP_rec.fillna(0).round()

# what resolution the data support: trials per municipality and the posterior width of the smoothed estimates
S["resolution"] = {o: {"median_trials": float(M[t].median()), "share_ge20": float((M[t] >= 20).mean()), "share_zero": float((M[t] == 0).mean()),
                       "median_ci_width": float((M[f"{o}_hi"] - M[f"{o}_lo"]).median()),
                       "share_ci_width_lt_0_2": float(((M[f"{o}_hi"] - M[f"{o}_lo"]) < 0.2).mean())} for o, (y, t) in OUTC.items()}
S["linked_outside_mesh"] = int(len(LL) - M.n.sum())


def wsub(mask):
    """The contiguity weights among the municipalities of ``mask`` (row-standardised), without those left with no neighbour."""
    ids = np.flatnonzero(mask)
    w = libpysal.weights.w_subset(W, ids.tolist(), silence_warnings=True)
    ids = np.array([k for k in ids if len(w.neighbors[k]) > 0])
    w = libpysal.weights.w_subset(W, ids.tolist(), silence_warnings=True)
    w.transform = "r"
    return ids, w


# the spread of the smoothed municipal field (variance of the logits of the BYM2 posterior means across municipalities), alone, after composition and
# after composition and state: the precision of a scaled intrinsic field is not the variance across the map, which is what is compared here
S["field_var"] = {o: {"M0": float(np.log(M[f"{o}_mean"] / (1 - M[f"{o}_mean"])).var()), "M1_composition": float(M[f"{o}_comp_field"].var()),
                      "M3_composition_state": float(M[f"{o}_resid_field"].var())} for o in ("PW", "KK", "disagree", "famPW")}

# the municipal distribution of the smoothed estimates, weighted by live births: where the certificate classes Brown mothers' infants White more
# often than families class Brown mothers' children, and the share of births in such municipalities
wq = M.births_all.fillna(0).to_numpy()


def wquant(v, q):
    v = np.asarray(v, float)
    ok_ = np.isfinite(v) & (wq > 0)
    o = np.argsort(v[ok_])
    c = np.cumsum(wq[ok_][o]) / wq[ok_].sum()
    return float(v[ok_][o][np.searchsorted(c, q)])


dif = (M.PW_mean - M.famPW_mean).to_numpy()
S["distribution"] = {o: {f"p{int(100 * q)}": wquant(M[f"{o}_mean"], q) for q in (0.05, 0.25, 0.5, 0.75, 0.95)} for o in ("PW", "famPW", "KK", "WW", "disagree")}
S["distribution"]["diff_PW"] = {f"p{int(100 * q)}": wquant(dif, q) for q in (0.05, 0.25, 0.5, 0.75, 0.95)}
S["distribution"]["births_cert_above_family"] = float(wq[np.isfinite(dif) & (dif > 0)].sum() / wq[np.isfinite(dif)].sum())
S["distribution"]["municipalities_cert_above_family"] = int((dif > 0).sum())
S["distribution"]["diff_by_region"] = {REGION[r]: float(np.average(dif[(M.region == r).to_numpy() & np.isfinite(dif)], weights=wq[(M.region == r).to_numpy() & np.isfinite(dif)] + 1e-9))
                                       for r in REGION}

# Moran's I of the empirical-Bayes rate (municipalities with at least 5 trials), and of the Pearson residuals of binomial models
# with composition (B-spline of the logit share of White births), state, both, and both with the municipal context
M["lws"] = np.log(M.white_share.clip(0.005, 0.995) / (1 - M.white_share.clip(0.005, 0.995)))
CONTEXT = ("np.log(gdp_pc) + illiterate + urban + np.log(pop2010) + capital + metro + physicians_1000 + natural_by_svo + external_by_iml"
           " + died_hospital + race_blank")
S["moran"], S["lisa"], S["glm"] = {}, {}, {}
for o, (y, t) in OUTC.items():
    if o == "famPW":
        continue
    ok = (M[t] >= 5) & M[["gdp_pc", "illiterate", "urban", "pop2010", "physicians_1000", "lws"]].notna().all(axis=1)
    ids, w = wsub(ok.to_numpy())
    d = M.iloc[ids].copy()
    d["state"] = d.uf.astype(str)
    d["capital"], d["metro"] = d.capital.astype(float), d.metro.astype(float)
    d["p"] = d[y] / d[t]
    mr_ = Moran_Rate(d[y].to_numpy().astype(float), d[t].to_numpy().astype(float), w, adjusted=True, permutations=999)
    res = {"rate": {"I": float(mr_.I), "p": float(mr_.p_sim), "units": int(len(ids))}}
    fits = {}
    for lab, f in (("none", "1"), ("composition", "bs(lws, df=3)"), ("state", "C(state)"), ("composition_state", "bs(lws, df=3) + C(state)"),
                   ("context", CONTEXT), ("composition_context", "bs(lws, df=3) + " + CONTEXT),
                   ("composition_state_context", "bs(lws, df=3) + C(state) + " + CONTEXT)):
        m = smf.glm(f"p ~ {f}", data=d, family=sm.families.Binomial(), var_weights=d[t]).fit()
        fits[lab] = m
        mi = Moran(m.resid_pearson.to_numpy(), w, permutations=999)
        res[lab] = {"I": float(mi.I), "p": float(mi.p_sim), "deviance": float(m.deviance), "df_resid": float(m.df_resid),
                    "dispersion": float(m.pearson_chi2 / m.df_resid)}
    d["lcw"] = np.log(d.census_white.clip(0.005, 0.995) / (1 - d.census_white.clip(0.005, 0.995))).fillna(d.lws)
    for lab, f in (("census_composition", "bs(lcw, df=3)"), ("census_composition_state", "bs(lcw, df=3) + C(state)"),
                   ("census_composition_context", "bs(lcw, df=3) + " + CONTEXT)):
        m = smf.glm(f"p ~ {f}", data=d, family=sm.families.Binomial(), var_weights=d[t]).fit()
        fits[lab] = m
        mi = Moran(m.resid_pearson.to_numpy(), w, permutations=999)
        res[lab] = {"I": float(mi.I), "p": float(mi.p_sim), "deviance": float(m.deviance), "df_resid": float(m.df_resid), "dispersion": float(m.pearson_chi2 / m.df_resid)}
    res["corr_birth_census_composition"] = float(np.corrcoef(d.white_share, d.census_white.fillna(d.white_share))[0, 1])
    dev0 = fits["none"].deviance
    res["deviance_explained"] = {k: float(1 - v.deviance / dev0) for k, v in fits.items()}
    for a_, b_ in (("composition", "composition_state"), ("state", "composition_state"), ("composition", "composition_context"),
                   ("context", "composition_context"), ("composition_state", "composition_state_context")):
        ddev, ddf = fits[a_].deviance - fits[b_].deviance, fits[a_].df_resid - fits[b_].df_resid
        phi = fits[b_].pearson_chi2 / fits[b_].df_resid               # quasi-likelihood F test (overdispersed binomial)
        F = ddev / ddf / phi
        res[f"F_{b_}_vs_{a_}"] = {"F": float(F), "df": [float(ddf), float(fits[b_].df_resid)], "p": float(stats.f.sf(F, ddf, fits[b_].df_resid))}
    S["moran"][o] = res
    if o in ("PW", "disagree", "KK"):
        ml = Moran_Local_Rate(d[y].to_numpy().astype(float), d[t].to_numpy().astype(float), w, adjusted=True, permutations=999, seed=1)
        q = np.where(ml.p_sim < 0.05, ml.q, 0)
        M.loc[M.index[ids], f"{o}_lisa"] = q
        S["lisa"][o] = {lab: int((q == k).sum()) for k, lab in ((1, "high-high"), (2, "low-high"), (3, "low-low"), (4, "high-low"), (0, "not significant"))}
    if o in ("PW", "disagree", "KK"):
        cc_ = fits["composition_state_context"]
        S["glm"][o] = {p: {"est": float(v), "se": float(cc_.bse[p])} for p, v in cc_.params.items() if not p.startswith(("C(state)", "bs("))}
        S["glm"][o + "_context_only"] = {p: {"est": float(v), "se": float(fits["context"].bse[p])} for p, v in fits["context"].params.items()}

# wealth at equal composition, with composition as a spline rather than in three classes (audit 4 P6): the coefficient of log GDP per capita, alone with
# composition and with composition and state; per doubling of GDP per capita as an odds ratio
dg = M[(M.nP >= 5) & M.gdp_pc.notna() & M.lws.notna()].copy()
dg["p"], dg["state"] = dg.PW / dg.nP, dg.uf.astype(str)
S["gdp_given_composition"] = {}
for lab, f in (("composition", "bs(lws, df=3) + np.log(gdp_pc)"), ("composition_state", "bs(lws, df=3) + C(state) + np.log(gdp_pc)")):
    m = smf.glm(f"p ~ {f}", data=dg, family=sm.families.Binomial(), var_weights=dg.nP).fit(scale="X2")
    b, se_ = m.params["np.log(gdp_pc)"], m.bse["np.log(gdp_pc)"]
    S["gdp_given_composition"][lab] = {"coef": float(b), "se": float(se_), "or_doubling": float(np.exp(b * np.log(2))),
                                       "or_doubling_lo": float(np.exp((b - 1.96 * se_) * np.log(2))), "or_doubling_hi": float(np.exp((b + 1.96 * se_) * np.log(2)))}

# the border test: is the jump across a state border the one predicted by state effects estimated away from the borders?
border = np.zeros(len(M), bool)
for i, j, cs in edges[["i", "j", "cross_state"]].itertuples(index=False):
    if cs:
        border[i - 1] = border[j - 1] = True
M["border"] = border
S["border"] = {"border_municipalities": int(border.sum())}
for o, (y, t) in (("PW", ("PW", "nP")), ("disagree", ("disagree", "n")), ("KK", ("KK", "nK"))):
    d = M[(M[t] > 0) & M.lws.notna()].copy()
    d["state"] = d.uf.astype(str)
    d["p"] = d[y] / d[t]
    inner = d[~d.border]
    m_in = smf.glm("p ~ bs(lws, df=3) + C(state)", data=inner, family=sm.families.Binomial(), var_weights=inner[t]).fit()
    ref = sorted(inner.state.unique())[0]
    alpha = {s: (0.0 if s == ref else m_in.params.get(f"C(state)[T.{s}]", np.nan)) for s in d.state.unique()}
    d["elogit"] = np.log((d[y] + 0.5) / (d[t] - d[y] + 0.5))
    d["evar"] = 1 / (d[y] + 0.5) + 1 / (d[t] - d[y] + 0.5)
    di = d.set_index("idx")
    pairs = edges[edges.cross_state & edges.i.isin(di.index) & edges.j.isin(di.index)]
    pi_, pj = di.loc[pairs.i], di.loc[pairs.j]
    D = pi_.elogit.to_numpy() - pj.elogit.to_numpy()
    dA = np.array([alpha[a] - alpha[b] for a, b in zip(pi_.state, pj.state, strict=True)])
    dX = pi_.lws.to_numpy() - pj.lws.to_numpy()
    wt = 1 / (pi_.evar.to_numpy() + pj.evar.to_numpy())
    good = np.isfinite(dA)
    grp = pd.factorize(np.array(["|".join(sorted((a_, b_))) for a_, b_ in zip(pi_.state, pj.state, strict=True)])[good])[0]
    fit = sm.WLS(D[good], sm.add_constant(np.column_stack([dA[good], dX[good]]), has_constant="add"), weights=wt[good]).fit(cov_type="cluster", cov_kwds={"groups": grp})
    if o == "PW":
        pd.DataFrame({"D": D[good], "dA": dA[good], "dX": dX[good], "w": wt[good]}).to_parquet(PAPER / "results" / "border_pairs.parquet", index=False)
    within = edges[~edges.cross_state & edges.i.isin(di.index) & edges.j.isin(di.index)]
    Dw = di.loc[within.i].elogit.to_numpy() - di.loc[within.j].elogit.to_numpy()
    ww = 1 / (di.loc[within.i].evar.to_numpy() + di.loc[within.j].evar.to_numpy())
    S["border"][o] = {"pairs": int(good.sum()), "state_pairs": int(grp.max() + 1), "interior_by_state_min": int(inner.groupby("state").size().min()), "slope_state_effect": float(fit.params[1]), "slope_se": float(fit.bse[1]),
                      "slope_composition": float(fit.params[2]), "composition_se": float(fit.bse[2]),
                      "sd_state_effects": float(np.nanstd(list(alpha.values()))),
                      "msd_cross": float(np.average(D ** 2, weights=wt)), "msd_within": float(np.average(Dw ** 2, weights=ww))}

# state by year: the linkage's agreement with the mother's race, and the Black category for Black mothers
gy = g.assign(st=g.uf.map(UF), agree=(g.dec == g.rec).astype(float))
S["state_year"] = {"agree": {s_: {int(y): float(v) for y, v in x.groupby("year").agree.mean().items()} for s_, x in gy.groupby("st")},
                   "KK": {s_: {int(y): float(v) for y, v in x[x.dec == "black"].groupby("year").apply(lambda z: (z.rec == "black").mean()).items()}
                          for s_, x in gy.groupby("st")},
                   "n": {s_: {int(y): int(v) for y, v in x.groupby("year").size().items()} for s_, x in gy.groupby("st")}}
# capitals, metropolitan regions and the interior; composition by wealth: the linkage's proportions
M["place"] = np.where(M.capital.fillna(False).astype(bool), "capital", np.where(M.metro.fillna(False).astype(bool), "metropolitan, not capital", "interior"))
g2 = g.merge(M[["mun", "place", "gdp_pc", "lws"]], left_on="mun6", right_on="mun", how="inner")
S["by_place"] = {p: link_matrix(x) for p, x in g2.groupby("place")}
g2["comp3"] = pd.cut(g2.lws, [-99, np.log(0.3 / 0.7), np.log(0.6 / 0.4), 99], labels=["<30%", "30-59%", ">=60%"])
g2["gdp3"] = pd.qcut(g2.gdp_pc, 3, labels=["low", "middle", "high"])
S["gdp_tertiles"] = [float(v) for v in g2.gdp_pc.quantile([1 / 3, 2 / 3])]
S["comp_gdp"] = {f"{c}|{q}": link_matrix(x) for (c, q), x in g2.groupby(["comp3", "gdp3"], observed=True)}
S["comp_place"] = {f"{c}|{q}": link_matrix(x) for (c, q), x in g2.groupby(["comp3", "place"], observed=True)}

# ages 1-9 and 15-24 by municipal context, with the candidate estimator: composition (3 classes) by GDP per capita (municipal
# tertiles, the same cut points as the infants), by place (capital, metropolitan, interior) and by death verification service
gq = S["gdp_tertiles"]
X = M[["mun", "lws", "gdp_pc", "place", "natural_by_svo"]].copy()
X["comp3"] = pd.cut(X.lws, [-99, np.log(0.3 / 0.7), np.log(0.6 / 0.4), 99], labels=["<30%", "30-59%", ">=60%"]).astype(str)
X["gdp3"] = pd.cut(X.gdp_pc, [-1, gq[0], gq[1], 1e12], labels=["low", "middle", "high"]).astype(str)
X["svo"] = np.where(X.natural_by_svo >= 0.10, "SVO 10% or more of natural deaths", "SVO under 10%")
con.register("X", X[["mun", "comp3", "gdp3", "place", "svo"]])
for t in ("children", "youth"):
    con.execute(f"CREATE OR REPLACE TABLE {t}_x AS SELECT c.*, X.comp3, X.gdp3, X.place, X.svo FROM {t} c LEFT JOIN X USING (mun)")
CW = "age BETWEEN 1 AND 9 AND births_year < 25600"
YW = "age BETWEEN 15 AND 24 AND births < 1600"
NAT, ASS = "kind = 'natural'", "kind IN ('other assault', 'assault by firearm', 'legal intervention')"
S["candidates_context"] = {
    "children_comp_gdp": {f"{c}|{q}": matrix("children_x", f"{CW} AND comp3 = '{c}' AND gdp3 = '{q}'") for c in ("<30%", "30-59%", ">=60%") for q in ("low", "middle", "high")},
    "children_place": {p: matrix("children_x", f"age BETWEEN 1 AND 9 AND place = '{p}'") for p in ("capital", "metropolitan, not capital", "interior")},
    "children_place_small": {p: matrix("children_x", f"{CW} AND place = '{p}'") for p in ("metropolitan, not capital", "interior")},
    "youth_comp_gdp": {k: {f"{c}|{q}": matrix("youth_x", f"{YW} AND {w} AND comp3 = '{c}' AND gdp3 = '{q}'") for c in ("<30%", "30-59%", ">=60%") for q in ("low", "middle", "high")}
                       for k, w in (("natural", NAT), ("assault", ASS))},
    "youth_svo": {k: {s: matrix("youth_x", f"{YW} AND {w} AND svo = '{s}'") for s in ("SVO 10% or more of natural deaths", "SVO under 10%")} for k, w in (("natural", NAT), ("assault", ASS))},
}

# the regions of the panel and of the ratios, for the figures, the supplement and the consequences
RG = None
for o in ("KK", "PP", "WW", "agree", "PW"):
    x = pd.DataFrame(A["panel"][o]["regions"]).rename(columns=lambda c, o=o: f"{o}_{c}" if c != "intermediate" else c)
    RG = x if RG is None else RG.merge(x, on="intermediate", how="outer")
RT = None
for cl in ("mother", "certificate", "family"):
    x = pd.DataFrame(A["ratio"][cl]["regions"]).rename(columns=lambda c, cl=cl: f"{cl}_{c}" if c != "immediate" else c)
    RT = x if RT is None else RT.merge(x, on="immediate")
agg = M.assign(wsw=M.white_share.fillna(0) * M.births_all.fillna(0), gdpw=M.gdp_pc.fillna(M.gdp_pc.median()) * M.pop2010.fillna(0))
agg = agg.groupby("immediate").agg(wsw=("wsw", "sum"), births=("births_all", "sum"), gdpw=("gdpw", "sum"), pop=("pop2010", "sum"), uf=("uf", "first")).reset_index()
agg["white_share"], agg["gdp_pc"] = agg.wsw / agg.births, agg.gdpw / agg["pop"]
RT = RT.merge(agg[["immediate", "white_share", "gdp_pc", "uf", "births"]], on="immediate")
RT["misstated"] = RT.certificate_log_rr - RT.mother_log_rr
RT["misstated_sd"] = np.hypot(RT.certificate_sd, RT.mother_sd)
rev = (RT.mother_log_rr < 0) & (RT.certificate_log_rr > 0)
S["misstated"] = {"regions": int(len(RT)), "reversed": int(rev.sum()),
                  "mother_below_1_credibly": int((RT.mother_log_rr + 1.96 * RT.mother_sd < 0).sum()),
                  "certificate_above_1_credibly": int((RT.certificate_log_rr - 1.96 * RT.certificate_sd > 0).sum()),
                  "reversed_credible": int(((RT.mother_log_rr + 1.96 * RT.mother_sd < 0) & (RT.certificate_log_rr - 1.96 * RT.certificate_sd > 0)).sum()),
                  "misstated_credibly_positive": int((RT.misstated - 1.96 * RT.misstated_sd > 0).sum()),
                  "births_share_reversed": float(RT.births[rev].sum() / RT.births.sum()),
                  "corr_white_share": float(np.corrcoef(RT.white_share, RT.misstated)[0, 1]),
                  "corr_log_gdp": float(np.corrcoef(np.log(RT.gdp_pc), RT.misstated)[0, 1]),
                  "corr_white_share_log_gdp": float(np.corrcoef(RT.white_share, np.log(RT.gdp_pc))[0, 1])}
X = sm.add_constant(np.column_stack([RT.white_share, np.log(RT.gdp_pc)]))
fit = sm.WLS(RT.misstated.to_numpy(), X, weights=(1 / RT.misstated_sd ** 2).to_numpy()).fit(cov_type="HC1")
fit_c = sm.WLS(RT.misstated.to_numpy(), X[:, :2], weights=(1 / RT.misstated_sd ** 2).to_numpy()).fit()
fit_g = sm.WLS(RT.misstated.to_numpy(), X[:, [0, 2]], weights=(1 / RT.misstated_sd ** 2).to_numpy()).fit()
S["misstated"]["wls"] = {"const": float(fit.params[0]), "white_share": float(fit.params[1]), "white_share_se": float(fit.bse[1]),
                         "log_gdp": float(fit.params[2]), "log_gdp_se": float(fit.bse[2]), "r2": float(fit.rsquared),
                         "r2_composition_only": float(fit_c.rsquared), "r2_gdp_only": float(fit_g.rsquared)}
cls = pd.cut(RT.white_share, [0, 0.1, 0.3, 0.6, 1.0], labels=["<10%", "10-29%", "30-59%", ">=60%"])
S["misstated"]["by_composition"] = {str(k): {"regions": int(len(x)), "births": float(x.births.sum()), "ratio_of_ratios": float(np.exp(np.average(x.misstated, weights=x.births))),
                                         "mother": float(np.exp(np.average(x.mother_log_rr, weights=x.births))), "certificate": float(np.exp(np.average(x.certificate_log_rr, weights=x.births)))}
                                     for k, x in RT.groupby(cls, observed=True)}
RG.to_parquet(PAPER / "results" / "intermediate_panel.parquet", index=False)
RT.to_parquet(PAPER / "results" / "immediate_ratios.parquet", index=False)
keep = ["mun", "uf", "immediate", "intermediate", "capital", "metro", "border", "place", "white_share", "births_year", "gdp_pc", "illiterate", "urban",
        "pop2010", "physicians_1000", "natural_by_svo", "external_by_iml", "died_hospital", "race_blank", "n", "nW", "nP", "nK", "PW", "PP", "WW", "WP",
        "KK", "KP", "agree", "famPW", "famP_rec"] + [c for c in M.columns if c.endswith(("_mean", "_lo", "_hi", "_sd", "_lisa", "_resid_field", "_comp_field"))]
M[keep].to_parquet(PAPER / "results" / "municipal_estimates.parquet", index=False)

# the names of the immediate regions, the regions where the certificate misstates the inequality most, and the supplementary data files
from pegasus_data.geography import memberships  # noqa: E402

one = M.groupby("immediate").mun.first()
RT["name"] = RT.immediate.map({i: memberships(m).get("ibge_immediate_region").member_label for i, m in one.items()})
UFS = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
       31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}
RT["uf"] = RT.uf.map(UFS)
srt = RT.sort_values("misstated", ascending=False)
cols = ["name", "uf", "white_share", "gdp_pc", "mother_log_rr", "certificate_log_rr", "misstated", "misstated_sd", "births"]
S["misstated"]["top"] = srt.head(25)[cols].to_dict("records")
S["misstated"]["bottom"] = srt.tail(10)[cols].to_dict("records")
(PAPER / "out").mkdir(exist_ok=True)
M[keep].to_csv(PAPER / "out" / "supplementary_data_1_municipalities.csv", index=False)
RT.to_csv(PAPER / "out" / "supplementary_data_2_immediate_regions.csv", index=False)

if (SP / "individual.json").exists():                                   # models.R individual (run after the linkage context)
    S["multilevel"] = json.loads((SP / "individual.json").read_text(encoding="utf-8"))["individual"]


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    return o


(PAPER / "results" / "spatial.json").write_text(json.dumps(clean(S), indent=1), encoding="utf-8")
print("written spatial.json", list(S))
