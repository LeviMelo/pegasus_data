# The Discussion and references of paper 3. Executed by build.py after text_results.py.
# ruff: noqa: F821
assert PHY["KK"]["all"]["physician"] < PHY["KK"]["all"]["death_estab"] or PHY["KK"]["all"]["physician"] < 0.1, "physicians now dominate: rewrite the Discussion"
assert MV and MV["movers_practice_slope"]["est"] - 2 * MV["movers_practice_slope"]["se"] > 0.5, "a mother's record no longer follows her hospital: rewrite"
assert MV["declared_again|black"]["est"] < MV["declared_again|white"]["est"] < MV["declared_again|brown"]["est"], "the declaration's stability changed"
assert R3["within_hospital_by_visits"]["none"]["lo"] > 1 and R3["home_deaths"]["mh_over_regions"]["lo"] > 1, "the association vanished where no shared record is likely"
assert 0.3 < R3["practice_per_sd"]["share_through_mothers_record"] < 0.7, "the practice's share through the mother's record is no longer about half"
d.add_heading("Discussion", level=1)
para(d, f"The infants of mothers who declared themselves Black were recorded as Black on a minority of death certificates: for the same "
        f"{n0(R3['n'])} infants, the hospital had recorded the mother as Black in {f2(R3['hospital_black_same_infants'])} and the certificate the infant in "
        f"{f2(R3['certified_black_same_infants'])}, and counted net the certificates recorded {f2(MB['net']['certificate_ratio']['est'])} as many infants as Black as "
        "there were infants of Black mothers. The certificate went with how the same mother was recorded at delivery, within the delivery hospital and also "
        "where the infant died elsewhere, at home or after no prenatal visit. The delivery hospital's practice went with the certificate too, about half of it "
        "through how the hospital recorded the mother herself. The category's use rose over the decade, faster on the certificate than in the hospital.")
para(d, "Several readings were set against each other (Table 1). If the certificate copied the delivery chart, the association would vanish where the chart "
        "was not at hand; it remained at a similar size among infants who died in another establishment. If a shared upstream record carried the same entry to "
        "every later record, such as the prenatal card or the national health card, the association would weaken among mothers with no prenatal visit and "
        "among deaths at home; it did not. If a hospital-wide practice decided the category, a mother's record would follow her hospital; it did, by about "
        f"the full difference in practice when she changed hospital (slope {f2(MV['movers_practice_slope']['est'])}, 95%CI "
        f"{f2(MV['movers_practice_slope']['est'] - 1.96 * MV['movers_practice_slope']['se'])}; {f2(MV['movers_practice_slope']['est'] + 1.96 * MV['movers_practice_slope']['se'])}), and a mother recorded Black at one delivery was recorded Black again in the same hospital far "
        f"more often (odds ratio about {OR_SAME:.0f}) than in another (about {OR_OTHER:.1f}), which is also what a hospital copying its own earlier file would "
        "produce. Beyond the hospital's level, a person component remained: across hospitals, being recorded Black once still raised the odds of being "
        "recorded Black again, and within hospitals the mother's record went with the certificate. The data are compatible with staff in different places "
        f"reading the same person alike at levels each institution sets, as studies of classification by observers describe {cite('telles2002', 'monk2016')}; "
        f"they are equally compatible with the mother's own varying self-classification {cite('muniz2022')} reaching the hospital and the informant at death. "
        "Appearance and the informant are not recorded, so the shared element cannot be named.")
para(d, "The mother's declaration is itself entered by staff on her answer. Within the same hospital, who filled the record changed the share declared Black by "
        f"about one percentage point, a small difference against a share of {pct(FLR['nursing']['black_declared_share'], 1)}; it does not separate the mother's "
        "answer from the hospital's way of asking. The declaration is not stable: of mothers who declared themselves Black at one birth, "
        f"{f2(MV['declared_again|black']['est'])} did so again at the next, against {f2(MV['declared_again|white']['est'])} of White and "
        f"{f2(MV['declared_again|brown']['est'])} of Brown mothers, after the chance pairs were removed. It is the reference here, not a truth. The infant's own "
        "race is not observed: the unit of this study is the infant of a Black mother, whose race also depends on the father and is reported by families "
        "lighter than the mother's for young children (a companion paper). That a minority of these infants were certified Black measures how the certificate "
        "uses the category for the children of Black women, not how many infants were Black.")
para(d, "The rise over 2013-2023 was faster on the certificate than in the hospital also without 2023, the year the hospital's race field changed, and it was "
        "not explained by the region, schooling and age of the Black mothers; it coincided with more mothers declaring themselves Black on birth records and "
        f"with a darkening of racial identification in surveys of the period {cite('freemannc2024')}. Whether certifiers responded to that change or to "
        f"training cannot be tested here. A change in how race was recorded on birth records in 2012 changed infant mortality by race {cite('caldas2022')}; the "
        "records filled by staff move separately from the mother's declaration and at different speeds.")
