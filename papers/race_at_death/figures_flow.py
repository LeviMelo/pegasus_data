"""The design and flow diagrams of the race papers, with the count at every step read from the results files, into figures/.
Coordinates are millimetres on a 175 mm wide page; each box is as tall as its lines.

    python papers/race_at_death/figures_flow.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = Path(__file__).parent
RES = HERE / "results"
R = json.loads((RES / "results.json").read_text(encoding="utf-8"))
BK = json.loads((RES / "black.json").read_text(encoding="utf-8"))
FA = json.loads((RES / "family.json").read_text(encoding="utf-8"))
VI = json.loads((RES / "violence.json").read_text(encoding="utf-8"))
SRC = {"SINASC": "#0072B2", "SIM": "#D55E00", "SIH": "#009E73", "census": "#CC79A7", "result": "#555555"}
plt.rcParams.update({"font.size": 7, "font.family": "DejaVu Sans"})
MM, W = 1 / 25.4, 175.0
LINE, TITLE, PAD = 3.3, 4.2, 2.2


def n0(x):
    return f"{x:,.0f}"


def height(lines):
    return PAD + TITLE + LINE * len(lines) + PAD


def box(ax, x, top, w, title, lines, kind):
    """A box whose top edge is at ``top`` (mm from the bottom); returns its geometry."""
    h = height(lines)
    y = top - h
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.5", lw=1.0, ec=SRC[kind], fc="white"))
    ax.text(x + w / 2, top - PAD, title, ha="center", va="top", fontsize=7.2, weight="bold", color=SRC[kind])
    ax.text(x + w / 2, top - PAD - TITLE, "\n".join(lines), ha="center", va="top", fontsize=6.4, color="#222222", linespacing=1.35)
    return {"x": x, "y": y, "w": w, "h": h}


def harrow(ax, a, b, label="", both=False):
    yy = min(a["y"] + a["h"], b["y"] + b["h"]) - TITLE - 3
    p, q = (a["x"] + a["w"], yy), (b["x"], yy)
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=8, lw=0.9, color="#555555", shrinkA=1, shrinkB=1))
    if label:
        ax.text((p[0] + q[0]) / 2, yy - 2, label, ha="center", va="top", fontsize=5.9, color="#333333", linespacing=1.3)


def varrow(ax, a, b, label="", xa=None, xb=None):
    p = ((xa if xa is not None else a["x"] + a["w"] / 2), a["y"])
    q = ((xb if xb is not None else b["x"] + b["w"] / 2), b["y"] + b["h"])
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=8, lw=0.9, color="#555555", shrinkA=1, shrinkB=1))
    if label:
        ax.text((p[0] + q[0]) / 2 + 1.5, (p[1] + q[1]) / 2, label, ha="left", va="center", fontsize=5.9, color="#333333")


def canvas(h):
    fig, ax = plt.subplots(figsize=(W * MM, h * MM))
    ax.set_xlim(0, W)
    ax.set_ylim(0, h)
    ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    return fig, ax


def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(HERE / "figures" / f"{name}.{ext}", dpi=300)
    plt.close(fig)


I, FL = R["infants"], R["infants"]["flow"]
FDR = f"{min(v['fdr_percent'] for v in I['link_quality'].values()):.2f}-{max(v['fdr_percent'] for v in I['link_quality'].values()):.2f}%"
# ---------------------------------------------------------------- the infant linkage (papers 1, 2)
fig, ax = canvas(84)
a = box(ax, 2, 82, 55, "Death certificates (SIM)", [f"infant deaths 2013-2023: {n0(I['certificates'])}", "race recorded on the certificate"], "SIM")
b = box(ax, 118, 82, 55, "Live birth records (SINASC)", ["births 2012-2023", "the mother's race, declared"], "SINASC")
harrow(ax, a, b, "one-to-one probabilistic linkage on birth date,\nsex, residence, birth weight and mother's age", both=True)
c = box(ax, 50, 56, 75, "Linked infant deaths", [f"{n0(I['linked'])} ({100 * I['linked'] / I['certificates']:.1f}% of certificates)",
                                                 f"with the mother's race: {n0(I['linked_with_race'])}", f"estimated false links {FDR} a year"], "result")
varrow(ax, a, c, xa=29.5, xb=70)
varrow(ax, b, c, xa=145.5, xb=105)
d = box(ax, 2, 25, 55, "Census 2010 sample", [f"{n0(R['census']['pairs_records'])} mother-child records", "how households report", "other, surviving children"], "census")
e = box(ax, 63, 25, 110, "The place, 2013-2023", ["5,570 municipalities, 510 immediate and 133 intermediate regions, 27 states;",
                                                  "composition of births, GDP, schooling, urbanisation, physicians, certification,",
                                                  "race left blank; establishments of birth and death; the certifying physician"], "result")
varrow(ax, c, e, "by residence and occurrence", xa=100, xb=110)
save(fig, "flow_infants")

# ---------------------------------------------------------------- paper 3: three records of the same families
NT, DL = BK["net"], BK["delivery_link"]
fig, ax = canvas(47)
a = box(ax, 2, 45, 44, "Birth record (SINASC)", ["the mother's declared race", f"deliveries of Black-declared mothers", f"with a hospital race: {n0(NT['hospital_declared_black'])}"], "SINASC")
b = box(ax, 65.5, 45, 44, "Delivery admission (SIH)", ["the hospital's record of the mother",
                                                      f"linked {min(v['linked_share'] for v in DL.values()):.2f}-{max(v['linked_share'] for v in DL.values()):.2f} of births a year",
                                                      f"false links {min(v['fdr_percent'] for v in DL.values()):.2f}-{max(v['fdr_percent'] for v in DL.values()):.2f}%"], "SIH")
c = box(ax, 129, 45, 44, "Death certificate (SIM)", ["the infant's certified race", f"infants of Black mothers: {n0(NT['certificate_declared_black'])}",
                                                     f"with the delivery record: {n0(BK['individual']['with_hospital_record_black'])}"], "SIM")
harrow(ax, a, b, "mother's\nbirth date,\nhospital,\nbirth day", both=True)
harrow(ax, b, c, "through\nthe infant\nlinkage", both=True)
box(ax, 2, 19, 171, "What separates the person, the chart and the hospital", [
    "within delivery hospitals and within the establishments of death (infants who died where delivered or elsewhere); each hospital's practice",
    "without the infant's own mother; the same mother at two births, in the same or another hospital (shifted-date control); who filled the birth record"], "result")
save(fig, "flow_black")

# ---------------------------------------------------------------- paper 4: the two censuses
fig, ax = canvas(47)
for i, (y, txt) in enumerate(((2010, ["sample microdata: municipality, single-year ages,", "the mother's order number"]),
                              (2022, ["public sample microdata (released 2026):", "state only, five-year ages, who answered"]))):
    m = FA["matrix"][str(y)]
    tot = sum(m[f"{r}|all"]["white"]["records"] for r in ("white", "brown", "black"))
    box(ax, 2 + 88 * i, 45, 83, f"Census {y}", txt + [f"children 0-9 of White, Brown and Black mothers: {n0(tot)}"], "census")
box(ax, 2, 22, 171, "One pairing rule for both censuses", [
    "a child of the household's couple living with the mother, paired with the couple's woman;",
    "the partner is the couple's man: the father of a child of both, a stepfather otherwise;",
    f"in 2010 it keeps {100 * FA['review1']['coverage']['brown']['couple_share_of_order']:.0f}% of the children 0-9 the mother's order number pairs; design-based errors (states, households)"], "result")
save(fig, "flow_family")

# ---------------------------------------------------------------- paper 5: deaths related to births and admissions without identifiers
TOT = sum(VI["deaths_total"][k] for k in ("natural", "transport", "suicide", "other external", "assault by firearm", "other assault", "legal intervention"))
fig, ax = canvas(47)
a = box(ax, 2, 45, 44, "Live births 2000-2009 (SINASC)", ["the newborn's colour,", "recorded by staff"], "SINASC")
b = box(ax, 65.5, 45, 44, "Deaths at 15-24, 2015-2024 (SIM)", [f"{n0(TOT)} deaths in municipalities", "under 1,600 births a year", "certified race and cause"], "SIM")
c = box(ax, 129, 45, 44, "Admissions 2010-2024 (SIH)", ["race recorded in hospital:", "earlier admissions (30+ days)", "and the admission of the death"], "SIH")
harrow(ax, a, b, "birth date,\nsex,\nmunicipality;\nother sex\nas control", both=True)
harrow(ax, b, c, "same key;\ncontrol\nscaled by\nmunicipality,\nbirth year", both=True)
box(ax, 2, 19, 171, "Estimated for the people found", [
    f"found among birth candidates: about half of deaths, alike for every cause; an earlier admission: {100 * VI['with_admission']['natural']:.0f}% of natural "
    f"and {100 * VI['with_admission']['assault by firearm']:.0f}% of firearm deaths;", "one record per person; checked by a shifted-date placebo, men only and a 180-day window"], "result")
save(fig, "flow_violence")
print("flow figures written")
