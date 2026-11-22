# The front of paper 4, the family: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py family`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
import json as _json

FA = _json.loads((HERE / "results" / "family.json").read_text(encoding="utf-8"))
DESIGN = "cross-sectional study of two national census samples"
OBJECTIVE = ("to describe how Brazilian households report the race of children relative to the mother and her partner, whether he is the child's father, "
             "between siblings, by who answered, by the child's age and by place, in the Censuses of 2010 and 2022")
MX, BY, MD, INF, CO, PM = FA["matrix"], FA["by"], FA["models"], FA["informant"], FA["coresidence"], FA["partner_mix"]
V2 = FA["review1"]
CEN, COH = R["census"], R["cohorts"]
FATHER, STEP5, STEP6 = "child of both (father)", "child of the mother only (stepfather)", "stepchild of the responsible man (stepfather)"


def v(y, m, c, a="0-4"):
    return MX[str(y)][f"{m}|{a}"][c]


def dci(x, d=2):
    """A design-based proportion with its 95% interval."""
    return f"{x['est']:.{d}f} (95%CI {x['est'] - 1.96 * x['se']:.{d}f}; {x['est'] + 1.96 * x['se']:.{d}f})"


def bp(y, m, outc, dim, lev):
    return BY[str(y)][f"{m}|{outc}|{dim}|{lev}"]


def rel(y, m, outc, r, p):
    return V2[f"{y}|{m}|{outc}|{r}|{p}"]


def orf(key, term):
    t = MD[key][term]
    return f"{t['or']:.2f} (95%CI {t['lo']:.2f}; {t['hi']:.2f})"


def chg(a, b):
    """The difference of two independent design-based proportions with its 95% interval."""
    d_, s_ = b["est"] - a["est"], math.hypot(a["se"], b["se"])
    return f"{d_:+.3f} (95%CI {d_ - 1.96 * s_:+.3f}; {d_ + 1.96 * s_:+.3f})"


# the cohort series without the 2000 cohort at the 2000 Census, which held only births of January-August 2000
_cb = {(c["cohort"], c["year"]): c["branca"] for c in COH if not (c["cohort"] == 2000 and c["year"] == 2000)}
_iv = [(k, a, b) for k in sorted({c for c, _ in _cb}) for a, b in ((2000, 2010), (2010, 2022)) if (k, a) in _cb and (k, b) in _cb]
CF = {"intervals": len(_iv), "white_fell": sum(_cb[(k, b)] < _cb[(k, a)] for k, a, b in _iv),
      "first": min(k for k, _, _ in _iv), "last": max(k for k, _, _ in _iv)}
IN2, SIB, DR, COV = V2["informant"], V2["siblings"], V2["drift"], V2["coverage"]
IA = MD["brown|is_white|interaction"]

# the claims of the text, held by the results
V3 = FA["review2"]
IC, FS, PAR, DB = V3["informant_cross"], V3["full_siblings"], V3["parents"], V3["drift_boot"]
F_W = (rel(2010, "brown", "is_white", FATHER, "white"), rel(2022, "brown", "is_white", FATHER, "white"))
F_B = (rel(2010, "brown", "is_white", FATHER, "brown"), rel(2022, "brown", "is_white", FATHER, "brown"))
S_W = [rel(y, "brown", "is_white", r, "white")["est"] for y in (2010, 2022) for r in (STEP5, STEP6)]
WB = (PAR["2010|white|brown"]["white"], PAR["2022|white|brown"]["white"])          # White mother, Brown father: child White
BW = (PAR["2010|brown|white"]["white"], PAR["2022|brown|white"]["white"])          # Brown mother, White father
assert min(F_W[0]["est"] - F_B[0]["est"], F_W[1]["est"] - F_B[1]["est"]) > 1.8 * max(
    rel(y, "brown", "is_white", r, "white")["est"] - rel(y, "brown", "is_white", r, "brown")["est"] for y in (2010, 2022) for r in (STEP5, STEP6)), \
    "the father no longer counts more than a stepfather"
CT = _json.loads((HERE / "results" / "category_test.json").read_text(encoding="utf-8"))
CP, CS, CG = CT["couples"], CT["by_state"], CT["0-9"]["white_births"]
for _y in ("2010", "2022"):
    assert CP[_y]["gM_minus_gF"]["lo"] > 0, "the mother's class no longer counts more than the father's"
    assert CP[_y]["aW"]["lo"] > 0 > CP[_y]["aK"]["hi"], "the pull toward White and away from Black is gone"
assert CG["PP_white"]["slope_bins"] < 0.25 * CT["certificate"]["slope_bins"], "the Brown couples' gradient with composition is no longer small"


def ex(v):
    return f"{math.exp(v['est']):.2f} (95%CI {math.exp(v['lo']):.2f}; {math.exp(v['hi']):.2f})"


