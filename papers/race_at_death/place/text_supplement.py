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
s.add_heading("Supplementary Text S2 - Methods of the spatial, multilevel and panel analyses", level=2)
para(s, f"Small-area estimation. For each municipality, the linked infant deaths of each class of mother certified in each race, and the census children of each class of "
        f"mother classified in each race, were modelled as binomial counts with a logit link and a Besag-York-Mollié random effect {cite('besag1991')} in the BYM2 "
        f"parametrisation {cite('riebler2016')}, which splits the between-municipality variance into a spatially structured part (on the queen contiguity of the 2022 mesh, "
        f"{n0(G['edges'])} pairs of neighbours; {G['islands_joined']} municipalities without a land neighbour joined to the nearest) and an unstructured part, with "
        f"penalised-complexity priors {cite('simpson2017')}. Models were fitted by integrated nested Laplace approximation {cite('rue2009')} (R-INLA, Gaussian approximation, "
        "empirical Bayes integration over the hyperparameters); maps show posterior means, and the raw proportions and the widths of the credible intervals are in the "
        "supplement.")
para(s, f"Spatial structure and competing explanations. Spatial autocorrelation was measured by Moran's I {cite('moran1950')} of the empirical-Bayes standardised proportion "
        f"{cite('assuncao1999')} and local clusters by the local Moran statistic {cite('anselin1995')}, both with 999 permutations, over municipalities with at least five "
        "linked deaths in the class. To set the explanations against one another, binomial models of the municipal proportions were fitted with the composition (a cubic "
        "B-spline of the logit share of White births), with state fixed effects, with the municipal context, and with their combinations; for each, the deviance explained, "
        "a quasi-likelihood F test of each block given the others, and Moran's I of the Pearson residuals are reported. The border test asks whether the certified race jumps "
        f"at state borders, as a state practice would make it, or changes continuously, as local composition would {cite('keele2015')}: state effects were estimated, with "
        "the composition, from the municipalities that touch no other state, and for each pair of neighbouring municipalities in different states the difference of their "
        "empirical logits was regressed on the difference of their states' effects and of their composition (slope 1: the full state difference appears at the border; "
        "slope 0: none of it does).")
para(s, f"Multilevel models. For the linked infant deaths of each class of mother, the certified race (for example, certified White for children of Brown mothers) was "
        f"modelled by logistic regression with a random intercept for the municipality {cite('bates2015')}. A sequence of fixed parts (none; composition; socioeconomic context "
        "and place; services and recording; their combinations; and these with the individual variables of the death and the birth, the macro-region and the year) gave the "
        f"proportional change in the municipal variance and the median odds ratio {cite('merlo2006')}; the order of entry is reported both ways so that no explanation is "
        "credited with variance it shares with another. Models were fitted by penalised iteratively reweighted least squares (nAGQ = 0); for two outcomes the full model was refitted with a crossed random intercept for the "
        "establishment of death, to set the place against the institution that certifies.")
para(s, "Time by place. The yearly proportions of linked infant deaths certified with the mother's race (2013-2023) in each of the 133 intermediate regions were modelled by "
        "binomial mixed models with a random intercept and a random slope for the year by region; the regional slopes give the change over the decade, and a model with the "
        "macro-region by year interaction tests where the change was faster.")
para(s, "Change within places. A municipality-year panel (2013-2023) set the certified race of each municipality's linked infant deaths against what the "
        f"municipality was that year: the share of White mothers among its live births, GDP per capita {cite('ibge_pib')} over the yearly population, physicians "
        "per 1,000 inhabitants, and, from its own death certificates of that year, the proportion with no race, of natural deaths certified by a death verification "
        "service and of external deaths certified by a medical examiner. Binomial mixed models with a random intercept for the place and year effects split each "
        f"variable into the place's mean over the years (between) and the year's deviation from it (within) {cite('mundlak1978')}; the within coefficient is what "
        "follows a change inside the same place, the between coefficient the cross-sectional gradient. Because a small municipality's yearly share of White births "
        "carries sampling noise that attenuates the within coefficient, the models were fitted on municipality-years and again on immediate region-years, and the "
        "share of the within variance that is not sampling noise is reported. As a second time point independent of the birth records, the change between 2013-2015 "
        "and 2021-2023 in municipalities with five or more deaths in each period was set against the change in the census share of White residents, literacy "
        f"and urbanisation between 2010 and 2022 {cite('ibge_sidra2010')}.")
