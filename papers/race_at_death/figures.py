"""The figures of the paper, from results/results.json (this file) and results/spatial.json (figures_space.py, run at the end).
Each is saved as PNG (for the manuscript), PDF and SVG in out/.

    python papers/race_at_death/figures.py

Main: 1 design, 2 three classifications, 3 the municipality (maps), 4 composition, state and context, 5 time by place,
6 competing explanations (multilevel), 7 mortality under the classifications, 8 consequences by immediate region,
9 ages 15-24 by cause. Supplementary: S1 validation, S2 regions, S3 model of the certifier, S4 schooling and partner,
S5 composition gradient, S6 age, S7 cohorts, S8-S10 maps.
One rule for every estimate of the candidate estimator: not drawn when its standard error exceeds 0.15 or it leaves 0 to 1 by
more than two standard errors (the tables' "not estimable").
"""
import json
import math
import runpy
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)
R = json.loads((HERE / "results" / "results.json").read_text(encoding="utf-8"))
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})
EN = {"Branca": "White", "Preta": "Black", "Parda": "Brown", "Indigena": "Indigenous", "other": "Other/none"}
COL = {"Branca": "#E69F00", "Parda": "#0072B2", "Preta": "#000000", "Indigena": "#009E73"}
BLUE, ORANGE, GREEN, GREY, PURPLE = "#0072B2", "#D55E00", "#009E73", "#777777", "#CC79A7"
ORDER = ["Branca", "Parda", "Preta", "Indigena"]


def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def ci95(x):
    return 1.96 * x["se"]


def ok(x):
    """The tables' rule: drawn unless the standard error exceeds 0.15 or the estimate leaves 0 to 1 by more than two errors."""
    return x is not None and x.get("se") is not None and x["se"] <= 0.15 and -2 * x["se"] <= x["est"] <= 1 + 2 * x["se"]


# ---------------------------------------------------------------- Figure 1: two levels of comparison and the context
fig, ax = plt.subplots(figsize=(7.2, 3.5))
ax.set_xlim(0, 10)
ax.set_ylim(0.6, 5.6)
ax.axis("off")


def box(x, y, w, h, title, body, col):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04", fc="white", ec=col, lw=1.5))
    ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="top", fontsize=8.2, weight="bold", color=col)
    ax.text(x + w / 2, y + h - 0.75, body, ha="center", va="top", fontsize=6.8, linespacing=1.35)


ax.text(0.1, 5.45, "Individual level: the same person on two records", fontsize=8, weight="bold", color="#333333", va="top")
box(0.1, 2.75, 3.0, 2.4, "Birth record (SINASC)", "mother's declared race\n(cohorts born from 2012)\nmother's schooling and age,\nbirth weight", BLUE)
box(4.3, 2.75, 3.0, 2.4, "Death certificate (SIM)", "race recorded by the certifier\n(deaths 2013-2024)\ncertifier, place, cause,\nestablishment", ORANGE)
ax.add_patch(FancyArrowPatch((3.15, 3.9), (4.25, 3.9), arrowstyle="<->", mutation_scale=12, color=GREY, lw=1.2))
ax.text(3.7, 4.05, "infants: one-to-one\nlinkage", ha="center", va="bottom", fontsize=6.3, color="#333333")
ax.text(3.7, 3.75, "after infancy:\ncandidate estimator", ha="center", va="top", fontsize=6.3, color="#333333")
ax.text(7.6, 5.45, "Population reference", fontsize=8, weight="bold", color="#333333", va="top")
box(7.6, 2.75, 2.3, 2.4, "Census 2010 sample", "race the household reports\nfor other children,\nby the mother's race, age\nand municipality", GREEN)
ax.add_patch(FancyArrowPatch((7.58, 3.9), (7.32, 3.9), arrowstyle="->", mutation_scale=10, color=GREY, lw=1.0))
ax.text(8.75, 2.68, "compared with the certificate by\nmother's race, age and place", ha="center", va="top", fontsize=6.2, color="#333333")
ax.add_patch(FancyBboxPatch((0.1, 0.75), 9.8, 1.3, boxstyle="round,pad=0.04", fc="#F4F4F4", ec="#999999", lw=1.0))
ax.text(5.0, 1.92, "The place: 5,570 municipalities, 510 immediate and 133 intermediate regions, 27 states, 2013-2023",
        ha="center", va="top", fontsize=8, weight="bold", color="#333333")
