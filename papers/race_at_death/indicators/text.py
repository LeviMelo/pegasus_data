# The front of the indicators paper: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py indicators`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
DESIGN = "cross-sectional study of routinely collected birth and death records, linked where possible"
OBJECTIVE = ("to measure how the White to Brown and Black to Brown ratios of infant and child mortality in Brazil change with the classification of the deaths "
             "and of the denominators, nationally and in each of 510 immediate regions")
I, IR, CH = R["infants"], R["infant_rates"], R["children"]
C14, C59 = CH["1-4"], CH["5-9"]
CONV, REB = C14["conventional_2016_2024"], R["reboucas"]
LR = IR["ratio_mother_linkage"]
MS, RA = SP["misstated"], SP["ratio"]
import json as _json  # noqa: E402
D2 = _json.loads((HERE / "results" / "indicators2.json").read_text(encoding="utf-8"))
N2 = D2["national"]


def jr(cellname, r):
    """A ratio of the 2 x 2 with its delete-one-state jackknife interval (log scale)."""
    return ci(N2[cellname][r], log=True)

MSB = MS["by_composition"]


C14W, C59W = C14["without_large"]["rates"], C59["without_large"]["rates"]   # after infancy: municipalities under 25,600 births a year
RML = IR["rate_mother_linkage"]
CBP = I["cluster_bootstrap"]
VAL = {v["size"]: v for v in R["validation"]}


def rr(rates, k="Branca"):
    return ci(rates["ratio_mother"][k], log=True)


def rc(rates, k="Branca"):
    return ci(rates["ratio_certificate"][k], log=True)


# the claims of the text, held by the results
assert LR["Branca"]["est"] < 1 < IR["ratio_certificate"]["Branca"]["est"], "infants: the White to Brown ratios no longer have opposite directions"
assert LR["Preta"]["est"] > 1 > IR["ratio_certificate"]["Preta"]["est"], "infants: the Black to Brown ratios no longer have opposite directions"
for blk in (C14W, C59W, C14["rates"], C59["rates"]):
    assert blk["ratio_mother"]["Branca"]["est"] < 1 < blk["ratio_certificate"]["Branca"]["est"], "children: the ratios no longer have opposite directions"
assert C14["ratio_household"]["Branca"] < CONV["ratio_certificate_population"] < 1, "1-4 years: the account no longer lies between the family's ratio and none"
assert abs(IR["ratio_certificate_population"] - LR["Branca"]["est"]) < 0.05, "infants: the census denominator no longer keeps the mother's-race ratio"
lo_ = LR["Branca"]["est"] * math.exp(-1.96 * LR["Branca"]["se"] / LR["Branca"]["est"])
hi_ = LR["Branca"]["est"] * math.exp(1.96 * LR["Branca"]["se"] / LR["Branca"]["est"])
assert lo_ < REB["under 1"]["ratio"] < hi_, "the linked cohort's infant ratio is outside the linkage's interval"
assert abs(RML["Branca"] / RML["Parda"] - LR["Branca"]["est"]) < 1e-6, "linked rates and ratio disagree"
assert MS["reversed"] > 0.6 * MS["regions"] and MS["reversed_credible"] < 0.3 * MS["regions"], "the regional counts changed"
assert MS["certificate_above_1_credibly"] > 2 * MS["mother_below_1_credibly"], "the regional asymmetry changed"
assert MSB["<10%"]["ratio_of_ratios"] > max(MSB["10-29%"]["ratio_of_ratios"], MSB["30-59%"]["ratio_of_ratios"], MSB[">=60%"]["ratio_of_ratios"])
ls_ = I["linked_share"]["by_certified"]
STRATA = list(D2["by_year"].values()) + list(D2["by_period"].values()) + [v for k, v in D2["by_cause"].items() if k != "other"]
assert all(x["mother_over_mother"]["white"] < 1 < x["certified_over_mother"]["white"] for x in STRATA), "the reversal no longer holds in every stratum"
assert N2["certified_over_child"]["white"]["est"] < 1 and N2["certified_over_child"]["black"]["est"] < 1 < N2["mother_over_mother"]["black"]["est"], "2 x 2 changed"
assert D2["waterfall"][1]["ratios"]["white"] > 1.3 > D2["waterfall"][2]["ratios"]["white"] > 1, "the waterfall's first steps changed"
assert D2["absolute"]["mother"]["brown"]["excess_deaths"] > 0 > D2["absolute"]["certified"]["brown"]["excess_deaths"], "absolute measures changed"
assert max(ls_[k] for k in ("Branca", "Parda", "Preta")) - min(ls_[k] for k in ("Branca", "Parda", "Preta")) < 0.02, "linkage differs by certified race"
CRED = "a 95% credible interval (posterior mean plus or minus 1.96 posterior standard deviations) that excludes 1"

