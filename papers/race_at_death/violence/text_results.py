# The Results of paper 5. Executed by build.py after text.py.
# ruff: noqa: F821
COMP = YC["by_composition"]
SCH = YC["by_schooling"]
CERT = YC["by_certifier"]
PLACE = YC["by_place"]
REG, PER = Y["by_kind_region"], Y["by_kind_period"]
STD = YC["standardised"]
hw_nat, hw_fire, hw_as = hv("natural", "white", "white"), hv("assault by firearm", "white", "white"), hv("all assault", "white", "white")
assert all(cell(COMP["assault"][i]["matrix"], "Branca", "Branca")["est"] < cell(COMP["natural"][i]["matrix"], "Branca", "Branca")["est"] for i in range(5)), \
    "assault no longer below natural in every composition class"
assert max(Y["by_kind"][k]["found"] for k in KINDS) - min(Y["by_kind"][k]["found"] for k in KINDS) < 0.1, "the share found now differs by cause"
d.add_heading("Results", level=1)
para(d, f"Of {n0(sum(Y['by_kind'][k]['deaths'] for k in KINDS))} deaths at 15-24 years in the smaller municipalities, {n0(Y['by_kind']['natural']['deaths'])} "
        f"were of natural causes, {n0(Y['by_kind']['assault by firearm']['deaths'])} assaults by firearm and {n0(Y['by_kind']['legal intervention']['deaths'])} legal "
        f"interventions. The deceased was among the candidate births in {pct(min(Y['by_kind'][k]['found'] for k in KINDS), 0)}-"
        f"{pct(max(Y['by_kind'][k]['found'] for k in KINDS), 0)} of deaths, alike for every cause; the others had moved or were born elsewhere.")
d.add_heading("Race at birth and on the certificate", level=2)
para(d, f"Of young people recorded White at birth, {cc(nat)} were certified White when they died of natural causes, against {cc(yc('transport'))} in transport "
        f"accidents, {cc(fire)} in assaults by firearm and {cc(leg)} in legal interventions; the remainder were mostly certified Brown ({cc(yc('assault by firearm', 'Branca', 'Parda'))} "
        f"for firearm deaths). Of those recorded Brown at birth, {cc(yc('natural', 'Parda', 'Parda'))} of natural and {cc(yc('assault by firearm', 'Parda', 'Parda'))} of "
        f"firearm deaths were certified Brown (Table 1, Figure 1). The departure toward Brown was specific to the cause: it was larger for every kind of assault "
        "than for transport accidents or suicide, which are also certified by medical examiners.")
rows = []
for k in KINDS:
    m = Y["by_kind"][k]
    rows.append([KL[k].capitalize(), n0(m["deaths"]), pct(m["found"], 0), cc(cell(m, "Branca", "Branca")), cc(cell(m, "Branca", "Parda")), cc(cell(m, "Parda", "Parda")),
                 cc(cell(m, "Parda", "Branca")), cc(cell(m, "Preta", "Preta"))])
table(d, "Table 1 - Certified race of young people aged 15-24 according to the race recorded at their birth, by cause of death, Brazil, 2015-2024",
      ["Cause of death", "Deaths", "Found among candidates", "White at birth: certified White", "White at birth: certified Brown", "Brown at birth: certified Brown",
       "Brown at birth: certified White", "Black at birth: certified Black"], rows,
      ["People born in 2000-2009, residents of municipalities with fewer than 1,600 births a year. Candidate estimator with the other sex as control; 95% "
       "confidence intervals from the difference of counts. Race at birth: the newborn's colour on the birth record of 2000-2009."])
figure(d, "violence_cause", "Figure 1 - Young people aged 15-24 certified in their race at birth, by cause of death, Brazil, 2015-2024",
       ["Candidate estimator, municipalities with fewer than 1,600 births a year; bars, 95% confidence intervals."])
d.add_heading("Composition, place, certifier and schooling", level=2)
para(d, f"The gap did not come from where the victims lived. In every fifth of municipal composition, those recorded White at birth were certified White less "
        f"often after an assault than after a natural death (from {f2(cell(COMP['assault'][0]['matrix'], 'Branca', 'Branca')['est'])} against "
        f"{f2(cell(COMP['natural'][0]['matrix'], 'Branca', 'Branca')['est'])} where under 20% of births were White to "
        f"{f2(cell(COMP['assault'][4]['matrix'], 'Branca', 'Branca')['est'])} against {f2(cell(COMP['natural'][4]['matrix'], 'Branca', 'Branca')['est'])} where 80% or "
        f"more were; Figure 2A), and standardised to the composition of natural deaths it was {f2(STD['assault']['Branca']['Branca']['est'])} for assaults and "
        f"{f2(STD['natural']['Branca']['Branca']['est'])} for natural deaths. It held in each region (assault against natural: "
        + "; ".join(f"{r} {f2(cell(REG['assault'][r], 'Branca', 'Branca')['est'])} against {f2(cell(REG['natural'][r], 'Branca', 'Branca')['est'])}" for r in REG["assault"])
        + f"), in 2015-2019 and 2020-2024, and in deaths in the street ({f2(cell(PLACE['assault']['street'], 'Branca', 'Branca')['est'])} for assaults, "
        f"{f2(cell(PLACE['natural']['street'], 'Branca', 'Branca')['est'])} for natural causes) as in health facilities. Within deaths certified by medical "
        f"examiners, those recorded White at birth were certified White in {cc(cell(CERT['assault']['medical examiner'], 'Branca', 'Branca'))} of assaults and "
        f"{cc(cell(CERT['external, not assault']['medical examiner'], 'Branca', 'Branca'))} of other external deaths (Figure 2B). The certified race rose steeply with the "
        f"mother's schooling at birth: among those recorded White at birth who died by assault, {cc(cell(SCH['assault']['0-3'], 'Branca', 'Branca'))} were certified White "
        f"when the mother had 0-3 years of schooling and {cc(cell(SCH['assault']['8-11'], 'Branca', 'Branca'))} with 8-11 (Figure 2C).")
figure(d, "violence_strata", "Figure 2 - Young people recorded White at birth and certified White, by cause of death, against the municipality's share of White "
                             "births (A), by certifier (B) and by the mother's schooling at birth (C), Brazil, 2015-2024",
       ["Candidate estimator, municipalities with fewer than 1,600 births a year; bars, 95% confidence intervals; cells with a standard error above 0.15 are not drawn."])
d.add_heading("An earlier hospital record", level=2)
para(d, f"Young people whose earlier admission recorded them as White were certified White in {cc(hw_nat)} of natural deaths, {cc(hv('transport', 'white', 'white'))} "
        f"of transport deaths, {cc(hw_fire)} of firearm assaults and {cc(hw_as)} of all assaults (Figure 3). Of young people certified Brown after an assault, "
        f"{cc(hv('all assault', 'white', 'brown', 'certified'))} had been recorded White at an earlier admission, against {cc(hv('natural', 'white', 'brown', 'certified'))} of "
        f"those certified Brown after a natural death.")
figure(d, "violence_hospital", "Figure 3 - Young people recorded White at an earlier hospital admission and certified White at death, by cause of death, Brazil, "
                               "2015-2024",
       ["Admissions of 2010-2024 that ended at least 30 days before the death; candidate estimator with the other sex as control, municipalities with fewer than "
        "1,600 births a year; bars, 95% confidence intervals from a bootstrap over municipalities."])
