"""The figures of paper 5 (violence/), from results/results.json (youth) and results/violence.json, into figures/.

    python papers/race_at_death/figures_violence.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).parent
OUT, RES = HERE / "figures", HERE / "results"
R = json.loads((RES / "results.json").read_text(encoding="utf-8"))
VI = json.loads((RES / "violence.json").read_text(encoding="utf-8"))
Y, YC = R["youth"], R["context"]["youth"]
KINDS = ["natural", "transport", "suicide", "other external", "other assault", "assault by firearm", "legal intervention"]
KL = {"natural": "natural", "transport": "transport", "suicide": "suicide", "other external": "other\nexternal", "other assault": "assault,\nother",
      "assault by firearm": "assault,\nfirearm", "legal intervention": "legal\nintervention"}
CAUSE3 = {"natural": "#0072B2", "external, not assault": "#E69F00", "assault": "#D55E00"}
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})


def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def cell(m, a="Branca", b="Branca"):
    r = m["rows"].get(a, {}).get(b)
    return r if r and r["se"] <= 0.15 else None


# ---------------------------------------------------------------- 1. by cause
fig, ax = plt.subplots(figsize=(7.2, 2.8))
for i, k in enumerate(KINDS):
    for dx, (a, b, col, lab) in zip((-0.15, 0.15), (("Branca", "Branca", "#E69F00", "White at birth, certified White"),
                                                    ("Parda", "Parda", "#0072B2", "Brown at birth, certified Brown")), strict=True):
        c = cell(Y["by_kind"][k], a, b)
        if c:
            ax.errorbar(i + dx, c["est"], yerr=1.96 * c["se"], fmt="o", color=col, ms=4, capsize=1.5, label=lab if i == 0 else None)
ax.set_xticks(range(len(KINDS)), [KL[k] for k in KINDS])
ax.set_ylim(0, 1)
ax.set_ylabel("Proportion of deaths")
ax.legend(frameon=False, fontsize=7, loc="lower left")
fig.tight_layout()
save(fig, "violence_cause")

# ---------------------------------------------------------------- 2. composition, certifier, schooling
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7), sharey=True)
ax = axes[0]
for cz, col in CAUSE3.items():
    bins = YC["by_composition"][cz]
    xs, ys, es = [], [], []
    for b in bins:
        c = cell(b["matrix"])
        if c:
            xs.append(np.mean(b["white_share"]) if b["white_share"][1] <= 1 else 0.9)
            ys.append(c["est"])
            es.append(1.96 * c["se"])
    ax.errorbar(xs, ys, yerr=es, fmt="-o", color=col, ms=3, capsize=1.5, label=cz)
ax.set_xlabel("municipality's share of White births")
ax.set_ylabel("White at birth, certified White")
ax.set_title("A. Composition", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=6)
ax = axes[1]
CERTS = ["physician", "medical examiner", "death verification service"]
for j, (cz, col) in enumerate(CAUSE3.items()):
    for i, ce in enumerate(CERTS):
        c = cell(YC["by_certifier"][cz][ce]) if ce in YC["by_certifier"][cz] else None
        if c:
            ax.errorbar(i + (j - 1) * 0.2, c["est"], yerr=1.96 * c["se"], fmt="o", color=col, ms=3.5, capsize=1.5)
ax.set_xticks(range(3), ["physician", "medical\nexaminer", "verification\nservice"])
ax.set_title("B. Certifier", fontsize=8, loc="left")
ax = axes[2]
SCH = ["0-3", "4-7", "8-11", "12 or more"]
for cz, col in CAUSE3.items():
    pts = [(i, cell(YC["by_schooling"][cz][s])) for i, s in enumerate(SCH) if s in YC["by_schooling"][cz]]
    pts = [(i, c) for i, c in pts if c]
    ax.errorbar([p[0] for p in pts], [p[1]["est"] for p in pts], yerr=[1.96 * p[1]["se"] for p in pts], fmt="-o", color=col, ms=3, capsize=1.5)
ax.set_xticks(range(4), SCH)
ax.set_xlabel("mother's schooling at birth (years)")
ax.set_title("C. Schooling", fontsize=8, loc="left")
ax.set_ylim(0, 1.05)
fig.tight_layout()
save(fig, "violence_strata")

# ---------------------------------------------------------------- 3. the earlier hospital record
fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), gridspec_kw={"width_ratios": [1.3, 1]})
ax = axes[0]
G = ["natural", "transport", "suicide", "other assault", "assault by firearm", "all assault"]
GL = ["natural", "transport", "suicide", "assault,\nother", "assault,\nfirearm", "all\nassaults"]
for i, g in enumerate(G):
    for dx, (j, k, col, lab) in zip((-0.15, 0.15), (("white", "white", "#E69F00", "White in hospital, certified White"),
                                                    ("brown", "brown", "#0072B2", "Brown in hospital, certified Brown")), strict=True):
        v = VI["person"][g]["cells"][f"hospital {j}|certified {k}"]
        ax.errorbar(i + dx, v["est"], yerr=[[v["est"] - v["lo"]], [v["hi"] - v["est"]]], fmt="o", color=col, ms=4, capsize=1.5, label=lab if i == 0 else None)
ax.set_xticks(range(len(G)), GL, fontsize=7)
ax.set_ylim(0, 1)
ax.set_ylabel("Proportion of deaths")
ax.set_title("A. Agreement of the two records", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=6.5, loc="lower left")
ax = axes[1]
for i, g in enumerate(G):
    mg = VI["person"][g]["margins"]
    ax.plot([i, i], [mg["hospital_white"]["est"], mg["certified_white"]["est"]], "-", color="#999999", lw=1)
    ax.plot(i, mg["hospital_white"]["est"], "s", color="#56B4E9", ms=5, label="hospital, in life" if i == 0 else None)
    ax.plot(i, mg["certified_white"]["est"], "o", color="#D55E00", ms=5, label="certificate" if i == 0 else None)
ax.set_xticks(range(len(G)), GL, fontsize=7)
ax.set_ylim(0, 0.6)
ax.set_ylabel("Share White")
ax.set_title("B. The same deaths, two records", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=6.5)
fig.tight_layout()
save(fig, "violence_hospital")
print("violence figures written")
