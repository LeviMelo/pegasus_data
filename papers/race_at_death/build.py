"""Builds the manuscript, the supplement and the figures from results/results.json. No number is typed here.

    python papers/race_at_death/build.py        -> out/manuscript.docx, out/supplement.docx, out/fig*.{png,pdf,svg}
"""
import json
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
R = json.loads((HERE / "results" / "results.json").read_text(encoding="utf-8"))
REFS = json.loads((HERE / "references" / "crossref.json").read_text(encoding="utf-8"))
MANUAL = json.loads((HERE / "references" / "manual.json").read_text(encoding="utf-8"))

DESIGN = "cross-sectional study of routinely collected birth and death records"
OBJECTIVE = ("to measure the agreement between the race on the death certificate and the race on the birth record among people who died before "
             "age 25 in Brazil, and to compare the mortality rate ratios of children under the two classifications")
NAMES = {"Branca": "White", "Preta": "Black", "Parda": "Brown", "Indigena": "Indigenous"}


# ---------------------------------------------------------------- formatting: a miss raises
def f2(x):
    return f"{x:.2f}"


def pct(x):
    return f"{100 * x:.1f}%"


def n0(x):
    return f"{int(round(x)):,}"


def ci(e, log=False):
    """est (95%CI lo; hi) from an {est, se}; a ratio's interval on the log scale."""
    v, s = e["est"], e["se"]
    lo, hi = (v * math.exp(-1.96 * s / v), v * math.exp(1.96 * s / v)) if log else (v - 1.96 * s, v + 1.96 * s)
    assert lo <= v <= hi
    return f"{v:.2f} (95%CI {lo:.2f}; {hi:.2f})"


def size_row(block, size):
    return next(r for r in block if r["size"] == size)


# ---------------------------------------------------------------- references: numbered at first citation
order: list[str] = []


def cite(*keys):
    for k in keys:
        if k not in REFS and k not in MANUAL:
            raise KeyError(f"reference {k} is not verified")
        if k not in order:
            order.append(k)
    nums = sorted(order.index(k) + 1 for k in keys)
    return "[" + ",".join(str(n) for n in nums) + "]"


def reference_text(k):
    if k in MANUAL:
        return MANUAL[k]
    r = REFS[k]
    authors = ", ".join(r["authors"][:6]) + (", et al" if len(r["authors"]) > 6 else "")
    vol = f";{r['volume']}" if r.get("volume") else ""
    issue = f"({r['issue']})" if r.get("issue") else ""
    pages = f":{r['pages']}" if r.get("pages") else ""
    return f"{authors}. {r['title']}. {r['journal']}. {r['year']}{vol}{issue}{pages}. doi:{r['doi']}"


# ---------------------------------------------------------------- the numbers used in the text
V = R["validation"]
v_all, v_small, v_big = size_row(V["rows"], "all"), size_row(V["rows"], "<400"), size_row(V["rows"], "6,400-25,599")
C14, C59 = R["children"]["1-4"], R["children"]["5-9"]
c14_small, c14_all = size_row(C14["by_size"], "<400"), size_row(C14["by_size"], "all")
K = R["kinds"]
T3 = R["triples"]
form = {r["year"]: r for r in R["form"]}
coh = {(r["cohort"], r["year"]): r for r in R["cohorts"]}
cb = {r["cohort"]: r for r in R["cohorts_birth"]}
lost = 1 - coh[(2000, 2022)]["branca"] / cb[2000]["branca"]
deaths_children = C14["deaths"] + C59["deaths"]
deaths_youth = sum(K[k]["small"]["deaths"] + K[k]["large"]["deaths"] for k in K)


# ---------------------------------------------------------------- figures
def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


COL = {"Branca": "#0072B2", "Parda": "#D55E00", "Preta": "#000000"}
sizes = ["<400", "400-1,599", "1,600-6,399", "6,400-25,599"]
fig, ax = plt.subplots(figsize=(6.5, 3.6))
for off, race in zip((-0.2, 0, 0.2), ("Branca", "Parda", "Preta"), strict=True):
    xs = [i + off for i in range(len(sizes))]
    e = [size_row(V["rows"], s)["stays"][race] for s in sizes]
    ax.errorbar(xs, [x["est"] for x in e], yerr=[1.96 * x["se"] for x in e], fmt="o", color=COL[race], capsize=2, label=f"{NAMES[race]}, estimate")
    ax.scatter(xs, [size_row(V["rows"], s)["link"][race] for s in sizes], marker="x", s=60, color=COL[race], label=f"{NAMES[race]}, one-to-one linkage")
ax.set_xticks(range(len(sizes)), sizes)
ax.set_xlabel("Live births per year in the municipality")
ax.set_ylabel("Proportion certified with the birth-record race")
ax.set_ylim(0, 1)
ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.28), frameon=False)
save(fig, "fig1")

fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.0), sharey=True)
for ax, (label, block) in zip(axes, (("1-4 years", C14), ("5-9 years", C59)), strict=True):
    for i, race in enumerate(("Branca", "Preta", "Indigena")):
        e = block["rate_ratio"][race]
        lo, hi = e["est"] * math.exp(-1.96 * e["se"] / e["est"]), e["est"] * math.exp(1.96 * e["se"] / e["est"])
        ax.errorbar([e["est"]], [i + 0.15], xerr=[[e["est"] - lo], [hi - e["est"]]], fmt="o", color="#0072B2", capsize=2, label="mother's race on the birth record" if i == 0 else None)
        cl, ch = e["certificate"] * math.exp(-1.96 * e["certificate_se"] / e["certificate"]), e["certificate"] * math.exp(1.96 * e["certificate_se"] / e["certificate"])
        ax.errorbar([e["certificate"]], [i - 0.15], xerr=[[e["certificate"] - cl], [ch - e["certificate"]]], fmt="x", markersize=7, color="#D55E00", capsize=2,
                    label="race on the death certificate" if i == 0 else None)
        ax.annotate(f"{e['est']:.2f}", (e["est"], i + 0.15), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=7)
        ax.annotate(f"{e['certificate']:.2f}", (e["certificate"], i - 0.15), textcoords="offset points", xytext=(0, -12), ha="center", fontsize=7)
    ax.axvline(1, color="grey", lw=0.8)
    ax.set_xscale("log")
    ax.set_xticks([0.5, 1, 2, 4, 8], ["0.5", "1", "2", "4", "8"])
    ax.set_yticks(range(3), ["White", "Black", "Indigenous"])
    ax.set_ylim(-0.6, 2.6)
    ax.set_title(label, fontsize=9)
    ax.set_xlabel("Rate ratio (reference: Brown)")
