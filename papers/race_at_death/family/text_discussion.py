# The Discussion and references of paper 4. Executed by build.py after text_results.py.
# ruff: noqa: F821
d.add_heading("Discussion", level=1)
para(d, "In two national censuses twelve years apart, Brazilian households reported most children in the mother's race when she was White or Brown, and fewer "
        "than half of Black mothers' children as Black. Among children of both members of the couple, the mother's and the father's races counted about alike; "
        "a stepfather counted less than a father; full siblings of mixed couples shared a classification more than chance but often differed; and where the "
        "partner answered for both the mother and the child, the child was reported closer to his race. Between 2010 and 2022 the classification changed "
        "by less than three percentage points.")
para(d, "Several readings of the partner's association were set against each other. If the household applied a rule to all its children, such as the "
        "father's race or the lighter of the two, full siblings would share a category, which two in five mixed households did not. If the report read each "
        "child's descent and appearance, the father would count far more than a stepfather and siblings would differ, as they did; but appearance is not "
        "observed, and the same pattern arises if mothers who form unions with White men are themselves lighter within the Brown category, a selection the "
        "stepfather contrast reduces but does not remove. If the respondent reported his or her own reading, the answer would lean toward the respondent's "
        "race; it did only where the partner answered for both the mother and the child, and only for non-White mothers, which points to one respondent "
        "classifying the whole household rather than to each informant pulling the child. The finding extends the observation that educated non-White "
        f"parents classify children as White in part through whom they marry {cite('schwartzman2007')}: the partner's race counts about as much as the "
        "mother's, and mostly when he is the father.")
para(d, "The changes between the censuses were small, and their sign depended on schooling. Schooling rose for mothers of every race, and more schooled "
        "mothers report lighter children; at the 2010 mothers' schooling and region, the children of White and Brown mothers were reported White less often in "
        "2022, a darkening within equal schooling of the kind surveys found in adults' own identification in the period " + cite('freemannc2024') + ". "
        "Fewer Brown mothers had White partners, while among White fathers the share of White children rose.")
para(d, "Black mothers' children were reported Black more often at older ages, and the whole-population cohort series showed the largest falls of White "
        "between a census at ages 0-4 and the next at ages 10-17, while households still report for them. Reclassification between censuses has "
        f"been described before {cite('carvalho2004')}; the cohort series also reflects mortality, migration and coverage, and two cross-sections cannot "
        "separate age from cohort or from the change of who reports.")
para(d, "Strengths and limitations. The study uses the public-access samples of two censuses with design-based errors, one pairing rule applicable in both "
        "and checked against the mother's order number in 2010, the relationship codes that tell a father from a stepfather, and the record of who answered "
        "for each person. Limitations: the pairs are children of the household's couple living with the mother, about four in five of the children aged 0-9 "
        "the 2010 order number pairs, leaving out children in their grandparents' households; the rule cannot be checked in 2022, where the mother may be a "
        "stepmother; the 2022 public file gives five-year ages and no municipality; who answered is not random; the intervals ignore imputation of race and "
        "the change of the questionnaire; the father-stepfather contrast is unadjusted; and Yellow and Indigenous mothers, whose numbers changed most between "
        "the censuses, are not analysed.")
para(d, "Implications. Statistics that take children's race from the household inherit a classification that follows both parents and the person who "
        "answers for the household. Records that carry the mother's own declaration, such as the live birth record, can be expected to differ from them for "
        "children of mixed couples even without error in either source, a hypothesis that linked records could test.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Households reported children by both parents about equally, by the father more than a stepfather, "
        "with siblings of mixed couples often classified apart, and closer to the partner's race when he answered for both mother and child; the classification "
        "changed little between 2010 and 2022.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
