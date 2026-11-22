# The Results of paper 3. Executed by build.py after text.py.
# ruff: noqa: F821
bm = IN["brown_mother_by_hospital"]
HY = HO["black_by_year"]
SQ = ML["sequence"]
NT = BK["net"]
FMD = BK["facility_model_delivery"]
WH = IN["within_hospital_or"]
HB = HO["black_bootstrap"]
HT = HO["trend_per_decade"]
FMA = FMD["practice_composition_region_year"]
assert by_h["black"]["black"]["est"] > 2 * by_h["brown"]["black"]["est"], "the certificate no longer follows the hospital's record of the mother"
assert by_h["black"]["black"]["est"] < 0.5, "children of mothers the hospital recorded Black are now mostly certified Black"
assert bm["black"]["black"]["est"] > 3 * bm["brown"]["black"]["est"], "Brown mothers recorded Black: no longer carried to the child"
assert WH["lo"] > 1.5, "within the same hospital, the hospital's record of the mother no longer doubles the odds"
assert FMA["coef"] - 1.96 * FMA["se"] > 0, "the delivery hospital's practice no longer predicts the certificate"
assert NT["certificate_ratio"] < 0.4 and 0.5 < NT["hospital_ratio"] < 1, "net counts changed"
assert abs(IN["black_with_record"]["est"] - IN["black_without_record"]["est"]) < 1.96 * math.hypot(IN["black_with_record"]["se"], IN["black_without_record"]["se"]), "selection by the hospital record"
assert LD["certificate_infant_below_25600"]["est"] < LD["certificate_1_4"]["est"] < LD["certificate_5_9"]["est"], "the age gradient does not hold in the same municipalities"
assert HT["est"] < PK["fixed"]["yc"]["Estimate"], "the hospital now changes as fast as the certificate"
assert MO["deviance_explained"]["state"] > MO["deviance_explained"]["composition"], "composition now explains more than the state"
assert FX["certifierdeath verification service"]["est"] + 1.96 * FX["certifierdeath verification service"]["se"] < 0
assert FX["certifiermedical examiner (IML)"]["est"] + 1.96 * FX["certifiermedical examiner (IML)"]["se"] < 0

d.add_heading("Results", level=1)
para(d, f"Of {n0(I['linked'])} infant deaths of 2013-2023 linked to their birth records, {n0(IL['n'])} were of children of mothers who declared themselves Black; for "
        f"{n0(IN['with_hospital_record_black'])} of them the birth was linked to the mother's delivery admission in the public system. Across all deliveries of "
        f"2012-2023 linked to their birth records, {n0(NT['hospital_declared_black'])} admissions of mothers who declared themselves Black carried a race.")
d.add_heading("Who records a Black person as Black", level=2)
para(d, "Every record used the Black category less than the mothers had declared it (Table 1, Figure 1). Hospitals recorded mothers who declared themselves Black as "
        f"Black at delivery in {ci(HB['black'])} of admissions with a race, as Brown in {ci(HB['brown'])} and as White in {ci(HB['white'])} (intervals from a bootstrap "
        f"over hospitals), and left the race blank in {pct(NT['hospital_blank_share']['black'])}; with blanks counted, {f2(NT['hospital_black_of_all_black_declared'])} "
        f"were recorded Black. Death certificates recorded the infants of Black mothers as Black in {cbci('Preta>Preta')}, as Brown in {cbci('Preta>Parda')} and as White "
        f"in {cbci('Preta>Branca')}. Families reported as Black {f2(LD['family_child_0'])} of the children under one year of Black mothers in 2010.")
para(d, "Gross agreement overstates the loss when a small group is misclassified into a large one and back. Counted net, the hospitals recorded "
        f"{n0(NT['hospital_recorded_black'])} mothers as Black against {n0(NT['hospital_declared_black'])} who declared themselves Black, a ratio of "
        f"{f2(NT['hospital_ratio'])}, because a small share of the far more numerous Brown mothers was recorded Black. The certificates recorded "
        f"{n0(NT['certificate_recorded_black'])} linked infant deaths as Black against {n0(NT['certificate_declared_black'])} infants of Black mothers, a ratio of "
        f"{f2(NT['certificate_ratio'])}: only {pct(NT['certificate_brown_to_black']['est'])} of Brown mothers' infants were certified Black, too few to make up the loss.")
para(d, f"On certificates the Black category was used more for older children: {cc(LD['certificate_1_4'])} at 1-4 years and {cc(LD['certificate_5_9'])} at 5-9 years, "
        f"against {ci(LD['certificate_infant_below_25600'])} for infants in the same municipalities (those with fewer than 25,600 births a year, where the estimator after "
        f"infancy works), and, for adult women who died in hospital and had declared themselves Black as mothers, {ci(LD['certificate_adult_women'])} (exploratory; "
        f"Supplementary Text S1, Supplementary Table S1), with the hospital recording them Black in {ci(LD['hospital_adult_women_death'])}. Families too reported older "
        f"children as Black more often ({f2(LD['family_child_1_4'])} at 1-4 and {f2(LD['family_child_5_9'])} at 5-9 years).")
