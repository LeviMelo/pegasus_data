"""The figures of paper 3 (the Black category), from results/black.json, results.json, spatial.json and the result tables beside them.

    python papers/race_at_death/figures_black.py        -> figures/black_*.png|pdf|svg
"""
import json
import math
import warnings
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


warnings.simplefilter("ignore")
matplotlib.use("Agg")
HERE = Path(__file__).parent
OUT, RES = HERE / "figures", HERE / "results"
R = json.loads((RES / "results.json").read_text(encoding="utf-8"))
S = json.loads((RES / "spatial.json").read_text(encoding="utf-8"))
BK = json.loads((RES / "black.json").read_text(encoding="utf-8"))
MC = json.loads((RES / "mechanism.json").read_text(encoding="utf-8"))
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})
OKABE = {"North": "#009E73", "Northeast": "#E69F00", "Southeast": "#0072B2", "South": "#CC79A7", "Centre-West": "#D55E00"}
FAMILY, HOSP, CERT = "#009E73", "#0072B2", "#D55E00"


def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- 1. the ladder: who records a Black person as Black
L = BK["ladder"]
rows = [("Mother's own declaration (reference)", {"est": 1.0, "se": 0.0}, "#777777"),
        ("Family: child under 1 (census)", {"est": L["family_child_0"], "se": 0.0}, FAMILY),
        ("Family: child 1-4 (census)", {"est": L["family_child_1_4"], "se": 0.0}, FAMILY),
        ("Hospital: the mother herself, at delivery", BK["hospital"]["black_bootstrap"]["black"], HOSP),
        ("Certificate: infant", L["certificate_infant"], CERT),
        ("Certificate: infant, municipalities under 25,600 births", L["certificate_infant_below_25600"], CERT),
        ("Certificate: child 1-4", L["certificate_1_4"], CERT),
        ("Count: hospital records Black, per Black-declared mother", MC["black"]["net"]["hospital_ratio"], HOSP),
        ("Count: infants certified Black, per infant of a Black mother", MC["black"]["net"]["certificate_ratio"], CERT),
        ]
fig, ax = plt.subplots(figsize=(6.9, 3.2))
y = np.arange(len(rows))[::-1]
for yi, (lab, x, col) in zip(y, rows, strict=True):
    ax.barh(yi, x["est"], color="white" if lab.startswith("Count") else col, edgecolor=col, hatch="////" if lab.startswith("Count") else None, height=0.62)
    if x.get("se"):
        ax.errorbar([x["est"]], [yi], xerr=[1.96 * x["se"]], fmt="none", color="black", capsize=2, lw=0.8)
    ax.text(x["est"] + (1.96 * x["se"] if x.get("se") else 0) + 0.015, yi, f"{x['est']:.2f}", va="center", fontsize=7)
ax.set_yticks(y, [r[0] for r in rows], fontsize=7)
ax.set_xlim(0, 1.08)
ax.axhline(1.5, color="#cccccc", lw=0.6)
ax.set_xlabel("Recorded Black: proportion of Black-declared mothers or their children (solid), or ratio of counts (hatched)")
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c, label=lab) for lab, c in (("family (census 2010)", FAMILY), ("hospital (SIH)", HOSP), ("death certificate (SIM)", CERT))],
          fontsize=6.5, frameon=False, loc="center right")
save(fig, "black_ladder")

# ---------------------------------------------------------------- 2. where and when
fig = plt.figure(figsize=(7.2, 3.4))
gs = fig.add_gridspec(1, 2, wspace=0.3)
ax = fig.add_subplot(gs[0, 0])
yrs = sorted(int(v) for v in R["infants"]["by_year"])
v = [R["infants"]["by_year"][str(t)]["rows"]["Preta"]["Preta"] for t in yrs]
ax.errorbar(yrs, [x["est"] for x in v], yerr=[1.96 * x["se"] for x in v], fmt="-o", color="black", ms=3, capsize=1.5, label="Brazil (linkage)")
pk = S["panel"]["KK"]
base = pk["by_macro"]["(Intercept)"]["Estimate"]
for rn, col in OKABE.items():
    a = base + (0 if rn == "North" else pk["by_macro"][f"macro{rn}"]["Estimate"])
    b = pk["by_macro"]["yc"]["Estimate"] + (0 if rn == "North" else pk["by_macro"][f"yc:macro{rn}"]["Estimate"])
    xs = np.array(yrs)
    ax.plot(xs, 1 / (1 + np.exp(-(a + b * (xs - 2018) / 10))), "-", color=col, lw=1.1, label=rn)
