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
assert PL_["practice_person"]["hb_or"] > 1.5, "the mother's record no longer goes with the certificate beside the practice"
RB = R3["by_hospital_record_region_standardised"]
assert abs(RB["white"]["region_standardised"] - RB["brown"]["region_standardised"]) < 0.03 and RB["white"]["south_share"] > 0.3, "the White cell is no longer regional"
assert STD["2022"]["standardised_2013"] > STD["2013"]["standardised_2013"] + 0.03, "the standardised rise to 2022 is gone"
J22 = R3["joint_trend_2013_2022"]
assert J22["hospital_minus_certificate"] + 1.96 * J22["difference_se"] < 0, "without 2023 the hospital rises as fast as the certificate"
assert JT["hospital_minus_certificate"] + 1.96 * JT["difference_se"] < 0, "the hospital now rises as fast as the certificate"
w_ph, w_ot = FLR["within_hospital_black_declared_difference"]["physician_vs_nursing"], FLR["within_hospital_black_declared_difference"]["other_vs_nursing"]
assert abs(w_ph["est"]) < 0.02 and abs(w_ot["est"]) < 0.02, "who filled the birth record now changes the declaration within hospitals"

d.add_heading("Results", level=1)
para(d, f"Of {n0(I['linked'])} infant deaths of 2013-2023 linked to their birth records, {n0(IL['n'])} were of children of mothers who declared themselves Black; for "
        f"{n0(IN['with_hospital_record_black'])} of them the birth was linked to the mother's delivery admission in the public system ({n0(R3['n'])} with a race "
        "on that admission and its hospital identified, the set of the comparisons below), and these infants were "
        f"certified Black as often as the others ({ci(IN['black_with_record'])} against {ci(IN['black_without_record'])}). Across all deliveries of 2012-2023 linked "
        f"to their birth records, {n0(NT['hospital_declared_black'])} admissions of mothers who declared themselves Black carried a race.")
