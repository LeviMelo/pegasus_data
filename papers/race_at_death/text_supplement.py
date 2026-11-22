# The supplement. Executed by build.py after text.py, whose names it uses.
# ruff: noqa: F821
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
        f"for infants was {pct(v_all['candidates']['found'])} overall (Supplementary Table S2).")
para(s, "The estimator of t N(j, k) is the difference of the two counts. Its variance was approximated by the sum of the candidate count and the control count, which "
        "ignores the scaling factor of the control (close to 1). A proportion is a ratio of two such differences; the variance of its denominator was ignored, which "
        "understates the error of rows with few deaths. A twin of the same sex is a candidate and a twin of the other sex is in the control; both share the mother's race "
        "with the deceased. Mortality by the mother's race uses the shares of each race among the estimated deaths, so that t cancels provided it does not differ by race.")
s.add_heading("Supplementary Text S2 - Three readings of race for the same woman", level=2)
BD = T3["by_declared"]
para(s, f"Deaths of women aged 15 to 49 years in 2015 to 2022 in municipalities with fewer than 2,000 mothers on the birth records ({n0(T3['women_deaths'])} deaths) were "
        f"related to the birth records on which they were the mother, by birth date and municipality ({n0(T3['linked'])} pairs). These deaths were then related to the "
        "hospital admission that ended in death, through a probabilistic linkage of admissions in the Hospital Information System to death certificates on birth date, sex, "
        f"date of death and hospital. {n0(T3['with_three'])} women had the three races recorded; the mean estimated proportion of false pairs among them was "
        f"{pct(T3['false_share'])}. False pairs were removed in expectation, taking the declared race of a false pair to follow the racial composition of mothers in the "
        "region; intervals are from 400 bootstrap resamples of the women. The certificate recorded the race the woman had declared as a mother for "
        f"{ci(BD['Branca']['certificate'])} of White, {ci(BD['Parda']['certificate'])} of Brown and {ci(BD['Preta']['certificate'])} of Black women; the hospital record did "
        f"so for {ci(BD['Branca']['hospital'])}, {ci(BD['Parda']['hospital'])} and {ci(BD['Preta']['hospital'])} (Supplementary Table S8). For comparison, among "
        f"{n0(R['delivery']['pairs'])} delivery admissions of 2022 related to the birth record, the hospital recorded the declared race for "
        f"{f2(R['delivery']['hospital_as_declared']['Branca']['est'])} of White, {f2(R['delivery']['hospital_as_declared']['Parda']['est'])} of Brown and "
        f"{f2(R['delivery']['hospital_as_declared']['Preta']['est'])} of Black mothers.")
s.add_heading("Supplementary Text S3 - Birth cohorts at three censuses (exploratory)", level=2)
para(s, "The racial composition of five-year birth cohorts at the censuses of 2000, 2010 and 2022 was read, by single year of age and race, from a cohort-component "
        "population account of every municipality built for this research programme from the censuses, the Mortality and Live Birth Information Systems and the official "
        f"estimates {cite('ibge_projections2024')}; in a census year the account takes the census population as given, so the shares at the three dates are census shares. "
        "The account is not a published product and its census-year values carry the censuses' own coverage error, which is not quantified by race. A cohort's White share "
        "can fall between censuses through reclassification, but also through higher mortality or emigration of White people, through differences in coverage between "
        "censuses and through the change of the 2022 questionnaire; the comparison between the first census of a cohort aged 0-4 and later ones also compares a race reported "
        "for small children by an adult of the household with one reported for adults. The analysis describes the cohorts and does not separate these explanations.")
figure(s, "figS1", "Supplementary Figure S1 - Estimates without individual linkage against the one-to-one linkage for every cell of the table of mother's race by certified race, "
                   "by size of municipality (A), and proportion of infant deaths certified with the mother's race by year of death (B), Brazil, 2013-2023", ["Bars: 95% confidence intervals."])
figure(s, "figS2", "Supplementary Figure S2 - White to Brown mortality rate ratio by region under the three classifications, ages 1-4 and 5-9, Brazil, 2013-2024",
       ["Bars: 95% confidence intervals; n.e.: a ratio by the mother's race with a standard error above 0.6 of the estimate, not drawn."])