ax.set_ylim(0, 0.5)
ax.set_xticks([2013, 2018, 2023])
ax.set_xlabel("Year of death")
ax.set_ylabel("Proportion certified Black")
ax.set_title("A. By year and region\n(regional lines: model)", fontsize=8, loc="left")
ax.legend(fontsize=6, frameon=False, loc="upper left")
ax = fig.add_subplot(gs[0, 1])
hy = BK["hospital"]["black_by_year"]
hx = sorted(int(t) for t in hy)
ax.errorbar(hx, [hy[str(t)]["est"] for t in hx], yerr=[1.96 * hy[str(t)]["se"] for t in hx], fmt="-s", color=HOSP, ms=3, capsize=1, label="hospital: the Black mother,\nat delivery (by year of birth)")
ax.errorbar(yrs, [x["est"] for x in v], yerr=[1.96 * x["se"] for x in v], fmt="-o", color=CERT, ms=3, capsize=1, label="certificate: her infant\n(by year of death)")
st = MC["black"]["certificate_by_year_standardised"]
ax.plot([int(t) for t in st], [st[t]["standardised_2013"] for t in st], "--", color=CERT, lw=1, label="certificate, standardised\nto the mothers of 2013")
ax.set_ylim(0, 0.5)
ax.set_xticks([2013, 2018, 2023])
ax.set_xlabel("Year")
ax.set_title("B. Two records of the same\nfamilies, by year", fontsize=8, loc="left")
ax.set_ylabel("Proportion recorded Black")
ax.legend(fontsize=6, frameon=False, loc="center", bbox_to_anchor=(0.55, 0.55))
save(fig, "black_where_when")

# ---------------------------------------------------------------- 3. the hospital and the certificate
MB, MV = MC["black"], MC["movers"]
fig = plt.figure(figsize=(6.9, 3.1))
axes = [fig.add_axes(r) for r in ((0.075, 0.25, 0.19, 0.62), (0.505, 0.25, 0.21, 0.62), (0.815, 0.25, 0.17, 0.62))]
ax = axes[0]
bh = BK["individual"]["black_mother_by_hospital"]
order = [h for h in ("black", "brown", "white") if h in bh]
for k, (c, col, lab) in enumerate((("black", "#000000", "certified Black"), ("brown", "#0072B2", "certified Brown"), ("white", "#E69F00", "certified White"))):
    xs = np.arange(len(order)) + (k - 1) * 0.26
    ax.bar(xs, [bh[h][c]["est"] for h in order], width=0.25, color=col, label=lab,
           yerr=[1.96 * bh[h][c]["se"] for h in order], error_kw={"lw": 0.7, "capsize": 1.5})
ax.set_xticks(range(len(order)), [f"{h.capitalize()}\n(n={bh[h]['black']['n']:,})" for h in order], fontsize=5.6)
ax.set_xlabel("Hospital's record of the\nmother at delivery", fontsize=7)
ax.set_ylim(0, 1)
ax.set_ylabel("Proportion of the infant deaths", fontsize=7)
ax.set_title("A. Certificate by the\nhospital's record", fontsize=7.5, loc="left")
ax.legend(fontsize=5.8, frameon=False, loc="upper right", handlelength=1)
ax = axes[1]
pl = MB["practice_loo_eb"]
OR = [("Same delivery hospital (MH)", MB["mh_delivery_hospital"]["est"], MB["mh_delivery_hospital"]["lo"], MB["mh_delivery_hospital"]["hi"]),
      ("Same delivery hospital, adjusted", MB["clogit_delivery_hospital_adjusted"]["or"], MB["clogit_delivery_hospital_adjusted"]["lo"], MB["clogit_delivery_hospital_adjusted"]["hi"]),
      ("Died where delivered", MB["clogit_death_estab_died_there"]["or"], MB["clogit_death_estab_died_there"]["lo"], MB["clogit_death_estab_died_there"]["hi"]),
      ("Died elsewhere (no chart)", MB["clogit_death_estab_elsewhere"]["or"], MB["clogit_death_estab_elsewhere"]["lo"], MB["clogit_death_estab_elsewhere"]["hi"])]
for k, lab in (("practice", "Practice alone"), ("practice_composition_region_year", "Practice, + mothers, region-year"), ("practice_person", "Practice, + mother's record")):
    c_, s_ = pl[k]["coef"], pl[k]["se"]
    OR.append((lab, math.exp(c_), math.exp(c_ - 1.96 * s_), math.exp(c_ + 1.96 * s_)))
OR.append(("Mother's record, + practice", pl["practice_person"]["hb_or"], math.exp(math.log(pl["practice_person"]["hb_or"]) - 1.96 * pl["practice_person"]["hb_se"]),
           math.exp(math.log(pl["practice_person"]["hb_or"]) + 1.96 * pl["practice_person"]["hb_se"])))
yy = np.arange(len(OR))[::-1]
for j, (lab, e_, lo_, hi_) in enumerate(OR):
    col = "#000000" if j < 4 or j == 7 else HOSP
    ax.errorbar([e_], [yy[j]], xerr=[[e_ - lo_], [hi_ - e_]], fmt="o", color=col, ms=3, capsize=1.5, lw=0.9)
    ax.text(3.6, yy[j], f"{e_:.2f}", va="center", fontsize=5.8)
