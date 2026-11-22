"""Who records what, part 2 (the fields of `counts.py mechanism`): who filled the birth record, the same mother across births and hospitals,
where the death occurred, the investigation of the death, and the table of the crossed physician model (analysis/physician.R). Adds its keys
to results/mechanism.json, which analysis/mechanism.py (part 1) writes.

    python papers/race_at_death/analysis/mechanism2.py
"""
import json
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

warnings.simplefilter("ignore")
HERE = Path(__file__).resolve().parents[1]
DATA, RES = HERE / "data", HERE / "results"
OUT = RES / "mechanism.json"
M = json.loads(OUT.read_text(encoding="utf-8"))
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

# ------------------------------------------------------------------ part 2: who filled the birth record, the physician, where the death occurred, the same mother
MECH = DATA / "infant_linkage_mechanism.parquet"
DEL = sorted((DATA / "deliveries").glob("*.parquet"))
FILLER = {"1": "physician", "2": "nursing", "3": "midwife", "4": "registry clerk", "5": "other staff"}
if len(DEL) == 12:
    COLS = ["l", "tpfuncresp", "dtnascmae", "codmunres", "qtdfilvivo", "codestab", "racacormae", "patient_race", "admission_facility", "birth_year"]
    V = pd.concat([pd.read_parquet(f, columns=COLS) for f in DEL], ignore_index=True)
    for c in ("tpfuncresp", "racacormae", "patient_race"):
        V[c] = V[c].astype("category")
    V["dec"] = V.racacormae.astype(str).map(RACE)
    V["hosp"] = V.patient_race.astype(str)
    V["filler"] = V.tpfuncresp.astype(str).map(FILLER).fillna("not recorded")
    fl = {}
    for fill_, g in V[V.birth_year >= 2014].groupby("filler"):
        known = g[g.hosp.isin(["white", "black", "brown", "indigenous", "asian"]) & g.dec.isin(["white", "black", "brown"])]
        fl[fill_] = {"births": int(len(g)), "black_declared_share": float((g.dec == "black").mean()),
                     "agreement": float((known.dec == known.hosp).mean()),
                     "black_recorded_black": prop(int(((known.dec == "black") & (known.hosp == "black")).sum()), int((known.dec == "black").sum()))}
    # the same hospital's births filled by different staff: the declaration's Black share by filler within hospitals (fixed effects)
    W = V[(V.birth_year >= 2014) & V.filler.isin(["physician", "nursing", "other staff"]) & V.dec.isin(["white", "black", "brown"])].copy()
    W["kb"] = (W.dec == "black").astype(float)
    W["fac"] = W.codestab.astype(str)
    W["kb_dm"] = W.kb - W.groupby("fac").kb.transform("mean")
    for f_ in ("physician", "other staff"):
        W[f"is_{f_}"] = (W.filler == f_).astype(float)
        W[f"is_{f_}_dm"] = W[f"is_{f_}"] - W.groupby("fac")[f"is_{f_}"].transform("mean")
    r = sm.OLS(W.kb_dm, W[["is_physician_dm", "is_other staff_dm"]]).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(W.fac)[0]})
    fl["within_hospital_black_declared_difference"] = {"physician_vs_nursing": {"est": float(r.params.iloc[0]), "se": float(r.bse.iloc[0])},
                                                       "other_vs_nursing": {"est": float(r.params.iloc[1]), "se": float(r.bse.iloc[1])}}
    M["filler"] = fl
    print("filler", fl, flush=True)

    # the same mother: births with the same mother's birth date and municipality of residence in two years, parity one or more higher;
    # chance pairs counted by the same key with the mother's birth date moved by one day (a negative control)
    V["munres"] = V.codmunres.astype(str).str[:6]
    bpy = V.groupby(["munres", "birth_year"]).size().groupby("munres").mean()
    small = bpy[bpy < 1600].index
    S = V[V.munres.isin(small) & V.dtnascmae.str.fullmatch(r"\d{8}", na=False)].copy()
    S["par"] = pd.to_numeric(S.qtdfilvivo, errors="coerce")
    one = S.groupby(["munres", "dtnascmae", "birth_year"]).l.transform("size") == 1           # one birth of that key in the year (twins out)
    S = S[one]
    S["k"] = S.munres + S.dtnascmae

    def pairs_of(T, key="k"):
        a = T[[key, "birth_year", "par", "dec", "hosp", "admission_facility", "codestab", "filler"]]
        p_ = a.merge(a, on=key, suffixes=("_1", "_2"))
        p_ = p_[(p_.birth_year_2 >= p_.birth_year_1 + 1) & (p_.par_2 >= p_.par_1 + 1)]
        return p_.sort_values("birth_year_2").drop_duplicates([key, "birth_year_1"])

    PR = pairs_of(S)
    sh = S.copy()
    sh["d"] = pd.to_datetime(sh.dtnascmae, format="%d%m%Y", errors="coerce") + pd.Timedelta(days=1)
    sh = sh.dropna(subset=["d"])
    sh["k2"] = sh.munres + sh.d.dt.strftime("%d%m%Y")
    ctrl = S[["k", "birth_year", "par", "dec", "hosp", "admission_facility", "codestab", "filler"]].merge(
        sh[["k2", "birth_year", "par", "dec", "hosp", "admission_facility", "codestab"]].rename(columns={"k2": "k"}), on="k", suffixes=("_1", "_2"))
    ctrl = ctrl[(ctrl.birth_year_2 >= ctrl.birth_year_1 + 1) & (ctrl.par_2 >= ctrl.par_1 + 1)].drop_duplicates(["k", "birth_year_1"])
    mv = {"pairs": int(len(PR)), "chance_pairs_control": int(len(ctrl)), "false_share": float(len(ctrl) / max(len(PR), 1))}

    def net(cond, outcome):
        """A proportion among the pairs meeting ``cond`` with the chance pairs (the shifted-date control, which has the same
        conditions) subtracted from numerator and denominator."""
        a_, c_ = PR[cond(PR)], ctrl[cond(ctrl)]
        n_, k_ = len(a_) - len(c_), int(outcome(a_).sum()) - int(outcome(c_).sum())
        p_ = k_ / n_ if n_ > 0 else float("nan")
        return {"est": float(p_), "se": float(np.sqrt(max(p_ * (1 - p_), 0) / n_ + (len(c_) / max(n_, 1)) ** 2 * 0.25 / max(len(c_), 1))) if n_ > 0 else None,
                "pairs": int(len(a_)), "chance": int(len(c_)), "raw": float(outcome(a_).mean()) if len(a_) else None}

    K3 = ("white", "black", "brown")
    for j in K3:
        mv[f"declared_again|{j}"] = net(lambda x, j=j: (x.dec_1 == j) & x.dec_2.isin(K3), lambda x, j=j: x.dec_2 == j)
    # the birth record's declaration at the next birth, in the same birth establishment or another (review 2026-11-22, round 2, 3.2): if the
    # "declaration" were the establishment's, it would repeat far more often in the same one
    for j in K3:
        for same, tag in ((True, "same establishment"), (False, "another establishment")):
            mv[f"declared_again|{j}|{tag}"] = net(lambda x, j=j, same=same: (x.dec_1 == j) & x.dec_2.isin(K3) & x.codestab_1.notna() & x.codestab_2.notna()
                                                  & ((x.codestab_1 == x.codestab_2) == same), lambda x, j=j: x.dec_2 == j)
    BB = lambda x: (x.dec_1 == "black") & (x.dec_2 == "black") & x.hosp_1.isin(K3) & x.hosp_2.isin(K3)  # noqa: E731
    for same, tag in ((True, "same hospital"), (False, "another hospital")):
        mv[f"hospital_black_again|{tag}"] = net(lambda x, same=same: BB(x) & (x.hosp_1 == "black") & ((x.admission_facility_1 == x.admission_facility_2) == same),
                                                lambda x: x.hosp_2 == "black")
        mv[f"hospital_black_after_not|{tag}"] = net(lambda x, same=same: BB(x) & (x.hosp_1 != "black") & ((x.admission_facility_1 == x.admission_facility_2) == same),
                                                    lambda x: x.hosp_2 == "black")
    hk = PR[BB(PR)].copy()
    hk["same_hospital"] = hk.admission_facility_1 == hk.admission_facility_2
    # mother against hospital: the change in the hospital's record of the same Black mother against the change in its practice (shrunk), among
    # mothers who changed hospital; chance pairs dilute the slope toward zero by their share, which is reported beside it
    pr_ = fb.assign(rate=(fb.k + ab) / (fb.n + ab + bb))
    mvh = hk[~hk.same_hospital].merge(pr_[["rate"]], left_on="admission_facility_1", right_index=True).merge(
        pr_[["rate"]].rename(columns={"rate": "rate_2"}), left_on="admission_facility_2", right_index=True)
    mvh["dy"] = (mvh.hosp_2 == "black").astype(int) - (mvh.hosp_1 == "black").astype(int)
    mvh["dp"] = mvh.rate_2 - mvh.rate
    r = sm.OLS(mvh.dy, sm.add_constant(mvh.dp)).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(mvh.admission_facility_2)[0]})
    r1 = sm.OLS(mvh.dy, sm.add_constant(mvh.dp)).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(mvh.admission_facility_1)[0]})
    cm = ctrl[BB(ctrl) & (ctrl.admission_facility_1 != ctrl.admission_facility_2)]
    shr = len(cm) / max(len(mvh), 1)
    mv["movers_practice_slope"] = {"est": float(r.params["dp"]), "se": float(r.bse["dp"]), "se_origin_cluster": float(r1.bse["dp"]),
                                   "destinations": int(mvh.admission_facility_2.nunique()), "n": int(len(mvh)), "chance_share": float(shr),
                                   "corrected": float(r.params["dp"] / (1 - shr)) if shr < 1 else None}
    M["movers"] = mv
    print("movers", mv, flush=True)