d.add_heading("Three records of the same families", level=2)
para(d, "Each later record used the Black category less than the mothers had declared it (Figure 2, Supplementary Table S2). Hospitals recorded mothers who declared themselves "
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
LADDER = ("Supplementary Table S2 - Race recorded for mothers who declared themselves Black, or for their children, by record, Brazil",
      ["Record", "Who classifies", "Black (95%CI)", "Brown (95%CI)", "White (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Census: weighted proportions of other, surviving children in 2010; standard errors below 0.005 treating the sample as simple. "
       f"Hospital: admissions with a race ({pct(NT['hospital_blank_share']['black'])} had none), bootstrap over hospitals. Certificate, infant: bootstrap over "
       "municipalities; the remainder is another category or none. Certificate, 1-4 years: candidate estimator, municipalities with fewer than 25,600 births a year. "
       "The populations and years differ between rows."])
figure(d, "black_ladder", "Figure 2 - Proportion recorded Black among mothers who declared themselves Black, or their children, by record and age, Brazil",
       ["The declaration bar is 1 by construction. Family: 2010 Census sample. Hospital: admissions of 2012-2023 with a race. Certificate, infant: linkage, 2013-2023; "
        "1-4 years: candidate estimator, municipalities with fewer than 25,600 births a year. Bars: 95% confidence intervals. Hatched: net ratios of counts, the records' Black count over the Black-declared mothers or their infants (Brown mothers recorded Black offset Black mothers recorded otherwise)."])
d.add_heading("The reference", level=2)
para(d, f"The mother's race on the birth record is entered by staff on her answer. Across all linked births, {pct(FLR['physician']['black_declared_share'], 1)} of "
        f"those filled by a physician declared the mother Black, {pct(FLR['nursing']['black_declared_share'], 1)} of those filled by nursing and "
        f"{pct(FLR['other staff']['black_declared_share'], 1)} of those filled by other staff; within the same hospital the differences were "
        f"{100 * w_ph['est']:.1f} (standard error {100 * w_ph['se']:.1f}) and {100 * w_ot['est']:.1f} ({100 * w_ot['se']:.1f}) percentage points against nursing: who "
        "filled the record hardly changed the declaration, which varied with the hospital's population."
        + (f" Of mothers with two births in the smaller municipalities ({n0(MV['pairs'])} pairs; {pct(MV['false_share'], 1)} expected by chance from the shifted-date "
           f"control), those who declared themselves Black at the first birth did so again in {ci(MV['declared_again|black'])}, against "
           f"{ci(MV['declared_again|brown'])} for Brown and {ci(MV['declared_again|white'])} for White mothers." if MV else ""))
HF = HD["by_practice_fifth"]
para(d, "The two records are written in the same hospital. The birth record is filled by the health establishment where the birth occurred, the mother's "
        f"race on her answer {cite('manual_dn2011')}; the admission is filled by the hospital's admitting staff. If the birth record's race were the mother's "
        "own answer, a hospital's share of mothers declared Black would follow the population it serves whatever its admission practice. It did not: in the "
        f"fifth of hospitals that recorded the fewest declared-Black mothers as Black on the admission (practice {f2(HF[0]['practice'])}), "
        f"{pct(HF[0]['dn_black'], 1)} of mothers were Black on the birth record against {pct(HF[0]['expected_black'], 1)} expected from the women aged 15-49 of "
        f"their municipalities in the 2022 Census; in the top fifth (practice {f2(HF[-1]['practice'])}), {pct(HF[-1]['dn_black'], 1)} against "
        f"{pct(HF[-1]['expected_black'], 1)} (Figure 6B; {n0(HD['hospitals'])} hospitals with 100 or more linked births). The association held with the "
        f"mothers' schooling held (slope {f2(HD['oe_black']['schooling']['slope'])}, standard error {f2(HD['oe_black']['schooling']['se'])} on the logit of "
        f"observed over expected) and vanished within states ({f2(HD['oe_black']['state']['slope'])}, {f2(HD['oe_black']['state']['se'])}): where hospitals "
        "record few Black mothers on the admission, the birth record also counts fewer Black mothers than the census holds, and both are properties of the state "
        "more than of each hospital. In those states the birth record's declaration is partly the hospital's, and the reference here is itself lower than "
        "self-declaration.")
CV = HD["coverage"]["2021"]
para(d, f"The comparison with the admission is limited to public-system deliveries ({pct(CV['linked_share'], 0)} of births in 2021). They left out mothers "
        f"with higher education (linked {pct(CV['by_schooling']['5'], 0)} of their births, against {pct(CV['by_schooling']['3'], 0)} for mothers with 4-7 years "
        f"of schooling) and White mothers more than Black ones ({pct(CV['by_race']['1'], 0)} against {pct(CV['by_race']['2'], 0)}): the hospital's record "
        "describes the public system, where most Black mothers give birth.")
d.add_heading("Person, chart or hospital", level=2)
para(d, "When the hospital had recorded the infant's own mother as Black, the infant was certified Black in "
        f"{ci(by_h['black']['black'])} of deaths; when it had recorded her as Brown, in {ci(by_h['brown']['black'])}; when as White, in {ci(by_h['white']['black'])} "
        f"(Supplementary Table S3). The White cell sat above the Brown one because {pct(RB['white']['south_share'], 0)} of these mothers lived in the South, "
        f"where certificates used the category most, against {pct(RB['brown']['south_share'], 0)} of those the hospital recorded as Brown; standardised to the "
        f"regions of all these infants, the three were {f2(RB['black']['region_standardised'])}, {f2(RB['brown']['region_standardised'])} and "
        f"{f2(RB['white']['region_standardised'])} (Figure 3A), and the Mantel-Haenszel odds ratio over regions for a Black against any other record was "
        f"{f2(R3['mh_over_regions']['est'])} ({f2(R3['mh_over_regions']['lo'])}; {f2(R3['mh_over_regions']['hi'])}). For the same {n0(R3['n'])} infants, the "
        f"hospital had recorded the mother as Black in {f2(R3['hospital_black_same_infants'])} and the certificate the infant in "
        f"{f2(R3['certified_black_same_infants'])}. Within the same delivery hospital, at equal schooling and age of the mother, birth weight, year and age at death, "
        f"the odds were {f2(CL_D['or'])} (95%CI {f2(CL_D['lo'])}; {f2(CL_D['hi'])}) times higher when the hospital had recorded the mother as Black "
        f"(Mantel-Haenszel {f2(MB['mh_delivery_hospital']['est'])}, {MB['mh_delivery_hospital']['strata']} hospitals; Breslow-Day p = "
        f"{MB['mh_delivery_hospital']['breslow_day_p']:.3f}, so the association varied between hospitals). If the certificate copied the delivery chart, the "
        "association would vanish where the chart was not at hand. It did not: within the establishments of death, it was "
        f"{f2(CL_T['or'])} (95%CI {f2(CL_T['lo'])}; {f2(CL_T['hi'])}) among infants who died where they were delivered and {f2(CL_E['or'])} (95%CI {f2(CL_E['lo'])}; "
        f"{f2(CL_E['hi'])}) among infants who died elsewhere ({n0(R3['elsewhere_informative']['deaths'])} deaths in {R3['elsewhere_informative']['strata']} "
        f"establishments with both records informative; Figure 3B). A shared upstream record, such as the prenatal card, would carry one entry to every later "
        "record; it is least likely without prenatal care and for deaths at home. Within the delivery hospital, the odds ratio was "
        f"{f2(R3['within_hospital_by_visits']['none']['est'])} (95%CI {f2(R3['within_hospital_by_visits']['none']['lo'])}; {f2(R3['within_hospital_by_visits']['none']['hi'])}) "
        f"for mothers with no prenatal visit ({n0(R3['within_hospital_by_visits']['none']['deaths'])} deaths), {f2(R3['within_hospital_by_visits']['1-6']['est'])} "
        f"with one to six and {f2(R3['within_hospital_by_visits']['7 or more']['est'])} with seven or more; among the {n0(R3['home_deaths']['mh_over_regions']['deaths'])} "
        f"infants who died at home it was {f2(R3['home_deaths']['mh_over_regions']['est'])} ({f2(R3['home_deaths']['mh_over_regions']['lo'])}; "
        f"{f2(R3['home_deaths']['mh_over_regions']['hi'])}) over regions. Where the death was investigated, the share certified Black was "
        f"{min(v['KK']['est'] for k, v in MC['investigation'].items() if v['KK']['n'] >= 100):.2f}-{max(v['KK']['est'] for k, v in MC['investigation'].items() if v['KK']['n'] >= 100):.2f} "
        "whatever the source of the investigation, including interviews with the family. For mothers who declared themselves Brown, the infant was certified Black in "
        f"{ci(bm['black']['black'])} when the hospital had recorded the mother as Black and {ci(bm['brown']['black'])} when as Brown.")
para(d, f"Hospitals differed in their practice: across {n0(HO['facilities']['n'])} hospitals with 30 or more Black mothers, the share recorded Black ranged from "
        f"{f2(HO['facilities']['p10'])} at the 10th percentile to {f2(HO['facilities']['p90'])} at the 90th (median {f2(HO['facilities']['p50'])}; Supplementary Table "
        f"S4, Supplementary Figure S1). With the practice estimated without the infant's own mother and shrunk toward the hospitals' mean, one standard deviation of "
        f"practice ({f2(R3['practice_per_sd']['sd_logit_hospitals'])} on the logit scale) multiplied the odds of being certified Black by "
        f"{ci3(R3['practice_per_sd']['practice'])} alone, {ci3(R3['practice_per_sd']['practice_composition_region_year'])} at equal composition, region and year, "
        f"and {ci3(R3['practice_per_sd']['practice_person'])} beside the hospital's record of the mother herself, whose odds ratio was "
        f"{f2(PL_['practice_person']['hb_or'])} ({n0(PL_['deaths'])} deaths, {n0(PL_['hospitals'])} hospitals; errors clustered by hospital). Since the "
        "hospital's practice shapes how it records the mother, the last estimate is the part of practice that does not pass through her record; "
        f"{pct(R3['practice_per_sd']['share_through_mothers_record'], 0)} of the effect at equal composition passed through it."
        + (f" The same Black mother recorded Black at one delivery was recorded Black again in {ci(MV['hospital_black_again|same hospital'])} of her deliveries in the "
           f"same hospital and {ci(MV['hospital_black_again|another hospital'])} in another, against {ci(MV['hospital_black_after_not|same hospital'])} and "
           f"{ci(MV['hospital_black_after_not|another hospital'])} when not recorded Black at the first delivery (odds ratios about {OR_SAME:.0f} in the same hospital, "
           f"which a hospital copying its own earlier file would also produce, and {OR_OTHER:.1f} in another); when she changed hospital, her record moved by "
           f"{f2(MV['movers_practice_slope']['est'])} (standard error {f2(MV['movers_practice_slope']['se'])}, clustered by the second hospital; {f2(MV['movers_practice_slope']['corrected'])} "
           f"corrected for the {pct(MV['movers_practice_slope']['chance_share'], 0)} of chance pairs) of the difference in the two hospitals' practice "
           f"({n0(MV['movers_practice_slope']['n'])} mothers; Figure 3C): a mother's record took on about the level of the hospital she moved to, while being recorded Black once still raised the odds in "
           "another hospital." if MV else ""))
figure(d, "black_hospital", "Figure 3 - Certified race of Black mothers' infants by the race the hospital recorded for the same mother at delivery (A), odds ratios "
                            "of being certified Black for the mother's record and per standard deviation of the hospital's practice (B), and the record of the same Black mother at two "
                            "deliveries in the same or another hospital (C), Brazil, 2012-2023",
       ["A: infant deaths linked to the birth record and the birth record to the delivery admission; bars, standardised to the regions of all these infants; "
        "points, crude. B: black, the mother recorded Black against not, within "
        "the delivery hospital (Mantel-Haenszel; conditional logistic regression adjusted for schooling and age of the mother, birth weight, year and age at death) "
        "and within the establishment of death, and without prenatal visits; blue, per standard deviation of the delivery hospital's practice estimated without the mother and shrunk, alone, at equal "
        "composition, region and year, and beside the mother's record, with the mother's record in that last model; errors clustered by hospital. C: mothers who "
        "declared themselves Black at both births, smaller municipalities, corrected for chance pairs by the shifted-date control. Bars: 95% confidence intervals."])
d.add_heading("The certifier", level=2)
para(d, f"Death verification services ({orx('certifierdeath verification service')}) and medical examiners ({orx('certifiermedical examiner (IML)')}) used the "
        f"Black category less than attending physicians, with the cause and place of death in the model (Figure 4). Among {n0(PHY['KK']['deaths'])} deaths of Black "
        f"mothers' infants of 2014-2018 with the certifying physician recorded ({n0(PHY['KK']['physicians'])} physicians), the variance of the log-odds of being "
        f"certified Black was {f2(PHY['KK']['all']['physician'])} between physicians, {f2(PHY['KK']['all']['death_estab'])} between establishments and "
        f"{f2(PHY['KK']['all']['mun6'])} between municipalities (Laplace approximation). Mothers under 20 had their infants certified Black less often "
        f"({orx('mother_age<20')}), and mothers with 0-3 years of schooling ({orx('school0-3')}) and with 12 or more ({orx('school12 or more')}) more often than "
        "those with 8-11.")
figure(d, "black_terms", "Figure 4 - Odds ratios of being certified Black for infants of Black mothers, full multilevel model, Brazil, 2013-2023",
       ["Logistic regression with a random intercept for the municipality (nAGQ = 0); also in the model, the municipality's composition, urbanisation, population, "
        "metropolitan status, physicians, certification and recording. References: attending physician, death in hospital, 0-6 days, perinatal cause, mother with 8-11 "
        "years of schooling and aged 20-34, birth weight 2,500 g or more, Southeast. Per decade: the year term. Bars: 95% confidence intervals."])
d.add_heading("Over time", level=2)
para(d, f"The certificate's use of the category rose from {f2(STD['2013']['crude'])} in 2013 to {f2(STD['2022']['crude'])} in 2022 and {f2(STD['2023']['crude'])} in 2023, "
        f"and standardised to the region, schooling and age of the Black mothers of 2013 from {f2(STD['2013']['standardised_2013'])} to "
        f"{f2(STD['2022']['standardised_2013'])} in 2022 and {f2(STD['2023']['standardised_2013'])} in 2023: the rise was not explained by the region, schooling and "
        "age of the Black mothers, although more mothers declared themselves Black ("
        f"{pct(BK['births_black_share']['2013'])} of births in 2013, {pct(BK['births_black_share']['2023'])} in 2023). For the same {n0(JT['n_infants'])} infants, "
        f"the certificate rose by {f2(JT['certificate_per_decade'])} in log-odds per decade and the hospital's record of their mothers by "
        f"{f2(JT['certificate_per_decade'] + JT['hospital_minus_certificate'])}, a difference of {f2(JT['hospital_minus_certificate'])} (95%CI "
        f"{f2(JT['hospital_minus_certificate'] - 1.96 * JT['difference_se'])}; {f2(JT['hospital_minus_certificate'] + 1.96 * JT['difference_se'])}) (Figure 5B); over 2013-2022 alone, before the hospital's race field changed, the "
        f"difference was {f2(J22['hospital_minus_certificate'])} (95%CI {f2(J22['hospital_minus_certificate'] - 1.96 * J22['difference_se'])}; "
        f"{f2(J22['hospital_minus_certificate'] + 1.96 * J22['difference_se'])}). "
        f"Across all deliveries, the hospitals recorded Black mothers as Black in {f2(HY['2013']['est'])} of births of 2013 and {f2(HY['2023']['est'])} of 2023; "
        f"admissions of Black-declared mothers with a race rose from {n0(HY['2022']['n'])} in 2022 to {n0(HY['2023']['n'])} "
        "in 2023 because the admission's race, blank for about a fifth of these mothers until 2022, was filled for nearly all from 2023, mostly with categories "
        "other than Black, which lowered the 2023 share below that of 2022. By region, the share certified Black rose in four regions and was highest in the South (Figure 5A).")
figure(d, "black_where_when", "Figure 5 - Infants of Black mothers certified Black by year, nationally and by region (A), and the hospital's record of Black mothers "
                              "against the certificate of their infants by year (B), Brazil, 2013-2023",
       ["A: linked deaths by region and year with binomial 95% confidence intervals, and the national linkage with bootstrap intervals. B: hospital by year of birth, certificate by year of death; dashed, the certificate standardised to the region, schooling and age of "
        "the Black mothers of 2013."])
d.add_heading("Where", level=2)
para(d, f"The hospital's practice differed most between states (Figure 6A): hospitals recorded declared-Black mothers as Black in {f2(_ps[PS_LO]['est'])} in "
        f"{PS_LO} and {f2(_ps[PS_HI]['est'])} in {PS_HI}, in the South and Southeast more than in the North and Northeast, the same order as the certificate's "
        "use of the category (Figure 5A).")
figure(d, "black_states", "Figure 6 - The hospital's recording of declared-Black mothers as Black by state (A), and the share of mothers declared Black on the "
                          "birth record against the share expected from the census, by fifth of the hospital's practice (B), Brazil, 2012-2023",
       ["A: births of 2012-2023 linked to their delivery admissions; proportion of mothers declared Black on the birth record whom the admission recorded as "
        "Black; 95% intervals from 500 bootstrap replicates over hospitals (wide where a state has few hospitals). B: hospitals with 100 or more linked births, "
        "by fifth of their practice (shrunk toward the national rate); expected share: each mother's municipality's share of Black women aged 15-49 in the 2022 "
        "Census (IBGE table 9606), averaged over the hospital's mothers."])
