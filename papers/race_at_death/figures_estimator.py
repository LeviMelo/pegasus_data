"""The figures of paper 6 (the estimator), from results/estimator.json and results/simulation.json, into figures/ as PNG, PDF
and SVG (estimator_design, estimator_validation, estimator_simulation).

    python papers/race_at_death/figures_estimator.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "figures"
E = json.loads((HERE / "results" / "estimator.json").read_text(encoding="utf-8"))
S = json.loads((HERE / "results" / "simulation.json").read_text(encoding="utf-8"))
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})
SIZE_COL = ["#56B4E9", "#0072B2", "#009E73", "#E69F00", "#D55E00"]          # Okabe-Ito, smallest to largest municipalities
SCEN_COL = {"ideal": "#000000", "twins": "#999999", "sparse": "#56B4E9", "a2": "#CC79A7", "movers": "#0072B2", "unequal": "#E69F00", "selective": "#D55E00"}


def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- Figure 1: one death, its candidates and its control
fig, ax = plt.subplots(figsize=(7.6, 3.0))
ax.set_xlim(-0.1, 10.6)
ax.set_ylim(0, 4.2)
ax.axis("off")


def box(x, y, w, h, title, body, col):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04", fc="white", ec=col, lw=1.4))
    ax.text(x + w / 2, y + h - 0.2, title, ha="center", va="top", fontsize=8, weight="bold", color=col)
    ax.text(x + w / 2, y + h - 0.55, body, ha="center", va="top", fontsize=6.4, linespacing=1.3)


box(0.1, 1.3, 2.4, 1.6, "A death (public file)", "boy, born 12 March 2015,\nresident in municipality m;\ncertified race k", "#000000")
box(3.2, 2.35, 3.3, 1.75, "Candidates", "boys born 12 March 2015 in m\n(birth records, declared race j):\nthe deceased, if he did not move,\nand others by chance", "#0072B2")
box(3.2, 0.1, 3.3, 1.75, "Control", "girls born 12 March 2015 in m,\nscaled by boys over girls born in m:\nthe same day, so as many chance\nagreements, and never the deceased", "#D55E00")
box(7.3, 1.25, 3.2, 1.7, "Candidates less control", "summed over the deaths of a group:\nt x deaths by (j, k), t the share\nfound; rows give P(k | j),\nrow sums the declared mix", "#009E73")
for y0, y1 in ((2.1, 3.2), (2.1, 1.0)):
    ax.annotate("", xy=(3.2, y1), xytext=(2.5, y0), arrowprops={"arrowstyle": "->", "lw": 1})
for y0 in (3.2, 1.0):
    ax.annotate("", xy=(7.3, 2.1), xytext=(6.5, y0), arrowprops={"arrowstyle": "->", "lw": 1})
ax.text(6.9, 2.95, "+", fontsize=12, ha="center", color="#0072B2")
ax.text(6.9, 1.05, "-", fontsize=14, ha="center", color="#D55E00")
save(fig, "estimator_design")

# ---------------------------------------------------------------- Figure 2: every cell against the known answer
panels = [("A  Infant deaths vs linkage", [(b["size"], b["full"]) for b in E["infants"] if b["size"] not in ("all", "<25,600")]),
          ("B  Admissions vs linked certificates", [(b["size"], b["mun"]["full_linked"]) for b in E["pair"]["by_size"] if b["size"] != "all"]),
          ("C  ... vs those sharing the key", [(b["size"], b["mun"]["full_findable"]) for b in E["pair"]["by_size"] if b["size"] != "all"])]
fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.9), sharex=True, sharey=True)
for ax, (title, blocks) in zip(axes, panels, strict=True):
    for (label, f), col in zip(blocks, SIZE_COL, strict=True):
        p, se = np.array(f["p"]), np.array(f["p_se_model"])
        for j, known in enumerate(f["truth"]):
            if known is None:
                continue
            ok = se[j] < 0.15
            ax.errorbar(np.array(known)[ok], p[j][ok], yerr=1.96 * se[j][ok], fmt="o", ms=2.6, lw=0.6, color=col, label=label if j == 0 else None)
    ax.plot([0, 1], [0, 1], color="#777777", lw=0.7, zorder=0)
    ax.set_title(title, fontsize=7.2, loc="left")
    ax.set_xlabel("known answer (proportion)")
    ax.set_xlim(-0.02, 1)
    ax.set_ylim(-0.1, 1.05)
    ax.legend(title="births a year" if ax is axes[0] else "certificates a year", fontsize=6, title_fontsize=6, frameon=False, loc="upper left")
axes[0].set_ylabel("candidates less control (proportion)")
save(fig, "estimator_validation")

# ---------------------------------------------------------------- Figure 3: the simulation, by municipality size and scenario
sizes = ["<400", "400-1,599", "1,600-6,399", "6,400-25,599"]
quant = [("p_white_white", "White recorded White"), ("p_black_black", "Black recorded Black"), ("p_brown_brown", "Brown recorded Brown"),
         ("ratio_white", "White to Brown rate ratio")]
fig, axes = plt.subplots(2, 4, figsize=(7.4, 3.9), sharex=True)
x = np.arange(len(sizes))
for c, (q, name) in enumerate(quant):
    for k, (sc, col) in enumerate(SCEN_COL.items()):
        rows = [S["results"][sc][s][q] for s in sizes]
        off = (k - 3) * 0.08
        axes[0, c].errorbar(x + off, [r["bias"] for r in rows], yerr=[1.96 * r["mcse_bias"] for r in rows], fmt="o", ms=2.6, lw=0.6, color=col, label=sc)
        axes[1, c].plot(x + off, [r["cover_super_model"] if q.startswith("p_") else r["cover_model"] for r in rows], "o", ms=2.6, color=col)
    axes[0, c].axhline(0, color="#777777", lw=0.6)
    axes[1, c].axhline(0.95, color="#777777", lw=0.6)
    axes[0, c].set_title(name, fontsize=7.2)
    axes[1, c].set_ylim(-0.02, 1.02)
    axes[1, c].set_xticks(x, sizes, rotation=40, ha="right", fontsize=6.5)
axes[0, 0].set_ylabel("bias")
axes[1, 0].set_ylabel("coverage")
fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="lower center", ncol=7, fontsize=6.5, frameon=False, bbox_to_anchor=(0.5, -0.04))
fig.supxlabel("births a year in the municipality", fontsize=7.5, y=0.04)
fig.tight_layout()
save(fig, "estimator_simulation")
print("figures written")
