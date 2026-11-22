# The Discussion and references of paper 3. Executed by build.py after text_results.py.
# ruff: noqa: F821
d.add_heading("Discussion", level=1)
para(d, f"Black families were recorded as Brown more often than as Black in Brazil's health records. Counted net, hospitals recorded {f2(NT['hospital_ratio'])} as many "
        f"Black mothers as declared themselves Black, and death certificates {f2(NT['certificate_ratio'])} as many Black infants as there were infants of Black mothers. "
        "The certificate followed the record of the same mother: within the same hospital, the infant of a mother the hospital had recorded as Black was twice as likely "
        "to be certified Black. The category was used more for older children than for infants, less by verification services and medical examiners than by attending "
        "physicians, and more each year, faster on the certificate than in the hospital.")
para(d, "These results locate the boundary between preto and pardo inside the records that produce health statistics. Studies of classification by observers found "
        f"that disagreement concentrates at the darker end of the colour continuum {cite('telles2002')}, that classification moves in both directions over time "
        f"{cite('muniz2022')}, and that Black and Brown people differ in socioeconomic position and in the discrimination they report {cite('monk2016', 'daflon2017')}. "
        "Here the observers are hospital staff and certifiers. The net counts separate two things gross agreement mixes: at the hospital, the loss of Black mothers to "
        "the Brown category is half made up by Brown mothers recorded as Black, as expected when a small group is misclassified into a large one and back; on the infant "
        "certificate it is not, and the Black population is undercounted by two thirds.")
para(d, "Three explanations fit parts of the results. The first is that hospital staff and certifiers perceive the same mother and child, so that appearance leads "
        "both to the Black category; it fits the strong association within the same hospital between the hospital's record of a mother and her infant's certificate, "
        "which a hospital-wide practice cannot produce. The second is a practice of each institution: hospitals differed widely in how often they recorded Black "
        "mothers as Black, and the delivery hospital's practice predicted the certificates at equal composition, although part of this association can be the same "
        "perception of the populations each hospital serves. The third is the classification of infants as lighter than older children, by observers and, in the census, "
        "by families: the certificate used the category less for infants than for children of 1-9 years in the same municipalities. A certificate completed from the "
        f"record at hand rather than by asking the informant, against the Ministry's instruction {cite('manual_do2022')}, would carry both the hospital's perception and "
        "its practice to the certificate.")
para(d, "The rise over 2013-2023 was faster on the certificate than in the hospital, and coincided with more mothers declaring themselves Black on birth records and "
        f"with a darkening of racial identification in surveys of the period {cite('freemannc2024')}; whether certifiers responded to that change or to training cannot "
        f"be tested here. A change in how race was recorded on birth records in 2012 changed infant mortality by race {cite('caldas2022')}; the records that remain "
        "filled by staff, the hospital and the certificate, move separately from the mother's declaration and at different speeds.")
para(d, "Strengths and limitations. The study follows the same families through linked records nationally over eleven years, with one-to-one linkage of the infant "
        "to the birth and of the birth to the delivery, and separates gross from net classification. Limitations: the mother's declaration on the birth record is the "
        "reference, but it is itself entered by staff on the mother's answer; the hospital record covers deliveries in the public system, about half of the infants' "
        f"mothers, though infants with and without it were certified Black in the same proportion; hospitals that recorded a default Yellow were left out, and a default "
        f"Brown would go undetected; appearance is not recorded, so a shared perception of the same person cannot be told from a shared practice; the family's "
        "classification is from 2010 and concerns other, surviving children; the adult women's comparison is exploratory; the estimates after infancy rest on an "
        "estimator that loses precision in the largest municipalities; the multilevel models were fitted by an approximation (nAGQ = 0); and many contrasts are reported "
        "beyond the two primary analyses.")
para(d, "Implications. Counts of the Black population from hospital and death records undercount it, and death certificates of infants most, by amounts that differ "
        "between hospitals and places; grouping Black and Brown as negros removes that error from comparisons with White people but not from statistics of the Black "
        "population itself. Recording who informed the race on the certificate, and auditing hospitals' records against their patients' declarations, which linked "
        f"records already allow, would show where the category is lost. As committees now decide by observation who is Black in affirmative action {cite('silva2024')}, "
        "these records show how far observation and declaration diverge at the Black boundary.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The Black category was used for a minority of the children of Black mothers, least for infants, and on infant "
        "certificates the Black population was undercounted by two thirds even net; its use followed the record of the same mother and the hospital, varied with the "
        "certifier and the place, and rose over the decade faster on the certificate than in the hospital.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
