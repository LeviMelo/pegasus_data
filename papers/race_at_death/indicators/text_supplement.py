# The supplement of the indicators paper. Executed by build.py after text.py, whose names it uses.
# ruff: noqa: F821
C19, CEN = CH["1-9"], R["census"]
v_all = next(r for r in R["validation"] if r["size"] == "all")
s = new_doc()
para(s, "Supplementary material - " + TITLE, bold=True)
s.add_heading("Supplementary Text S1 - Estimation without individual linkage and its control", level=2)
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
s.add_heading("Supplementary Text S2 - The census-based population account", level=2)
para(s, "The racial composition of five-year birth cohorts at the censuses of 2000, 2010 and 2022 was read, by single year of age and race, from a cohort-component "
        "population account of every municipality built for this research programme from the censuses, the Mortality and Live Birth Information Systems and the official "
        "estimates of IBGE (population projections, 2024 revision); in a census year the account takes the census population as given, so the shares at the three dates are "
        "census shares. Between and after censuses, race shares are modelled along each birth cohort: log shares change linearly between the censuses of 2000, 2010 and 2022, "
        "a cohort born after a census takes the shares it has in the next census carried back by the state's rate of reclassification of the previous decade, and after "
        "2022 the state's drift carries them forward. The rates over the census-based population in the main text use these modelled shares. "
        "The account is not a published product and its census-year values carry the censuses' own coverage error, which is not quantified by race. A cohort's White share "
        "can fall between censuses through reclassification, but also through higher mortality or emigration of White people, through differences in coverage between "
        "censuses and through the change of the 2022 questionnaire; the comparison between the first census of a cohort aged 0-4 and later ones also compares a race reported "
        "for small children by an adult of the household with one reported for adults. The analysis describes the cohorts and does not separate these explanations.")
figure(s, "regional_ratios_1to9", "Supplementary Figure S1 - White to Brown mortality rate ratio by region under the three classifications, ages 1-4 and 5-9, Brazil, 2013-2024",
       ["Bars: 95% confidence intervals; n.e.: a ratio by the mother's race with a standard error above 0.35 of the estimate (the rule of Supplementary Table S4), not drawn."])
rows = []
for grp, blocks in (("Age at death", D2["by_period_jack"]), ("Cause", D2["by_cause_jack"]), ("Year", D2["by_year_jack"])):
    for k, v in blocks.items():
        rows.append([grp, str(k)] + [f"{v[c][r]['est']:.2f} ({v[c][r]['est'] * math.exp(-1.96 * v[c][r]['se'] / v[c][r]['est']):.2f}; "
                                     f"{v[c][r]['est'] * math.exp(1.96 * v[c][r]['se'] / v[c][r]['est']):.2f})"
                                     for c in ("mother_over_mother", "certified_over_mother", "certified_over_child") for r in ("white", "black")])
table(s, "Supplementary Table S1 - Infant mortality rate ratios against Brown by age at death, cause and year, with deaths and births classified by the mother's "
         "race or the child's, Brazil, 2013-2023",
      ["Group", "Class", "Mother's: White", "Mother's: Black", "Usual: White", "Usual: Black", "Child's: White", "Child's: Black"], rows,
      ["Mother's: deaths and births by the mother's race. Usual: certified deaths over births by the mother's race. Child's: certified deaths over births "
       "classified as households classify infants. In parentheses, 95% confidence intervals from a delete-one-state jackknife on the log scale."])
RTs = MS["top"] + MS["bottom"]
rows = [[r["name"], r["uf"], f2(r["white_share"]), n0(r["gdp_pc"]), f2(math.exp(r["mother_log_rr"])), f2(math.exp(r["certificate_log_rr"])), f2(math.exp(r["misstated"]))]
        for r in RTs]