s.add_heading("Supplementary Text S3 - Within places in detail", level=2)
para(s, f"Within places, composition moved the certificate far less than it separated places. Over {n0(WM['n_unit_years'])} municipality-years of "
        f"{n0(WM['n_units'])} municipalities ({n0(WM['deaths'])} deaths of Brown mothers' infants, 2013-2023), with region-by-year effects, the log-odds of being "
        f"certified White rose by {bw('lw', part='b')} per unit of the logit of the share of White births between municipalities, and by {bw('lw')} when a "
        f"municipality's own share rose by the same amount from one year to another (Figure 5C, Supplementary Table S8). The within variation was small (standard "
        f"deviation {f2(WM['spread']['lw']['sd_within'])} against {f2(WM['spread']['lw']['sd_between'])} between municipalities) and "
        f"{pct(1 - WM['lw_reliability'], 0)} of it was sampling noise of the yearly share, which attenuates the coefficient (the share not noise is one minus the "
        f"mean sampling variance of the yearly logit share over its within variance); over {WI['n_units']} immediate regions, where "
        f"{pct(WI['lw_reliability'], 0)} of the within variation was real change, the two coefficients were {bw('lw', 'immediate', part='b')} and "
        f"{bw('lw', 'immediate')}, the second about {WI['all']['lw_w']['est'] / WI['lw_reliability'] / WI['all']['lw_b']['est'] * 100:.0f}% of the first once corrected "
        f"for noise. A municipality's GDP per capita ({bw('lgdp')}) and physicians ({bw('lphys')}) did not move the certificate within it; the share of natural "
        f"deaths certified by a verification service did ({bw('svo')}; {bw('svo', 'immediate')} within immediate regions), and so did the share of deaths with "
        f"the race left blank ({bw('blank')}); the share of external deaths certified by a medical examiner moved it within immediate regions "
        f"({bw('iml', 'immediate')}). Over a longer span, the "
        f"census composition interpolated between 2010 and 2022 varied within municipalities by a standard deviation of {f2(L2['sd_within_lc'])} on the logit scale, "
        f"against {f2(L2['sd_between_lc'])} between them. On that small variation, the certificate's excess of White over the births' share moved by "
        f"{f2(L2['within']['lc']['est'])} (standard error {f2(L2['within']['lc']['se'])}) per unit within municipalities ({n0(L2['unit_years'])} municipality-years, "
        f"state-by-year effects; 95%CI {f2(L2['within']['lc']['est'] - 1.96 * L2['within']['lc']['se'])}; {f2(L2['within']['lc']['est'] + 1.96 * L2['within']['lc']['se'])}; "
        f"between them {f2(L2['between']['lc']['est'])}). On this outcome a certificate fixed in each place predicts -1 and one that follows the census predicts 0: the "
        "interval excludes full following and includes a fixed certificate. With the next year's composition added as a placebo lead, the within estimate was "
        f"{f2(L2['within_with_lead']['lc']['est'])} (standard error {f2(L2['within_with_lead']['lc']['se'])}) and the lead {f2(L2['within_with_lead']['lc_lead']['est'])} "
        f"({f2(L2['within_with_lead']['lc_lead']['se'])}), uninformative; over 2000-2010, with the newborn's colour, the within estimate was "
        f"{f2(PL['2000-2010 (newborn observed)']['within']['lc']['est'])} (standard error {f2(PL['2000-2010 (newborn observed)']['within']['lc']['se'])}). The decade's census change gave {f2(CEN2['coef']['cw_w']['est'])} (95%CI {f2(CEN2['coef']['cw_w']['est'] - 1.96 * CEN2['coef']['cw_w']['se'])}; "
        f"{f2(CEN2['coef']['cw_w']['est'] + 1.96 * CEN2['coef']['cw_w']['se'])}) against {f2(CEN2['coef']['cw_b']['est'])} between municipalities (Figure 5D). The "
        "yearly panel and the census decade agree that within places the certificate moved with composition much less than between places; the long panel's "
        "interval includes both a fixed certificate and the gradient between places, so it does not discriminate. Within-place variation was small in all three, "
        "and none excludes a slow adjustment.")
s.add_heading("Supplementary Text S4 - Results in detail", level=2)
for _t in S4:
    para(s, _t)
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
      [f"The linkage read {n0(I['certificates'])} certificates; {I['flow']['birth_after_death']} of them have a birth date after the date of death "
       f"({I['flow']['birth_after_death_linked']} linked), and a count of the files by valid dates gives {n0(I['flow']['lake_infant_deaths'])}. The candidate estimator "
       f"holds {I['flow']['candidate_deaths'] - I['flow']['with_sex_and_municipality']:.0f} of these {I['flow']['birth_after_death']} among its "
       f"{n0(I['flow']['candidate_deaths'])} deaths with sex and municipality."])
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
OUTC = {"PW": "Brown mother, certified White", "KK": "Black mother, certified Black"}
rows = []
for key, kl in OUTC.items():
    for lv, ll in (("municipality", "municipality-years"), ("immediate", "immediate region-years")):
        blk = PNL[key][lv]
        for v, vl in PNL["labels"].items():
            b_, w_ = blk["all"][f"{v}_b"], blk["all"][f"{v}_w"]
            rows.append([kl, f"{ll} ({n0(blk['n_unit_years'])}; {n0(blk['deaths'])} deaths)", vl, f"{f2(b_['est'])} ({f2(b_['se'])})", f"{f2(w_['est'])} ({f2(w_['se'])})",
                         f"{f2(blk['spread'][v]['sd_between'])}", f"{f2(blk['spread'][v]['sd_within'])}"])
