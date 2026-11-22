# The Discussion and the references of the manuscript. Executed by build.py after text.py and text_results.py, whose names it uses.
# ruff: noqa: F821
BDW = T3["by_declared"]
il_pp, f0_pp = cell(IL, "Preta", "Preta")["est"], fam(F0, "Preta", "Preta")
assert il_pp < 0.5 * f0_pp, "the certificate's Black share is no longer half the family's"
assert abs(cell(IL, "Parda", "Branca")["est"] - fam(F0, "Parda", "Branca")) < 0.05, "certificate and family no longer agree on Brown to White in infants"
assert IR["ratio_mother"]["Branca"]["est"] * math.exp(-1.96 * IR["ratio_mother"]["Branca"]["se"] / IR["ratio_mother"]["Branca"]["est"]) < REB["under 1"]["ratio"] \
    < IR["ratio_mother"]["Branca"]["est"] * math.exp(1.96 * IR["ratio_mother"]["Branca"]["se"] / IR["ratio_mother"]["Branca"]["est"]), "the linked cohort's infant ratio is outside the interval"

d.add_heading("Discussion", level=1)
LR_ = IR["ratio_mother_linkage"]["Branca"]
para(d, "The race on the death certificate of a child or young person in Brazil was neither the race the mother had declared for herself nor the race families assign to "
        f"children, and it depended on where the child lived. Across municipalities, the certificate's classification of Brown mothers' infants as White varied "
        f"{FV['PW']['M0'] / FV['famPW']['M0']:.0f} times as much (in log-odds variance) as families' classification of Brown mothers' children aged 0-9, in two large "
        "contiguous blocks: whiter than the family in the South, Southeast and Centre-West and less White in the North and Northeast. The racial composition of the "
        "municipality's births and the state each accounted for about three quarters of that variation and together for four fifths, with a step at state borders; wealth, "
        "schooling, urbanisation, the supply of physicians and the services that certify accounted for less than composition and little in addition to it. The Black "
        "category, used for fewer than one in five infants of Black mothers, became more common over the decade, unevenly between regions. Computed over the same births, the "
        "White to Brown mortality rate ratio of children was below 1 by the mother's race and above 1 by certified race, and relative to the mother's race the certificate "
        "changed the ratio most where White births were fewest.")
para(d, "The three readings set out in the Introduction make different predictions in space, and the data narrow them. The certificate does not transmit the mother's race: "
        "its agreement with her varied from one region of the country to another. Nor does it record what the family would answer, as the Ministry of Health instructs "
        f"{cite('manual_do2022')}. Nationally the two agree on the exchange between Brown and White in infants ({f2(cell(IL, 'Parda', 'Branca')['est'])} on the certificate, "
        f"{f2(fam(F0, 'Parda', 'Branca'))} in the family), but this is an average of opposite departures in different regions, and the certificate used the Black category "
        f"less than half as often as families ({f2(il_pp)} against {f2(f0_pp)}). Families themselves classify children by both parents and by schooling "
        f"{cite('schwartzman2007')}, but their classification moved with the local composition far less than the certificate did. The data are consistent with the third "
        "reading, a classification by whoever fills the certificate that is associated with the local population and has a state component, which could reflect the "
        "training, the forms or the practice of each state's certifiers. Two explanations remain open. Municipal associations do not say who classifies. And the Brown "
        "category itself is not the same population everywhere: if Brown mothers and their children look different in the South and in the North, an observer who "
        "classifies by appearance, with no local norm at all, would produce the same gradient with composition; the comparison of neighbours across state borders controls "
        "for this only near the borders. The alternative that the gradient follows the wealth or the services of the place explained less than composition and little in "
        "addition to it. Within municipalities, residual clustering was better captured by the establishment where the child died, and the kind of certifier, the mother's "
        "schooling and the child's age at death moved the classification. Composition was measured from the same birth records that give the reference, but in the "
        "municipal models the census share of White residents explained as much.")
