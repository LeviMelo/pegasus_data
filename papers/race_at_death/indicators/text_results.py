# The Results of the indicators paper. Executed by build.py after text.py.
# ruff: noqa: F821
STD2, WF = D2["region_standardised"], D2["waterfall"]
d.add_heading("Results", level=1)
para(d, f"Of {n0(I['certificates'])} infant deaths of 2013-2023, {pct(I['linked'] / I['certificates'])} were linked to their birth records; linked deaths were "
        "scaled to all certificates within strata of certified race, region, neonatal or later death and year, and "
        f"{pct(D2['no_race_share'])} of certificates carried no race. Scaled by certified race alone, the White to Brown ratio by the mother's race was "
        f"{f2(ROR['national']['mother_over_mother']['white']['est'])} instead of {f2(N2['mother_over_mother']['white']['est'])}, and the Black to Brown "
        f"{f2(ROR['national']['mother_over_mother']['black']['est'])} instead of {f2(N2['mother_over_mother']['black']['est'])}: the coarser scaling tilts the deaths "
        "toward the South and the neonatal period, where linkage succeeds more often. Births with no race, left out of every denominator, were "
        f"{pct(R3_['births_no_race']['2013'])} of births in 2013 and "
        f"{pct(R3_['births_no_race']['2023'])} in 2023 ({pct(R3_['births_no_race_all'])} "
        "overall); distributed like the births with a race, they would lower every rate by that share and leave the ratios unchanged.")
d.add_heading("Two classifications in one rate", level=2)
para(d, f"By the mother's race in both terms, infant mortality was {f1(N2['rates']['mother']['white'])} per 1,000 live births for children of White mothers, "
        f"{f1(N2['rates']['mother']['brown'])} for Brown, {f1(N2['rates']['mother']['black'])} for Black and {f1(N2['rates']['mother']['indigenous'])} for Indigenous "
        f"mothers: White to Brown {jr('mother_over_mother', 'white')}, Black to Brown {jr('mother_over_mother', 'black')}, Indigenous to Brown "
        f"{jr('mother_over_mother', 'indigenous')} (Table 1, Figure 2A). With certified deaths over the same births, the usual way, the ratios were "
        f"{jr('certified_over_mother', 'white')}, {jr('certified_over_mother', 'black')} and {jr('certified_over_mother', 'indigenous')}. With certified deaths over "
        f"births classified as households classify infants, they were {jr('certified_over_child', 'white')}, {jr('certified_over_child', 'black')} and "
        f"{jr('certified_over_child', 'indigenous')}. Standardised to the regions, the White to Brown ratio was {f2(STD2['mother_over_mother']['white'])} by the "
        f"mother's race, {f2(STD2['certified_over_mother']['white'])} the usual way and {f2(STD2['certified_over_child']['white'])} by the child's race: standardisation moved the usual ratio away from 1 and the mother's-race ratio "
        "toward it, because White births concentrate in the regions of lower mortality. The usual computation reproduces what is published from the same "
        f"systems: for 2017 it gave an Indigenous to White ratio of {f2(CAL_RATIO)}, as Caldas, Santos and Cardoso computed it {cite('caldas2022')} (1.81, 95%CI "
        "1.67; 1.96), with certified deaths over births by the mother's race. The linked cohort of 2012-2018 births "
        f"classified by the mother's race {cite('reboucas2022')} agrees: a crude White to Brown ratio of {f2(REB['under 1']['ratio'])} under one year.")
rows = []
for cname, lab in (("mother_over_mother", "Deaths and births by the mother's race"), ("certified_over_mother", "Certified deaths over births by the mother's race (usual)"),
                   ("certified_over_child", "Certified deaths over births by the child's race"), ("mother_over_child", "Deaths by the mother's race over births by the child's race")):
    AB = {"mother_over_mother": "mother", "certified_over_mother": "certified"}.get(cname)
    rows.append([lab] + [jr(cname, r) for r in ("white", "black", "indigenous")] + [f2(STD2[cname]["white"]) if cname in STD2 else "-"]
                + ([f"{n0(D2['absolute'][AB]['brown']['excess_deaths'])}; {n0(D2['absolute'][AB]['black']['excess_deaths'])}"] if AB else ["-"]))
