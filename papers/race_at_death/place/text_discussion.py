# The Discussion and the references of the place paper. Executed by build.py after text.py and text_results.py, whose names it uses.
# ruff: noqa: F821
il_pp, f0_pp = cell(IL, "Preta", "Preta")["est"], fam(F0, "Preta", "Preta")
assert il_pp < 0.5 * f0_pp, "the certificate's Black share is no longer half the family's"
assert abs(cell(IL, "Parda", "Branca")["est"] - fam(F0, "Parda", "Branca")) < 0.05, "certificate and family no longer agree on Brown to White in infants"

d.add_heading("Discussion", level=1)
para(d, "The race on the death certificate of a child in Brazil was neither the race the mother had declared for herself nor the race families assign to children, and it "
        f"depended on where the child lived. Across municipalities, the certificate's classification of Brown mothers' infants as White varied "
        f"{FV['PW']['M0'] / FV['famPW']['M0']:.0f} times as much (in log-odds variance) as families' classification of Brown mothers' children aged 0-9, in two large "
        "contiguous blocks: whiter than the family in the South, Southeast and Centre-West and less White in the North and Northeast. The racial composition of the "
        "municipality's births and the state each accounted for about three quarters of that variation and together for four fifths, with a step at state borders; wealth, "
        "schooling, urbanisation, the supply of physicians and the services that certify accounted for less than composition and little in addition to it, and the "
        "characteristics of the deaths themselves accounted for none of it. The Black category, used for fewer than one in five infants of Black mothers, became more common "
        "over the decade, unevenly between regions.")
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
        "municipal models the census share of White residents explained as much. Over time the gradient behaved as a trait of the place: when a municipality's or a "
        f"region's share of White births changed, its certificate moved about {WI['all']['lw_w']['est'] / WI['lw_reliability'] / WI['all']['lw_b']['est'] * 100:.0f}% "
        "as far as the cross-sectional gradient predicts, and not at all with its wealth or physicians. A norm that responded to the local population as it is would "
        "follow its changes; an observer reading the appearance of a regionally distinct Brown population would not, and neither would a practice settled in each "
        "place's institutions. The within changes of a decade were small, however, and the census comparison could not exclude a modest response.")
para(d, "A classification that follows the local majority is what studies of classification by observers in Brazil describe. Agreement between interviewers and "
        f"respondents varied with the local racial composition {cite('telles2002')}, and self-declared Brown people were reclassified as White more often in cities with more "
        f"White residents {cite('muniz2017')}; classification by others also responds to social position {cite('penner2008', 'saperstein2012')}. The certificate shows the "
        f"same pattern at the scale of the country: Brown mothers' infants were certified White in {f2(g_pb[0])} to {f2(g_pb[1])} of linked deaths pooled in the least and the most "
        f"White of {len(GI)} classes of municipalities by their share of White births (the smoothed municipal values ranged from {f2(DI['PW']['p5'])} to "
        f"{f2(DI['PW']['p95'])}), a proportion that rose with composition within states and stepped at their borders. One part of the certificate does not follow "
        "the local majority: the Black category. Its use clustered in space, depended on the state more than on composition, and rose over the decade, without a clear difference between regions; "
        f"whether this follows the growth of Black identification seen between censuses {cite('miranda2015', 'ibge_census2022')} cannot be tested here. On United States "
        f"certificates the race recorded also depended on circumstances other than the person {cite('noymer2011', 'arias2016')}, and in São Paulo correcting the certified "
        f"race of older adults changed the ranking of mortality {cite('santos2019')}.")
para(d, "Strengths and limitations. The study covers every municipality of the country over eleven years; it compares the certificate with the mother's declaration for the "
        "same child, by one-to-one linkage in infancy, and with the family's classification as a population reference; it measures the spatial and temporal structure of "
        "the difference with small-area models and sets the competing explanations against one another rather than adjusting for them. Its limitations are these. (1) The "
        "family's classification concerns other children, in 2010, living with their mother, and the mother's race there is the household's report of her, not her own "
        "declaration on a birth record; it is a reference by mother's race, age and place. (2) After infancy the estimator, validated in infants in municipalities with fewer "
        f"than 25,600 births a year, finds the deceased only if the family did not move ({pct(C19['matrix']['found'])} at 1-9 years) and assumes that this does not differ by "
        "the mother's race; it cannot describe state capitals. (3) The mother's race on the birth record is itself filled by hospital or registry staff in practice, and may "
        "carry a place-dependent component; part of what is attributed here to the certificate could belong to the birth record. "
        f"{pct(1 - form[2012]['mother_field'], 1)} of 2012 births were still on the earlier form. (4) The composition of the municipality is measured from the same mothers' "
        "declarations; the census share of White residents was substituted only in the municipal models. (5) The explanations were compared ecologically between "
        "municipalities and through municipal random effects. A composition effect at the municipal level does not say which person, certifier or informant classifies, "
        "nor exclude that the Brown category differs between regions; the certifier and the informant cannot be separated because the certificate does not record who gave "
        "the race; proportions of municipal variance explained in a logistic model are affected by rescaling when individual variables enter; and the multilevel models were "
        "fitted by an approximation (nAGQ = 0) that can understate variance components. (6) Municipal estimates for the Black category rest on few deaths, and the time "
        "analysis uses intermediate regions because municipal counts by year do not support it. (7) Standard errors of the candidate estimator treat counts as Poisson; "
        "census standard errors ignore the sample design. (8) The analyses by place and context were not pre-specified, and many contrasts are reported. (9) Deaths of 2023 "
        "may be revised.")
para(d, "Implications. A child's race on the death certificate depends on where the child died, on the state and on the establishment, and only in part on the child's "
        "family; statistics by certified race therefore compare places as much as groups. Infant and child deaths that can be linked to their birth records can be "
        f"classified by the mother's race, as linked cohorts already do {cite('reboucas2022')}, which removes the certificate's dependence on place, though not any "
        "place-dependence of the birth record itself. Recording on the certificate who informed the race, as the instructions presuppose, would allow the classification "
        "to be audited, and the steps at state borders point to the states' practice as one place to act. What the classification does to mortality rate ratios by race, "
        "nationally and region by region, is the subject of a companion analysis.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The certificate departed from both the mother's declaration and the family's classification. It was associated with "
        "the racial composition of the municipality and with the state, with a step at state borders, more than with the wealth or the services of the place or the "
        f"circumstances of the death; and it used the Black category for {f2(il_pp)} of the infants of Black mothers, more often each year and unevenly in space. The design "
        "does not establish which classification is correct; it establishes that the certificate is a third one, whose relation to the other two depends on place.")

d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