figure(s, "figS3", "Supplementary Figure S3 - Certified race of infants, family's classification and the mixture model of the certifier with its two reference distributions, "
                   "by the share of White mothers among the live births of the municipality, Brazil")
figure(s, "figS4", "Supplementary Figure S4 - Classification of children by the mother's instruction and her partner's race in the family's classification (A), and certified race "
                   "by the mother's years of schooling on the birth record at 1-9 years (B) and at 15-24 years by class of municipal composition (C), Brazil",
       ["Bars: 95% confidence intervals; estimates that are not estimable are not drawn."])
figure(s, "figS5", "Supplementary Figure S5 - Classification of children according to the share of White mothers among the live births of the municipality: family's "
                   "classification (under 1 year and 1-4 years) and death certificate (under 1 year, linkage; 1-9 years, candidate estimator), Brazil",
       ["Bars: 95% confidence intervals."])
figure(s, "figS6", "Supplementary Figure S6 - Proportion classified with the mother's race by the child's age in the family's classification and on the certificate (A, B), and "
                   f"proportion certified White among people recorded White at birth by single year of age at death, natural causes and assault (C), Brazil",
       [f"C: people born in {YOUTH_BORN} who died in {YOUTH_YEARS}, municipalities with fewer than 1,600 live births per year; age at death and birth cohort are confounded "
        "(age 24 comes only from the earliest cohorts). The family's age gradient is cross-sectional (age 0 born in 2010, age 19 born in 1991) and conditional on living with the mother."])
figure(s, "figS7", "Supplementary Figure S7 - Share of White, Brown and Black people in five-year birth cohorts at the censuses of 2000, 2010 and 2022 and, for cohorts born from "
                   "2000, on the birth record, Brazil", ["Census shares: the population account (Supplementary Text S3). Birth record: colour recorded at birth, cohorts born 2000-2009."])
figure(s, "figS8", "Supplementary Figure S8 - Brown mothers' infants certified White by municipality: raw proportion, BYM2 posterior mean and width of the 95% credible interval, "
                   "Brazil, 2013-2023", ["Raw proportions are drawn for municipalities with five or more linked deaths of Brown mothers."])
figure(s, "figS9", "Supplementary Figure S9 - The other cells of the table by municipality: White mothers' infants certified White (A) and Brown (B), Black mothers' infants "
                   "certified Black (C) and Brown (D), BYM2 posterior means, Brazil, 2013-2023")
figure(s, "figS10", "Supplementary Figure S10 - Infant deaths certified in a race other than the mother's, all linked deaths, by municipality (A) and its local clusters (B), "
                    "Brazil, 2013-2023")
table(s, "Supplementary Table S1 - Live births, proportion with the mother's race field filled and share of each race on the birth record, by year, Brazil, 2000-2024",
      ["Year", "Live births", "Mother's race filled, %", "White, %", "Brown, %", "Black, %"],
      [[r["year"], n0(r["births"]), pct(r["mother_field"]), pct(r["branca"]), pct(r["parda"]), pct(r["preta"])] for r in R["form"]],
      ["Births of 2024 are shown and not used. Before 2010 the shares are of the colour recorded for the newborn; the dedicated field for the mother's race did not exist."])
rows = []
for r in V:
    for m in ORDER:
        if m in r["candidates"]["rows"] and m in r["linkage"]["rows"]:
            rows.append([r["size"], n0(r["candidates"]["deaths"]), pct(r["candidates"]["found"]), EN[m], n0(r["linkage"]["rows"][m]["n"]), ci(cell(r["linkage"], m, m)),
                         cc(cell(r["candidates"], m, m), limit=9)])
table(s, "Supplementary Table S2 - Proportion of infant deaths certified with the mother's race: one-to-one linkage and estimate without individual linkage, by live births per "
         "year in the municipality of residence, Brazil, 2013-2023",
      ["Live births per year", "Deaths", "Deceased found among candidates", "Mother's race", "Linked pairs", "Linkage (95%CI)", "Without individual linkage (95%CI)"], rows,
      ["95%CI: 95% confidence interval. The estimates without individual linkage are printed even where the tables of the main text would call them not estimable, "
       "so that the comparison is complete."])
