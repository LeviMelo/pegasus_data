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
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6), sharey=True)
for ax, m in zip(axes, ("white", "brown", "black"), strict=True):
    for i, c in enumerate(("white", "brown", "black")):
        for k, y in enumerate(("2010", "2022")):
            eb(ax, i + (k - 0.5) * 0.25, F["matrix"][y][f"{m}|0-4"][c], YC[y], label=y if (i == 0 and m == "white") else None)
    ax.set_xticks(range(3), ["White", "Brown", "Black"])
    ax.set_xlabel("child reported")
    ax.set_title(f"{'ABC'[['white', 'brown', 'black'].index(m)]}. {EN[m]} mother", fontsize=8, loc="left")
    ax.set_ylim(0, 1)
axes[0].set_ylabel("Proportion of children aged 0-4")
axes[0].legend(frameon=False, fontsize=7, loc="upper right")
fig.tight_layout()
save(fig, "family_matrix")

# ---------------------------------------------------------------- 2. by the partner's race
fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8))
for ax, (m, outc, title) in zip(axes, (("brown", "is_white", "A. Brown mother: child reported White"),
                                       ("black", "is_black", "B. Black mother: child reported Black")), strict=True):
    parts = ["white", "brown", "black", "other", "no partner"]
    for i, p in enumerate(parts):
        for k, y in enumerate(("2010", "2022")):
            v = F["by"][y].get(f"{m}|{outc}|partner|{p}")
            if v:
                eb(ax, i + (k - 0.5) * 0.25, v, YC[y], label=y if i == 0 else None)
    ax.set_xticks(range(len(parts)), [EN[p].replace(" or ", "/\n").replace("no partner identified", "no partner\nidentified") for p in parts], fontsize=7)
    ax.set_xlabel("partner of the mother")
    ax.set_ylim(0, 1)
    ax.set_title(title, fontsize=8, loc="left")
axes[0].set_ylabel("Proportion of children aged 0-9")
axes[0].legend(frameon=False, fontsize=7)
fig.tight_layout()
save(fig, "family_partner")

# ---------------------------------------------------------------- 3. by the child's age, and who still lives with the mother
AGES = ["0-4", "5-9", "10-14", "15-19", "20-24"]
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
for ax, (m, outc, title) in zip(axes[:2], (("brown", "is_white", "A. Brown mother:\nchild reported White"),
                                           ("black", "is_black", "B. Black mother:\nchild reported Black")), strict=True):
    for y in ("2010", "2022"):
        vs = [F["by"][y][f"{m}|{outc}|age|{a}"] for a in AGES]
        ax.errorbar(range(5), [v["est"] for v in vs], yerr=[1.96 * v["se"] for v in vs], fmt="-o", color=YC[y], ms=3.5, capsize=1.5, label=y)
    ax.set_xticks(range(5), AGES)
    ax.set_xlabel("age of the child")
    ax.set_ylim(0, 0.8)
    ax.set_title(title, fontsize=8, loc="left")
axes[0].set_ylabel("Proportion")
axes[0].legend(frameon=False, fontsize=7)
ax = axes[2]
for y in ("2010", "2022"):
    for r, ls in (("brown", "-"), ("black", "--")):
        ax.plot(range(5), [F["coresidence"][f"{y}|{a}|{r}"]["with_mother"] for a in AGES], ls, color=YC[y], marker="o", ms=3, label=f"{y}, {EN[r]}")
ax.set_xticks(range(5), AGES)
ax.set_xlabel("age")
ax.set_ylim(0, 1)
ax.set_title("C. Living with the mother", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=6)
fig.tight_layout()
save(fig, "family_age")

# ---------------------------------------------------------------- 4. birth cohorts across three censuses (universe and sample tables)
fig, ax = plt.subplots(figsize=(7.2, 2.8))
co = R["cohorts"]
cohorts = sorted({c["cohort"] for c in co})
for y, mk in ((2000, "s"), (2010, "o"), (2022, "^")):
    pts = [(c["cohort"], c["branca"]) for c in co if c["year"] == y]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], mk + "-", color={2000: "#56B4E9", 2010: "#999999", 2022: "#D55E00"}[y], ms=3.5, label=f"Census {y}")
ax.set_xlabel("five-year birth cohort (first year)")
ax.set_ylabel("Share reported White")
ax.legend(frameon=False, fontsize=7)
ax.set_xticks(cohorts[::2])
fig.tight_layout()
save(fig, "family_cohorts")

# ---------------------------------------------------------------- 5. who answered for the child (2022)
fig, ax = plt.subplots(figsize=(7.2, 2.6))
WHO = ["mother", "other resident", "non-resident"]
for i, (m, outc, lab) in enumerate((("white", "same", "White mother: child White"), ("brown", "same", "Brown mother: child Brown"),
                                    ("black", "same", "Black mother: child Black"))):
    for k, w in enumerate(WHO):
        v = F["informant"].get(f"{m}|{outc}|0-4|{w}")
        if v:
            eb(ax, i + (k - 1) * 0.22, v, ["#009E73", "#CC79A7", "#56B4E9"][k], label=w if i == 0 else None)
ax.set_xticks(range(3), ["White mother:\nchild White", "Brown mother:\nchild Brown", "Black mother:\nchild Black"])
ax.set_ylabel("Proportion, children aged 0-4, 2022")
ax.set_ylim(0, 1)
ax.legend(frameon=False, fontsize=7, title="who answered for the child", title_fontsize=7)
fig.tight_layout()
save(fig, "family_informant")
print("family figures written")
