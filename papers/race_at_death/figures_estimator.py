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
SCEN_COL = {"ideal": "#000000", "twins": "#999999", "sparse": "#56B4E9", "a2": "#CC79A7", "movers": "#0072B2", "unequal": "#E69F00", "selective": "#D55E00",
            "overdisp": "#117733", "keyerr": "#882255", "keyerr_k": "#AA4499", "pooled12": "#44AA99", "munfx": "#999933", "application": "#CC6677"}


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

# ---------------------------------------------------------------- Figure 2: every cell against the known answer, on exactly the linked units
LI, LP = E["like_infants"]["groups"], E["like_pair"]["groups"]
panels = [("A  Infant deaths, linked units", [(k, LI[k]["full"]) for k in LI if k not in ("all", "<25,600") and LI[k]["full"]]),
          ("B  Admissions, linked units", [(k, LP[k]["full"]) for k in LP if k != "all" and LP[k]["full"]])]
fig, axes = plt.subplots(2, 2, figsize=(6.9, 5.6), gridspec_kw={"hspace": 0.45, "wspace": 0.3})
axes = axes.ravel()
zs = {}
for ax, (title, blocks) in zip(axes[:2], panels, strict=True):
    for (label, f), col in zip(blocks, SIZE_COL, strict=True):
        p, se = np.array(f["p"]), np.array(f["p_se_exact"])
        zz = []
        for j, known in enumerate(f["truth"]):
            if known is None:
                continue
            ok = np.isfinite(se[j]) & (se[j] < 0.15)
            kn = np.array(known)
            ax.errorbar(kn[ok], (p[j] - kn)[ok], yerr=1.96 * se[j][ok], fmt="o", ms=2.6, lw=0.6, color=col, label=label if j == 0 else None)
            zz += list(((p[j] - kn) / np.where(se[j] > 0, se[j], np.nan))[np.isfinite(se[j]) & (se[j] > 0)])
        zs.setdefault(title[0], []).append(zz)
    ax.axhline(0, color="#777777", lw=0.7, zorder=0)
    ax.set_title(title, fontsize=7.2, loc="left")
    ax.set_xlabel("known answer (proportion)")
    ax.set_xlim(-0.02, 1)
    ax.set_ylim(-0.25, 0.25)
    ax.legend(title="births a year" if title[0] == "A" else "certificates a year", fontsize=5.5, title_fontsize=5.5, frameon=False, loc="upper left", ncol=2)
axes[0].set_ylabel("estimate less known answer")
ax = axes[2]
for off, (tag, name, mk) in zip((-0.17, 0.17), (("A", "infants", "o"), ("B", "admissions", "s")), strict=True):
    for i, zz in enumerate(zs[tag]):
        ax.plot(np.full(len(zz), i + off) + np.linspace(-0.08, 0.08, max(len(zz), 1))[: len(zz)], np.clip(zz, -5.9, 5.9), mk, ms=2.2, color=SIZE_COL[i], mfc="none" if tag == "B" else SIZE_COL[i])
ax.plot([], [], "o", ms=2.6, color="#444444", label="infants")
ax.plot([], [], "s", ms=2.6, color="#444444", mfc="none", label="admissions")
ax.axhline(0, color="#777777", lw=0.7)
for yv in (-1.96, 1.96):
    ax.axhline(yv, color="#777777", lw=0.6, ls="--")