ax.text(5.0, 1.55, "racial composition of live births  |  GDP per capita, illiteracy, low income, urbanisation, size  |  state capital, metropolitan region\n"
        "physicians, death verification and medico-legal certification, deaths in hospital, race left blank  |  contiguity of municipalities",
        ha="center", va="top", fontsize=6.8, linespacing=1.5)
for x in (1.6, 5.8):
    ax.add_patch(FancyArrowPatch((x, 2.1), (x, 2.7), arrowstyle="-", color="#999999", lw=0.8, linestyle=(0, (2, 2))))
save(fig, "design")

# ---------------------------------------------------------------- Figure 2: the classifications, under one year and at 1-4 years
fig = plt.figure(figsize=(7.2, 5.6))
gsf = fig.add_gridspec(3, 3, height_ratios=[1, 1, 0.06], hspace=0.85, wspace=0.12)
axes = np.array([[fig.add_subplot(gsf[r, k]) for k in range(3)] for r in range(2)])
rows = (("0", "under 1 year", "linkage"), ("1-4", "1-4 years", "candidate estimator"))
for r, (band, lab, how) in enumerate(rows):
    D = R["decomposition"][band]
    fam = np.array([[D[m][c]["family"] for c in ORDER] for m in ORDER])
    cer = np.array([[D[m][c]["certificate"] for c in ORDER] for m in ORDER])
    for k, (mat, title, cmap, lim) in enumerate(((fam, f"Family (census), {lab}", "Blues", (0, 1)), (cer, f"Certificate, {lab}", "Blues", (0, 1)),
                                                  (cer - fam, "Certificate minus family", "PuOr_r", (-0.4, 0.4)))):
        ax = axes[r, k]
        im = ax.imshow(mat, cmap=cmap, vmin=lim[0], vmax=lim[1])
        for i in range(4):
            for j in range(4):
                v = mat[i, j]
                txt = f"{v:+.2f}" if k == 2 else f"{v:.2f}"
                txt = txt.replace("-0.00", "0.00").replace("+0.00", "0.00")
                ax.text(j, i, txt, ha="center", va="center", fontsize=6.8, color="white" if (abs(v) > 0.6 if k < 2 else abs(v) > 0.28) else "black")
        ax.set_xticks(range(4), [EN[c] for c in ORDER], rotation=40, ha="right", fontsize=6.8)
        ax.set_yticks(range(4), [EN[c] for c in ORDER] if k == 0 else [], fontsize=6.8)
        ax.set_title(f"{'ABCDEF'[3 * r + k]}. {title}", fontsize=7.3, loc="left")
        for sp in ax.spines.values():
            sp.set_visible(False)
        if r == 1:
            cb = fig.colorbar(im, cax=fig.add_subplot(gsf[2, k]), orientation="horizontal")
            cb.set_label("Proportion" if k < 2 else "Difference", fontsize=7)
            cb.ax.tick_params(labelsize=6)
    axes[r, 0].set_ylabel("Mother's race")
save(fig, "classifications")

# ---------------------------------------------------------------- Figure 7: mortality under the classifications
fig, axes = plt.subplots(1, 4, figsize=(7.2, 2.9), gridspec_kw={"width_ratios": [1, 1, 1, 1.35], "wspace": 0.55})
blocks = [("A. Under 1 year\nper 1,000 births", R["infant_rates"]), ("B. 1-4 years\nper 100,000", R["children"]["1-4"]["rates"]),
          ("C. 5-9 years\nper 100,000", R["children"]["5-9"]["rates"])]
