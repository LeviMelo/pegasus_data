# The Discussion and references of paper 5. Executed by build.py after text_results.py.
# ruff: noqa: F821
_dn = MB_["natural"][0] - MB_["natural"][1]
assert all(2 <= (MB_[k][0] - MB_[k][1]) / _dn <= 4.5 for k in ("transport", "suicide", "assault by firearm")), "no longer about three times"
d.add_heading("Discussion", level=1)
para(d, "Young people who died of external causes in the smaller Brazilian municipalities were recorded White less often on the death certificate than at "
        "birth, by about three times as much as those who died of natural causes, and assaults no more than transport accidents or suicides. Hospital records "
        "made during their lives already showed most of that change for those who later died by assault: they had been recorded White less often than those "
        "who died of other causes. From the hospital record to the certificate the net change was small for every external cause; what distinguished violent "
        "deaths was that the two records agreed less, in both directions.")
para(d, f"Two readings were set against each other. Labelling at death would make the certificate darker than any record made in life, for violent deaths "
        f"above all, as found on United States certificates by cause of death {cite('noymer2011')}. Selection or reclassification in life would make the people "
        "who die violently already darker in the records of their lives. The data favour the second for the net change: those who were killed had been "
        "recorded White less often in hospital, and the certificate, net, was about as dark as that record. The first survives in a weaker form: certificates "
        "of violent deaths departed from the hospital's record more often, in both directions, which is what a classification made from a body and the "
        "circumstances of death, with no family to ask, would produce. Race read as a status marker changes over a life "
        f"{cite('saperstein2010', 'penner2008')}; here the change is visible years before death.")
para(d, "The mother's schooling at birth ordered the certified race for every cause, and for assaults more steeply: young people of less schooled mothers "
        "were certified darker. Social position at birth, the circumstances of a life and the manner of death all move the record, and the design separates "
        "only the last from the others.")
para(d, "Strengths and limitations. The study follows the same young people through records made by different observers at birth, in life and at death, "
        "counts each person once, and measures chance agreement with a negative control and a shifted-date placebo. Limitations: it covers the smaller "
        "municipalities, where a birth date, sex and municipality are shared by few people; the capitals and large cities, where most homicides occur, cannot be "
        "reached without identified records, which require a data-use agreement (the Center for Data and Knowledge Integration for Health's 100 Million "
        "Cohort, or a state health secretariat); people who moved are not found, about half of the deaths, alike for every cause; only a fifth of those who "
        "died by violence had an earlier admission, a selected group; the birth, hospital and certificate shares are compared on overlapping, not identical, "
        "sets of deaths; the race at birth is the newborn's colour recorded by staff; the placebo shows a residual of chance agreement of about a tenth of the "
        "estimate for violent deaths; and the standard errors of the birth estimates omit the variance of their denominator.")
para(d, "Implications. Rates of homicide by race in Brazil take the victim's race from a certificate that, in these municipalities, classes victims about "
        "as hospital staff did during their lives and darker than at birth. The racial gap in violent death is not mainly made at death; that it is so for "
        "the large cities requires identified linkage.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Young people who died violently were recorded darker than at birth, and the change was already "
        "present in hospital records made during their lives; the certificate after a violent death departed from those records more often but, net, not "
        "darker.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
