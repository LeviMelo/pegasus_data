# The Results of the manuscript. Executed by build.py after text.py, whose names it uses.
# ruff: noqa: F821
d.add_heading("Results", level=1)

# ----------------------------------------------------------------- the records
FL, LS = I["flow"], I["linked_share"]
para(d, f"The one-to-one linkage found the birth record of {pct(I['linked'] / I['certificates'])} of infant deaths; the linked share was "
        f"{pct(LS['by_certified']['Branca'])}, {pct(LS['by_certified']['Parda'])} and {pct(LS['by_certified']['Preta'])} for deaths certified White, Brown and Black, "
        f"{pct(LS['by_certified']['Indigena'])} for Indigenous, and was lower after the first month ({pct(LS['by_age']['28-364 d'])}) and in the North "
        f"({pct(LS['by_region']['North'])}) than in the South ({pct(LS['by_region']['South'])}) (Supplementary Table S11). Of the {n0(FL['lake_infant_deaths'])} infant certificates, "
        f"{n0(FL['no_sex'])} had no sex and {n0(FL['no_municipality'])} no municipality of residence and could not enter the candidate estimator. In municipalities with fewer "
        f"than 25,600 births per year, the candidate estimator reproduced the linkage's proportions; over all sizes, {f2(cell(v_all['candidates'], 'Branca', 'Branca')['est'])} "
        f"against {f2(cell(v_all['linkage'], 'Branca', 'Branca')['est'])} for White, {f2(cell(v_all['candidates'], 'Parda', 'Parda')['est'])} against "
        f"{f2(cell(v_all['linkage'], 'Parda', 'Parda')['est'])} for Brown and {f2(cell(v_all['candidates'], 'Preta', 'Preta')['est'])} against "
        f"{f2(cell(v_all['linkage'], 'Preta', 'Preta')['est'])} for Black mothers; in the largest municipalities its standard error for White reached "
        f"{f2(cell(v_top['candidates'], 'Branca', 'Branca')['se'])} (Supplementary Figure S1, Supplementary Table S2). The deceased was among the candidates for "
        f"{pct(C19['matrix']['found'])} of deaths at 1-9 years and {pct(Y['by_kind']['natural']['found'])} of deaths from natural causes at 15-24 years, against "
        f"{pct(v_all['candidates']['found'])} of infant deaths; the remainder had moved municipality or had no birth record. Table 1 gives the populations.")
table(d, "Table 1 - Sources and study populations",
      ["Population", "Source and period", "Classification compared with the certificate", "Records"],
      [["Infant deaths", "SIM 2013-2023 linked one-to-one to SINASC", "Mother's declaration", f"{n0(I['certificates'])} deaths; {n0(I['linked_with_race'])} linked with the mother's race"],
       ["Deaths at 1-9 years", "SIM 2013-2024, born 2012-2023; candidate estimator", "Mother's declaration", f"{n0(C19['matrix']['deaths'])} deaths ({n0(C14['matrix']['deaths'])} at 1-4, {n0(C59['matrix']['deaths'])} at 5-9)"],
       ["Deaths at 15-24 years", f"SIM {YOUTH_YEARS}, born {YOUTH_BORN}; candidate estimator", "Colour recorded at birth", f"{n0(youth_all)} deaths; {n0(youth_small)} in municipalities under 1,600 births per year"],
       ["Children under 25 living with their mother", "2010 Census sample", "Family's classification of other children, by the mother's race", f"{n0(CEN['pairs_records'])} pair records"],
       ["Municipalities", "IBGE mesh 2022; SIDRA; CNES; SIM", "Context of the place", f"{n0(G['municipalities'])} municipalities, {n0(G['edges'])} pairs of neighbours"],
       ["Women who died in hospital at 15-49 years", "SIM, SINASC and hospital admissions 2015-2022", "Declaration as a mother, hospital record (exploratory)", f"{n0(T3['with_three'])} with three races recorded"]],
      ["SIM: Mortality Information System. SINASC: Live Birth Information System. IBGE: Brazilian Institute of Geography and Statistics. CNES: National Register of Health "
       "Establishments."])
figure(d, "fig1", "Figure 1 - Design: the two records of the same person, the census reference of other children and the place",
       ["The family's classification is a population reference applied by the mother's race, the age and the place; it is not a label of the deceased."])