PAIRS7 = (("Branca", "Branca"), ("Branca", "Parda"), ("Parda", "Parda"), ("Parda", "Branca"), ("Preta", "Preta"), ("Preta", "Parda"), ("Preta", "Branca"))
rows = []
for group, blocks in (("Region", I["by_region"]), ("State", I["by_state"]), ("Age at death", I["by_age"]), ("Year of death", I["by_year"])):
    for k, m in blocks.items():
        rows.append([group, k, n0(m["pairs"])] + [f2(cell(m, a, b)["est"]) if a in m["rows"] else "-" for a, b in PAIRS7])
table(s, "Supplementary Table S3 - Certified race of infants according to the mother's race, by region, state, age at death and year of death, one-to-one linkage, Brazil, 2013-2023",
      ["Group", "Class", "Linked pairs", "White mother, certified White", "White, certified Brown", "Brown, certified Brown", "Brown, certified White", "Black, certified Black",
       "Black, certified Brown", "Black, certified White"], rows)
rows = []
for b_i, b_f in zip(GI, GC0, strict=True):
    cb_ = next((x for x in C19["gradient"] if x["bin"] == b_i["bin"]), None)
    f19 = CEN["gradient"]["1-9"][b_i["bin"]]["matrix"]
    for a, c in (("Parda", "Branca"), ("Branca", "Parda"), ("Preta", "Preta"), ("Preta", "Parda")):
        rows.append([f"{10 * b_i['bin']}-{10 * b_i['bin'] + 10}%", f"{EN[a]} mother, child {EN[c]}", f2(fam(b_f["matrix"], a, c)) if a in b_f["matrix"] and c in b_f["matrix"][a] else "-",
                     ci(cell(b_i["matrix"], a, c)) if a in b_i["matrix"]["rows"] else "-", f2(fam(f19, a, c)) if a in f19 and c in f19[a] else "-",
                     cc(cell(cb_["matrix"], a, c)) if cb_ and a in cb_["matrix"]["rows"] else "-"])
table(s, "Supplementary Table S4 - Classification of children according to the share of White mothers among the live births of the municipality: family's classification "
         "(2010 Census) and death certificate, Brazil",
      ["Share of White mothers", "Cell", "Family, under 1 year", "Certificate, under 1 year (95%CI)", "Family, 1-9 years", "Certificate, 1-9 years (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Not estimable: standard error above 0.15."])


def four(m):
    return [cc(cell(m, "Branca", "Branca")), cc(cell(m, "Branca", "Parda")), cc(cell(m, "Parda", "Parda")), cc(cell(m, "Parda", "Branca"))]


rows = []
for lab, m in CTX["youth"]["by_schooling"]["all"].items():
    rows.append(["all causes", "Mother's years of schooling", str(lab), "-", *four(m)])
for k in ("natural", "external, not assault", "assault"):
    kk = "external" if k == "external, not assault" else k
    for group, blocks in (("Certifier", CTX["youth"]["by_certifier"][k]), ("Place of death", CTX["youth"]["by_place"][k]), ("Mother's years of schooling", CTX["youth"]["by_schooling"][k])):
        for lab, m in blocks.items():
            rows.append([k, group, str(lab), n0(m["deaths"]) if m["deaths"] else "-", *four(m)])
    st = CTX["youth"]["standardised"][k]
    rows.append([k, "Standardised to the composition of natural deaths", "", "-", ci(st["Branca"]["Branca"]), ci(st["Branca"]["Parda"]), ci(st["Parda"]["Parda"]), ci(st["Parda"]["Branca"])])
    for x in CTX["youth"]["by_composition"][k]:
        rows.append([k, "Share of White mothers among local births", f"{100 * x['white_share'][0]:.0f}-{min(100 * x['white_share'][1], 100):.0f}%", n0(x["matrix"]["deaths"]), *four(x["matrix"])])
    if k != "external, not assault":
        for group, blocks in (("Region", Y["by_kind_region"][kk]), ("Period", Y["by_kind_period"][kk])):
            for lab, m in blocks.items():
                rows.append([k + (" and legal intervention" if k == "assault" else ""), group, str(lab), n0(m["deaths"]), *four(m)])