table(d, "Table 1 - Infant mortality rate ratios against Brown with deaths and births classified by the mother's race or the child's, Brazil, 2013-2023",
      ["Numerator and denominator", "White to Brown (95%CI)", "Black to Brown (95%CI)", "Indigenous to Brown (95%CI)", "White to Brown, region-standardised",
       "Deaths above the White rate: Brown; Black mothers' infants"], rows,
      ["95%CI: delete-one-state jackknife on the log scale. Deaths by the mother's race: linked deaths scaled to all certificates within strata of certified race, region, neonatal or later death and year. Births by the "
       "child's race: births by the mother's race passed through the proportions in which households classify infants of mothers of each race (2010 Census). "
       "Region-standardised: Mantel-Haenszel over the five regions. Deaths above the White rate: (rate of the group minus the White rate) times the group's births, "
       f"2013-2023; negative, a deficit. Infant mortality by the mother's race: White {f1(RT2['white'])}, Brown {f1(RT2['brown'])} per 1,000 live births. "
       "Yellow (Asian) births and deaths are not shown. By region, certified deaths over the child's births gave a White to Brown ratio of "
       + ", ".join(f"{f2(RG2_[r]['certified_over_child']['white'])} ({r})" for r in RG2_) + " (point estimates)."])
para(d, f"Switching on the certificate's flows one at a time (Figure 2B), Brown mothers' infants certified White moved the White to Brown ratio from "
        f"{f2(WF[0]['ratios']['white'])} to {f2(WF[1]['ratios']['white'])}; White mothers' infants certified Brown brought it back to {f2(WF[2]['ratios']['white'])}; "
        f"the remaining flows and the deaths with no race took it to {f2(WF[-2]['ratios']['white'])}; and dividing by births classified as households classify "
        f"infants returned it to {f2(WF[-1]['ratios']['white'])}. This single order depends on the order chosen; averaged over every order (Figure 2B), Brown "
        f"mothers' infants certified White contributed {SH['players'][BW_]['est']:+.2f} (95%CI {SH['players'][BW_]['est'] - 1.96 * SH['players'][BW_]['se']:+.2f}; "
        f"{SH['players'][BW_]['est'] + 1.96 * SH['players'][BW_]['se']:+.2f}) to the log ratio, White mothers' infants certified Brown "
        f"{SH['players'][WB_]['est']:+.2f}, the deaths with no race {SH['players']['deaths with no race on the certificate']['est']:+.2f}, the other flows "
        f"{SH['players']['the other flows']['est'] + sum(SH['players'][k]['est'] for k in SH['players'] if k not in (BW_, WB_, 'the other flows', 'deaths with no race on the certificate')):+.2f}, "
        f"and the scaling of linked deaths {SH['residual_scaling']['est']:+.2f}, for a net change of {SH['certified'] - SH['start']:+.2f}. For Black to Brown, the step "
        f"for Black mothers' infants certified Brown took the ratio from {f2(WF[2]['ratios']['black'])} to {f2(WF[3]['ratios']['black'])} "
        f"(averaged over orders, {SK['players'][KB_]['est']:+.2f} in log ratio), and the child's denominator raised it only to {f2(WF[-1]['ratios']['black'])}: the "
        "certificate uses the Black category less than households do, so the Black infants' excess does not return.")
figure(d, "indicators_decomposition", "Figure 2 - Infant mortality rate ratios with deaths and births classified four ways (A), the ratios as each flow of the certificate "
                                      "is switched on (B), and the White to Brown ratio by year (C), Brazil, 2013-2023",
       ["A: 95% confidence intervals from a delete-one-state jackknife, log scale. B: contribution of each flow of the certificate to the change of the log "
        "ratio from deaths and births by the mother's race to certified deaths over births by the mother's race, averaged over every order in which the "
        "flows can be switched on (Shapley values), with jackknife intervals; orange, White to Brown; black, Black to Brown; net change at the bottom. C: three of the four classifications of A, with yearly "
        "delete-one-state jackknife intervals."])
