# The Results of paper 5. Executed by build.py after text.py.
# ruff: noqa: F821
COMP = YC["by_composition"]
SCH = YC["by_schooling"]
CERT = YC["by_certifier"]
REG, PER = Y["by_kind_region"], Y["by_kind_period"]
STD = YC["standardised"]
G5 = ["natural", "transport", "suicide", "other external", "undetermined intent", "assault by firearm", "other assault", "legal intervention"]
GL5 = {"natural": "Natural causes", "transport": "Transport accidents", "suicide": "Suicide", "other external": "Other external causes",
       "undetermined intent": "Undetermined intent", "assault by firearm": "Assault by firearm", "other assault": "Assault by other means",
       "legal intervention": "Legal intervention"}
FOUND = {g: BC[g]["n_est"] / max(VI["deaths_total"][g], 1) for g in G5}
assert max(FOUND[g] for g in G5 if VI["deaths_total"][g] > 2000) - min(FOUND[g] for g in G5 if VI["deaths_total"][g] > 2000) < 0.12, "the share found now differs by cause"
assert all(cell(COMP["assault"][i]["matrix"], "Branca", "Branca")["est"] < cell(COMP["natural"][i]["matrix"], "Branca", "Branca")["est"] for i in range(5)), \
    "assault no longer below natural in every composition class"
d.add_heading("Results", level=1)
para(d, f"Of {n0(sum(VI['deaths_total'][g] for g in G5))} deaths at 15-24 years in the smaller municipalities, {n0(VI['deaths_total']['natural'])} were of "
        f"natural causes, {n0(VI['deaths_total']['assault by firearm'])} assaults by firearm and {n0(VI['deaths_total']['legal intervention'])} legal "
        f"interventions. The deceased was found among the candidate births in an estimated {pct(min(FOUND[g] for g in G5 if VI['deaths_total'][g] > 2000), 0)}-"
        f"{pct(max(FOUND[g] for g in G5 if VI['deaths_total'][g] > 2000), 0)} of deaths of the larger cause groups, alike across causes; the others had moved "
        "or were born elsewhere.")
d.add_heading("From birth to the certificate", level=2)
para(d, f"Among the deaths found, the share White was {f2(BC['natural']['birth_white']['est'])} at birth and {f2(BC['natural']['certified_white']['est'])} on "
        f"the certificate for natural deaths, a change of {ddc(BC['natural']['net_shift'])} (Table 1, Figure 2A). Every external cause lost more: "
        + "; ".join(f"{GL5[g].lower()} {f2(BC[g]['birth_white']['est'])} and {f2(BC[g]['certified_white']['est'])}" for g in EXT)
        + f". Against natural deaths, the change was {ddc(P_ASS)} for assaults and {ddc(P_EXT)} for the other external causes together: assaults lost no "
        f"more than transport accidents or suicides. Of those White at birth, {cc(BC['natural']['white_white'])} were certified White after a natural death "
        f"and {cc(BC['assault by firearm']['white_white'])} after a firearm assault; of those Brown at birth, {cc(BC['natural']['brown_brown'])} and "
        f"{cc(BC['assault by firearm']['brown_brown'])} were certified Brown, and {cc(BC['natural']['brown_white'])} and "
        f"{cc(BC['assault by firearm']['brown_white'])} White (Figure 2B).")
rows = []
for g in G5:
    b = BC[g]
    rows.append([GL5[g], n0(VI["deaths_total"][g]), pct(FOUND[g], 0), cc(b["birth_white"]), cc(b["certified_white"]), cc(b["white_white"]), cc(b["brown_brown"]),
                 cc(b["brown_white"])])
table(d, "Table 1 - Race at birth and on the death certificate of young people aged 15-24, by cause of death, Brazil, 2015-2024",
      ["Cause of death", "Deaths", "Found among birth candidates", "White at birth", "White on the certificate", "White at birth: certified White",
       "Brown at birth: certified Brown", "Brown at birth: certified White"], rows,
      ["People born in 2000-2009, residents of municipalities with fewer than 1,600 births a year (2000-2009). Candidate estimator with the other sex as "
       "control; shares among the deaths found; 95% confidence intervals from 500 bootstrap replicates over municipalities. Race at birth: the newborn's colour "
       "on the birth record of 2000-2009. Legal intervention: too few deaths for stable shares."])
figure(d, "violence_cause", "Figure 2 - Share White at birth and on the death certificate (A), and young people certified in their race at birth (B), by cause of "
                            "death, Brazil, 2015-2024",
       ["Deaths at 15-24 years found among their birth candidates, municipalities with fewer than 1,600 births a year; bars, 95% confidence intervals from "
        "500 bootstrap replicates over municipalities."])
