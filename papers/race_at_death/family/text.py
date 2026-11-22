# The front of paper 4, the family: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py family`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
import json as _json

FA = _json.loads((HERE / "results" / "family.json").read_text(encoding="utf-8"))
DESIGN = "cross-sectional study of two national census samples"
OBJECTIVE = ("to describe how Brazilian households classify children by race relative to the mother, by the mother's partner, her schooling, the "
             "child's age, the place and who answered, in the Censuses of 2010 and 2022")
MX, BY, MD, INF, CO, PM = FA["matrix"], FA["by"], FA["models"], FA["informant"], FA["coresidence"], FA["partner_mix"]
CEN, COH, CF = R["census"], R["cohorts"], R["cohort_falls"]


def v(y, m, c, a="0-4"):
    return MX[str(y)][f"{m}|{a}"][c]


def dci(x, d=2):
    """A design-based proportion with its 95% interval."""
    return f"{x['est']:.{d}f} (95%CI {x['est'] - 1.96 * x['se']:.{d}f}; {x['est'] + 1.96 * x['se']:.{d}f})"


def bp(y, m, outc, dim, lev):
    return BY[str(y)][f"{m}|{outc}|{dim}|{lev}"]


def orf(key, term):
    t = MD[key][term]
    return f"{t['or']:.2f} (95%CI {t['lo']:.2f}; {t['hi']:.2f})"


def chg(a, b):
    """The difference of two independent design-based proportions with its 95% interval."""
    d_, s_ = b["est"] - a["est"], math.hypot(a["se"], b["se"])
    return f"{d_:+.3f} (95%CI {d_ - 1.96 * s_:+.3f}; {d_ + 1.96 * s_:+.3f})"


# the claims of the text, held by the results
BWW = (bp(2010, "brown", "is_white", "partner", "white"), bp(2022, "brown", "is_white", "partner", "white"))
assert BWW[1]["est"] - BWW[0]["est"] > 3 * math.hypot(BWW[0]["se"], BWW[1]["se"]), "Brown mothers with White partners: the 2022 rise is gone"
assert MD["brown|is_white"]["partner[T.white]"]["lo"] > 5, "the White partner no longer dominates"
assert abs(v(2022, "black", "black")["est"] - v(2010, "black", "black")["est"]) < 0.02, "Black mothers' children 0-4 reported Black changed"
assert v(2022, "black", "white")["est"] - v(2010, "black", "white")["est"] > 3 * math.hypot(v(2022, "black", "white")["se"], v(2010, "black", "white")["se"])
assert bp(2022, "black", "is_black", "age", "10-14")["est"] > bp(2010, "black", "is_black", "age", "0-4")["est"] + 0.03, "the same cohorts no longer darken with age"
inf_b = INF["model_same|brown"]["informant[T.other resident]"]
assert 0.9 < inf_b["lo"] and inf_b["hi"] < 1.05, "another resident now answers differently from the mother"
assert abs(FA["rule_check_2010"]["couple"]["est"] - FA["rule_check_2010"]["order"]["est"]) < 0.005, "the couple rule now differs from the mother's order number"
assert CF["white_fell"] >= CF["intervals"] - 1, "cohorts no longer leave White"

d = new_doc()
TITLE = ("The race of a child in the household: partners, schooling, age and who answers, in the Brazilian Censuses of 2010 and 2022")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}, Brazil. Children aged 0-24 of the household's couple were paired with their mothers in the sample "
        f"microdata of the 2010 Census ({n0(MX['2010']['brown|all']['white']['records'] + MX['2010']['white|all']['white']['records'] + MX['2010']['black|all']['white']['records'])} "
        f"children of White, Brown and Black mothers aged 0-9) and of the 2022 Census, by a rule both public files allow. The race reported for the child "
        "was set against the mother's, by the partner's race, the mother's schooling, the child's age, the region and, in 2022, who answered for the child; "
        "proportions and odds ratios carry design-based intervals.")
para(d, f"Results: Households reported as White {f2(v(2010, 'brown', 'white')['est'])} of Brown mothers' children aged 0-4 in 2010 and "
        f"{f2(v(2022, 'brown', 'white')['est'])} in 2022, and as Black {f2(v(2010, 'black', 'black')['est'])} and {f2(v(2022, 'black', 'black')['est'])} of Black "
        f"mothers' children. The partner decided most: Brown mothers' children aged 0-9 were reported White in {f2(BWW[0]['est'])} with a White partner in 2010 and "
        f"{f2(BWW[1]['est'])} in 2022, against {f2(bp(2022, 'brown', 'is_white', 'partner', 'brown')['est'])} with a Brown partner; Black mothers' children were "
        f"reported Black in {f2(bp(2022, 'black', 'is_black', 'partner', 'black')['est'])} with a Black partner and {f2(bp(2022, 'black', 'is_black', 'partner', 'brown')['est'])} "
        f"with a Brown one. Black mothers' children aged 0-4 reported White rose from {f2(v(2010, 'black', 'white')['est'])} to {f2(v(2022, 'black', 'white')['est'])}. "
        f"Children were reported Black more often at older ages, and the children aged 0-4 in 2010 were reported Black more often at 10-14 in 2022 "
        f"({f2(bp(2022, 'black', 'is_black', 'age', '10-14')['est'])} against {f2(bp(2010, 'black', 'is_black', 'age', '0-4')['est'])}). In 2022 the classification "
        f"hardly depended on whether the mother or another resident answered (odds ratio of the mother's race {inf_b['or']:.2f}). Birth cohorts were reported "
        f"White less often at each later census in {CF['white_fell']} of {CF['intervals']} census intervals.")