for comp_lab, blocks in CTX["youth"]["by_schooling_composition"].items():
    for lab, m in blocks.items():
        rows.append(["All causes", f"Mother's years of schooling, municipalities with {comp_lab} of White births", lab, "-", *four(m)])
for k in KINDS:
    for sex, lab in (("M", "men"), ("F", "women")):
        m = Y["by_kind_sex"][k][sex]
        rows.append([KL[k], "Sex", lab, n0(m["deaths"]), *four(m)])
    m = Y["by_kind_large"][k]
    rows.append([KL[k], "Municipalities of 1,600 births per year or more", "", n0(m["deaths"]), *four(m)])
table(s, f"Supplementary Table S5 - Certified race of people who died at 15-24 years according to the colour recorded at birth, by cause of death and certifier, place of death, "
         f"mother's schooling, municipal composition, region, period, sex and size of municipality, Brazil, {YOUTH_YEARS}",
      ["Cause of death", "Group", "Class", "Deaths", "White at birth certified White (95%CI)", "White certified Brown (95%CI)", "Brown certified Brown (95%CI)",
       "Brown certified White (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Municipalities with fewer than 1,600 live births per year unless stated. Assault includes legal intervention in the first block. Deaths are "
       "not counted in the rows by mother's schooling, which is a property of the birth record. Not estimable: standard error above 0.15."])
rows = []
for group, blocks in (("Mother's partner", CEN["by_partner"]), ("Mother's level of instruction", CEN["by_instruction"])):
    for lab, m in blocks.items():
        for a in ("Branca", "Parda", "Preta"):
            rows.append(["Family (census, ages 0-9)", group, lab, EN[a], n0(m[a]["records"])] + [f2(fam(m, a, c)) if c in m[a] else "0.00" for c in ("Branca", "Parda", "Preta")])
for group, blocks in (("Mother's years of schooling", CTX["children"]["by_schooling"]),
                      *((f"Mother's years of schooling, municipalities with {k} of White births", v) for k, v in CTX["children"]["by_schooling_composition"].items()),
                      ("Certifier", CTX["children"]["by_certifier"]), ("Place of death", CTX["children"]["by_place"]),
                      ("Sex", C19["by_sex"]), ("Type of cause", C19["by_kind"]), ("Period", C19["by_period"])):
    for lab, m in blocks.items():
        for a in ("Branca", "Parda", "Preta"):
            rows.append(["Certificate (deaths at 1-9 years)", group, str(lab), EN[a], n0(m["deaths"]) if m["deaths"] else "-"] + [cc(cell(m, a, c)) for c in ("Branca", "Parda", "Preta")])
table(s, "Supplementary Table S6 - Race assigned to children according to the mother's race, by characteristics of the household (2010 Census) and of the death (2013-2024), Brazil",
      ["Classification", "Group", "Class", "Mother's race", "Records or deaths", "Child White", "Child Brown", "Child Black"], rows,
      ["Census: weighted proportions; records are sample records. Certificate: candidate estimator with 95% confidence intervals, municipalities with fewer than 25,600 live births "
       "per year; deaths are those of the class (all mothers' races), not counted in the rows by mother's schooling. Not estimable: standard error above 0.15."])
rows = []
for c0 in sorted({k[0] for k in coh}):
    for race, key in (("White", "branca"), ("Brown", "parda"), ("Black", "preta")):
        rows.append([f"{c0}-{c0 + 4}", race, pct(cb[c0][key]) if c0 in cb else "-"] + [pct(coh[(c0, y)][key]) if (c0, y) in coh else "-" for y in (2000, 2010, 2022)])
table(s, "Supplementary Table S7 - Share of each race in five-year birth cohorts born from 1940 to 2009, on the birth record and at the censuses of 2000, 2010 and 2022, Brazil",
      ["Birth cohort", "Race", "Birth record, %", "Census 2000, %", "Census 2010, %", "Census 2022, %"], rows)
