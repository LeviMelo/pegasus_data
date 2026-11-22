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
        f"for infants was {pct(v_all['candidates']['found'])} overall (Supplementary Table S4).")
para(s, "The estimator of t N(j, k) is the difference of the two counts. Its variance was approximated by the sum of the candidate count and the control count, which "
        "ignores the scaling factor of the control (close to 1). A proportion is a ratio of two such differences; the variance of its denominator was ignored, which "
        "understates the error of rows with few deaths. A twin of the same sex is a candidate and a twin of the other sex is in the control; both share the mother's race "
        "with the deceased. Mortality by the mother's race uses the shares of each race among the estimated deaths, so that t cancels provided it does not differ by race.")
figure(s, "validation", "Supplementary Figure S1 - Estimates without individual linkage against the one-to-one linkage for every cell of the table of mother's race by certified race, "
                   "by size of municipality (A), and proportion of infant deaths certified with the mother's race by year of death (B), Brazil, 2013-2023", ["Bars: 95% confidence intervals."])
figure(s, "map_raw", "Supplementary Figure S2 - Brown mothers' infants certified White by municipality: raw proportion, BYM2 posterior mean and width of the 95% credible interval, "
                   "Brazil, 2013-2023", ["Raw proportions are drawn for municipalities with five or more linked deaths of Brown mothers."])
figure(s, "map_other_cells", "Supplementary Figure S3 - The other cells of the table by municipality: White mothers' infants certified White (A) and Brown (B), Black mothers' infants "
                   "certified Black (C) and Brown (D), BYM2 posterior means, Brazil, 2013-2023")
figure(s, "map_disagree", "Supplementary Figure S4 - Infant deaths certified in a race other than the mother's, all linked deaths, by municipality (A) and its local clusters (B), "
                    "Brazil, 2013-2023")
figure(s, "gradient_1to9", "Supplementary Figure S5 - Classification of children according to the share of White mothers among the live births of the municipality: family's "
                   "classification (under 1 year and 1-4 years) and death certificate (under 1 year, linkage; 1-9 years, candidate estimator), Brazil",
       ["Bars: 95% confidence intervals."])
figure(s, "mixture", "Supplementary Figure S6 - Certified race of infants, family's classification and the mixture model of the certifier with its two reference distributions, "
                   "by the share of White mothers among the live births of the municipality, Brazil")
table(s, "Supplementary Table S1 - Live births, proportion with the mother's race field filled and share of each race on the birth record, by year, Brazil, 2000-2024",
      ["Year", "Live births", "Mother's race filled, %", "White, %", "Brown, %", "Black, %"],
      [[r["year"], n0(r["births"]), pct(r["mother_field"]), pct(r["branca"]), pct(r["parda"]), pct(r["preta"])] for r in R["form"]],
      ["Births of 2024 are shown and not used. Before 2010 the shares are of the colour recorded for the newborn; the dedicated field for the mother's race did not exist."])
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
for yr, q_ in I["link_quality"].items():
    rows.append([f"Linkage {yr}: threshold (bits), estimated false links, delivery type and plurality agree", "", f"{q_['threshold_bits']:.1f}; {q_['fdr_percent']:.2f}%; "
                 f"{q_['validations']['delivery type agrees']:.1f}%; {q_['validations']['plurality agrees']:.1f}%"])
for k, v in CB.items():
    a, b = k.split(">")
    rows.append([f"{EN[a]} mother, certified {EN[b]}: interval, bootstrap over municipalities", "", ci(v)])
    rows.append([f"{EN[a]} mother, certified {EN[b]}: interval, binomial", "", ci({"est": v["est"], "se": v["se_binomial"]})])
table(s, "Supplementary Table S2 - Flow of infant death certificates, linked share and intervals of the linkage's proportions, Brazil, 2013-2023",
      ["Group", "Certificates", "Share or estimate"], rows,
      [f"The linkage read {n0(I['certificates'])} certificates and a direct count of the files gives {n0(I['flow']['lake_infant_deaths'])}: the difference is in how "
       "invalid dates are read. The candidate estimator holds 3 deaths more than the direct count with sex and municipality, for the same reason."])
