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
figure(d, "family_matrix", "Figure 2 - Race reported for children aged 0-4 according to the race of their mother (A-C), and the change 2010-2022 at 0-9 years, "
                           "crude and at the 2010 mothers' schooling and region (D), Brazilian Censuses of 2010 and 2022",
       ["Children of the household's couple living with their mother. Weighted proportions with design-based 95% confidence intervals (most narrower than the "
        "markers). D: percentage points with 95% confidence intervals from a household bootstrap; White mothers' children as a check."])
d.add_heading("Mother, father, stepfather and siblings", level=2)
para(d, f"Among children of both members of the couple the child took the mother's class somewhat more than the father's: in the model of the nine "
        f"couple types, taking the mother's class multiplied the odds by {ex(CP['2010']['gM'])} in 2010 and {ex(CP['2022']['gM'])} in 2022, taking the father's "
        f"by {ex(CP['2010']['gF'])} and {ex(CP['2022']['gF'])}, and whatever the parents the child leaned toward White over Brown ({ex(CP['2010']['aW'])} and "
        f"{ex(CP['2022']['aW'])}) and away from Black ({ex(CP['2010']['aK'])} and {ex(CP['2022']['aK'])}). The pull toward White is why the child of a Brown mother and a "
        f"White father was reported White in {dci(BW[0])} in 2010 and {dci(BW[1])} in 2022, and the child of a White mother and a Brown father in {dci(WB[0])} "
        f"and {dci(WB[1])}; the child of a Black mother and a White father in {f2(PAR['2022|black|white']['white']['est'])} and of a White mother and a Black "
        f"father in {f2(PAR['2022|white|black']['white']['est'])} (2022). With a Brown father, a Brown mother's child was reported White in {dci(F_B[0])} and "
        f"{dci(F_B[1])} (Figure 3A). A White stepfather went with fewer White children than a White father: {f2(rel(2010, 'brown', 'is_white', STEP5, 'white')['est'])} "
        f"(2010) and {f2(rel(2022, 'brown', 'is_white', STEP5, 'white')['est'])} (2022) for the mother's own child and {f2(rel(2010, 'brown', 'is_white', STEP6, 'white')['est'])} "
        f"and {f2(rel(2022, 'brown', 'is_white', STEP6, 'white')['est'])} for the man's stepchild, against "
        f"{min(rel(y, 'brown', 'is_white', r, 'brown')['est'] for y in (2010, 2022) for r in (STEP5, STEP6)):.2f}-"
        f"{max(rel(y, 'brown', 'is_white', r, 'brown')['est'] for y in (2010, 2022) for r in (STEP5, STEP6)):.2f} with a Brown stepfather; the gap between a White "
        "and a Brown partner was two to three times larger when he was the father. The remaining stepfather gap may come from the household's reading, from the "
        "child's absent father or from which mothers form unions with White men, which these data do not separate. Black mothers' children were reported Black "
        f"in {dci(rel(2022, 'black', 'is_black', FATHER, 'black'))} with a Black father, {dci(rel(2022, 'black', 'is_black', FATHER, 'brown'))} with a Brown father "
        f"and {dci(rel(2022, 'black', 'is_black', FATHER, 'white'))} with a White one in 2022 (Figure 3B). With no partner, Brown mothers' children were reported "
        f"White in {dci(bp(2022, 'brown', 'is_white', 'partner', 'no partner'))} in 2022.")
para(d, f"Full siblings were reported in different races in {pct(FSW[0]['observed']['est'], 0)} (2010) and {pct(FSW[1]['observed']['est'], 0)} (2022) of "
        f"households of a Brown mother and a White father with two or more children aged 0-9, against {pct(FS['2010|brown|brown']['observed']['est'], 0)} and "
        f"{pct(FS['2022|brown|brown']['observed']['est'], 0)} where both parents were Brown and {pct(FS['2010|white|white']['observed']['est'], 0)} and "
        f"{pct(FS['2022|white|white']['observed']['est'], 0)} where both were White (Figure 3D). Had each child been classified independently with the proportions "
        f"of its parents' races, {pct(FSW[0]['independent'], 0)} and {pct(FSW[1]['independent'], 0)} of the mixed households would have differed: siblings shared "
        "a classification more than chance, in every couple type, but in mixed couples two in five households did not give all their children one category.")