rows = [[EN[j], ci(BD[j]["hospital"]), ci(BD[j]["certificate"])] + [cc(BD[j]["certificate_given_hospital"][h]) for h in ("Branca", "Parda", "Preta")] for j in ("Branca", "Parda", "Preta")]
table(s, f"Supplementary Table S8 - Race recorded by the hospital and on the death certificate according to the race declared as a mother, women who died in hospital at "
         f"15-49 years, Brazil, 2015-2022 (n={n0(T3['with_three'])})",
      ["Declared race", "Hospital records the declared race (95%CI)", "Certificate records the declared race (95%CI)", "Certified as declared when the hospital recorded White (95%CI)",
       "When the hospital recorded Brown (95%CI)", "When the hospital recorded Black (95%CI)"], rows,
      ["95%CI: 95% confidence interval (bootstrap), after removal of the expected false pairs."])
rows = []
for u, x in C19["by_state"].items():
    rm, rce = x["rates"]["ratio_mother"]["Branca"], x["rates"]["ratio_certificate"]["Branca"]
    ok = rm["est"] > 0 and rm["se"] / rm["est"] < 0.35
    iu = I["by_state"].get(u)
    rows.append([u, n0(x["rates"]["deaths"]), ci(rm, log=True) if ok else "not estimable", ci(rce, log=True), f2(fam(CEN["by_state"][u], "Parda", "Branca")),
                 f2(cell(iu, "Parda", "Branca")["est"]) if iu and "Parda" in iu["rows"] else "-", f2(fam(CEN["by_state"][u], "Preta", "Preta")),
                 f2(cell(iu, "Preta", "Preta")["est"]) if iu and "Preta" in iu["rows"] else "-"])
table(s, "Supplementary Table S9 - White to Brown mortality rate ratio at 1-9 years by the mother's race and by certified race, and classification of the children of Brown and "
         "Black mothers by families and on infant death certificates, by state, Brazil",
      ["State", "Deaths at 1-9 years", "Ratio, mother's race (95%CI)", "Ratio, certified race (95%CI)", "Brown mother, child White: family (ages 1-9)",
       "Brown mother, child White: certificate (under 1)", "Black mother, child Black: family", "Black mother, child Black: certificate"], rows,
      ["95%CI: 95% confidence interval. Not estimable: standard error above 0.35 of the estimate."])
# ----------------------------------------------------------------- space, context and the linkage's reporting
table(s, "Supplementary Table S10 - Variables of the municipality: definition, source and years",
      ["Variable", "Definition", "Source", "Years"],
      [["Racial composition", "share of White mothers among the live births of residents", "SINASC", "2012-2023"],
       ["GDP per capita", "gross domestic product at current prices over the mean of the 2010 and 2022 census populations", "IBGE, PIB dos Municípios, SIDRA table 5938", "2013-2021 (mean)"],
       ["Illiteracy", "people aged 15 or more who cannot read and write, over people aged 15 or more", "Census 2010, SIDRA table 3149 (preliminary universe results)", "2010"],
       ["Low income", "people with household income per head up to half a minimum wage or none", "Census 2010, SIDRA table 3578", "2010"],
       ["Urban share and population size", "urban population over resident population; resident population", "Census 2010, SIDRA table 202", "2010"],
       ["Physicians", "distinct physicians registered, per 1,000 inhabitants", "CNES, professionals, December", "2013-2023 (mean)"],
       ["Death verification service", "natural deaths of residents certified by a death verification service", "SIM", "2013-2023"],
       ["Medico-legal certification", "external deaths of residents certified by a medical examiner", "SIM", "2013-2023"],
       ["Deaths in hospital", "deaths of residents that occurred in a hospital", "SIM", "2013-2023"],
       ["Race left blank", "deaths of residents with no race on the certificate", "SIM", "2013-2023"],
       ["Capital, metropolitan region", "state capital; member of a metropolitan region", "IBGE", "current division"],
       ["Immediate and intermediate region", "IBGE's 510 immediate and 133 intermediate geographic regions", "IBGE, Divisão regional 2017", "2017"],
       ["Contiguity", "queen contiguity of municipal polygons; municipalities with no land neighbour joined to the nearest", "IBGE mesh 2022", "2022"]],
      ["SINASC: Live Birth Information System. SIM: Mortality Information System. CNES: National Register of Health Establishments. IBGE: Brazilian Institute of Geography and "
       "Statistics. All variables were read through the pegasus_data library from the public files."])