PPB = CG["PP_white"]["bins"]
STW = {u: v["PP_white"]["est"] for u, v in CS["2010"].items() if u != "BR"}
assert all(PAR[f"{y}|white|black"]["white"]["est"] - PAR[f"{y}|black|white"]["white"]["est"] < 0.05 for y in (2010, 2022))
assert F_W[1]["est"] - F_W[0]["est"] > 3 * math.hypot(F_W[0]["se"], F_W[1]["se"]), "White fathers: the 2022 rise is gone"
FSW = (FS["2010|brown|white"], FS["2022|brown|white"])
assert all(x["observed"]["est"] < 0.8 * x["independent"] for x in FS.values() if x["households"] >= 1000), "siblings no longer agree more than chance"
assert min(x["observed"]["est"] for x in FSW) > 2 * max(FS[f"{y}|brown|brown"]["observed"]["est"] for y in (2010, 2022))
PB, PS, MB_ = IC["brown|white|child by partner|mother by partner"], IC["brown|white|child by partner|mother by mother"], IC["brown|white|child by mother|mother by mother"]
assert PB["white"]["est"] - MB_["white"]["est"] > 0.06 and PS["white"]["est"] - MB_["white"]["est"] < 0.03, "the one-respondent pattern changed"
assert abs(IC["white|brown|child by partner|mother by partner"]["white"]["est"] - IC["white|brown|child by mother|mother by mother"]["white"]["est"]) < 0.02, \
    "White mothers' children now lean toward the answering partner"
assert DB["white|is_white"]["std_change"] < -0.02 and abs(DB["white|is_white"]["change"]) < 0.01, "the White-mother placebo no longer moves"
assert abs(v(2022, "black", "black")["est"] - v(2010, "black", "black")["est"]) < 0.02, "Black mothers' children 0-4 reported Black changed"
assert COV["order_agrees"] > 0.99
assert max(abs(x["change"]) for x in DB.values()) < 0.03, "a change between the censuses now exceeds three points"
assert CF["white_fell"] >= CF["intervals"] - 1, "cohorts no longer leave White"
C05 = {c["year"]: c["branca"] for c in COH if c["cohort"] == 2005}
C95 = {c["year"]: c["branca"] for c in COH if c["cohort"] == 1995}
assert C05[2010] - C05[2022] > 0.07 and C95[2000] - C95[2010] > 0.1, "the children's cohorts no longer fall most"


def pp(x, se):
    return f"{100 * x:+.1f} (95%CI {100 * (x - 1.96 * se):+.1f}; {100 * (x + 1.96 * se):+.1f})"


d = new_doc()
TITLE = ("The race of a child in the household: mothers, fathers, stepfathers, siblings and who answers, in the Brazilian Censuses of 2010 and 2022")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
CLAIM = ["pull toward White", "away from Black", "small against the death certificate"]
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}, Brazil. Children of the household's couple living with their mother were paired with her in the 2010 "
        f"Census microdata ({n0(MX['2010']['brown|all']['white']['records'] + MX['2010']['white|all']['white']['records'] + MX['2010']['black|all']['white']['records'])} "
        f"children aged 0-9) and the public-access sample of the 2022 Census. "
        "The race reported for the child was set against the mother's and the partner's, between "
        "full siblings, by who answered, by municipality and between the censuses.")
para(d, f"Results: Among children of both members of the couple, in a model of the nine couple types, taking the mother's class multiplied the odds "
        f"by {ex(CP['2010']['gM'])} and the father's by {ex(CP['2010']['gF'])} (2010), and every child leaned toward White over Brown "
        f"({ex(CP['2010']['aW'])}) and away from Black ({ex(CP['2010']['aK'])}). Households reported as White {f2(v(2010, 'brown', 'white')['est'])} of Brown mothers' children aged 0-4 in 2010 and "
        f"{f2(v(2022, 'brown', 'white')['est'])} in 2022. Full siblings of a Brown mother and a "
        f"White father were reported in different races in {pct(FSW[0]['observed']['est'], 0)} and {pct(FSW[1]['observed']['est'], 0)} of households, against "
        f"{pct(FSW[0]['independent'], 0)} and {pct(FSW[1]['independent'], 0)} if each child were classified independently. The child of two Brown parents was reported White in "
        f"{f2(PPB[0]['est'])} in the least White municipalities and {f2(PPB[-1]['est'])} in the most, a gradient under a quarter of the death certificate's.")
para(d, "Conclusion: The race households report for a child follows both parents, the mother somewhat more, with a pull toward White and away from Black. "
        "The place differences for a Brown couple's child are small against the death certificate's (under a quarter of its gradient), and little changed from 2010 to 2022.")
para(d, "Keywords: Racial Groups; Family Characteristics; Censuses; Child; Brazil.")

d.add_heading("Introduction", level=1)
para(d, "In Brazil a child's race is reported by someone else for most of childhood: by the household in the census, by staff on health records. Children "
        f"cannot declare it, and parents of different colour must choose. Highly educated non-White parents more often classify their children as White, in "
        f"part because they more often have White partners {cite('schwartzman2007')}. The same person is classified differently by different observers and "
        f"methods {cite('telles2002', 'muniz2017')}, census cohorts move between categories {cite('carvalho2004')}, and adults' own identification darkened "
        f"in the 2010s {cite('freemannc2024')}. How households report children relative to their mothers sets the reference that health statistics are "
        "compared with, and decides how much of the children's racial distribution is the mothers', the fathers' or the households'.")
