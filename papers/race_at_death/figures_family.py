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
fig, axes = plt.subplots(1, 4, figsize=(6.9, 2.5), sharey=True, gridspec_kw={"width_ratios": [1, 1, 1, 1.05]})
for ax, m in zip(axes[:3], ("white", "brown", "black"), strict=True):
    for i, c in enumerate(("white", "brown", "black")):
        for k, y in enumerate(("2010", "2022")):
            eb(ax, i + (k - 0.5) * 0.25, F["matrix"][y][f"{m}|0-4"][c], YC[y], label=y if (i == 0 and m == "white") else None)
    ax.set_xticks(range(3), ["White", "Brown", "Black"])
    ax.set_xlabel("child reported")
    ax.set_title(f"{'ABC'[['white', 'brown', 'black'].index(m)]}. {EN[m]} mother", fontsize=8, loc="left")
    ax.set_ylim(0, 1)
DRF = F["review1"]["drift"]
ax = axes[3]
CELLS3 = (("brown|is_white", "Brown:\nWhite"), ("black|is_black", "Black:\nBlack"), ("black|is_white", "Black:\nWhite"))
for i, (key, _) in enumerate(CELLS3):
    ax.plot([i - 0.2], [DRF[key]["2010"]], "o", color=YC["2010"], ms=4)
    ax.plot([i], [DRF[key]["2022"]], "o", color=YC["2022"], ms=4)
    ax.plot([i + 0.2], [DRF[key]["2022_at_2010_mothers"]], "o", mfc="white", mec=YC["2022"], ms=4,
            label="2022 at the 2010\nmothers' schooling\nand region" if i == 0 else None)
ax.set_xticks(range(3), [lab for _, lab in CELLS3], fontsize=5.6)
ax.set_xlabel("mother: child, ages 0-9")
ax.set_title("D. Standardised", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=5.6, loc="upper right")
axes[0].set_ylabel("Proportion of children aged 0-4")
axes[0].legend(frameon=False, fontsize=7, loc="upper right")
fig.tight_layout()
save(fig, "family_matrix")

# ---------------------------------------------------------------- 2. by the partner's race: father or stepfather, and siblings
V2 = F["review1"]
RELS = [("child of both (father)", "father", "o"), ("child of the mother only (stepfather)", "mother's child\n(stepfather)", "s"),
        ("stepchild of the responsible man (stepfather)", "his stepchild\n(stepfather)", "^")]
fig = plt.figure(figsize=(6.9, 2.9))
BOX = [(0.07, 0.22, 0.25, 0.66), (0.385, 0.22, 0.25, 0.66), (0.80, 0.22, 0.19, 0.66)]
for j, (m, outc, title) in enumerate((("brown", "is_white", "A. Brown mother:\nchild reported White"), ("black", "is_black", "B. Black mother:\nchild reported Black"))):
    ax = fig.add_axes(BOX[j])
    parts = ["white", "brown", "black"]
    for i, p in enumerate(parts):
        for r, (rel, rl, mk) in enumerate(RELS):
            for k, y in enumerate(("2010", "2022")):
                v = V2.get(f"{y}|{m}|{outc}|{rel}|{p}")
                if v:
                    eb(ax, i + (r - 1) * 0.26 + (k - 0.5) * 0.1, v, YC[y], mk=mk, label=(f"{y}" if (r == 0 and i == 0) else None))
    ax.set_xticks(range(3), [EN[p] for p in parts], fontsize=6.8)
    ax.set_xlabel("partner of the mother", fontsize=7)
    ax.set_ylim(0, 1)
    ax.tick_params(labelsize=6.5)
    ax.set_title(title, fontsize=7.5, loc="left")
    if j == 0:
        ax.set_ylabel("Proportion of children aged 0-9", fontsize=7)
        h = [plt.Line2D([], [], color="#555555", marker=mk, ls="", ms=3.5, label=rl.replace("\n", " ")) for _, rl, mk in RELS]
        h += [plt.Line2D([], [], color=YC[y], marker="o", ls="", ms=3.5, label=y) for y in ("2010", "2022")]
        ax.legend(handles=h, frameon=False, fontsize=5.6, loc="upper right")
ax = fig.add_axes(BOX[2])
SIB = V2["siblings"]
pairs = [("white", "white"), ("brown", "brown"), ("black", "black"), ("brown", "white"), ("white", "brown"), ("black", "white"), ("black", "brown"), ("brown", "no partner")]
yy = list(range(len(pairs)))[::-1]
for yi, (m, p) in zip(yy, pairs, strict=True):
    for k, y in enumerate(("2010", "2022")):
        s_ = SIB.get(f"{y}|{m}|{p}")
        if s_:
            ax.plot(s_["discordant"], yi + (0.5 - k) * 0.3, "o", color=YC[y], ms=3.5)
ax.set_yticks(yy, [f"{EN[m]} mother, {EN[p] if p != 'no partner' else 'no partner'}" for m, p in pairs], fontsize=6)
ax.set_xlim(0, 0.5)
ax.tick_params(axis="x", labelsize=6.5)
ax.set_xlabel("Households whose children 0-9\nare reported in different races", fontsize=6.5)
ax.set_title("C. Siblings", fontsize=7.5, loc="left")
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
ax.legend(frameon=False, fontsize=5.6)
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

# ---------------------------------------------------------------- 4. who answered for the child, within the couple (2022)
IN2 = V2["informant"]
WHO = [("mother", "#009E73"), ("partner", "#D55E00"), ("other resident", "#CC79A7"), ("non-resident", "#56B4E9")]
CELLS = [("brown", "white", "white", "Brown mother,\nWhite partner:\nchild White"), ("black", "white", "white", "Black mother,\nWhite partner:\nchild White"),
         ("brown", "brown", "white", "Brown mother,\nBrown partner:\nchild White"), ("black", "black", "black", "Black mother,\nBlack partner:\nchild Black"),
         ("black", "brown", "black", "Black mother,\nBrown partner:\nchild Black"), ("brown", "no partner", "white", "Brown mother,\nno partner:\nchild White")]
fig, ax = plt.subplots(figsize=(6.9, 2.7))
for i, (m, p, c, _) in enumerate(CELLS):
    for k, (w, col) in enumerate(WHO):
        v = IN2.get(f"{m}|{p}|{w}")
        if v:
            eb(ax, i + (k - 1.5) * 0.17, v[c], col, label=w if i == 0 else None)
ax.set_xticks(range(len(CELLS)), [c[3] for c in CELLS], fontsize=6.3)
ax.set_ylabel("Proportion, children aged 0-9, 2022", fontsize=7)
ax.set_ylim(0, 1)
ax.tick_params(axis="y", labelsize=6.5)
ax.legend(frameon=False, fontsize=6, title="who answered for the child", title_fontsize=6, loc="upper right", ncol=2)
save(fig, "family_informant")
print("family figures written")
