# The Results of the indicators paper. Executed by build.py after text.py.
# ruff: noqa: F821
d.add_heading("Results", level=1)
para(d, f"Before one year, mortality by the mother's race from the linked deaths was {f1(RML['Branca'])} per 1,000 live births for children of White mothers, "
        f"{f1(RML['Parda'])} for Brown and {f1(RML['Preta'])} for Black mothers. The White to Brown ratio was {ci(LR['Branca'], log=True)} by the mother's race and "
        f"{ci(IR['ratio_certificate']['Branca'], log=True)} by certified race over the same births, the primary contrast; the Black to Brown ratio was "
        f"{ci(LR['Preta'], log=True)} and {ci(IR['ratio_certificate']['Preta'], log=True)}, and the Indigenous to Brown ratio {ci(LR['Indigena'], log=True)} and "
        f"{ci(IR['ratio_certificate']['Indigena'], log=True)} (Table 1, Figure 1). At 1-4 years the White to Brown ratios were {rr(C14W)} by the mother's race and "
        f"{rc(C14W)} by certified race over the same person-years, at 5-9 years {rr(C59W)} and {rc(C59W)}; for Black against Brown at 1-4 years, {rr(C14W, 'Preta')} and "
        f"{rc(C14W, 'Preta')}. The linked cohort of 2012-2018 births classified by the mother's race {cite('reboucas2022')} agrees: crude White to Brown ratios of "
        f"{f2(REB['under 1']['ratio'])} under one year and {f2(REB['1-4']['ratio'])} at 1-4 years.")
para(d, f"Over the census-based population, the White to Brown ratio by certified race was {f2(IR['ratio_certificate_population'])} in infancy, close to the "
        f"mother's-race ratio, and {f2(CONV['ratio_certificate_population'])} at 1-4 years (2016-2024, against {ci(CONV['ratio_mother'], log=True)} by the mother's race in "
        f"the same years, all municipalities). The census's own household classification, applied by the mother's race, gave {f2(IR['ratio_household']['Branca'])} in infancy, "
        f"{f2(C14['ratio_household']['Branca'])} at 1-4 and {f2(C59['ratio_household']['Branca'])} at 5-9 years. The census-based value at 1-4 years thus lies between the "
        "household classification and no difference, and depends on how the population account carries the 2022 race shares of children born after 2010 back in time "
        "(Supplementary Text S2); none of these values carries an interval.")
rows = []
INF = {"ratio_mother": LR, "ratio_certificate": IR["ratio_certificate"], "by_mother": {k: {"est": v} for k, v in RML.items()}, "by_certificate": IR["by_certificate"]}
for label, B, hh, pop, unit in (("Under 1 year", INF, IR["ratio_household"], IR["ratio_certificate_population"], "per 1,000 live births"),
                                ("1-4 years", C14W, C14["ratio_household"], CONV["ratio_certificate_population"], "per 100,000 person-years"),
                                ("5-9 years", C59W, C59["ratio_household"], None, "per 100,000 person-years")):
    for k in ORDER:
        ref = k == "Parda"
        rows.append([f"{label} ({unit})", EN[k], f1(B["by_mother"][k]["est"]), f1(B["by_certificate"][k]["est"]),
                     "1 (reference)" if ref else ci(B["ratio_mother"][k], log=True), "1 (reference)" if ref else ci(B["ratio_certificate"][k], log=True),
                     "1 (reference)" if ref else (f2(pop) if (pop is not None and k == "Branca") else "-"), "1 (reference)" if ref else f"{f2(hh[k])}"])
