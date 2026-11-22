# The Results of the manuscript. Executed by build.py after text.py, whose names it uses.
# ruff: noqa: F821
d.add_heading("Results", level=1)
S4 = []  # detailed results paragraphs, moved whole to Supplementary Text S4

# ----------------------------------------------------------------- the records
FL, LS = I["flow"], I["linked_share"]
para(d, f"The one-to-one linkage found the birth record of {pct(I['linked'] / I['certificates'])} of infant deaths; the linked share was "
        f"{pct(LS['by_certified']['Branca'])}, {pct(LS['by_certified']['Parda'])} and {pct(LS['by_certified']['Preta'])} for deaths certified White, Brown and Black, "
        f"{pct(LS['by_certified']['Indigena'])} for Indigenous, and was lower after the first month ({pct(LS['by_age']['28-364 d'])}) and in the North "
        f"({pct(LS['by_region']['North'])}) than in the South ({pct(LS['by_region']['South'])}) (Supplementary Table S2). In municipalities with fewer "
        f"than 25,600 births per year, the candidate estimator reproduced the linkage's proportions; the deceased was among its candidates for "
        f"{pct(C19['matrix']['found'])} of deaths at 1-9 years, against {pct(v_all['candidates']['found'])} of infant deaths (Figure 1, Supplementary Figure S1, Supplementary Tables S4 and S12; Supplementary Text S4).")
S4.append(f"The one-to-one linkage found the birth record of {pct(I['linked'] / I['certificates'])} of infant deaths; the linked share was "
        f"{pct(LS['by_certified']['Branca'])}, {pct(LS['by_certified']['Parda'])} and {pct(LS['by_certified']['Preta'])} for deaths certified White, Brown and Black, "
        f"{pct(LS['by_certified']['Indigena'])} for Indigenous, and was lower after the first month ({pct(LS['by_age']['28-364 d'])}) and in the North "
        f"({pct(LS['by_region']['North'])}) than in the South ({pct(LS['by_region']['South'])}) (Supplementary Table S2). Of the {n0(I['certificates'])} infant certificates, "
        f"{FL['birth_after_death']} had a birth date after the death; {n0(FL['no_sex'])} had no sex and {n0(FL['no_municipality'])} no municipality of residence and could not enter the candidate estimator. In municipalities with fewer "
        f"than 25,600 births per year, the candidate estimator reproduced the linkage's proportions; over all sizes, {f2(cell(v_all['candidates'], 'Branca', 'Branca')['est'])} "
        f"against {f2(cell(v_all['linkage'], 'Branca', 'Branca')['est'])} for White, {f2(cell(v_all['candidates'], 'Parda', 'Parda')['est'])} against "
        f"{f2(cell(v_all['linkage'], 'Parda', 'Parda')['est'])} for Brown and {f2(cell(v_all['candidates'], 'Preta', 'Preta')['est'])} against "
        f"{f2(cell(v_all['linkage'], 'Preta', 'Preta')['est'])} for Black mothers; in the largest municipalities its standard error for White reached "
        f"{f2(cell(v_top['candidates'], 'Branca', 'Branca')['se'])} (Supplementary Figure S1, Supplementary Table S4). The deceased was among the candidates for "
        f"{pct(C19['matrix']['found'])} of deaths at 1-9 years, against "
        f"{pct(v_all['candidates']['found'])} of infant deaths; the remainder had moved municipality or had no birth record. Figure 1 and Supplementary Table S12 give the populations.")
SUPP_TABLES = []


def stable(*a):
    SUPP_TABLES.append(a)


stable("Supplementary Table S12 - Sources and study populations",
      ["Population", "Source and period", "Classification compared with the certificate", "Records"],
      [["Infant deaths", "SIM 2013-2023 linked one-to-one to SINASC", "Mother's declaration", f"{n0(I['certificates'])} deaths; {n0(I['linked_with_race'])} linked with the mother's race"],
       ["Deaths at 1-9 years", "SIM 2013-2024, born 2012-2023; candidate estimator", "Mother's declaration", f"{n0(C19['matrix']['deaths'])} deaths ({n0(C14['matrix']['deaths'])} at 1-4, {n0(C59['matrix']['deaths'])} at 5-9)"],
       ["Children under 25 living with their mother", "2010 Census sample", "Family's classification of other children, by the mother's race", f"{n0(CEN['pairs_records'])} pair records"],
       ["Municipalities", "IBGE mesh 2022; SIDRA; CNES; SIM", "Context of the place", f"{n0(G['municipalities'])} municipalities, {n0(G['edges'])} pairs of neighbours"],
      ],
      ["SIM: Mortality Information System. SINASC: Live Birth Information System. IBGE: Brazilian Institute of Geography and Statistics. CNES: National Register of Health "
       "Establishments."])
figure(d, "flow_infants", "Figure 1 - Design: the two records of the same infant, the census reference of other children and the place, with the number of records at each "
                          "step, Brazil",
       ["SIM: Mortality Information System. SINASC: Live Birth Information System. The family's classification is a population reference applied by the mother's race, "
        "the age and the place; it is not a label of the deceased. Deaths at 1-9 years were related to births by the candidate estimator (Methods)."])

# ----------------------------------------------------------------- three classifications
d.add_heading("Three classifications", level=2)
para(d, f"Families did not classify children as their mothers (Figure 2, Supplementary Table S13). Before one year, the household reported as White {f2(fam(F0, 'Branca', 'Branca'))} of the children "
        f"of White mothers, as Brown {f2(fam(F0, 'Parda', 'Parda'))} of the children of Brown mothers and as Black {f2(fam(F0, 'Preta', 'Preta'))} of the children of Black "
        f"mothers; {f2(fam(F0, 'Parda', 'Branca'))} of the children of Brown mothers were reported White. The certificate agreed with the family on the exchange between Brown and White, recording White for {cbci('Parda>Branca')} of the infants of Brown mothers, and "
        f"departed from it elsewhere: it recorded Brown for {cbci('Parda>Parda')} of those of Brown mothers and "
        f"Black for {cbci('Preta>Preta')} of those of Black mothers, of whom {cbci('Preta>Parda')} were certified Brown (Supplementary Text S4).")