# ----------------------------------------------------------------- three classifications
d.add_heading("Three classifications", level=2)
para(d, f"Families did not classify children as their mothers (Table 2, Figure 2). Before one year, the household reported as White {f2(fam(F0, 'Branca', 'Branca'))} of the children "
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
table(d, "Table 2 - Proportion of children assigned to each race according to the mother's race, in the family's classification (2010 Census) and on the death certificate "
         "(2013-2024), Brazil", ["Mother's race", "Classification of the child", "White (95%CI)", "Brown (95%CI)", "Black (95%CI)", "Indigenous (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Census proportions are weighted sample estimates (standard errors below 0.005 under simple random sampling, not shown). Certificate, "
       f"under 1 year: one-to-one linkage, binomial intervals (intervals from the bootstrap over municipalities are {CBRANGE} times wider; text). Certificate at 1-9 years: "
       "candidate estimator, municipalities with fewer than 25,600 live births per year; estimates are differences of counts and can leave the interval 0 to 1. Not estimable: "
       "standard error above 0.15, or outside 0 to 1 by more than two standard errors. Rows do not sum to 1: the remainder is another category or no race recorded."])
figure(d, "fig2", "Figure 2 - Proportion of children assigned to each race according to the mother's race: family's classification, death certificate and their difference, "
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
para(d, f"The linked infant deaths gave a median of {RES['PW']['median_trials']:.0f} deaths of Brown mothers' children per municipality ({pct(RES['PW']['share_ge20'])} of "
        f"municipalities had 20 or more) and of {RES['KK']['median_trials']:.0f} of Black mothers' children ({pct(RES['KK']['share_zero'])} of municipalities had none). The "
        f"municipal resolution is therefore supported for the children of Brown mothers, with credible intervals of median width {f2(RES['PW']['median_ci_width'])}; other "
        "cells, the Black category above all, rest on few deaths per municipality and are shown as smoothed fields (Supplementary Figures S8, S9; the spatial models' "
        "parameters in Supplementary Table S13).")
para(d, f"The proportion of Brown mothers' infants certified White ranged, across the municipalities in which 90% of births occur, from {f2(DI['PW']['p5'])} to "
        f"{f2(DI['PW']['p95'])} (Figure 3A); the proportion of Brown mothers' children aged 0-9 whom families reported White ranged from {f2(DI['famPW']['p5'])} to "
        f"{f2(DI['famPW']['p95'])} (Figure 3B). On the logit scale the smoothed municipal values of the certificate varied {FV['PW']['M0'] / FV['famPW']['M0']:.1f} times as much "
        f"as the family's (variances {f2(FV['PW']['M0'])} and {f2(FV['famPW']['M0'])}; the family's values rest on more children per municipality and are less shrunk, so "
        f"the ratio is not inflated by smoothing). The variation was spatially structured: the BYM2 mixing parameter was estimated at {f2(BY['PW']['M0']['phi'])}, Moran's I "
        f"of the standardised proportions was {f2(MO['PW']['rate']['I'])} (p ≤ 0.001 by 999 permutations, {n0(MO['PW']['rate']['units'])} municipalities), and local "
        f"statistics at p < 0.05, without correction for multiplicity, marked {n0(LI['PW']['high-high'])} municipalities of high values among high values in the South, "
        f"Southeast and Centre-West and {n0(LI['PW']['low-low'])} of low values in the North and Northeast (Figure 3D). The certificate classed Brown mothers' infants White "
        f"more often than families class Brown mothers' children where White births were the majority and less often where they were few (Figure 3C, Figure 4A), the two "
        f"crossing where about {pct(cross, 0)} of births were White; weighted by births, the certificate exceeded the family by {f2(DI['diff_by_region']['South'])} in the "
        f"South and fell short of it by {f2(-DI['diff_by_region']['Northeast'])} in the Northeast. Certified race differed from the mother's in proportions that were also "
        f"spatially clustered (Moran's I {f2(MO['disagree']['rate']['I'])}; Supplementary Figure S10), as was the use of the Black category for Black mothers' infants "
        f"(Moran's I {f2(MO['KK']['rate']['I'])}; Supplementary Figure S9).")
figure(d, "fig3", "Figure 3 - Infant deaths of Brown mothers' children certified White (A), Brown mothers' children aged 0-9 reported White by the family (B), their difference "
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
CP = SP["comp_place"]
para(d, f"For Brown mothers' infants certified White, the municipality's composition alone explained {pct(mP['deviance_explained']['composition'], 0)} of the deviance "
        f"between municipalities, the state alone {pct(mP['deviance_explained']['state'], 0)}, and the socioeconomic, service and recording context alone "
        f"{pct(mP['deviance_explained']['context'], 0)}; composition and state together explained {pct(mP['deviance_explained']['composition_state'], 0)}, and the context "
        f"added {pct(mP['deviance_explained']['composition_state_context'] - mP['deviance_explained']['composition_state'], 0)} (Table 3, Figure 4B). Composition (3 degrees "
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
        f"{f2(bt['slope_state_effect'] - 1.96 * bt['slope_se'])}; {f2(bt['slope_state_effect'] + 1.96 * bt['slope_se'])}, errors clustered by the {bt['state_pairs']} pairs of "
        f"states) times the difference between their states' effects estimated from municipalities touching no other state ({n0(bt['pairs'])} pairs; Figure 4C); for the "
        f"certified race differing from the mother's it was {f2(bd_['slope_state_effect'])} (95%CI {f2(bd_['slope_state_effect'] - 1.96 * bd_['slope_se'])}; "
        f"{f2(bd_['slope_state_effect'] + 1.96 * bd_['slope_se'])}), and for the Black category the state effects estimated away from borders were too unstable for the test. "
        "The certified race changes in a step at state borders, as a state practice would make it, and the step is smaller than the difference between the states' interiors; "
        "because the estimated state effects carry error, which pulls the slope toward 0, the slope is a lower bound of the step. By place within the state, Brown mothers' "
        f"infants were certified White in {f2(SP['by_place']['capital']['rows']['Parda']['Branca']['est'])} of deaths in state capitals, "
        f"{f2(SP['by_place']['metropolitan, not capital']['rows']['Parda']['Branca']['est'])} in the rest of the metropolitan regions and "
        f"{f2(SP['by_place']['interior']['rows']['Parda']['Branca']['est'])} in the interior (Figure 4D); where 30-59% of births were White, the proportions were "
        f"{f2(CP['30-59%|capital']['rows']['Parda']['Branca']['est'])}, {f2(CP['30-59%|metropolitan, not capital']['rows']['Parda']['Branca']['est'])} and "
        f"{f2(CP['30-59%|interior']['rows']['Parda']['Branca']['est'])}. At equal composition, municipal wealth changed the proportion less than composition did: where under 30% "
        f"of births were White, it was {f2(SP['comp_gdp']['<30%|low']['rows']['Parda']['Branca']['est'])} in the poorest third of municipalities by GDP per capita and "
        f"{f2(SP['comp_gdp']['<30%|high']['rows']['Parda']['Branca']['est'])} in the richest; where 60% or more were White, "
        f"{f2(SP['comp_gdp']['>=60%|low']['rows']['Parda']['Branca']['est'])} and {f2(SP['comp_gdp']['>=60%|high']['rows']['Parda']['Branca']['est'])} (Figure 4E). Intervals "
        "are not given for these proportions: binomial intervals understate the clustering of deaths by place.")
if ML:
    sq = {o: ML[o]["sequence"] for o in ML}
    bw, bk = sq["brown_white"], sq.get("black_black")
    assert bw["composition"]["pcv"] > bw["socioeconomic"]["pcv"] > 0 and bw["composition"]["pcv"] > bw["services"]["pcv"], "composition no longer explains most"
    assert bw["composition_socioeconomic_services"]["pcv"] - bw["composition"]["pcv"] < 0.1, "the context now adds much to composition"
    para(d, f"In the multilevel models of the {n0(ML['brown_white']['n'])} linked infant deaths of Brown mothers' children, the variance between municipalities of the "
            f"log-odds of being certified White was {f2(bw['null']['var_mun'])} (median odds ratio {f2(bw['null']['mor'])}). Composition alone explained "
            f"{pct(bw['composition']['pcv'], 0)} of it; the socioeconomic context and place alone {pct(bw['socioeconomic']['pcv'], 0)}; the services and recording alone "
            f"{pct(bw['services']['pcv'], 0)}; and composition with both {pct(bw['composition_socioeconomic_services']['pcv'], 0)}: most of what wealth and services explain "
            f"alone, they share with composition. The variables of the death and the birth with the macro-region and the year, without any municipal variable, explained "
            f"{pct(bw['individual_only']['pcv'], 0)}: part of what differs between municipalities is who dies there and of what, and where. With everything, "
            f"{pct(bw['full']['pcv'], 0)} was explained and the median odds ratio between municipalities fell to {f2(bw['full']['mor'])} (Table 3, Figure 5, "
            "Supplementary Table S12). The models were fitted by penalised quasi-likelihood steps (nAGQ = 0), which can understate variance components with binary outcomes; "
            "the proportions of variance explained are approximate."
            + (f" For Black mothers' children certified Black, composition explained {pct(bk['composition']['pcv'], 0)}, the socioeconomic context "
               f"{pct(bk['socioeconomic']['pcv'], 0)}, the services {pct(bk['services']['pcv'], 0)}, the individual variables {pct(bk['individual_only']['pcv'], 0)}, and all "
               f"together {pct(bk['full']['pcv'], 0)}." if bk else ""))
    EST = {o: ML[o]["establishment"] for o in ("brown_white", "black_black")}
    assert all(EST[o]["var_estab"] > 2 * EST[o]["var_mun"] and EST[o]["aic"] < EST[o]["aic_without"] - 100 for o in EST), "the establishment no longer holds the residual variation"
    FXW, FXK = ML["brown_white"]["full_laplace"]["fixed"], ML["black_black"]["full_laplace"]["fixed"]

    def orx(fx, term):
        e_, s_ = fx[term]["est"], fx[term]["se"]
        return f"{math.exp(e_):.2f} (95%CI {math.exp(e_ - 1.96 * s_):.2f}; {math.exp(e_ + 1.96 * s_):.2f})"

    assert FXW["certifierdeath verification service"]["est"] - 1.96 * FXW["certifierdeath verification service"]["se"] > 0
    assert FXK["certifierdeath verification service"]["est"] + 1.96 * FXK["certifierdeath verification service"]["se"] < 0
    assert FXK["certifiermedical examiner (IML)"]["est"] + 1.96 * FXK["certifiermedical examiner (IML)"]["se"] < 0
    para(d, f"Residual clustering was better captured by the establishment where the death occurred than by the municipality. With a crossed random effect for the "
            f"establishment ({n0(EST['brown_white']['establishments'])} levels; deaths outside any registered establishment share one level per municipality), the variance of the log-odds of Brown mothers' infants being "
            f"certified White was {f2(EST['brown_white']['var_estab'])} between establishments and {f2(EST['brown_white']['var_mun'])} between municipalities, and for Black "
            f"mothers' infants certified Black {f2(EST['black_black']['var_estab'])} and {f2(EST['black_black']['var_mun'])}; the Akaike information criterion fell by "
            f"{n0(EST['brown_white']['aic_without'] - EST['brown_white']['aic'])} and {n0(EST['black_black']['aic_without'] - EST['black_black']['aic'])}. Where a municipality "
            "has one hospital the two levels cannot be told apart, and the composition of a hospital's catchment is not measured, so this does not partition the variance "
            "between them. Within the full "
            f"model (Figure 5B), death verification services certified Brown mothers' infants White more often than attending physicians (odds ratio "
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
table(d, "Table 3 - What composition, state and municipal context explain of the variation between municipalities in the certified race of linked infant deaths, Brazil, "
         "2013-2023",
      ["Explanation", "Brown mother, certified White: deviance explained", "Moran's I of residuals", "Black mother, certified Black: deviance explained",
       "Moran's I of residuals"] + (["Brown, certified White: municipal variance explained (multilevel)", "Black, certified Black: municipal variance explained (multilevel)"] if ML else []),
      rows,
      [f"Deviance explained and Moran's I: binomial models of the municipal proportions, municipalities with five or more linked deaths ({n0(mP['rate']['units'])} and "
       f"{n0(mK['rate']['units'])}); Moran's I without any term: {f2(mP['none']['I'])} and {f2(mK['none']['I'])}. Composition: B-spline of the logit share of White births. "
       "Context: GDP per capita, illiteracy, urban share, population, capital, metropolitan region, physicians, certification by verification service and medical examiner, "
       "deaths in hospital, race left blank. Multilevel: proportional change in the variance of a municipal random intercept of a logistic model of the individual deaths "
       "(context there: socioeconomic and services blocks; state not entered)."])
figure(d, "fig4", "Figure 4 - Brown mothers' infants certified White: municipalities against the composition of their births (A), what each explanation removes (B), the "
                  "border test (C), place within the state (D) and municipal wealth at equal composition (E), Brazil, 2013-2023",
       ["A: one point per municipality, BYM2 posterior means; the solid line is the national linkage by tenth of composition, the dashed line the family's classification "
        "under one year. C: grey points are pairs of neighbouring municipalities in different states, black points means by eighth with 95% confidence intervals."])
if ML:
    figure(d, "fig5", "Figure 5 - Multilevel models of the certified race of linked infant deaths: municipal variance explained by each set of variables (A) and odds ratios "
                      "of the full model (B), Brazil, 2013-2023",
           ["Random intercept for the municipality. B: Brown mothers' infants certified White and Black mothers' infants certified Black; municipal variables per standard "
            "deviation; reference categories: attending physician, death in hospital, death at 0-6 days, perinatal cause, mother with 8-11 years of schooling and aged 20-34, "
            "birth weight 2,500 g or more. Bars: 95% confidence intervals."])

# ----------------------------------------------------------------- time
d.add_heading("Time and place", level=2)
pk, pa_, pw, pp = PN["KK"], PN["agree"], PN["PW"], PN["PP"]
kk_sl = pk["fixed"]["yc"]
assert kk_sl["Estimate"] - 1.96 * kk_sl["Std. Error"] > 0 and pk["lrt_slope_varies"] < 0.01, "the Black category no longer rises, or rises evenly"
south = pk["by_macro"]["yc"]["Estimate"] + pk["by_macro"]["yc:macroSouth"]["Estimate"]
UFNAME = {"SC": "Santa Catarina", "RS": "Rio Grande do Sul", "GO": "Goiás", "RN": "Rio Grande do Norte", "PR": "Paraná", "PA": "Pará", "AM": "Amazonas", "ES": "Espírito Santo",
          "RJ": "Rio de Janeiro", "AP": "Amapá", "SP": "São Paulo", "MG": "Minas Gerais", "BA": "Bahia", "DF": "Distrito Federal", "MS": "Mato Grosso do Sul",
          "MT": "Mato Grosso", "TO": "Tocantins", "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará", "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas", "SE": "Sergipe",
          "RO": "Rondônia", "AC": "Acre", "RR": "Roraima"}
sy = {st: sum(v.values()) / len(v) for st, v in SP["state_year"]["agree"].items()}
rank = sorted(sy, key=sy.get)
slopes = {"North": pk["by_macro"]["yc"]["Estimate"]} | {rn: pk["by_macro"]["yc"]["Estimate"] + pk["by_macro"][f"yc:macro{rn}"]["Estimate"]
                                                        for rn in ("Northeast", "Southeast", "South", "Centre-West")}
lo_r, hi_r = min(slopes, key=slopes.get), max(slopes, key=slopes.get)
ag_sl = pa_["fixed"]["yc"]
para(d, f"From 2013 to 2023 the Black category for Black mothers' infants rose by {f2(kk_sl['Estimate'])} (95%CI {f2(kk_sl['Estimate'] - 1.96 * kk_sl['Std. Error'])}; "
        f"{f2(kk_sl['Estimate'] + 1.96 * kk_sl['Std. Error'])}) in log-odds per decade, nationally from {f2(cell(I['by_year']['2013'], 'Preta', 'Preta')['est'])} to "
        f"{f2(cell(I['by_year']['2023'], 'Preta', 'Preta')['est'])} (Figure 6A; by region, state, age and year in Supplementary Table S3); the Brown category for Brown mothers' infants rose by {f2(pp['fixed']['yc']['Estimate'])} and the "
        f"White category for Brown mothers' infants fell by {f2(-pw['fixed']['yc']['Estimate'])}. The rise was not uniform: the regional slopes for the Black category varied "
        f"with a standard deviation of {f2(pk['sd_slope'])} (likelihood-ratio p = {pk['lrt_slope_varies']:.4f}), from {f2(slopes[lo_r])} per decade in the {lo_r} to "
        f"{f2(slopes[hi_r])} in the {hi_r} (Figure 6B, 6C), and in 2023 the certificate still used the category for a minority of Black mothers' infants. The overall "
        f"agreement with the mother's race changed by {f2(ag_sl['Estimate'])} (95%CI {f2(ag_sl['Estimate'] - 1.96 * ag_sl['Std. Error'])}; "
        f"{f2(ag_sl['Estimate'] + 1.96 * ag_sl['Std. Error'])}) per decade, an interval that includes no change; the negative correlation of regional level and slope "
        f"({f2(pa_['cor_intercept_slope'])}) is expected in part from regression to the mean. By state, mean agreement over the years was highest in {UFNAME[rank[-1]]} "
        f"({f2(sy[rank[-1]])}) and {UFNAME[rank[-2]]} ({f2(sy[rank[-2]])}) and lowest in {UFNAME[rank[0]]} ({f2(sy[rank[0]])}) and {UFNAME[rank[1]]} ({f2(sy[rank[1]])}) "
        "(Figure 6D).")
figure(d, "fig6", "Figure 6 - Certified race of infants by year of death (A), and the change of the Black category for Black mothers' infants by intermediate region (B, C), "
                  "and agreement with the mother's race by state and year (D), Brazil, 2013-2023",
       ["A: one-to-one linkage, 95% confidence intervals. B, C: binomial mixed model with random intercept and slope for the year by intermediate region; change in the "
        "probability scale between the fitted values of 2013 and 2023."])


# ----------------------------------------------------------------- mortality under each classification
d.add_heading("Mortality under each classification", level=2)
para(d, f"Table 4 and Figure 7 give mortality by the mother's race and by certified race over the same births. Before one year, mortality was {f1(IR['by_mother']['Branca']['est'])} "
        f"per 1,000 live births for children of White mothers and {f1(IR['by_mother']['Parda']['est'])} for children of Brown mothers (ratio {ci(IR['ratio_mother']['Branca'], log=True)}); "
        f"by certified race over the same births, which is the Ministry's indicator, the ratio was {ci(IR['ratio_certificate']['Branca'], log=True)}, and over the census-based "
        f"population under one year {f2(IR['ratio_certificate_population'])}. At 1-4 years the White to Brown ratio was {rr(C14)} by the mother's race and {rc(C14)} by certified "
        f"race over births; over the census-based population of 2016-2024, the ratio by certified race was {f2(CONV['ratio_certificate_population'])}, against "
        f"{ci(CONV['ratio_mother'], log=True)} by the mother's race in the same years. Certification reversed the direction of the ratio when the denominator was declared by the "
        "mother and compressed it toward 1 when the denominator was classified as the census classifies. At 5-9 years the ratios were "
        f"{rr(C59)} and {rc(C59)}. Passing deaths and births through the family's classification gave {f2(C14['ratio_household']['Branca'])} at 1-4 and "
        f"{f2(C59['ratio_household']['Branca'])} at 5-9 years (no interval). For Black against Brown the ratios at 1-4 years were {rr(C14, 'Preta')} by the mother's race and "
        f"{rc(C14, 'Preta')} by certified race, and for Indigenous against Brown {rr(C14, 'Indigena')} and {rc(C14, 'Indigena')}. Without the municipalities of 25,600 or more "
        f"births per year the White to Brown ratio by the mother's race was {ci(C14['without_large']['rates']['ratio_mother']['Branca'], log=True)} at 1-4 years; leaving out one "
        f"state at a time, it ranged from {f2(C14['rates']['ratio_mother']['Branca']['loo_min'])} to {f2(C14['rates']['ratio_mother']['Branca']['loo_max'])}; and if the deceased "
        f"were found among the candidates 10 points less often for White than for Brown mothers, or the reverse, it would be {f2(C14['t_sensitivity'][min(C14['t_sensitivity'])])} "
        f"or {f2(C14['t_sensitivity'][max(C14['t_sensitivity'])])}. A linked cohort of births of 2012-2018 classified by the mother's race {cite('reboucas2022')} reported crude "
        f"rates that give White to Brown ratios of {f2(REB['under 1']['ratio'])} under one year and {f2(REB['1-4']['ratio'])} at 1-4 years.")
rows = []
for label, B, hh, unit in (("Under 1 year", IR, IR["ratio_household"], "per 1,000 live births"), ("1-4 years", C14["rates"], C14["ratio_household"], "per 100,000 person-years"),
                           ("5-9 years", C59["rates"], C59["ratio_household"], "per 100,000 person-years")):
    for k in ORDER:
        rows.append([f"{label} ({unit})", EN[k], f1(B["by_mother"][k]["est"]), f1(B["by_certificate"][k]["est"]),
                     "1 (reference)" if k == "Parda" else ci(B["ratio_mother"][k], log=True), "1 (reference)" if k == "Parda" else f"{f2(hh[k])} (no interval)",
                     "1 (reference)" if k == "Parda" else ci(B["ratio_certificate"][k], log=True)])
table(d, "Table 4 - Mortality rates and rate ratios by race under the mother's declaration, the family's classification and the death certificate, Brazil, deaths of 2013-2024 "
         "(under 1 year: 2013-2023)",
      ["Age", "Race", "Rate, mother's race", "Rate, certified race", "Ratio, mother's race (95%CI)", "Ratio, family's classification", "Ratio, certified race (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Denominators: live births of the same cohorts by mother's race. Family's classification: deaths and births by mother's race passed through "
       "the proportions of the 2010 Census at the same age. Deaths with no race on the certificate are not in the rates by certified race; giving them the race of the mother "
       f"changes the infant White to Brown ratio by certified race from {f2(IR['ratio_certificate']['Branca']['est'])} to {f2(IR['ratio_certificate_blank_as_mother'])}."])
figure(d, "fig7", "Figure 7 - Mortality rates by the mother's race and by certified race over the same births (A-C), and White to Brown rate ratios under four ways of "
                  "classifying deaths and denominators (D), Brazil, 2013-2024",
       ["Bars: 95% confidence intervals. Census-based population: the population account by race, under one year in 2013-2023 and at 1-4 years in 2016-2024."])
# ----------------------------------------------------------------- consequences
d.add_heading("Where the certificate misstates the inequality", level=2)
MSB = MS["by_composition"]
assert MS["reversed"] > 0.6 * MS["regions"] and MSB["<10%"]["ratio_of_ratios"] > max(MSB["10-29%"]["ratio_of_ratios"], MSB["30-59%"]["ratio_of_ratios"]), "the misstatement pattern changed"
NNE = ("AC", "AM", "AP", "PA", "RO", "RR", "TO", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA")
n_nne = sum(r["uf"] in NNE for r in MS["top"])
assert n_nne >= 20, "the most misstated regions are no longer mostly in the North and Northeast"
para(d, f"In {MS['reversed']} of the {MS['regions']} immediate regions, holding {pct(MS['births_share_reversed'], 0)} of births, the White to Brown infant mortality rate ratio by "
        f"certified race had the opposite direction to the ratio by the mother's race; the ratio by the mother's race was below 1 with a credible interval excluding 1 in "
        f"{MS['mother_below_1_credibly']} regions, the certified ratio above 1 in {MS['certificate_above_1_credibly']}, and both in {MS['reversed_credible']} (Figure 8A, 8B). "
        "The misstatement, the ratio of the certified to the mother's-race rate ratio, was largest where White births were fewest (a mean, weighted by births, of "
        f"{f2(MSB['<10%']['ratio_of_ratios'])} in regions with under 10% of White births, against {f2(MSB['30-59%']['ratio_of_ratios'])} at 30-59% and "
        f"{f2(MSB['>=60%']['ratio_of_ratios'])} at 60% or more; Figure 8C, 8D): where White births are rare, a small share of Brown mothers' infants certified White inflates "
        "a small White rate. The relation was U-shaped, so that composition and GDP per capita, which were correlated "
        f"({f2(MS['corr_white_share_log_gdp'])}), each explained little of it linearly (R² {f2(MS['wls']['r2'])}). Of the 25 regions where the certificate most overstated the "
        f"ratio, {n_nne} were in the North and Northeast (Supplementary Table S14; all regions in Supplementary Data 2).")
figure(d, "fig8", "Figure 8 - White to Brown infant mortality rate ratio by immediate region, by the mother's race (A) and by certified race (B), the ratio of the two (C), and "
                  "the ratio of the two against the share of White births and GDP per capita (D), Brazil, 2013-2023",
       ["Posterior means of a Poisson model with BYM2 effects over the 510 immediate regions; deaths over live births of the same years by mother's race. D: area of a point, "
        "live births; the line is the births-weighted mean by class of composition."])

# ----------------------------------------------------------------- ages 15-24
d.add_heading("Ages 15 to 24: cause of death, place and certifier", level=2)
YK = Y["by_kind"]
YA = Y["by_age"]
gap_ages = [a for a in range(15, 25) if all(YA[k][str(a)]["rows"].get("Branca") for k in ("natural", "assault"))
            and YA["natural"][str(a)]["rows"]["Branca"]["Branca"]["est"] - YA["assault"][str(a)]["rows"]["Branca"]["Branca"]["est"]
            > 1.96 * math.hypot(YA["natural"][str(a)]["rows"]["Branca"]["Branca"]["se"], YA["assault"][str(a)]["rows"]["Branca"]["Branca"]["se"])]
para(d, "In municipalities with fewer than 1,600 births per year, people recorded as White at birth who died at 15-24 years were certified White less often as the cause of "
        "death moved from natural causes to assault (Table 5, Figure 9): "
        + ", ".join(f"{cc(cell(YK[k], 'Branca', 'Branca'))} for {KL[k].lower()}" for k in KINDS)
        + f". The proportion certified Brown rose from {cc(cell(YK['natural'], 'Branca', 'Parda'))} to {cc(cell(YK['assault by firearm'], 'Branca', 'Parda'))}. People recorded as Brown "
        f"at birth were certified Brown in {cc(cell(YK['natural'], 'Parda', 'Parda'))} of natural deaths and {cc(cell(YK['assault by firearm'], 'Parda', 'Parda'))} of assaults by firearm. "
        "The difference between natural causes and assault was present in every region ("
        + "; ".join(f"{rn}: {f2(cell(Y['by_kind_region']['natural'][rn], 'Branca', 'Branca')['est'])} and {f2(cell(Y['by_kind_region']['assault'][rn], 'Branca', 'Branca')['est'])}"
                    for rn in Y["by_kind_region"]["natural"])
        + f") and in both periods, and by single year of age it exceeded twice its standard error at {len(gap_ages)} of the 10 ages from 15 to 24 "
        f"({', '.join(str(a) for a in gap_ages)}) (Supplementary Figure S6); in larger municipalities it could not be estimated.")
ST = CTX["youth"]["standardised"]
BC = CTX["youth"]["by_composition"]
assert ST["natural"]["Branca"]["Branca"]["est"] > ST["external, not assault"]["Branca"]["Branca"]["est"] > ST["assault"]["Branca"]["Branca"]["est"]
gaps = [cell(a["matrix"], "Branca", "Branca")["est"] - cell(b["matrix"], "Branca", "Branca")["est"] for a, b in zip(BC["natural"], BC["assault"], strict=True)]
assert all(x > 0 for x in gaps), "a class of composition without the gradient"
para(d, "Assaults were concentrated in municipalities with few White births, where people recorded White at birth were less often certified White whatever the cause "
        f"(Figure 9B). In the municipalities with under 20% of White births the proportion certified White was {cc(cell(BC['natural'][0]['matrix'], 'Branca', 'Branca'))} for natural "
        f"causes and {cc(cell(BC['assault'][0]['matrix'], 'Branca', 'Branca'))} for assaults; with 80% or more it was {cc(cell(BC['natural'][4]['matrix'], 'Branca', 'Branca'))} and "
        f"{cc(cell(BC['assault'][4]['matrix'], 'Branca', 'Branca'))}. Standardised to the composition of the natural deaths, the proportions were "
        f"{ci(ST['natural']['Branca']['Branca'])} for natural causes, {ci(ST['external, not assault']['Branca']['Branca'])} for external causes other than assault and "
        f"{ci(ST['assault']['Branca']['Branca'])} for assaults and legal interventions: the difference between causes was smaller than the crude one, and its point estimate "
        "was positive in every class of composition, with overlapping intervals in the classes at the two ends.")
YC = CTX["youth"]["by_certifier"]
YP = CTX["youth"]["by_place"]
share_me = {k: v.get("medical examiner", 0) / sum(v.values()) for k, v in CTX["youth"]["certifier_share"].items()}
ph_nat, me_nat = cell(YC["natural"]["physician"], "Branca", "Branca"), cell(YC["natural"]["medical examiner"], "Branca", "Branca")
me_ass, me_ext = cell(YC["assault"]["medical examiner"], "Branca", "Branca"), cell(YC["external, not assault"]["medical examiner"], "Branca", "Branca")
assert abs(ph_nat["est"] - me_nat["est"]) < 1.96 * math.hypot(ph_nat["se"], me_nat["se"]), "physician and medical examiner now differ"
assert me_ext["est"] - me_ass["est"] > 1.96 * math.hypot(me_ext["se"], me_ass["se"])
para(d, f"A medical examiner certified {pct(share_me['natural'])} of the natural deaths, {pct(share_me['external, not assault'])} of the external deaths other than assault and "
        f"{pct(share_me['assault'])} of the assaults. Within natural deaths, the proportion of people recorded White at birth who were certified White was {cc(ph_nat)} when a "
        f"physician certified and {cc(me_nat)} when a medical examiner did; among deaths certified by a medical examiner it was {cc(me_ass)} for assaults and {cc(me_ext)} for "
        f"other external causes, against {cc(cell(YC['external, not assault']['physician'], 'Branca', 'Branca'))} when a physician certified those. The difference between "
        "causes was present within one kind of certifier; between certifiers, within one kind of cause, the intervals were 15 to 30 points wide for natural causes and "
        "assaults and cannot exclude differences of 10 points, and for external causes other than assault medical examiners certified White more often than physicians. "
        f"By place of death, assaults gave {cc(cell(YP['assault']['health facility'], 'Branca', 'Branca'))} in a health facility and "
        f"{cc(cell(YP['assault']['street'], 'Branca', 'Branca'))} on the street (Supplementary Table S5).")
rows = []
for k in KINDS:
    m = YK[k]
    rows.append([KL[k], n0(m["deaths"]), cc(cell(m, "Branca", "Branca")), cc(cell(m, "Branca", "Parda")), cc(cell(m, "Parda", "Parda")), cc(cell(m, "Parda", "Branca")), cc(cell(m, "Preta", "Preta"))])
for k, lab in (("natural", "Natural causes"), ("external, not assault", "External, not assault"), ("assault", "Assault (all means, with legal intervention)")):
    for c in ("physician", "medical examiner"):
        m = YC[k][c]
        rows.append([f"{lab}, certified by {c}", n0(m["deaths"]), cc(cell(m, "Branca", "Branca")), cc(cell(m, "Branca", "Parda")), cc(cell(m, "Parda", "Parda")), cc(cell(m, "Parda", "Branca")),
                     cc(cell(m, "Preta", "Preta"))])
table(d, f"Table 5 - Certified race of people who died at 15-24 years according to the colour recorded at birth, by cause of death and certifier, municipalities with fewer than "
         f"1,600 live births per year, Brazil, {YOUTH_YEARS}",
      ["Cause of death", "Deaths", "Recorded White at birth, certified White (95%CI)", "Recorded White, certified Brown (95%CI)", "Recorded Brown, certified Brown (95%CI)",
       "Recorded Brown, certified White (95%CI)", "Recorded Black, certified Black (95%CI)"], rows,
      ["95%CI: 95% confidence interval. Candidate estimator: estimates are differences of counts, and intervals can extend beyond 0 or 1. Not estimable: standard error "
       "above 0.15, or outside 0 to 1 by more than two standard errors."])
figure(d, "fig9", f"Figure 9 - Proportion certified White among people recorded as White at birth who died at 15-24 years, by cause of death and sex (A) and by cause of "
                  f"death and racial composition of the municipality (B), Brazil, {YOUTH_YEARS}",
       ["Municipalities with fewer than 1,600 live births per year. Bars: 95% confidence intervals; estimates that are not estimable are not drawn."])

# ----------------------------------------------------------------- after infancy, and the family
d.add_heading("After infancy, and the family's own classification", level=2)
CC_ = SP["candidates_context"]
cg, yg = CC_["children_comp_gdp"], CC_["youth_comp_gdp"]
assert cg[">=60%|middle"]["rows"]["Parda"]["Branca"]["est"] > cg["<30%|middle"]["rows"]["Parda"]["Branca"]["est"] + 0.2, "composition no longer orders the 1-9 estimates"
ya_lo, ya_hi = yg["assault"]["<30%|low"]["rows"]["Branca"]["Branca"], yg["assault"]["<30%|high"]["rows"]["Branca"]["Branca"]
assert ya_hi["est"] - ya_lo["est"] > 1.96 * math.hypot(ya_lo["se"], ya_hi["se"]) and ya_hi["se"] <= 0.15, "wealth no longer matters for assaults in the least White class"
para(d, "The dependence on composition held after infancy, with the candidate estimator. At 1-9 years, Brown mothers' children were certified White in "
        f"{cc(cg['<30%|middle']['rows']['Parda']['Branca'])} of deaths in municipalities with under 30% of White births and middle GDP per capita, and in "
        f"{cc(cg['>=60%|middle']['rows']['Parda']['Branca'])} where 60% or more were White, with smaller differences by GDP within each class; at 15-24 years, among "
        f"people recorded White at birth who died of natural causes, the proportion certified White was {cc(yg['natural']['<30%|low']['rows']['Branca']['Branca'])} in the "
        f"poorest municipalities with under 30% of White births and {cc(yg['natural']['>=60%|middle']['rows']['Branca']['Branca'])} in middle-income municipalities with 60% "
        f"or more, and among assaults {cc(yg['assault']['<30%|low']['rows']['Branca']['Branca'])} and {cc(yg['assault']['>=60%|middle']['rows']['Branca']['Branca'])} "
        f"(Supplementary Table S15). Within the least White class, wealth mattered at 15-24 years: assaults gave {cc(yg['assault']['<30%|low']['rows']['Branca']['Branca'])} "
        f"in the poorest third of municipalities and {cc(yg['assault']['<30%|high']['rows']['Branca']['Branca'])} in the richest. Regional rate ratios after infancy are in Supplementary "
        "Figure S2 and, by state, in Supplementary Table S9; the composition gradient at 1-9 years is in Supplementary Figure S5 and Supplementary Table S4.")
BP, BI = CEN["by_partner"], CEN["by_instruction"]
para(d, f"The family's classification itself depended on both parents: children under 10 of Brown mothers were reported White in {f2(fam(BP['White'], 'Parda', 'Branca'))} of "
        f"households where the mother's partner was White, {f2(fam(BP['Brown'], 'Parda', 'Branca'))} where the partner was Brown and {f2(fam(BP['Black'], 'Parda', 'Branca'))} "
        f"where the partner was Black (a partner was identified for {pct(CEN['partner_identified'])} of children), and by the mother's instruction in "
        f"{f2(fam(BI['none or incomplete primary'], 'Parda', 'Branca'))} to {f2(fam(BI['higher'], 'Parda', 'Branca'))} (Supplementary Figure S4, Supplementary Table S6). A model in which the "
        "certificate mixes the family's classification with the local distribution fitted the children of White and Brown mothers and not those of Black mothers "
        "(Supplementary Figure S3, Supplementary Table S16). Birth cohorts born from 1940 to 2009 moved away from the White category between censuses in "
        f"{R['cohort_falls']['white_fell']} of {R['cohort_falls']['intervals']} intervals, a description that does not separate reclassification from differential "
        "mortality, migration and coverage (Supplementary Text S3, Supplementary Figure S7, Supplementary Table S7).")
