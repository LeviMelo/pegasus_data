# The Discussion and the references of the place paper. Executed by build.py after text.py and text_results.py, whose names it uses.
# ruff: noqa: F821
il_pp, f0_pp = cell(IL, "Preta", "Preta")["est"], fam(F0, "Preta", "Preta")
assert il_pp < 0.5 * f0_pp, "the certificate's Black share is no longer half the family's"
assert abs(cell(IL, "Parda", "Branca")["est"] - fam(F0, "Parda", "Branca")) < 0.05, "certificate and family no longer agree on Brown to White in infants"

d.add_heading("Discussion", level=1)
assert PHY["PW"]["all"]["physician"] > PHY["PW"]["all"]["death_estab"] > PHY["PW"]["all"]["mun6"], "the order of the levels changed: rewrite the Discussion"
assert OCC["PW"]["lws_occ"]["coef"] > OCC["PW"]["lws"]["coef"] and OCC["WP"]["lws_occ"]["coef"] < OCC["WP"]["lws"]["coef"], "the residence now predicts more than the place of death: rewrite the Discussion"
assert all(v["agreement"]["est"] < 0.8 for v in INV.values()), "an investigated group now agrees with the mother: rewrite the Discussion"
para(d, "The race on the death certificate of a child in Brazil was neither the race the mother had declared for herself nor the race families assign to children, and it "
        f"depended on where the child lived. Across municipalities, the certificate's classification of Brown mothers' infants as White varied "
        f"{FV['PW']['M0'] / FV['famPW']['M0']:.0f} times as much (in log-odds variance) as families' classification of Brown mothers' children aged 0-9, in two large "
        "contiguous blocks: whiter than the family in the South, Southeast and Centre-West and less White in the North and Northeast. The racial composition of the "
        "municipality's births and the state each accounted for about three quarters of that variation and together for four fifths, with a step at state borders; wealth, "
        "schooling, urbanisation, the supply of physicians and the services that certify accounted for less than composition and little in addition to it, and the "
        "characteristics of the deaths, without the macro-region, accounted for none of it. The White category for Brown mothers' infants became less common over the "
        "decade, unevenly between regions.")
para(d, "The three readings set out in the Introduction make different predictions, and the data narrow them (Table 1). The certificate does not transmit the "
        "mother's race: its agreement with her varied between regions, and it was only slightly higher where the birth record lay at hand. Nor does it record what the "
        f"family would answer, as the Ministry of Health instructs {cite('manual_do2022')}: nationally the two agree on the exchange between Brown and White "
        f"({f2(cell(IL, 'Parda', 'Branca')['est'])} on the certificate, {f2(fam(F0, 'Parda', 'Branca'))} in the family), but as an average of opposite departures by region, "
        f"and the certificate used the Black category less than half as often as families ({f2(il_pp)} against {f2(f0_pp)}). What remains is a classification by whoever fills "
        "the certificate. It moves toward the local majority, partly, in the three cells tested; it has a state component, with a step at state borders; and it varies "
        f"between the individuals who certify: the variance between physicians ({f2(PHY['PW']['all']['physician'])}) exceeded that between establishments "
        f"({f2(PHY['PW']['all']['death_estab'])}) and municipalities ({f2(PHY['PW']['all']['mun6'])}), though with few deaths per physician that order is not secure. "
        "A Brown category that is not the same population everywhere could also produce the gradient; families do not show it: a Brown couple's child was reported White "
        f"only a little more often in whiter places ({f2(PPW['bins'][0]['est'])} to {f2(PPW['bins'][-1]['est'])}), under a quarter of the certificate's gradient. The birth "
        f"record, the reference here, also leaned toward the local majority (logit slope {f2(MW['slope_region']['slope'])} within regions against the census), so the "
        "certificate's departure from the mothers' own declaration would be larger, not smaller. Wealth and services explained little beside composition, though in Brazil they are collinear with it. "
        "The within-place change was small and imprecise: when a region's share of White births changed, its certificate moved about "
        f"{WI['all']['lw_w']['est'] / WI['lw_reliability'] / WI['all']['lw_b']['est'] * 100:.0f}% as far as the cross-sectional gradient predicts, with an interval that "
        "includes no change, and a slow adjustment cannot be excluded.")
para(d, "A classification that follows the local majority is what studies of classification by observers in Brazil describe: agreement between interviewers and "
        f"respondents varied with the local racial composition {cite('telles2002')}, and Brown people were reclassified as White more often in whiter cities {cite('muniz2017')}. "
        f"The certificate shows the same pattern at the scale of the country: Brown mothers' infants were certified White in {f2(g_pb[0])} to {f2(g_pb[1])} of linked deaths pooled in the least and the most "
        f"White of {len(GI)} classes of municipalities by their share of White births, a proportion that rose with composition within states and stepped at their borders. One part of the certificate does not follow "
        "the local majority as strongly: the Black category, the subject of a companion paper. Its use clustered in space, depended on the state more than on "
        "composition, and rose over the decade; "
        f"whether this follows the growth of Black identification seen between censuses {cite('miranda2015', 'ibge_census2022')} cannot be tested here.")
para(d, "Strengths and limitations. The study covers every municipality of the country over eleven years, compares the certificate with the mother's declaration for the "
        "same child by one-to-one linkage, and sets the competing explanations against one another rather than adjusting for them. Its limitations are these. (1) The "
        "family's classification concerns other children, in 2010, and is a reference by mother's race, age and place. (2) After infancy the estimator finds the "
        f"deceased only if the family did not move ({pct(C19['matrix']['found'])} at 1-9 years) and cannot describe state capitals. (3) The birth record, the reference, itself leans toward the local majority, "
        "and the census comparison is by municipality, not by person. "
        f"{pct(1 - form[2012]['mother_field'], 1)} of 2012 births were still on the earlier form. (4) Composition is measured from the same mothers' declarations; the census share "
        "substituted only in the municipal models. (5) The explanations were compared ecologically, and the certifier and the informant cannot be separated because the "
        "certificate does not record who gave the race; the multilevel models used an approximation, with which a Laplace refit agreed. (6) Municipal estimates for the Black category rest on few deaths. "
        "(7) Standard errors of the candidate estimator treat counts as Poisson, and census ones ignore the sample design. (8) The analyses by place and context were not "
        "pre-specified. (9) Deaths of 2023 may be revised. (10) The family benchmark is not the same child's classification by its own family, and households report children "
        "by both parents (a companion paper).")
para(d, "Implications. An infant's race on the death certificate depends on where the child died, on the state and on the establishment, and only in part on the "
        "child's family; statistics by certified race therefore compare places as much as groups. Infant and child deaths that can be linked to their birth records can be "
        f"classified by the mother's race, as linked cohorts already do {cite('reboucas2022')}, which removes the certificate's dependence on place, though not any "
        "place-dependence of the birth record itself. Recording on the certificate who informed the race would allow the classification "
        "to be audited, and the steps at state borders point to the states' practice as one place to act.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The certificate departed from both the mother's declaration and the family's classification. It was associated with "
        "the racial composition of the municipality and with the state, with a step at state borders, and varied most between establishments and certifiers, "
        "more than with the wealth or the services of the place or the circumstances of the death; and it used the Black category for "
        f"{f2(il_pp)} of the infants of Black mothers. The design does not establish which "
        "classification is correct; it establishes that the certificate departs from both, by amounts that depend on place.")

d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