S4.append(f"Families did not classify children as their mothers (Figure 2, Supplementary Table S13). Before one year, the household reported as White {f2(fam(F0, 'Branca', 'Branca'))} of the children "
        f"of White mothers, as Brown {f2(fam(F0, 'Parda', 'Parda'))} of the children of Brown mothers and as Black {f2(fam(F0, 'Preta', 'Preta'))} of the children of Black "
        f"mothers; {f2(fam(F0, 'Parda', 'Branca'))} of the children of Brown mothers were reported White and {f2(fam(F0, 'Preta', 'Parda'))} of the children of Black mothers "
        f"Brown. The certificate agreed with the family on the exchange between Brown and White, recording White for {cbci('Parda>Branca')} of the infants of Brown mothers, and "
        f"departed from it elsewhere: it recorded White for {cbci('Branca>Branca')} of the infants of White mothers, Brown for {cbci('Parda>Parda')} of those of Brown mothers and "
        f"Black for {cbci('Preta>Preta')} of those of Black mothers, of whom {cbci('Preta>Parda')} were certified Brown. At 1-4 years the certificate recorded the mother's race for "
        f"{cc(cell(W14, 'Branca', 'Branca'))}, {cc(cell(W14, 'Parda', 'Parda'))} and {cc(cell(W14, 'Preta', 'Preta'))} of the children of White, Brown and Black mothers, and the "
        f"family for {f2(fam(F14, 'Branca', 'Branca'))}, {f2(fam(F14, 'Parda', 'Parda'))} and {f2(fam(F14, 'Preta', 'Preta'))}. For children of Indigenous mothers the certificate "
        f"recorded Indigenous in {ci(cell(IL, 'Indigena', 'Indigena'))} of infant deaths, against {f2(fam(F0, 'Indigena', 'Indigena'))} in the family's classification. The "
        f"certificate left the race blank or recorded another category for {pct(I['blank_by_mother']['Parda'])} of the infants of Brown mothers, {pct(I['blank_by_mother']['Preta'])} "
        f"of Black and {pct(I['blank_by_mother']['Branca'])} of White mothers.")
rows = []
for m in ORDER:
    for label, getter in (("Family, census, under 1 year", lambda c, m=m: f2(fam(F0, m, c)) if c in F0[m] else "0.00"),
                          ("Certificate, under 1 year", lambda c, m=m: ci(cell(IL, m, c))),
                          ("Family, census, 1-4 years", lambda c, m=m: f2(fam(F14, m, c)) if c in F14[m] else "0.00"),
                          ("Certificate, 1-4 years", lambda c, m=m: cc(cell(W14, m, c))), ("Certificate, 5-9 years", lambda c, m=m: cc(cell(W59, m, c)))):
        rows.append([EN[m], label] + [getter(c) for c in ORDER])
stable("Supplementary Table S13 - Proportion of children assigned to each race according to the mother's race, in the family's classification (2010 Census) and on the death certificate "
         "(2013-2024), Brazil", ["Mother's race", "Classification of the child", "White (95%CI)", "Brown (95%CI)", "Black (95%CI)", "Indigenous (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Census proportions are weighted sample estimates (standard errors below 0.005 under simple random sampling, not shown). Certificate, "
       f"under 1 year: one-to-one linkage, binomial intervals (intervals from the bootstrap over municipalities are {CBRANGE} times wider; text). Certificate at 1-9 years: "
       "candidate estimator, municipalities with fewer than 25,600 live births per year; estimates are differences of counts and can leave the interval 0 to 1. Not estimable: "
       "standard error above 0.15, or outside 0 to 1 by more than two standard errors. Rows do not sum to 1: the remainder is another category or no race recorded."])
figure(d, "classifications", "Figure 2 - Proportion of children assigned to each race according to the mother's race: family's classification, death certificate and their difference, "
                  "under one year (A-C) and at 1-4 years (D-F), Brazil",
       ["Rows: mother's race; columns: race assigned to the child. A, D: 2010 Census sample. B: one-to-one linkage, deaths of 2013-2023. E: candidate estimator, deaths of "
        "2013-2024, municipalities with fewer than 25,600 live births per year."])

# ----------------------------------------------------------------- the municipality
d.add_heading("The municipality", level=2)
RES, FV, DI, LI = SP["resolution"], SP["field_var"], SP["distribution"], SP["lisa"]
cross = next(b["white_share"] for b, f in zip(GI, GC0, strict=True) if b["matrix"]["rows"]["Parda"]["Branca"]["est"] > f["matrix"]["Parda"].get("Branca", {"est": 0})["est"])
assert FV["PW"]["M0"] > 4 * FV["famPW"]["M0"], "the certificate no longer varies far more between municipalities than the family"
assert MO["PW"]["rate"]["I"] > 0.5 and BY["PW"]["M0"]["phi"] > 0.9
assert DI["diff_by_region"]["South"] > 0.1 > 0 > DI["diff_by_region"]["Northeast"], "the regional sign of certificate minus family changed"
S4.append(f"The linked infant deaths gave a median of {RES['PW']['median_trials']:.0f} deaths of Brown mothers' children per municipality ({pct(RES['PW']['share_ge20'])} of "
        f"municipalities had 20 or more) and of {RES['KK']['median_trials']:.0f} of Black mothers' children ({pct(RES['KK']['share_zero'])} of municipalities had none). The "
        f"municipal resolution is therefore supported for the children of Brown mothers, with credible intervals of median width {f2(RES['PW']['median_ci_width'])}; other "
        "cells, the Black category above all, rest on few deaths per municipality and are shown as smoothed fields (Supplementary Figures S2, S3; the spatial models' "
        "parameters in Supplementary Table S5).")
para(d, f"The proportion of Brown mothers' infants certified White ranged, across the municipalities in which 90% of births occur, from {f2(DI['PW']['p5'])} to "
        f"{f2(DI['PW']['p95'])} (Figure 3A); the proportion of Brown mothers' children aged 0-9 whom families reported White, from {f2(DI['famPW']['p5'])} to "
        f"{f2(DI['famPW']['p95'])} (Figure 3B). On the logit scale the smoothed municipal values of the certificate varied {FV['PW']['M0'] / FV['famPW']['M0']:.1f} times as much "
        f"as the family's. The variation was spatially structured (BYM2 mixing parameter {f2(BY['PW']['M0']['phi'])}, Moran's I "
        f"{f2(MO['PW']['rate']['I'])}, {n0(MO['PW']['rate']['units'])} municipalities; Figure 3D). The certificate classed Brown mothers' infants White "
        f"more often than families class Brown mothers' children where White births were the majority and less often where they were few (Figure 3C): "
        f"weighted by births, it exceeded the family by {f2(DI['diff_by_region']['South'])} in the "
        f"South and fell short of it by {f2(-DI['diff_by_region']['Northeast'])} in the Northeast. Municipal resolution, local clusters and the other cells are in Supplementary Text S4.")