d.add_heading("Ages, causes, years and absolute measures", level=2)
BP, BC = D2["by_period"], D2["by_cause"]
para(d, f"The usual ratio exceeded 1 and the mother's ratio stayed below it in every year of 2013-2023 (White to Brown by the mother's race {min(v['mother_over_mother']['white'] for v in D2['by_year'].values()):.2f}-"
        f"{max(v['mother_over_mother']['white'] for v in D2['by_year'].values()):.2f}, the usual way {min(v['certified_over_mother']['white'] for v in D2['by_year'].values()):.2f}-"
        f"{max(v['certified_over_mother']['white'] for v in D2['by_year'].values()):.2f}; Figure 2C), in the neonatal period ({f2(BP['neonatal']['mother_over_mother']['white'])} "
        f"and {f2(BP['neonatal']['certified_over_mother']['white'])}) and after it ({f2(BP['post-neonatal']['mother_over_mother']['white'])} and "
        f"{f2(BP['post-neonatal']['certified_over_mother']['white'])}), and for every cause group, though for congenital anomalies the mother's ratio "
        f"was close to 1 ({f2(BC['congenital']['mother_over_mother']['white'])}), from perinatal ({f2(BC['perinatal']['mother_over_mother']['white'])} "
        f"and {f2(BC['perinatal']['certified_over_mother']['white'])}) to infectious or respiratory causes ({f2(BC['infectious or respiratory']['mother_over_mother']['white'])} "
        f"and {f2(BC['infectious or respiratory']['certified_over_mother']['white'])}) (Supplementary Table S1). In absolute terms, by the mother's race "
        f"{n0(D2['absolute']['mother']['brown']['excess_deaths'])} deaths of Brown mothers' infants and {n0(D2['absolute']['mother']['black']['excess_deaths'])} of "
        f"Black mothers' infants exceeded the White mothers' rate over 2013-2023 ({D2['absolute']['mother']['brown']['difference_per_1000']:.1f} and "
        f"{D2['absolute']['mother']['black']['difference_per_1000']:.1f} per 1,000 live births); the usual indicator showed deficits of "
        f"{n0(-D2['absolute']['certified']['brown']['excess_deaths'])} and {n0(-D2['absolute']['certified']['black']['excess_deaths'])}. Counted against the White "
        f"mothers' rate of the same region, which removes the regional concentration of White births, the excess was {n0(EXW['brown']['within_regions'])} and "
        f"{n0(EXW['black']['within_regions'])}.")
para(d, "After infancy, with deaths related to births through the candidate estimator in municipalities with fewer than 25,600 births a year, the White to Brown "
        f"ratios were {rr(C14W)} by the mother's race and {rc(C14W)} by certified race over the same person-years at 1-4 years, and {rr(C59W)} and {rc(C59W)} at "
        "5-9 years; the shares found among candidates are lower than in infancy and the mother's-race ratios after infancy rest on the assumption that they "
        "do not differ by race (by region in Supplementary Figure S1, by state in Supplementary Table S4).")
d.add_heading("Regions", level=2)
RG2 = D2["by_region"]
para(d, "By region, the usual way reversed the ratio everywhere and the child's denominator did not restore the same value everywhere: certified deaths over "
        "the child's births gave a White to Brown ratio of "
        + ", ".join(f"{f2(RG2[r]['certified_over_child']['white'])} in the {r}" for r in RG2)
        + f", against {', '.join(f2(RG2[r]['mother_over_mother']['white']) for r in RG2)} by the mother's race. In 510 immediate regions, modelled separately "
        f"for each classification with Besag-York-Mollié effects, the certified ratio was credibly above 1 in {MS['certificate_above_1_credibly']} regions and "
        f"the mother's-race ratio credibly below 1 in {MS['mother_below_1_credibly']}; few White deaths per region draw the mother's-race estimates toward the "
        f"national term ({math.exp(RA['mother']['national']['mean']):.2f}), so they are shown ranked with their intervals rather than mapped (Figure 3A, Supplementary Table S2). Weighted by births, "
        f"the certified ratio was {f2(MSB['<10%']['ratio_of_ratios'])} times the mother's-race ratio where under 10% of births were White and "
        f"{f2(MSB['30-59%']['ratio_of_ratios'])} at 30-59%.")
figure(d, "regional_ratios", "Figure 3 - White to Brown infant mortality rate ratio by immediate region, by the mother's race ranked with intervals (A) and by certified race (B), the ratio of the two "
                             "(C), and the ratio of the two against the share of White births and GDP per capita (D), Brazil, 2013-2023",
       ["Posterior means of Poisson models with Besag-York-Mollié effects over 510 immediate regions, fitted separately for each classification; the colour scales "
        "of B-C are censored at their ends. A: posterior means and 95% credible intervals, coloured by macro-region. D: area of a point, live births; the line is "
        "the births-weighted mean by class of composition."])