for ax, (title, B) in zip(axes[:3], blocks, strict=True):
    for race in ("Branca", "Parda", "Preta"):
        a, b = B["by_mother"][race], B["by_certificate"][race]
        ax.plot([0, 1], [a["est"], b["est"]], "-", color=COL[race], lw=1.3)
        ax.errorbar([0], [a["est"]], yerr=[ci95(a)], fmt="o", color=COL[race], ms=4, capsize=2)
        ax.errorbar([1], [b["est"]], yerr=[ci95(b)], fmt="s", color=COL[race], ms=4, capsize=2)
    top = 1.08 * max(B[k][r]["est"] + ci95(B[k][r]) for k in ("by_mother", "by_certificate") for r in ("Branca", "Parda", "Preta"))
    ax.set_ylim(0, top)
    for xpos, key, ha, dx in ((0, "by_mother", "right", -6), (1, "by_certificate", "left", 6)):
        last = -1e9
        for race in sorted(("Branca", "Parda", "Preta"), key=lambda r, key=key, B=B: B[key][r]["est"]):
            ypos = max(B[key][race]["est"], last + 0.06 * top)
            ax.text(xpos + dx / 55, ypos, f"{B[key][race]['est']:.1f}", ha=ha, va="center", fontsize=6.3, color=COL[race])
            last = ypos
    ax.set_xticks([0, 1], ["mother", "certif."], fontsize=6.3)
    ax.set_xlabel("race by", fontsize=6.3, color="#555555")
    ax.set_xlim(-0.8, 1.8)
    ax.set_title(title, fontsize=7.3, loc="left")
axes[0].set_ylabel("Mortality rate over the births of the same cohorts")
ax = axes[3]
rows = [("under 1 y", R["infant_rates"], R["infant_rates"]["ratio_household"], R["infant_rates"]["ratio_certificate_population"]),
        ("1-4 y", R["children"]["1-4"]["rates"], R["children"]["1-4"]["ratio_household"], R["children"]["1-4"]["conventional_2016_2024"]["ratio_certificate_population"]),
        ("5-9 y", R["children"]["5-9"]["rates"], R["children"]["5-9"]["ratio_household"], None)]
for y, (lab, B, hh, pop) in enumerate(rows[::-1]):
    m, c = B["ratio_mother"]["Branca"], B["ratio_certificate"]["Branca"]
    lo, hi = m["est"] * math.exp(-1.96 * m["se"] / m["est"]), m["est"] * math.exp(1.96 * m["se"] / m["est"])
    ax.errorbar([m["est"]], [y + 0.27], xerr=[[m["est"] - lo], [hi - m["est"]]], fmt="o", color=BLUE, ms=4, capsize=2)
    ax.plot([hh["Branca"]], [y + 0.09], "D", color=GREEN, ms=4)
    ax.plot([c["est"]], [y - 0.09], "s", color=ORANGE, ms=4)
    if pop is not None:
        ax.plot([pop], [y - 0.27], "^", color=PURPLE, ms=4.5)
ax.axvline(1, color=GREY, lw=0.8)
ax.set_xscale("log")
ax.set_xticks([0.5, 0.67, 1, 1.5], ["0.5", "0.67", "1", "1.5"])
ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
ax.set_yticks(range(3), [r[0] for r in rows[::-1]])
ax.set_ylim(-0.6, 2.6)
ax.set_xlabel("Rate ratio, White to Brown")
ax.set_title("D. White to Brown\nrate ratio", fontsize=7.3, loc="left")
fig.legend(handles=[plt.Line2D([], [], marker="o", ls="", color=BLUE, label="deaths and births by mother's race"),
                    plt.Line2D([], [], marker="D", ls="", color=GREEN, label="both through the family's classification (no interval)"),
                    plt.Line2D([], [], marker="s", ls="", color=ORANGE, label="certified deaths over births by mother's race"),
                    plt.Line2D([], [], marker="^", ls="", color=PURPLE, label="certified deaths over the census-based population")]
           + [plt.Line2D([], [], color=COL[r], label=EN[r]) for r in ("Branca", "Parda", "Preta")],
           fontsize=6.3, frameon=False, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.17))