S4.append(f"The proportion of Brown mothers' infants certified White ranged, across the municipalities in which 90% of births occur, from {f2(DI['PW']['p5'])} to "
        f"{f2(DI['PW']['p95'])} (Figure 3A); the proportion of Brown mothers' children aged 0-9 whom families reported White ranged from {f2(DI['famPW']['p5'])} to "
        f"{f2(DI['famPW']['p95'])} (Figure 3B). On the logit scale the smoothed municipal values of the certificate varied {FV['PW']['M0'] / FV['famPW']['M0']:.1f} times as much "
        f"as the family's (variances {f2(FV['PW']['M0'])} and {f2(FV['famPW']['M0'])}; the family's values rest on more children per municipality and are less shrunk, so "
        f"the ratio is not inflated by smoothing). The variation was spatially structured: the BYM2 mixing parameter was estimated at {f2(BY['PW']['M0']['phi'])}, Moran's I "
        f"of the standardised proportions was {f2(MO['PW']['rate']['I'])} (p ≤ 0.001 by 999 permutations, {n0(MO['PW']['rate']['units'])} municipalities), and local "
        f"statistics at p < 0.05, without correction for multiplicity, marked {n0(LI['PW']['high-high'])} municipalities of high values among high values in the South, "
        f"Southeast and Centre-West and {n0(LI['PW']['low-low'])} of low values in the North and Northeast (Figure 3D); with the false discovery rate held at "
        f"5%, {n0(LI['PW']['fdr']['high-high'])} and {n0(LI['PW']['fdr']['low-low'])} remained, and none for the Black category. The certificate classed Brown mothers' infants White "
        f"more often than families class Brown mothers' children where White births were the majority and less often where they were few (Figure 3C, Figure 4A); "
        f"weighted by births, the certificate exceeded the family by {f2(DI['diff_by_region']['South'])} in the "
        f"South and fell short of it by {f2(-DI['diff_by_region']['Northeast'])} in the Northeast. Certified race differed from the mother's in proportions that were also "
        f"spatially clustered (Moran's I {f2(MO['disagree']['rate']['I'])}; Supplementary Figure S4), as was the use of the Black category for Black mothers' infants "
        f"(Moran's I {f2(MO['KK']['rate']['I'])}; Supplementary Figure S3).")
figure(d, "map_municipal", "Figure 3 - Infant deaths of Brown mothers' children certified White (A), Brown mothers' children aged 0-9 reported White by the family (B), their difference "
                  "(C) and local clusters of the certified proportion (D), by municipality, Brazil",
       ["A: linked infant deaths 2013-2023. B: 2010 Census sample. A-C: posterior means of a binomial BYM2 model on the contiguity of the 5,570 municipalities. D: local Moran "
        "statistic of the empirical-Bayes proportion, 999 permutations, municipalities with five or more linked deaths. State borders in black."])

# ----------------------------------------------------------------- composition, state and context
d.add_heading("Composition, state and context", level=2)
mP, mK = MO["PW"], MO["KK"]
bt = BD_["PW"]
assert mP["deviance_explained"]["composition"] > mP["deviance_explained"]["context"] + 0.2 and mP["deviance_explained"]["composition_state_context"] - mP["deviance_explained"]["composition_state"] < 0.05, "context now rivals composition"
assert mP["F_composition_state_vs_composition"]["p"] < 0.001 and mP["F_composition_state_vs_state"]["p"] < 0.001, "state or composition no longer adds"
assert 0 < bt["slope_state_effect"] - 1.96 * bt["slope_se"] and bt["slope_state_effect"] + 1.96 * bt["slope_se"] < 1, "the border slope is no longer between 0 and 1"
assert abs(mP["deviance_explained"]["census_composition"] - mP["deviance_explained"]["composition"]) < 0.05, "the census composition no longer reproduces the birth-record composition"
bd_ = BD_["disagree"]
GG = SP["gdp_given_composition"]
CP = SP["comp_place"]
para(d, f"For Brown mothers' infants certified White, the municipality's composition alone explained {pct(mP['deviance_explained']['composition'], 0)} of the deviance "
        f"between municipalities, the state alone {pct(mP['deviance_explained']['state'], 0)}, and the socioeconomic, service and recording context alone "
        f"{pct(mP['deviance_explained']['context'], 0)}; composition and state together explained {pct(mP['deviance_explained']['composition_state'], 0)}, and the context "
        f"added {pct(mP['deviance_explained']['composition_state_context'] - mP['deviance_explained']['composition_state'], 0)} (Figure 4B, Supplementary Table S14). Composition and state "
        f"each added to the other, and Moran's I of the residuals fell from {f2(mP['none']['I'])} to {f2(mP['composition_state']['I'])} with both (Supplementary Text S4).")
S4.append(f"For Brown mothers' infants certified White, the municipality's composition alone explained {pct(mP['deviance_explained']['composition'], 0)} of the deviance "
        f"between municipalities, the state alone {pct(mP['deviance_explained']['state'], 0)}, and the socioeconomic, service and recording context alone "
        f"{pct(mP['deviance_explained']['context'], 0)}; composition and state together explained {pct(mP['deviance_explained']['composition_state'], 0)}, and the context "
        f"added {pct(mP['deviance_explained']['composition_state_context'] - mP['deviance_explained']['composition_state'], 0)} (Figure 4B, Supplementary Table S14). Composition (3 degrees "
        "of freedom) and state (26) each explained about three quarters, and each added to the other "
        f"(F = {mP['F_composition_state_vs_state']['F']:.0f} for composition given state; F = {mP['F_composition_state_vs_composition']['F']:.1f} for state given "
        "composition; these tests assume independent residuals, which residual clustering contradicts, so their p-values are too small). Part of the deviance is binomial "
        f"noise (dispersion {mP['none']['dispersion']:.1f} without any term), so the explainable share is below 100%. Moran's I of the residuals fell from "
        f"{f2(mP['none']['I'])} to {f2(mP['composition']['I'])} with composition and to {f2(mP['composition_state']['I'])} with composition and state; in the spatial model, "
        f"the variance of the municipal field fell from {f2(FV['PW']['M0'])} to {f2(FV['PW']['M1_composition'])} and {f2(FV['PW']['M3_composition_state'])}. Because the "
        "composition is measured from the mothers' declarations on the same birth records that give the reference, it was replaced by the share of White residents in the "
        f"2010 Census (correlation {f2(mP['corr_birth_census_composition'])}): it explained {pct(mP['deviance_explained']['census_composition'], 0)} alone and "
        f"{pct(mP['deviance_explained']['census_composition_state'], 0)} with the state. For Black mothers' infants certified Black, composition explained less "
        f"({pct(mK['deviance_explained']['composition'], 0)}) than the state ({pct(mK['deviance_explained']['state'], 0)}), and residual clustering remained "
        f"({f2(mK['composition_state_context']['I'])} with every term).")
