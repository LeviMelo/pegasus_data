# The front of the manuscript: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# before text_results.py, text_discussion.py and text_supplement.py, which share its namespace (R, SP, cite, para, table, figure, ci, cc ...).
# ruff: noqa: F821
DESIGN = "cross-sectional study of routinely collected birth and death records and of census microdata"
OBJECTIVE = ("to compare the race recorded on the death certificates of infants and children in Brazil with the race their mothers declared for themselves "
             "and with the race families assign to children, and to find where in the country and over which years they differ and what explains it")
I, V = R["infants"], R["validation"]
IL = I["linkage"]
CH = R["children"]
C14, C59, C19 = CH["1-4"], CH["5-9"], CH["1-9"]
CEN, MIX, Y, CTX = R["census"], R["mixture"], R["youth"], R["context"]
F0, F14, F59 = CEN["by_band"]["0"], CEN["by_band"]["1-4"], CEN["by_band"]["5-9"]
GI, GC0, GC14 = R["gradient_infants"], CEN["gradient"]["0"], CEN["gradient"]["1-4"]
T3 = R["triples"]
IR = R["infant_rates"]
CB = I["cluster_bootstrap"]
form = {r["year"]: r for r in R["form"]}
coh = {(r["cohort"], r["year"]): r for r in R["cohorts"]}
cb = {r["cohort"]: r for r in R["cohorts_birth"]}
KINDS = ["natural", "suicide", "transport", "other external", "other assault", "assault by firearm", "legal intervention"]
KL = {"natural": "Natural causes", "suicide": "Suicide", "transport": "Transport accidents", "other external": "Other external causes", "other assault": "Assault, other means",
      "assault by firearm": "Assault by firearm", "legal intervention": "Legal intervention"}
youth_small = sum(Y["by_kind"][k]["deaths"] for k in KINDS)
youth_all = youth_small + sum(Y["by_kind_large"][k]["deaths"] for k in KINDS)
size = {r["size"]: r for r in V}
v_all, v_top = size["all"], size[">=25,600"]
YOUTH_YEARS = f"{Y['death_years'][0]}-{Y['death_years'][1]}"
YOUTH_BORN = f"{Y['birth_years'][0]}-{Y['birth_years'][1]}"
W14, W59 = C14["without_large"]["matrix"], C59["without_large"]["matrix"]
CONV = C14["conventional_2016_2024"]
REB = R["reboucas"]
PNL = json.loads((HERE / "results" / "panel.json").read_text(encoding="utf-8"))
WB = {lv: PNL["PW"][lv] for lv in ("municipality", "immediate")}
PL = json.loads((HERE / "results" / "panel_long.json").read_text(encoding="utf-8"))
MC = json.loads((HERE / "results" / "mechanism.json").read_text(encoding="utf-8"))
G, MO, BY, BD_, PN, RA, MS, ML = SP["graph"], SP["moran"], SP["bym2"], SP["border"], SP["panel"], SP["ratio"], SP["misstated"], SP.get("multilevel", {})


def lo_hi(bins, m, c, family=False):
    """The cell in the first and in the last bin of the municipal share of White births where it is estimable."""
    ok = [(b["white_share"], (b["matrix"][m][c]["est"] if family else b["matrix"]["rows"][m][c]["est"])) for b in bins
          if (m in b["matrix"] if family else m in b["matrix"]["rows"])]
    return ok[0][1], ok[-1][1]


def rr(block, k="Branca"):
    return ci(block["rates"]["ratio_mother"][k], log=True)


def rc(block, k="Branca"):
    return ci(block["rates"]["ratio_certificate"][k], log=True)


def cbci(key):
    """A proportion of the linkage with its interval from the bootstrap over municipalities."""
    return ci(CB[key])


def cbx(place):
    """Brown mothers' infants certified White in a kind of place (state capital, metropolitan, interior), with a binomial interval."""
    return ci(SP["by_place"][place]["rows"]["Parda"]["Branca"])


