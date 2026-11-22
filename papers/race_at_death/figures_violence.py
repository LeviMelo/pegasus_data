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


# ---------------------------------------------------------------- 1. by cause: birth against certificate, the same deaths found among their birth candidates
BC = VI["birth_cert"]
G1 = ["natural", "transport", "suicide", "other external", "undetermined intent", "assault by firearm", "other assault"]
GL1 = ["natural", "transport", "suicide", "other external", "undetermined", "assault, firearm", "assault, other"]
fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.9), gridspec_kw={"width_ratios": [1, 1], "wspace": 0.3})
ax = axes[0]
for i, g in enumerate(G1):
    b, c = BC[g]["birth_white"], BC[g]["certified_white"]
    ax.plot([i, i], [b["est"], c["est"]], "-", color="#999999", lw=1)
    ax.errorbar(i - 0.08, b["est"], yerr=1.96 * b["se"], fmt="s", color="#009E73", ms=4, capsize=1.2, label="at birth" if i == 0 else None)
    ax.errorbar(i + 0.08, c["est"], yerr=1.96 * c["se"], fmt="o", color="#D55E00", ms=4, capsize=1.2, label="on the certificate" if i == 0 else None)
ax.set_xticks(range(len(G1)), GL1, fontsize=6.5, rotation=35, ha="right")
ax.set_ylim(0, 0.7)
ax.set_ylabel("Share White", fontsize=7)
ax.set_title("A. Share White at birth and at death", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=7, loc="lower left")
ax = axes[1]
for i, g in enumerate(G1):
    for dx, (k, col, lab) in zip((-0.15, 0.15), (("white_white", "#E69F00", "White at birth, certified White"),
                                                 ("brown_brown", "#0072B2", "Brown at birth, certified Brown")), strict=True):
        v = BC[g][k]
        ax.errorbar(i + dx, v["est"], yerr=1.96 * v["se"], fmt="o", color=col, ms=4, capsize=1.2, label=lab if i == 0 else None)
ax.set_xticks(range(len(G1)), GL1, fontsize=6.5, rotation=35, ha="right")
ax.set_ylim(0, 1)
ax.set_ylabel("Proportion of deaths", fontsize=7)
ax.set_title("B. Certified in the race at birth", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=7, loc="lower left")
save(fig, "violence_cause")

# ---------------------------------------------------------------- 2. composition, certifier, schooling
fig, axes = plt.subplots(1, 3, figsize=(6.9, 2.8), sharey=True)
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
ax.legend(frameon=False, fontsize=7)
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
fig, axes = plt.subplots(1, 2, figsize=(6.9, 3.0), gridspec_kw={"width_ratios": [1.15, 1.15]})
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
TR = VI["three_records"]
for i, g in enumerate(G):
    t = TR[g]
    xs = [i - 0.2, i, i + 0.2]
    vals = [t["birth_white"], t["hospital_white"], t["certified_white"]]
    ax.plot(xs, [v["est"] for v in vals], "-", color="#bbbbbb", lw=0.8)
    for x_, v, col, mk, lab in zip(xs, vals, ("#009E73", "#56B4E9", "#D55E00"), ("s", "D", "o"), ("birth", "hospital, in life", "certificate"), strict=True):
        ax.errorbar(x_, v["est"], yerr=1.96 * v["se"], fmt=mk, color=col, ms=3.5, capsize=1, label=lab if i == 0 else None)
ax.set_xticks(range(len(G)), GL, fontsize=7)
ax.set_ylim(0, 0.75)
ax.set_ylabel("Share White", fontsize=7)
ax.set_title("B. The same deaths, three records", fontsize=8, loc="left")
ax.legend(frameon=False, fontsize=6.5, loc="upper right", ncol=3)
fig.tight_layout()
save(fig, "violence_hospital")
# ---------------------------------------------------------------- the cause contrast by place (review 2026-11-22, 5.1 and 5.2)
VP = json.loads((RES / "violence_place.json").read_text(encoding="utf-8"))
CAUSES = [("natural", "Natural", "#0072B2"), ("transport", "Transport", "#999999"), ("all assault", "Assault", "#D55E00"), ("suicide", "Suicide", "#CC79A7")]
fig = plt.figure(figsize=(6.9, 2.8))
axA, axB = fig.add_axes([0.08, 0.2, 0.42, 0.66]), fig.add_axes([0.6, 0.2, 0.38, 0.66])
cut = VP["thirds_cut"]
labs = [f"under {cut[0]:.2f}", f"{cut[0]:.2f}-{cut[1]:.2f}", f"{cut[1]:.2f} or more"]
for k, (g, lab, col) in enumerate(CAUSES):
    ys = [VP["by_occurrence_third"][str(t)][g] for t in range(3)]
    xs = np.arange(3) + (k - 1.5) * 0.17
    axA.errorbar(xs, [100 * y["shift"] for y in ys], yerr=[196 * y["se"] for y in ys], fmt="o", ms=3.5, color=col, capsize=1.5, lw=0.9, label=lab)
axA.axhline(0, color="#777777", lw=0.6)
axA.set_xticks(range(3), labs)
axA.set_xlabel("Share of White births in the municipality where the death occurred")
axA.set_ylabel("Change of the share White,\nbirth to certificate (points)")
axA.set_title("A  By composition of the place of occurrence", loc="left", fontsize=8)
axA.legend(fontsize=6, frameon=False, ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.08))
for k, (g, _lab, col) in enumerate(CAUSES):
    ys = [VP[w][g] for w in ("died_at_home_municipality", "died_elsewhere", "died_in_hospital", "died_out_of_hospital")]
    xs = np.arange(4) + (k - 1.5) * 0.17
    axB.errorbar(xs, [100 * y["shift"] for y in ys], yerr=[196 * y["se"] for y in ys], fmt="o", ms=3.5, color=col, capsize=1.5, lw=0.9)
axB.axhline(0, color="#777777", lw=0.6)
axB.set_xticks(range(4), ["in residence\nmunicipality", "elsewhere", "in hospital", "out of\nhospital"], fontsize=6.5)
axB.set_title("B  By where the death occurred", loc="left", fontsize=8)
save(fig, "violence_place")

print("violence figures written")
