# The Discussion and the references of the manuscript. Executed by build.py after text.py and text_results.py, whose names it uses.
# ruff: noqa: F821
BDW = T3["by_declared"]
il_pp, f0_pp = cell(IL, "Preta", "Preta")["est"], fam(F0, "Preta", "Preta")
assert il_pp < 0.5 * f0_pp, "the certificate's Black share is no longer half the family's"
assert abs(cell(IL, "Parda", "Branca")["est"] - fam(F0, "Parda", "Branca")) < 0.05, "certificate and family no longer agree on Brown to White in infants"
assert IR["ratio_mother"]["Branca"]["est"] * math.exp(-1.96 * IR["ratio_mother"]["Branca"]["se"] / IR["ratio_mother"]["Branca"]["est"]) < REB["under 1"]["ratio"] \
    < IR["ratio_mother"]["Branca"]["est"] * math.exp(1.96 * IR["ratio_mother"]["Branca"]["se"] / IR["ratio_mother"]["Branca"]["est"]), "the linked cohort's infant ratio is outside the interval"

d.add_heading("Discussion", level=1)
para(d, "The race on the death certificate of a child or young person in Brazil was neither the race the mother had declared for herself nor the race families assign to "
        f"their children, and it depended on where the child lived. Across municipalities the certificate's classification of Brown mothers' infants as White varied "
        f"{FV['PW']['M0'] / FV['famPW']['M0']:.0f} times as much as the family's classification of the same mothers' children, in two large contiguous blocks, whiter than the "
        "family in the South, Southeast and Centre-West and less White in the North and Northeast. The racial composition of the municipality's births explained most of that "
        "variation; the state explained part of what remained, with half of the states' differences appearing as steps at their borders; wealth, schooling, urbanisation, the "
        "supply of physicians and the services that certify explained little that composition did not. The Black category, used for fewer than one in five infants of Black "
        "mothers, became more common over the decade, unevenly between regions and most where it was already most used. Computed over the same births, the White to Brown "
        "mortality rate ratio of children was below 1 by the mother's race and above 1 by certified race, and the misstatement was largest where White births were fewest.")
para(d, "The three readings set out in the Introduction make different predictions in space, and the data adjudicate between them. The certificate does not transmit the "
        "mother's race: its agreement with her varied with the municipality from one region of the country to another. Nor does it record what the family would answer, as "
        f"the Ministry of Health instructs {cite('manual_do2022')}. Nationally the two agree on the exchange between Brown and White in infants "
        f"({f2(cell(IL, 'Parda', 'Branca')['est'])} on the certificate, {f2(fam(F0, 'Parda', 'Branca'))} in the family), but this agreement is an average of two opposite "
        "departures, in the regions where the certificate is whiter than the family and in those where it is less White, and the certificate used the Black category less "
        f"than half as often as families ({f2(il_pp)} against {f2(f0_pp)}). Families themselves classify children by both parents and by schooling "
        f"{cite('schwartzman2007')}, but their classification moved with the local composition far less than the certificate did. What the data support is the third "
        "reading, a classification made by whoever fills the certificate, and its spatial form specifies it: a classification that draws on the local population, so that "
        "the same child is more often White where most people are White, with a state component that marks the training, the forms or the practice of each state's "
        "certifiers. The test at state borders, the residual Moran's I after composition and state, and the multilevel variances all point the same way; the alternative that "
        "the gradient reflects the wealth or the services of the place was tested and explained little once composition was known. What composition left lay mostly between "
        "the establishments where children died, and the kind of certifier, the mother's schooling and the child's age moved the classification within them: the "
        "classification belongs to the place and, within the place, to the institution and the circumstances in which the certificate is filled.")