def expit(x):
    return 1 / (1 + math.exp(-x))


# claims the text makes in words: each must hold in the results, or the build stops
for blk in (C14, C59):
    assert blk["rates"]["ratio_mother"]["Branca"]["est"] < 1 < blk["rates"]["ratio_certificate"]["Branca"]["est"], "the White to Brown ratios do not have opposite directions"
    assert blk["rates"]["ratio_mother"]["Branca"]["est"] < blk["ratio_household"]["Branca"] < blk["rates"]["ratio_certificate"]["Branca"]["est"], "the family counterfactual is not between"
assert IR["ratio_mother"]["Branca"]["est"] < 1 < IR["ratio_certificate"]["Branca"]["est"], "infants: the ratios do not have opposite directions"
for lv_ in ("municipality", "immediate"):
    b_, w_ = WB[lv_]["all"]["lw_b"], WB[lv_]["all"]["lw_w"]
    assert w_["est"] + 1.96 * w_["se"] < 0.5 * b_["est"], "the within-place composition slope is no longer far below the between slope"
assert WB["immediate"]["lw_reliability"] > 0.9, "the regional yearly composition is now mostly sampling noise"
assert PNL["census"]["coef"]["cw_w"]["est"] + 1.96 * PNL["census"]["coef"]["cw_w"]["se"] < PNL["census"]["coef"]["cw_b"]["est"], "census: within reaches between"
FW = I["flow"]
assert I["certificates"] - FW["birth_after_death"] == FW["lake_infant_deaths"], "the certificate counts no longer reconcile"
assert 0 <= FW["candidate_deaths"] - FW["with_sex_and_municipality"] <= FW["birth_after_death"], "the candidate estimator's deaths no longer reconcile"
assert CONV["ratio_mother"]["est"] < CONV["ratio_certificate_population"] < 1 < CONV["ratio_certificate_births"]["est"], "conventional denominator: not compressed between"
assert abs(IR["ratio_certificate_population"] - IR["ratio_mother"]["Branca"]["est"]) < 0.05, "infants: the census denominator no longer agrees with the mother's race"
assert fam(F14, "Preta", "Preta") > 1.5 * cell(W14, "Preta", "Preta")["est"], "Black children: the certificate is not far below the family"
assert cell(Y["by_kind"]["assault by firearm"], "Branca", "Branca")["est"] + 0.1 < cell(Y["by_kind"]["natural"], "Branca", "Branca")["est"]
assert v_top["candidates"]["rows"]["Branca"]["Branca"]["se"] > 0.1, "the largest class is now precise"
ls_ = I["linked_share"]["by_certified"]
assert max(ls_[k] for k in ("Branca", "Parda", "Preta")) - min(ls_[k] for k in ("Branca", "Parda", "Preta")) < 0.02, "linkage differs by certified race"
CBR = [CB[k]["se"] / CB[k]["se_binomial"] for k in CB]
CBRANGE = f"{min(CBR):.0f} to {max(CBR):.0f}"
assert min(CBR) > 2, "the municipal bootstrap no longer widens the intervals"
g_pb = lo_hi(GI, "Parda", "Branca")
g_bp = lo_hi(GI, "Branca", "Parda")
f_pb = lo_hi(GC0, "Parda", "Branca", family=True)
f_bp = lo_hi(GC0, "Branca", "Parda", family=True)
assert g_pb[1] > g_pb[0] + 0.3 and g_bp[0] > g_bp[1] + 0.3, "no gradient with the local composition"

d = new_doc()
TITLE = ("Race on the death certificate and place: the mother's declaration, the family's classification and the certified race of "
         "infants and children across 5,570 Brazilian municipalities, 2013-2024")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
