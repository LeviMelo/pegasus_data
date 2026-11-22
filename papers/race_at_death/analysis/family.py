"""Paper 4: how households classify children relative to the mother, in two censuses (2010, 2022), from the mother-child pairs of the
sample microdata (data/probes/census2022/pairs.py: pairs_2010.parquet, pairs_2022.parquet, persons_*.parquet).

Pairs are those the two public files share: a child aged 0-24 of the household's couple, paired with its woman (relation 04, 05 or 06,
mother co-resident). Estimates are weighted; their standard errors are design-based by Taylor linearisation with strata = state and
primary units = households (the 2022 public file carries no weighting area; 2010's weighting areas give a sensitivity).

    python papers/race_at_death/analysis/family.py      -> results/family.json   (about ten minutes)
    python papers/race_at_death/analysis/family.py review2   -> adds "review2" to it
"""
import json
import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

warnings.simplefilter("ignore")
HERE = Path(__file__).resolve().parents[1]
CEN = HERE.parents[1] / "data" / "probes" / "census2022"
OUT = HERE / "results" / "family.json"
RACE = {"1": "white", "2": "black", "3": "asian", "4": "brown", "5": "indigenous"}
AGE = {1: "0-4", 2: "5-9", 3: "10-14", 4: "15-19", 5: "20-24"}
INSTR = {"1": "none or primary incomplete", "2": "primary complete", "3": "secondary complete", "4": "higher complete"}
REGION = {"1": "North", "2": "Northeast", "3": "Southeast", "4": "South", "5": "Centre-West"}
PARTNERS = lambda ref: [ref] + [x for x in ("white", "brown", "black", "other", "no partner") if x != ref]  # noqa: E731
con = duckdb.connect()
con.execute("PRAGMA disable_progress_bar; SET memory_limit='1500MB'")


def load(year, rule="couple"):
    d = con.execute(f"""SELECT uf, hh, wa, w, rel, sex, age_group, race, mother_race, mother_age_group, mother_instruction, partner_race, informant,
                        mother_informant, order_agrees FROM '{(CEN / f'pairs2_{year}.parquet').as_posix()}' WHERE rule = '{rule}'""").df()
    d["year"] = year
    return d


def ratio(df, y, x=None, strata="uf", psu="hh"):
    """A weighted ratio sum(w y) / sum(w x) (x = 1 when None) with its design-based standard error (Taylor linearisation,
    with-replacement sampling of primary units within strata)."""
    w = df.w.to_numpy()
    yy = df[y].to_numpy(float)
    xx = np.ones(len(df)) if x is None else df[x].to_numpy(float)
    X = (w * xx).sum()
    r = (w * yy).sum() / X
    z = w * (yy - r * xx) / X
    t = pd.DataFrame({"h": df[strata].to_numpy(), "u": df[psu].to_numpy(), "z": z}).groupby(["h", "u"]).z.sum().reset_index()
    g = t.groupby("h").z.agg(["count", "mean"])
    t = t.join(g, on="h")
    v = (((t.z - t["mean"]) ** 2) * t["count"] / (t["count"] - 1).clip(lower=1)).sum()
    return {"est": float(r), "se": float(np.sqrt(v)), "records": int(len(df)), "weighted": float(X)}


F = {}
D = {y: load(y) for y in (2010, 2022)}
for y, d in D.items():
    d["region"] = d.uf.str[0].map(REGION)
    d["child"] = d.race.map(RACE)
    d["mother"] = d.mother_race.map(RACE)
    d["partner"] = d.partner_race.map(RACE).replace({"indigenous": "other", "asian": "other"}).fillna("no partner")
    d["age"] = d.age_group.map(AGE)
    d["instruction"] = d.mother_instruction.map(INSTR).fillna("not determined")
    d["mother_age"] = d.mother_age_group.map(lambda a: "under 25" if a <= 5 else ("25-34" if a <= 7 else ("35-44" if a <= 9 else "45 or more")))
    for c in ("white", "brown", "black"):
        d[f"is_{c}"] = (d.child == c).astype(int)
    d["same"] = (d.child == d.mother).astype(int)