axes[0].legend(fontsize=7, loc="upper center", bbox_to_anchor=(1.05, 1.32), ncol=2, frameon=False)
save(fig, "fig2")

kinds = ["natural", "transport", "other external", "assault"]
klabel = {"natural": "Natural causes", "transport": "Transport accidents", "other external": "Other external causes", "assault": "Assault"}
fig, ax = plt.subplots(figsize=(6.5, 3.2))
for off, key, col, lab in ((-0.18, "Branca stays", "#0072B2", "White at birth, certified White"), (0.18, "Branca>Parda", "#D55E00", "White at birth, certified Brown")):
    e = [K[k]["small"][key] for k in kinds]
    xs = [i + off for i in range(len(kinds))]
    ax.bar(xs, [x["est"] for x in e], width=0.34, color=col, label=lab)
    ax.errorbar(xs, [x["est"] for x in e], yerr=[1.96 * x["se"] for x in e], fmt="none", ecolor="black", capsize=2)
    for x, v in zip(xs, e, strict=True):
        ax.annotate(f"{v['est']:.2f}", (x, v["est"] + 1.96 * v["se"]), textcoords="offset points", xytext=(0, 3), ha="center", fontsize=7)
ax.set_xticks(range(len(kinds)), [klabel[k] for k in kinds], fontsize=8)
ax.set_ylabel("Proportion of deaths at 15-24 years")
ax.set_ylim(0, 1)
ax.legend(fontsize=7, frameon=False, loc="upper right")
save(fig, "fig3")


# ---------------------------------------------------------------- document helpers
def new_doc():
    d = Document()
    style = d.styles["Normal"]
    style.font.name, style.font.size = "Times New Roman", Pt(11)
    for s in d.sections:
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(2.5)
    return d


def para(d, text, bold=False, italic=False, align=None):
    text = re.sub(r"([.,;]) (\[\d+(?:,\d+)*\])", lambda m: " " + m.group(2) + m.group(1), text)          # a citation goes before the punctuation
    p = d.add_paragraph()
    r = p.add_run(text)
    r.bold, r.italic = bold, italic
    if align:
        p.alignment = align
    return p


def table(d, title, header, rows, notes=()):
    para(d, title, bold=True)
    t = d.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for i, h in enumerate(header):
        t.rows[0].cells[i].text = h
    for row in rows:
        cells = t.add_row().cells
        assert len(row) == len(header), (title, row)
        for i, v in enumerate(row):
            cells[i].text = str(v)
            if i:
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for cell in (c for r in t.rows for c in r.cells):
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.size = Pt(10)
    for note in notes:
        para(d, note).runs[0].font.size = Pt(9)
    d.add_paragraph()


def figure(d, name, title, notes=()):
    d.add_picture(str(OUT / f"{name}.png"), width=Cm(15))
    para(d, title, bold=True)
    for note in notes:
        para(d, note).runs[0].font.size = Pt(9)
    d.add_paragraph()


# ---------------------------------------------------------------- the manuscript
def cell_ci(e):
    """A proportion from the candidate estimator: shown as estimated; 'not estimable' when it leaves 0-1 or its error is wide."""
    if e["est"] < 0 or e["est"] > 1 or e["se"] > 0.15:
        return "not estimable"
    return ci(e)


Y0, Y1 = R["old_cohort_death_years"]                       # birth years of those who died at 15-24
YOUTH = f"{Y0 + 15}-2024"
small_youth = sum(K[k]["small"]["deaths"] for k in kinds)
no_class = C14["deaths"] - size_row(C14["by_size"], "all")["deaths"]
fig1_n = sum(size_row(V["rows"], s_)["deaths"] for s_ in sizes)
CF = R["cohort_falls"]
exc = "; ".join(f"the cohort born in {c0}-{c0 + 4} between {a} and {b}" for c0, a, b in CF["exceptions"])
rr, rr59 = C14["rate_ratio"], C59["rate_ratio"]
wl, wl59 = C14["rate_ratio_without_large"], C59["rate_ratio_without_large"]


def cert(e):
    return ci({"est": e["certificate"], "se": e["certificate_se"]}, log=True)


v_top = size_row(V["rows"], ">=25,600")
# claims the text makes in words: each must hold in the results, or the build stops
def inside(e_small, e_main):
    v, lo_hi = e_small["est"], (e_main["est"] * math.exp(-1.96 * e_main["se"] / e_main["est"]), e_main["est"] * math.exp(1.96 * e_main["se"] / e_main["est"]))
    return lo_hi[0] <= v <= lo_hi[1]


assert all(inside(blk["rate_ratio_without_large"][k], blk["rate_ratio"][k]) for blk in (C14, C59) for k in ("Branca", "Preta", "Indigena")), "sensitivity outside the main intervals"
assert rr["Branca"]["est"] < 1 < rr["Branca"]["certificate"] and rr59["Branca"]["est"] < 1 < rr59["Branca"]["certificate"], "the White to Brown ratios do not have opposite directions"
assert c14_small["moves"]["Preta>Parda"]["est"] > c14_small["stays"]["Preta"]["est"], "children of Black mothers are not more often certified Brown than Black"
assert K["assault"]["small"]["Branca stays"]["est"] + 1.96 * K["assault"]["small"]["Branca stays"]["se"] < K["natural"]["small"]["Branca stays"]["est"] - 1.96 * K["natural"]["small"]["Branca stays"]["se"]
assert all(not (0 <= K[k]["large"]["Branca stays"]["est"] <= 1) or K[k]["large"]["Branca stays"]["se"] > 0.15 for k in kinds), "a large-municipality White row is estimable"
assert v_top["found"] > 1, "the largest class no longer fails"
assert T3["certificate_given_hospital"]["Branca"]["Branca"] > T3["certificate_given_hospital"]["Branca"]["Parda"]