para(d, "A classification that follows the local majority is what studies of classification by observers in Brazil describe. Agreement between interviewers and "
        f"respondents varied with the local racial composition {cite('telles2002')}, and self-declared Brown people were reclassified as White more often in cities with more "
        f"White residents {cite('muniz2017')}. The certificate shows the same pattern at the scale of the country: Brown mothers' infants were certified White in "
        f"{f2(g_pb[0])} to {f2(g_pb[1])} of deaths between the least and the most White classes of municipalities, a proportion that rose with composition within states and "
        "stepped at their borders. One part of the certificate does not follow the local majority: the Black category. Its use clustered in space, depended on the state "
        "more than on composition, and rose over the decade, most in the South; whether this follows the growth of Black identification seen between censuses "
        f"{cite('miranda2015', 'ibge_census2022')} cannot be tested here. Certificates recorded the declared race of {ci(BDW['Preta']['certificate'])} of adult Black women "
        "who had declared it as mothers (exploratory, Supplementary Table S8), three times the proportion for the infants of Black mothers, in a different population and setting.")
para(d, "At 15 to 24 years, in the small municipalities where the estimator works, the certified race of people recorded as White at birth depended on the cause of death: "
        "about two thirds were certified White when the death was natural and about one third when it was an assault by firearm, with suicide, transport accidents and other "
        "external causes in between. Part of this is place: assaults occur where few births are White. At equal municipal composition the proportions were "
        f"{f2(ST['natural']['Branca']['Branca']['est'])} and {f2(ST['assault']['Branca']['Branca']['est'])}. On United States certificates, homicide raised the odds of being "
        f"certified Black relative to the report of the next of kin {cite('noymer2011')}, and people who had been incarcerated were more often seen as Black by interviewers "
        f"{cite('saperstein2010', 'penner2008')}; in experiments, cues of social status shifted how faces were classified by race {cite('freeman2011')}. Three mechanisms can "
        "produce the gradient, and the design separates them only in part. The kind of certifier does not account for it: the difference between causes was present among "
        "deaths certified by medical examiners, although certifiers may differ by 10 points or more within a cause. The second is the classification of the victim by cues of "
        "the death itself, by the certifier or by the informant, who cannot be told apart. The third is selection: the colour recorded at birth is not the person's later "
        "classification, and those recorded White at birth who died by assault may be those who came to be seen, or to see themselves, as Brown. For people recorded White at "
        "birth in these municipalities, the race in the numerator of a homicide rate depends on the homicide itself. The same proportion rose with the schooling the mother "
        "had when the person was born, within each of three classes of composition at 15-24 years (not consistently at 1-9 years), as both a classification by social cues "
        "and selection would produce.")
para(d, f"The reversal of the White to Brown ratio in childhood does not come from the candidate estimator: from the one-to-one linkage alone the infant ratio by the mother's "
        f"race was {ci(LR_, log=True)}, against {f2(IR['ratio_certificate']['Branca']['est'])} by certified race over the same births, and both it and the estimator's "
        f"{f2(IR['ratio_mother']['Branca']['est'])} agree with the crude rates of a linked cohort of 19.5 million births classified the same way "
        f"({f2(REB['under 1']['ratio'])} under one year, {f2(REB['1-4']['ratio'])} at 1-4 years) {cite('reboucas2022')}. What the reversal is relative to matters. Certified "
        "deaths over live births by race is the Ministry's infant indicator, and it reverses the ratio. After infancy, rates are computed over a census-based population; over "
        f"such a denominator, whose race shares for children born after 2010 are carried back from the 2022 Census (Supplementary Text S3), the certified ratio at 1-4 years "
        f"was {f2(CONV['ratio_certificate_population'])}, compressed toward 1 rather than reversed, and under one year {f2(IR['ratio_certificate_population'])}. Earlier "
        f"Brazilian comparisons of infant mortality by race between sources found differences in opposite directions {cite('cardoso2005', 'caldas2017')}; in the United States "
        f"the classification of infants at birth and at death altered the rates of the smaller groups {cite('hahn1992')}, and certificates understate American Indian mortality "
        f"{cite('arias2016')}.")
