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
MSB = MS["by_composition"]


def rr(block, k="Branca"):
    return ci(block["rates"]["ratio_mother"][k], log=True)


def rc(block, k="Branca"):
    return ci(block["rates"]["ratio_certificate"][k], log=True)


# the claims of the text, held by the results
assert LR["Branca"]["est"] < 1 < IR["ratio_certificate"]["Branca"]["est"], "infants: the ratios no longer have opposite directions"
for blk in (C14, C59):
    assert blk["rates"]["ratio_mother"]["Branca"]["est"] < 1 < blk["rates"]["ratio_certificate"]["Branca"]["est"], "children: the ratios no longer have opposite directions"
assert CONV["ratio_mother"]["est"] < CONV["ratio_certificate_population"] < 1 < CONV["ratio_certificate_births"]["est"], "1-4 years: the census denominator no longer compresses"
assert abs(IR["ratio_certificate_population"] - LR["Branca"]["est"]) < 0.05, "infants: the census denominator no longer keeps the mother's-race ratio"
lo_ = LR["Branca"]["est"] * math.exp(-1.96 * LR["Branca"]["se"] / LR["Branca"]["est"])
hi_ = LR["Branca"]["est"] * math.exp(1.96 * LR["Branca"]["se"] / LR["Branca"]["est"])
assert lo_ < REB["under 1"]["ratio"] < hi_, "the linked cohort's infant ratio is outside the linkage's interval"
assert MS["reversed"] > 0.6 * MS["regions"] and MSB["<10%"]["ratio_of_ratios"] > max(MSB["10-29%"]["ratio_of_ratios"], MSB["30-59%"]["ratio_of_ratios"])
assert MSB[">=60%"]["ratio_of_ratios"] > MSB["30-59%"]["ratio_of_ratios"], "no longer U-shaped"
ls_ = I["linked_share"]["by_certified"]
assert max(ls_[k] for k in ("Branca", "Parda", "Preta")) - min(ls_[k] for k in ("Branca", "Parda", "Preta")) < 0.02, "linkage differs by certified race"

d = new_doc()
TITLE = ("The same deaths, four inequalities: how the classification of deaths and denominators changes racial inequality in infant and child mortality in "
         "Brazil, nationally and in 510 regions, 2013-2024")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}. Infant deaths of 2013-2023 were linked one-to-one to their birth records (the mother's race); deaths at 1-9 years were "
        "classified by the mother's race through an estimator that relates each death to the births of the same date, sex and municipality. Rate ratios were computed "
        "with deaths and births by the mother's race, with certified deaths over births by the mother's race (the Ministry of Health's infant indicator), with certified "
        "deaths over a census-based population, and with deaths and births reclassified as families classify children in the 2010 Census; regional ratios came from "
        "Poisson models with Besag-York-Mollié effects over 510 immediate regions.")
para(d, f"Results: The White to Brown infant mortality rate ratio was {ci(LR['Branca'], log=True)} by the mother's race and {ci(IR['ratio_certificate']['Branca'], log=True)} "
        f"by certified race over the same births; over the census-based population it was {f2(IR['ratio_certificate_population'])}. At 1-4 years the ratios were {rr(C14)} "
        f"and {rc(C14)}, and {f2(CONV['ratio_certificate_population'])} over the census-based population (2016-2024). By certified race the infant ratio had the opposite "
        f"direction to the mother's-race ratio in {MS['reversed']} of {MS['regions']} immediate regions ({pct(MS['births_share_reversed'], 0)} of births), credibly in "
        f"{MS['reversed_credible']}; the change was largest where under 10% of births were White (certified over mother's-race ratio {f2(MSB['<10%']['ratio_of_ratios'])}).")
para(d, "Conclusion: Brown children's excess mortality relative to White children, present when deaths and births are classified by the mother, is reversed by the "
        "Ministry's infant indicator; over census-based denominators it is kept in infancy and compressed toward none at 1-4 years. Infant and child mortality by race "
        "should be computed from linked records or, where that is impossible, read with its denominator named and the composition of the place in mind.")
para(d, "Keywords: Infant Mortality; Child Mortality; Race Factors; Health Status Indicators; Vital Statistics; Medical Record Linkage; Brazil.")