para(d, "Two national samples now allow the question to be asked twice. The 2022 Census sample microdata, released in 2026, record who answered for each "
        "person, which the 2010 file did not, and both identify the household's couple and its children, and whether the couple's man is the child's father. "
        f"We found no study comparing how households report children relative to the mother in two censuses. This study aimed {OBJECTIVE}.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the STROBE statement. The sample microdata of the 2010 Census {cite('ibge_microdata2010')} "
        f"and the public-access sample microdata of the 2022 Census {cite('ibge_microdata2022')} were read for every state. In both, each person carries the race "
        "reported for them (White, Black, Yellow, Brown or Indigenous), sex, age (single years in 2010, five-year groups in 2022), the relationship to the person "
        "responsible for the household and, from age 15, the level of instruction in categories the two censuses share.")
para(d, "Mother-child pairs. The 2010 file identifies each person's co-resident mother by her order number; the 2022 public file says only whether the "
        "mother or stepmother lives in the household. Pairs were therefore made in both censuses by one rule: a child of the household's couple, with the "
        "mother co-resident, paired with the couple's woman; the couple's man is the partner (Figure 1). The relationship to the responsible person tells "
        "whether he is the father: a child of both members of the couple has its father as the partner; a child of the responsible woman only, or a stepchild of "
        "the responsible man, has a stepfather. In 2010 the order number pointed at the couple's woman for "
        f"{pct(COV['order_agrees'], 1)} of the pairs, and the rule kept {pct(COV['brown']['couple_share_of_order'], 0)} of the children aged 0-9 that the order "
        f"number pairs with a Brown mother ({pct(COV['white']['couple_share_of_order'], 0)} White, {pct(COV['black']['couple_share_of_order'], 0)} Black); the "
        "others live with a mother who is not of the household's couple, mostly in their grandparents' households. Brown mothers' children aged 0-9 were "
        f"reported White in {COV['brown']['couple']['est']:.3f} by the rule and {COV['brown']['order']['est']:.3f} by the order number, and Black mothers' "
        f"children Black in {COV['black']['couple']['est']:.3f} and {COV['black']['order']['est']:.3f}. The rule cannot be checked in 2022, where the file "
        "records only that the mother or a stepmother lives in the household. Full siblings are children aged 0-9 of the same couple in the same "
        "household, all children of both; their discordance was set against what independent classification would give, one minus the chance that "
        "every child falls in the same category when each is classified with the proportions of its mother's and father's races.")
para(d, "Who answered. In 2022 the questionnaire records who gave each person's information: the person, another resident (identified by order number) or a "
        "non-resident. A child's information was classed as given by the mother or by the partner when the informant's order number was theirs, and the "
        "same for the mother's own information, so that a child answered for by the partner can be split by whether the mother answered for herself.")
para(d, "Cohorts. The share of each five-year birth cohort reported White at the Censuses of 2000, 2010 and 2022 came from a cohort-component population "
        "account that takes the census population by single year of age and race as given in census years (Supplementary Text S1). The cohort born in 2000 "
        "was left out of the 2000 Census, which held only its births of January to August.")
para(d, "Couple types and place. For children aged 0-9 of both members of the couple, the weighted counts of the child's class (White, Brown, Black) "
        "in each of the nine couple types were fitted by a log-linear model with a term for each couple type, a term for each class of the child (the pull "
        "toward that class whatever the parents), a term for the child taking the mother's class and one for taking the father's; intervals came from 200 "
        "bootstrap replicates resampling municipalities (2010) or households (2022). By place, the shares of fixed couple types (two Brown parents, child "
        "White; two White parents, child Brown; two Black parents, child Black) were related to the municipality's share of White births in 2010, when the "
        "file carries the municipality, with errors clustered by municipality, and compared by state in 2010 and 2022.")
para(d, "Analysis. Proportions are weighted; their standard errors are design-based (Taylor linearisation, strata the states, primary units the "
        "households; with 2010's weighting areas as strata the standard errors were unchanged). The reporting of Brown mothers' children aged 0-9 as White, "
        "and of Black mothers' as Black, was modelled by weighted logistic regression on both censuses together, with the census, the partner's race, the "
        "mother's instruction, the child's age and sex, the mother's age and the region, with standard errors clustered by household; census by partner "
        "interactions tested whether the change differed by partner. The 2022 proportions were also reweighted to the 2010 mothers' distribution of "
        "instruction and region, with White mothers as a check, and the changes given intervals from 200 replicates of a household bootstrap. Analyses used Python 3.11; the code accompanies the "
        "article. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council no review was required.")
figure(d, "flow_family", "Figure 1 - The two census samples and the pairing rule, Brazil, 2010 and 2022",
       ["The partner is the man of the household's couple; he is the child's father when the child is a child of both, a stepfather otherwise."])