DI, FV = SP["distribution"], SP["field_var"]
d.add_heading("Abstract", level=1)
mP_ = MO["PW"]
bw_ = ML["brown_white"]["sequence"] if ML else None
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}. Infant deaths of 2013-2023 in the Mortality Information System were linked one-to-one to their birth records, "
        "and deaths at 1-9 years (2013-2024) were related to the live births of the same birth date, sex and municipality, with births of the other sex as the control for "
        "chance agreement. The race households report for children came from the 2010 Census sample. Across 5,570 municipalities, proportions were smoothed by "
        "Besag-York-Mollié (BYM2) models, spatial structure was measured by Moran's I and a test at state borders, and composition, state, socioeconomic context, health "
        "services and recording quality were set against one another in binomial and multilevel models; change over 2013-2023 was modelled by region.")
para(d, f"Results: Among {n0(I['linked_with_race'])} linked infant deaths, the certificate recorded the mother's race for {cbci('Branca>Branca')} of children of White mothers, "
        f"{cbci('Parda>Parda')} of Brown and {cbci('Preta>Preta')} of Black mothers. The smoothed proportion of Brown mothers' infants certified White ranged from {f2(DI['PW']['p5'])} to "
        f"{f2(DI['PW']['p95'])} across the municipalities holding 90% of births, with a between-municipality variance (log-odds) {FV['PW']['M0'] / FV['famPW']['M0']:.0f} times that of the "
        f"family's classification of Brown mothers' children aged 0-9, spatially clustered (Moran's I {f2(mP_['rate']['I'])}); whether it follows a place's "
        f"population as it changes was not settled by two panel designs. Racial composition was associated with "
        f"{pct(mP_['deviance_explained']['composition'], 0)} of the deviance between municipalities, the state {pct(mP_['deviance_explained']['state'], 0)}, both "
        f"{pct(mP_['deviance_explained']['composition_state'], 0)}, and socioeconomic and service context {pct(mP_['deviance_explained']['context'], 0)} alone and little in addition"
        + (f"; in multilevel models composition explained {pct(bw_['composition']['pcv'], 0)} of the municipal variance, context {pct(bw_['socioeconomic_services']['pcv'], 0)}, "
           f"and the deaths' own characteristics none" if bw_ else "")
        + f". At state borders the certified race moved by {f2(BD_['PW']['slope_state_effect'])} of the difference between the states' interiors (a regression "
        "slope on estimated state effects). Where the birth record lay at hand, the certificate agreed with the mother only slightly more often, and the "
        "cells the Brown-to-White exchange does not involve followed the local majority too.")
para(d, "Conclusion: The race on the death certificate of a child differed from both the mother's declaration and the family's classification, was not a copy of "
        "the birth record, and was associated with place: with the racial composition of the municipality, in every cell in the direction of the local majority, "
        "and with the state, more than with wealth, services or the circumstances of the death. The analyses by place and context were exploratory and "
        "ecological, and they do not separate a local classification norm from a Brown category that differs between regions.")
para(d, "Keywords: Race Factors; Death Certificates; Medical Record Linkage; Spatial Analysis; Infant Mortality; Vital Statistics; Brazil.")

# ================================================================= introduction
d.add_heading("Introduction", level=1)
para(d, "Mortality by race in Brazil is computed from two classifications made by different people. The numerator is the race on the death certificate. The Ministry of "
        f"Health instructs that it be asked of the person who informs on the deceased and never decided by the physician from observation {cite('manual_do2022')}; the system does "
        f"not record who gave the information {cite('romero2006')}, and in practice the physician or hospital staff often enter it {cite('travassos2004')}. Deaths from violent "
        f"causes are certified by the medico-legal services {cite('cfm1779')}. The denominator is a declaration: the census respondent's, or, on the live birth record since the "
        f"form of 2011, the mother's declaration of her own race {cite('manual_dn2011')}. Rates computed from the two were shown to depend on the source {cite('chor2005', 'cardoso2005', 'caldas2017')}.")