table(s, "Supplementary Table S3 - Variables of the municipality: definition, source and years",
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
rows = []
for r in V:
    for m in ORDER:
        if m in r["candidates"]["rows"] and m in r["linkage"]["rows"]:
            rows.append([r["size"], n0(r["candidates"]["deaths"]), pct(r["candidates"]["found"]), EN[m], n0(r["linkage"]["rows"][m]["n"]), ci(cell(r["linkage"], m, m)),
                         cc(cell(r["candidates"], m, m), limit=9)])
table(s, "Supplementary Table S4 - Proportion of infant deaths certified with the mother's race: one-to-one linkage and estimate without individual linkage, by live births per "
         "year in the municipality of residence, Brazil, 2013-2023",
      ["Live births per year", "Deaths", "Deceased found among candidates", "Mother's race", "Linked pairs", "Linkage (95%CI)", "Without individual linkage (95%CI)"], rows,
      ["95%CI: 95% confidence interval. The estimates without individual linkage are printed even where the tables of the main text would call them not estimable, "
       "so that the comparison is complete."])
rows = []
for o, ol in (("PW", "Brown mother, certified White"), ("KK", "Black mother, certified Black"), ("disagree", "Certified race differs from the mother's"),
              ("famPW", "Family: Brown mother, child White")):
    for k in ("M0", "M1_composition", "M2_state", "M3_composition_state", "M4_context", "M5_composition_context", "M6_all"):
        if k in BY[o]:
            x = BY[o][k]
            rows.append([ol, k.split("_", 1)[1].replace("_", " + ") if "_" in k else "none", f"{x['sd_total']:.2f}", f"{x['phi']:.2f}", f"{x['dic']:,.0f}"])
table(s, "Supplementary Table S5 - Spatial models of the municipal proportions (BYM2): standard deviation of the municipal effect, share of it spatially structured (phi) and "
         "deviance information criterion, by fixed part, Brazil",
      ["Outcome", "Fixed part", "SD of the municipal effect (logit)", "Phi", "DIC"], rows,
      ["Binomial model with a BYM2 effect on the queen contiguity of 5,570 municipalities; composition: B-spline of the logit share of White births; context: the variables of "
       "Supplementary Table S3. DIC: deviance information criterion."])
rows = []
LAB = {"null": "none", "composition": "composition", "socioeconomic": "socioeconomic context and place", "services": "services and recording",
       "composition_socioeconomic": "composition + socioeconomic", "socioeconomic_services": "socioeconomic + services",
       "composition_socioeconomic_services": "composition + socioeconomic + services", "full": "all, with individual variables, region and year",
       "individual_only": "individual variables, region and year", "individual_no_region": "individual variables and year"}
OUTL = {"brown_white": "Brown mother, certified White", "brown_brown": "Brown mother, certified Brown", "black_black": "Black mother, certified Black",
        "black_brown": "Black mother, certified Brown", "white_white": "White mother, certified White"}
for o, ol in OUTL.items():
    if o not in ML:
        continue
    for k, kl in LAB.items():
        x = ML[o]["sequence"][k]
        rows.append([ol, kl, f"{x['var_mun']:.3f}", pct(x["pcv"]), f2(x["mor"]), n0(x["aic"])])
table(s, "Supplementary Table S6 - Between-municipality variance of the certified race of linked infant deaths under successive fixed parts of a multilevel logistic model, Brazil, "
         "2013-2023",
      ["Outcome", "Fixed part", "Municipal variance (log-odds)", "Variance explained", "Median odds ratio", "AIC"], rows,
      ["Random intercept for the municipality; fitted by penalised iteratively reweighted least squares (lme4, nAGQ = 0). Variance explained: proportional change from the "
       "model with no fixed part. AIC: Akaike information criterion."])
PAIRS7 = (("Branca", "Branca"), ("Branca", "Parda"), ("Parda", "Parda"), ("Parda", "Branca"), ("Preta", "Preta"), ("Preta", "Parda"), ("Preta", "Branca"))
rows = []
for group, blocks in (("Region", I["by_region"]), ("State", I["by_state"]), ("Age at death", I["by_age"]), ("Year of death", I["by_year"])):
    for k, m in blocks.items():
        rows.append([group, k, n0(m["pairs"])] + [f2(cell(m, a, b)["est"]) if a in m["rows"] else "-" for a, b in PAIRS7])
table(s, "Supplementary Table S7 - Certified race of infants according to the mother's race, by region, state, age at death and year of death, one-to-one linkage, Brazil, 2013-2023",
      ["Group", "Class", "Linked pairs", "White mother, certified White", "White, certified Brown", "Brown, certified Brown", "Brown, certified White", "Black, certified Black",
       "Black, certified Brown", "Black, certified White"], rows)
CCs = SP["candidates_context"]
rows = []
for k, m in CCs["children_comp_gdp"].items():
    c_, g_ = k.split("|")
    rows.append(["1-9 years, mother's race", f"{c_} White births, {g_} GDP", n0(m["deaths"]), cc(cell(m, "Parda", "Branca")), cc(cell(m, "Preta", "Preta"))])
for k, m in CCs["children_place_small"].items():
    rows.append(["1-9 years, mother's race", k, n0(m["deaths"]), cc(cell(m, "Parda", "Branca")), cc(cell(m, "Preta", "Preta"))])
table(s, "Supplementary Table S8 - Certified race at 1-9 years by municipal composition and GDP per capita and by place, candidate estimator, Brazil",
      ["Age and classification", "Class of municipality", "Deaths", "Brown mother, certified White (95%CI)", "Black mother, certified Black (95%CI)",
       ], rows,
      [f"GDP thirds, weighted by linked infant deaths (cut points R$ {n0(SP['gdp_tertiles'][0])} and {n0(SP['gdp_tertiles'][1])} per person). 1-9 years: municipalities with fewer than "
       "25,600 live births per year (state capitals cannot be estimated). Not estimable: standard error above 0.15, or "
       "outside 0 to 1 by more than two standard errors."])
rows = []
for b_i, b_f in zip(GI, GC0, strict=True):
    cb_ = next((x for x in C19["gradient"] if x["bin"] == b_i["bin"]), None)
    f19 = CEN["gradient"]["1-9"][b_i["bin"]]["matrix"]
    for a, c in (("Parda", "Branca"), ("Branca", "Parda"), ("Preta", "Preta"), ("Preta", "Parda")):
        rows.append([f"{10 * b_i['bin']}-{10 * b_i['bin'] + 10}%", f"{EN[a]} mother, child {EN[c]}", f2(fam(b_f["matrix"], a, c)) if a in b_f["matrix"] and c in b_f["matrix"][a] else "-",
                     ci(cell(b_i["matrix"], a, c)) if a in b_i["matrix"]["rows"] else "-", f2(fam(f19, a, c)) if a in f19 and c in f19[a] else "-",
                     cc(cell(cb_["matrix"], a, c)) if cb_ and a in cb_["matrix"]["rows"] else "-"])
table(s, "Supplementary Table S9 - Classification of children according to the share of White mothers among the live births of the municipality: family's classification "
         "(2010 Census) and death certificate, Brazil",
      ["Share of White mothers", "Cell", "Family, under 1 year", "Certificate, under 1 year (95%CI)", "Family, 1-9 years", "Certificate, 1-9 years (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Not estimable: standard error above 0.15."])
rows = []
for g, gl in (("infants", "Under 1 year"), ("children 1-9", "1-9 years")):
    for prior, pl in (("certified", "Certified race of local deaths"), ("births", "Race of the mothers of local births")):
        for m in ("Branca", "Parda", "Preta"):
            x = MIX[g][prior][m]
            rows.append([gl, pl, EN[m], ci(x["lambda"]), str(x["cells"]), f"{x['rms_family_only']:.3f}", f"{x['rms_mixture']:.3f}"])
table(s, "Supplementary Table S10 - Weight of the local distribution (λ) in a mixture model of the certified race of children, by mother's race, age and reference distribution, Brazil",
      ["Age at death", "Local reference distribution", "Mother's race", "λ (95%CI)", "Cells", "Root mean square difference from the family's classification", "From the model with λ"], rows,
      ["C(m -> c) = (1 - λ) F(m -> c) + λ π(c) over ten classes of municipal composition, F the family's classification in the census and π the local reference. λ = 0: the "
       "certificate records the family's classification; λ = 1: it records the local distribution whatever the mother's race. With the certified race of local deaths as the "
       "reference, the reference contains the certificates being modelled, which biases λ upward; the fit for Black mothers is poor under both references."])
s.save(OUT / "supplement.docx")