para(d, f"In the model of both censuses (Table 1), a White partner multiplied the odds of a Brown mother's child being reported White by "
        f"{orf('brown|is_white', 'partner[T.white]')}, a mother with higher education by {orf('brown|is_white', 'instruction[T.higher complete]')} against no or "
        f"incomplete primary schooling, and the South by {orf('brown|is_white', 'C(region)[T.South]')} against the Centre-West. Between the censuses the odds "
        f"rose with White partners (census by partner interaction {IA['C(census)[T.2022]:partner[T.white]']['est']:.2f} in log-odds, standard error "
        f"{IA['C(census)[T.2022]:partner[T.white]']['se']:.2f}) and with Black partners ({IA['C(census)[T.2022]:partner[T.black]']['est']:.2f}, "
        f"{IA['C(census)[T.2022]:partner[T.black]']['se']:.2f}), not with no partner ({IA['C(census)[T.2022]:partner[T.no partner]']['est']:.2f}, "
        f"{IA['C(census)[T.2022]:partner[T.no partner]']['se']:.2f}); among fathers the share rose from {f2(F_W[0]['est'])} to {f2(F_W[1]['est'])}, so the rise is "
        f"not the growth of stepfather households. A Brown partner multiplied the odds of a Black mother's child being reported Black by {orf('black|is_black', 'partner[T.brown]')}.")
d.add_heading("Changes between the censuses", level=2)
para(d, f"Partners changed: {pct(PMIX['partner_share']['2010']['white'], 0)} of Brown mothers of children aged 0-9 had a White partner in 2010 and "
        f"{pct(PMIX['partner_share']['2022']['white'], 0)} in 2022, and {pct(PMIX['partner_share']['2010']['no partner'], 0)} and "
        f"{pct(PMIX['partner_share']['2022']['no partner'], 0)} no partner; {pct(KMIX['partner_share']['2010']['black'], 0)} and "
        f"{pct(KMIX['partner_share']['2022']['black'], 0)} of Black mothers had a Black partner. At the partners of 2010, Brown mothers' children would have been "
        f"reported White in {f2(PMIX['2022_at_2010_partners'])} in 2022 (observed {f2(PMIX['crude']['2022'])}; 2010 {f2(PMIX['crude']['2010'])}). Schooling rose "
        "for mothers of every race: no or incomplete primary schooling fell from "
        f"{pct(V3['instruction_by_mother']['2010|white']['none or primary incomplete'], 0)} to {pct(V3['instruction_by_mother']['2022|white']['none or primary incomplete'], 0)} "
        f"among White mothers, {pct(V3['instruction_by_mother']['2010|brown']['none or primary incomplete'], 0)} to "
        f"{pct(V3['instruction_by_mother']['2022|brown']['none or primary incomplete'], 0)} among Brown and {pct(V3['instruction_by_mother']['2010|black']['none or primary incomplete'], 0)} "
        f"to {pct(V3['instruction_by_mother']['2022|black']['none or primary incomplete'], 0)} among Black mothers. In percentage points, the crude change of children "
        f"aged 0-9 reported White was {pp(DB['brown|is_white']['change'], DB['brown|is_white']['change_se'])} for Brown mothers and "
        f"{pp(DB['white|is_white']['change'], DB['white|is_white']['change_se'])} for White mothers; the change of Black mothers' children reported Black was "
        f"{pp(DB['black|is_black']['change'], DB['black|is_black']['change_se'])} and reported White {pp(DB['black|is_white']['change'], DB['black|is_white']['change_se'])}. "
        "At the 2010 mothers' instruction and region the changes were "
        f"{pp(DB['brown|is_white']['std_change'], DB['brown|is_white']['std_change_se'])}, {pp(DB['white|is_white']['std_change'], DB['white|is_white']['std_change_se'])}, "
        f"{pp(DB['black|is_black']['std_change'], DB['black|is_black']['std_change_se'])} and {pp(DB['black|is_white']['std_change'], DB['black|is_white']['std_change_se'])} "
        "(Figure 2D). Within equal schooling and region, children of White and Brown mothers were reported White less often in 2022; the standardisation "
        "moved every group, White mothers' children included, by more than the crude change, because schooling rose for all mothers and more schooled mothers "
        "report lighter children. It does not tell whether the women declaring each category changed.")