def review2():
    """Review 2: the child's and the mother's informant crossed; full siblings against independence; both parents' races among fathers;
    the 2022 reweighting with bootstrap intervals and a White-mother placebo. Written into family.json under "review2"."""
    out = {}
    # 1. who answered for the child crossed with who answered for the mother (2022), children 0-9 with a partner
    d = D[2022]
    sub = d[d.age.isin(["0-4", "5-9"]) & d.mother.isin(["white", "brown", "black"]) & (d.partner != "no partner")].copy()
    sub["child_by"] = sub.informant.where(sub.informant.isin(["mother", "partner"]), "other")
    sub["mother_by"] = sub.mother_informant.map({"self": "mother", "partner": "partner"}).fillna("other")
    cross = {}
    for (m, p, cb, mb), g in sub.groupby(["mother", "partner", "child_by", "mother_by"]):
        if len(g) >= 300 and cb != "other" and mb != "other":
            cross[f"{m}|{p}|child by {cb}|mother by {mb}"] = {"white": ratio(g, "is_white"), "black": ratio(g, "is_black"), "brown": ratio(g, "is_brown")}
    out["informant_cross"] = cross
    # 2. full siblings (every child aged 0-9 of the couple a child of both) against independence within the mother-by-partner cell
    sib = {}
    for y, d in D.items():
        s0 = d[d.age.isin(["0-4", "5-9"]) & d.mother.isin(["white", "brown", "black"]) & d.child.isin(["white", "brown", "black"])]
        h = s0.groupby("hh").agg(n=("child", "size"), k=("child", "nunique"), allfull=("rel", lambda r: bool((r == "04").all())), w=("w", "first"),
                                 uf=("uf", "first"), mother=("mother", "first"), partner=("partner", "first"))
        h = h[(h.n >= 2) & h.allfull].reset_index()
        h["disc"] = (h.k > 1).astype(int)
        kids = s0[s0.hh.isin(h.hh)]
        for (m, p), x in h.groupby(["mother", "partner"]):
            if len(x) < 300:
                continue
            kk = kids[(kids.mother == m) & (kids.partner == p)]
            pc = (kk.groupby("child").w.sum() / kk.w.sum()).to_dict()
            expected = float(np.average(1 - sum(pc.get(c, 0) ** x.n for c in ("white", "brown", "black")), weights=x.w))
            sib[f"{y}|{m}|{p}"] = {"observed": ratio(x, "disc"), "independent": expected, "households": int(len(x))}
    out["full_siblings"] = sib
    # 3. both parents' races among children of both (fathers): the child White, Brown or Black
    par = {}
    for y, d in D.items():
        s0 = d[d.age.isin(["0-4", "5-9"]) & (d.rel == "04")]
        for (m, p), g in s0.groupby(["mother", "partner"]):
            if m in ("white", "brown", "black") and p in ("white", "brown", "black"):
                par[f"{y}|{m}|{p}"] = {c: ratio(g, f"is_{c}") for c in ("white", "brown", "black")}
    out["parents"] = par
    # 4. the 2022 proportions at the 2010 mothers' instruction and region, with a household bootstrap, for each mother's race (White a placebo)
    rng = np.random.default_rng(2026)
    cells = [("brown", "is_white"), ("black", "is_black"), ("black", "is_white"), ("white", "is_white"), ("brown", "is_brown")]
    S10 = {m: D[2010][(D[2010].mother == m) & D[2010].age.isin(["0-4", "5-9"])][["hh", "w", "instruction", "region", "is_white", "is_black", "is_brown"]]
           for m in ("white", "brown", "black")}
    S22 = {m: D[2022][(D[2022].mother == m) & D[2022].age.isin(["0-4", "5-9"])][["hh", "w", "instruction", "region", "is_white", "is_black", "is_brown"]]
           for m in ("white", "brown", "black")}

    def std(a10, a22, outc, w10, w22):
        p10 = (a10.assign(w=w10).groupby(["instruction", "region"]).w.sum())
        p10 = p10 / p10.sum()
        g22 = a22.assign(w=w22, wy=w22 * a22[outc]).groupby(["instruction", "region"])[["w", "wy"]].sum()
        r22 = g22.wy / g22.w
        common = p10.index.intersection(r22.index)
        return (float((w10 * a10[outc]).sum() / w10.sum()), float((w22 * a22[outc]).sum() / w22.sum()),
                float((r22[common] * p10[common]).sum() / p10[common].sum()))

    def hh_mult(a):
        u, inv = np.unique(a.hh.to_numpy(), return_inverse=True)
        return inv, len(u)

    idx = {(m, y): hh_mult(S10[m] if y == 2010 else S22[m]) for m in S10 for y in (2010, 2022)}
    est = {f"{m}|{o}": std(S10[m], S22[m], o, S10[m].w.to_numpy(), S22[m].w.to_numpy()) for m, o in cells}
    reps = {k: [] for k in est}
    for _ in range(200):
        mult = {}
        for (m, y), (inv, n) in idx.items():
            mult[(m, y)] = rng.poisson(1.0, n)[inv]
        for m, o in cells:
            reps[f"{m}|{o}"].append(std(S10[m], S22[m], o, S10[m].w.to_numpy() * mult[(m, 2010)], S22[m].w.to_numpy() * mult[(m, 2022)]))
    dr = {}
    for k, (a, b, c) in est.items():
        r = np.array(reps[k])
        dr[k] = {"2010": a, "2022": b, "2022_at_2010_mothers": c, "se": {"2010": float(r[:, 0].std()), "2022": float(r[:, 1].std()), "std": float(r[:, 2].std())},
                 "change": b - a, "change_se": float((r[:, 1] - r[:, 0]).std()), "std_change": c - a, "std_change_se": float((r[:, 2] - r[:, 0]).std())}
    out["drift_boot"] = dr
    out["instruction_by_mother"] = {f"{y}|{m}": ((S10[m] if y == 2010 else S22[m]).groupby("instruction").w.sum()
                                                 / (S10[m] if y == 2010 else S22[m]).w.sum()).to_dict() for m in S10 for y in (2010, 2022)}
    return out


