# The Results of paper 4. Executed by build.py after text.py.
# ruff: noqa: F821
KMIX = PM["black|is_black"]
WMIX = PM["black|is_white"]
PMIX = PM["brown|is_white"]
RMX = {y: V2[f"{y}|brown|relation_mix"] for y in (2010, 2022)}
assert abs(WMIX["2022_at_2010_partners"] - WMIX["crude"]["2022"]) < 0.005, "Black mothers' children White: the partner mix now explains the rise"
assert PMIX["partner_share"]["2022"]["white"] < PMIX["partner_share"]["2010"]["white"], "Brown mothers: White partners no longer fewer"
assert RMX[2022]["05"] > RMX[2010]["05"] + 0.05, "the stepfather structures no longer grew"
d.add_heading("Results", level=1)
para(d, f"The rule paired {n0(MX['2010']['brown|all']['white']['records'])} children aged 0-9 of Brown mothers, "
        f"{n0(MX['2010']['white|all']['white']['records'])} of White and {n0(MX['2010']['black|all']['white']['records'])} of Black mothers in 2010, and "
        f"{n0(MX['2022']['brown|all']['white']['records'])}, {n0(MX['2022']['white|all']['white']['records'])} and {n0(MX['2022']['black|all']['white']['records'])} "
        f"in 2022. Among Brown mothers' children aged 0-9 in the pairs, the partner was the father of {pct(RMX[2010]['04'], 0)} in 2010 and "
        f"{pct(RMX[2022]['04'], 0)} in 2022; the child was the responsible woman's only (a stepfather or no partner) for {pct(RMX[2010]['05'], 0)} and "
        f"{pct(RMX[2022]['05'], 0)}. The children of the couple living with the mother were {pct(CO['2010|0-4|brown']['child_of_couple'], 0)} of Brown children "
        f"aged 0-4 in 2010 and {pct(CO['2022|0-4|brown']['child_of_couple'], 0)} in 2022, {pct(CO['2010|10-14|brown']['child_of_couple'], 0)} and "
        f"{pct(CO['2022|10-14|brown']['child_of_couple'], 0)} at 10-14 years and {pct(CO['2010|20-24|brown']['child_of_couple'], 0)} and "
        f"{pct(CO['2022|20-24|brown']['child_of_couple'], 0)} at 20-24 (Figure 5C).")
d.add_heading("The child against the mother", level=2)
para(d, f"Households reported most White mothers' children as White and most Brown mothers' children as Brown, but fewer than half of Black mothers' "
        f"children as Black (Figure 2, Supplementary Table S1). At 0-4 years in 2022, White mothers' children were reported White in {dci(v(2022, 'white', 'white'), 3)}, "
        f"Brown mothers' Brown in {dci(v(2022, 'brown', 'brown'), 3)} and White in {dci(v(2022, 'brown', 'white'), 3)}, and Black mothers' Black in "
        f"{dci(v(2022, 'black', 'black'), 3)}, Brown in {dci(v(2022, 'black', 'brown'), 3)} and White in {dci(v(2022, 'black', 'white'), 3)}. Between 2010 and "
        f"2022 the share changed by {chg(v(2010, 'brown', 'white'), v(2022, 'brown', 'white'))} for Brown mothers' children reported White, by "
        f"{chg(v(2010, 'black', 'black'), v(2022, 'black', 'black'))} for Black mothers' children reported Black and by "
        f"{chg(v(2010, 'black', 'white'), v(2022, 'black', 'white'))} for Black mothers' children reported White. The intervals reflect sampling alone; the "
        "changes are small against what the next sections show about who the mothers and partners are.")
figure(d, "family_matrix", "Figure 2 - Race reported for children aged 0-4 according to the race of their mother (A-C), and at 0-9 years in 2010, 2022 and 2022 "
                           "standardised to the 2010 mothers' schooling and region (D), Brazilian Censuses of 2010 and 2022",
       ["Children of the household's couple living with their mother. Weighted proportions with design-based 95% confidence intervals (most narrower than the "
        "markers)."])