GROUPS = [("Census", [("C(census)[T.2022]", "2022 (ref. 2010)")]),
          ("Mother's partner (ref. of the mother's race)", [("partner[T.white]", "White"), ("partner[T.brown]", "Brown"), ("partner[T.black]", "Black"),
                                                            ("partner[T.other]", "Other"), ("partner[T.no partner]", "No partner")]),
          ("Mother's instruction (ref. none or incomplete primary)", [("instruction[T.primary complete]", "Primary complete"),
                                                                      ("instruction[T.secondary complete]", "Secondary complete"),
                                                                      ("instruction[T.higher complete]", "Higher complete")]),
          ("Child (ref. aged 0-4, boy)", [("C(age)[T.5-9]", "Aged 5-9"), ("C(sex)[T.2]", "Girl")]),
          ("Mother's age (ref. 25-34)", [("C(mother_age)[T.under 25]", "Under 25"), ("C(mother_age)[T.35-44]", "35-44"), ("C(mother_age)[T.45 or more]", "45 or more")]),
          ("Region (ref. Centre-West)", [("C(region)[T.North]", "North"), ("C(region)[T.Northeast]", "Northeast"), ("C(region)[T.Southeast]", "Southeast"),
                                         ("C(region)[T.South]", "South")])]


def _or(key, term):
    v_ = MD[key].get(term)
    return f"{v_['or']:.2f} ({v_['lo']:.2f}; {v_['hi']:.2f})" if isinstance(v_, dict) else "-"


rows = []
for grp, terms in GROUPS:
    rows.append([grp, "", ""])
    rows += [[f"   {lab}", _or("brown|is_white", t), _or("black|is_black", t)] for t, lab in terms]
table(d, "Table 1 - Odds ratios of the race reported for children aged 0-9, logistic models of the Censuses of 2010 and 2022 together, Brazil",
      ["Variable", "Brown mother: child reported White, OR (95%CI)", "Black mother: child reported Black, OR (95%CI)"], rows,
      ["Weighted logistic regression; standard errors clustered by household. -: not in the model (the partner of the mother's own race is the reference). "
       "Census by partner interactions in the text."])
figure(d, "family_partner", "Figure 3 - Children aged 0-9 reported White, of Brown mothers (A), and reported Black, of Black mothers (B), by the race of the mother's "
                            "partner and whether he is the father; children of both reported White by the mother's and the father's race (C); and households whose "
                            "full siblings aged 0-9 are reported in different races (D), Brazilian Censuses of 2010 and 2022",
       ["Partner: the man of the household's couple; father, child of both; stepfather, child of the responsible woman only or stepchild of the responsible "
        "man. Weighted proportions with design-based 95% confidence intervals (grey 2010, orange 2022). D: households with two or more children aged 0-9, all "
        "children of both; the vertical mark is the share expected if each child were classified independently with the proportions of its parents' races."])
d.add_heading("Who answered", level=2)
para(d, f"In 2022 the mother answered for {pct(IN2['share_0_14']['mother'], 0)} of the children aged 0-14 of the pairs, the partner for "
        f"{pct(IN2['share_0_14']['partner'], 0)}, another resident for {pct(IN2['share_0_14']['other resident'], 0)} and a non-resident for "
        f"{pct(IN2['share_0_14']['non-resident'], 0)}; the mother answered for herself in {pct(IN2['mother_informant']['self'], 0)} of the pairs and the partner "
        f"for her in {pct(IN2['mother_informant']['partner'], 0)}. The child of a Brown mother and a White partner was reported White in {dci(MB_['white'])} when "
        f"she answered for both, {dci(PS['white'])} when he answered for the child and she for herself, and {dci(PB['white'])} when he answered for both "
        f"(Figure 4); for a Black mother and a White partner, {f2(IC['black|white|child by mother|mother by mother']['white']['est'])}, "
        f"{f2(IC['black|white|child by partner|mother by mother']['white']['est'])} and {f2(IC['black|white|child by partner|mother by partner']['white']['est'])}. "
        "When a White mother had a Brown or Black partner, who answered made no difference (White "
        f"{f2(IC['white|brown|child by mother|mother by mother']['white']['est'])} and {f2(IC['white|brown|child by partner|mother by partner']['white']['est'])} "
        f"with a Brown partner; {f2(IC['white|black|child by mother|mother by mother']['white']['est'])} and "
        f"{f2(IC['white|black|child by partner|mother by partner']['white']['est'])} with a Black one). The difference sat where one respondent, the partner, "
        "classified both the mother and the child, and where the mother was not White; who answers is not random, and a partner who answers for the whole "
        "household may differ in other ways.")
figure(d, "family_informant", "Figure 4 - Children aged 0-9 reported in a race according to who answered for the child and for the mother, by the mother's and the "
                              "partner's race, Brazilian Census of 2022",
       ["Weighted proportions with design-based 95% confidence intervals."])
