# The Results of paper 3. Executed by build.py after text.py.
# ruff: noqa: F821
bm = IN["brown_mother_by_hospital"]
HY = HO["black_by_year"]
NT = BK["net"]
HB = HO["black_bootstrap"]
FLR, MV = MC.get("filler", {}), MC.get("movers", {})
PHY = _json.loads((HERE / "results" / "physician.json").read_text(encoding="utf-8"))
PL_ = MB["practice_loo_eb"]
JT = MB["joint_trend_same_infants"]
STD = MB["certificate_by_year_standardised"]
CL_D, CL_E, CL_T = MB["clogit_delivery_hospital_adjusted"], MB["clogit_death_estab_elsewhere"], MB["clogit_death_estab_died_there"]
assert CL_E["lo"] > 1, "where the chart was not at hand the hospital's record of the mother no longer predicts the certificate"
assert PL_["practice_person"]["hb_or"] > 1.5 and PL_["practice_person"]["or_per_logit"] < 1.2, "practice now rivals the person"
assert STD["2023"]["standardised_2013"] > STD["2013"]["standardised_2013"] + 0.05, "the standardised rise is gone"
assert JT["hospital_minus_certificate"] + 1.96 * JT["difference_se"] < 0, "the hospital now rises as fast as the certificate"
w_ph, w_ot = FLR["within_hospital_black_declared_difference"]["physician_vs_nursing"], FLR["within_hospital_black_declared_difference"]["other_vs_nursing"]
assert abs(w_ph["est"]) < 0.02 and abs(w_ot["est"]) < 0.02, "who filled the birth record now changes the declaration within hospitals"

d.add_heading("Results", level=1)
para(d, f"Of {n0(I['linked'])} infant deaths of 2013-2023 linked to their birth records, {n0(IL['n'])} were of children of mothers who declared themselves Black; for "
        f"{n0(IN['with_hospital_record_black'])} of them the birth was linked to the mother's delivery admission in the public system, and these infants were "
        f"certified Black as often as the others ({ci(IN['black_with_record'])} against {ci(IN['black_without_record'])}). Across all deliveries of 2012-2023 linked "
        f"to their birth records, {n0(NT['hospital_declared_black'])} admissions of mothers who declared themselves Black carried a race.")
d.add_heading("Three records of the same families", level=2)
para(d, "Each later record used the Black category less than the mothers had declared it (Table 1, Figure 1). Hospitals recorded mothers who declared themselves "
        f"Black as Black at delivery in {ci(HB['black'])} of admissions with a race, as Brown in {ci(HB['brown'])} and as White in {ci(HB['white'])}, and left the race "
        f"blank in {pct(NT['hospital_blank_share']['black'])}; counting the blanks as not Black or as Black, {f2(MB['net']['hospital_black_share_blank_as_other'])} to "
        f"{f2(MB['net']['hospital_black_share_blank_as_black'])} of these mothers were recorded Black. Death certificates recorded their infants as Black in "
        f"{cbci('Preta>Preta')}, as Brown in {cbci('Preta>Parda')} and as White in {cbci('Preta>Branca')}. Counted net, so that Brown mothers recorded Black offset "
        f"Black mothers recorded otherwise, the hospitals recorded {ci(MB['net']['hospital_ratio'])} as many mothers as Black as declared themselves Black, and the "
        f"certificates {ci(MB['net']['certificate_ratio'])} as many infants as Black as there were infants of Black mothers; only "
        f"{pct(NT['certificate_brown_to_black']['est'])} of Brown mothers' infants were certified Black. In the same municipalities, certificates used the "
        f"category for {ci(LD['certificate_infant_below_25600'])} of infants and {cc(LD['certificate_1_4'])} of children aged 1-4 (the estimate at 5-9 years was too "
        f"imprecise to compare); families in 2010 reported as Black {f2(LD['family_child_0'])} of Black mothers' children under one year.")
F0B = CEN["by_band"]["0"]["Preta"]
W14B = CH["1-4"]["without_large"]["matrix"]["rows"]["Preta"]
rows = [["Family (census 2010), child under 1", "household", f2(F0B["Preta"]["est"]), f2(F0B["Parda"]["est"]), f2(F0B["Branca"]["est"])],
        ["Hospital, the mother at delivery (2012-2023)", "hospital staff", ci(HB["black"]), ci(HB["brown"]), ci(HB["white"])],
        ["Death certificate, infant (2013-2023)", "certifier or informant", cbci("Preta>Preta"), cbci("Preta>Parda"), cbci("Preta>Branca")],
        ["Death certificate, child 1-4 (2013-2024)", "certifier or informant", cc(W14B["Preta"]), cc(W14B["Parda"]), cc(W14B["Branca"])]]