d = new_doc()
TITLE = ("Race on death certificates and race on birth records in Brazil: cross-sectional study of deaths before age 25 related to the births "
         "of their birth date, sex and municipality, 2013-2024")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)

d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}. Deaths in the Mortality Information System (2013-2024) were related to the live births of the same birth date, sex "
        "and municipality of residence in the Live Birth Information System. Births of the other sex on the same day in the same municipality served as the control for "
        "chance agreement (candidate estimator). The race on the birth record was the mother's own for children born from 2012 and the newborn's recorded colour for "
        "people born from 2000 to 2010. The estimator was compared with a one-to-one linkage of infant deaths. Mortality rate ratios used the births of the same cohorts "
        "as denominators.")
para(d, f"Results: Among {n0(v_all['deaths'])} infant deaths, the proportion certified with the birth-record race was {ci(v_all['stays']['Branca'])} (95% confidence "
        f"interval, CI) for White, {ci(v_all['stays']['Parda'])} for Brown and {ci(v_all['stays']['Preta'])} for Black; the one-to-one linkage gave "
        f"{f2(v_all['link']['Branca'])}, {f2(v_all['link']['Parda'])} and {f2(v_all['link']['Preta'])}. At 1-4 years ({n0(C14['deaths'])} deaths), the mortality rate ratio "
        f"of children of White mothers to children of Brown mothers was {ci(rr['Branca'], log=True)}, and the ratio by certified race was {cert(rr['Branca'])}; for Black "
        f"against Brown, {ci(rr['Preta'], log=True)} and {cert(rr['Preta'])}; for Indigenous against Brown, {ci(rr['Indigena'], log=True)} and {cert(rr['Indigena'])}. "
        f"At 15-24 years ({YOUTH}; municipalities with fewer than 1,600 births per year; {n0(small_youth)} deaths), people recorded as White at birth were certified White in "
        f"{ci(K['natural']['small']['Branca stays'])} of deaths from natural causes and {ci(K['assault']['small']['Branca stays'])} of deaths from assault.")
para(d, "Conclusion: The race on the death certificate disagreed with the race on the birth record; among children the mortality rate ratio between White and Brown had "
        "opposite directions under the two classifications, and at 15-24 years the certified race of people recorded as White at birth differed by cause of death.")
para(d, "Keywords: Race Factors; Death Certificates; Medical Record Linkage; Mortality; Health Status Disparities; Brazil. [to be checked against MeSH/DeCS by the authors]", italic=True)

d.add_heading("Introduction", level=1)
para(d, f"Mortality rates by race divide deaths classified by one source by a population classified by another. In Brazil the race on the death certificate is recorded "
        f"by whoever fills it in, and the race in the census and on the birth record is declared by the person or by the mother {cite('travassos2004', 'cardoso2005')}. "
        f"Infant mortality rates by race differed according to the information systems used for numerator and denominator {cite('cardoso2005', 'caldas2017')}, and the race "
        f"assigned by an interviewer differs from the race a respondent declares {cite('telles1998', 'bailey2013', 'muniz2017')}.")
para(d, f"Race is not fixed over a life. Brazilian censuses show a growing share of the Brown and Black categories {cite('miranda2015', 'loveman2012')}; in the United "
        f"States, individual responses changed between two censuses {cite('liebler2017')} and racial classification followed changes in social position {cite('saperstein2012')}. "
        f"On death certificates in the United States the recorded race varied with the cause of death {cite('noymer2011')}, and misclassification of ethnicity on "
        f"certificates altered mortality comparisons {cite('arias2010')}.")
para(d, f"Linked birth and death records give two classifications for the same person. Probabilistic record linkage {cite('fellegi1969')} needs fields that tell "
        f"individuals apart, and errors of linkage bias the estimates that use linked data {cite('doidge2019')}. In the Brazilian mortality files examined here, the fields "
        "on the mother and the birth are filled for deaths before one year of age only, so that after infancy a death shares with a birth record the birth date, the sex "
        f"and the municipality. Completeness of the race field has been assessed in the Brazilian systems {cite('braz2013', 'romero2006')}; the authors found no study of "
        "its agreement with the birth record after infancy. This study uses an estimator that requires no one-to-one match, checks it on infant deaths against a "
        "one-to-one linkage, and applies it to ages 1 to 9 and 15 to 24. Deaths at 15 to 24 years are analysed by cause because the certified race may depend on the "
        "circumstances of death; the racial composition of birth cohorts across censuses and the race recorded for the same women at delivery, at hospital admission and "
        "at death are examined to interpret the comparison.")
para(d, f"The objective was {OBJECTIVE}.")

d.add_heading("Methods", level=1)
para(d, "Design", bold=True)
para(d, f"This is a {DESIGN}. The unit is the death; each death is related to the live births of its birth cohort.")
para(d, "Setting and data sources", bold=True)
para(d, f"Deaths came from the Mortality Information System and births from the Live Birth Information System of the Brazilian Ministry of Health, in the public, "
        f"anonymised national files {cite('datasus')}, obtained in 2026. Births of 2000 to 2023 and deaths of 2013 to 2024 were used. Municipalities were those of the files' "
        "own coding; seven-digit codes in the earlier birth files were converted to the six-digit code of the same municipality.")
para(d, f"In these files the race field of the birth record changed content after 2010. A field for the mother's race was filled in {pct(form[2010]['mother_field'])} of "
        f"births in 2010, {pct(form[2011]['mother_field'])} in 2011 and {pct(form[2012]['mother_field'])} in 2012, and wherever both fields were filled the newborn's race "
        f"equalled the mother's. Births recorded as Black were {pct(form[2010]['preta'])} of births in 2010 and {pct(form[2012]['preta'])} in 2012 (Supplementary Table S1). "
        "Births from 2012 onward were taken to carry the mother's own declaration and births of 2000 to 2010 the colour recorded for the newborn. The two were not pooled, "
        "and births of 2011 were not used.")
