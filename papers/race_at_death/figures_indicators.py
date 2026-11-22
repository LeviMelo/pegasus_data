"""The decomposition figure of paper 2 (indicators/), from results/indicators2.json, into figures/.

    python papers/race_at_death/figures_indicators.py
"""
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).parent
O = json.loads((HERE / "results" / "indicators2.json").read_text(encoding="utf-8"))
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})
CELLS = [("mother_over_mother", "deaths and births\nby the mother's race", "#0072B2"), ("certified_over_mother", "certified deaths over\nthe mother's births", "#D55E00"),
         ("certified_over_child", "certified deaths over\nthe child's births", "#009E73"), ("mother_over_child", "the mother's deaths over\nthe child's births", "#999999")]
fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.0), gridspec_kw={"width_ratios": [1, 1.25, 1.1]})
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
fig.legend(*ax.get_legend_handles_labels(), fontsize=6.3, frameon=False, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.13))
ax = axes[1]
W = O["waterfall"]
labs = ["mother's race", "Brown to White", "White to Brown", "Black to Brown", "Brown to Black", "Indigenous to Brown", "certified,\nno race too",
        "over the child's\nbirths"]
for r, col, mk in (("white", "#E69F00", "o"), ("black", "#000000", "s")):
    ax.plot(range(len(W)), [w["ratios"][r] for w in W], "-" + mk, color=col, ms=3.5, label=f"{r.capitalize()} to Brown")
ax.axhline(1, color="#999999", lw=0.7)
ax.set_xticks(range(len(W)), labs, rotation=60, ha="right", fontsize=6.3)
ax.set_title("B. Each flow of the certificate in turn", fontsize=8, loc="left")
ax.legend(fontsize=6.3, frameon=False)
ax = axes[2]
yrs = sorted(O["by_year"], key=int)
for k, lab, col in CELLS[:3]:
    ax.plot([int(y) for y in yrs], [O["by_year"][y][k]["white"] for y in yrs], "-o", color=col, ms=2.5)
ax.axhline(1, color="#999999", lw=0.7)
ax.set_xticks([2013, 2018, 2023])
ax.set_ylabel("White to Brown")
ax.set_title("C. By year", fontsize=8, loc="left")
fig.tight_layout()
for ext in ("png", "pdf", "svg"):
    fig.savefig(HERE / "figures" / f"indicators_decomposition.{ext}", dpi=300, bbox_inches="tight")
print("indicators figure written")
