# The Discussion and references of paper 5. Executed by build.py after text_results.py.
# ruff: noqa: F821
assert all(2.5 <= BC[k]["net_shift"]["est"] / BC["natural"]["net_shift"]["est"] <= 4 for k in ("transport", "suicide", "assault by firearm", "other assault")), "no longer about three times"
assert all(TR[g]["birth_white"]["est"] > TR[g]["hospital_white"]["est"] for g in TR), "the hospital is no longer darker than birth for every cause"
d.add_heading("Discussion", level=1)
para(d, "Young people who died of external causes in the smaller Brazilian municipalities were certified White less often than they had been recorded at "
        "birth, by about three times as much as those who died of natural causes, whatever the external cause: assaults changed as transport deaths did. For "
        "the same deaths, the change from birth to the hospital record was alike for every cause; the difference arose on the certificate. Where the death "
        "occurred carried part of it: away from a health establishment natural deaths changed as much as external ones, and with the natural deaths' places "
        "of death the assaults' difference halved, while that of the other external causes stayed.")
para(d, f"Four readings were set against each other. If the young people who die of external causes were reclassified in life, the hospital record "
        "would already be darker for them than for others, relative to birth; it was not, within about five points. If the classification were made at "
        f"death because of the cause, as on United States certificates {cite('noymer2011')}, the certificate would depart from the records of life by cause at "
        f"any place of death; it did, by about {100 * -H_ASS['est']:.0f} points between assaults and natural deaths from the earlier admissions, and part of it "
        "remained with the place of death held. If instead what matters is who can answer for the race, a family present at a death in hospital against a "
        "body examined after a death elsewhere, the difference would follow the place of death across causes; it did in part: natural deaths away from a "
        "health establishment changed as much as external ones, and about half of the assaults' difference went with where they died. The two readings meet "
        "in the law: every death from an external cause goes to the medico-legal institute, wherever it occurs, so the cause decides who certifies and "
        f"whether a family is asked. A fourth reading, that hospital clerks code darker than other observers, explains the level, not the contrast: the "
        f"hospital record was darker than birth for every cause. Race read as a status marker {cite('saperstein2010', 'penner2008')} changed here between "
        "records made by different observers, by an amount that depended on the observer and the place more than on the kind of external cause.")
para(d, f"Who assigns race at a death from an external cause is documented: at medico-legal institutes the dead cannot declare it, and the examiner assigns it, "
        f"often imprecisely and with little weight {cite('santos2013', 'rodrigues2012')}; the certificate means different things to physicians depending "
        f"on how the death occurred {cite('melo2013')}. The completeness of the race field, which has improved {cite('romero2019')}, says nothing of its "
        f"agreement with earlier records. Studies of homicide by race {cite('soaresfilho2011', 'cerqueira2014', 'aiquoc2022')} take the certificate's race "
        "as given.")
para(d, "Within external causes, the certifier recorded on the certificate (medical examiner or attending physician) did not order the change "
        "among those White at birth, but the certifier field does not say who gave the race; the place of death, which does bear on it, did. The mother's "
        "schooling at birth ordered the certified race for every cause.")
para(d, "Strengths and limitations. The study relates the same deaths, without identifiers, to records made at birth, in life and at death, counts each person once, measures "
        "chance agreement with a negative control and shifted-date placebos, and compares the causes on one population. Limitations: it covers the smaller "
        "municipalities, where a birth date, sex and municipality are shared by few people; the capitals and large cities, where most homicides occur, cannot be "
        "reached without identified records, which require a data-use agreement; people who moved are not found, about half of the deaths, alike for every "
        "cause; only about a fifth of those who died of external causes had an earlier admission, a selected group, though one whose change from birth to the "
        "certificate matched that of all deaths found; about a third of the persons found carried no race on their admissions, more often after external-cause deaths; "
        "the time between the admission and the death, and the age at admission, were not examined; the race at birth is the newborn's colour recorded by staff; the placebo leaves a residual of chance agreement of about a "
        "tenth of the persons found for external-cause deaths, which pulls their hospital shares toward the municipality's population; and the strata of Figure 3 come "
        "from a tabulation with a different set of municipalities and intervals that omit the variance of their denominator. Who is found depends on the class "
        f"recorded: in the validation of the estimator, {pct(EF['Branca'], 0)} of White, {pct(EF['Preta'], 0)} of Black and {pct(EF['Parda'], 0)} of Brown people "
        "shared the key with their own record (companion paper). Such unequal finding raises the share White at birth among the deaths found by about one "
        "point for every cause alike; it would bias the contrast of causes only if it differed between causes by more than the contrast itself, which the "
        "data cannot test.")
_BVC = _json.loads((HERE / "results" / "birth_vs_census.json").read_text(encoding="utf-8")) if "_json" in globals() else __import__("json").loads((HERE / "results" / "birth_vs_census.json").read_text(encoding="utf-8"))
_HD = __import__("json").loads((HERE / "results" / "hospital_declaration.json").read_text(encoding="utf-8"))
_SL = _BVC["mothers_2010"]["W"]["slope_region"]["slope"]
_H0 = _HD["by_practice_fifth"][0]
assert _SL > 1 and _H0["dn_black"] < 0.6 * _H0["expected_black"], "the two findings about the reference changed: rewrite the paragraph on the reference"
para(d, f"The reference. Two findings of the companion papers weaken the birth record as the reference: it leans toward the local majority, recording mothers whiter than the census in whiter places and less White in less White ones (logit slope {_SL:.2f} within regions, 1 if it followed the census), and where hospitals rarely record Black on the admission it counts about half the Black mothers the census holds ({100 * _H0['dn_black']:.1f}% against {100 * _H0['expected_black']:.1f}%). "
        "Here the race at birth is the newborn's colour recorded by staff in 2000-2009, before the mother's declaration was introduced. If it "
        "leaned toward the local majority as the later field does, young people from less White places, more of those who died by assault, were recorded "
        "less White at birth than they would have declared, which makes their fall from birth to the certificate, and its contrast with natural deaths, "
        "if anything understated.")
para(d, "Implications. Rates of death from external causes by race in Brazil, homicide among them, take the race from a certificate that, in these "
        "municipalities, records the dead as White less often than their birth and hospital records did, more than for natural deaths and alike for every "
        "external cause. Recording on the certificate who informed the race, and asking a relative wherever one is reached, would let the field be audited. "
        "Whether this holds in the large cities requires identified linkage.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Young people in deaths from external causes, assaults no different from transport deaths, were "
        "certified White less often than their earlier records had them; the difference arose at death, partly with dying away from a health establishment "
        "and a family and partly with the external cause itself.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