ax.set_ylim(-6, 6)
ax.set_xticks(range(5), ["smallest", "", "", "", "largest"], fontsize=6.5)
ax.set_xlabel("municipality size class")
ax.set_ylabel("z = difference / model SE")
ax.set_title("C  Calibration of the interval", fontsize=7.2, loc="left")
ax.legend(fontsize=6, frameon=False, loc="upper left")
# D: the working limit is the expected number of chance candidates per unit, not the municipality's size (review 2026-11-22, 6.3)
ax = axes[3]
BA = E.get("like_pair_by_age", {})
series = [("infants, by size", "o", "#0072B2", [(LI[k]["variants"]["linked"]["chance_per_unit"], LI[k]["variants"]["linked"]["against_findable"]["mean_abs_diff"])
                                                for k in LI if k not in ("all", "<25,600") and "linked" in LI[k]["variants"]]),
          ("admissions, by size", "s", "#D55E00", [(LP[k]["variants"]["linked"]["chance_per_unit"], LP[k]["variants"]["linked"]["against_findable"]["mean_abs_diff"])
                                                   for k in LP if k != "all" and "linked" in LP[k]["variants"]]),
          ("admissions, by age", "^", "#009E73", [(v["groups"]["all"]["linked"]["chance_per_unit"], v["groups"]["all"]["linked"]["against_findable"]["mean_abs_diff"])
                                                  for v in BA.values()])]
for lab, mk, col, pts in series:
    if pts:
        x_, y_ = zip(*sorted(pts), strict=True)
        ax.plot(x_, y_, mk + "-", color=col, ms=3.5, lw=0.8, label=lab)
ax.set_xscale("log")
ax.set_xlabel("chance candidates per unit (control, scaled)")
ax.set_ylabel("mean |estimate - target| over cells")
ax.set_title("D  Accuracy against chance agreement", fontsize=7.2, loc="left")
ax.legend(fontsize=6, frameon=False, loc="upper left")
save(fig, "estimator_validation")

# ---------------------------------------------------------------- Figure 3: the simulation, by municipality size and scenario
sizes = ["<400", "400-1,599", "1,600-6,399", "6,400-25,599"]
quant = [("p_white_white", "White recorded White"), ("p_black_black", "Black recorded Black"), ("p_brown_brown", "Brown recorded Brown"),
         ("p_indigenous_indigenous", "Indigenous recorded Indigenous"), ("ratio_white", "White to Brown rate ratio")]
scen = {k: c for k, c in SCEN_COL.items() if k in S["results"]}
fig, axes = plt.subplots(3, 5, figsize=(7.6, 5.4), sharex=True)
x = np.arange(len(sizes))
n_rep = S["replicates"]
band = 1.96 * np.sqrt(0.95 * 0.05 / n_rep)
for c, (q, name) in enumerate(quant):
    for k, (sc, col) in enumerate(scen.items()):
        rows = [S["results"][sc][s][q] for s in sizes]
        off = (k - len(scen) / 2) * 0.07
        axes[0, c].errorbar(x + off, [r["bias"] for r in rows], yerr=[1.96 * r["mcse_bias"] for r in rows], fmt="o", ms=2.4, lw=0.6, color=col, label=sc)
        axes[1, c].plot(x + off, [r["bias"] / r["mcse_bias"] for r in rows], "o", ms=2.4, color=col)
        axes[2, c].plot(x + off, [r["cover_super_model"] if q.startswith("p_") else r["cover_model"] for r in rows], "o", ms=2.4, color=col)
    axes[0, c].axhline(0, color="#777777", lw=0.6)
    axes[1, c].axhline(0, color="#777777", lw=0.6)
    for yv in (-1.96, 1.96):
        axes[1, c].axhline(yv, color="#777777", lw=0.5, ls="--")
    axes[1, c].set_ylim(-8, 8)
    axes[2, c].axhline(0.95, color="#777777", lw=0.6)
    axes[2, c].axhspan(0.95 - band, 0.95 + band, color="#bbbbbb", alpha=0.5, lw=0)
    axes[0, c].set_title(name, fontsize=6.4)
    axes[2, c].set_ylim(0.5, 1.02)
    axes[2, c].set_xticks(x, sizes, rotation=40, ha="right", fontsize=5.8)
axes[0, 0].set_ylabel("bias")
axes[1, 0].set_ylabel("bias / MC SE")
axes[2, 0].set_ylabel("coverage")
fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="lower center", ncol=min(len(scen), 7), fontsize=6.2, frameon=False, bbox_to_anchor=(0.5, -0.03))
fig.supxlabel("births a year in the municipality", fontsize=7.5, y=0.045)
fig.tight_layout()
save(fig, "estimator_simulation")
print("figures written")