para(d, f"Race is not one variable. Self-identification, classification by an observer and other dimensions are distinct, though correlated, and which one is used can change findings {cite('roth2016')}. "
        f"In a Brazilian national survey, interviewers and respondents classified people consistently as White, Brown or Black in 79% of cases, with agreement varying with "
        f"education and with the racial composition of the place {cite('telles2002')}; income differences between groups depended on who classified "
        f"{cite('telles1998', 'bailey2013')}, and Brown people were reclassified as White more often in whiter cities {cite('muniz2017')}. Parents do not simply transmit "
        f"their race to their children: in household surveys, more educated non-White parents classified their children as White more often, partly because of whom they married "
        f"{cite('schwartzman2007')}. Classification by others also responds to the social position of the person classified {cite('penner2008', 'saperstein2012')} and, in experiments, to cues of status {cite('freeman2011')}, "
        f"and on United States death certificates it varied with the cause of death {cite('noymer2011')}.")
para(d, f"What this does to mortality statistics has been measured where a second classification of the same person exists. In the United States, certificates agreed with "
        f"survey reports for White and Black decedents and disagreed for American Indian decedents, whose death rates were understated {cite('sorlie1992', 'rosenberg1999', 'arias2016')}, "
        f"and linked birth and infant death records changed infant mortality rates of the smaller groups {cite('hahn1992')}. In São Paulo, 17.3% of 1,012 older adults had on the "
        f"certificate a race other than the one they had reported in a survey, and the correction changed the ranking of mortality {cite('santos2019')}. A cohort of 19.5 million "
        f"Brazilian births linked to deaths, classified by the mother's race, found higher mortality before age 5 among children of Indigenous, Black and Brown mothers than among "
        f"children of White mothers {cite('reboucas2022')}. To our knowledge no study has compared, for the same people and for the country, the race on the death certificate with the "
        "race on the birth record, or either with the race families assign to their children, and none asked where in the country the two disagree.")
para(d, "Where matters because both the composition of the population and the services that fill certificates vary across Brazil's municipalities. The share of White "
        "births ranges from almost none to almost all between neighbouring regions; certificates are completed by hospital physicians, by medico-legal institutes organised by "
        "the states for violent deaths, and, where they exist, by death verification services; and the 27 state health secretariats train and audit the certifiers. Three "
        "readings of the certificate make different predictions in space. Under the first, it transmits the mother's race, and the agreement between the two should not depend "
        "on place. Under the second, it records what the family would answer about the child, as the Ministry's instruction intends; it should then follow the family's "
        "classification wherever families classify children differently from their mothers. Under the third, it reflects a classification made by whoever fills it. If that "
        "classification draws on the local population, it should move continuously with the racial composition of the municipality, across state borders as within states; if it "
        "is an administrative practice, it should change at state borders and with the services that certify; if it follows social position, it should follow the wealth and "
        "schooling of the place and of the family.")
para(d, f"This study aimed {OBJECTIVE}.")

# ================================================================= methods
d.add_heading("Methods", level=1)
para(d, f"Design and reporting. This is a {DESIGN}, reported according to the REporting of studies Conducted using Observational Routinely-collected health Data (RECORD) "
        f"statement {cite('benchimol2015')}.")
para(d, f"Data sources. Death certificates came from the Mortality Information System (SIM) and live birth records from the Live Birth Information System (SINASC), in the "
        f"public files of the Ministry of Health {cite('datasus')}, read in November 2026: deaths of 2013 to 2024 (those of 2023 and 2024 are subject to revision) and births "
        f"of 2000 to 2023. The classification made by families came from the person records of the sample of the 2010 Population Census {cite('ibge_microdata2010')} "
        f"({n0(CEN['records'])} records representing {n0(CEN['persons'])} people). Municipal boundaries were those of the 2022 mesh {cite('ibge_mesh2022')}; immediate and "
        f"intermediate geographic regions {cite('ibge_regions2017')}, state capitals and metropolitan regions {cite('ibge_metro')} were taken from the Brazilian Institute of "
        "Geography and Statistics (IBGE). All files are public and carry no names; records were related through the variables they share, and no identifier was created or kept.")