LSx = I["linked_share"]
rows = [["Infant certificates with a valid age under one year", n0(I["flow"]["lake_infant_deaths"]), ""],
        ["of which no sex recorded", n0(I["flow"]["no_sex"]), "excluded from the candidate estimator"],
        ["of which no municipality of residence", n0(I["flow"]["no_municipality"]), "excluded from the candidate estimator"],
        ["Deaths in the candidate estimator", n0(I["flow"]["candidate_deaths"]), ""],
        ["Linked one-to-one", n0(I["linked"]), pct(I["linked"] / I["certificates"])],
        ["Linked, no mother's race on the birth record", n0(I["flow"]["linked_no_mother_race"]), ""],
        ["Linked with the mother's race", n0(I["linked_with_race"]), ""]]
for grp, lab in (("by_certified", "Linked share by certified race"), ("by_size", "Linked share by births per year"), ("by_region", "Linked share by region"),
                 ("by_age", "Linked share by age at death"), ("by_year", "Linked share by year of death")):
    for k, v in LSx[grp].items():
        rows.append([f"{lab}: {EN.get(k, k)}", "", pct(v)])
for k, v in CB.items():
    a, b = k.split(">")
    rows.append([f"{EN[a]} mother, certified {EN[b]}: interval, bootstrap over municipalities", "", ci(v)])
    rows.append([f"{EN[a]} mother, certified {EN[b]}: interval, binomial", "", ci({"est": v["est"], "se": v["se_binomial"]})])
table(s, "Supplementary Table S11 - Flow of infant death certificates, linked share and intervals of the linkage's proportions, Brazil, 2013-2023",
      ["Group", "Certificates", "Share or estimate"], rows)
rows = []
LAB = {"null": "none", "composition": "composition", "socioeconomic": "socioeconomic context and place", "services": "services and recording",
       "composition_socioeconomic": "composition + socioeconomic", "socioeconomic_services": "socioeconomic + services",
       "composition_socioeconomic_services": "composition + socioeconomic + services", "full": "all, with individual variables, region and year",
       "individual_only": "individual variables, region and year"}
OUTL = {"brown_white": "Brown mother, certified White", "brown_brown": "Brown mother, certified Brown", "black_black": "Black mother, certified Black",
        "black_brown": "Black mother, certified Brown", "white_white": "White mother, certified White"}
for o, ol in OUTL.items():
    if o not in ML:
        continue
    for k, kl in LAB.items():
        x = ML[o]["sequence"][k]
        rows.append([ol, kl, f"{x['var_mun']:.3f}", pct(x["pcv"]), f2(x["mor"]), n0(x["aic"])])
table(s, "Supplementary Table S12 - Between-municipality variance of the certified race of linked infant deaths under successive fixed parts of a multilevel logistic model, Brazil, "
         "2013-2023",
      ["Outcome", "Fixed part", "Municipal variance (log-odds)", "Variance explained", "Median odds ratio", "AIC"], rows,
      ["Random intercept for the municipality; fitted by penalised iteratively reweighted least squares (lme4, nAGQ = 0). Variance explained: proportional change from the "
       "model with no fixed part. AIC: Akaike information criterion."])
rows = []
for o, ol in (("PW", "Brown mother, certified White"), ("KK", "Black mother, certified Black"), ("disagree", "Certified race differs from the mother's"),
              ("famPW", "Family: Brown mother, child White")):
    for k in ("M0", "M1_composition", "M2_state", "M3_composition_state", "M4_context", "M5_composition_context", "M6_all"):
        if k in BY[o]:
            x = BY[o][k]
            rows.append([ol, k.split("_", 1)[1].replace("_", " + ") if "_" in k else "none", f"{x['sd_total']:.2f}", f"{x['phi']:.2f}", f"{x['dic']:,.0f}"])
table(s, "Supplementary Table S13 - Spatial models of the municipal proportions (BYM2): standard deviation of the municipal effect, share of it spatially structured (phi) and "
         "deviance information criterion, by fixed part, Brazil",
      ["Outcome", "Fixed part", "SD of the municipal effect (logit)", "Phi", "DIC"], rows,
      ["Binomial model with a BYM2 effect on the queen contiguity of 5,570 municipalities; composition: B-spline of the logit share of White births; context: the variables of "
       "Supplementary Table S10. DIC: deviance information criterion."])