table(d, "Table 1 - Race recorded for mothers who declared themselves Black, or for their children, by record, Brazil",
      ["Record", "Who classifies", "Black (95%CI)", "Brown (95%CI)", "White (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Census: weighted proportions of other, surviving children in 2010; standard errors below 0.005 treating the sample as simple. "
       f"Hospital: admissions with a race ({pct(NT['hospital_blank_share']['black'])} had none), bootstrap over hospitals. Certificate, infant: bootstrap over "
       "municipalities; the remainder is another category or none. Certificate, 1-4 years: candidate estimator, municipalities with fewer than 25,600 births a year. "
       "The populations and years differ between rows."])
figure(d, "black_ladder", "Figure 1 - Proportion recorded Black among mothers who declared themselves Black, or their children, by record and age, Brazil",
       ["The declaration bar is 1 by construction. Family: 2010 Census sample. Hospital: admissions of 2012-2023 with a race. Certificate, infant: linkage, 2013-2023; "
        "1-4 years: candidate estimator, municipalities with fewer than 25,600 births a year. Bars: 95% confidence intervals."])
d.add_heading("The reference", level=2)
para(d, f"The mother's race on the birth record is entered by staff on her answer. Across all linked births, {pct(FLR['physician']['black_declared_share'], 1)} of "
        f"those filled by a physician declared the mother Black, {pct(FLR['nursing']['black_declared_share'], 1)} of those filled by nursing and "
        f"{pct(FLR['other staff']['black_declared_share'], 1)} of those filled by other staff; within the same hospital the differences were "
        f"{100 * w_ph['est']:.1f} (standard error {100 * w_ph['se']:.1f}) and {100 * w_ot['est']:.1f} ({100 * w_ot['se']:.1f}) percentage points against nursing: who "
        "filled the record hardly changed the declaration, which varied with the hospital's population."
        + (f" Of mothers with two births in the smaller municipalities ({n0(MV['pairs'])} pairs; {pct(MV['false_share'], 1)} expected by chance from the shifted-date "
           f"control), those who declared themselves Black at the first birth did so again in {ci(MV['declared_again|black'])}, against "
           f"{ci(MV['declared_again|brown'])} for Brown and {ci(MV['declared_again|white'])} for White mothers." if MV else ""))
d.add_heading("Person, chart or hospital", level=2)
para(d, "When the hospital had recorded the infant's own mother as Black, the infant was certified Black in "
        f"{ci(by_h['black']['black'])} of deaths; when it had recorded her as Brown, in {ci(by_h['brown']['black'])}; when as White, in {ci(by_h['white']['black'])} "
        f"(Figure 2A, Supplementary Table S2). Within the same delivery hospital, at equal schooling and age of the mother, birth weight, year and age at death, "
        f"the odds were {f2(CL_D['or'])} (95%CI {f2(CL_D['lo'])}; {f2(CL_D['hi'])}) times higher when the hospital had recorded the mother as Black "
        f"(Mantel-Haenszel {f2(MB['mh_delivery_hospital']['est'])}, {MB['mh_delivery_hospital']['strata']} hospitals; Breslow-Day p = "
        f"{MB['mh_delivery_hospital']['breslow_day_p']:.3f}, so the association varied between hospitals). If the certificate copied the delivery chart, the "
        "association would vanish where the chart was not at hand. It did not: within the establishments of death, it was "
        f"{f2(CL_T['or'])} (95%CI {f2(CL_T['lo'])}; {f2(CL_T['hi'])}) among infants who died where they were delivered and {f2(CL_E['or'])} (95%CI {f2(CL_E['lo'])}; "
        f"{f2(CL_E['hi'])}) among the {n0(CL_E['n'])} who died elsewhere. For mothers who declared themselves Brown, the infant was certified Black in "
        f"{ci(bm['black']['black'])} when the hospital had recorded the mother as Black and {ci(bm['brown']['black'])} when as Brown.")
para(d, f"Hospitals differed in their practice: across {n0(HO['facilities']['n'])} hospitals with 30 or more Black mothers, the share recorded Black ranged from "
        f"{f2(HO['facilities']['p10'])} at the 10th percentile to {f2(HO['facilities']['p90'])} at the 90th (median {f2(HO['facilities']['p50'])}; Supplementary Table "
        f"S3). With the practice estimated without the infant's own mother and shrunk toward the hospitals' mean, the odds of being certified Black were "
        f"multiplied by {f2(PL_['practice']['or_per_logit'])} per logit unit of the delivery hospital's practice, by "
        f"{f2(PL_['practice_composition_region_year']['or_per_logit'])} at equal composition, region and year, and by "
        f"{f2(PL_['practice_person']['or_per_logit'])} (95%CI {math.exp(PL_['practice_person']['coef'] - 1.96 * PL_['practice_person']['se']):.2f}; "
        f"{math.exp(PL_['practice_person']['coef'] + 1.96 * PL_['practice_person']['se']):.2f}) beside the hospital's record of the mother herself, whose odds "
        f"ratio was {f2(PL_['practice_person']['hb_or'])} ({n0(PL_['deaths'])} deaths, {n0(PL_['hospitals'])} hospitals; errors clustered by hospital)."
        + (f" The same Black mother recorded Black at one delivery was recorded Black again in {ci(MV['hospital_black_again|same hospital'])} of her deliveries in the "
           f"same hospital and {ci(MV['hospital_black_again|another hospital'])} in another; when she changed hospital, her record moved by "
           f"{f2(MV['movers_practice_slope']['est'])} (standard error {f2(MV['movers_practice_slope']['se'])}; {f2(MV['movers_practice_slope']['corrected'])} "
           f"corrected for the {pct(MV['movers_practice_slope']['chance_share'], 0)} of chance pairs) of the difference in the two hospitals' practice "
           f"({n0(MV['movers_practice_slope']['n'])} mothers): the hospital sets how often its records say Black." if MV else ""))