F0B, F14B = CEN["by_band"]["0"]["Preta"], CEN["by_band"]["1-4"]["Preta"]
W14B = CH["1-4"]["without_large"]["matrix"]["rows"]["Preta"]
WOM = R["triples"]["by_declared"]["Preta"]
rows = [["Family (census 2010), child under 1", "household", f2(F0B["Preta"]["est"]), f2(F0B["Parda"]["est"]), f2(F0B["Branca"]["est"])],
        ["Family (census 2010), child 1-4", "household", f2(F14B["Preta"]["est"]), f2(F14B["Parda"]["est"]), f2(F14B["Branca"]["est"])],
        ["Hospital, the mother at delivery (2012-2023)", "hospital staff", ci(HB["black"]), ci(HB["brown"]), ci(HB["white"])],
        ["Death certificate, infant (2013-2023)", "certifier or informant", cbci("Preta>Preta"), cbci("Preta>Parda"), cbci("Preta>Branca")],
        ["Death certificate, child 1-4 (2013-2024)", "certifier or informant", cc(W14B["Preta"]), cc(W14B["Parda"]), cc(W14B["Branca"])],
        ["Hospital, adult woman at death (2015-2022)", "hospital staff", ci(WOM["hospital"]), "-", "-"],
        ["Death certificate, adult woman (2015-2022)", "certifier or informant", ci(WOM["certificate"]), "-", "-"]]
table(d, "Table 1 - Race recorded for people who declared themselves Black, or for children of mothers who did, by record, Brazil",
      ["Record", "Who classifies", "Black (95%CI)", "Brown (95%CI)", "White (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Census: weighted proportions; standard errors treat the sample as simple and are below 0.005. Hospital at delivery: admissions with "
       f"a race ({pct(NT['hospital_blank_share']['black'])} of Black mothers' admissions had none), bootstrap over hospitals. Certificate, infant: bootstrap over "
       "municipalities; the remainder of the row is another category or none. Certificate, 1-4 years: candidate estimator, municipalities with fewer than 25,600 births a "
       "year; its estimates can fall outside 0 to 1. Adult women: exploratory, bootstrap after removal of expected false pairs. The populations and years differ between rows."])
figure(d, "black_ladder", "Figure 1 - Proportion recorded Black among people who declared themselves Black, or children of mothers who did, by record and age, Brazil",
       ["The declaration bar is 1 by construction. Family: 2010 Census sample. Hospital at delivery: admissions of 2012-2023 with a race. Certificate, infant: linkage, 2013-2023; 1-4 and 5-9 years: candidate "
        "estimator, municipalities with fewer than 25,600 births a year; adult women: deaths at 15-49 years in hospital, 2015-2022 (exploratory). Bars: 95% confidence "
        "intervals."])
d.add_heading("The hospital and the certificate", level=2)
para(d, "When the hospital had recorded the infant's own mother as Black, the infant was certified Black in "
        f"{ci(by_h['black']['black'])} of deaths and Brown in {ci(by_h['black']['brown'])}; when it had recorded her as Brown, Black in {ci(by_h['brown']['black'])}; when "
        f"as White, Black in {ci(by_h['white']['black'])} and White in {ci(by_h['white']['white'])} (Figure 2A, Supplementary Table S2). Within the same delivery "
        f"hospital, the odds of being certified Black were {f2(WH['est'])} (95%CI {f2(WH['lo'])}; {f2(WH['hi'])}) times higher when the hospital had recorded the mother "
        f"as Black (Mantel-Haenszel, {WH['hospitals']} hospitals). For mothers who declared themselves Brown, the infant was certified Black in {ci(bm['black']['black'])} "
        f"when the hospital had recorded the mother as Black and {ci(bm['brown']['black'])} when as Brown. Infants of Black mothers were certified Black in "
        f"{ci(IN['black_with_record'])} with a linked delivery admission and {ci(IN['black_without_record'])} without one.")
para(d, f"Hospitals differed in their practice: across {n0(HO['facilities']['n'])} hospitals with 30 or more Black mothers, the share recorded Black ranged from "
        f"{f2(HO['facilities']['p10'])} at the 10th percentile to {f2(HO['facilities']['p90'])} at the 90th (median {f2(HO['facilities']['p50'])}; Supplementary Table "
        f"S3). For {n0(FMD['deaths'])} infant deaths of Black mothers delivered in {n0(FMD['facilities'])} such hospitals ({pct(IN['died_where_delivered'], 0)} of Black "
        f"mothers' infants with a delivery record died where they were born), the odds of being certified Black were multiplied by {f2(FMD['practice']['or_per_logit'])} per unit "
        f"of the logit of the delivery hospital's share, and by {f2(FMA['or_per_logit'])} (95%CI {math.exp(FMA['coef'] - 1.96 * FMA['se']):.2f}; "
        f"{math.exp(FMA['coef'] + 1.96 * FMA['se']):.2f}) at equal municipal composition, region and year; across {FL['facilities']} hospitals with 10 or more such "
        f"deaths, practice and certificates correlated at {f2(FL['corr'])} ({f2(FL['wcorr'])} weighted by deaths; Figure 2B).")