RTs = MS["top"] + MS["bottom"]
rows = [[r["name"], r["uf"], f2(r["white_share"]), n0(r["gdp_pc"]), f2(math.exp(r["mother_log_rr"])), f2(math.exp(r["certificate_log_rr"])), f2(math.exp(r["misstated"]))]
        for r in RTs]
table(s, "Supplementary Table S14 - The 25 immediate regions where the certificate most overstates the White to Brown infant mortality rate ratio, and the 10 where it most "
         "understates it, Brazil, 2013-2023",
      ["Immediate region", "State", "Share of White births", "GDP per capita (R$)", "Rate ratio, mother's race", "Rate ratio, certified race", "Certified over mother's"], rows,
      ["Rate ratios: posterior means of a Poisson BYM2 model over the 510 immediate regions. All regions are in Supplementary Data 2."])

CCs = SP["candidates_context"]
rows = []
for k, m in CCs["children_comp_gdp"].items():
    c_, g_ = k.split("|")
    rows.append(["1-9 years, mother's race", f"{c_} White births, {g_} GDP", n0(m["deaths"]), cc(cell(m, "Parda", "Branca")), cc(cell(m, "Preta", "Preta")), "-"])
for k, m in CCs["children_place_small"].items():
    rows.append(["1-9 years, mother's race", k, n0(m["deaths"]), cc(cell(m, "Parda", "Branca")), cc(cell(m, "Preta", "Preta")), "-"])
for kind, lab in (("natural", "15-24 years, natural causes"), ("assault", "15-24 years, assault")):
    for k, m in CCs["youth_comp_gdp"][kind].items():
        c_, g_ = k.split("|")
        rows.append([lab, f"{c_} White births, {g_} GDP", n0(m["deaths"]), "-", "-", cc(cell(m, "Branca", "Branca"))])
    for k, m in CCs["youth_svo"][kind].items():
        rows.append([lab, k, n0(m["deaths"]), "-", "-", cc(cell(m, "Branca", "Branca"))])
table(s, "Supplementary Table S15 - Certified race after infancy by municipal composition and GDP per capita, place and death verification service, candidate estimator, Brazil",
      ["Age and classification", "Class of municipality", "Deaths", "Brown mother, certified White (95%CI)", "Black mother, certified Black (95%CI)",
       "Recorded White at birth, certified White (95%CI)"], rows,
      [f"GDP tertiles of municipalities (cut points R$ {n0(SP['gdp_tertiles'][0])} and {n0(SP['gdp_tertiles'][1])} per person). 1-9 years: municipalities with fewer than "
       "25,600 live births per year (state capitals cannot be estimated). 15-24 years: municipalities with fewer than 1,600. Not estimable: standard error above 0.15, or "
       "outside 0 to 1 by more than two standard errors."])
rows = []
for g, gl in (("infants", "Under 1 year"), ("children 1-9", "1-9 years")):
    for prior, pl in (("certified", "Certified race of local deaths"), ("births", "Race of the mothers of local births")):
        for m in ("Branca", "Parda", "Preta"):
            x = MIX[g][prior][m]
            rows.append([gl, pl, EN[m], ci(x["lambda"]), str(x["cells"]), f"{x['rms_family_only']:.3f}", f"{x['rms_mixture']:.3f}"])
table(s, "Supplementary Table S16 - Weight of the local distribution (λ) in a mixture model of the certified race of children, by mother's race, age and reference distribution, Brazil",
      ["Age at death", "Local reference distribution", "Mother's race", "λ (95%CI)", "Cells", "Root mean square difference from the family's classification", "From the model with λ"], rows,
      ["C(m -> c) = (1 - λ) F(m -> c) + λ π(c) over ten classes of municipal composition, F the family's classification in the census and π the local reference. λ = 0: the "
       "certificate records the family's classification; λ = 1: it records the local distribution whatever the mother's race. With the certified race of local deaths as the "
       "reference, the reference contains the certificates being modelled, which biases λ upward; the fit for Black mothers is poor under both references."])

s.save(OUT / "supplement.docx")