save(fig, "mortality")

# ---------------------------------------------------------------- Figure 9: cause of death at 15-24
kinds = ["natural", "suicide", "transport", "other external", "other assault", "assault by firearm", "legal intervention"]
KL = {"natural": "Natural causes", "suicide": "Suicide", "transport": "Transport accidents", "other external": "Other external causes", "other assault": "Assault, other means",
      "assault by firearm": "Assault by firearm", "legal intervention": "Legal intervention"}
Y = R["youth"]["by_kind"]
fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.1), gridspec_kw={"width_ratios": [1.2, 1], "wspace": 0.35})
ax = axes[0]
for i, k in enumerate(kinds[::-1]):
    for off, sex, colr in ((0.0, None, "#333333"), (0.25, "M", BLUE), (-0.25, "F", ORANGE)):
        src = Y[k] if sex is None else R["youth"]["by_kind_sex"][k][sex]
        x = src["rows"].get("Branca", {}).get("Branca")
        if not ok(x):
            continue
        ax.errorbar([x["est"]], [i + off], xerr=[ci95(x)], fmt="o" if sex is None else ("^" if sex == "M" else "v"), color=colr, ms=4.5 if sex is None else 3,
                    capsize=1.5, label={None: "both sexes", "M": "men", "F": "women"}[sex] if k == "natural" else None)
        if sex is None:
            ax.text(1.02, i, f"{x['est']:.2f}", ha="left", va="center", fontsize=6.3, transform=ax.get_yaxis_transform())
ax.set_xlim(0, 1)
ax.set_title("A. By cause of death and sex", fontsize=7.5, loc="left")
ax.set_xlabel("Proportion certified White (both sexes on the right)")
ax.set_yticks(range(len(kinds)), [f"{KL[k]} (n={int(Y[k]['deaths']):,})" for k in kinds[::-1]], fontsize=6.6)
ax.legend(fontsize=6.3, frameon=False, loc="lower right")
ax = axes[1]
BC = R["context"]["youth"]["by_composition"]
for k, col, lab, dx in (("natural", BLUE, "natural causes", -0.012), ("external, not assault", GREEN, "external, not assault", 0.0),
                        ("assault", ORANGE, "assault and legal intervention", 0.012)):
    pts = [((x["white_share"][0] + min(x["white_share"][1], 1)) / 2 + dx, x["matrix"]["rows"].get("Branca", {}).get("Branca")) for x in BC[k]]
    pts = [p for p in pts if ok(p[1])]
    ax.errorbar([q[0] for q in pts], [q[1]["est"] for q in pts], yerr=[ci95(q[1]) for q in pts], fmt="-o", color=col, ms=3.5, lw=1.2, capsize=1.5, label=lab)
ax.set_ylim(0, 1.15)
ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
ax.set_xlim(0, 1)
ax.set_title("B. By cause and municipal composition", fontsize=7.5, loc="left")
ax.set_xlabel("Share of White among local live births")
ax.set_ylabel("Proportion certified White")
ax.legend(fontsize=6.3, frameon=False, loc="upper left", ncol=1, bbox_to_anchor=(0, 1.02))
save(fig, "youth_cause")