d.add_heading("Father, stepfather and siblings", level=2)
para(d, f"The child's race followed the father's (Figure 3A, 3B). A Brown mother's child aged 0-9 was reported White in {dci(F_W[0])} in 2010 and "
        f"{dci(F_W[1])} in 2022 when the father was White, against {dci(F_B[0])} and {dci(F_B[1])} when he was Brown, and "
        f"{f2(rel(2010, 'brown', 'is_white', FATHER, 'black')['est'])} and {f2(rel(2022, 'brown', 'is_white', FATHER, 'black')['est'])} when he was Black. With a "
        f"White stepfather the share was {f2(rel(2010, 'brown', 'is_white', STEP5, 'white')['est'])} and {f2(rel(2022, 'brown', 'is_white', STEP5, 'white')['est'])} "
        f"for the mother's own child and {f2(rel(2010, 'brown', 'is_white', STEP6, 'white')['est'])} and {f2(rel(2022, 'brown', 'is_white', STEP6, 'white')['est'])} "
        f"for the man's stepchild, against {min(rel(y, 'brown', 'is_white', r, 'brown')['est'] for y in (2010, 2022) for r in (STEP5, STEP6)):.2f}-"
        f"{max(rel(y, 'brown', 'is_white', r, 'brown')['est'] for y in (2010, 2022) for r in (STEP5, STEP6)):.2f} "
        "with a Brown stepfather: the gap a White partner makes was two to three times larger when he was the father. A stepfather still mattered, "
        f"and a Black stepfather went with more White children ({f2(rel(2022, 'brown', 'is_white', STEP5, 'black')['est'])}) than a Black father "
        f"({f2(rel(2022, 'brown', 'is_white', FATHER, 'black')['est'])}). Black mothers' children were reported Black in "
        f"{dci(rel(2022, 'black', 'is_black', FATHER, 'black'))} with a Black father, {dci(rel(2022, 'black', 'is_black', FATHER, 'brown'))} with a Brown father and "
        f"{dci(rel(2022, 'black', 'is_black', FATHER, 'white'))} with a White one, and in {f2(rel(2022, 'black', 'is_black', STEP5, 'black')['est'])} with a "
        f"Black stepfather. With no partner, Brown mothers' children were reported White in {dci(bp(2022, 'brown', 'is_white', 'partner', 'no partner'))}.")
para(d, f"Siblings of the same couple were reported in different races in {pct(SIB['2010|brown|white']['discordant'], 0)} (2010) and "
        f"{pct(SIB['2022|brown|white']['discordant'], 0)} (2022) of households of a Brown mother and a White partner with two or more children aged 0-9, "
        f"{pct(SIB['2022|black|white']['discordant'], 0)} of a Black mother and a White partner and {pct(SIB['2022|white|brown']['discordant'], 0)} of a White "
        f"mother and a Brown partner, against {pct(SIB['2022|brown|brown']['discordant'], 0)} where both were Brown, {pct(SIB['2022|black|black']['discordant'], 0)} "
        f"where both were Black and {pct(SIB['2022|white|white']['discordant'], 1)} where both were White (Figure 3C): in mixed couples the household did not "
        "apply one category to all its children.")
para(d, f"In the model of both censuses (Table 1), a White partner multiplied the odds of a Brown mother's child being reported White by "
        f"{orf('brown|is_white', 'partner[T.white]')}, a mother with higher education by {orf('brown|is_white', 'instruction[T.higher complete]')} against no or "
        f"incomplete primary schooling, and the South by {orf('brown|is_white', 'C(region)[T.South]')} against the Centre-West. Between the censuses the odds "
        f"rose with White partners (census by partner interaction {IA['C(census)[T.2022]:partner[T.white]']['est']:.2f} in log-odds, standard error "
        f"{IA['C(census)[T.2022]:partner[T.white]']['se']:.2f}) and with Black partners ({IA['C(census)[T.2022]:partner[T.black]']['est']:.2f}, "
        f"{IA['C(census)[T.2022]:partner[T.black]']['se']:.2f}), not with no partner ({IA['C(census)[T.2022]:partner[T.no partner]']['est']:.2f}, "
        f"{IA['C(census)[T.2022]:partner[T.no partner]']['se']:.2f}); the rise held among fathers ({f2(F_W[0]['est'])} to {f2(F_W[1]['est'])}), so it is not the "
        f"growth of stepfather households. A Brown partner multiplied the odds of a Black mother's child being reported Black by {orf('black|is_black', 'partner[T.brown]')}.")