para(d, f"Among young people White at birth, those who died by assault were certified White less often than those who died of natural causes in every fifth "
        f"of municipal composition (from {f2(cell(COMP['assault'][0]['matrix'], 'Branca', 'Branca')['est'])} against "
        f"{f2(cell(COMP['natural'][0]['matrix'], 'Branca', 'Branca')['est'])} where under 20% of births were White to "
        f"{f2(cell(COMP['assault'][4]['matrix'], 'Branca', 'Branca')['est'])} against {f2(cell(COMP['natural'][4]['matrix'], 'Branca', 'Branca')['est'])} where 80% "
        f"or more were, with overlapping intervals there), and standardised to the composition of natural deaths ({f2(STD['assault']['Branca']['Branca']['est'])} "
        f"against {f2(STD['natural']['Branca']['Branca']['est'])}); by region and period the difference kept its direction (Supplementary Table S1). It was "
        f"present whoever certified: {cc(cell(CERT['assault']['medical examiner'], 'Branca', 'Branca'))} of assaults certified by medical examiners and "
        f"{cc(cell(CERT['assault']['physician'], 'Branca', 'Branca'))} by attending physicians, against {cc(cell(CERT['external, not assault']['medical examiner'], 'Branca', 'Branca'))} "
        f"of other external deaths certified by medical examiners. The share certified White rose with the mother's schooling at birth for every cause: among "
        f"those White at birth who died by assault, {cc(cell(SCH['assault']['0-3'], 'Branca', 'Branca'))} with 0-3 years of schooling and "
        f"{cc(cell(SCH['assault']['8-11'], 'Branca', 'Branca'))} with 8-11 (Figure 3).")
figure(d, "violence_strata", "Figure 3 - Young people recorded White at birth and certified White, by cause of death, against the municipality's share of White "
                             "births (A), by certifier (B) and by the mother's schooling at birth (C), Brazil, 2015-2024",
       ["Candidate estimator, municipalities with fewer than 1,600 births a year in 2012-2023; bars, 95% confidence intervals of a difference of counts; cells with "
        "a standard error above 0.15 are not drawn."])
d.add_heading("Birth, hospital and certificate for the same deaths", level=2)
para(d, f"An earlier admission, ending at least 30 days before the death and not in death, was found for {pct(VI['with_admission']['natural'], 0)} of young "
        f"people who died of natural causes and {pct(VI['with_admission']['assault by firearm'], 0)} of those who died by firearm; each person was counted once, "
        f"and {pct(VI['hospital_race_missing']['natural'], 0)} and {pct(VI['hospital_race_missing']['assault by firearm'], 0)} of these persons had no race "
        "among White, Black and Brown on their admissions. For the same deaths at birth, in hospital and on the certificate (Figure 4B), the share White "
        f"fell from birth to the hospital record by {100 * -TR['natural']['birth_white->hospital_white']['est']:.0f} points for natural deaths, "
        f"{100 * -TR['transport']['birth_white->hospital_white']['est']:.0f} for transport accidents and "
        f"{100 * -TR['assault by firearm']['birth_white->hospital_white']['est']:.0f} for firearm assaults (assaults against natural {ddc(B_ASS)}). From the "
        f"hospital record to the certificate it changed by {100 * TR['natural']['hospital_white->certified_white']['est']:+.0f} points for natural deaths, "
        f"{100 * TR['transport']['hospital_white->certified_white']['est']:+.0f} for transport accidents and "
        f"{100 * TR['all assault']['hospital_white->certified_white']['est']:+.0f} for assaults (assaults against natural {ddc(H_ASS)}). The two records "
        "exchanged categories asymmetrically by cause: of young people the hospital recorded Brown, "
        f"{cc(hv('natural', 'brown', 'white'))} were certified White after a natural death and {cc(hv('assault by firearm', 'brown', 'white'))} after a firearm "
        f"assault, while of those the hospital recorded White, {cc(hv('natural', 'white', 'white'))} and {cc(hv('assault by firearm', 'white', 'white'))} were "
        f"certified White (Figure 4A, Supplementary Table S2). In the admission in which the young person died, the hospital recorded White "
        f"{f2(TM['natural']['hospital_white']['est'])} of natural deaths and the certificate {f2(TM['natural']['certified_white']['est'])}; for firearm deaths "
        f"{f2(TM['assault by firearm']['hospital_white']['est'])} and {f2(TM['assault by firearm']['certified_white']['est'])}: the hospital's record was darker "
        "than the certificate for every cause. The results were alike for men alone and with admissions ending at least 180 days before death "
        f"({f2(VI['person180']['assault by firearm']['cells']['hospital white|certified white']['est'])} of those recorded White certified White after a firearm "
        f"death). With the admissions' birth dates shifted by 7 or 14 days either way, where the person cannot be among them, the estimator still counted on "
        f"average {pct(PLS['assault by firearm'], 0)} as many persons as found for firearm deaths and {pct(PLS['natural'], 0)} for natural deaths, a residual "
        "of chance agreement the control did not remove, which draws the hospital shares of violent deaths toward their municipalities' population.")
figure(d, "violence_hospital", "Figure 4 - Agreement of the earlier hospital record and the certificate (A), and the share White at birth, in hospital and on the "
                               "certificate of the same deaths (B), by cause of death, Brazil, 2015-2024",
       ["Admissions of 2010-2024 that ended at least 30 days before the death and not in death, one record per person; candidate estimator with the other sex "
        "as control, municipalities with fewer than 1,600 births a year; A, 1,000 and B, 500 bootstrap replicates over municipalities; bars, 95% confidence "
        "intervals."])