table(s, "Supplementary Table S2 - The 25 immediate regions where the certificate most raises the White to Brown infant mortality rate ratio, and the 10 where it most lowers it relative to the mother's race, "
         "Brazil, 2013-2023",
      ["Immediate region", "State", "Share of White births", "GDP per capita (R$)", "Rate ratio, mother's race", "Rate ratio, certified race", "Certified over mother's"], rows,
      ["Rate ratios: posterior means of a Poisson BYM2 model over the 510 immediate regions. All regions are in Supplementary Data 2."])

rows = []
for u, x in C19["by_state"].items():
    rm, rce = x["rates"]["ratio_mother"]["Branca"], x["rates"]["ratio_certificate"]["Branca"]
    ok = rm["est"] > 0 and rm["se"] / rm["est"] < 0.35
    iu = I["by_state"].get(u)
    rows.append([u, n0(x["rates"]["deaths"]), ci(rm, log=True) if ok else "not estimable", ci(rce, log=True), f2(fam(CEN["by_state"][u], "Parda", "Branca")),
                 f2(cell(iu, "Parda", "Branca")["est"]) if iu and "Parda" in iu["rows"] else "-", f2(fam(CEN["by_state"][u], "Preta", "Preta")),
                 f2(cell(iu, "Preta", "Preta")["est"]) if iu and "Preta" in iu["rows"] else "-"])
table(s, "Supplementary Table S4 - White to Brown mortality rate ratio at 1-9 years by the mother's race and by certified race, and classification of the children of Brown and "
         "Black mothers by families and on infant death certificates, by state, Brazil",
      ["State", "Deaths at 1-9 years", "Ratio, mother's race (95%CI)", "Ratio, certified race (95%CI)", "Brown mother, child White: family (ages 1-9)",
       "Brown mother, child White: certificate (under 1)", "Black mother, child Black: family", "Black mother, child Black: certificate"], rows,
      ["95%CI: 95% confidence interval. Not estimable: standard error above 0.35 of the estimate."])
rows = [["Under 1 year", f2(IR["ratio_certificate_population"]), f2(IR["ratio_household"]["Branca"])],
        ["1-4 years (2016-2024)", f2(CONV["ratio_certificate_population"]), f2(C14["ratio_household"]["Branca"])],
        ["5-9 years", "-", f2(C59["ratio_household"]["Branca"])]]
table(s, "Supplementary Table S3 - White to Brown mortality rate ratio with certified deaths over a modelled census-based population, and with deaths and births "
         "passed through the family's classification, Brazil", ["Age", "Certified over census-based population", "Family's classification"], rows,
      ["Census-based population: a cohort-component account (Supplementary Text S2); no interval. Family's classification: deaths and births by the mother's race "
       "passed through the households' classification of children of the same age, 2010 Census; no interval."])
# ----------------------------------------------------------------- space, context and the linkage's reporting
s.add_heading("Supplementary Text S3 - The correction for the instability of the mother's declaration", level=2)
para(s, "Let Q be the 3 x 3 matrix of the chance that a mother who declared class i (White, Black, Brown) at one birth declares class j at the next, "
        "estimated from mothers with two births in the smaller municipalities, with chance pairs from a shifted birth date subtracted (companion paper). Only "
        "its diagonal is published there; the six off-diagonal cells follow from the three row sums and from reversibility, pi_i Q_ij = pi_j Q_ji, with pi the "
        "shares of the first declarations. If each declaration is drawn from a stable class with misclassification matrix E, and the chain is reversible, Q is "
        "approximately E times E, and E was taken as the principal matrix square root of Q, negative cells set to zero and rows renormalised. Deaths and births by "
        "declared class, d = E' d* and b = E' b*, were solved for the stable-class counts d* and b*, assuming the misclassification does not depend on the "
        f"infant's death, and the ratios recomputed. Q: {[[round(x, 3) for x in r] for r in MCL['Q']]}; E: {[[round(x, 3) for x in r] for r in MCL['E']]}.")
s.save(OUT / "supplement.docx")