para(d, "The three classifications. The categories are the five of the official classification: branca (White), preta (Black), parda (Brown), amarela (Yellow) and indígena "
        "(Indigenous); Yellow is not shown separately because of small numbers, and Black and Brown, which Brazilian statistics often group as negros, are kept apart. "
        f"(1) Mother's declaration: on the birth record, the race field became the mother's self-declared race with the form introduced in 2011 {cite('manual_dn2011')}; the "
        f"dedicated field was filled on {pct(form[2010]['mother_field'])} of births in 2010, {pct(form[2011]['mother_field'])} in 2011 and {pct(form[2012]['mother_field'])} in "
        "2012 (Supplementary Table S1), so cohorts born from 2012 were taken to carry the mother's race. For cohorts born from 2000 to 2010 the field is the colour recorded for "
        "the newborn on the previous form, called here the colour recorded at birth. (2) Family's classification: the census asks one resident to report the race of every member "
        "of the household, and the sample questionnaire identifies each person's mother when she lives in the household, which gives the race reported for the child and for the "
        f"mother by the same household ({n0(CEN['pairs_records'])} pair records of children under 25; {pct(CEN['with_mother']['1-4'])} of children aged 1-4 and "
        f"{pct(CEN['with_mother']['15-19'])} of people aged 15-19 lived with their mother). It concerns other children than those who died: it is a population reference, applied "
        "by the mother's race, the child's age and the place, and not a second label of the deceased. (3) Certificate: the race field of the death certificate. Figure 1 "
        "shows how the records relate.")
para(d, f"Linkage of infant deaths. Deaths before one year of age in 2013 to 2023 ({n0(I['certificates'])} certificates) were linked to birth records by a probabilistic linkage "
        f"{cite('fellegi1969')} on birth date, sex, municipality of residence of the mother, birth weight and mother's age, keeping one-to-one pairs. {n0(I['linked'])} "
        f"({pct(I['linked'] / I['certificates'])}) were linked and {n0(I['linked_with_race'])} had the mother's race on the birth record. Candidate pairs were blocked on "
        "combinations of birth date, sex, residence, weight and mother's age, scored by log-likelihood ratios and accepted above a threshold set for each year "
        f"({min(v['threshold_bits'] for v in I['link_quality'].values()):.1f}-{max(v['threshold_bits'] for v in I['link_quality'].values()):.1f} bits); the share of false "
        "links, estimated from the pairs the same keys make when the birth date is moved by seven days, was "
        f"{min(v['fdr_percent'] for v in I['link_quality'].values()):.2f}-{max(v['fdr_percent'] for v in I['link_quality'].values()):.2f}% a year, and on fields not used to "
        f"link the pairs agreed on delivery type in {min(v['validations']['delivery type agrees'] for v in I['link_quality'].values()):.0f}% or more and on plurality in "
        f"{min(v['validations']['plurality agrees'] for v in I['link_quality'].values()):.0f}% or more (Supplementary Table S2). The linked share was compared across "
        f"certified race, size of municipality, region, year and age at death {cite('harron2017', 'doidge2019')}. Each linked pair carries the certifier, place, establishment and "
        "underlying cause of the death, and the mother's schooling and age and the birth weight from the birth record.")
para(d, "Deaths after infancy: estimation without individual linkage. After the first year the certificate has no birth weight or mother's age, and a birth date, a sex and a "
        "municipality do not identify one birth. For each death, the candidates are all live births with the same birth date, sex and municipality of residence. If the family did "
        "not move, one candidate is the deceased; the others agree by chance. The chance candidates were estimated from the births of the other sex on the same day in the same "
        "municipality, scaled by the ratio of births of the two sexes: they share the day and the place and cannot contain the deceased, which makes them a negative control "
        f"{cite('lipsitch2010')}. The difference between candidates and control, summed over a group of deaths and cross-classified by the race on the birth record and the race "
        "on the certificate, estimates the number of deaths of the group in each pair of classes, times the proportion of the deceased found among their candidates "
        "(Supplementary Text S1). The approach estimates a contingency table and not individual links; it differs from methods that correct a regression for linkage error with "
        f"known link probabilities {cite('lahiri2005', 'hof2012')} or that impute over candidate links {cite('goldstein2012')}. It was compared with the one-to-one linkage on the "
        "infant deaths, by size of municipality.")