# ---------------------------------------------------------------- Supplementary figures
V = [r for r in R["validation"] if r["size"] != "all"]
fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0))
ax = axes[0]
mark = {"<400": "o", "400-1,599": "s", "1,600-6,399": "^", "6,400-25,599": "D", ">=25,600": "x"}
for r in V:
    for m in ORDER:
        if m not in r["candidates"]["rows"] or m not in r["linkage"]["rows"]:
            continue
        for c in ORDER:
            a, b = r["linkage"]["rows"][m][c]["est"], r["candidates"]["rows"][m][c]
            if b["se"] <= 0.15:
                ax.errorbar([a], [b["est"]], yerr=[ci95(b)], fmt=mark[r["size"]], color=GREY if r["size"] == ">=25,600" else BLUE, ms=3, capsize=1, alpha=0.8,
                            label=r["size"] if (m, c) == ("Branca", "Branca") else None)
ax.plot([0, 1], [0, 1], "-", color="black", lw=0.6)
ax.set_xlabel("One-to-one linkage")
ax.set_ylabel("Estimate without individual linkage")
ax.set_title("A. Every cell of the table, by municipality size", fontsize=7.5, loc="left")
ax.legend(fontsize=6, frameon=False, title="Live births per year", title_fontsize=6)
ax = axes[1]
ys = sorted(int(y) for y in R["infants"]["by_year"])
for m in ("Branca", "Parda", "Preta"):
    ax.errorbar(ys, [R["infants"]["by_year"][str(y)]["rows"][m][m]["est"] for y in ys], yerr=[ci95(R["infants"]["by_year"][str(y)]["rows"][m][m]) for y in ys], fmt="-o", color=COL[m], ms=3,
                capsize=1.5, label=f"{EN[m]} mother, certified {EN[m]}")
ax.set_ylim(0, 1)
ax.set_xlabel("Year of death")
ax.set_ylabel("Proportion of infant deaths")
ax.set_title("B. Infant deaths, one-to-one linkage, by year", fontsize=7.5, loc="left")
ax.legend(fontsize=6.3, frameon=False)
save(fig, "validation")

fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0), sharey=True)
regs = ["North", "Northeast", "Southeast", "South", "Centre-West"]
for ax, lab in zip(axes, ("1-4", "5-9"), strict=True):
    for i, rn in enumerate(regs):
        B = R["children"][lab]["by_region"][rn]
        m, c = B["rates"]["ratio_mother"]["Branca"], B["rates"]["ratio_certificate"]["Branca"]
        if m["est"] > 0 and m["se"] / m["est"] < 0.6:
            lo, hi = m["est"] * math.exp(-1.96 * m["se"] / m["est"]), m["est"] * math.exp(1.96 * m["se"] / m["est"])
            ax.errorbar([m["est"]], [i + 0.2], xerr=[[m["est"] - lo], [hi - m["est"]]], fmt="o", color=BLUE, ms=4, capsize=2)
        else:
            ax.text(0.27, i + 0.2, "n.e.", fontsize=6, color=BLUE, va="center")
        ax.plot([B["ratio_household"]["Branca"]], [i], "D", color=GREEN, ms=4)
        ax.plot([c["est"]], [i - 0.2], "s", color=ORANGE, ms=4)
    ax.axvline(1, color=GREY, lw=0.8)
    ax.set_xscale("log")
    ax.set_xlim(0.25, 4.5)
    ax.set_xticks([0.5, 1, 2, 4], ["0.5", "1", "2", "4"])
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_title(f"Ages {lab}", fontsize=8, loc="left")
    ax.set_xlabel("Mortality rate ratio, White to Brown")
axes[0].set_yticks(range(5), regs)
fig.legend(handles=[plt.Line2D([], [], marker="o", ls="", color=BLUE, label="mother's race (n.e.: error above 0.6 of the estimate)"),
                    plt.Line2D([], [], marker="D", ls="", color=GREEN, label="family's classification (no interval)"),
                    plt.Line2D([], [], marker="s", ls="", color=ORANGE, label="certified race")], fontsize=6.3, frameon=False, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.1))
save(fig, "regional_ratios_1to9")

