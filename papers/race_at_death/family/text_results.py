# The Results of paper 4. Executed by build.py after text.py.
# ruff: noqa: F821
BI = MD["brown|is_white|interaction"]
KMIX = PM["black|is_black"]
WMIX = PM["black|is_white"]
PMIX = PM["brown|is_white"]
assert abs(WMIX["2022_at_2010_partners"] - WMIX["crude"]["2022"]) < 0.005, "Black mothers' children White: the partner mix now explains the rise"
assert PMIX["partner_share"]["2022"]["white"] < PMIX["partner_share"]["2010"]["white"], "Brown mothers: White partners no longer fewer"
d.add_heading("Results", level=1)
para(d, f"The rule paired {n0(MX['2010']['brown|all']['white']['records'])} children aged 0-9 of Brown mothers, "
        f"{n0(MX['2010']['white|all']['white']['records'])} of White and {n0(MX['2010']['black|all']['white']['records'])} of Black mothers in 2010, and "
        f"{n0(MX['2022']['brown|all']['white']['records'])}, {n0(MX['2022']['white|all']['white']['records'])} and {n0(MX['2022']['black|all']['white']['records'])} "
        f"in 2022. At 0-4 years, {pct(CO['2010|0-4|brown']['with_mother'], 0)} of Brown children lived with their mother in 2010 and "
        f"{pct(CO['2022|0-4|brown']['with_mother'], 0)} in 2022; at 20-24 years, {pct(CO['2010|20-24|brown']['with_mother'], 0)} and "
        f"{pct(CO['2022|20-24|brown']['with_mother'], 0)} (Figure 3C).")
d.add_heading("The child against the mother", level=2)
para(d, f"Households reported most White mothers' children as White and most Brown mothers' children as Brown, but fewer than half of Black mothers' "
        f"children as Black (Table 1, Figure 1). At 0-4 years in 2022, White mothers' children were reported White in {dci(v(2022, 'white', 'white'))}, Brown "
        f"mothers' Brown in {dci(v(2022, 'brown', 'brown'))} and White in {dci(v(2022, 'brown', 'white'))}, and Black mothers' Black in "
        f"{dci(v(2022, 'black', 'black'))}, Brown in {dci(v(2022, 'black', 'brown'))} and White in {dci(v(2022, 'black', 'white'))}. Between 2010 and 2022 "
        f"the share changed by {chg(v(2010, 'brown', 'white'), v(2022, 'brown', 'white'))} for Brown mothers' children reported White, by "
        f"{chg(v(2010, 'black', 'black'), v(2022, 'black', 'black'))} for Black mothers' children reported Black and by "
        f"{chg(v(2010, 'black', 'white'), v(2022, 'black', 'white'))} for Black mothers' children reported White.")
rows = []
for m, ml in (("white", "White"), ("brown", "Brown"), ("black", "Black"), ("indigenous", "Indigenous")):
    for y in (2010, 2022):
        rows.append([ml, str(y), n0(MX[str(y)][f"{m}|0-4"]["white"]["records"])] + [dci(v(y, m, c)) for c in ("white", "brown", "black")])
table(d, "Table 1 - Race reported for children aged 0-4 according to the race of their mother, Brazilian Censuses of 2010 and 2022",
      ["Mother's race", "Census", "Children (sample records)", "Reported White (95%CI)", "Reported Brown (95%CI)", "Reported Black (95%CI)"], rows,
      ["Children of the household's couple living with their mother. Weighted proportions; 95% confidence intervals (95%CI) by Taylor linearisation, strata "
       "the states, primary units the households. Rows do not sum to 1: the remainder is Yellow, Indigenous or not reported."])
figure(d, "family_matrix", "Figure 1 - Race reported for children aged 0-4 according to the race of their mother, Brazilian Censuses of 2010 and 2022",
       ["Weighted proportions with design-based 95% confidence intervals (most narrower than the markers)."])
d.add_heading("The partner", level=2)
para(d, f"The mother's partner changed the child's classification more than any other characteristic (Figure 2). Brown mothers' children aged 0-9 were "
        f"reported White in {dci(BWW[0])} with a White partner in 2010 and {dci(BWW[1])} in 2022, against {dci(bp(2022, 'brown', 'is_white', 'partner', 'brown'))} "
        f"with a Brown partner and {dci(bp(2022, 'brown', 'is_white', 'partner', 'no partner'))} with none identified in 2022. In the model of both censuses, "
        f"a White partner multiplied the odds of a Brown mother's child being reported White by {orf('brown|is_white', 'partner[T.white]')}, a mother with higher "
        f"education by {orf('brown|is_white', 'instruction[T.higher complete]')} against no or incomplete primary schooling, and the South by "
        f"{orf('brown|is_white', 'C(region)[T.South]')} against the Centre-West; the census term was {orf('brown|is_white', 'C(census)[T.2022]')}, and the rise "
        f"was concentrated with White partners (census by White partner interaction {BI['C(census)[T.2022]:partner[T.white]']['est']:.2f} in log-odds, standard "
        f"error {BI['C(census)[T.2022]:partner[T.white]']['se']:.2f}). Black mothers' children were reported Black in "
        f"{dci(bp(2022, 'black', 'is_black', 'partner', 'black'))} with a Black partner, {dci(bp(2022, 'black', 'is_black', 'partner', 'brown'))} with a Brown "
        f"partner and {dci(bp(2022, 'black', 'is_black', 'partner', 'white'))} with a White partner in 2022; a Brown partner multiplied the odds by "
        f"{orf('black|is_black', 'partner[T.brown]')}.")