para(d, f"Study populations. (a) Infant deaths of 2013-2023, linked. (b) Deaths at 1 to 9 years in 2013-2024 of children born in 2012-2023 "
        f"({n0(C19['matrix']['deaths'])} deaths), classified by the mother's race. (c) Children under 10 living with their mother in the 2010 Census sample.")
para(d, "Variables of the death and of the birth. Age at death, sex, municipality of residence, year, underlying cause of death (10th revision of the "
        "International Classification of Diseases: perinatal conditions, congenital anomalies, external causes, other), the certifier (attending or substitute physician, "
        "medical examiner of a medico-legal institute, death verification service, other), the place and the establishment of death, and the mother's years of schooling and "
        "age and the birth weight on the birth record.")
para(d, "Variables of the municipality. Racial composition: the share of White mothers among the municipality's live births of 2012-2023. Socioeconomic context: gross "
        f"domestic product per capita, mean of 2013-2021 {cite('ibge_pib')}; the proportion of people aged 15 or over who could not read and write, the proportion of people "
        "with a household income per head of up to half a minimum wage or none, the urban proportion of the population and the population size, all from the 2010 Census "
        f"{cite('ibge_sidra2010')}. Health services: physicians per 1,000 inhabitants in the December registers of 2013-2023 {cite('cnes')}; and, from the municipality's "
        "own death certificates of 2013-2023, the proportion of natural deaths certified by a death verification service, the proportion of external deaths certified by a "
        "medical examiner and the proportion of deaths in hospital. Quality of recording: the proportion of the municipality's death certificates with no race. Place: state "
        "capital, metropolitan region, macro-region (North: RO, AC, AM, RR, PA, AP, TO; Northeast: MA, PI, CE, RN, PB, PE, AL, SE, BA; Southeast: MG, ES, RJ, SP; "
        "South: PR, SC, RS; Centre-West: MS, MT, GO, DF) and state. The variables, their sources and years are listed in Supplementary Table S3.")
para(d, "Measures. For each class of mother, the proportion of deaths certified in each race, and, in the census, the proportion of children the family classified in "
        "each race.")
para(d, f"Small-area estimation. For each municipality, the linked infant deaths of each class of mother certified in each race, and the census children of each class of "
        f"mother classified in each race, were modelled as binomial counts with a logit link and a Besag-York-Mollié random effect {cite('besag1991')} in the BYM2 "
        f"parametrisation {cite('riebler2016')}, which splits the between-municipality variance into a spatially structured part (on the queen contiguity of the 2022 mesh, "
        f"{n0(G['edges'])} pairs of neighbours; {G['islands_joined']} municipalities without a land neighbour joined to the nearest) and an unstructured part, with "
        f"penalised-complexity priors {cite('simpson2017')}. Models were fitted by integrated nested Laplace approximation {cite('rue2009')} (R-INLA, Gaussian approximation, "
        "empirical Bayes integration over the hyperparameters); maps show posterior means, and the raw proportions and the widths of the credible intervals are in the "
        "supplement.")
para(d, f"Spatial structure and competing explanations. Spatial autocorrelation was measured by Moran's I {cite('moran1950')} of the empirical-Bayes standardised proportion "
        f"{cite('assuncao1999')} and local clusters by the local Moran statistic {cite('anselin1995')}, both with 999 permutations, over municipalities with at least five "
        "linked deaths in the class. To set the explanations against one another, binomial models of the municipal proportions were fitted with the composition (a cubic "
        "B-spline of the logit share of White births), with state fixed effects, with the municipal context, and with their combinations; for each, the deviance explained, "
        "a quasi-likelihood F test of each block given the others, and Moran's I of the Pearson residuals are reported. The border test asks whether the certified race jumps "
        f"at state borders, as a state practice would make it, or changes continuously, as local composition would {cite('keele2015')}: state effects were estimated, with "
        "the composition, from the municipalities that touch no other state, and for each pair of neighbouring municipalities in different states the difference of their "
        "empirical logits was regressed on the difference of their states' effects and of their composition (slope 1: the full state difference appears at the border; "
        "slope 0: none of it does).")