figure(d, "black_hospital", "Figure 2 - Certified race of Black mothers' infants by the race the hospital recorded for the same mother at delivery (A), and each hospital's "
                            "practice against the certificates of Black mothers' infants who died there (B), Brazil, 2013-2023",
       ["A: infant deaths linked to the birth record and the birth record to the delivery admission; bars, 95% confidence intervals. B: hospitals with 10 or more "
        "deaths of Black mothers' infants; practice, share of Black mothers recorded Black at delivery, 2012-2023; the dotted line is equality."])
d.add_heading("The certifier", level=2)
para(d, f"Death verification services ({orx('certifierdeath verification service')}) and medical examiners ({orx('certifiermedical examiner (IML)')}) used the "
        f"Black category less than attending physicians, with the cause and place of death in the model (Figure 3). Among {n0(PHY['KK']['deaths'])} deaths of Black "
        f"mothers' infants of 2014-2018 with the certifying physician recorded ({n0(PHY['KK']['physicians'])} physicians), the variance of the log-odds of being "
        f"certified Black was {f2(PHY['KK']['all']['physician'])} between physicians, {f2(PHY['KK']['all']['death_estab'])} between establishments and "
        f"{f2(PHY['KK']['all']['mun6'])} between municipalities (Laplace approximation). Mothers under 20 had their infants certified Black less often "
        f"({orx('mother_age<20')}), and mothers with 0-3 years of schooling ({orx('school0-3')}) and with 12 or more ({orx('school12 or more')}) more often than "
        "those with 8-11.")
figure(d, "black_terms", "Figure 3 - Odds ratios of being certified Black for infants of Black mothers, full multilevel model, Brazil, 2013-2023",
       ["Logistic regression with a random intercept for the municipality (nAGQ = 0); also in the model, the municipality's composition, urbanisation, population, "
        "metropolitan status, physicians, certification and recording. References: attending physician, death in hospital, 0-6 days, perinatal cause, mother with 8-11 "
        "years of schooling and aged 20-34, birth weight 2,500 g or more, Southeast. Per decade: the year term. Bars: 95% confidence intervals."])
d.add_heading("Over time", level=2)
para(d, f"The certificate's use of the category rose from {f2(STD['2013']['crude'])} in 2013 to {f2(STD['2023']['crude'])} in 2023, and standardised to the region, "
        f"schooling and age of the Black mothers of 2013 from {f2(STD['2013']['standardised_2013'])} to {f2(STD['2023']['standardised_2013'])}: the rise was not a "
        "change in who the Black mothers were, although more mothers declared themselves Black ("
        f"{pct(BK['births_black_share']['2013'])} of births in 2013, {pct(BK['births_black_share']['2023'])} in 2023). For the same {n0(JT['n_infants'])} infants, "
        f"the certificate rose by {f2(JT['certificate_per_decade'])} in log-odds per decade and the hospital's record of their mothers by "
        f"{f2(JT['certificate_per_decade'] + JT['hospital_minus_certificate'])}, a difference of {f2(JT['hospital_minus_certificate'])} (95%CI "
        f"{f2(JT['hospital_minus_certificate'] - 1.96 * JT['difference_se'])}; {f2(JT['hospital_minus_certificate'] + 1.96 * JT['difference_se'])}) (Figure 4). "
        f"Across all deliveries, the hospitals recorded Black mothers as Black in {f2(HY['2013']['est'])} of births of 2013 and {f2(HY['2023']['est'])} of 2023; "
        f"admissions of Black-declared mothers with a race rose from {n0(MB['hospital_admissions_by_year']['2022'])} in 2022 to {n0(MB['hospital_admissions_by_year']['2023'])} "
        "in 2023 because the admission's race, blank for about a fifth of these mothers until 2022, was filled for nearly all from 2023, mostly with categories "
        "other than Black, which lowered that year's share. The use of the category clustered in space and was highest in the South, as "
        "a companion paper describes.")
figure(d, "black_where_when", "Figure 4 - Infants of Black mothers certified Black by year, nationally and by region (A), and the hospital's record of Black mothers "
                              "against the certificate of their infants by year (B), Brazil, 2013-2023",
       ["A: national linkage with 95% confidence intervals; the regional lines are conditional fits of a binomial mixed model (regional random effects at zero), not "
        "regional proportions. B: hospital by year of birth, certificate by year of death."])