para(d, "Participants", bold=True)
para(d, f"Three sets of deaths were analysed. (1) Deaths before one year of age in 2021 and 2022, for validation. (2) Deaths at 1 to 9 completed years in 2013 to 2024 of "
        f"children born from 2012 to 2023. (3) Deaths at 15 to 24 completed years in {YOUTH.replace('-', ' to ')} of people born from {Y0} to {Y1}. Age was the age in completed "
        "years on the certificate. Deaths without a municipality of residence, a sex or a valid birth date were excluded. No death was excluded for its race: certificates "
        "without a race and the Yellow category were kept in all totals and are not reported separately.")
para(d, "Variables", bold=True)
para(d, "Certified race is the race on the death certificate. Birth-record race is the race on the birth record: the mother's race for children born from 2012, the "
        "newborn's recorded colour for people born from 2000 to 2010. Both use the categories White, Black, Yellow, Brown and Indigenous. The underlying cause of death was "
        "grouped by the International Classification of Diseases, 10th Revision: transport accidents (V01-V99), assault and legal intervention (X85-Y09, Y35, Y36), other "
        "external causes (the remaining codes V01-Y98) and natural causes (all other codes). Municipalities were classed by their live births in the year of the birth "
        "cohort, in classes whose bounds increase by a factor of four from 400.")
para(d, "Candidate estimator", bold=True)
para(d, "For each death, the candidates are the births that share its birth date, its sex and its municipality of residence (the mother's residence at the birth). One "
        "candidate is the deceased, unless the family moved; the others agree by chance. As the control, the births of the other sex on the same day in the same "
        "municipality were counted and multiplied by the ratio of births of the two sexes in that municipality and year. For a group of deaths, the number of candidates "
        "with birth-record race j among deaths with certified race k, less the same number in the control, estimates t times the number of deaths with that pair of races, "
        "where t is the proportion of the deceased found among their candidates. The proportion certified with the birth-record race j is the estimate for the pair (j, j) "
        "over the sum of the estimates for j. The estimate is a difference of counts and is not constrained to lie between 0 and 1. A control based on birth dates shifted "
        "by whole weeks was examined and rejected (Supplementary Text S1).")
para(d, "Mortality rate ratios", bold=True)
para(d, "Deaths by birth-record race were the row sums of the estimator. The denominators were the live births of the same cohorts by race on the birth record, summed "
        "over the calendar years and ages of the deaths; deaths before the age of interest were not subtracted. Ratios between races were taken with Brown as the "
        "reference; t cancels in a ratio if it does not differ by race. Ratios by certified race used all deaths by the race on the certificate over the same denominators.")
para(d, "Analyses", bold=True)
para(d, "Primary analysis: the mortality rate ratios at 1 to 4 and 5 to 9 years by birth-record race and by certified race. Validation: the candidate estimator against "
        "a one-to-one probabilistic linkage of infant deaths to births on birth date, sex, municipality, birth weight and maternal age, with a target of 1% of false links, "
        "by class of municipality. Secondary analyses: (a) the proportion certified with the birth-record race at 1 to 9 years by class of municipality; (b) the same at "
        "15 to 24 years by cause of death and sex, reported for municipalities with fewer than 1,600 births per year, a bound set after the estimates for larger "
        "municipalities were found to leave the interval 0 to 1; (c) the racial composition of five-year birth cohorts on the birth record and at the 2000, 2010 and 2022 "
        "censuses, from census tabulations of race by age scaled to the official population estimates by state, sex and age; (d) for women who died in hospital at 15 to 49 "
        "years and had given birth, the race they declared as mothers, the race recorded at hospital admission and the certified race (Supplementary Text S2). Sensitivity "
        "analyses: the rate ratios without municipalities of 25,600 or more births per year (threat: failure of the estimator where candidates are many); standard errors "
        "by a delete-one-state jackknife (threat: dependence between deaths of one place).")
para(d, "Statistical methods", bold=True)
para(d, "Standard errors treated the candidate and control counts as Poisson and the denominators of proportions as fixed. For the rate ratios by birth-record race the "
        "larger of that standard error and the jackknife standard error was used; for ratios by certified race, the Poisson error of the death counts. Intervals are 95% "
        "confidence intervals from the normal approximation, on the logarithmic scale for ratios. Analyses used Python and DuckDB.")
para(d, "Ethics and data availability", bold=True)
para(d, "The study used public, anonymised data. [Ethics statement, data and code deposit with a persistent identifier, and disclosure of the use of generative artificial "
        "intelligence in the analysis and drafting: to be completed by the authors in the wording of the target journal.]")

d.add_heading("Results", level=1)
v_top = size_row(V["rows"], ">=25,600")
para(d, f"Of {n0(V['certificates_in_system'])} infant death certificates of 2021 and 2022, {n0(v_all['deaths'])} had the fields required and {n0(v_all['linked_deaths'])} had a "
        f"one-to-one linkage with a birth-record race. The deceased was found among the candidates in {pct(v_all['found'])} of deaths. The proportion certified with the "
        f"birth-record race was {ci(v_all['stays']['Branca'])} for White, {ci(v_all['stays']['Parda'])} for Brown and {ci(v_all['stays']['Preta'])} for Black by the candidate "
        f"estimator, and {f2(v_all['link']['Branca'])}, {f2(v_all['link']['Parda'])} and {f2(v_all['link']['Preta'])} by the linkage. In municipalities with fewer than 400 "
        f"births per year the values were {ci(v_small['stays']['Branca'])}, {ci(v_small['stays']['Parda'])} and {ci(v_small['stays']['Preta'])}, against "
        f"{f2(v_small['link']['Branca'])}, {f2(v_small['link']['Parda'])} and {f2(v_small['link']['Preta'])}; with 6,400 to 25,599 births, {ci(v_big['stays']['Branca'])}, "
        f"{ci(v_big['stays']['Parda'])} and {ci(v_big['stays']['Preta'])}, against {f2(v_big['link']['Branca'])}, {f2(v_big['link']['Parda'])} and {f2(v_big['link']['Preta'])}. "
        f"With 25,600 or more births ({n0(v_top['deaths'])} deaths) the estimated proportion found was {pct(v_top['found'])} and the estimate for White was "
        f"{ci(v_top['stays']['Branca'])}, against {f2(v_top['link']['Branca'])} (Table 1, Figure 1, Supplementary Table S2).")