figure(d, "black_hospital", "Figure 2 - Certified race of Black mothers' infants by the race the hospital recorded for the same mother at delivery (A), and each hospital's "
                            "practice against the certificates of Black mothers' infants who died there (B), Brazil, 2013-2023",
       ["A: infant deaths linked to the birth record and the birth record to the delivery admission; bars, 95% confidence intervals. B: hospitals with 10 or more "
        "deaths of Black mothers' infants; practice, share of Black mothers recorded Black at delivery, 2012-2023; the dotted line is equality."])
d.add_heading("Who certifies, and the child", level=2)
para(d, f"In the full multilevel model (Figure 3), death verification services ({orx('certifierdeath verification service')}) and medical examiners "
        f"({orx('certifiermedical examiner (IML)')}) used the Black category less than attending physicians, with the cause and place of death in the model; mothers under 20 "
        f"had their infants certified Black less often ({orx('mother_age<20')}), and mothers with 0-3 years of schooling ({orx('school0-3')}) and with 12 or more "
        f"({orx('school12 or more')}) more often than those with 8-11. The municipality's composition explained {pct(SQ['composition']['pcv'], 0)} of the variance between "
        f"municipalities, its socioeconomic context {pct(SQ['socioeconomic']['pcv'], 0)}, its services {pct(SQ['services']['pcv'], 0)}, and all terms "
        f"{pct(SQ['full']['pcv'], 0)} (Supplementary Table S4); with a crossed random effect for the establishment of death, the variance was {f2(EST['var_estab'])} between "
        f"establishments and {f2(EST['var_mun'])} between municipalities.")
figure(d, "black_terms", "Figure 3 - Odds ratios of being certified Black for infants of Black mothers, full multilevel model, Brazil, 2013-2023",
       ["Logistic regression with a random intercept for the municipality (nAGQ = 0); also in the model, the municipality's composition, urbanisation, population, "
        "metropolitan status, physicians, certification and recording. References: attending physician, death in hospital, 0-6 days, perinatal cause, mother with 8-11 "
        "years of schooling and aged 20-34, birth weight 2,500 g or more, Southeast. Bars: 95% confidence intervals."])
d.add_heading("Where and when", level=2)
para(d, f"The use of the category clustered in space (Moran's I {f2(MO['rate']['I'])}) and was highest in the South (Figure 4A). Between municipalities, the state "
        f"explained {pct(MO['deviance_explained']['state'], 0)} of the deviance with 26 parameters and the composition {pct(MO['deviance_explained']['composition'], 0)} with three "
        f"({pct(MO['deviance_explained']['census_composition'], 0)} with the census share of White residents), and residual clustering remained "
        f"(Moran's I {f2(MO['composition_state_context']['I'])}). From 2013 to 2023 the certificate's use rose by {f2(PK['fixed']['yc']['Estimate'])} (95%CI "
        f"{f2(PK['fixed']['yc']['Estimate'] - 1.96 * PK['fixed']['yc']['Std. Error'])}; {f2(PK['fixed']['yc']['Estimate'] + 1.96 * PK['fixed']['yc']['Std. Error'])}) in "
        f"log-odds per decade, from {f2(cell(I['by_year']['2013'], 'Preta', 'Preta')['est'])} to {f2(cell(I['by_year']['2023'], 'Preta', 'Preta')['est'])}; the regional "
        f"slopes ranged from {f2(slopes[lo_r])} in the {lo_r} to {f2(slopes[hi_r])} in the {hi_r} per decade, without a clear difference between regions (Figure 4B). "
        f"The hospitals' recording of Black mothers as Black rose more slowly, by {f2(HT['est'])} (95%CI {f2(HT['est'] - 1.96 * HT['se'])}; "
        f"{f2(HT['est'] + 1.96 * HT['se'])}) in log-odds per decade, from {f2(HY['2013']['est'])} for births of 2013 to {f2(HY['2023']['est'])} for births of 2023 (Figure "
        f"4C), while the share of births to mothers who declared themselves Black rose from {pct(BK['births_black_share']['2013'])} to "
        f"{pct(BK['births_black_share']['2023'])}.")
figure(d, "black_where_when", "Figure 4 - Black mothers' infants certified Black by municipality (A), by year and region (B), and the hospital's record of Black mothers "
                              "against the certificate of their infants by year (C), Brazil, 2013-2023",
       ["A: posterior means of a binomial BYM2 model over 5,570 municipalities; few deaths per municipality, so the map is smoothed strongly. B: national linkage with 95% "
        "confidence intervals; regional lines are conditional fits of a binomial mixed model (regional random effects at zero), not regional proportions. C: hospital by "
        "year of birth, certificate by year of death."])
