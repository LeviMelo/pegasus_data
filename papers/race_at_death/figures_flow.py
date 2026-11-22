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
MC = json.loads((RES / "mechanism.json").read_text(encoding="utf-8"))
BK_MB = MC["black"]
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
c = box(ax, 50, 56, 75, "Linked infant deaths", [f"{n0(I['linked'])} ({100 * I['linked'] / I['certificates']:.1f}% of certificates; {n0(I['certificates'] - I['linked'])} unlinked)",
                                                 f"with the mother's race: {n0(I['linked_with_race'])} ({n0(I['linked'] - I['linked_with_race'])} without)",
                                                 f"estimated false links {FDR} a year"], "result")
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
fig, ax = canvas(50)
a = box(ax, 2, 48, 44, "Birth record (SINASC)", ["the mother's declared race", f"deliveries of Black-declared mothers", f"with a hospital race: {n0(NT['hospital_declared_black'])}"], "SINASC")
b = box(ax, 65.5, 48, 44, "Delivery admission (SIH)", ["the hospital's record of the mother",
                                                      f"linked {min(v['linked_share'] for v in DL.values()):.2f}-{max(v['linked_share'] for v in DL.values()):.2f} of births a year",
                                                      f"false links {min(v['fdr_percent'] for v in DL.values()):.2f}-{max(v['fdr_percent'] for v in DL.values()):.2f}%"], "SIH")
c = box(ax, 129, 48, 44, "Death certificate (SIM)", ["the infant's certified race", f"infants of Black mothers: {n0(NT['certificate_declared_black'])}",
                                                     f"with the delivery record: {n0(BK['individual']['with_hospital_record_black'])}"], "SIM")
harrow(ax, a, b, "mother's\nbirth date,\nhospital,\nbirth day", both=True)
harrow(ax, b, c, "through\nthe infant\nlinkage", both=True)
R3 = MC["review3"]
box(ax, 2, 22, 171, "What separates the person, the chart and the hospital", [
    f"within {BK_MB['mh_delivery_hospital']['strata']} delivery hospitals ({n0(R3['n'])} infants with both records and a race on each);",
    f"where the infant died elsewhere ({n0(R3['elsewhere_informative']['deaths'])} informative deaths); with no prenatal visit "
    f"({n0(R3['within_hospital_by_visits']['none']['deaths'])}); at home ({n0(R3['home_deaths']['mh_over_regions']['deaths'])});",
    f"each hospital's practice without the infant's own mother; the same mother at two births ({n0(MC['movers']['movers_practice_slope']['n'])} movers, shifted-date control)"], "result")
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
TOT = sum(VI["deaths_total"][k] for k in ("natural", "transport", "suicide", "other external", "undetermined intent", "assault by firearm", "other assault", "legal intervention"))
fig, ax = canvas(47)
a = box(ax, 2, 45, 44, "Births (SINASC)", ["2000-2009: the newborn's", "colour, recorded by staff"], "SINASC")
b = box(ax, 65.5, 45, 44, "Deaths (SIM)", [f"15-24 years, 2015-2024: {n0(TOT)}", "in municipalities under", "1,600 births a year"], "SIM")
c = box(ax, 129, 45, 44, "Admissions (SIH)", ["2010-2024: race in hospital,", "earlier admissions (30+ days)", "and the admission of death"], "SIH")
harrow(ax, a, b, "birth date,\nsex,\nmunicipality;\nother sex\nas control", both=True)
harrow(ax, b, c, "same key;\ncontrol\nscaled by\nmunicipality,\nbirth year", both=True)
TR_ = VI["three_records"]
box(ax, 2, 19, 171, "Estimated for the people found, the same deaths in all three records", [
    f"found among birth candidates: about half of deaths, alike for every cause; with an earlier admission: {100 * VI['with_admission']['natural']:.0f}% of natural "
    f"and {100 * VI['with_admission']['assault by firearm']:.0f}% of firearm deaths;", "one record per person; shifted-date placebos at 7 and 14 days; men only; a 180-day window"], "result")
save(fig, "flow_violence")
# ---------------------------------------------------------------- paper 2: the 2 x 2 of numerators and denominators
D2 = json.loads((RES / "indicators2.json").read_text(encoding="utf-8"))
NA = D2["national"]
fig, ax = canvas(66)
a = box(ax, 2, 64, 82, "Deaths by the mother's race", [f"{n0(I['linked_with_race'])} infant deaths linked to their birth records,",
                                                       "scaled to all certificates by certified race"], "SINASC")
b = box(ax, 91, 64, 82, "Deaths by certified race", [f"{n0(I['certificates'])} infant death certificates, 2013-2023,", "the race on the certificate"], "SIM")
c = box(ax, 2, 40, 82, "Births by the mother's race", ["live births 2013-2023 (SINASC),", "the mother's declaration"], "SINASC")
e = box(ax, 91, 40, 82, "Births by the child's race", ["the same births passed through the shares in which", "households classify infants of each mother's race (census 2010)"], "census")


def cell_(k):
    v = NA[k]["white"]
    return f"{v['est']:.2f}"


box(ax, 2, 17, 171, "White to Brown infant mortality rate ratio", [
    f"mother's deaths / mother's births {cell_('mother_over_mother')};   certified deaths / mother's births (the usual way) {cell_('certified_over_mother')};",
    f"certified deaths / child's births {cell_('certified_over_child')};   mother's deaths / child's births {cell_('mother_over_child')}"], "result")
ax.plot([2, 173], [44.4, 44.4], ls=(0, (3, 3)), color="#999999", lw=0.7)
ax.text(173, 45.2, "numerators", ha="right", va="bottom", fontsize=6.2, color="#555555")
ax.text(173, 43.6, "denominators", ha="right", va="top", fontsize=6.2, color="#555555")
save(fig, "flow_indicators")
print("flow figures written")