para(d, f"At 1 to 4 years there were {n0(C14['deaths'])} deaths ({n0(no_class)} in a municipality without births in the cohort year), with "
        f"{f2(c14_all['candidates_per_death'])} candidates per death; the deceased was found in {pct(c14_all['found'])}. In municipalities with fewer than 400 births per year "
        f"the proportion certified with the mother's race was {ci(c14_small['stays']['Branca'])} for White, {ci(c14_small['stays']['Parda'])} for Brown and "
        f"{ci(c14_small['stays']['Preta'])} for Black; {ci(c14_small['moves']['Preta>Parda'])} of children of Black mothers were certified Brown and "
        f"{ci(c14_small['moves']['Parda>Branca'])} of children of Brown mothers were certified White (Table 2).")
para(d, f"The mortality rate ratio at 1 to 4 years of children of White mothers to children of Brown mothers was {ci(rr['Branca'], log=True)}; the ratio of deaths "
        f"certified White to deaths certified Brown over the same births was {cert(rr['Branca'])}. For Black against Brown the two ratios were {ci(rr['Preta'], log=True)} and "
        f"{cert(rr['Preta'])}; for Indigenous against Brown, {ci(rr['Indigena'], log=True)} and {cert(rr['Indigena'])}. At 5 to 9 years ({n0(C59['deaths'])} deaths) the ratios "
        f"by birth-record race were {ci(rr59['Branca'], log=True)}, {ci(rr59['Preta'], log=True)} and {ci(rr59['Indigena'], log=True)}, and by certified race "
        f"{cert(rr59['Branca'])}, {cert(rr59['Preta'])} and {cert(rr59['Indigena'])} (Figure 2). Without municipalities of 25,600 or more births per year "
        f"({n0(C14['deaths_without_large'])} deaths at 1 to 4 years), the ratios by birth-record race at 1 to 4 years were {ci(wl['Branca'], log=True)}, "
        f"{ci(wl['Preta'], log=True)} and {ci(wl['Indigena'], log=True)}, and at 5 to 9 years {ci(wl59['Branca'], log=True)}, {ci(wl59['Preta'], log=True)} and "
        f"{ci(wl59['Indigena'], log=True)}. Leaving out one state at a time, the White to Brown ratio at 1 to 4 years ranged from {f2(rr['Branca']['loo_min'])} to "
        f"{f2(rr['Branca']['loo_max'])} (Supplementary Table S3).")
ks, ka, kt = K["natural"]["small"], K["assault"]["small"], K["transport"]["small"]
para(d, f"At 15 to 24 years, in municipalities with fewer than 1,600 births per year, the deceased was found in {pct(ks['found'])} of deaths from natural causes and "
        f"{pct(ka['found'])} of deaths from assault. People recorded as White at birth were certified White in {ci(ks['Branca stays'])} of {n0(ks['deaths'])} deaths from "
        f"natural causes, {ci(kt['Branca stays'])} of {n0(kt['deaths'])} deaths from transport accidents and {ci(ka['Branca stays'])} of {n0(ka['deaths'])} deaths from assault; "
        f"they were certified Brown in {ci(ks['Branca>Parda'])}, {ci(kt['Branca>Parda'])} and {ci(ka['Branca>Parda'])}. People recorded as Brown at birth were certified Brown in "
        f"{ci(ks['Parda stays'])}, {ci(kt['Parda stays'])} and {ci(ka['Parda stays'])} (Table 3, Figure 3). In municipalities with 1,600 or more births per year the estimates "
        f"for people recorded as White left the interval 0 to 1; people recorded as Brown were certified Brown in {ci(K['natural']['large']['Parda stays'])} of deaths from "
        f"natural causes and {ci(K['assault']['large']['Parda stays'])} of deaths from assault (Supplementary Table S4).")
para(d, f"Of the cohort born in 2000 to 2004, {pct(cb[2000]['branca'])} were recorded as White, {pct(cb[2000]['parda'])} as Brown and {pct(cb[2000]['preta'])} as Black at "
        f"birth; the shares were {pct(coh[(2000, 2010)]['branca'])}, {pct(coh[(2000, 2010)]['parda'])} and {pct(coh[(2000, 2010)]['preta'])} at the 2010 census and "
        f"{pct(coh[(2000, 2022)]['branca'])}, {pct(coh[(2000, 2022)]['parda'])} and {pct(coh[(2000, 2022)]['preta'])} at the 2022 census. Among the five-year cohorts born from "
        f"1940 to 2009, the share White was lower at the later census in {CF['white_fell']} of {CF['intervals']} comparisons between consecutive censuses"
        + (f" (exception: {exc})" if exc else "") + " (Table 4, Supplementary Table S5).")
para(d, f"Among {n0(T3['with_three'])} women with a race declared as mothers, a race recorded at hospital admission and a certified race, the hospital recorded the "
        f"declared race for {f2(T3['hospital_as_declared']['Branca'])} of White, {f2(T3['hospital_as_declared']['Parda'])} of Brown and {f2(T3['hospital_as_declared']['Preta'])} "
        f"of Black women, and the certificate for {f2(T3['certificate_as_declared']['Branca'])}, {f2(T3['certificate_as_declared']['Parda'])} and "
        f"{f2(T3['certificate_as_declared']['Preta'])}. A woman declared White was certified White in {f2(T3['certificate_given_hospital']['Branca']['Branca'])} of cases when "
        f"the hospital had recorded White and in {f2(T3['certificate_given_hospital']['Branca']['Parda'])} when it had recorded Brown (Supplementary Table S6).")