para(d, "A classification that follows the local majority is what studies of classification by observers in Brazil describe. Interviewers and respondents agreed more or "
        f"less according to the local racial composition {cite('telles2002')}, and self-declared Brown people were reclassified as White more often in cities with more White "
        f"residents {cite('muniz2017')}. The certificate shows this at the scale of the country and as a continuous surface: the classification of the same kind of child moved "
        f"from {f2(g_pb[0])} to {f2(g_pb[1])} between the least and the most White classes of municipalities, across state borders as well as within states. One part of the "
        "certificate does not follow the local majority: the Black category. Its use clustered in space, depended on the state more than on composition, and rose over the "
        f"decade, most in the South, in the period in which the Black share of the population grew between censuses {cite('miranda2015', 'ibge_census2022')}. Certificates "
        f"recorded the declared race of {ci(BDW['Preta']['certificate'])} of adult Black women who had declared it as mothers (exploratory, Supplementary Table S8), three "
        "times the proportion for the infants of Black mothers: the scarcity of the category is sharpest for small children.")

para(d, "At 15 to 24 years, in the municipalities small enough for the estimator, the certified race of people recorded as White at birth depended on the cause of death: about "
        "two thirds were certified White when the death was natural and about one third when it was an assault by firearm, with suicide, transport accidents and other "
        "external causes in between. Part of this is place: assaults occur where few births are White, and there everyone recorded White at birth is less often certified White. "
        f"At equal municipal composition the proportions were {f2(ST['natural']['Branca']['Branca']['est'])} and {f2(ST['assault']['Branca']['Branca']['est'])}. On United States "
        f"certificates, homicide raised the odds of being certified Black relative to the report of the next of kin {cite('noymer2011')}, and people who had been incarcerated "
        f"were more often seen as Black by interviewers {cite('saperstein2010')}; classification by others follows cues of social position {cite('freeman2011', 'penner2008')}. "
        "Three mechanisms can produce the gradient, and the design separates them only in part. The kind of certifier does not account for it: the difference between causes was present among "
        "deaths certified by medical examiners, and physicians and medical examiners did not differ within natural deaths. The second is the classification of the victim by "
        "cues of the death itself, by the certifier or by the informant, who cannot be told apart. The third is selection: the colour recorded at birth is not the person's "
        "later classification, and those recorded White at birth who died by assault may be those who came to be seen, or to see themselves, as Brown. For people recorded "
        "White at birth in these municipalities, the race in the numerator of a homicide rate depends on the homicide itself, which a declared denominator does not share. The "
        "same proportion rose with the schooling the mother had when the person was born, within each of three classes of composition at 15-24 years (not consistently at 1-9 "
        "years), as both a classification by social cues and selection would produce.")
para(d, f"The reversal of the White to Brown ratio in childhood does not come from the estimator: infants, whose deaths were linked one-to-one, show it ({f2(IR['ratio_mother']['Branca']['est'])} "
        f"by the mother's race, {f2(IR['ratio_certificate']['Branca']['est'])} by certified race over the same births), and the ratio by the mother's race agrees with the crude "
        f"rates of a linked cohort of 19.5 million births classified the same way ({f2(REB['under 1']['ratio'])} under one year, {f2(REB['1-4']['ratio'])} at 1-4 years) "
        f"{cite('reboucas2022')}. What the reversal is relative to matters. Certified deaths over live births by race is the Ministry's infant indicator, and it reverses the "
        "ratio. After infancy, rates are computed over a census-based population, which classifies children as households do; over that denominator the certified ratio at 1-4 "
        f"years was {f2(CONV['ratio_certificate_population'])}, compressed toward 1 rather than reversed. Under one year, the same denominator brought it to "
        f"{f2(IR['ratio_certificate_population'])}, close to the mother's-race ratio: the household's classification of infants moves births between White and Brown in roughly "
        "the proportions in which the certificate moves deaths. Earlier Brazilian comparisons of infant "
        f"mortality by race between sources found differences in opposite directions {cite('cardoso2005', 'caldas2017')}; in the United States the classification of infants at "
        f"birth and at death altered the rates of the smaller groups {cite('hahn1992')}, and certificates understate American Indian mortality {cite('arias2016')}.")

