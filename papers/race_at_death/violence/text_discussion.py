# The Discussion and references of paper 5. Executed by build.py after text_results.py.
# ruff: noqa: F821
assert all(2.5 <= BC[k]["net_shift"]["est"] / BC["natural"]["net_shift"]["est"] <= 4 for k in ("transport", "suicide", "assault by firearm", "other assault")), "no longer about three times"
assert all(TR[g]["birth_white"]["est"] > TR[g]["hospital_white"]["est"] for g in TR), "the hospital is no longer darker than birth for every cause"
d.add_heading("Discussion", level=1)
para(d, "Young people who died of external causes in the smaller Brazilian municipalities were certified White less often than they had been recorded at "
        "birth, by about three times as much as those who died of natural causes, and assaults no more than the other external causes. For the same deaths, "
        "the change from birth to the hospital record was alike for every cause; the difference between causes arose afterwards, between the last hospital "
        "record and the certificate, where natural deaths regained part of the White category and violent deaths did not.")
para(d, f"Three readings were set against each other. If the young people who die violently were reclassified in life, the hospital record would already be "
        "darker for them than for others, relative to birth; it was not: every cause lost about the same share White between birth and hospital, and the "
        "lower hospital share of victims of assault restates their lower share at birth. If the classification were made at death, the certificate would "
        "depart from the last record of life by cause, as on United States certificates by cause of death " + cite('noymer2011') + "; it did, by about "
        f"{100 * -H_ASS['est']:.0f} points between assaults and natural deaths. A third reading is that hospital clerks code darker than other observers; the "
        "hospital record was darker than the birth record for every cause, and darker than the certificate in the admission of the death itself, so the "
        "hospital is not a neutral reference of life, and the comparison between causes, not the level, carries the inference. Race read as a status marker "
        f"changes with circumstances {cite('saperstein2010', 'penner2008')}; here it changed between records made by different observers, by an amount that "
        "depended on the observer more than on the cause, except at death.")
para(d, "Who certified did not explain the difference: assaults were certified White less often among those White at birth whether a medical examiner or an "
        "attending physician signed. The mother's schooling at birth ordered the certified race for every cause.")
para(d, "Strengths and limitations. The study follows the same deaths through records made at birth, in life and at death, counts each person once, measures "
        "chance agreement with a negative control and shifted-date placebos, and compares the causes on one population. Limitations: it covers the smaller "
        "municipalities, where a birth date, sex and municipality are shared by few people; the capitals and large cities, where most homicides occur, cannot be "
        "reached without identified records, which require a data-use agreement; people who moved are not found, about half of the deaths, alike for every "
        "cause; only about a fifth of those who died by violence had an earlier admission, a selected group, and about a third of the persons found carried no "
        "race on their admissions; the race at birth is the newborn's colour recorded by staff; the placebo leaves a residual of chance agreement of about a "
        "tenth of the persons found for violent deaths, which pulls their hospital shares toward the municipality's population; and the strata of Figure 3 come "
        "from a tabulation with a different set of municipalities and intervals that omit the variance of their denominator.")
para(d, "Implications. Rates of homicide by race in Brazil take the victim's race from a certificate that, in these municipalities, records victims as White "
        "less often than their birth records did, by more than for natural deaths; part of that difference is made at death. Whether this holds in the large "
        "cities requires identified linkage.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Young people who died of external causes were certified White less often than at birth, by more than "
        "those who died of natural causes; the change from birth to the hospital record was the same for every cause, and the difference by cause arose "
        "after it, on the certificate.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