rows = [[r["size"], n0(r["deaths"]), pct(r["found"])] + [x for k in ("Branca", "Parda", "Preta") for x in (ci(r["stays"][k]), f2(r["link"][k]))] for r in V["rows"]]
table(d, f"Table 1 - Proportion of infant deaths certified with the race on the birth record, estimated without individual linkage and observed in a one-to-one linkage, "
         f"by live births per year in the municipality of residence, Brazil, 2021-2022 (n={n0(v_all['deaths'])})",
      ["Live births per year", "Deaths", "Deceased found, %", "White, estimate (95%CI)", "White, linkage", "Brown, estimate (95%CI)", "Brown, linkage", "Black, estimate (95%CI)",
       "Black, linkage"], rows, ["CI: confidence interval. Deceased found: estimated proportion of the deceased among the candidate births."])
figure(d, "fig1", f"Figure 1 - Proportion of infant deaths certified with the race on the birth record, estimated without individual linkage (points) and observed in a "
                  f"one-to-one linkage (crosses), by live births per year in the municipality of residence, municipalities with fewer than 25,600 births per year, Brazil, "
                  f"2021-2022 (n={n0(fig1_n)})", ["Bars: 95% confidence intervals."])
rows = [[r["size"], n0(r["deaths"]), f2(r["candidates_per_death"]), pct(r["found"])] + [cell_ci(r["stays"][k]) for k in ("Branca", "Parda", "Preta")] for r in C14["by_size"]]
table(d, f"Table 2 - Proportion of deaths at 1-4 years certified with the mother's race on the birth record, by live births per year in the municipality of residence, "
         f"Brazil, 2013-2024 (n={n0(C14['deaths'])})",
      ["Live births per year", "Deaths", "Candidates per death", "Deceased found, %", "White (95%CI)", "Brown (95%CI)", "Black (95%CI)"], rows,
      ["CI: confidence interval. Not estimable: estimate outside 0 to 1 or standard error above 0.15.",
       f"{n0(no_class)} death in a municipality without births in the cohort year is in no class."])
figure(d, "fig2", f"Figure 2 - Mortality rate ratios by the mother's race on the birth record and by the race on the death certificate, children of 1-4 years "
                  f"(n={n0(C14['deaths'])}) and 5-9 years (n={n0(C59['deaths'])}), Brazil, 2013-2024", ["Reference: Brown. Bars: 95% confidence intervals. Logarithmic scale."])
rows = [[klabel[k], n0(K[k]["small"]["deaths"]), pct(K[k]["small"]["found"]), ci(K[k]["small"]["Branca stays"]), ci(K[k]["small"]["Branca>Parda"]), ci(K[k]["small"]["Parda stays"]),
         ci(K[k]["small"]["Preta stays"])] for k in kinds]
table(d, f"Table 3 - Certified race of people who died at 15-24 years according to the colour recorded at birth, by cause of death, municipalities with fewer than 1,600 live "
         f"births per year, Brazil, {YOUTH} (n={n0(small_youth)} deaths)",
      ["Cause of death", "Deaths", "Deceased found, %", "White at birth certified White (95%CI)", "White at birth certified Brown (95%CI)", "Brown at birth certified Brown (95%CI)",
       "Black at birth certified Black (95%CI)"], rows, ["CI: confidence interval. Deaths: all deaths of the cause, of any recorded colour."])
figure(d, "fig3", f"Figure 3 - Proportion certified White and proportion certified Brown among people recorded as White at birth who died at 15-24 years, by cause of death, "
                  f"municipalities with fewer than 1,600 live births per year, Brazil, {YOUTH} (n={n0(small_youth)} deaths of any recorded colour)", ["Bars: 95% confidence intervals."])
rows = []
for c0 in (1950, 1970, 1985, 1995, 2000, 2005):
    for race, key in (("White", "branca"), ("Brown", "parda"), ("Black", "preta")):
        rows.append([f"{c0}-{c0 + 4}", race, pct(cb[c0][key]) if c0 in cb else "-"] + [pct(coh[(c0, y)][key]) if (c0, y) in coh else "-" for y in (2000, 2010, 2022)])
table(d, "Table 4 - Share of each race in selected five-year birth cohorts on the birth record and at the censuses of 2000, 2010 and 2022, Brazil",
      ["Birth cohort", "Race", "Birth record, %", "Census 2000, %", "Census 2010, %", "Census 2022, %"], rows,
      ["Share among people with a race recorded. The birth record holds the newborn's colour for these cohorts. All cohorts are in Supplementary Table S5."])

d.add_heading("Discussion", level=1)
para(d, "The race on the death certificate and the race on the birth record disagreed at every age studied, and the two classifications gave mortality rate ratios "
        "between White and Brown children with opposite directions. Children of Brown mothers were often certified White and children of Black mothers were more often "
        "certified Brown than Black. At 15 to 24 years, people recorded as White at birth were certified White less often when they died from assault than when they died "
        "from natural causes.")
para(d, f"The candidate estimator reproduced the one-to-one linkage of infant deaths in municipalities with fewer than 25,600 births per year and did not in the largest "
        f"ones, where the number of chance candidates per death is two orders of magnitude above that of small municipalities; the rate ratios without those municipalities "
        f"agreed with the national ones. Linkage error is a known source of bias in studies of linked data {cite('doidge2019')}; here the chance agreement is estimated "
        "from a control and not assumed. The validation concerns infants, for whom the deceased was found far more often than at later ages, and does not show that the "
        "estimator is unbiased at 1 to 24 years.")