d.add_heading("Age and cohort", level=2)
para(d, f"Older children were reported Black more often: Black mothers' children were reported Black in {dci(bp(2010, 'black', 'is_black', 'age', '0-4'))} at "
        f"0-4 years and {dci(bp(2010, 'black', 'is_black', 'age', '20-24'))} at 20-24 in 2010, and {dci(bp(2022, 'black', 'is_black', 'age', '0-4'))} and "
        f"{dci(bp(2022, 'black', 'is_black', 'age', '20-24'))} in 2022 (Figure 5B). The children aged 0-4 in 2010 (born 2006-2010) overlap for about three of "
        f"five birth years those aged 10-14 in 2022 (born 2008-2012), who were reported Black in {dci(bp(2022, 'black', 'is_black', 'age', '10-14'))}; that rise "
        f"({bp(2022, 'black', 'is_black', 'age', '10-14')['est'] - bp(2010, 'black', 'is_black', 'age', '0-4')['est']:+.2f}) was about half the 2010 cross-section's "
        f"gradient between 0-4 and 10-14 ({bp(2010, 'black', 'is_black', 'age', '10-14')['est'] - bp(2010, 'black', 'is_black', 'age', '0-4')['est']:+.2f}). For Brown "
        f"mothers the gradient ran the other way: their children were reported White in {dci(bp(2022, 'brown', 'is_white', 'age', '0-4'))} at 0-4 years and "
        f"{dci(bp(2022, 'brown', 'is_white', 'age', '10-14'))} at 10-14 (Figure 5A). In the whole population, free of the pairing, the cohort born in 2005-2009 "
        f"was reported White in {f2(C05[2010])} in 2010 and {f2(C05[2022])} in 2022, and the cohort born in 1995-1999 in {f2(C95[2000])} in 2000 and "
        f"{f2(C95[2010])} in 2010: the two largest falls of any cohort, both between a census at ages 0-4 and one at 10-17, while households still report "
        f"for them. Five-year birth cohorts of {CF['first']}-{CF['last'] + 4} were reported White less often at each later census in "
        f"{CF['white_fell']} of {CF['intervals']} intervals (Figure 5D). Different mothers, partners and informants report each time, so age and cohort cannot "
        "be separated.")
figure(d, "family_age", "Figure 5 - Children of Brown mothers reported White (A) and of Black mothers reported Black (B), by age; children of the couple living with "
                        "the mother (C); and the share of each five-year birth cohort reported White at the Censuses of 2000, 2010 and 2022 (D), Brazil",
       ["A, B: children of the household's couple living with their mother; design-based 95% confidence intervals. C: share of all children of the age and "
        "race who are in the pairs. D: whole population, from a population account that takes the census populations as given; the cohort born in 2000 is "
        "not shown for 2000."])

d.add_heading("Place", level=2)
PPC, WWC, KKC = CG["PP_white"], CG["WW_brown"], CG["KK_black"]
para(d, f"The family's classification of fixed couple types changed little with the municipality's composition (Figure 6A). The child aged 0-9 of two Brown "
        f"parents was reported White in {dci(PPC['bins'][0])} of households in municipalities with under 10% of White births and {dci(PPC['bins'][-1])} where "
        f"90% or more were, most of the rise below 30% (logit slope {f2(PPC['raw']['slope'])}, standard error {f2(PPC['raw']['se'])}); the child of two White "
        f"parents was reported Brown in {dci(WWC['bins'][0])} and {dci(WWC['bins'][-1])}, and the child of two Black parents Black in {dci(KKC['bins'][0])} and "
        f"{dci(KKC['bins'][-1])}. The death certificate of a Brown mother's infant moves far more on the same axis (logit slope "
        f"{f2(CT['certificate']['slope_bins'])} against {f2(PPC['slope_bins'])}; companion paper). By state, the child of two Brown parents was reported White in "
        f"{min(STW.values()):.2f} to {max(STW.values()):.2f} in 2010, and the states kept their order in 2022 (Figure 6B); nationally, "
        f"{f2(CS['2010']['BR']['PP_white']['est'])} and {f2(CS['2022']['BR']['PP_white']['est'])}.")
figure(d, "family_place", "Figure 6 - Children of fixed couple types by the municipality's composition in 2010 (A) and by state in 2010 and 2022 (B), Brazil",
       ["A: children aged 0-9 of the household's couple (2010 Census sample) by tenth of the municipality's share of White births (SINASC 2012-2023); bars, "
        "95% confidence intervals clustered by municipality. B: the same shares by state in the 2010 and 2022 samples; the 2022 public file carries no "
        "municipality."])