d.add_heading("Who the mothers and partners were", level=2)
para(d, f"Partners changed between the censuses: {pct(PMIX['partner_share']['2010']['white'], 0)} of Brown mothers of children aged 0-9 had a White partner in "
        f"2010 and {pct(PMIX['partner_share']['2022']['white'], 0)} in 2022, and {pct(PMIX['partner_share']['2010']['no partner'], 0)} and "
        f"{pct(PMIX['partner_share']['2022']['no partner'], 0)} no partner; {pct(KMIX['partner_share']['2010']['black'], 0)} and "
        f"{pct(KMIX['partner_share']['2022']['black'], 0)} of Black mothers had a Black partner. At the partners of 2010, Brown mothers' children would have been "
        f"reported White in {f2(PMIX['2022_at_2010_partners'])} in 2022 (observed {f2(PMIX['crude']['2022'])}; 2010 {f2(PMIX['crude']['2010'])}). The mothers "
        "changed more: the share of Black mothers of children aged 0-9 with no or incomplete primary schooling fell from "
        f"{pct(DR['black|is_black']['instruction_2010']['none or primary incomplete'], 0)} to {pct(DR['black|is_black']['instruction_2022']['none or primary incomplete'], 0)} "
        f"and with higher education rose from {pct(DR['black|is_black']['instruction_2010']['higher complete'], 0)} to "
        f"{pct(DR['black|is_black']['instruction_2022']['higher complete'], 0)}. Given the 2010 mothers' instruction and region, the 2022 share of Brown mothers' "
        f"children aged 0-9 reported White was {f2(DR['brown|is_white']['2022_at_2010_mothers'])} (observed {f2(DR['brown|is_white']['2022'])}; 2010 "
        f"{f2(DR['brown|is_white']['2010'])}), of Black mothers' children reported Black {f2(DR['black|is_black']['2022_at_2010_mothers'])} (observed "
        f"{f2(DR['black|is_black']['2022'])}; 2010 {f2(DR['black|is_black']['2010'])}) and reported White {f2(DR['black|is_white']['2022_at_2010_mothers'])} "
        f"(observed {f2(DR['black|is_white']['2022'])}; 2010 {f2(DR['black|is_white']['2010'])}): the small national changes depend on who the women declaring "
        "each category were (Figure 2D).")
rows = []
for key, lab in (("brown|is_white", "Brown mother, child White"), ("black|is_black", "Black mother, child Black")):
    for term, val in MD[key].items():
        if isinstance(val, dict):
            rows.append([lab, term.replace("C(", "").replace(")[T.", ": ").replace("[T.", ": ").replace("]", ""), f"{val['or']:.2f} ({val['lo']:.2f}; {val['hi']:.2f})"])
table(d, "Table 1 - Odds ratios of the race reported for children aged 0-9, logistic models of the Censuses of 2010 and 2022 together, Brazil",
      ["Outcome", "Term", "Odds ratio (95%CI)"], rows,
      ["References: census 2010; partner of the mother's race; mother with no or incomplete primary schooling; child aged 0-4; mother aged 25-34; boy; "
       "Centre-West. Weighted; standard errors clustered by household. Census by partner interactions in the text."])
figure(d, "family_partner", "Figure 3 - Children aged 0-9 reported White, of Brown mothers (A), and reported Black, of Black mothers (B), by the race of the mother's "
                            "partner and whether he is the father, and households whose children aged 0-9 are reported in different races (C), Brazilian Censuses of "
                            "2010 and 2022",
       ["Partner: the man of the household's couple. A, B: weighted proportions with design-based 95% confidence intervals; father, child of both; stepfather, "
        "child of the responsible woman only or stepchild of the responsible man. C: households with two or more children aged 0-9 of the couple, by the "
        "mother's and the partner's race."])