if sys.argv[1:] == ["review2"]:
    F = json.loads(OUT.read_text(encoding="utf-8"))
    F["review2"] = review2()
    OUT.write_text(json.dumps(F, indent=1, default=float), encoding="utf-8")
    print("review2 written", {k: (round(v["observed"]["est"], 3), round(v["independent"], 3)) for k, v in F["review2"]["full_siblings"].items()}, flush=True)
    sys.exit(0)


# ------------------------------------------------------------------ the household's classification of the child by the mother's race, two censuses
F["matrix"] = {}
for y, d in D.items():
    F["matrix"][y] = {}
    for m in ("white", "brown", "black", "indigenous"):
        for a in ("0-4", "5-9", "all"):
            sub = d[(d.mother == m) & ((d.age == a) if a != "all" else d.age.isin(["0-4", "5-9"]))]
            F["matrix"][y][f"{m}|{a}"] = {c: ratio(sub, f"is_{c}") for c in ("white", "brown", "black")} | {"same": ratio(sub, "same")}
    print(y, "matrix", {k: round(v["white"]["est"], 3) for k, v in F["matrix"][y].items()}, flush=True)

# ------------------------------------------------------------------ Brown and Black mothers' children by partner, mother's instruction, child's age and region
F["by"] = {}
for y, d in D.items():
    F["by"][y] = {}
    for m, outc in (("brown", "is_white"), ("black", "is_black"), ("black", "is_brown"), ("white", "is_white")):
        sub = d[(d.mother == m) & d.age.isin(["0-4", "5-9"])]
        for dim in ("partner", "instruction", "region"):
            for lev, g in sub.groupby(dim):
                if len(g) >= 200:
                    F["by"][y][f"{m}|{outc}|{dim}|{lev}"] = ratio(g, outc)
        for lev, g in d[d.mother == m].groupby("age"):
            F["by"][y][f"{m}|{outc}|age|{lev}"] = ratio(g, outc)
    print(y, "by", len(F["by"][y]), flush=True)