fig, axes = plt.subplots(1, 4, figsize=(7.2, 2.5), sharey=True)
for ax, (m, c, title) in zip(axes, (("Parda", "Branca", "Brown mother,\ncertified White"), ("Branca", "Parda", "White mother,\ncertified Brown"), ("Preta", "Parda", "Black mother,\ncertified Brown"),
                                    ("Preta", "Preta", "Black mother,\ncertified Black")), strict=True):
    for prior, ls in (("certified", "--"), ("births", "-.")):
        fit = [x for x in R["mixture"]["infants"][prior][m]["fit"] if x["class"] == c]
        xs = [R["gradient_infants"][[b["bin"] for b in R["gradient_infants"]].index(x["bin"])]["white_share"] for x in fit]
        if prior == "certified":
            ax.plot(xs, [x["family"] for x in fit], "-s", color=GREEN, ms=3, lw=1, label="family (census, under 1)")
            ax.plot(xs, [x["certificate"] for x in fit], "o", color=ORANGE, ms=3.5, label="certificate")
        ax.plot(xs, [x["model"] for x in fit], ls, color="black" if prior == "certified" else GREY, lw=1,
                label="model, reference: local certified" if prior == "certified" else "model, reference: local births")
    ax.set_title(title, fontsize=7.5)
    ax.set_ylim(0, 1)
    ax.set_xlim(0, 1)
axes[0].set_ylabel("Proportion of infant deaths")
fig.text(0.5, -0.04, "Share of White among the live births of the municipality", ha="center", fontsize=8)
fig.legend(*axes[0].get_legend_handles_labels(), fontsize=6.3, frameon=False, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.17))
save(fig, "mixture")

fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.9), gridspec_kw={"wspace": 0.35})
ax = axes[0]
IP = R["census"]["by_instruction_partner"]
levels = list(IP)
for partner, col in (("White", COL["Branca"]), ("Brown", COL["Parda"]), ("Black", "#000000")):
    ax.plot(range(len(levels)), [IP[lv][partner]["Parda"]["Branca"]["est"] for lv in levels], "-o", color=col, ms=3.5, lw=1.2, label=f"partner {partner}")
ax.set_xticks(range(len(levels)), ["none or\nincomplete", "primary", "secondary", "higher"], fontsize=6.3)
ax.set_ylim(0, 1)
ax.set_title("A. Family: Brown mother,\nchild reported White (ages 0-9)", fontsize=7.3, loc="left")
ax.set_xlabel("Mother's level of instruction")
ax.set_ylabel("Proportion")
ax.legend(fontsize=6.3, frameon=False)
SCH = ["0-3", "4-7", "8-11", "12 or more"]
ax = axes[1]
CSc = R["context"]["children"]["by_schooling"]
for (m, c), col, lab in ((("Parda", "Branca"), COL["Parda"], "Brown mother, White"), (("Branca", "Branca"), COL["Branca"], "White mother, White"),
                         (("Preta", "Preta"), "#000000", "Black mother, Black")):
    pts = [(i, CSc[s]["rows"][m][c]) for i, s in enumerate(SCH) if m in CSc[s]["rows"] and ok(CSc[s]["rows"][m][c])]
    ax.errorbar([p[0] for p in pts], [p[1]["est"] for p in pts], yerr=[ci95(p[1]) for p in pts], fmt="-o", color=col, ms=3.5, lw=1.2, capsize=1.5, label=lab)
ax.set_xticks(range(4), SCH, fontsize=6.8)
ax.set_ylim(0, 1.1)
ax.set_title("B. Certificate, deaths at 1-9 years", fontsize=7.3, loc="left")
ax.set_xlabel("Mother's schooling (years)")
ax.legend(fontsize=6, frameon=False, loc="upper left")
ax = axes[2]
YS = R["context"]["youth"]["by_schooling_composition"]
for (k, lab), col in zip((("0.0-0.3", "under 30% White births"), ("0.3-0.6", "30% to 59%"), ("0.6-1.0", "60% or more")), (ORANGE, GREEN, BLUE), strict=True):
    pts = [(i, YS[k][s_]["rows"]["Branca"]["Branca"]) for i, s_ in enumerate(SCH) if "Branca" in YS[k][s_]["rows"] and ok(YS[k][s_]["rows"]["Branca"]["Branca"])]
    ax.errorbar([q[0] for q in pts], [q[1]["est"] for q in pts], yerr=[ci95(q[1]) for q in pts], fmt="-o", color=col, ms=3.5, lw=1.2, capsize=1.5, label=lab)
