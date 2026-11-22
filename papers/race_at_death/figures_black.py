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
        ]
fig, ax = plt.subplots(figsize=(7.0, 2.9))
y = np.arange(len(rows))[::-1]
for yi, (lab, x, col) in zip(y, rows, strict=True):
    ax.barh(yi, x["est"], color=col, height=0.62)
    if x.get("se"):
        ax.errorbar([x["est"]], [yi], xerr=[1.96 * x["se"]], fmt="none", color="black", capsize=2, lw=0.8)
    ax.text(x["est"] + (1.96 * x["se"] if x.get("se") else 0) + 0.015, yi, f"{x['est']:.2f}", va="center", fontsize=7)
ax.set_yticks(y, [r[0] for r in rows], fontsize=7)
ax.set_xlim(0, 1.08)
ax.set_xlabel("Proportion recorded Black (people who declared themselves Black, or children of such mothers)")
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c, label=lab) for lab, c in (("family (census 2010)", FAMILY), ("hospital (SIH)", HOSP), ("death certificate (SIM)", CERT))],
          fontsize=6.5, frameon=False, loc="lower right")
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
ax.set_ylim(0, 0.5)
ax.set_xticks([2013, 2018, 2023])
ax.set_xlabel("Year")
ax.set_title("B. Two records of the same\nfamilies, by year", fontsize=8, loc="left")
ax.set_ylabel("Proportion recorded Black")
ax.legend(fontsize=6, frameon=False, loc="center", bbox_to_anchor=(0.55, 0.55))
save(fig, "black_where_when")

# ---------------------------------------------------------------- 3. the hospital and the certificate
fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), gridspec_kw={"width_ratios": [1, 1.2], "wspace": 0.35})
ax = axes[0]
bh = BK["individual"]["black_mother_by_hospital"]
order = [h for h in ("black", "brown", "white") if h in bh]
for k, (c, col, lab) in enumerate((("black", "#000000", "certified Black"), ("brown", "#0072B2", "certified Brown"), ("white", "#E69F00", "certified White"))):
    xs = np.arange(len(order)) + (k - 1) * 0.26
    ax.bar(xs, [bh[h][c]["est"] for h in order], width=0.25, color=col, label=lab,
           yerr=[1.96 * bh[h][c]["se"] for h in order], error_kw={"lw": 0.7, "capsize": 1.5})
ax.set_xticks(range(len(order)), [f"{h.capitalize()}\n(n={bh[h]['black']['n']:,})" for h in order], fontsize=6.8)
ax.set_xlabel("Hospital's record of the mother at delivery")
ax.set_ylim(0, 1)
ax.set_ylabel("Proportion of the infant deaths")
ax.set_title("A. Black mothers' infants, by how the hospital\nrecorded the same mother at delivery", fontsize=8, loc="left")
ax.legend(fontsize=6.3, frameon=False, loc="upper right")
ax = axes[1]
fb = pd.read_parquet(RES / "black_facilities.parquet")
ax.scatter(fb.rate, fb.cert, s=np.sqrt(fb.deaths) * 6, color="#0072B2", alpha=0.6, lw=0)
ax.plot([0, 1], [0, 1], ":", color="#999999", lw=0.8)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.set_xlabel("Hospital: Black mothers recorded Black")
ax.set_ylabel("Certificate: Black mothers' infants\ndying there, certified Black")
ax.set_title(f"B. {len(fb)} hospitals with 10 or more such deaths\n(area: deaths)", fontsize=8, loc="left")
save(fig, "black_hospital")

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
