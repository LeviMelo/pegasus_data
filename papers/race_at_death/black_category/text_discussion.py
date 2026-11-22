# The Discussion and references of paper 3. Executed by build.py after text_results.py.
# ruff: noqa: F821
assert PHY["KK"]["all"]["physician"] < PHY["KK"]["all"]["death_estab"] or PHY["KK"]["all"]["physician"] < 0.1, "physicians now dominate: rewrite the Discussion"
assert MV and MV["movers_practice_slope"]["est"] - 2 * MV["movers_practice_slope"]["se"] > 0.8, "a mother's record no longer follows her hospital: rewrite"
assert MV["declared_again|black"]["est"] < MV["declared_again|white"]["est"] < MV["declared_again|brown"]["est"], "the declaration's stability changed"
d.add_heading("Discussion", level=1)
para(d, f"The infants of mothers who declared themselves Black were recorded as Black on a minority of death certificates: counted net, the certificates recorded "
        f"{f2(MB['net']['certificate_ratio']['est'])} as many infants as Black as there were infants of Black mothers, and hospitals recorded "
        f"{f2(MB['net']['hospital_ratio']['est'])} as many of the mothers themselves as Black as declared it. The certificate went with how the same mother was "
        "recorded at delivery, also when the infant died in another establishment, where the delivery chart was not at hand; beside the mother's own record, the "
        "hospital's practice added little. The category's use rose over the decade, faster on the certificate than in the hospital, and not because the "
        "Black mothers changed.")
para(d, "Three readings were set against each other (Table 1). If the certificate copied the delivery chart, the association between the hospital's record of a "
        "mother and her infant's certificate would vanish where the chart was not at hand; it remained, at a similar size. If a hospital-wide practice decided "
        "the category, the hospital's practice would predict the certificate as well as the mother's own record; it predicted it far less. The two are not "
        "exclusive, and the data show both. The hospital sets how often it records Black: a mother who changed hospital took on the new hospital's rate in "
        "full. Within that rate, which mothers it records Black is shared by the certifier of their infants wherever the infants die. Staff in different "
        f"places sort the same people alike, at levels each institution sets. This is what studies of classification "
        f"by observers describe at the darker end of the colour continuum {cite('telles2002', 'monk2016')}, and what is unstable over time and across "
        f"observers {cite('muniz2022')}. Appearance is not recorded, so the shared element cannot be named; the data show that it belongs to the person as staff see "
        "her, at a level the institution sets, and not to the chart.")
para(d, "The mother's declaration is itself entered by staff on her answer. Within the same hospital, who filled the record hardly changed the share declared "
        f"Black, which argues that the declaration is the mother's rather than the filler's. It is not stable: of mothers who declared themselves Black at "
        f"one birth, {f2(MV['declared_again|black']['est'])} did so again at the next, against {f2(MV['declared_again|white']['est'])} of White and "
        f"{f2(MV['declared_again|brown']['est'])} of Brown mothers, after the chance pairs were removed. The Black category is the least stable of the "
        "three in the mother's own answer too, and it remains the reference here, not a truth. The infant's own race "
        "is not observed: the unit of this study is the infant of a Black mother, whose race also depends on the father and is reported by families lighter "
        "than the mother's for young children (a companion paper). That a minority of these infants were certified Black therefore measures how the certificate "
        "uses the category for the children of Black women, not how many infants were Black.")
para(d, f"The rise over 2013-2023 was faster on the certificate than in the hospital and survived standardisation for who the Black mothers were; it coincided "
        f"with more mothers declaring themselves Black on birth records and with a darkening of racial identification in surveys of the period {cite('freemannc2024')}. "
        f"Whether certifiers responded to that change or to training cannot be tested here. A change in how race was recorded on birth records in 2012 changed "
        f"infant mortality by race {cite('caldas2022')}; the records that remain filled by staff move separately from the mother's declaration and at different speeds.")
para(d, "Strengths and limitations. The study follows the same families through linked records nationally over eleven years, with one-to-one linkage of the infant "
        "to the birth and of the birth to the delivery, separates gross from net classification, and tests copying, practice and the person against each other. "
        "Limitations: the reference is the mother's declaration, entered by staff; the hospital record covers deliveries in the public system, about half of the "
        "infants' mothers, though infants with and without it were certified Black in the same proportion; hospitals that recorded a default Yellow were left out, "
        "and a hospital's blanks were bounded rather than imputed; the same mothers across births were identified by birth date and residence in smaller "
        "municipalities, with a measured share of chance pairs; the certifying physician is filed only in 2014-2018; the estimate after infancy rests on an "
        "estimator that loses precision in the largest municipalities; and the analyses beyond the two primary ones are exploratory.")
para(d, "Implications. Counts of the Black population from hospital and death records undercount it, the infant certificate most, by amounts that differ between "
        "hospitals; grouping Black and Brown as negros removes that error from comparisons with White people but not from statistics of the Black population "
        "itself. Recording who informed the race on the certificate, and comparing hospital records with the birth record, which is also entered by staff but "
        "closer to the mother's answer, would show where the category is lost.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The infants of Black mothers were recorded as Black on a minority of certificates, fewer than the hospitals "
        "recorded their mothers; the category followed how the same person was recorded, within a level each hospital sets, not the chart, and it rose over the decade "
        "faster on the certificate than in the hospital.")
RD3 = [["Copying the delivery chart", "association only where the infant died where it was delivered",
        f"{f2(CL_T['or'])} there, {f2(CL_E['or'])} ({f2(CL_E['lo'])}; {f2(CL_E['hi'])}) elsewhere", "weakened"],
       ["A hospital-wide practice", "practice predicts the certificate as well as the mother's record; a mother's record follows her hospital",
        f"practice {f2(PL_['practice_person']['or_per_logit'])} beside the mother's record {f2(PL_['practice_person']['hb_or'])}"
        + (f"; a mother's record moved by {f2(MV['movers_practice_slope']['est'])} of the practice gap" if MV else ""), "sets the level"],
       ["The person as staff see her", "association everywhere, mother's record dominant", "as above", "sorts within the level; the element unnamed"],
       ["The certifying physician", "large variance between physicians", f"physicians {f2(PHY['KK']['all']['physician'])}, establishments "
        f"{f2(PHY['KK']['all']['death_estab'])}", "present, smaller than the establishment"],
       ["The reference is the filler's", "declared share varies with who filled the record within hospitals",
        f"{100 * w_ph['est']:.1f} and {100 * w_ot['est']:.1f} percentage points", "weakened"],
       ["The rise is who declares", "no rise at the mothers of 2013", f"{f2(STD['2013']['standardised_2013'])} to {f2(STD['2023']['standardised_2013'])}", "excluded"]]
table(d, "Table 1 - Readings of who records the infant of a Black mother as Black, what each predicts, and what the data showed, Brazil, 2012-2023",
      ["Reading", "Prediction", "Result", "Status"], RD3, ["Odds ratios from conditional and clustered logistic models; see Results."])
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