para(d, f"At state borders, the difference between two neighbouring municipalities in different states was {f2(bt['slope_state_effect'])} (95%CI "
        f"{f2(bt['slope_state_effect'] - 1.96 * bt['slope_se'])}; {f2(bt['slope_state_effect'] + 1.96 * bt['slope_se'])}) times the difference between their states' effects "
        f"estimated from municipalities touching no other state ({n0(bt['pairs'])} pairs; Figure 4C); for the "
        f"certified race differing from the mother's it was {f2(bd_['slope_state_effect'])} (95%CI {f2(bd_['slope_state_effect'] - 1.96 * bd_['slope_se'])}; "
        f"{f2(bd_['slope_state_effect'] + 1.96 * bd_['slope_se'])}). "
        "The certified race changes in a step at state borders, as a state practice would make it, and the step is smaller than the difference between the states' interiors. "
        "The split by place within the state and by municipal wealth is in Supplementary Text S4.")
S4.append(f"At state borders, the difference between two neighbouring municipalities in different states was {f2(bt['slope_state_effect'])} (95%CI "
        f"{f2(bt['slope_state_effect'] - 1.96 * bt['slope_se'])}; {f2(bt['slope_state_effect'] + 1.96 * bt['slope_se'])}, errors clustered by the {bt['state_pairs']} pairs of "
        f"states) times the difference between their states' effects estimated from municipalities touching no other state ({n0(bt['pairs'])} pairs; Figure 4C); for the "
        f"certified race differing from the mother's it was {f2(bd_['slope_state_effect'])} (95%CI {f2(bd_['slope_state_effect'] - 1.96 * bd_['slope_se'])}; "
        f"{f2(bd_['slope_state_effect'] + 1.96 * bd_['slope_se'])}), and for the Black category the state effects estimated away from borders were too unstable for the test. "
        "The certified race changes in a step at state borders, as a state practice would make it, and the step is smaller than the difference between the states' interiors; "
        f"the estimated state effects carry error, which attenuates the slope. The step is small beside the differences between neighbours: the mean squared difference of "
        f"their logits was {f2(bt['msd_cross'])} across state borders and {f2(bt['msd_within'])} within states. By place within the state, Brown mothers' "
        f"infants were certified White in {f2(SP['by_place']['capital']['rows']['Parda']['Branca']['est'])} of deaths in state capitals, "
        f"{f2(SP['by_place']['metropolitan, not capital']['rows']['Parda']['Branca']['est'])} in the rest of the metropolitan regions and "
        f"{f2(SP['by_place']['interior']['rows']['Parda']['Branca']['est'])} in the interior (Supplementary Figure S7A); where 30-59% of births were White, the proportions were "
        f"{f2(CP['30-59%|capital']['rows']['Parda']['Branca']['est'])}, {f2(CP['30-59%|metropolitan, not capital']['rows']['Parda']['Branca']['est'])} and "
        f"{f2(CP['30-59%|interior']['rows']['Parda']['Branca']['est'])}. At equal composition, municipal wealth changed the proportion less than composition did: where under 30% "
        f"of births were White, it was {f2(SP['comp_gdp']['<30%|low']['rows']['Parda']['Branca']['est'])} in the poorest third of municipalities by GDP per capita and "
        f"{f2(SP['comp_gdp']['<30%|high']['rows']['Parda']['Branca']['est'])} in the richest; where 60% or more were White, "
        f"{f2(SP['comp_gdp']['>=60%|low']['rows']['Parda']['Branca']['est'])} and {f2(SP['comp_gdp']['>=60%|high']['rows']['Parda']['Branca']['est'])} (Supplementary Figure S7B). Intervals "
        "are not given for these proportions: binomial intervals understate the clustering of deaths by place. With composition entered as a spline instead of classes, a "
        f"doubling of GDP per capita multiplied the odds by {f2(GG['composition']['or_doubling'])} (95%CI {f2(GG['composition']['or_doubling_lo'])}; "
        f"{f2(GG['composition']['or_doubling_hi'])}), and with the state as well by {f2(GG['composition_state']['or_doubling'])} (95%CI "
        f"{f2(GG['composition_state']['or_doubling_lo'])}; {f2(GG['composition_state']['or_doubling_hi'])}).")