ax.set_xticks(range(4), SCH, fontsize=6.8)
ax.set_ylim(0, 1.1)
ax.set_title("C. Deaths at 15-24 years: White\nat birth, certified White", fontsize=7.3, loc="left")
ax.set_xlabel("Mother's schooling (years)")
ax.legend(fontsize=6, frameon=False, loc="lower right")
save(fig, "family_schooling")

# S5: the composition gradient (family under 1 with infant certificates; family 1-4 with certificates at 1-9)
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7), sharex=True, sharey=True)
panels = [("Parda", "Branca", "A. Brown mother,\nchild classed White"), ("Branca", "Parda", "B. White mother,\nchild classed Brown"), ("Preta", "Preta", "C. Black mother,\nchild classed Black")]
for ax, (m, c, title) in zip(axes, panels, strict=True):
    for band, ls, lab in (("0", "-", "family, under 1 year"), ("1-4", ":", "family, 1-4 years")):
        g = [b for b in R["census"]["gradient"][band] if m in b["matrix"] and b["matrix"][m]["records"] >= 200]
        ax.plot([b["white_share"] for b in g], [b["matrix"][m].get(c, {"est": 0})["est"] for b in g], ls, color=GREEN, marker="s", ms=3, lw=1.2, label=lab)
    g = [b for b in R["gradient_infants"] if m in b["matrix"]["rows"] and b["matrix"]["rows"][m]["n"] >= 100]
    ax.errorbar([b["white_share"] for b in g], [b["matrix"]["rows"][m][c]["est"] for b in g], yerr=[ci95(b["matrix"]["rows"][m][c]) for b in g], fmt="-o", color=ORANGE,
                ms=3.5, lw=1.2, capsize=1.5, label="certificate, under 1 year")
    g = [b for b in R["children"]["1-9"]["gradient"] if m in b["matrix"]["rows"] and ok(b["matrix"]["rows"][m][c])]
    ax.errorbar([b["white_share"] for b in g], [b["matrix"]["rows"][m][c]["est"] for b in g], yerr=[ci95(b["matrix"]["rows"][m][c]) for b in g], fmt="--^", color=PURPLE,
                ms=3.5, lw=1.0, capsize=1.5, label="certificate, 1-9 years")
    ax.set_title(title, fontsize=7.5, loc="left")
    ax.set_ylim(0, 1)
    ax.set_xlim(0, 1)
axes[0].set_ylabel("Proportion of children")
axes[1].set_xlabel("Share of White among the live births of the municipality")
fig.legend(*axes[0].get_legend_handles_labels(), fontsize=6.3, frameon=False, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.13))
save(fig, "gradient_1to9")

# S6: age. A, B: family by age 0-24 and certificate 0-9; C: natural against assault at 15-24 (born 2000-2009)
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7), gridspec_kw={"wspace": 0.3})
for ax, (m, title) in zip(axes[:2], (("Preta", "A. Black mother,\nchild classed Black"), ("Parda", "B. Brown mother,\nchild classed Brown")), strict=True):
    ages = sorted(int(a) for a in R["census"]["by_age"])
    ax.plot(ages, [R["census"]["by_age"][str(a)][m][m]["est"] for a in ages], "-", color=GREEN, lw=1.4, label="family (census)")
    ax.errorbar([0], [R["infants"]["linkage"]["rows"][m][m]["est"]], yerr=[ci95(R["infants"]["linkage"]["rows"][m][m])], fmt="o", color=ORANGE, ms=4, capsize=2,
                label="certificate")
    ca = [a for a in range(1, 10) if m in R["children_by_age"][str(a)]["rows"] and ok(R["children_by_age"][str(a)]["rows"][m][m])]
    ax.errorbar(ca, [R["children_by_age"][str(a)]["rows"][m][m]["est"] for a in ca], yerr=[ci95(R["children_by_age"][str(a)]["rows"][m][m]) for a in ca], fmt="o",
                color=ORANGE, ms=3, capsize=1.5)
    ax.set_ylim(0, 1)
    ax.set_xlim(-0.5, 24.5)
    ax.set_title(title, fontsize=7.5, loc="left")
    ax.set_xlabel("Age of the child (years)")