d.add_heading("Introduction", level=1)
para(d, "Brazil monitors racial inequality in child health through mortality rates by race. The numerator is the race on the death certificate, which the Ministry of Health "
        f"instructs be asked of the informant and which in practice the certifier or hospital staff often enter {cite('manual_do2022', 'travassos2004')}; the denominator is the "
        f"race on the live birth record, the mother's declaration of her own race since 2011 {cite('manual_dn2011')}, or the race households report in the census. When the "
        f"two disagree, the rate is a ratio of two classifications. Comparisons of infant mortality by race between sources gave differences in opposite directions "
        f"{cite('cardoso2005', 'caldas2017')}, and in the United States the classification of infants at birth and at death altered the rates of smaller groups "
        f"{cite('hahn1992')}, while certificates understate American Indian mortality {cite('arias2016')}. A linked cohort of 19.5 million Brazilian births classified by the "
        f"mother's race found higher mortality before age 5 among children of Brown, Black and Indigenous mothers than among children of White mothers {cite('reboucas2022')}.")
para(d, f"This study aimed {OBJECTIVE}.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the RECORD statement {cite('benchimol2015')}. Deaths came from the Mortality Information System (SIM) "
        f"and live births from the Live Birth Information System (SINASC), public files of the Ministry of Health {cite('datasus')}, deaths of 2013-2024 and births of "
        f"2012-2023; the family's classification from the sample of the 2010 Census {cite('ibge_microdata2010')}; immediate regions from IBGE {cite('ibge_regions2017')}.")
para(d, f"The mother's race for each death. Infant deaths of 2013-2023 ({n0(I['certificates'])}) were linked to their birth records by probabilistic linkage "
        f"{cite('fellegi1969')} on birth date, sex, residence, birth weight and mother's age; {pct(I['linked'] / I['certificates'])} were linked, with an estimated "
        f"{min(v['fdr_percent'] for v in I['link_quality'].values()):.2f}-{max(v['fdr_percent'] for v in I['link_quality'].values()):.2f}% of false links a year, and the linked "
        f"share was {pct(ls_['Branca'])}, {pct(ls_['Parda'])} and {pct(ls_['Preta'])} for deaths certified White, Brown and Black. Deaths at 1-9 years carry no birth weight "
        "or mother's age, and were classified by the mother's race with a candidate estimator: the births of the same birth date, sex and municipality, less the births of "
        "the other sex on the same day as a control for chance agreement, cross-classified by the race on the birth record and on the certificate (Supplementary Text S1); "
        f"it reproduced the linkage's proportions in infants in municipalities with fewer than 25,600 births a year {cite('lipsitch2010')}.")
para(d, "Four ways of computing a rate. (1) Mother's race: deaths and births (or person-years from the births of the same cohorts) by the mother's race. (2) Certified "
        "race over births: certified deaths over births by the mother's race, the Ministry's infant indicator. (3) Certified race over a census-based population: "
        "certified deaths over the population by race of a population account in which census years are census counts and children born after 2010 take their cohort's "
        "race shares in the 2022 Census carried back by the state's rate of reclassification (Supplementary Text S2), as rates after infancy are usually computed. "
        "(4) Family's classification: deaths and births by mother's race passed through the proportions in which households classify children by the mother's race at the "
        "same age in the 2010 Census.")
para(d, f"Regions. For each of the 510 immediate regions, deaths of White and Brown mothers' infants (linked deaths scaled to all deaths of the region) and certified White "
        f"and Brown infant deaths were modelled over births by the mother's race as Poisson counts with Besag-York-Mollié effects {cite('besag1991', 'riebler2016')} for the "
        f"region and for the region's White to Brown contrast, fitted by integrated nested Laplace approximation {cite('rue2009', 'lindgren2015')}; each region's log ratio is a "
        "linear combination of the fixed and the regional effect. The ratio of the certified to the mother's-race rate ratio measures, relative to the mother's race, how much "
        "the certificate changes the inequality.")
para(d, "Uncertainty and sensitivity. National ratios carry the larger of the Poisson standard error and a delete-one-state jackknife. Sensitivity: deaths with no race on "
        "the certificate given the mother's race; municipalities of 25,600 or more births left out; the share of the deceased found among the candidates differing by up to 10 "
        "points between White and Brown mothers. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council no review was required.")