para(d, "Strengths and limitations. The study covers every municipality of the country over eleven to twelve years; it compares the certificate with the mother's "
        "declaration for the same child, by one-to-one linkage in infancy, and with the family's classification as a population reference; it measures the spatial and "
        "temporal structure of the difference with small-area models and sets the competing explanations against one another rather than adjusting for them. Its "
        "limitations are these. (1) The family's classification concerns other children, in 2010, living with their mother; it is a reference by mother's race, age and place, "
        "and the rise of Black identification since 2010 would, if anything, widen its gap with the certificate. (2) After infancy the estimator validated in infants "
        f"(in municipalities with fewer than 25,600 births a year) finds the deceased only if the family did not move ({pct(C19['matrix']['found'])} at 1-9 years, about half at "
        "15-24), assumes that this does not differ by the mother's race (a difference of 10 points would move the 1-4 year ratio within the range printed in the Results), and "
        "cannot describe state capitals; the results at 15-24 years rest on municipalities with fewer than 1,600 births a year, a bound chosen after inspecting the estimates. "
        "(3) The mother's race on the birth record is itself filled by hospital or registry staff in practice, and may carry a place-dependent component; part of what is "
        f"attributed here to the certificate could belong to the birth record. {pct(1 - form[2012]['mother_field'], 1)} of 2012 births were still on the earlier form. (4) The "
        "composition of the municipality is measured from the same mothers' declarations, over 2012-2023, and is applied to people born in 2000-2009 at 15-24 years. (5) The "
        "explanations were compared ecologically between municipalities and through municipal random effects; a composition effect at the municipal level does not say "
        "which person, certifier or informant classifies, and the certifier and the informant cannot be separated because the certificate does not record who gave the race. "
        "(6) Municipal estimates for the Black category are pooled through the spatial field and rest on few deaths; the time analysis uses intermediate regions, and the "
        "mortality ratios immediate regions, because municipal counts by year and by race do not support them. (7) Standard errors of the candidate estimator treat counts as "
        "Poisson; census standard errors ignore the sample design; the rate ratio under the family's classification has no interval. (8) The analyses by place, context, "
        "certifier, cause and schooling were not pre-specified, and many contrasts are reported. (9) Deaths of 2023 and 2024 may be revised.")
para(d, "Implications. For statistics of mortality in childhood, a rate ratio by race depends on who classified the deaths and the denominators and, now, on where. Infant "
        "and child deaths that can be linked to their birth records can be classified by the mother's race, as linked cohorts already do "
        f"{cite('reboucas2022')}, which removes the dependence on place; where that is not possible, indicators by certified race should be read against the racial "
        "composition of the place, because the same child is more often certified White where White people are the majority, and the misstatement of the inequality is "
        "largest where White births are fewest (Supplementary Data 2 lists every immediate region). Recording on the certificate who informed the race, as the instructions "
        "presuppose, would allow the classification to be audited, and the state differences found at borders suggest that state-level training is one place to act. For "
        "deaths from violence at young ages, comparisons by certified race combine the classification with the cause of death; the grouping of Black and Brown used in "
        f"Brazilian statistics on violence {cite('atlas2025', 'soaresfilho2011')} removes the exchanges between those two categories but not those between White and Brown, "
        "which were the largest at 15-24 years.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The certificate agreed with neither the mother nor the family. It followed the racial composition of the "
        "municipality as a continuous surface, with a smaller state component, and at 15-24 years the cause of death; it used the Black category for "
        f"{f2(il_pp)} of the infants of Black mothers, more often each year and unevenly in space; and with births as the denominator it reversed the direction of the White to "
        "Brown mortality rate ratio in childhood, in most regions of the country and most where White births are rare. The design does not establish which classification "
        "is correct; it establishes that the certificate is a third one, made under conditions of place that the other two do not share.")

d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