if ML:
    sq = {o: ML[o]["sequence"] for o in ML}
    bw, bk = sq["brown_white"], sq.get("black_black")
    assert bw["composition"]["pcv"] > bw["socioeconomic"]["pcv"] > 0 and bw["composition"]["pcv"] > bw["services"]["pcv"], "composition no longer explains most"
    assert bw["composition_socioeconomic_services"]["pcv"] - bw["composition"]["pcv"] < 0.1, "the context now adds much to composition"
    assert abs(bw["individual_no_region"]["pcv"]) < 0.05, "the deaths' own characteristics now explain municipal variance"
    para(d, f"In the multilevel models of the {n0(ML['brown_white']['n'])} linked infant deaths of Brown mothers' children, the variance between municipalities of the "
            f"log-odds of being certified White was {f2(bw['null']['var_mun'])} (median odds ratio {f2(bw['null']['mor'])}). Composition alone explained "
            f"{pct(bw['composition']['pcv'], 0)} of it, the socioeconomic context and place alone {pct(bw['socioeconomic']['pcv'], 0)}, the services and recording alone "
            f"{pct(bw['services']['pcv'], 0)}, and composition with both {pct(bw['composition_socioeconomic_services']['pcv'], 0)}. The variables of the death and the birth explained "
            f"{pct(bw['individual_no_region']['pcv'], 0)} without the macro-region: the differences between municipalities are not who dies there or of what. With everything, "
            f"{pct(bw['full']['pcv'], 0)} was explained and the median odds ratio fell to {f2(bw['full']['mor'])} (Figure 4D, Supplementary Tables S6 and S14; Supplementary Text S4).")
    S4.append(f"In the multilevel models of the {n0(ML['brown_white']['n'])} linked infant deaths of Brown mothers' children, the variance between municipalities of the "
            f"log-odds of being certified White was {f2(bw['null']['var_mun'])} (median odds ratio {f2(bw['null']['mor'])}). Composition alone explained "
            f"{pct(bw['composition']['pcv'], 0)} of it; the socioeconomic context and place alone {pct(bw['socioeconomic']['pcv'], 0)}; the services and recording alone "
            f"{pct(bw['services']['pcv'], 0)}; the two together {pct(bw['socioeconomic_services']['pcv'], 0)}; and composition with both {pct(bw['composition_socioeconomic_services']['pcv'], 0)}: most of what wealth and services explain "
            f"alone, they share with composition. The variables of the death and the birth with the macro-region and the year, without any municipal variable, explained "
            f"{pct(bw['individual_only']['pcv'], 0)}, and without the macro-region none ({pct(bw['individual_no_region']['pcv'], 0)}): the differences between municipalities "
            "are not who dies there or of what, and that share belonged to the macro-region. Because the variance of a logistic model is rescaled when individual variables "
            "enter, these proportions are not shares of one fixed variance. With everything, "
            f"{pct(bw['full']['pcv'], 0)} was explained and the median odds ratio between municipalities fell to {f2(bw['full']['mor'])} (Figure 4D, Supplementary Table S14, "
            "Supplementary Table S6). The models were fitted by penalised quasi-likelihood steps (nAGQ = 0); refitted by the Laplace approximation, composition "
            f"explained {pct(LAP['brown_white']['composition']['pcv'], 1)} of the municipal variance against {pct(bw['composition']['pcv'], 1)}, and all variables "
            f"{pct(LAP['brown_white']['full']['pcv'], 1)} against {pct(bw['full']['pcv'], 1)}."
            + (f" For Black mothers' children certified Black, composition explained {pct(bk['composition']['pcv'], 0)}, the socioeconomic context "
               f"{pct(bk['socioeconomic']['pcv'], 0)}, the services {pct(bk['services']['pcv'], 0)}, the individual variables without the macro-region {pct(bk['individual_no_region']['pcv'], 0)}, and all "
               f"together {pct(bk['full']['pcv'], 0)}." if bk else ""))
    EST = {o: ML[o]["establishment"] for o in ("brown_white", "black_black")}
    assert all(EST[o]["var_estab"] > 2 * EST[o]["var_mun"] and EST[o]["aic"] < EST[o]["aic_without"] - 100 for o in EST), "the establishment no longer holds the residual variation"
    FXW, FXK = ML["brown_white"]["full_fit"]["fixed"], ML["black_black"]["full_fit"]["fixed"]

    def orx(fx, term):
        e_, s_ = fx[term]["est"], fx[term]["se"]
        return f"{math.exp(e_):.2f} (95%CI {math.exp(e_ - 1.96 * s_):.2f}; {math.exp(e_ + 1.96 * s_):.2f})"

    assert FXW["certifierdeath verification service"]["est"] - 1.96 * FXW["certifierdeath verification service"]["se"] > 0
    assert FXK["certifierdeath verification service"]["est"] + 1.96 * FXK["certifierdeath verification service"]["se"] < 0
    assert FXK["certifiermedical examiner (IML)"]["est"] + 1.96 * FXK["certifiermedical examiner (IML)"]["se"] < 0
    para(d, f"Residual clustering was better captured by the establishment where the death occurred than by the municipality: with a crossed random effect for the "
            f"establishment ({n0(EST['brown_white']['establishments'])} levels), the variance of the log-odds of Brown mothers' infants being "
            f"certified White was {f2(EST['brown_white']['var_estab'])} between establishments and {f2(EST['brown_white']['var_mun'])} between municipalities, and for Black "
            f"mothers' infants certified Black {f2(EST['black_black']['var_estab'])} and {f2(EST['black_black']['var_mun'])}; the Akaike information criterion fell by "
            f"{n0(EST['brown_white']['aic_without'] - EST['brown_white']['aic'])} and {n0(EST['black_black']['aic_without'] - EST['black_black']['aic'])}. Where a municipality "
            "has one hospital the two levels cannot be told apart. The certifier and the individual terms of the full model are in Figure 4E and Supplementary Text S4.")
    S4.append(f"Residual clustering was better captured by the establishment where the death occurred than by the municipality. With a crossed random effect for the "
            f"establishment ({n0(EST['brown_white']['establishments'])} levels; deaths outside any registered establishment share one level per municipality), the variance of the log-odds of Brown mothers' infants being "
            f"certified White was {f2(EST['brown_white']['var_estab'])} between establishments and {f2(EST['brown_white']['var_mun'])} between municipalities, and for Black "
            f"mothers' infants certified Black {f2(EST['black_black']['var_estab'])} and {f2(EST['black_black']['var_mun'])}; the Akaike information criterion fell by "
            f"{n0(EST['brown_white']['aic_without'] - EST['brown_white']['aic'])} and {n0(EST['black_black']['aic_without'] - EST['black_black']['aic'])}. Where a municipality "
            "has one hospital the two levels cannot be told apart, and the composition of a hospital's catchment is not measured, so this does not partition the variance "
            "between them. Within the full "
            f"model (Figure 4E), death verification services certified Brown mothers' infants White more often than attending physicians (odds ratio "
            f"{orx(FXW, 'certifierdeath verification service')}), and both verification services and medical examiners certified Black mothers' infants Black less often "
            f"({orx(FXK, 'certifierdeath verification service')} and {orx(FXK, 'certifiermedical examiner (IML)')}). Brown mothers' infants were certified White more often "
            f"when the mother had 12 or more years of schooling ({orx(FXW, 'school12 or more')} against 8-11 years) and less often with 0-3 years "
            f"({orx(FXW, 'school0-3')}), more often when the death occurred after the first month ({orx(FXW, 'age_group28-364 days')} against the first week) and less often "
            f"when the birth weight was under 2,500 g ({orx(FXW, 'low_weight<2500 g')}).")
rows = []
EXPL = [("composition", "Composition"), ("state", "State"), ("context", "Context (socioeconomic, services, recording)"), ("composition_state", "Composition + state"),
        ("composition_context", "Composition + context"), ("composition_state_context", "Composition + state + context")]
MLMAP = {"composition": "composition", "context": "socioeconomic_services", "composition_context": "composition_socioeconomic_services"}
for k, lab in EXPL:
    row = [lab, pct(mP["deviance_explained"][k], 0), f2(mP[k]["I"]), pct(mK["deviance_explained"][k], 0), f2(mK[k]["I"])]
    if ML:
        row += [pct(ML["brown_white"]["sequence"][MLMAP[k]]["pcv"], 0) if k in MLMAP else "-",
                pct(ML["black_black"]["sequence"][MLMAP[k]]["pcv"], 0) if k in MLMAP and "black_black" in ML else "-"]
    rows.append(row)
stable("Supplementary Table S14 - What composition, state and municipal context explain of the variation between municipalities in the certified race of linked infant deaths, Brazil, "
         "2013-2023",
      ["Explanation", "Brown mother, certified White: deviance explained", "Moran's I of residuals", "Black mother, certified Black: deviance explained",
       "Moran's I of residuals"] + (["Brown, certified White: municipal variance explained (multilevel)", "Black, certified Black: municipal variance explained (multilevel)"] if ML else []),
      rows,
      [f"Deviance explained and Moran's I: binomial models of the municipal proportions, municipalities with five or more linked deaths ({n0(mP['rate']['units'])} and "
       f"{n0(mK['rate']['units'])}); Moran's I without any term: {f2(mP['none']['I'])} and {f2(mK['none']['I'])}. Composition: B-spline of the logit share of White births. "
       "Context: GDP per capita, illiteracy, urban share, population, capital, metropolitan region, physicians, certification by verification service and medical examiner, "
       "deaths in hospital, race left blank. Multilevel: proportional change in the variance of a municipal random intercept of a logistic model of the individual deaths "
       "(context there: socioeconomic and services blocks; state not entered)."])