para(d, f"The findings in children are in the direction of those reported for infants in Brazil, where rates by race depended on which system classified the deaths "
        f"{cite('cardoso2005', 'caldas2017')}. Two readings of the disagreement in childhood are possible and are not separated here. The certifier may assign a lighter "
        f"category than the family would declare, as interviewers and respondents differ {cite('telles1998', 'muniz2017')}. Or the child's race may differ from the mother's, "
        "which the birth record holds: a child of a Black mother certified Brown may be a child the family also calls Brown. The rate ratios by the mother's race do not "
        "depend on that distinction, because numerator and denominator share the mother's classification; the ratios by certified race do.")
para(d, f"At 15 to 24 years the certified race varied with the cause of death, as described for homicide in the United States {cite('noymer2011')}. The reference for these "
        f"cohorts is the newborn's recorded colour, and the censuses show the same cohorts moving away from White: of those born in 2000 to 2004, {pct(cb[2000]['branca'])} "
        f"were recorded as White at birth and {pct(coh[(2000, 2022)]['branca'])} declared White in 2022, a relative fall of {pct(lost)}, in line with the reclassification "
        f"described between earlier censuses {cite('miranda2015')}. The proportion of natural deaths of people recorded as White at birth that were certified Brown "
        f"({ci(ks['Branca>Parda'])}) is of that order; the proportion for assault ({ci(ka['Branca>Parda'])}) is above it. Two explanations of the difference between causes "
        "cannot be separated. The certifier of a violent death may assign a darker category. Or, among people recorded as White at birth, those who later declare themselves "
        "Brown may be more exposed to violence, and the certificate would then agree with what they would have declared. The three readings of race for the same women show "
        "that the certified race follows the race recorded by the hospital more closely than the declared one, which is compatible with a classification made by observers; "
        "those figures have no interval and concern women who had given birth and died in hospital.")
para(d, f"Limitations. (1) The deceased is among the candidates only if the family did not move municipality ({pct(c14_all['found'])} of deaths at 1 to 4 years, "
        f"{pct(ks['found'])} to {pct(ka['found'])} at 15 to 24 years). The estimates describe those who stayed; the direction of any difference from those who moved is "
        "unknown. (2) The rate ratios assume that the proportion found does not differ by race; if families of one race move more, that race's deaths are undercounted and "
        "its ratio is biased downward. (3) The estimator was validated in infants only, and failed in municipalities of 25,600 or more births per year; national estimates "
        "include those municipalities, and the sensitivity analysis without them gave ratios within the intervals of the main analysis. (4) The standard errors assume "
        "Poisson counts and ignore the scaling of the control; the jackknife error was larger for Indigenous children and was the one reported. (5) Denominators are births "
        "of the cohort and not survivors, which lowers all rates by the cumulative mortality before the age studied; a race with higher earlier mortality has its ratio "
        "biased downward, by less than its cumulative mortality. (6) For people born from 2000 to 2010 the birth-record race is the newborn's recorded colour and not a "
        "declaration, and the result by cause of death rests on municipalities with fewer than 1,600 births per year, a bound chosen after inspecting the estimates. "
        f"(7) Deaths of 2023 and 2024 may be revised in later releases of the files. (8) The mother's race was available from 2012, so no cohort with it had reached age 15; "
        f"it will from {2012 + 15}.")
para(d, "Implications. Mortality by race in childhood computed from certified race over a population classified by declaration does not measure the same contrast as "
        "mortality by the mother's race. Where birth and death records share a birth date, a sex and a municipality, deaths by birth-record race can be estimated without "
        "individual linkage. Comparisons of deaths from external causes by certified race at young ages combine the classification with the cause of death.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The two classifications disagreed from infancy to age 24, the rate ratios between White and Brown children had "
        "opposite directions under them, and at 15 to 24 years the certified race of people recorded as White at birth differed by cause of death. The design does not "
        "identify whether the disagreement is an error of the certificate or a difference between two valid classifications.")

d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")

# ---------------------------------------------------------------- the supplement
s = new_doc()
para(s, "Supplementary material - " + TITLE, bold=True)
s.add_heading("Supplementary Text S1 - The candidate estimator and its control", level=2)
para(s, "Let G be a group of deaths. For a death i, let C_i be the set of live births with the birth date, sex and municipality of residence of i. If the family did not "
        "move, exactly one element of C_i is the deceased; the remaining elements, and all elements when the family moved, are births that agree by chance. Write N(j, k) "
        "for the number of deaths in G with birth-record race j and certified race k, and t for the probability that the deceased is in C_i. The expected number of "
        "candidates with race j among deaths certified k is t N(j, k) + E(j, k), where E(j, k) is the expected number of chance candidates.")
para(s, "E(j, k) depends on how many children were born on the deceased's birth date in the municipality. That is not the number of an arbitrary day: a day on which more "
        "children were born contributes more people and therefore more deaths, so the birth date of a death is a size-biased draw from the days of the year. A control that "
        "moves the birth date by whole weeks samples other days and undercounts E; with it the estimated t exceeded 1 in municipalities with 6,400 or more births per year. "
        "The births of the other sex on the same day in the same municipality share the day, cannot contain the deceased and have the racial composition of that day's "
        "births; multiplied by the ratio of births of the two sexes in the municipality and year, their count estimates E(j, k). With this control the estimated t for "
        f"infants was {pct(v_all['found'])} overall, {pct(v_big['found'])} with 6,400 to 25,599 births per year and {pct(v_top['found'])} with 25,600 or more, where the "
        "estimator was judged to fail (Supplementary Table S2).")
para(s, "The estimator of t N(j, k) is the difference of the two counts. Its variance was approximated by the sum of the candidate count and the control count, which "
        "ignores the scaling factor of the control (close to 1) and the variance of the denominator of a proportion. A twin of the same sex is a candidate and a twin of "
        "the other sex is in the control; both share the mother's race with the deceased.")