# ------------------------------------------------------------------ the mothers' partners in each census, and the 2022 classification at 2010's partner mix
mix = {}
for m, outc in (("brown", "is_white"), ("black", "is_black"), ("black", "is_white")):
    shares, rates = {}, {}
    for y, d in D.items():
        sub = d[(d.mother == m) & d.age.isin(["0-4", "5-9"])]
        shares[y] = (sub.groupby("partner").w.sum() / sub.w.sum()).to_dict()
        rates[y] = sub.groupby("partner").apply(lambda g, o=outc: (g.w * g[o]).sum() / g.w.sum()).to_dict()
    std = sum(rates[2022][p] * shares[2010][p] for p in shares[2010] if p in rates[2022])
    mix[f"{m}|{outc}"] = {"partner_share": shares, "rate_by_partner": rates, "crude": {y: F["matrix"][y][f"{m}|all"][outc.replace("is_", "")]["est"] for y in D},
                          "2022_at_2010_partners": float(std)}
F["partner_mix"] = mix

# ------------------------------------------------------------------ one model of both censuses: Brown mothers' children 0-9 reported White
mods = {}
for m, outc, ref in (("brown", "is_white", "brown"), ("black", "is_black", "black")):
    S = pd.concat([D[y][(D[y].mother == m) & D[y].age.isin(["0-4", "5-9"])] for y in (2010, 2022)])
    S["census"] = S.year.astype(str)
    S = S[S.instruction != "not determined"]
    S["partner"] = pd.Categorical(S.partner, categories=PARTNERS(ref))
    S["instruction"] = pd.Categorical(S.instruction, categories=["none or primary incomplete", "primary complete", "secondary complete", "higher complete"])
    f = f"{outc} ~ C(census) + partner + instruction + C(age) + C(mother_age) + C(sex) + C(region)"
    r = smf.glm(f, data=S, family=sm.families.Binomial(), var_weights=S.w / S.w.mean()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(S.hh)[0]})
    mods[f"{m}|{outc}"] = {k: {"or": float(np.exp(r.params[k])), "lo": float(np.exp(r.params[k] - 1.96 * r.bse[k])), "hi": float(np.exp(r.params[k] + 1.96 * r.bse[k]))}
                           for k in r.params.index if k != "Intercept"} | {"records": int(len(S))}
    # the census contrast inside each partner class: is the change between censuses the same whoever the partner is?
    r2 = smf.glm(f.replace("C(census) + partner", "C(census) * partner"), data=S, family=sm.families.Binomial(), var_weights=S.w / S.w.mean()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(S.hh)[0]})
    mods[f"{m}|{outc}|interaction"] = {k: {"est": float(r2.params[k]), "se": float(r2.bse[k])} for k in r2.params.index if ":" in k}
    print(m, "model", {k: round(v["or"], 2) for k, v in mods[f"{m}|{outc}"].items() if isinstance(v, dict)}, flush=True)
F["models"] = mods

# ------------------------------------------------------------------ 2022: who answered for the child
d = D[2022]
inf = {}
for m, outc in (("brown", "is_white"), ("black", "is_black"), ("white", "is_white"), ("brown", "same"), ("black", "same"), ("white", "same")):
    for a in ("0-4", "5-9", "10-14"):
        for who, g in d[(d.mother == m) & (d.age == a)].groupby("informant"):
            if len(g) >= 200:
                inf[f"{m}|{outc}|{a}|{who}"] = ratio(g, outc)