para(d, f"Read against the right comparator for each record, the ladder is shorter than against the mother's declaration taken as 1. The same "
        f"mother declared herself Black again at her next birth in {f2(AGAIN['est'])}, so a record of her at another time and by other people cannot be "
        f"expected to reach 1: the hospital's {f2(HO['black_bootstrap']['black']['est'])} is below her own repetition. The infant is not the mother, and "
        f"families report Black mothers' children under one as Black in {f2(LD['family_child_0'])}: the certificate's {f2(LD['certificate_infant']['est'])} "
        "is below half of that. The birth record itself counts fewer Black mothers than the census where hospitals use the category least, so these "
        "levels are, if anything, measured against a reference that already leans away from Black.")
para(d, "Strengths and limitations. The study follows the same families through linked records nationally over eleven years, with one-to-one linkage of the infant "
        "to the birth and of the birth to the delivery, separates gross from net classification, and sets copying, a shared upstream record, practice and the "
        "person against each other. Limitations: the reference is the mother's declaration, entered by staff; the infant's own hospital record was not used; the "
        "hospital record covers deliveries in the public system, about half of the infants' mothers, though infants with and without it were certified Black in "
        "the same proportion; hospitals that recorded a default Yellow were left out, and a hospital's blanks were bounded rather than imputed; the same mothers "
        "across births were identified by birth date and residence in smaller municipalities, with a measured share of chance pairs; the certifying physician is "
        "filed only in 2014-2018, with few deaths per physician; the estimate after infancy rests on an estimator that loses precision in the largest "
        "municipalities; and the analyses beyond the two primary ones are exploratory.")
para(d, "Implications. Taking the mother's declaration as the reference, hospital and death records count fewer of the Black population as Black, the infant "
        "certificate least, by amounts that differ between hospitals; grouping Black and Brown as negros removes that difference from comparisons with White "
        "people but not from statistics of the Black population itself. Recording who informed the race on the certificate would show where the category is lost.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The infants of Black mothers were recorded as Black on a minority of certificates, fewer than the hospitals "
        "recorded their mothers; the certificate went with how the same mother was recorded, within levels each hospital sets, also where no chart or shared "
        "record was likely at hand; and the category's use rose over the decade faster on the certificate than in the hospital.")
PPS = R3["practice_per_sd"]
RD3 = [["Copying the delivery chart", "association only where the infant died where it was delivered",
        f"{f2(CL_T['or'])} there, {f2(CL_E['or'])} ({f2(CL_E['lo'])}; {f2(CL_E['hi'])}) elsewhere", "no"],
       ["A shared upstream record (prenatal or health card)", "association weak with no prenatal visit and in deaths at home",
        f"no visit {f2(R3['within_hospital_by_visits']['none']['est'])} ({f2(R3['within_hospital_by_visits']['none']['lo'])}; "
        f"{f2(R3['within_hospital_by_visits']['none']['hi'])}); home {f2(R3['home_deaths']['mh_over_regions']['est'])}", "no"],
       ["A hospital-wide level", "a mother's record follows her hospital; practice goes with the certificate",
        f"slope {f2(MV['movers_practice_slope']['est'])}; practice {f2(PPS['practice_composition_region_year']['or_per_sd'])} per SD, "
        f"{pct(PPS['share_through_mothers_record'], 0)} through the mother's record", "yes"],
       ["The hospital copies its own earlier file", "persistence far higher in the same hospital than in another",
        f"odds ratio about {OR_SAME:.0f} against {OR_OTHER:.1f}", "compatible"],
       ["The person as staff see her, or her own varying answer", "association within hospitals and across hospitals",
        f"{f2(CL_D['or'])} within; {OR_OTHER:.1f} across", "compatible; not separable"],
       ["The certifying physician", "large variance between physicians", f"physicians {f2(PHY['KK']['all']['physician'])}, establishments "
        f"{f2(PHY['KK']['all']['death_estab'])} (few deaths per physician)", "partly"],
       ["The rise is who declares", "no rise at the mothers of 2013", f"{f2(STD['2013']['standardised_2013'])} to {f2(STD['2022']['standardised_2013'])} by 2022; "
        f"certificate faster than the hospital, {f2(R3['joint_trend_2013_2022']['hospital_minus_certificate'])} per decade in log-odds (2013-2022)",
        "not explained by region, schooling and age"]]
table(d, "Table 1 - Readings of who records the infant of a Black mother as Black, what each predicts, and what the data showed, Brazil, 2012-2023",
      ["Reading", "Prediction", "Result", "Does the result fit the reading?"], RD3,
      ["Odds ratios from conditional and clustered logistic models and Mantel-Haenszel estimates; see Results. No: the predicted pattern was absent, with an "
       "interval excluding it. Yes or compatible: the pattern was present; compatible readings are not separated by these data."])
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
