"""The decomposition figure of paper 2 (indicators/), from results/indicators2.json, into figures/.

    python papers/race_at_death/figures_indicators.py
"""
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).parent
O = json.loads((HERE / "results" / "indicators2.json").read_text(encoding="utf-8"))
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})
CELLS = [("mother_over_mother", "deaths and births\nby the mother's race", "#0072B2"), ("certified_over_mother", "certified deaths over\nthe mother's births", "#D55E00"),
         ("certified_over_child", "certified deaths over\nthe child's births", "#009E73"), ("mother_over_child", "the mother's deaths over\nthe child's births", "#999999")]
fig = plt.figure(figsize=(6.9, 3.2))
axes = [fig.add_axes(r) for r in ((0.08, 0.25, 0.2, 0.65), (0.5, 0.25, 0.24, 0.65), (0.83, 0.25, 0.16, 0.65))]
ax = axes[0]
for i, r in enumerate(("white", "black")):
    for j, (k, lab, col) in enumerate(CELLS):
        v = O["national"][k][r]
        lo, hi = v["est"] * math.exp(-1.96 * v["se"] / v["est"]), v["est"] * math.exp(1.96 * v["se"] / v["est"])
        ax.errorbar(i + (j - 1.5) * 0.17, v["est"], yerr=[[v["est"] - lo], [hi - v["est"]]], fmt="o", color=col, ms=4, capsize=1.5, label=lab if i == 0 else None)
ax.axhline(1, color="#999999", lw=0.7)
ax.set_yscale("log")
ax.set_yticks([0.25, 0.5, 1, 2, 4], ["0.25", "0.5", "1", "2", "4"])
ax.set_xticks([0, 1], ["White to\nBrown", "Black to\nBrown"])
ax.set_ylabel("Infant mortality rate ratio")
ax.set_title("A. Four ways to classify", fontsize=8, loc="left")
fig.legend(*ax.get_legend_handles_labels(), fontsize=6.3, frameon=False, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.06))
ax = axes[1]
SHP = O["shapley"]
PL = ["Brown mothers' infants certified White", "White mothers' infants certified Brown", "Black mothers' infants certified Brown",
      "Brown mothers' infants certified Black", "Indigenous mothers' infants certified Brown", "the other flows", "deaths with no race on the certificate"]
PLAB = ["Brown m., certified White", "White m., certified Brown", "Black m., certified Brown", "Brown m., certified Black", "Indig. m., certified Brown",
        "other flows", "no race on certificate"]
yy = np.arange(len(PL) + 1)[::-1]
for k_, (r, col, mk) in enumerate((("white", "#E69F00", "o"), ("black", "#000000", "s"))):
    vals = [SHP[r]["players"][q] for q in PL] + [{"est": SHP[r]["certified"] - SHP[r]["start"], "se": 0.0}]
    ax.errorbar([v["est"] for v in vals], yy + (0.5 - k_) * 0.3, xerr=[1.96 * v["se"] for v in vals], fmt=mk, color=col, ms=3.5, capsize=1.2,
                label=f"{r.capitalize()} to Brown")
ax.axvline(0, color="#999999", lw=0.7)
ax.axhline(0.5, color="#dddddd", lw=0.6)
ax.set_yticks(yy, PLAB + ["net change"], fontsize=6.5)
ax.set_xlabel("Contribution to the log rate ratio\n(averaged over all orders)", fontsize=7)
ax.set_title("B. What each flow contributes", fontsize=8, loc="left")
ax.legend(fontsize=6.5, frameon=False, loc="upper left")
ax = axes[2]
yrs = sorted(O["by_year"], key=int)
YJ = O["by_year_jack"]
for j, (k, lab, col) in enumerate(CELLS[:3]):
    xs = [int(y) + (j - 1) * 0.15 for y in yrs]
    est = [YJ[y][k]["white"]["est"] for y in yrs]
    lo = [e * np.exp(-1.96 * YJ[y][k]["white"]["se"] / e) for e, y in zip(est, yrs, strict=True)]
    hi = [e * np.exp(1.96 * YJ[y][k]["white"]["se"] / e) for e, y in zip(est, yrs, strict=True)]
    ax.errorbar(xs, est, yerr=[np.subtract(est, lo), np.subtract(hi, est)], fmt="-o", color=col, ms=2.2, lw=0.9, capsize=0.8, elinewidth=0.6)
ax.axhline(1, color="#999999", lw=0.7)
ax.set_xticks([2013, 2018, 2023])
ax.set_ylabel("White to Brown")
ax.set_title("C. By year", fontsize=8, loc="left")
for ext in ("png", "pdf", "svg"):
    fig.savefig(HERE / "figures" / f"indicators_decomposition.{ext}", dpi=300, bbox_inches="tight")
print("indicators figure written")
