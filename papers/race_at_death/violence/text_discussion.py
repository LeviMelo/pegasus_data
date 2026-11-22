# The Discussion and references of paper 5. Executed by build.py after text_results.py.
# ruff: noqa: F821
assert hw_fire["est"] + 2 * hw_fire["se"] < hw_nat["est"] - 2 * hw_nat["se"], "the earlier hospital record no longer separates the causes"
d.add_heading("Discussion", level=1)
para(d, f"Young people who died by assault were certified in a darker category than their race at birth far more often than those who died of natural "
        f"causes: of those recorded White at birth, about {f2(fire['est'])} of firearm deaths and {f2(nat['est'])} of natural deaths were certified White. The "
        f"departure held at equal municipal composition, in every region, in both halves of the decade, for deaths in the street and in health facilities, and "
        f"within deaths certified by medical examiners. The same young people's earlier hospital admissions, recorded while they were alive, called White "
        f"most of those later certified Brown after an assault: of those a hospital had recorded White, {f2(hw_fire['est'])} of firearm deaths were certified White, "
        f"against {f2(hw_nat['est'])} of natural deaths.")
para(d, "Two readings were set against each other. Selection in life would mean that the young people who are killed had already become Brown, in their own "
        "declarations and in the eyes of others, before they died, so that the certificate reports a classification made in life. Labelling at death would mean "
        "that the certificate classes them darker because of how they died. An earlier hospital record is a classification made in life by staff who saw the "
        "person; under selection it should already show the victims as Brown. It did not: among young people a hospital had recorded White, the certificate "
        "called half of the firearm deaths Brown and a sixth of the natural deaths. The departure is made at death, or between the last admission and death, "
        "and it is largest where the certifier, a medical examiner, sees a body with wounds and knows the circumstances. This is what studies of observer "
        f"classification predict when race is read as a status marker {cite('saperstein2010', 'penner2008')}, and what was found on United States certificates "
        f"by cause of death {cite('noymer2011')}.")
para(d, "The mother's schooling at birth ordered the departure, as it ordered the certified race of natural deaths: young people of less schooled mothers were "
        "certified darker after every cause. Social position at birth and the manner of death both moved the certificate, and the second did so at every level "
        "of the first.")
para(d, "Strengths and limitations. The study follows the same young people from birth to death through records made by different observers, with the "
        "chance agreement measured by a negative control, and tests the two readings against a record made in life. Limitations: it covers the smaller "
        "municipalities, where a birth date, sex and municipality are shared by few people; the capitals and large cities, where most homicides occur, cannot be "
        "reached without identified records, which the public files do not carry and which require a data-use agreement (the Center for Data and Knowledge "
        "Integration for Health's 100 Million Cohort, or a state health secretariat); people who moved are not found, about half of the deaths, alike for every "
        "cause; the race at birth is the newborn's colour recorded by staff, not a declaration; the hospital record is that of admissions in the public system, "
        "weighted by their number, and some years have the race blank on a quarter of admissions; and the standard errors of the estimator omit the variance of "
        "its denominator.")
para(d, "Implications. Rates of homicide by race in Brazil take the victim's race from a certificate that classes victims darker than their earlier records, "
        "so part of the racial gap in homicide rates is made at death. The size of that part in the large cities, and its direction for Black victims, "
        "require identified linkage. Recording whether the race on the certificate was asked of a relative, and comparing it with the hospital and birth "
        "records already linked by health secretariats, would measure it.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Young people who died by assault were certified darker than their race at birth, and darker than "
        "earlier hospital records of the same people, much more often than those who died of other causes: the departure arises at death.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