S = d[d.mother.isin(["white", "brown", "black"]) & d.age.isin(["0-4", "5-9", "10-14"]) & d.informant.isin(["mother", "other resident", "non-resident"])].copy()
S["informant"] = pd.Categorical(S.informant, categories=["mother", "other resident", "non-resident"])
S["instruction"] = pd.Categorical(S.instruction, categories=["none or primary incomplete", "primary complete", "secondary complete", "higher complete",
                                                              "not determined"])
for m in ("brown", "black", "white"):
    Sm = S[(S.mother == m) & (S.instruction != "not determined")].copy()
    Sm["instruction"] = Sm.instruction.cat.remove_unused_categories()
    Sm["partner"] = pd.Categorical(Sm.partner, categories=PARTNERS(m))
    r = smf.glm("same ~ informant + partner + instruction + C(age) + C(mother_age) + C(sex) + C(region)", data=Sm, family=sm.families.Binomial(),
                var_weights=Sm.w / Sm.w.mean()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(Sm.hh)[0]})
    inf[f"model_same|{m}"] = {k: {"or": float(np.exp(r.params[k])), "lo": float(np.exp(r.params[k] - 1.96 * r.bse[k])), "hi": float(np.exp(r.params[k] + 1.96 * r.bse[k]))}
                              for k in r.params.index if k.startswith("informant")} | {"records": int(len(Sm))}
inf["share"] = {who: float(g.w.sum() / d.w.sum()) for who, g in d.groupby("informant")}
F["informant"] = inf
print("informant", {k: v for k, v in inf.items() if k.startswith("model")}, flush=True)

# ------------------------------------------------------------------ the pairs the rule keeps: co-residence and the couple rule, by age and race
P = pd.concat([con.execute(f"SELECT * FROM '{(CEN / f'persons2_{y}.parquet').as_posix()}'").df() for y in (2010, 2022)])
P["race"] = P.race.map(RACE)
co = {}
for (y, a, r), g in P[P.age_group.between(1, 5)].groupby(["year", "age_group", "race"]):
    if r in ("white", "brown", "black"):
        co[f"{y}|{AGE[a]}|{r}"] = {"with_mother": float(g.with_mother.sum() / g.n.sum()), "child_of_couple": float(g.child_of_couple.sum() / g.n.sum())}
F["coresidence"] = co
o10 = load(2010, "order")
o10["child"], o10["mother"] = o10.race.map(RACE), o10.mother_race.map(RACE)
o10["is_white"] = (o10.child == "white").astype(int)
F["rule_check_2010"] = {"couple": F["matrix"][2010]["brown|all"]["white"],
                        "order": ratio(o10[(o10.mother == "brown") & o10.age_group.isin([1, 2])], "is_white"),
                        "couple_share_of_order": float(len(D[2010]) / len(o10))}
# the design sensitivity: weighting areas as strata (2010)
d10 = D[2010][(D[2010].mother == "brown") & D[2010].age.isin(["0-4", "5-9"])]
F["design_check_2010"] = {"state_strata": ratio(d10, "is_white"), "weighting_area_strata": ratio(d10, "is_white", strata="wa")}
# ------------------------------------------------------------------ review 1: father or stepfather, siblings, who answered, coverage, category drift
v2 = {}
REL = {"04": "child of both (father)", "05": "child of the mother only (stepfather)", "06": "stepchild of the responsible man (stepfather)"}
for y, d in D.items():
    for m, outc in (("brown", "is_white"), ("black", "is_black")):
        sub = d[(d.mother == m) & d.age.isin(["0-4", "5-9"])]
        for (rel, part), g in sub.groupby(["rel", "partner"]):
            if len(g) >= 200 and rel in REL:
                v2[f"{y}|{m}|{outc}|{REL[rel]}|{part}"] = ratio(g, outc)
        v2[f"{y}|{m}|relation_mix"] = (sub.groupby("rel").w.sum() / sub.w.sum()).to_dict()
