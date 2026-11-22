# The Discussion and references of paper 4. Executed by build.py after text_results.py.
# ruff: noqa: F821
d.add_heading("Discussion", level=1)
para(d, "In two national censuses twelve years apart, Brazilian households reported most children in the mother's race when she was White or Brown, and fewer "
        "than half of Black mothers' children as Black. The child's race followed the couple, and mostly the father: a White father made a Brown mother's "
        "child White in more than half of households, a White stepfather in about a third. Siblings of mixed couples were often reported in different races, "
        "and the child leaned toward the race of the parent who answered.")
para(d, "Three readings of the partner's association were set against each other. If the household applied a rule, such as giving the children the "
        "partner's race or the lighter of the two, siblings would share a category and a stepfather would count as much as a father. If the report read the "
        "child's descent or appearance, the father would count far more than a stepfather and siblings of mixed couples would often differ. If the informant "
        "reported his or her own reading, the answer would lean toward the informant's race. The data fit the second and third readings: the father's gap "
        "was two to three times the stepfather's, about two in five mixed couples' households reported their children differently against one in seven "
        "Brown couples', and the child leaned toward the answering partner's race in every couple type examined. The stepfather's residual effect and "
        "the higher share of White children among Black stepfathers than Black fathers suggest that the mother's earlier partner, absent from the household, "
        "also counts, which these data cannot show. The finding refines the observation that educated non-White parents classify children as White in part "
        f"through whom they marry {cite('schwartzman2007')}: at equal schooling the partner's race multiplied the odds about ninefold, and much of that is the "
        "father's.")
para(d, "The changes between the censuses are small and depend on who the mothers were. Women reporting themselves Black in 2022 were far more schooled than "
        "in 2010, consistent with the darkening of adults' identification in the period " + cite('freemannc2024') + "; given the 2010 mothers' "
        "schooling and region, Brown mothers' children were reported White slightly less often in 2022, not more. Within White fathers the share rose, and "
        "fewer Brown mothers had White partners. Census cohorts as a whole were reported White less often at each later census, as reclassification between "
        f"censuses has been described before {cite('carvalho2004')}; that series also reflects mortality, migration and coverage, and does not identify "
        "reclassification.")
para(d, "Black mothers' children were reported Black more often at older ages. Age, cohort and the changing set of reporters cannot be separated with two "
        "cross-sections: the children of 2010 at 10-14 years in 2022 were reported Black about half as much more often as the 2010 cross-section's "
        "gradient implies, and the pairs keep a different share of children at each age, rising from 0-4 to 10-14 and falling after.")
para(d, "Strengths and limitations. The study uses the public-access samples of two censuses with design-based errors, one pairing rule applicable in both "
        "and checked against the mother's order number in 2010, and the relationship codes that tell a father from a stepfather. Limitations: the pairs are "
        "children of the household's couple living with the mother, about four in five of the children aged 0-9 the 2010 order number pairs, leaving out "
        "children in their grandparents' households; the rule cannot be checked in 2022; the 2022 public file gives five-year ages and no municipality; who "
        "answered is not random; the sampling intervals ignore imputation of race and the change of the questionnaire; and Yellow and Indigenous mothers, "
        "whose numbers changed most between the censuses, are not analysed.")
para(d, "Implications. Statistics that take children's race from the household inherit a reading of the child that follows the father and the person "
        "answering; records that carry the mother's declaration, such as the live birth record, will differ from them for children of mixed couples even "
        "without error in either source.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Households reported children by the couple, mostly by the father, differently between siblings of "
        "mixed couples and toward the race of whoever answered; the national changes between 2010 and 2022 were small and depended on who the mothers of "
        "each category were.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