figure(d, "place_explain", "Figure 4 - What the variation between municipalities goes with: Brown mothers' infants certified White against the composition of births "
                          "(A), what each explanation removes in binomial models (B), the border test (C), the municipal variance explained in multilevel models (D) "
                          "and the terms of the full multilevel model (E), Brazil, 2013-2023",
       ["A: one point per municipality, BYM2 posterior means; the solid line is the national linkage by tenth of composition, the dashed line the family's classification "
        "under one year. B: binomial models of the municipal proportions, municipalities with five or more linked deaths; composition, a B-spline of the logit share of "
        "White births; context, the municipal variables of E. C: grey points are pairs of neighbouring municipalities in different states, black points means by eighth "
        "with 95% confidence intervals. D: proportional change in the variance of a municipal random intercept of a logistic model of the individual deaths. E: random "
        "intercept for the municipality; the eleven terms above the line are municipal, per standard deviation where continuous; references: attending physician, death "
        "in hospital, death at 0-6 days, perinatal cause, mother with 8-11 years of schooling and aged 20-34, birth weight 2,500 g or more. Bars: 95% confidence "
        "intervals."])
if False:
    figure(d, "multilevel", "Figure 5 - Multilevel models of the certified race of linked infant deaths: municipal variance explained by each set of variables (A) and odds ratios "
                      "of the full model (B), Brazil, 2013-2023",
           ["Random intercept for the municipality. B: Brown mothers' infants certified White and Black mothers' infants certified Black; municipal variables per standard "
            "deviation; reference categories: attending physician, death in hospital, death at 0-6 days, perinatal cause, mother with 8-11 years of schooling and aged 20-34, "
            "birth weight 2,500 g or more. Bars: 95% confidence intervals."])

# ----------------------------------------------------------------- who classifies
d.add_heading("Who classifies", level=2)
CPY, CEL, OCC, INV = MC["copy"], MC["cells"], MC["occurrence"], MC["investigation"]
PHY = json.loads((HERE / "results" / "physician.json").read_text(encoding="utf-8"))
AT, EL = CPY["agreement"]["birth establishment, 0-1 day"], CPY["agreement"]["elsewhere"]
GA, GE = CPY["gradient_PW"]["birth establishment, 0-1 day"], CPY["gradient_PW"]["elsewhere"]
assert AT["est"] < 0.75 and GA["coef"] > GE["coef"], "the certificate now looks copied where the birth record is at hand"
assert CEL["WP"]["coef"] < -0.5 < 0.5 < CEL["PW"]["coef"] and CEL["KP_on_brown_share"]["coef"] > 0.3, "the cells are no longer symmetric"
po = OCC["PW"]
para(d, f"The certificate was not a copy of the birth record. Among infants who died in the establishment where they were born, on the day of birth or the "
        f"next, when the birth record and its mother's race lay at hand, the certificate agreed with the mother's race in {ci(AT)} of deaths, against {ci(EL)} "
        f"among infants who died elsewhere, and the dependence of Brown mothers' infants certified White on composition was steeper there (slope "
        f"{f2(GA['coef'])} per logit unit, against {f2(GE['coef'])} elsewhere). The other cells moved toward the local majority only partly: Brown mothers' infants were "
        f"certified White as often as not where {pct(CEL['PW_half_white_share']['est'], 0)} (95%CI {pct(CEL['PW_half_white_share']['lo'], 0)}; "
        f"{pct(CEL['PW_half_white_share']['hi'], 0)}) of births were White, not where half were (Supplementary Text S4).")
S4.append(f"The certificate was not a copy of the birth record. Among infants who died in the establishment where they were born, on the day of birth or the "
        f"next, when the birth record and its mother's race lay at hand, the certificate agreed with the mother's race in {ci(AT)} of deaths, against {ci(EL)} "
        f"among infants who died elsewhere, and the dependence of Brown mothers' infants certified White on composition was steeper there (slope "
        f"{f2(GA['coef'])} per logit unit, against {f2(GE['coef'])} elsewhere). The cells the Brown-to-White exchange does not involve moved with the local "
        f"majority as well: White mothers' infants were certified Brown more often where fewer births were White (slope {f2(CEL['WP']['coef'])}, against "
        f"{f2(CEL['PW']['coef'])} for Brown mothers' infants certified White), Black mothers' infants were certified Brown more often where more births were Brown "
        f"({f2(CEL['KP_on_brown_share']['coef'])} per logit unit of the Brown share), and Brown mothers' infants were certified White as often as not where "
        f"{pct(CEL['PW_half_white_share']['est'], 0)} (95%CI {pct(CEL['PW_half_white_share']['lo'], 0)}; {pct(CEL['PW_half_white_share']['hi'], 0)}) of births were "
        f"White, not where half were, as a rule of classing by the local majority would predict; with slopes below one per logit unit, the cells moved toward "
        f"the local majority only partly. Of the infants who died outside their municipality of residence ({pct(OCC['share_elsewhere'], 0)} of linked deaths), Brown mothers' infants "
        f"were certified White by {f2(po['lws']['coef'])} (standard error {f2(po['lws']['se'])}) per logit unit of the composition of the municipality of residence "
        f"and {f2(po['lws_occ']['coef'])} ({f2(po['lws_occ']['se'])}) of the municipality where the death occurred, at equal values of the other. The two were "
        "not tested against each other, and the composition of a small municipality of residence is measured with more noise than that of the larger "
        "municipality where most such deaths occur, which attenuates the first; the contrast is inconclusive.")
INVK = {"not investigated": "not investigated", "2": "investigated with a home visit or family interview", "3": "investigated from the health establishment's chart",
        "8": "investigated from several sources", "1": "investigated by the committee"}
inv_rows = [(INVK[k], INV[k]) for k in INVK if k in INV]
para(d, "Whether the death was investigated, and how, changed the certificate little: agreement with the mother's race was "
        + "; ".join(f"{ci(v['agreement'])} {lab}" for lab, v in inv_rows[:2]) + "; the other kinds of investigation were alike. "
        f"Among {n0(PHY['PW']['deaths'])} deaths of 2014-2018 with the certifying physician recorded, the log-odds variance of Brown mothers' infants certified White "
        f"was {f2(PHY['PW']['all']['physician'])} between physicians, {f2(PHY['PW']['all']['death_estab'])} between establishments and {f2(PHY['PW']['all']['mun6'])} "
        f"between municipalities; with {PHY['PW']['deaths'] / PHY['PW']['physicians']:.1f} deaths per physician that order is not secure.")
