# The supplement of paper 3. Executed by build.py after text.py, whose names it uses.
# ruff: noqa: F821
s = new_doc()
para(s, "Supplementary material - " + TITLE, bold=True)
T3 = R["triples"]
v_all = next(r for r in R["validation"] if r["size"] == "all")
s.add_heading("Supplementary Text S1 - Three readings of race for the same woman (exploratory)", level=2)
BD = T3["by_declared"]
para(s, f"Deaths of women aged 15 to 49 years in 2015 to 2022 in municipalities with fewer than 2,000 mothers on the birth records ({n0(T3['women_deaths'])} deaths) were "
        f"related to the birth records on which they were the mother, by birth date and municipality ({n0(T3['linked'])} pairs). These deaths were then related to the "
        "hospital admission that ended in death, through a probabilistic linkage of admissions in the Hospital Information System to death certificates on birth date, sex, "
        f"date of death and hospital. {n0(T3['with_three'])} women had the three races recorded; the mean estimated proportion of false pairs among them was "
        f"{pct(T3['false_share'])}. False pairs were removed in expectation, taking the declared race of a false pair to follow the racial composition of mothers in the "
        "region; intervals are from 400 bootstrap resamples of the women. The certificate recorded the race the woman had declared as a mother for "
        f"{ci(BD['Branca']['certificate'])} of White, {ci(BD['Parda']['certificate'])} of Brown and {ci(BD['Preta']['certificate'])} of Black women; the hospital record did "
        f"so for {ci(BD['Branca']['hospital'])}, {ci(BD['Parda']['hospital'])} and {ci(BD['Preta']['hospital'])} (Supplementary Table S1). For comparison, among "
        f"{n0(R['delivery']['pairs'])} delivery admissions of 2022 related to the birth record, the hospital recorded the declared race for "
        f"{f2(R['delivery']['hospital_as_declared']['Branca']['est'])} of White, {f2(R['delivery']['hospital_as_declared']['Parda']['est'])} of Brown and "
        f"{f2(R['delivery']['hospital_as_declared']['Preta']['est'])} of Black mothers.")
s.add_heading("Supplementary Text S2 - Estimation without individual linkage and its control", level=2)
para(s, "Let G be a group of deaths. For a death i, let C_i be the set of live births with the birth date, sex and municipality of residence of i. If the family did not "
        "move, exactly one element of C_i is the deceased; the remaining elements, and all elements when the family moved, are births that agree by chance. Write N(j, k) "
        "for the number of deaths in G with race j on the birth record and certified race k, and t for the probability that the deceased is in C_i. The expected number of "
        "candidates with race j among deaths certified k is t N(j, k) + E(j, k), where E(j, k) is the expected number of chance candidates.")
para(s, "E(j, k) depends on how many children were born on the birth date of the deceased in the municipality. That is not the number of an arbitrary day: a day on which "
        "more children were born contributes more people and therefore more deaths, so the birth date of a death is a size-biased draw from the days of the year, and a control "
        "drawn from other days would undercount E. The births of the other sex on the same day in the same municipality share the day, cannot contain the deceased and have the racial composition of that "
        "day's births; multiplied by the ratio of births of the two sexes in the municipality and year, their count estimates E(j, k). With this control the estimated t "
        f"for infants was {pct(v_all['candidates']['found'])} overall.")
para(s, "The estimator of t N(j, k) is the difference of the two counts. Its variance was approximated by the sum of the candidate count and the control count, which "
        "ignores the scaling factor of the control (close to 1). A proportion is a ratio of two such differences; the variance of its denominator was ignored, which "
        "understates the error of rows with few deaths. A twin of the same sex is a candidate and a twin of the other sex is in the control; both share the mother's race "
        "with the deceased. Mortality by the mother's race uses the shares of each race among the estimated deaths, so that t cancels provided it does not differ by race.")
