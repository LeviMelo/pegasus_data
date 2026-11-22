# The Discussion and references of paper 4. Executed by build.py after text_results.py.
# ruff: noqa: F821
d.add_heading("Discussion", level=1)
para(d, "In two national censuses twelve years apart, Brazilian households reported most children in the mother's race when she was White or Brown, and fewer "
        "than half of Black mothers' children as Black. The partner shaped the child's race more than the mother's schooling, the region or the census: a "
        "White partner made a Brown mother's child White in more than half of households, and in more of them in 2022 than in 2010, while a Black mother's "
        "child was reported Black mostly when the partner was Black too. Children were reported Black more often as they grew older, and in 2022 the answer "
        "hardly depended on whether the mother or another resident gave it.")
para(d, f"The rise in whitening by White partners runs against the darkening of identification reported in surveys of the same period {cite('freemannc2024')} "
        f"and against the census cohorts' move out of the White category, which the present series confirms {cite('carvalho2004', 'marteleto2012')}. The two "
        "need not conflict. Adults darken their own identification, and the cohorts' change is measured mostly on adults reporting for themselves or their "
        "peers, while the child's race at 0-9 years is decided for the child at a moment when the parents' combination is what the household reports. The "
        f"finding extends the observation that educated non-White parents classify children as White in part through whom they marry {cite('schwartzman2007')}: "
        "at equal schooling, the partner's race multiplied the odds roughly ninefold, and the mother's schooling by little more than one third.")
para(d, "The age gradient among Black mothers' children is the same cohorts reported darker as they grow, since the share at 0-4 years did not change "
        "between the censuses while the children of 2010 were reported Black more often at 10-14 in 2022. Two readings fit. Households may report a young "
        "child in the lighter category and move to Black as the child's appearance, school and social experience settle; or the children who stay in the "
        "household as they grow differ from those who leave. Co-residence fell from about nine in ten at 0-4 years to half at 20-24, so the second reading "
        "can explain the older ages but not the change between 0-4 and 10-14, when most children still live with the mother.")
para(d, "That another resident answered as the mother did suggests that the household, not the individual informant, holds the classification of the "
        "child. Non-resident informants, who answer for households no one else in which could be interviewed, gave the mother's race more often, as a "
        "proxy who knows only the mother would.")
para(d, "Strengths and limitations. The study uses the complete samples of two censuses with design-based errors and one pairing rule valid in both, which "
        "reproduced the mother's order number in 2010. Limitations: the pairs are children of the household's couple living with the mother, a selection that "
        "grows with age; the 2022 public file gives five-year ages and no municipality, so the analysis of place is by region; the mother's race is itself "
        "the household's report, given by her in most cases; the partner is the man of the couple and may not be the father; the 2022 public file has no "
        "weighting area, so the strata are states; Yellow and Indigenous mothers are too few for most comparisons; and the census series of cohorts mixes "
        "reclassification with mortality, migration and coverage.")
para(d, "Implications. Health statistics that take children's race from the household inherit a classification that follows the father as much as the "
        "mother and darkens with age; comparisons with records that carry the mother's declaration, such as the live birth record, should expect Black "
        "children to be counted differently by the two sources even without error in either.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Households classified children by the couple, not by the mother alone, darker with age, in much the "
        "same way whoever in the household answered; mixed unions with White partners whitened children more in 2022 than in 2010.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