para(d, f"Multilevel models. For the linked infant deaths of each class of mother, the certified race (for example, certified White for children of Brown mothers) was "
        f"modelled by logistic regression with a random intercept for the municipality {cite('bates2015')}. A sequence of fixed parts (none; composition; socioeconomic context "
        "and place; services and recording; their combinations; and these with the individual variables of the death and the birth, the macro-region and the year) gave the "
        f"proportional change in the municipal variance and the median odds ratio {cite('merlo2006')}; the order of entry is reported both ways so that no explanation is "
        "credited with variance it shares with another. Models were fitted by penalised iteratively reweighted least squares (nAGQ = 0); for two outcomes the full model was refitted with a crossed random intercept for the "
        "establishment of death, to set the place against the institution that certifies.")
para(d, "Time by place. The yearly proportions of linked infant deaths certified with the mother's race (2013-2023) in each of the 133 intermediate regions were modelled by "
        "binomial mixed models with a random intercept and a random slope for the year by region; the regional slopes give the change over the decade, and a model with the "
        "macro-region by year interaction tests where the change was faster.")
para(d, "Change within places. A municipality-year panel (2013-2023) set the certified race of each municipality's linked infant deaths against what the "
        f"municipality was that year: the share of White mothers among its live births, GDP per capita {cite('ibge_pib')} over the yearly population, physicians "
        "per 1,000 inhabitants, and, from its own death certificates of that year, the proportion with no race, of natural deaths certified by a death verification "
        "service and of external deaths certified by a medical examiner. Binomial mixed models with a random intercept for the place and year effects split each "
        f"variable into the place's mean over the years (between) and the year's deviation from it (within) {cite('mundlak1978')}; the within coefficient is what "
        "follows a change inside the same place, the between coefficient the cross-sectional gradient. Because a small municipality's yearly share of White births "
        "carries sampling noise that attenuates the within coefficient, the models were fitted on municipality-years and again on immediate region-years, and the "
        "share of the within variance that is not sampling noise is reported. As a second time point independent of the birth records, the change between 2013-2015 "
        "and 2021-2023 in municipalities with five or more deaths in each period was set against the change in the census share of White residents, literacy "
        f"and urbanisation between 2010 and 2022 {cite('ibge_sidra2010')}.")
para(d, "Statistical analysis. Proportions from the one-to-one linkage carry 95% confidence intervals (95%CI) from 400 bootstrap resamples of municipalities, because pairs "
        f"cluster by place; binomial intervals, {CBRANGE} times narrower, are in the supplement. For the candidate estimator, the variance of a difference of counts was "
        "taken as the sum of the two counts (Poisson); because it lost precision in municipalities with 25,600 or more live births per year (Results), its proportions exclude "
        "them, and an estimate is reported as not estimable when its standard error exceeds 0.15 or it lies outside 0 to 1 by more than two standard errors. Municipalities "
        "were grouped by thirds of GDP per capita, weighted by linked deaths, and as state capitals, other members of metropolitan regions and the interior. Census "
        "proportions are weighted; their standard errors treat the sample as simple and are understated. Local Moran statistics are reported at p < 0.05 without "
        "correction for multiplicity. No hypothesis test was pre-registered, and the analyses by place and context are exploratory. Analyses used Python 3.11 (DuckDB, "
        f"statsmodels, esda {cite('rey2010')}, geopandas) and R 4.4 (R-INLA {cite('lindgren2015')}, lme4); the code that produces every number, table and figure "
        "accompanies the article.")
para(d, "Ethics. The study used only public, anonymised data and, under Resolution 510/2016 of the National Health Council, did not require review by a research ethics committee.")