d = new_doc()
TITLE = ("Two races in one rate: the child's on the death certificate, the mother's on the birth record, and racial inequality in infant mortality in "
         "Brazil, 2013-2023")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}. Infant deaths of 2013-2023 were linked one-to-one to their birth records. Rate ratios were computed with "
        "the numerator classified by the mother's race (linked deaths) or by the certificate, and the denominator by the mother's race (births) or by the "
        "child's race as households classify infants of mothers of each race (census flows), with delete-one-state jackknife intervals; the change from one to "
        "another was decomposed flow by flow, by age at death, cause, year and region.")
para(d, f"Results: Infant mortality was {f1(RML['Branca'])} per 1,000 live births for children of White mothers and {f1(RML['Parda'])} for children of Brown "
        f"mothers (White to Brown {jr('mother_over_mother', 'white')}; Black to Brown {jr('mother_over_mother', 'black')}). Certified deaths over births by the "
        f"mother's race, the usual way the rate is computed, gave {jr('certified_over_mother', 'white')} and {jr('certified_over_mother', 'black')}; certified "
        f"deaths over births reclassified as households classify infants gave {jr('certified_over_child', 'white')} and {jr('certified_over_child', 'black')}. "
        "The reversal came almost entirely from Brown mothers' infants certified White, partly offset by White mothers' infants certified Brown, and held in "
        f"every year, age at death and cause. Counted by the mother's race, {n0(D2['absolute']['mother']['brown']['excess_deaths'])} infant deaths of Brown "
        "mothers' children exceeded the White mothers' rate in 2013-2023; by the usual indicator there was a deficit.")
para(d, "Conclusion: The usual infant mortality rate by race divides deaths classified by the child's race by births classified by the mother's, and the "
        "mismatch reverses the White to Brown inequality; classified consistently, by the mother or by the child, the children of Brown mothers die more often. "
        "Black infants' excess relative to Brown persisted by the mother's race and fell below parity on the certificate even over the child's births.")
para(d, "Keywords: Infant Mortality; Child Mortality; Race Factors; Health Status Indicators; Vital Statistics; Medical Record Linkage; Brazil.")

d.add_heading("Introduction", level=1)
para(d, f"Racial inequality in child health in Brazil is measured through mortality rates by race {cite('cardoso2005', 'caldas2017')}. The numerator is the race on the death certificate, which the Ministry of Health "
        f"instructs be asked of the informant and which in practice the certifier or hospital staff often enter {cite('manual_do2022', 'travassos2004')}; the denominator is the "
        f"race on the live birth record, the mother's declaration of her own race since 2011 {cite('manual_dn2011')} and in nearly all records from 2012, or the race households report in the census. When the "
        f"two disagree, the rate is a ratio of two classifications. Comparisons of infant mortality by race between sources gave differences in opposite directions "
        f"{cite('cardoso2005', 'caldas2017')}, and in the United States the classification of infants at birth and at death altered the rates of smaller groups "
        f"{cite('hahn1992')}, while certificates misclassify American Indian deaths {cite('arias2016')}. A linked cohort of 19.5 million Brazilian births classified by the "
        f"mother's race found higher mortality before age 5 among children of Brown, Black and Indigenous mothers than among children of White mothers {cite('reboucas2022')}.")
para(d, f"This study aimed {OBJECTIVE}.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the RECORD statement {cite('benchimol2015')}. Deaths came from the Mortality Information System (SIM) "
        f"and live births from the Live Birth Information System (SINASC), public files of the Ministry of Health {cite('datasus')}, deaths of 2013-2024 and births of "
        f"2012-2023; the family's classification from the sample of the 2010 Census {cite('ibge_microdata2010')}; immediate regions from IBGE {cite('ibge_regions2017')}.")