para(d, "Strengths and limitations. The study covers every municipality of the country over eleven to twelve years; it compares the certificate with the mother's "
        "declaration for the same child, by one-to-one linkage in infancy, and with the family's classification as a population reference; it measures the spatial and "
        "temporal structure of the difference with small-area models and sets the competing explanations against one another rather than adjusting for them. Its "
        "limitations are these. (1) The family's classification concerns other children, in 2010, living with their mother, and the mother's race there is the household's "
        "report of her, not her own declaration on a birth record; it is a reference by mother's race, age and place. (2) After infancy the estimator, validated in infants "
        f"in municipalities with fewer than 25,600 births a year, finds the deceased only if the family did not move ({pct(C19['matrix']['found'])} at 1-9 years, about half at "
        "15-24) and assumes that this does not differ by the mother's race; it cannot describe state capitals, and the results at 15-24 years rest on municipalities with "
        "fewer than 1,600 births a year, a bound chosen after inspecting the estimates. (3) The mother's race on the birth record is itself filled by hospital or registry "
        "staff in practice, and may carry a place-dependent component; part of what is attributed here to the certificate could belong to the birth record. "
        f"{pct(1 - form[2012]['mother_field'], 1)} of 2012 births were still on the earlier form. (4) The composition of the municipality is measured from the same mothers' "
        "declarations, over 2012-2023, and is applied to people born in 2000-2009 at 15-24 years; the census share of White residents was substituted only in the municipal "
        "models of infants. (5) The explanations were compared ecologically between municipalities and through municipal random effects. A composition effect at the "
        "municipal level does not say which person, certifier or informant classifies, nor exclude that the Brown category differs between regions; the certifier and the "
        "informant cannot be separated because the certificate does not record who gave the race; proportions of municipal variance explained in a logistic model are "
        "affected by rescaling when individual variables enter; and the multilevel models were fitted by an approximation (nAGQ = 0) that can understate variance "
        "components. (6) Municipal estimates for the Black category rest on few deaths; the time analysis uses intermediate regions, and the mortality ratios immediate "
        "regions, because municipal counts by year and by race do not support them; the regional mother's-race ratios come from the linkage and the national ones from both "
        "the linkage and the candidate estimator. (7) Standard errors of the candidate estimator treat counts as Poisson; census standard errors ignore the sample design; "
        "the rate ratio under the family's classification has no interval. (8) The analyses by place, context, certifier, cause and schooling were not pre-specified, and many "
        "contrasts are reported. (9) Deaths of 2023 and 2024 may be revised.")
para(d, "Implications. For statistics of mortality in childhood, a rate ratio by race depends on who classified the deaths, on the denominator and on where. Infant and child "
        f"deaths that can be linked to their birth records can be classified by the mother's race, as linked cohorts already do {cite('reboucas2022')}, which removes the "
        "certificate's dependence on place, though not any place-dependence of the birth record itself. Where that is not possible, indicators by certified race should be "
        "read against the racial composition of the place: Brown mothers' children are more often certified White where White people are the majority, and relative to the "
        "mother's race the ratio changes most where White births are fewest (Supplementary Data 2 lists every immediate region). Recording on the certificate who informed "
        "the race, as the instructions presuppose, would allow the classification to be audited, and the steps at state borders point to the states' practice as one place "
        "to act. For deaths from violence at young ages, comparisons by certified race combine the classification with the cause of death; the grouping of Black and Brown "
        f"used in Brazilian statistics on violence {cite('atlas2025', 'soaresfilho2011')} removes the exchanges between those two categories but not those between White and "
        "Brown, which were the largest at 15-24 years.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The certificate departed from both the mother's declaration and the family's classification. It was associated with "
        "the racial composition of the municipality and with the state, with a step at state borders, and at 15-24 years with the cause of death; it used the Black category "
        f"for {f2(il_pp)} of the infants of Black mothers, more often each year and unevenly in space; and with births as the denominator it reversed the direction of the "
        f"White to Brown mortality rate ratio in childhood, by posterior means in {MS['reversed']} of {MS['regions']} immediate regions and credibly in "
        f"{MS['reversed_credible']}. The design does not establish which classification is correct; it establishes that the certificate is a third one, whose relation to "
        "the other two depends on place.")

d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