# siblings: households with two or more children 0-9 of the couple, reported in different races
sib = {}
for y, d in D.items():
    sub = d[d.age.isin(["0-4", "5-9"]) & d.mother.isin(["white", "brown", "black"])]
    g = sub.groupby("hh").agg(n=("race", "size"), k=("race", "nunique"), w=("w", "first"), mother=("mother", "first"), partner=("partner", "first"))
    g = g[g.n >= 2]
    for (m, part), x in g.groupby(["mother", "partner"]):
        if len(x) >= 200:
            sib[f"{y}|{m}|{part}"] = {"households": int(len(x)), "discordant": float((x.w * (x.k > 1)).sum() / x.w.sum())}
v2["siblings"] = sib
# who answered for the child, within the mother's and the partner's race (2022); who answered for the mother
d = D[2022]
inf2 = {}
sub = d[d.age.isin(["0-4", "5-9"]) & d.mother.isin(["white", "brown", "black"])]
for (m, part, who), g in sub.groupby(["mother", "partner", "informant"]):
    if len(g) >= 300 and who in ("mother", "partner", "other resident", "non-resident"):
        inf2[f"{m}|{part}|{who}"] = {"same": ratio(g, "same"), "white": ratio(g, "is_white"), "black": ratio(g, "is_black")}
inf2["share_0_14"] = {w: float(g.w.sum() / d[d.age.isin(["0-4", "5-9", "10-14"])].w.sum()) for w, g in d[d.age.isin(["0-4", "5-9", "10-14"])].groupby("informant")}
inf2["mother_informant"] = {w: float(g.w.sum() / sub.w.sum()) for w, g in sub.groupby("mother_informant")}
v2["informant"] = inf2
# the couple rule against the mother's order number (2010): coverage at 0-9 by mother's race; does the order number point at the couple's woman
o10["age_group"] = o10.age_group.astype(int)
cov = {}
for m in ("white", "brown", "black"):
    a_ = D[2010][(D[2010].mother == m) & D[2010].age.isin(["0-4", "5-9"])]
    b_ = o10[(o10.mother == m) & o10.age_group.isin([1, 2])]
    cov[m] = {"couple_share_of_order": float(len(a_) / len(b_)), "couple": ratio(a_, f"is_{ {'white': 'white', 'brown': 'white', 'black': 'black'}[m]}"),
              "order": ratio(b_.assign(is_white=(b_.child == "white").astype(int), is_black=(b_.child == "black").astype(int)),
                             f"is_{ {'white': 'white', 'brown': 'white', 'black': 'black'}[m]}")}
c10 = D[2010]
cov["order_agrees"] = float(c10.order_agrees.astype(float).mean())
v2["coverage"] = cov
# category drift: the 2022 Black and Brown mothers reweighted to the 2010 mothers' instruction and region
drift = {}
for m, outc in (("black", "is_black"), ("black", "is_white"), ("brown", "is_white")):
    a10 = D[2010][(D[2010].mother == m) & D[2010].age.isin(["0-4", "5-9"])]
    a22 = D[2022][(D[2022].mother == m) & D[2022].age.isin(["0-4", "5-9"])]
    p10 = a10.groupby(["instruction", "region"]).w.sum() / a10.w.sum()
    r22 = a22.groupby(["instruction", "region"]).apply(lambda g, o=outc: (g.w * g[o]).sum() / g.w.sum())
    common = p10.index.intersection(r22.index)
    drift[f"{m}|{outc}"] = {"2010": ratio(a10, outc)["est"], "2022": ratio(a22, outc)["est"],
                            "2022_at_2010_mothers": float((r22[common] * p10[common]).sum() / p10[common].sum()),
                            "instruction_2010": (a10.groupby("instruction").w.sum() / a10.w.sum()).to_dict(),
                            "instruction_2022": (a22.groupby("instruction").w.sum() / a22.w.sum()).to_dict()}
v2["drift"] = drift
F["review1"] = v2
OUT.write_text(json.dumps(F, indent=1, default=float), encoding="utf-8")
print("written", OUT, flush=True)