if MECH.exists():
    X = pd.read_parquet(MECH)
    ctx_all = pd.read_parquet(DATA / "infant_linkage_delivery.parquet")
    assert len(X) == len(ctx_all)
    X.index = ctx_all.index
    D2 = D.join(X, how="left")
    K2 = D2[D2.dec.isin(["white", "brown", "black"])].copy()
    # where the death occurred: outside the municipality of residence, the composition of both
    K2["occ6"] = K2.occurrence_mun.astype(str).str[:6]
    ws = E.set_index("mun").white_share
    K2["lws_occ"] = np.log(K2.occ6.map(ws).clip(0.005, 0.995) / (1 - K2.occ6.map(ws).clip(0.005, 0.995)))
    out_ = K2[(K2.occ6 != K2.mun6) & K2.lws_occ.notna() & K2.lws.notna()]
    occ = {"deaths_elsewhere": int(len(out_)), "share_elsewhere": float(len(out_) / len(K2))}
    for key, dec, rec in (("PW", "brown", "white"), ("WP", "white", "brown"), ("KK", "black", "black")):
        g = out_[out_.dec == dec].assign(y=lambda x, rec=rec: (x.rec == rec).astype(int))
        mm = smf.glm("y ~ lws + lws_occ", data=g, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.mun6)[0]})
        occ[key] = {t: {"coef": float(mm.params[t]), "se": float(mm.bse[t])} for t in ("lws", "lws_occ")} | {"n": int(len(g))}
    M["occurrence"] = occ
    # investigation: was the death investigated, and from which source; agreement with the mother by source
    inv = {}
    K2["src"] = np.where(K2.investigated == "S", K2.investigation_source.fillna("?"), "not investigated")
    for s_, g in K2.groupby("src"):
        if len(g) >= 500:
            inv[s_] = {"agreement": prop(int((g.rec == g.dec).sum()), len(g)),
                       "PW": prop(int(((g.dec == "brown") & (g.rec == "white")).sum()), int((g.dec == "brown").sum())),
                       "KK": prop(int(((g.dec == "black") & (g.rec == "black")).sum()), int((g.dec == "black").sum()))}
    M["investigation"] = inv
    # the table for the crossed physician, establishment and municipality model (models.R stage physician)
    ph = K2[K2.crm.notna() & (K2.crm.astype(str).str.strip() != "") & K2.year.between(2014, 2018)].copy()
    ph["physician"] = ph.uf.astype(str) + ":" + ph.crm.astype(str).str.strip()
    ph["PW"] = ((ph.dec == "brown") & (ph.rec == "white")).astype(int)
    ph["KK"] = ((ph.dec == "black") & (ph.rec == "black")).astype(int)
    ph[["dec", "PW", "KK", "physician", "death_estab", "mun6", "lws", "certifier", "year", "hb" if "hb" in ph else "mh"]].to_parquet(DATA / "spatial" / "physician.parquet", index=False)
    M["physician_table"] = {"deaths": int(len(ph)), "physicians": int(ph.physician.nunique())}
    print("occurrence", occ, "investigation", list(inv), M["physician_table"], flush=True)

OUT.write_text(json.dumps(M, indent=1, default=float), encoding="utf-8")
print("written", OUT, flush=True)
