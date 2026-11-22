# The Results of the indicators paper. Executed by build.py after text.py.
# ruff: noqa: F821
d.add_heading("Results", level=1)
para(d, f"Before one year, mortality was {f1(IR['by_mother']['Branca']['est'])} per 1,000 live births for children of White mothers and {f1(IR['by_mother']['Parda']['est'])} "
        f"for children of Brown mothers. The White to Brown ratio was {ci(LR['Branca'], log=True)} from the linked deaths by the mother's race "
        f"({ci(IR['ratio_mother']['Branca'], log=True)} by the candidate estimator), {ci(IR['ratio_certificate']['Branca'], log=True)} by certified race over the same births, "
        f"{f2(IR['ratio_certificate_population'])} by certified race over the census-based population and {f2(IR['ratio_household']['Branca'])} under the family's "
        f"classification (Table 1, Figure 1). At 1-4 years the ratios were {rr(C14)} by the mother's race, {rc(C14)} by certified race over births, "
        f"{f2(CONV['ratio_certificate_population'])} by certified race over the census-based population (2016-2024, against {ci(CONV['ratio_mother'], log=True)} by the "
        f"mother's race in the same years) and {f2(C14['ratio_household']['Branca'])} under the family's classification; at 5-9 years, {rr(C59)}, {rc(C59)} and "
        f"{f2(C59['ratio_household']['Branca'])}. For Black against Brown at 1-4 years the ratios were {rr(C14, 'Preta')} by the mother's race and {rc(C14, 'Preta')} by certified "
        f"race. The linked cohort of 2012-2018 births classified by the mother's race {cite('reboucas2022')} gives crude White to Brown ratios of "
        f"{f2(REB['under 1']['ratio'])} under one year and {f2(REB['1-4']['ratio'])} at 1-4 years.")
rows = []
for label, B, hh, pop, unit in (("Under 1 year", IR, IR["ratio_household"], IR["ratio_certificate_population"], "per 1,000 live births"),
                                ("1-4 years", C14["rates"], C14["ratio_household"], CONV["ratio_certificate_population"], "per 100,000 person-years"),
                                ("5-9 years", C59["rates"], C59["ratio_household"], None, "per 100,000 person-years")):
    for k in ORDER:
        ref = k == "Parda"
        rows.append([f"{label} ({unit})", EN[k], f1(B["by_mother"][k]["est"]), f1(B["by_certificate"][k]["est"]),
                     "1 (reference)" if ref else ci(B["ratio_mother"][k], log=True), "1 (reference)" if ref else ci(B["ratio_certificate"][k], log=True),
                     "1 (reference)" if ref else (f2(pop) if (pop is not None and k == "Branca") else "-"), "1 (reference)" if ref else f"{f2(hh[k])}"])
table(d, "Table 1 - Mortality rates and rate ratios by race with deaths and denominators classified four ways, Brazil, 2013-2024 (under 1 year: 2013-2023)",
      ["Age", "Race", "Rate, mother's race", "Rate, certified race over births", "Ratio, mother's race (95%CI)", "Ratio, certified over births (95%CI)",
       "Ratio, certified over census-based population", "Ratio, family's classification"], rows,
      ["95%CI: 95% confidence interval. Mother's race: candidate estimator; from the linked infant deaths alone the White to Brown ratio is "
       f"{ci(LR['Branca'], log=True)}. Census-based population: White to Brown only, under one year in 2013-2023 and at 1-4 years in 2016-2024. Family's classification: "
       "deaths and births passed through the census proportions of the same age; no interval. Deaths with no race on the certificate are not in the certified rates; given "
       f"the mother's race, the infant ratio by certified race becomes {f2(IR['ratio_certificate_blank_as_mother'])}."])
figure(d, "mortality", "Figure 1 - Mortality rates by the mother's race and by certified race over the same births (A-C), and White to Brown rate ratios under four ways of "
                       "classifying deaths and denominators (D), Brazil, 2013-2024", ["Bars: 95% confidence intervals."])
para(d, f"The reversal was general across the country (Figure 2). In {MS['reversed']} of the {MS['regions']} immediate regions, holding {pct(MS['births_share_reversed'], 0)} "
        f"of births, the infant ratio by certified race had the opposite direction to the ratio by the mother's race; the mother's-race ratio was credibly below 1 in "
        f"{MS['mother_below_1_credibly']} regions, the certified ratio credibly above 1 in {MS['certificate_above_1_credibly']}, both in {MS['reversed_credible']}, and the "
        f"certified ratio exceeded the mother's-race ratio credibly in {MS['misstated_credibly_positive']}. The change was U-shaped in the composition of births: weighted by "
        f"births, the certified ratio was {f2(MSB['<10%']['ratio_of_ratios'])} times the mother's-race ratio where under 10% of births were White, "
        f"{f2(MSB['10-29%']['ratio_of_ratios'])} at 10-29%, {f2(MSB['30-59%']['ratio_of_ratios'])} at 30-59% and {f2(MSB['>=60%']['ratio_of_ratios'])} at 60% or more. At the "
        "low end, a small share of Brown mothers' infants certified White adds many deaths to a small White denominator; at the high end, Brown mothers' infants certified "
        "White leave the Brown numerator. Where White births are rare, the mother's-race ratio rests on few deaths and is pulled toward its mean by the model "
        f"({f2(MSB['<10%']['mother'])} in that class). The regions where the certificate raised the ratio most are listed in Supplementary Table S1 and every region in "
        "Supplementary Data.")
figure(d, "regional_ratios", "Figure 2 - White to Brown infant mortality rate ratio by immediate region, by the mother's race (A) and by certified race (B), the ratio of the two "
                             "(C), and the ratio of the two against the share of White births and GDP per capita (D), Brazil, 2013-2023",
       ["Posterior means of Poisson models with Besag-York-Mollié effects over 510 immediate regions. D: area of a point, live births; the line is the births-weighted mean by "
        "class of composition."])
para(d, "The national ratios were robust to the choices of the estimator. Without municipalities of 25,600 or more births a year, the White to Brown ratio at 1-4 years by "
        f"the mother's race was {ci(C14['without_large']['rates']['ratio_mother']['Branca'], log=True)}; leaving out one state at a time it ranged from "
        f"{f2(C14['rates']['ratio_mother']['Branca']['loo_min'])} to {f2(C14['rates']['ratio_mother']['Branca']['loo_max'])}; and with the share of the deceased found among the "
        f"candidates differing by up to 10 points between White and Brown mothers it lay between {f2(min(C14['t_sensitivity'].values()))} and "
        f"{f2(max(C14['t_sensitivity'].values()))}. By region, the ratios at 1-9 years are in Supplementary Figure S1, and by state in Supplementary Table S2.")