ax.axvline(1, color="#999999", lw=0.7)
ax.axhline(3.5, color="#dddddd", lw=0.6)
ax.set_xscale("log")
ax.set_xticks([1, 2, 3], ["1", "2", "3"])
ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
ax.set_xlim(0.8, 4.2)
ax.set_yticks(yy, [o[0] for o in OR], fontsize=6.0)
ax.set_xlabel("Odds ratio of certified Black\n(black: mother recorded Black;\nblue: per logit of hospital practice)", fontsize=6.3)
ax.set_title("B. Person or hospital", fontsize=7.5, loc="left")
ax = axes[2]
for k, (h, col, mk) in enumerate((("same hospital", "#000000", "o"), ("another hospital", HOSP, "s"))):
    vals = [MV[f"hospital_black_after_not|{h}"], MV[f"hospital_black_again|{h}"]]
    ax.errorbar([0 + k * 0.08, 1 + k * 0.08], [v_["est"] for v_ in vals], yerr=[1.96 * v_["se"] for v_ in vals], fmt="-" + mk, color=col, ms=3.5, capsize=1.5, lw=1,
                label=h)
ax.set_xticks([0.04, 1.04], ["not Black", "Black"], fontsize=6.5)
ax.set_xlim(-0.3, 1.35)
ax.set_ylim(0, 1)
ax.set_xlabel("Hospital's record at\nthe first delivery", fontsize=7)
ax.set_ylabel("Recorded Black at the next delivery", fontsize=7)
ax.set_title("C. Same mother,\ntwo births", fontsize=7.5, loc="left")
ax.legend(fontsize=5.8, frameon=False, loc="lower right", handlelength=1.2)
for a_ in axes:
    a_.tick_params(labelsize=6.3)
save(fig, "black_hospital")

fig, ax = plt.subplots(figsize=(3.4, 3.0))
fb = pd.read_parquet(RES / "black_facilities.parquet")
ax.scatter(fb.rate, fb.cert, s=np.sqrt(fb.deaths) * 6, color="#0072B2", alpha=0.6, lw=0)
ax.plot([0, 1], [0, 1], ":", color="#999999", lw=0.8)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.set_xlabel("Hospital: Black mothers recorded Black")
ax.set_ylabel("Certificate: Black mothers' infants\ndying there, certified Black")
ax.set_title(f"{len(fb)} hospitals with 10 or more such deaths (area: deaths)", fontsize=7, loc="left")
save(fig, "black_practice")

# ---------------------------------------------------------------- 4. who certifies and the individual terms (Black mothers' infants, full model)
FX = S["multilevel"]["black_black"]["full_fit"]["fixed"]
TERMS = [("certifiermedical examiner (IML)", "certifier: medical examiner"), ("certifierdeath verification service", "certifier: verification service"),
         ("certifiersubstitute physician", "certifier: substitute physician"), ("death_placehome", "died at home"), ("death_placeother health facility", "died in other facility"),
         ("age_group7-27 days", "died at 7-27 days"), ("age_group28-364 days", "died at 28-364 days"), ("cause_groupcongenital", "congenital anomaly"),
         ("cause_groupexternal", "external cause"), ("school0-3", "mother 0-3 years of school"), ("school4-7", "mother 4-7 years"), ("school12 or more", "mother 12+ years"),
         ("mother_age<20", "mother under 20"), ("mother_age35+", "mother 35 or older"), ("low_weight<2500 g", "birth weight < 2500 g"), ("z_lgdp", "GDP per capita (+1 SD)"),
         ("z_illit", "illiteracy (+1 SD)"), ("capital", "state capital"), ("regionNorth", "North (v. Southeast)"), ("regionNortheast", "Northeast"), ("regionSouth", "South"),
         ("regionCentre-West", "Centre-West"), ("yc", "per decade")]
fig, ax = plt.subplots(figsize=(5.6, 5.2))
yy = np.arange(len(TERMS))[::-1]
for j, (t, lab) in enumerate(TERMS):
    e_, s_ = FX[t]["est"], FX[t]["se"]
    ax.errorbar([math.exp(e_)], [yy[j]], xerr=[[math.exp(e_) - math.exp(e_ - 1.96 * s_)], [math.exp(e_ + 1.96 * s_) - math.exp(e_)]], fmt="o", color="black", ms=3.5,
                capsize=1.5, lw=0.9)
ax.axvline(1, color="#999999", lw=0.7)
ax.set_xscale("log")
ax.set_xticks([0.25, 0.5, 1, 2, 4], ["0.25", "0.5", "1", "2", "4"])
ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
ax.set_xlim(0.2, 5)
ax.set_yticks(yy, [lab for _, lab in TERMS], fontsize=6.8)
ax.set_xlabel("Odds ratio of being certified Black (Black mothers' infants)")
save(fig, "black_terms")
print("black figures written")
