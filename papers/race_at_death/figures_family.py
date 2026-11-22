"""The figures of paper 4 (family/), from results/family.json and the cohort series of results/results.json, into figures/.

    python papers/race_at_death/figures_family.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).parent
OUT, RES = HERE / "figures", HERE / "results"
F = json.loads((RES / "family.json").read_text(encoding="utf-8"))
R = json.loads((RES / "results.json").read_text(encoding="utf-8"))
COL = {"white": "#E69F00", "brown": "#0072B2", "black": "#000000"}
YC = {"2010": "#999999", "2022": "#D55E00"}
EN = {"white": "White", "brown": "Brown", "black": "Black", "indigenous": "Indigenous", "other": "Indigenous or Yellow", "no partner": "no partner identified"}
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})


def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def eb(ax, x, v, col, mk="o", label=None):
    ax.errorbar(x, v["est"], yerr=1.96 * v["se"], fmt=mk, color=col, ms=4, capsize=1.5, label=label)


# ---------------------------------------------------------------- 1. the household's classification by the mother's race, two censuses
V2, V3 = F["review1"], F["review2"]
fig = plt.figure(figsize=(6.9, 4.6))
gs = fig.add_gridspec(2, 3, height_ratios=[1, 0.8], hspace=0.6, wspace=0.15)
axes = [fig.add_subplot(gs[0, k]) for k in range(3)] + [fig.add_subplot(gs[1, :2])]
for ax, m in zip(axes[:3], ("white", "brown", "black"), strict=True):
    for i, c in enumerate(("white", "brown", "black")):
        for k, y in enumerate(("2010", "2022")):
            eb(ax, i + (k - 0.5) * 0.25, F["matrix"][y][f"{m}|0-4"][c], YC[y], label=y if (i == 0 and m == "white") else None)
    ax.set_xticks(range(3), ["White", "Brown", "Black"], fontsize=7)
    ax.set_xlabel("child reported", fontsize=7)
    ax.set_title(f"{'ABC'[['white', 'brown', 'black'].index(m)]}. {EN[m]} mother", fontsize=8, loc="left")
    ax.set_ylim(0, 1)
    ax.tick_params(labelsize=7)
    if m != "white":
        ax.set_yticklabels([])
axes[0].set_ylabel("Proportion of children aged 0-4", fontsize=7)
axes[0].legend(frameon=False, fontsize=7, loc="upper right")
DRF = V3["drift_boot"]
ax = axes[3]
CELLS3 = (("white|is_white", "White:\nWhite"), ("brown|is_white", "Brown:\nWhite"), ("black|is_black", "Black:\nBlack"), ("black|is_white", "Black:\nWhite"))
for i, (key, _) in enumerate(CELLS3):
    r = DRF[key]
    for dx, val, se, fc, col, lab in ((-0.22, r["change"], r["change_se"], YC["2022"], YC["2022"], "crude"),
                                     (0.22, r["std_change"], r["std_change_se"], "white", YC["2022"], "at the 2010 mothers'\nschooling and region")):
        ax.errorbar(i + dx, 100 * val, yerr=196 * se, fmt="o", mfc=fc, mec=col, color=col, ms=4, capsize=1.5, label=lab if i == 0 else None)
ax.axhline(0, color="#999999", lw=0.6)
ax.set_xticks(range(4), [lab.replace("\n", " ") for _, lab in CELLS3], fontsize=7)
ax.set_xlabel("mother: child, ages 0-9", fontsize=7)
ax.set_ylabel("Percentage points", fontsize=7)
ax.tick_params(labelsize=7)
ax.set_title("D. Change 2010-2022, crude and standardised", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=7, loc="center left", bbox_to_anchor=(1.02, 0.5))
save(fig, "family_matrix")

# ---------------------------------------------------------------- 2. the father and the mother, stepfathers, and siblings
RELS = [("child of both (father)", "father", "o"), ("child of the mother only (stepfather)", "mother's child (stepfather)", "s"),
        ("stepchild of the responsible man (stepfather)", "his stepchild (stepfather)", "^")]
fig = plt.figure(figsize=(6.9, 5.6))
BOX = [(0.08, 0.58, 0.38, 0.35), (0.58, 0.58, 0.38, 0.35), (0.22, 0.07, 0.24, 0.38), (0.72, 0.07, 0.24, 0.38)]
for j, (m, outc, title) in enumerate((("brown", "is_white", "A. Brown mother: child reported White"), ("black", "is_black", "B. Black mother: child reported Black"))):
    ax = fig.add_axes(BOX[j])
    parts = ["white", "brown", "black"]
    for i, p in enumerate(parts):
        for r, (rel, rl, mk) in enumerate(RELS):
            for k, y in enumerate(("2010", "2022")):
                v = V2.get(f"{y}|{m}|{outc}|{rel}|{p}")
                if v:
                    eb(ax, i + (r - 1) * 0.26 + (k - 0.5) * 0.1, v, YC[y], mk=mk)
    ax.set_xticks(range(3), [f"{EN[p]} partner" for p in parts], fontsize=7)
    ax.set_ylim(0, 1)
    ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=8, loc="left")
    ax.set_ylabel("Proportion of children aged 0-9", fontsize=7)
    if j == 0:
        h = [plt.Line2D([], [], color="#555555", marker=mk, ls="", ms=3.5, label=rl) for _, rl, mk in RELS]
        h += [plt.Line2D([], [], color=YC[y], marker="o", ls="", ms=3.5, label=y) for y in ("2010", "2022")]
        ax.legend(handles=h, frameon=False, fontsize=7, loc="upper right")
# C: both parents' races, children of both (fathers): the child reported White
ax = fig.add_axes(BOX[2])
PAR = V3["parents"]
pp = [("white", "white"), ("white", "brown"), ("brown", "white"), ("white", "black"), ("black", "white"), ("brown", "brown"), ("brown", "black"),
      ("black", "brown"), ("black", "black")]
yy = list(range(len(pp)))[::-1]
for yi, (m, p) in zip(yy, pp, strict=True):
    for k, y in enumerate(("2010", "2022")):
        v = PAR[f"{y}|{m}|{p}"]["white"]
        ax.errorbar(v["est"], yi + (0.5 - k) * 0.3, xerr=1.96 * v["se"], fmt="o", color=YC[y], ms=3.2, capsize=1)
ax.set_yticks(yy, [f"{EN[m]} mother, {EN[p]} father" for m, p in pp], fontsize=7)
ax.set_xlim(0, 1)
ax.tick_params(axis="x", labelsize=7)
ax.set_xlabel("Child reported White (children of both)", fontsize=7)
ax.set_title("C. Mother and father", fontsize=8, loc="left")
# D: full siblings, observed against independent classification
ax = fig.add_axes(BOX[3])
FS = V3["full_siblings"]
sp = [("white", "white"), ("brown", "brown"), ("black", "black"), ("brown", "white"), ("white", "brown"), ("black", "white"), ("white", "black"),
      ("black", "brown"), ("brown", "black")]
yy = list(range(len(sp)))[::-1]
for yi, (m, p) in zip(yy, sp, strict=True):
    for k, y in enumerate(("2010", "2022")):
        s_ = FS.get(f"{y}|{m}|{p}")
        if s_:
            o = s_["observed"]
            ax.errorbar(o["est"], yi + (0.5 - k) * 0.3, xerr=1.96 * o["se"], fmt="o", color=YC[y], ms=3.2, capsize=1)
            ax.plot(s_["independent"], yi + (0.5 - k) * 0.3, "|", color=YC[y], ms=7, mew=1.2)
ax.set_yticks(yy, [f"{EN[m]} mother, {EN[p]} father" for m, p in sp], fontsize=7)
ax.set_xlim(0, 0.75)
ax.tick_params(axis="x", labelsize=7)
ax.set_xlabel("Households with full siblings 0-9 in\ndifferent races (|: if independent)", fontsize=7)
ax.set_title("D. Full siblings", fontsize=8, loc="left")
save(fig, "family_partner")

# ---------------------------------------------------------------- 3. age, co-residence and birth cohorts
AGES = ["0-4", "5-9", "10-14", "15-19", "20-24"]
fig = plt.figure(figsize=(6.9, 5.2))
gs = fig.add_gridspec(2, 3, height_ratios=[1, 0.95], hspace=0.55, wspace=0.4)
for j, (m, outc, title) in enumerate((("brown", "is_white", "A. Brown mother:\nchild reported White"), ("black", "is_black", "B. Black mother:\nchild reported Black"))):
    ax = fig.add_subplot(gs[0, j])
    for y in ("2010", "2022"):
        vs = [F["by"][y][f"{m}|{outc}|age|{a}"] for a in AGES]
        ax.errorbar(range(5), [v["est"] for v in vs], yerr=[1.96 * v["se"] for v in vs], fmt="-o", color=YC[y], ms=3, capsize=1.2, label=y)
    ax.set_xticks(range(5), AGES, fontsize=6.5)
    ax.set_xlabel("age of the child", fontsize=7)
    ax.set_ylim(0, 0.8)
    ax.tick_params(labelsize=6.5)
    ax.set_title(title, fontsize=7.5, loc="left")
    if j == 0:
        ax.set_ylabel("Proportion", fontsize=7)
        ax.legend(frameon=False, fontsize=6)
ax = fig.add_subplot(gs[0, 2])
for y in ("2010", "2022"):
    for r, ls in (("brown", "-"), ("black", "--")):
        ax.plot(range(5), [F["coresidence"][f"{y}|{a}|{r}"]["child_of_couple"] for a in AGES], ls, color=YC[y], marker="o", ms=2.5, label=f"{y}, {EN[r]}")
ax.set_xticks(range(5), AGES, fontsize=6.5)
ax.set_xlabel("age", fontsize=7)
ax.set_ylim(0, 1)
ax.tick_params(labelsize=6.5)
ax.set_title("C. In the pairs: child of the\ncouple, with the mother", fontsize=7.5, loc="left")
ax.legend(frameon=False, fontsize=7)
ax = fig.add_subplot(gs[1, :])
co = [c for c in R["cohorts"] if not (c["cohort"] == 2000 and c["year"] == 2000)]
cohorts = sorted({c["cohort"] for c in co})
for y, mk in ((2000, "s"), (2010, "o"), (2022, "^")):
    pts = sorted((c["cohort"], c["branca"]) for c in co if c["year"] == y)
    ax.plot([p[0] for p in pts], [p[1] for p in pts], mk + "-", color={2000: "#56B4E9", 2010: "#999999", 2022: "#D55E00"}[y], ms=3, label=f"Census {y}")
ax.set_xlabel("five-year birth cohort (first year)", fontsize=7)
ax.set_ylabel("Share reported White", fontsize=7)
ax.tick_params(labelsize=6.5)
ax.legend(frameon=False, fontsize=6)
ax.set_xticks(cohorts[::2])
ax.set_title("D. Birth cohorts at three censuses, whole population", fontsize=7.5, loc="left")
save(fig, "family_age")

# ---------------------------------------------------------------- 4. who answered for the child and for the mother (2022)
IC = V3["informant_cross"]
WHO = [("child by mother|mother by mother", "mother for both", "#009E73", "o"), ("child by partner|mother by mother", "partner for the child,\nmother for herself", "#CC79A7", "s"),
       ("child by partner|mother by partner", "partner for both", "#56B4E9", "D")]
CELLS = [("brown", "white", "white", "Brown mother,\nWhite partner:\nchild White"), ("black", "white", "white", "Black mother,\nWhite partner:\nchild White"),
         ("white", "brown", "white", "White mother,\nBrown partner:\nchild White"), ("white", "black", "white", "White mother,\nBlack partner:\nchild White"),
         ("black", "brown", "black", "Black mother,\nBrown partner:\nchild Black"), ("black", "black", "black", "Black mother,\nBlack partner:\nchild Black"),
         ("brown", "black", "black", "Brown mother,\nBlack partner:\nchild Black")]
fig, ax = plt.subplots(figsize=(6.9, 2.9))
for i, (m, p, c, _) in enumerate(CELLS):
    for k, (w, lab, col, mk) in enumerate(WHO):
        v = IC.get(f"{m}|{p}|{w}")
        if v:
            eb(ax, i + (k - 1) * 0.22, v[c], col, mk=mk, label=lab if i == 0 else None)
ax.set_xticks(range(len(CELLS)), [c[3] for c in CELLS], fontsize=6.6)
ax.set_ylabel("Proportion, children aged 0-9, 2022", fontsize=7)
ax.set_ylim(0, 1)
ax.tick_params(axis="y", labelsize=7)
ax.legend(frameon=False, fontsize=7, title="who answered", title_fontsize=7, loc="upper right", ncol=3)
save(fig, "family_informant")
print("family figures written")