table(d, "Table 1 - Mortality rates and rate ratios by race with deaths and denominators classified four ways, Brazil, 2013-2024 (under 1 year: 2013-2023)",
      ["Age", "Race", "Rate, mother's race", "Rate, certified race over births", "Ratio, mother's race (95%CI)", "Ratio, certified over births (95%CI)",
       "Ratio, certified over census-based population", "Ratio, family's classification"], rows,
      ["95%CI: 95% confidence interval. Under 1 year, mother's race: linked deaths scaled to every certificate. 1-4 and 5-9 years: candidate estimator, municipalities "
       f"with fewer than 25,600 births a year (all municipalities: White to Brown {rr(C14['rates'])} at 1-4 years). Census-based population: White to Brown only, under one "
       "year in 2013-2023 and at 1-4 years in 2016-2024; none at 5-9 years. Family's classification: deaths and births passed through the census proportions of the same "
       "age; no interval. Deaths with no race on the certificate are not in the certified rates; given the mother's race, the infant ratio by certified race becomes "
       f"{f2(IR['ratio_certificate_blank_as_mother'])}. Yellow (Asian) births and deaths are not shown."])
figure(d, "mortality", "Figure 1 - Mortality rates by the mother's race and by certified race over the same births (A-C), and White to Brown rate ratios under four ways of "
                       "classifying deaths and denominators (D), Brazil, 2013-2024",
       ["A: per 1,000 live births, linked deaths. B, C: per 100,000 person-years, candidate estimator in municipalities with fewer than 25,600 births a year. D: log scale. "
        "Bars: 95% confidence intervals."])
para(d, f"By region the two infant ratios usually pointed in opposite directions, but credibly so in a minority of regions (Figure 2). By posterior means, the infant "
        f"ratio by certified race had the opposite direction to the ratio by the mother's race in {MS['reversed']} of the {MS['regions']} immediate regions, holding "
        f"{pct(MS['births_share_reversed'], 0)} of births. The certified ratio was credibly above 1 in {MS['certificate_above_1_credibly']} regions, while the mother's-race "
        f"ratio was credibly below 1 in only {MS['mother_below_1_credibly']}: regional White deaths by the mother's race are few, and the model draws each region toward the "
        f"national term (a White to Brown ratio of {math.exp(RA['mother']['national']['mean']):.2f} by the mother's race and {math.exp(RA['certificate']['national']['mean']):.2f} "
        f"by certified race). Both were credible in {MS['reversed_credible']} regions, and the certified ratio credibly exceeded the mother's-race ratio in "
        f"{MS['misstated_credibly_positive']}. Weighted by births, the certified ratio was {f2(MSB['<10%']['ratio_of_ratios'])} times the mother's-race ratio where under "
        f"10% of births were White, {f2(MSB['10-29%']['ratio_of_ratios'])} at 10-29%, {f2(MSB['30-59%']['ratio_of_ratios'])} at 30-59% and "
        f"{f2(MSB['>=60%']['ratio_of_ratios'])} at 60% or more: highest where White births are rare. These class means exceed the national ratios because the national "
        "ratio pools regions of different composition, whereas each class mean averages regional ratios. The regions where the certificate raised the ratio most are listed "
        "in Supplementary Table S1 and every region in Supplementary Data.")
figure(d, "regional_ratios", "Figure 2 - White to Brown infant mortality rate ratio by immediate region, by the mother's race (A) and by certified race (B), the ratio of the two "
                             "(C), and the ratio of the two against the share of White births and GDP per capita (D), Brazil, 2013-2023",
       ["Posterior means of Poisson models with Besag-York-Mollié effects over 510 immediate regions; the colour scales of A-C are censored at their ends (the largest "
        "values are in Supplementary Table S1). D: area of a point, live births; the line is the births-weighted mean by class of composition."])
para(d, "The direction of the national ratios did not depend on the choices of the estimator; their size moved within the intervals. With all municipalities, the White "
        f"to Brown ratio at 1-4 years by the mother's race was {rr(C14['rates'])}; for that estimate, leaving out one state at a time gave "
        f"{f2(C14['rates']['ratio_mother']['Branca']['loo_min'])} to {f2(C14['rates']['ratio_mother']['Branca']['loo_max'])}; and with the share of the deceased found among the "
        f"candidates differing by up to 10 points between White and Brown mothers it lay between {f2(min(C14['t_sensitivity'].values()))} and "
        f"{f2(max(C14['t_sensitivity'].values()))}. By region, the ratios at 1-9 years are in Supplementary Figure S1, and by state in Supplementary Table S2.")
