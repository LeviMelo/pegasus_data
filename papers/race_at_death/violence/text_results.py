# The Results of paper 5. Executed by build.py after text.py.
# ruff: noqa: F821
COMP = YC["by_composition"]
SCH = YC["by_schooling"]
CERT = YC["by_certifier"]
REG, PER = Y["by_kind_region"], Y["by_kind_period"]
STD = YC["standardised"]
assert all(cell(COMP["assault"][i]["matrix"], "Branca", "Branca")["est"] < cell(COMP["natural"][i]["matrix"], "Branca", "Branca")["est"] for i in range(5)), \
    "assault no longer below natural in every composition class"
assert max(Y["by_kind"][k]["found"] for k in KINDS) - min(Y["by_kind"][k]["found"] for k in KINDS) < 0.1, "the share found now differs by cause"
d.add_heading("Results", level=1)
para(d, f"Of {n0(sum(Y['by_kind'][k]['deaths'] for k in KINDS))} deaths at 15-24 years in the smaller municipalities, {n0(Y['by_kind']['natural']['deaths'])} "
        f"were of natural causes, {n0(Y['by_kind']['assault by firearm']['deaths'])} assaults by firearm and {n0(Y['by_kind']['legal intervention']['deaths'])} legal "
        f"interventions. The deceased was among the candidate births in {pct(min(Y['by_kind'][k]['found'] for k in KINDS), 0)}-"
        f"{pct(max(Y['by_kind'][k]['found'] for k in KINDS), 0)} of deaths, alike for every cause; the others had moved or were born elsewhere.")
d.add_heading("From birth to the certificate", level=2)
para(d, f"Of young people recorded White at birth, {cc(nat)} were certified White when they died of natural causes, against {cc(yc('transport'))} in transport "
        f"accidents, {cc(yc('suicide'))} in suicides, {cc(fire)} in assaults by firearm and {cc(leg)} in legal interventions (Table 1, Figure 2). Because fewer "
        "of those who died by assault were White at birth, the margins show the net change: among the deaths found, the share White was "
        f"{f2(MB_['natural'][0])} at birth and {f2(MB_['natural'][1])} on the certificate for natural deaths, {f2(MB_['transport'][0])} and "
        f"{f2(MB_['transport'][1])} for transport accidents, {f2(MB_['suicide'][0])} and {f2(MB_['suicide'][1])} for suicides, and "
        f"{f2(MB_['assault by firearm'][0])} and {f2(MB_['assault by firearm'][1])} for firearm assaults: every external cause lost more White "
        "between birth and death than natural causes did, assaults no more than transport accidents.")
rows = []
for k in KINDS:
    m = Y["by_kind"][k]
    rows.append([KL[k].capitalize(), n0(m["deaths"]), pct(m["found"], 0), f2(MB_[k][0]), f2(MB_[k][1]), cc(cell(m, "Branca", "Branca")), cc(cell(m, "Parda", "Parda")),
                 cc(cell(m, "Parda", "Branca"))])
table(d, "Table 1 - Race at birth and on the death certificate of young people aged 15-24, by cause of death, Brazil, 2015-2024",
      ["Cause of death", "Deaths", "Found among candidates", "White at birth (share)", "White on the certificate (share)", "White at birth: certified White",
       "Brown at birth: certified Brown", "Brown at birth: certified White"], rows,
      ["People born in 2000-2009, residents of municipalities with fewer than 1,600 births a year. Candidate estimator with the other sex as control; 95% "
       "confidence intervals from the difference of counts. Shares: among the deaths found among their birth candidates. Race at birth: the newborn's colour on "
       "the birth record of 2000-2009."])
figure(d, "violence_cause", "Figure 2 - Young people aged 15-24 certified in their race at birth, by cause of death, Brazil, 2015-2024",
       ["Candidate estimator, municipalities with fewer than 1,600 births a year; bars, 95% confidence intervals."])