d.add_heading("Who answered", level=2)
para(d, f"In 2022 the mother answered for {pct(IN2['share_0_14']['mother'], 0)} of the children aged 0-14 of the pairs, the partner for "
        f"{pct(IN2['share_0_14']['partner'], 0)}, another resident for {pct(IN2['share_0_14']['other resident'], 0)} and a non-resident for "
        f"{pct(IN2['share_0_14']['non-resident'], 0)}; the mother answered for herself in {pct(IN2['mother_informant']['self'], 0)} of the pairs and the partner "
        f"for her in {pct(IN2['mother_informant']['partner'], 0)}. Within the same couple, the child leaned toward the answering partner's race (Figure 4): a "
        f"Brown mother's child with a White partner was reported White in {dci(IN2['brown|white|partner']['white'])} when he answered and "
        f"{dci(IN2['brown|white|mother']['white'])} when the mother did; a Black mother's child with a White partner in {f2(IN2['black|white|partner']['white']['est'])} "
        f"and {f2(IN2['black|white|mother']['white']['est'])}; with a Black partner, the child was reported Black in {f2(IN2['black|black|partner']['black']['est'])} "
        f"and {f2(IN2['black|black|mother']['black']['est'])}, and with a Brown partner in {f2(IN2['black|brown|partner']['black']['est'])} and "
        f"{f2(IN2['black|brown|mother']['black']['est'])}. Who answers is not chosen at random: the partner answers in households where he is at home, which "
        "may differ in other ways.")
figure(d, "family_informant", "Figure 4 - Children aged 0-9 reported in a race according to who answered for them, by the mother's and the partner's race, Brazilian "
                              "Census of 2022",
       ["Weighted proportions with design-based 95% confidence intervals."])
d.add_heading("Age and cohort", level=2)
para(d, f"Older children were reported Black more often: Black mothers' children were reported Black in {dci(bp(2010, 'black', 'is_black', 'age', '0-4'))} at "
        f"0-4 years and {dci(bp(2010, 'black', 'is_black', 'age', '20-24'))} at 20-24 in 2010, and {dci(bp(2022, 'black', 'is_black', 'age', '0-4'))} and "
        f"{dci(bp(2022, 'black', 'is_black', 'age', '20-24'))} in 2022 (Figure 5B). The children aged 0-4 in 2010 (born 2006-2010) overlap for about three of "
        f"five birth years those aged 10-14 in 2022 (born 2008-2012), who were reported Black in {dci(bp(2022, 'black', 'is_black', 'age', '10-14'))}; the "
        f"difference ({bp(2022, 'black', 'is_black', 'age', '10-14')['est'] - bp(2010, 'black', 'is_black', 'age', '0-4')['est']:+.2f}) is about half the "
        f"gradient between 0-4 and 10-14 in the 2010 cross-section ({bp(2010, 'black', 'is_black', 'age', '10-14')['est'] - bp(2010, 'black', 'is_black', 'age', '0-4')['est']:+.2f}), "
        "and different mothers, partners and informants report each time, so age and cohort cannot be separated. For Brown mothers the gradient ran the "
        f"other way: their children were reported White in {dci(bp(2022, 'brown', 'is_white', 'age', '0-4'))} at 0-4 years and "
        f"{dci(bp(2022, 'brown', 'is_white', 'age', '10-14'))} at 10-14 (Figure 5A). Across the whole population, five-year birth cohorts of {CF['first']}-"
        f"{CF['last'] + 4} were reported White less often at each later census in {CF['white_fell']} of {CF['intervals']} intervals (Figure 5D).")
figure(d, "family_age", "Figure 5 - Children of Brown mothers reported White (A) and of Black mothers reported Black (B), by age; children of the couple living with "
                        "the mother (C); and the share of each five-year birth cohort reported White at the Censuses of 2000, 2010 and 2022 (D), Brazil",
       ["A, B: children of the household's couple living with their mother; design-based 95% confidence intervals. C: share of all children of the age and "
        "race who are in the pairs. D: whole population, from a population account that takes the census populations as given; the cohort born in 2000 is "
        "not shown for 2000."])