# ----------------------------------------------------------------- time
d.add_heading("Time and place", level=2)
pk, pa_, pw, pp = PN["KK"], PN["agree"], PN["PW"], PN["PP"]
kk_sl = pk["fixed"]["yc"]
pw_sl = pw["fixed"]["yc"]
assert pw_sl["Estimate"] + 1.96 * pw_sl["Std. Error"] < 0 and pw["lrt_slope_varies"] < 0.01, "Brown to White no longer falls, or falls evenly"
UFNAME = {"SC": "Santa Catarina", "RS": "Rio Grande do Sul", "GO": "Goiás", "RN": "Rio Grande do Norte", "PR": "Paraná", "PA": "Pará", "AM": "Amazonas", "ES": "Espírito Santo",
          "RJ": "Rio de Janeiro", "AP": "Amapá", "SP": "São Paulo", "MG": "Minas Gerais", "BA": "Bahia", "DF": "Distrito Federal", "MS": "Mato Grosso do Sul",
          "MT": "Mato Grosso", "TO": "Tocantins", "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará", "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas", "SE": "Sergipe",
          "RO": "Rondônia", "AC": "Acre", "RR": "Roraima"}
sy = {st: sum(v.values()) / len(v) for st, v in SP["state_year"]["agree"].items()}
rank = sorted(sy, key=sy.get)
slopes = {"North": pw["by_macro"]["yc"]["Estimate"]} | {rn: pw["by_macro"]["yc"]["Estimate"] + pw["by_macro"][f"yc:macro{rn}"]["Estimate"]
                                                        for rn in ("Northeast", "Southeast", "South", "Centre-West")}
lo_r, hi_r = min(slopes, key=slopes.get), max(slopes, key=slopes.get)
ag_sl = pa_["fixed"]["yc"]
para(d, f"From 2013 to 2023 the certificate moved toward the mother's race for Brown mothers' infants: the White category for them fell by "
        f"{f2(-pw_sl['Estimate'])} (95%CI {f2(-pw_sl['Estimate'] - 1.96 * pw_sl['Std. Error'])}; {f2(-pw_sl['Estimate'] + 1.96 * pw_sl['Std. Error'])}) in log-odds "
        f"per decade within intermediate regions (the crude national proportion went from {f2(cell(I['by_year']['2013'], 'Parda', 'Branca')['est'])} "
        f"to {f2(cell(I['by_year']['2023'], 'Parda', 'Branca')['est'])}), and the Brown category rose by {f2(pp['fixed']['yc']['Estimate'])} (Figure 5A, Supplementary Table S7). "
        f"The change was uneven, by macro-region from {f2(slopes[lo_r])} per decade in the {lo_r} to {f2(slopes[hi_r])} in the {hi_r} (Figure 5B; Supplementary Text S4).")
S4.append(f"From 2013 to 2023 the certificate moved toward the mother's race for Brown mothers' infants: the White category for them fell by "
        f"{f2(-pw_sl['Estimate'])} (95%CI {f2(-pw_sl['Estimate'] - 1.96 * pw_sl['Std. Error'])}; {f2(-pw_sl['Estimate'] + 1.96 * pw_sl['Std. Error'])}) in log-odds "
        f"per decade within intermediate regions (a conditional slope; the crude national proportion went from {f2(cell(I['by_year']['2013'], 'Parda', 'Branca')['est'])} "
        f"to {f2(cell(I['by_year']['2023'], 'Parda', 'Branca')['est'])}), and "
        f"the Brown category rose by {f2(pp['fixed']['yc']['Estimate'])} (Figure 5A; by region, state, age and year in Supplementary Table S7). The change was "
        f"uneven: the slopes of the 133 intermediate regions varied with a standard deviation of {f2(pw['sd_slope'])} (likelihood-ratio p < 0.001), and by "
        f"macro-region from {f2(slopes[lo_r])} per decade in the {lo_r} to {f2(slopes[hi_r])} in the {hi_r} (Figure 5B, Supplementary Figure S8A). The overall agreement with the mother's "
        f"race changed by {f2(ag_sl['Estimate'])} (95%CI {f2(ag_sl['Estimate'] - 1.96 * ag_sl['Std. Error']).replace('-0.00', '0.00')}; "
        f"{f2(ag_sl['Estimate'] + 1.96 * ag_sl['Std. Error'])}) per decade, an interval that includes no change, because the Black category rose while the White "
        "category for Brown mothers' infants fell (the Black category is the subject of a companion paper). By state, mean agreement over the years was highest "
        f"in {UFNAME[rank[-1]]} ({f2(sy[rank[-1]])}) and {UFNAME[rank[-2]]} ({f2(sy[rank[-2]])}) and lowest in {UFNAME[rank[0]]} ({f2(sy[rank[0]])}) and "
        f"{UFNAME[rank[1]]} ({f2(sy[rank[1]])}) (Supplementary Figure S8B).")


def bw(v, lv="municipality", key="PW", part="w", model="all"):
    """A between (b) or within (w) coefficient of the panel, log-odds with its 95%CI."""
    c = PNL[key][lv][model][f"{v}_{part}"]
    return f"{f2(c['est'])} (95%CI {f2(c['est'] - 1.96 * c['se'])}; {f2(c['est'] + 1.96 * c['se'])})"


WM, WI, CEN2 = WB["municipality"], WB["immediate"], PNL["census"]
L2 = PL["2012-2023 (mother declared)"]
para(d, f"Within places, composition moved the certificate far less than it separated places: in the municipality-year panel the within coefficient "
        f"was about {WI['all']['lw_w']['est'] / WI['lw_reliability'] / WI['all']['lw_b']['est'] * 100:.0f}% of the between coefficient once corrected for the noise "
        f"of the yearly share (immediate regions), over the census decade {f2(CEN2['coef']['cw_w']['est'])} against {f2(CEN2['coef']['cw_b']['est'])}, and the long "
        "panel did not discriminate (Figure 5C-D). Within places, GDP per capita and physicians did not move the certificate; the share of natural deaths "
        f"certified by a verification service ({bw('svo')}) and of deaths with the race left blank ({bw('blank')}) did. Details are in Supplementary Text S3.")
figure(d, "place_time", "Figure 5 - Over time and within places: certified race of infants by year of death (A), the change of Brown mothers' infants certified White by "
                       "intermediate region (B), and the certificate against composition between places and within the same place over the years, in the yearly "
                       "panel (C) and against the census (D), Brazil, 2013-2023",
       ["A: one-to-one linkage, 95% confidence intervals. B: binomial mixed model with random intercept and slope for the year by intermediate region; change in the "
        "probability scale between the fitted values of 2013 and 2023. C: binomial mixed models of municipality-years and of immediate region-years, with region-by-year "
        "effects and a random intercept for the place; all variables in one model; composition is the logit of the share of White mothers among the year's live births. "
        "D, left: deaths of 2013-2015 and 2021-2023 against the Censuses of 2010 and 2022, with literacy and urbanisation in the model; right: the certificate's excess "
        "of White over the births' share against the census composition interpolated yearly, 2012-2023, with state-by-year effects. Bars: 95% confidence intervals."])