para(d, f"The lower share certified White among those White at birth who died by assault did not come from where they lived: it held in every fifth of "
        f"municipal composition (from {f2(cell(COMP['assault'][0]['matrix'], 'Branca', 'Branca')['est'])} against "
        f"{f2(cell(COMP['natural'][0]['matrix'], 'Branca', 'Branca')['est'])} for natural deaths where under 20% of births were White to "
        f"{f2(cell(COMP['assault'][4]['matrix'], 'Branca', 'Branca')['est'])} against {f2(cell(COMP['natural'][4]['matrix'], 'Branca', 'Branca')['est'])} where 80% "
        f"or more were), standardised to the composition of natural deaths ({f2(STD['assault']['Branca']['Branca']['est'])} against "
        f"{f2(STD['natural']['Branca']['Branca']['est'])}), in each region and in both halves of the decade (Supplementary Table S1). It held whoever certified: "
        f"{cc(cell(CERT['assault']['medical examiner'], 'Branca', 'Branca'))} of assaults certified by medical examiners and "
        f"{cc(cell(CERT['assault']['physician'], 'Branca', 'Branca'))} by attending physicians, against {cc(cell(CERT['external, not assault']['medical examiner'], 'Branca', 'Branca'))} "
        f"of other external deaths certified by medical examiners. It fell steeply with the mother's schooling at birth: among those White at birth who died by "
        f"assault, {cc(cell(SCH['assault']['0-3'], 'Branca', 'Branca'))} were certified White when the mother had 0-3 years of schooling and "
        f"{cc(cell(SCH['assault']['8-11'], 'Branca', 'Branca'))} with 8-11 (Figure 3).")
figure(d, "violence_strata", "Figure 3 - Young people recorded White at birth and certified White, by cause of death, against the municipality's share of White "
                             "births (A), by certifier (B) and by the mother's schooling at birth (C), Brazil, 2015-2024",
       ["Candidate estimator, municipalities with fewer than 1,600 births a year; bars, 95% confidence intervals; cells with a standard error above 0.15 are not drawn."])
d.add_heading("Hospital records made during life", level=2)
para(d, f"An earlier admission, ending at least 30 days before the death, was found for {pct(VI['with_admission']['natural'], 0)} of young people who died of "
        f"natural causes and {pct(VI['with_admission']['assault by firearm'], 0)} of those who died by firearm, with "
        f"{VI['admissions_per_death']['natural']:.1f} and {VI['admissions_per_death']['assault by firearm']:.1f} admissions per death; each person was counted "
        f"once. Those who later died by assault had been recorded White less often in hospital ({f2(PM['all assault']['hospital_white']['est'])}, against "
        f"{f2(PM['natural']['hospital_white']['est'])} for natural and {f2(PM['all external, not assault']['hospital_white']['est'])} for other external deaths). "
        f"From the hospital record to the certificate, the share White changed by {PM['natural']['net_shift']['est']:+.2f} for natural deaths, "
        f"{PM['transport']['net_shift']['est']:+.2f} for transport accidents and {PM['assault by firearm']['net_shift']['est']:+.2f} for firearm assaults "
        f"(Figure 4). The two records agreed less for violent deaths, in both directions: of those recorded White in hospital, {cc(hv('natural', 'white', 'white'))} "
        f"were certified White after a natural death, {cc(hv('transport', 'white', 'white'))} after a transport accident and "
        f"{cc(hv('assault by firearm', 'white', 'white'))} after a firearm assault, while of those recorded Brown, {cc(hv('assault by firearm', 'brown', 'white'))} "
        f"of firearm deaths were certified White (Supplementary Table S2). The results were the same for men alone "
        f"({f2(VI['person_men']['assault by firearm']['cells']['hospital white|certified white']['est'])} for firearm deaths) and with admissions ending at least "
        f"180 days before death ({f2(VI['person180']['assault by firearm']['cells']['hospital white|certified white']['est'])}). In the admission in which the "
        f"young person died, the hospital recorded White {f2(TM['assault by firearm']['hospital_white']['est'])} of firearm deaths and the certificate "
        f"{f2(TM['assault by firearm']['certified_white']['est'])}; of those the hospital recorded White, "
        f"{f2(VI['terminal']['assault by firearm']['cells']['hospital white|certified white']['est'])} were certified White, against "
        f"{f2(VI['terminal']['natural']['cells']['hospital white|certified white']['est'])} of natural deaths. With the admissions' birth dates moved by a week, "
        f"where the person cannot be among them, the estimator still counted {pct(abs(PLC['assault by firearm']), 0)} as many persons for firearm deaths and "
        f"{pct(abs(PLC['natural']), 0)} for natural deaths, a residual of chance agreement the control did not remove.")
figure(d, "violence_hospital", "Figure 4 - Young people recorded White at an earlier hospital admission and certified White at death (A), and the share White in the "
                               "hospital and on the certificate of the same deaths (B), by cause of death, Brazil, 2015-2024",
       ["Admissions of 2010-2024 that ended at least 30 days before the death, one record per person; candidate estimator with the other sex as control, "
        "municipalities with fewer than 1,600 births a year; bars, 95% confidence intervals from 1,000 bootstrap replicates over municipalities."])
