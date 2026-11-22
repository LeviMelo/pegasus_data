# The front of paper 4, the family: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py family`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
import json as _json

FA = _json.loads((HERE / "results" / "family.json").read_text(encoding="utf-8"))
DESIGN = "cross-sectional study of two national census samples"
OBJECTIVE = ("to describe how Brazilian households report the race of children relative to the mother, by the mother's partner and whether he is the "
             "child's father, the siblings, the mother's schooling, the child's age, the region and who answered, in the Censuses of 2010 and 2022")
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
F_W = (rel(2010, "brown", "is_white", FATHER, "white"), rel(2022, "brown", "is_white", FATHER, "white"))
F_B = (rel(2010, "brown", "is_white", FATHER, "brown"), rel(2022, "brown", "is_white", FATHER, "brown"))
S_W = [rel(y, "brown", "is_white", r, "white")["est"] for y in (2010, 2022) for r in (STEP5, STEP6)]
assert min(F_W[0]["est"] - F_B[0]["est"], F_W[1]["est"] - F_B[1]["est"]) > 1.8 * max(
    rel(y, "brown", "is_white", r, "white")["est"] - rel(y, "brown", "is_white", r, "brown")["est"] for y in (2010, 2022) for r in (STEP5, STEP6)), \
    "the father no longer carries most of the partner's effect"
assert F_W[1]["est"] - F_W[0]["est"] > 3 * math.hypot(F_W[0]["se"], F_W[1]["se"]), "White fathers: the 2022 rise is gone"
assert min(SIB[f"{y}|brown|white"]["discordant"] for y in (2010, 2022)) > 2 * max(SIB[f"{y}|brown|brown"]["discordant"] for y in (2010, 2022)), \
    "siblings of mixed couples no longer differ more"
assert IN2["brown|white|partner"]["white"]["est"] - IN2["brown|white|mother"]["white"]["est"] > 0.04, "the White partner's answer no longer whitens"
assert IN2["black|white|partner"]["white"]["est"] > IN2["black|white|mother"]["white"]["est"] + 0.04
assert IN2["black|black|partner"]["black"]["est"] > IN2["black|black|mother"]["black"]["est"]
assert IN2["black|brown|partner"]["black"]["est"] < IN2["black|brown|mother"]["black"]["est"]
assert DR["brown|is_white"]["2022_at_2010_mothers"] < DR["brown|is_white"]["2010"] < DR["brown|is_white"]["2022"], "the schooling standardisation no longer reverses"
assert abs(v(2022, "black", "black")["est"] - v(2010, "black", "black")["est"]) < 0.02, "Black mothers' children 0-4 reported Black changed"
assert v(2022, "black", "white")["est"] - v(2010, "black", "white")["est"] > 3 * math.hypot(v(2022, "black", "white")["se"], v(2010, "black", "white")["se"])
assert COV["order_agrees"] > 0.99 and abs(COV["black"]["couple"]["est"] - COV["black"]["order"]["est"]) < 0.01
assert CF["white_fell"] >= CF["intervals"] - 1, "cohorts no longer leave White"

d = new_doc()
TITLE = ("The race of a child in the household: fathers, stepfathers, siblings and who answers, in the Brazilian Censuses of 2010 and 2022")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}, Brazil. Children of the household's couple living with their mother were paired with her in the sample "
        f"microdata of the 2010 Census ({n0(MX['2010']['brown|all']['white']['records'] + MX['2010']['white|all']['white']['records'] + MX['2010']['black|all']['white']['records'])} "
        f"children of White, Brown and Black mothers aged 0-9) and the public-access sample of the 2022 Census, by a rule both files allow. The race reported "
        "for the child was set against the mother's, by the partner's race and whether he was the child's father or a stepfather, between siblings, by the "
        "mother's schooling, the child's age, the region and, in 2022, who answered for the child; proportions and odds ratios carry design-based intervals.")
para(d, f"Results: Households reported as White {f2(v(2010, 'brown', 'white')['est'])} of Brown mothers' children aged 0-4 in 2010 and "
        f"{f2(v(2022, 'brown', 'white')['est'])} in 2022, and as Black {f2(v(2010, 'black', 'black')['est'])} and {f2(v(2022, 'black', 'black')['est'])} of Black "
        f"mothers' children. A Brown mother's child aged 0-9 was reported White in {f2(F_W[0]['est'])} (2010) and {f2(F_W[1]['est'])} (2022) when the father was "
        f"White, against {f2(F_B[0]['est'])} and {f2(F_B[1]['est'])} when he was Brown, and in {min(S_W):.2f}-{max(S_W):.2f} when a White partner was a stepfather. "
        f"In households of a Brown mother and a White partner, {pct(SIB['2022|brown|white']['discordant'], 0)} reported their children aged 0-9 in different "
        f"races, against {pct(SIB['2022|brown|brown']['discordant'], 0)} with a Brown partner. In 2022, when the White partner answered for the child, the child "
        f"was reported White in {f2(IN2['brown|white|partner']['white']['est'])}, against {f2(IN2['brown|white|mother']['white']['est'])} when the mother "
        f"answered. The rise of White among Brown mothers' children between the censuses ({f2(DR['brown|is_white']['2010'])} to "
        f"{f2(DR['brown|is_white']['2022'])} at 0-9) became a fall ({f2(DR['brown|is_white']['2022_at_2010_mothers'])}) with the 2022 mothers given the 2010 "
        "mothers' schooling and region.")
para(d, "Conclusion: The race households report for a child follows the couple, mostly the father, differs between siblings in mixed couples and leans "
        "toward the race of whoever answers: it reads the child's descent and appearance more than it applies a household rule. Comparisons of the two "
        "censuses depend on who the mothers of each category are.")
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
        f"reported White in {f2(COV['brown']['couple']['est'])} by the rule and {f2(COV['brown']['order']['est'])} by the order number, and Black mothers' "
        f"children Black in {f2(COV['black']['couple']['est'])} and {f2(COV['black']['order']['est'])}. The rule cannot be checked in 2022. Siblings are "
        "children aged 0-9 of the same couple in the same household.")
para(d, "Who answered. In 2022 the questionnaire records who gave each person's information: the person, another resident (identified by order number) or a "
        "non-resident. A child's information was classed as given by the mother or by the partner when the informant's order number was theirs; the same was "
        "recorded for the mother's own information.")
para(d, "Cohorts. The share of each five-year birth cohort reported White at the Censuses of 2000, 2010 and 2022 came from a cohort-component population "
        "account that takes the census population by single year of age and race as given in census years (Supplementary Text S1). The cohort born in 2000 "
        "was left out of the 2000 Census, which held only its births of January to August.")
para(d, "Analysis. Proportions are weighted; their standard errors are design-based (Taylor linearisation, strata the states, primary units the "
        "households; with 2010's weighting areas as strata the standard errors were unchanged). The reporting of Brown mothers' children aged 0-9 as White, "
        "and of Black mothers' as Black, was modelled by weighted logistic regression on both censuses together, with the census, the partner's race, the "
        "mother's instruction, the child's age and sex, the mother's age and the region, with standard errors clustered by household; census by partner "
        "interactions tested whether the change differed by partner. To separate a change in reporting from a change in who the mothers of a category are, "
        "the 2022 proportions were reweighted to the 2010 mothers' distribution of instruction and region. Analyses used Python 3.11; the code accompanies the "
        "article. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council no review was required.")
figure(d, "flow_family", "Figure 1 - The two census samples and the pairing rule, Brazil, 2010 and 2022",
       ["The partner is the man of the household's couple; he is the child's father when the child is a child of both, a stepfather otherwise."])