table(s, "Supplementary Table S8 - Between and within places: coefficients of yearly municipal variables on the certified race of linked infant deaths, Brazil, 2013-2023",
      ["Outcome", "Units", "Variable", "Between: log-odds (SE)", "Within: log-odds (SE)", "SD between", "SD within"], rows,
      ["Binomial mixed models with year effects and a random intercept for the place (nAGQ = 0); every variable split into the place's mean over 2013-2023 and the "
       "year's deviation from it; all variables in one model. SD: standard deviation of the place means and of the deviations, weighted by deaths. Share of the within "
       f"variance of composition that is not sampling noise: {f2(PNL['PW']['municipality']['lw_reliability'])} in municipalities, "
       f"{f2(PNL['PW']['immediate']['lw_reliability'])} in immediate regions."])
CCs = SP["candidates_context"]
rows = []
for k, m in CCs["children_comp_gdp"].items():
    c_, g_ = k.split("|")
    rows.append(["1-9 years, mother's race", f"{c_} White births, {g_} GDP", n0(m["deaths"]), cc(cell(m, "Parda", "Branca")), cc(cell(m, "Preta", "Preta"))])
for k, m in CCs["children_place_small"].items():
    rows.append(["1-9 years, mother's race", k, n0(m["deaths"]), cc(cell(m, "Parda", "Branca")), cc(cell(m, "Preta", "Preta"))])
table(s, "Supplementary Table S9 - Certified race at 1-9 years by municipal composition and GDP per capita and by place, candidate estimator, Brazil",
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
table(s, "Supplementary Table S10 - Classification of children according to the share of White mothers among the live births of the municipality: family's classification "
         "(2010 Census) and death certificate, Brazil",
      ["Share of White mothers", "Cell", "Family, under 1 year", "Certificate, under 1 year (95%CI)", "Family, 1-9 years", "Certificate, 1-9 years (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Not estimable: standard error above 0.15."])
rows = []
for g, gl in (("infants", "Under 1 year"), ("children 1-9", "1-9 years")):
    for prior, pl in (("certified", "Certified race of local deaths"), ("births", "Race of the mothers of local births")):
        for m in ("Branca", "Parda", "Preta"):
            x = MIX[g][prior][m]
            rows.append([gl, pl, EN[m], ci(x["lambda"]), str(x["cells"]), f"{x['rms_family_only']:.3f}", f"{x['rms_mixture']:.3f}"])
table(s, "Supplementary Table S11 - Weight of the local distribution (λ) in a mixture model of the certified race of children, by mother's race, age and reference distribution, Brazil",
      ["Age at death", "Local reference distribution", "Mother's race", "λ (95%CI)", "Cells", "Root mean square difference from the family's classification", "From the model with λ"], rows,
      ["C(m -> c) = (1 - λ) F(m -> c) + λ π(c) over ten classes of municipal composition, F the family's classification in the census and π the local reference. λ = 0: the "
       "certificate records the family's classification; λ = 1: it records the local distribution whatever the mother's race. With the certified race of local deaths as the "
       "reference, the reference contains the certificates being modelled, which biases λ upward; the fit for Black mothers is poor under both references."])
figure(s, "place_within_state", "Supplementary Figure S7 - Infant deaths certified as each cell of the table by place within the state (A), and Brown mothers' infants "
                                "certified White by municipal composition and GDP per capita (B), Brazil, 2013-2023",
       ["A: one-to-one linkage, 95% confidence intervals. B: proportions without intervals (binomial intervals understate the clustering by place)."])
figure(s, "time_regions", "Supplementary Figure S8 - Change of Brown mothers' infants certified White against its level in 2013 by intermediate region (A), and the "
                          "proportion certified as the mother's race by state and year (B), Brazil, 2013-2023",
       ["A: binomial mixed model with random intercept and slope for the year by intermediate region. B: one-to-one linkage, all mothers."])
for t_ in SUPP_TABLES:
    table(s, *t_)
s.save(OUT / "supplement.docx")