para(d, "Conclusion: A Brazilian household classifies a child as much by the partner as by the mother, and darker as the child grows; mixed unions with White "
        "men whitened children more in 2022 than in 2010, while the classification of Black mothers' young children did not darken. Statistics that take a "
        "child's race from the household rather than from the mother inherit these rules.")
para(d, "Keywords: Racial Groups; Family Characteristics; Censuses; Child; Brazil.")

d.add_heading("Introduction", level=1)
para(d, "In Brazil a child's race is reported by someone else for most of childhood: by the household in the census, by staff on health records. Children "
        f"cannot declare it, and parents of different colour must choose. Highly educated non-White parents more often classify their children as White, in "
        f"part because they more often have White partners {cite('schwartzman2007')}. The same person is classified differently by different observers and "
        f"methods {cite('telles2002', 'muniz2017')}, and census cohorts move between categories over time {cite('carvalho2004')}, in recent decades toward "
        f"Brown and Black {cite('marteleto2012', 'freemannc2024')}. How households report the race of children relative to their mothers sets the reference "
        "that health statistics are compared with, and its rules decide how much of the children's racial distribution is the mothers', the fathers' or the "
        "households'.")
para(d, "Two national samples now allow the question to be asked twice. The 2022 Census sample microdata, released in 2026, record who answered for each "
        "person, which the 2010 file did not, and both identify the household's couple and its children. We know of no study that compared how households "
        f"classify children relative to the mother in two censuses. This study aimed {OBJECTIVE}.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the STROBE statement. The sample microdata of the 2010 Census {cite('ibge_microdata2010')} "
        f"and the public-access sample microdata of the 2022 Census {cite('ibge_microdata2022')} were read for every state. In both, each person carries the race "
        "reported for them (White, Black, Yellow, Brown or Indigenous), sex, age (single years in 2010, five-year groups in 2022), the relationship to the person "
        "responsible for the household and, from age 15, the level of instruction in categories the two censuses share.")
para(d, "Mother-child pairs. The 2010 file identifies each person's co-resident mother by her order number; the 2022 public file says only whether the "
        "mother or stepmother lives in the household. Pairs were therefore made in both censuses by one rule: a child of the household's couple (a child of "
        "both, of the responsible person only when she is the woman of the couple, or a stepchild of the responsible person when the woman is the spouse), "
        "with the mother co-resident, paired with the couple's woman; the couple's man is the partner. In 2010 this rule kept "
        f"{pct(FA['rule_check_2010']['couple_share_of_order'], 0)} of the pairs the mother's order number identifies, and Brown mothers' children aged 0-9 were "
        f"reported White in {f2(FA['rule_check_2010']['couple']['est'])} by the rule and {f2(FA['rule_check_2010']['order']['est'])} by the order number. "
        "Children are those aged 0-24; the analyses of the mother's race concern children aged 0-4 or 0-9, most of whom live with their mother.")
para(d, "Who answered. In 2022 the questionnaire records who gave each person's information: the person, another resident (identified by order number) or a "
        "non-resident. A child's information was classed as given by the mother when the informant's order number was hers.")
para(d, "Cohorts. The share of each five-year birth cohort reported White at the Censuses of 2000, 2010 and 2022 came from the census counts by "
        f"single year of age and race {cite('ibge_sidra2010')}, as held in a population account that takes the census population as given in census "
        "years (Supplementary Text S1).")
para(d, "Analysis. Proportions are weighted; their standard errors are design-based (Taylor linearisation, strata the states, primary units the "
        "households; the 2022 public file carries no weighting area, and with 2010's weighting areas as strata the standard errors were unchanged). The "
        "reporting of Brown mothers' children aged 0-9 as White, and of Black mothers' as Black, was modelled by weighted logistic regression on both "
        "censuses together, with the census, the partner's race, the mother's instruction, the child's age and sex, the mother's age and the region, with "
        "standard errors clustered by household; a census by partner interaction tested whether the change differed by partner. In 2022, agreement of the "
        "child's race with the mother's was modelled on who answered, with the same terms. Analyses used Python 3.11; the code accompanies the article. "
        "Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council no review was required.")