para(d, f"The mother's race for each death. Infant deaths of 2013-2023 ({n0(I['certificates'])}) were linked to their birth records by probabilistic linkage "
        f"{cite('fellegi1969')} on birth date, sex, residence, birth weight and mother's age (Figure 1); {pct(I['linked'] / I['certificates'])} were linked, with an estimated "
        f"{min(v['fdr_percent'] for v in I['link_quality'].values()):.2f}-{max(v['fdr_percent'] for v in I['link_quality'].values()):.2f}% of false links a year, and the linked "
        f"share was {pct(ls_['Branca'])}, {pct(ls_['Parda'])} and {pct(ls_['Preta'])} for deaths certified White, Brown and Black ({pct(ls_['Indigena'])} for Indigenous). "
        "Linked deaths with the mother's race were scaled to every infant certificate, which assumes that unlinked deaths are distributed by the mother's race as linked "
        "ones; this cannot be checked, since the mother's race of an unlinked death is unknown. Deaths at 1-9 years carry no birth weight or mother's age, and were "
        "classified by the mother's race with a candidate estimator: the births of the same birth date, sex and municipality, less the births of the other sex on the same "
        f"day as a control for chance agreement {cite('lipsitch2010')}, cross-classified by the race on the birth record and on the certificate (Supplementary Text S1). In "
        "infants, where the linkage gives the answer, the estimator reproduced the linkage's proportion of White mothers' infants certified White in municipalities with "
        f"fewer than 25,600 births a year ({f2(cell(VAL['1,600-6,399']['candidates'], 'Branca', 'Branca')['est'])} against "
        f"{f2(cell(VAL['1,600-6,399']['linkage'], 'Branca', 'Branca')['est'])} at 1,600-6,399 births) but not above "
        f"({f2(cell(VAL['>=25,600']['candidates'], 'Branca', 'Branca')['est'])} against {f2(cell(VAL['>=25,600']['linkage'], 'Branca', 'Branca')['est'])}); after infancy the "
        "main estimates are therefore restricted to the smaller municipalities, and all municipalities are a sensitivity analysis.")
figure(d, "flow_infants", "Figure 1 - Infant deaths linked to their birth records, with the number of records at each step, and the census reference of how "
                          "households classify infants, Brazil, 2013-2023",
       ["SIM: Mortality Information System. SINASC: Live Birth Information System. The census gives the proportions in which households classify infants of "
        "mothers of each race, which reclassify births by the child's race (Methods)."])
para(d, "Rates. Infant mortality: deaths of 2013-2023 over live births of the same years, per 1,000. At 1-4 and 5-9 years: deaths of 2013-2024 of children born in "
        "2012-2023 over the person-years those birth cohorts contribute at each age, per 100,000; the 5-9 year rates therefore cover the cohorts born in 2012-2019. Births "
        "with no race or of Yellow (Asian) mothers enter no race's rate.")
para(d, "Two classifications in each term. The numerator was classified by the mother's race (linked deaths scaled to all certificates by certified race, "
        "since the linked share differs by race) or by the race on the certificate, which concerns the child. The denominator was classified by the mother's "
        "race (live births of the same years) or by the child's race, obtained by passing the births of each mother's race through the proportions in which "
        "households classify children under one year of mothers of that race in the 2010 Census, nationally and by region. The four combinations form a 2 x 2: "
        "consistent by the mother, consistent by the child (certified deaths over the child's births), and the two mixed ones, of which certified deaths over "
        "births by the mother's race is the usual way infant mortality by race is computed from the two systems. A modelled census-based population and the "
        "family's classification applied to deaths and births are reported in the supplement.")
para(d, "Decomposition. Starting from deaths and births by the mother's race, the certificate's flows were switched on one at a time (Brown mothers' infants "
        "certified White, White mothers' certified Brown, Black mothers' certified Brown, Brown mothers' certified Black, Indigenous mothers' certified Brown), "
        "then the deaths with no race on the certificate, then the denominator by the child's race. The 2 x 2 was repeated by age at death (neonatal 0-27 days, "
        "post-neonatal), cause group (perinatal, congenital, infectious or respiratory, external, ill-defined, other), year of death, region, and standardised "
        "to the regions (Mantel-Haenszel). Absolute measures: rate differences and the deaths above the White mothers' rate.")
para(d, f"Regions. For each of the 510 immediate regions, deaths of White and Brown mothers' infants (linked deaths scaled to all deaths of the region) and certified White "
        f"and Brown infant deaths were modelled as Poisson counts with the births by the mother's race as exposure, a fixed White term, and Besag-York-Mollié (BYM2) "
        f"effects {cite('besag1991', 'riebler2016')} for the region and for the region's White to Brown contrast, on a graph joining regions whose municipalities share a "
        "border, with penalised-complexity priors; fitted by integrated nested Laplace approximation (Gaussian approximation, empirical Bayes) "
        f"{cite('rue2009', 'lindgren2015')}. Each region's log ratio is the fixed White term plus the region's contrast effect; a ratio is called credible when it has "
        f"{CRED}. The ratio of the certified to the mother's-race rate ratio measures how much the certificate changes the inequality relative to the mother's race.")
para(d, "Analyses. The study is descriptive. The 2 x 2 for infants is the main result; the strata, the ratios after infancy and the regional ratios are "
        "exploratory.")
para(d, "Uncertainty and sensitivity. National ratios of the 2 x 2 carry delete-one-state jackknife intervals, which reflect the variation between states but not the error of the "
        "linkage or of the population account, and the census-based and family's ratios carry no interval. Sensitivity: deaths with no race on "
        "the certificate given the mother's race; municipalities of 25,600 or more births included; the share of the deceased found among the candidates differing by up to 10 "
        "points between White and Brown mothers. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council no review was required.")