BD = T3["by_declared"]
rows = [[EN[j], ci(BD[j]["hospital"]), ci(BD[j]["certificate"])] + [cc(BD[j]["certificate_given_hospital"][h]) for h in ("Branca", "Parda", "Preta")] for j in ("Branca", "Parda", "Preta")]
table(s, f"Supplementary Table S1 - Race recorded by the hospital and on the death certificate according to the race declared as a mother, women who died in hospital at "
         f"15-49 years, Brazil, 2015-2022 (n={n0(T3['with_three'])})",
      ["Declared race", "Hospital records the declared race (95%CI)", "Certificate records the declared race (95%CI)", "Certified as declared when the hospital recorded White (95%CI)",
       "When the hospital recorded Brown (95%CI)", "When the hospital recorded Black (95%CI)"], rows,
      ["95%CI: 95% confidence interval (bootstrap), after removal of the expected false pairs."])
RN = {"white": "White", "black": "Black", "brown": "Brown"}
rows = []
for lab, block in (("Black", IN["black_mother_by_hospital"]), ("Brown", IN["brown_mother_by_hospital"])):
    for h in ("black", "brown", "white"):
        if h in block:
            rows.append([lab, RN[h], n0(block[h]["black"]["n"])] + [ci(block[h][c]) for c in ("white", "brown", "black")])
table(s, *LADDER)
table(s, "Supplementary Table S3 - Certified race of infants according to the mother's declaration and the race the hospital recorded for the same mother at delivery, "
         "Brazil, 2013-2023",
      ["Mother's declaration", "Hospital's record of the mother", "Infant deaths", "Certified White (95%CI)", "Certified Brown (95%CI)", "Certified Black (95%CI)"], rows,
      ["Infant deaths linked to the birth record, the birth record linked to the delivery admission; binomial intervals."])
rows = [[RN[j], n0(HO["matrix"][j]["black"]["n"])] + [ci(HO["matrix"][j][h]) for h in ("white", "brown", "black")] for j in ("white", "brown", "black")]
rows += [[f"Black, births of {y}", n0(v["n"]), "-", "-", ci(v)] for y, v in HO["black_by_year"].items()]
table(s, "Supplementary Table S4 - Race recorded by the hospital at delivery according to the race the mother declared on the birth record, and for Black mothers by year "
         "of birth, Brazil, 2012-2023",
      ["Mother's declaration", "Admissions", "Hospital: White (95%CI)", "Hospital: Brown (95%CI)", "Hospital: Black (95%CI)"], rows,
      [f"Delivery admissions in the public system linked to the birth record; hospitals recording over a tenth of patients as Yellow left out ({HO['facilities_left_out']}). "
       f"Hospitals with 30 or more Black mothers: {n0(HO['facilities']['n'])}; share recorded Black at the 10th, 50th and 90th percentiles "
       f"{f2(HO['facilities']['p10'])}, {f2(HO['facilities']['p50'])}, {f2(HO['facilities']['p90'])}."])
LAB = {"null": "none", "composition": "composition", "socioeconomic": "socioeconomic context and place", "services": "services and recording",
       "composition_socioeconomic": "composition + socioeconomic", "socioeconomic_services": "socioeconomic + services",
       "composition_socioeconomic_services": "composition + socioeconomic + services", "full": "all, with individual variables, region and year",
       "individual_only": "individual variables, region and year", "individual_no_region": "individual variables and year"}
SQ = ML["sequence"]
rows = [[kl, f"{SQ[k]['var_mun']:.3f}", pct(SQ[k]["pcv"]), f2(SQ[k]["mor"])] for k, kl in LAB.items() if k in SQ]
table(s, "Supplementary Table S5 - Between-municipality variance of being certified Black, infants of Black mothers, under successive fixed parts of a multilevel "
         "logistic model, Brazil, 2013-2023",
      ["Fixed part", "Municipal variance (log-odds)", "Variance explained", "Median odds ratio"], rows,
      [f"Random intercept for the municipality, nAGQ = 0; {n0(ML['n'])} deaths in {n0(ML['municipalities'])} municipalities. With a crossed random effect for the "
       f"establishment of death: {f2(EST['var_estab'])} between establishments, {f2(EST['var_mun'])} between municipalities."])
figure(s, "black_practice", "Supplementary Figure S1 - Each hospital's practice against the certificates of Black mothers' infants who died there, Brazil, 2012-2023",
       ["Hospitals with 10 or more deaths of Black mothers' infants; practice, share of Black mothers recorded Black at delivery, 2012-2023; area, deaths; the dotted "
        "line is equality."])
s.save(OUT / "supplement.docx")