para(d, f"The partners changed between the censuses: {pct(PMIX['partner_share']['2010']['white'], 0)} of Brown mothers of children aged 0-9 had a White "
        f"partner in 2010 and {pct(PMIX['partner_share']['2022']['white'], 0)} in 2022, and {pct(PMIX['partner_share']['2010']['no partner'], 0)} and "
        f"{pct(PMIX['partner_share']['2022']['no partner'], 0)} no partner identified; {pct(KMIX['partner_share']['2010']['black'], 0)} and "
        f"{pct(KMIX['partner_share']['2022']['black'], 0)} of Black mothers had a Black partner. At the partners of 2010, Brown mothers' children would have been "
        f"reported White in {f2(PMIX['2022_at_2010_partners'])} in 2022 (observed {f2(PMIX['crude']['2022'])}; 2010 {f2(PMIX['crude']['2010'])}): fewer White "
        "partners offset more whitening within mixed unions. Black mothers' children would have been reported Black in "
        f"{f2(KMIX['2022_at_2010_partners'])} (observed {f2(KMIX['crude']['2022'])}; 2010 {f2(KMIX['crude']['2010'])}) and White in "
        f"{f2(WMIX['2022_at_2010_partners'])} (observed {f2(WMIX['crude']['2022'])}; 2010 {f2(WMIX['crude']['2010'])}): the rise of White among Black mothers' "
        "children is not a change of partners.")
figure(d, "family_partner", "Figure 2 - Children aged 0-9 reported White, of Brown mothers (A), and reported Black, of Black mothers (B), by the race of the mother's "
                            "partner, Brazilian Censuses of 2010 and 2022",
       ["Partner: the man of the household's couple. Weighted proportions with design-based 95% confidence intervals."])
d.add_heading("Age and cohort", level=2)
para(d, f"Older children were reported Black more often: Black mothers' children were reported Black in {dci(bp(2010, 'black', 'is_black', 'age', '0-4'))} at "
        f"0-4 years and {dci(bp(2010, 'black', 'is_black', 'age', '20-24'))} at 20-24 in 2010, and {dci(bp(2022, 'black', 'is_black', 'age', '0-4'))} and "
        f"{dci(bp(2022, 'black', 'is_black', 'age', '20-24'))} in 2022 (Figure 3). The children aged 0-4 in 2010 (born 2006-2010) overlap those aged 10-14 in "
        f"2022 (born 2008-2012), who were reported Black in {dci(bp(2022, 'black', 'is_black', 'age', '10-14'))}; at 0-4 years the share did not change between "
        f"the censuses, so the gradient with age is the same children reported darker as they grow, not a cohort lighter at birth. At every age from 5 years, however, the share was lower in 2022 than in 2010 ({f2(bp(2010, 'black', 'is_black', 'age', '10-14')['est'])} against {f2(bp(2022, 'black', 'is_black', 'age', '10-14')['est'])} at 10-14 years), as expected if the women reporting themselves Black in 2022 included more whose children the household reports lighter. For Brown mothers the "
        f"gradient ran the other way: their children were reported White in {dci(bp(2022, 'brown', 'is_white', 'age', '0-4'))} at 0-4 years and "
        f"{dci(bp(2022, 'brown', 'is_white', 'age', '10-14'))} at 10-14. Across the whole population, five-year birth cohorts of 1940-2009 were reported White less "
        f"often at each later census in {CF['white_fell']} of {CF['intervals']} intervals (Figure 4).")
figure(d, "family_age", "Figure 3 - Children of Brown mothers reported White (A) and of Black mothers reported Black (B), by age, and children living with their "
                        "mother (C), Brazilian Censuses of 2010 and 2022",
       ["A, B: children of the household's couple living with their mother; design-based 95% confidence intervals. C: all children of the age and race."])
figure(d, "family_cohorts", "Figure 4 - Share of each five-year birth cohort reported White at the Censuses of 2000, 2010 and 2022, Brazil",
       ["Census counts by single year of age and race."])
d.add_heading("Who answered", level=2)
para(d, f"In 2022 the mother answered for {pct(INF['share']['mother'], 0)} of the children of the pairs, another resident for "
        f"{pct(INF['share']['other resident'], 0)} and a non-resident for {pct(INF['share']['non-resident'], 0)} (Figure 5). At equal partner, schooling, age "
        f"and region, the odds that the child was reported in the mother's race were {INF['model_same|brown']['informant[T.other resident]']['or']:.2f} (95%CI "
        f"{INF['model_same|brown']['informant[T.other resident]']['lo']:.2f}; {INF['model_same|brown']['informant[T.other resident]']['hi']:.2f}) when another "
        f"resident rather than the mother answered for a Brown mother's child, and {INF['model_same|black']['informant[T.other resident]']['or']:.2f} (95%CI "
        f"{INF['model_same|black']['informant[T.other resident]']['lo']:.2f}; {INF['model_same|black']['informant[T.other resident]']['hi']:.2f}) for a Black "
        f"mother's child; when a non-resident answered they were {INF['model_same|brown']['informant[T.non-resident]']['or']:.2f} and "
        f"{INF['model_same|black']['informant[T.non-resident]']['or']:.2f}.")
figure(d, "family_informant", "Figure 5 - Children aged 0-4 reported in their mother's race, by who answered for the child, Brazilian Census of 2022",
       ["Weighted proportions with design-based 95% confidence intervals."])