# ----------------------------------------------------------------- the family and the birth record (review 2026-11-22: tests C and B)
d.add_heading("The family and the birth record against place", level=2)
DEC = CT_["0-9"]["decomposition_brown_mother"]
para(d, f"Families carried little of the gradient. The children aged 0-9 of a Brown mother and a Brown father were reported White in "
        f"{ci(PPW['bins'][0])} of households in municipalities with under 10% of White births and in {ci(PPW['bins'][-1])} where 90% or more were White, most of "
        f"the rise below 30% (Figure 6A); the logit slope was {f2(PPW['raw']['slope'])} (standard error {f2(PPW['raw']['se'])}; {f2(PPW['adjusted']['slope'])} with age, "
        f"sex and schooling held), against {f2(CT_['certificate']['slope_bins'])} for the certificate on the same axis. For all Brown mothers the family's share White "
        f"rose from {f2(DEC[0]['observed'])} to {f2(DEC[-1]['observed'])}: with the partner mix held at the national one it rose to {f2(DEC[-1]['mix_held'])}, with the "
        f"rate within couple type held to {f2(DEC[-1]['rate_held'])}, about half each; in whiter places Brown mothers more often had White partners "
        f"({f2(DEC[0]['partner_white'])} to {f2(DEC[-1]['partner_white'])}). The birth record leaned toward the local majority. Against the mothers of children aged 0-2 "
        f"in the 2010 Census sample, the share of White mothers on the birth records of 2012-2013 followed the census with a logit slope of "
        f"{f2(MW['slope_none']['slope'])} nationally, {f2(MW['slope_region']['slope'])} within region and {f2(MW['slope_uf']['slope'])} within state, where 1 means "
        f"agreement up to a constant (Figure 6B); against the women aged 15-49 of the 2022 Census, the birth records of 2021-2023 gave "
        f"{f2(BVC['W']['15-49']['slope_none']['slope'])}, {f2(BVC['W']['15-49']['slope_region']['slope'])} and {f2(BVC['W']['15-49']['slope_uf']['slope'])}. In the "
        f"least White tenth of municipalities {f2(MW['bins'][0]['birth'])} of mothers were White on the birth record against {f2(MW['bins'][0]['census'])} in the "
        "census. Sampling error in the census would flatten the slope, not steepen it.")
figure(d, "place_category", "Figure 6 - Where the gradient lies: the certificate and the family by the municipality's composition (A), and the birth record "
                            "against the census (B), Brazil",
       ["A: share of children recorded White by tenth of the municipality's share of White births (SINASC 2012-2023): Brown mothers' infants on the death "
        "certificate (linked deaths 2013-2023) and children aged 0-9 of Brown mothers reported by their household (2010 Census sample), all and with a Brown "
        "partner; bars, 95% confidence intervals clustered by municipality. B: share of mothers White on the birth record against the census share, by tenth of "
        "municipalities: mothers of children aged 0-2 in the 2010 Census sample against birth records of 2012-2013, and women aged 15-49 in the 2022 Census "
        "(IBGE table 9606) against birth records of 2021-2023; dashed, equality."])

RD = [["The certificate copies the birth record (transmission)", "agreement near 1 where the birth record is at hand; no gradient there",
       f"agreement {f2(AT['est'])} at hand against {f2(EL['est'])} elsewhere; gradient {f2(GA['coef'])} against {f2(GE['coef'])}", "excluded as the main mechanism"],
      ["The certificate records the family's answer", "certificate equal to the family's classification everywhere; family interviews change it",
       "equal nationally for Brown to White, opposite departures by region; interviewed deaths agreed slightly more often", "weakened"],
      ["A local norm of the certifier", "every cell follows the local majority, even odds where half the births are White",
       f"White mothers' infants Brown slope {f2(CEL['WP']['coef'])}; Black mothers' infants Brown on Brown share {f2(CEL['KP_on_brown_share']['coef'])}; "
       f"even odds at {pct(CEL['PW_half_white_share']['est'], 0)} White", "supported in part: partial, not a majority rule"],
      ["A state practice", "a step at state borders", f"border slope {f2(BD_['PW']['slope_state_effect'])}", "supported in part"],
      ["The Brown category differs between regions", "families in whiter places report a Brown couple's child White more often",
       f"{f2(PPW['bins'][0]['est'])} to {f2(PPW['bins'][-1]['est'])} across composition; logit slope {f2(PPW['slope_bins'])} against the certificate's "
       f"{f2(CT_['certificate']['slope_bins'])}", "weakened: a small part at most"],
      ["The birth record leans toward the local majority", "the birth record's share White departs from the census along composition",
       f"mothers against mothers: slope {f2(MW['slope_none']['slope'])} nationally, {f2(MW['slope_region']['slope'])} within region", "present: the reference bends the same way"],
      ["The individual certifier", "large variance between physicians", f"physicians {f2(PHY['PW']['all']['physician'])}, establishments "
       f"{f2(PHY['PW']['all']['death_estab'])}, municipalities {f2(PHY['PW']['all']['mun6'])}", "present; weakly identified"],
      ["A norm that follows the population as it changes", "within-place slope equal to the between slope",
       f"yearly: about a tenth of between; census decade: {f2(PNL['census']['coef']['cw_w']['est'])} against {f2(PNL['census']['coef']['cw_b']['est'])}; "
       "long panel: does not discriminate", "weakened; a slow adjustment not excluded"],
      ["Wealth or services", "context explains as composition does", "less alone, little beside composition; within places, wealth and physicians nothing, "
       "verification-service share and blanks moved it", "weakened"],
      ["The deaths' case mix", "individual variables explain municipal variance", "none without the macro-region", "excluded"]]
table(d, "Table 1 - Readings of the certified race, what each predicts, and what the data showed, linked infant deaths, Brazil, 2013-2023", ["Reading", "Prediction",
      "Result", "Status"], RD, ["Results of the tests in this section and the preceding ones; slopes in log-odds per logit unit of the share of White (or Brown) births."])


# ----------------------------------------------------------------- after infancy, and the family
d.add_heading("After infancy", level=2)
CC_ = SP["candidates_context"]
cg = CC_["children_comp_gdp"]
assert cg[">=60%|middle"]["rows"]["Parda"]["Branca"]["est"] > cg["<30%|middle"]["rows"]["Parda"]["Branca"]["est"] + 0.2, "composition no longer orders the 1-9 estimates"
para(d, "After infancy, with an estimator that needs no linkage, Brown mothers' children aged 1-9 were certified White in "
        f"{cc(cg['<30%|middle']['rows']['Parda']['Branca'])} of deaths in municipalities with under 30% of White births and middle GDP per capita and in "
        f"{cc(cg['>=60%|middle']['rows']['Parda']['Branca'])} where 60% or more were White (Supplementary Text S1, Tables S9-S11, Figures S5-S6).")