s.add_heading("Supplementary Text S2 - Three readings of race for the same woman", level=2)
para(s, f"Deaths of women aged 15 to 49 years in 2015 to 2022 in municipalities with fewer than 2,000 mothers on the birth records ({n0(T3['women_deaths'])} deaths) were "
        f"related to the birth records on which they were the mother, by birth date and municipality ({n0(T3['linked'])} pairs). These deaths were then related to the "
        "hospital admission that ended in death, through a probabilistic linkage of admissions in the Hospital Information System to death certificates on birth date, sex, "
        f"date of death and hospital. {n0(T3['with_three'])} women had the three races recorded; the mean estimated proportion of false pairs among them was "
        f"{pct(T3['false_share'])}. False pairs were removed in expectation, taking the declared race of a false pair to follow the racial composition of mothers in the "
        f"region. For comparison, among {n0(R['delivery']['pairs'])} delivery admissions of 2022 related to the birth record by a probabilistic linkage, the hospital recorded "
        f"the declared race for {f2(R['delivery']['hospital_as_declared']['Branca'])} of White, {f2(R['delivery']['hospital_as_declared']['Parda'])} of Brown and "
        f"{f2(R['delivery']['hospital_as_declared']['Preta'])} of Black mothers.")
table(s, "Supplementary Table S1 - Live births, proportion with the mother's race field filled and share of each race on the birth record, by year, Brazil, 2000-2024",
      ["Year", "Live births", "Mother's race filled, %", "White, %", "Brown, %", "Black, %"],
      [[r["year"], n0(r["births"]), pct(r["mother_field"]), pct(r["branca"]), pct(r["parda"]), pct(r["preta"])] for r in R["form"]])
rows = []
for label, block in (("Under 1 year", V["rows"]), ("1-4 years", C14["by_size"]), ("5-9 years", C59["by_size"])):
    for r in block:
        rows.append([label, r["size"], n0(r["deaths"]), f2(r["candidates_per_death"]), pct(r["found"])] + [ci(r["stays"][k]) if k in r["stays"] else "-" for k in ("Branca", "Parda", "Preta", "Indigena")])
table(s, "Supplementary Table S2 - Proportion of deaths certified with the race on the birth record, by age and live births per year in the municipality of residence, "
         "all estimates as obtained, Brazil, infant deaths of 2021-2022 and deaths at 1-9 years of 2013-2024",
      ["Age", "Live births per year", "Deaths", "Candidates per death", "Deceased found, %", "White (95%CI)", "Brown (95%CI)", "Black (95%CI)", "Indigenous (95%CI)"], rows,
      ["CI: confidence interval. Estimates are differences of counts and can leave the interval 0 to 1."])
rows = []
for label, block in (("1-4 years", C14), ("5-9 years", C59)):
    for k in ("Branca", "Preta", "Indigena"):
        e = block["rate_ratio"][k]
        rows.append([label, NAMES[k], ci(e, log=True), f2(e["se_counts"]), f2(e["se_jackknife"]), f"{f2(e['loo_min'])}-{f2(e['loo_max'])}",
                     ci(block["rate_ratio_without_large"][k], log=True), cert(e)])
table(s, "Supplementary Table S3 - Mortality rate ratios by the mother's race on the birth record (reference: Brown): standard errors, range leaving out one state, "
         "ratios without municipalities of 25,600 or more births per year, and ratios by certified race, Brazil, 2013-2024",
      ["Age", "Race", "Rate ratio (95%CI)", "Standard error, counts", "Standard error, jackknife", "Range leaving out one state", "Without the largest municipalities (95%CI)",
       "By certified race (95%CI)"], rows, ["CI: confidence interval."])
rows = []
for k in kinds:
    for label, key in (("under 1,600 births, both sexes", "small"), ("under 1,600 births, men", "small_men"), ("under 1,600 births, women", "small_women"), ("1,600 births or more", "large")):
        e = K[k][key]
        rows.append([klabel[k], label, n0(e["deaths"]), cell_ci(e["Branca stays"]), cell_ci(e["Parda stays"]), cell_ci(e["Preta stays"])])
table(s, f"Supplementary Table S4 - Proportion of deaths at 15-24 years certified with the colour recorded at birth, by cause of death, sex and size of municipality, Brazil, {YOUTH}",
      ["Cause of death", "Group", "Deaths", "White certified White (95%CI)", "Brown certified Brown (95%CI)", "Black certified Black (95%CI)"], rows,
      ["CI: confidence interval. Not estimable: estimate outside 0 to 1 or standard error above 0.15."])
rows = []
for c0 in sorted({k[0] for k in coh}):
    for race, key in (("White", "branca"), ("Brown", "parda"), ("Black", "preta")):
        rows.append([f"{c0}-{c0 + 4}", race, pct(cb[c0][key]) if c0 in cb else "-"] + [pct(coh[(c0, y)][key]) if (c0, y) in coh else "-" for y in (2000, 2010, 2022)])
table(s, "Supplementary Table S5 - Share of each race in five-year birth cohorts born from 1940 to 2009, on the birth record and at the censuses of 2000, 2010 and 2022, Brazil",
      ["Birth cohort", "Race", "Birth record, %", "Census 2000, %", "Census 2010, %", "Census 2022, %"], rows)
rows = [[NAMES[j], f2(T3["hospital_as_declared"][j]), f2(T3["certificate_as_declared"][j])] + [f2(T3["certificate_given_hospital"][j][h]) for h in ("Branca", "Parda", "Preta")]
        for j in ("Branca", "Parda", "Preta")]
table(s, f"Supplementary Table S6 - Race recorded by the hospital and on the death certificate according to the race declared as a mother, women who died in hospital at "
         f"15-49 years, Brazil, 2015-2022 (n={n0(T3['with_three'])})",
      ["Declared race", "Hospital records the declared race", "Certificate records the declared race", "Certified as declared when the hospital recorded White",
       "When the hospital recorded Brown", "When the hospital recorded Black"], rows, ["Proportions after removal of the expected false pairs; no interval was computed."])
s.save(OUT / "supplement.docx")

words = sum(len(p.text.split()) for p in d.paragraphs)
print("manuscript paragraphs", len(d.paragraphs), "words (all)", words, "references", len(order), "tables 4, figures 3; supplement tables 6")
(OUT / "build_report.json").write_text(json.dumps({"words_total": words, "references": len(order), "reference_keys": order}, indent=1), encoding="utf-8")