axes[0].set_ylabel("Proportion classed with the mother's race")
axes[0].legend(fontsize=6.3, frameon=False, loc="upper left")
ax = axes[2]
for kind, col, lab in (("natural", BLUE, "natural causes"), ("assault", ORANGE, "assault and legal intervention")):
    Yk = R["youth"]["by_age"][kind]
    aa = [a for a in range(15, 25) if "Branca" in Yk[str(a)]["rows"] and ok(Yk[str(a)]["rows"]["Branca"]["Branca"])]
    ax.errorbar(aa, [Yk[str(a)]["rows"]["Branca"]["Branca"]["est"] for a in aa], yerr=[ci95(Yk[str(a)]["rows"]["Branca"]["Branca"]) for a in aa], fmt="-o", color=col, ms=3,
                lw=1, capsize=1.5, label=lab)
ax.set_ylim(0, 1)
ax.set_ylabel("White at birth, certified White")
ax.set_xticks(range(15, 25, 2))
ax.set_title(f"C. Ages 15-24 (born {R['youth']['birth_years'][0]}-{R['youth']['birth_years'][1]})", fontsize=7.5, loc="left")
ax.set_xlabel("Age at death (years)")
ax.legend(fontsize=6.3, frameon=False, loc="lower left")
save(fig, "age")

# S7: the same cohorts across censuses
coh = {(r["cohort"], r["year"]): r for r in R["cohorts"]}
cb_ = {r["cohort"]: r for r in R["cohorts_birth"]}
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7), sharex=True)
cohorts = sorted({k[0] for k in coh})
cmap = plt.cm.viridis
for ax, (key, title) in zip(axes, (("branca", "A. White"), ("parda", "B. Brown"), ("preta", "C. Black")), strict=True):
    for n_, c0 in enumerate(cohorts):
        pts = [(y, coh[(c0, y)][key]) for y in (2000, 2010, 2022) if (c0, y) in coh]
        colr = cmap(n_ / (len(cohorts) - 1))
        ax.plot([p[0] for p in pts], [100 * p[1] for p in pts], "-o", ms=2.5, lw=1, color=colr)
        if c0 in cb_:
            ax.plot([1997], [100 * cb_[c0][key]], "D", ms=4, mfc="white", mec=colr)
    ax.set_title(title, fontsize=8, loc="left")
    ax.set_xticks([1997, 2000, 2010, 2022], ["birth\nrecord", "2000", "2010", "2022"], fontsize=6.5)
    ax.plot([], [], "D", ms=4, mfc="white", mec="#555555", ls="", label="birth record (born 2000-2009)")
    ax.legend(fontsize=6, frameon=False, loc="best")
axes[0].set_ylabel("Share of the birth cohort (%)")
sm = plt.cm.ScalarMappable(norm=matplotlib.colors.Normalize(vmin=cohorts[0], vmax=cohorts[-1]), cmap=cmap)
cb = fig.colorbar(sm, ax=axes, fraction=0.025, pad=0.02)
cb.set_label("Birth cohort (first year)", fontsize=7)
save(fig, "cohorts")
print("figures written")
runpy.run_path(str(HERE / "figures_space.py"), run_name="__main__")
