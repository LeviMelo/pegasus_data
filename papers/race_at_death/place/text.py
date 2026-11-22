# The front of the manuscript: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# before text_results.py, text_discussion.py and text_supplement.py, which share its namespace (R, SP, cite, para, table, figure, ci, cc ...).
# ruff: noqa: F821
DESIGN = "cross-sectional study of routinely collected birth and death records and of census microdata"
OBJECTIVE = ("to compare the race recorded on the death certificates of infants in Brazil with the race their mothers declared for themselves "
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
LAP = json.loads((HERE / "data" / "spatial" / "laplace.json").read_text(encoding="utf-8"))
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
         "infants across 5,570 Brazilian municipalities, 2013-2023")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
DI, FV = SP["distribution"], SP["field_var"]
d.add_heading("Abstract", level=1)
mP_ = MO["PW"]
bw_ = ML["brown_white"]["sequence"] if ML else None
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}. Infant deaths of 2013-2023 were linked one-to-one to their birth records, and the race households report for children in the 2010 Census was set against both. "
        "Across 5,570 municipalities, proportions were smoothed by BYM2 models, with Moran's I, a test at state borders and multilevel models.")
CT_ = json.loads((HERE / "results" / "category_test.json").read_text(encoding="utf-8"))
BVC = json.loads((HERE / "results" / "birth_vs_census.json").read_text(encoding="utf-8"))
PPW, PAW = CT_["0-9"]["white_births"]["PP_white"], CT_["0-9"]["white_births"]["P_any_white"]
MW = BVC["mothers_2010"]["W"]
assert PPW["slope_bins"] < 0.25 * CT_["certificate"]["slope_bins"], "the Brown couples' gradient is no longer a small fraction of the certificate's"
assert MW["slope_region"]["slope"] - 1.96 * MW["slope_region"]["se_robust"] > 1, "the birth record no longer bends toward the local majority within regions"
EST_ = ML["brown_white"]["establishment"]
CLAIM = ["followed the place", "more than the family", "leans toward the local majority"]
para(d, f"Results: Among {n0(I['linked_with_race'])} linked infant deaths, the certificate recorded the mother's race for {cbci('Branca>Branca')} of children of "
        f"White mothers, {cbci('Parda>Parda')} of Brown and {cbci('Preta>Preta')} of Black mothers. The share of Brown mothers' infants certified White ranged from "
        f"{f2(DI['PW']['p5'])} to {f2(DI['PW']['p95'])} across municipalities, rose with the municipality's share of White births "
        f"(composition alone {pct(mP_['deviance_explained']['composition'], 0)} of the deviance) and stepped at state borders. The residual variation lay in the establishment where the death occurred (log-odds variance {f2(EST_['var_estab'])} against "
        f"{f2(EST_['var_mun'])} between municipalities). Families classified a Brown couple's child as White in {f2(PPW['bins'][0]['est'])} "
        f"in the least White municipalities and {f2(PPW['bins'][-1]['est'])} in the most, a gradient under a quarter of the certificate's, while the birth record "
        f"recorded mothers whiter than the census where most were White (logit slope {f2(MW['slope_region']['slope'])} within regions, 1 if it followed the census).")
para(d, "Conclusion: The race on an infant's death certificate followed the place (establishment, composition, state) more than the family, whose classification of a Brown couple's child changed little with composition. "
        "The birth record leans toward the local majority, so against self-declaration the certificate's place dependence is, if anything, understated.")
para(d, "Keywords: Race Factors; Death Certificates; Medical Record Linkage; Spatial Analysis; Infant Mortality; Vital Statistics; Brazil.")

# ================================================================= introduction
d.add_heading("Introduction", level=1)
para(d, "Mortality by race in Brazil is computed from two classifications made by different people. The numerator is the race on the death certificate. The Ministry of "
        f"Health instructs that it be asked of the person who informs on the deceased and never decided by the physician from observation {cite('manual_do2022')}; the system does "
        f"not record who gave the information {cite('romero2006')}, and in practice the physician or hospital staff often enter it {cite('travassos2004')}. The denominator is a declaration: the census respondent's, or, on the live birth record since the "
        f"form of 2011, the mother's declaration of her own race {cite('manual_dn2011')}. Rates computed from the two were shown to depend on the source {cite('chor2005', 'cardoso2005', 'caldas2017')}.")
para(d, f"Race is not one variable: self-identification and classification by an observer are distinct, though correlated {cite('roth2016')}. "
        f"In a Brazilian national survey, interviewers and respondents agreed on White, Brown or Black in 79% of cases, with agreement varying with "
        f"the racial composition of the place {cite('telles2002')}, and Brown people were reclassified as White more often in whiter cities {cite('muniz2017')}. "
        f"Parents do not simply transmit their race to their children {cite('schwartzman2007')}.")
para(d, f"What this does to mortality statistics has been measured where a second classification of the same person exists: United States certificates disagreed with survey reports "
        f"for American Indian decedents, whose death rates were understated {cite('sorlie1992', 'rosenberg1999', 'arias2016')}, and in São Paulo 17.3% of 1,012 older adults had on the "
        f"certificate a race other than the one they had reported {cite('santos2019')}. A cohort of 19.5 million Brazilian births linked to deaths, classified by the mother's race, "
        f"found higher mortality before age 5 among children of Indigenous, Black and Brown mothers {cite('reboucas2022')}. To our knowledge no study has compared, for the country, the race on the death certificate with the race on the birth record, or either with the race families assign to their children, and none asked where "
        "the two disagree.")
para(d, "Where matters because the composition of the population and the services that fill certificates vary across Brazil's municipalities. Three "
        "readings of the certificate make different predictions in space. Under the first, it transmits the mother's race, and the agreement should not depend "
        "on place. Under the second, it records what the family would answer about the child, and should follow the family's classification. Under the third, it reflects a "
        "classification made by whoever fills it: if that draws on the local population, it should move with the racial composition of the municipality; if it "
        "is an administrative practice, it should change at state borders and with the services that certify; if it follows social position, it should follow the wealth and "
        "schooling of the place and of the family.")
para(d, f"This study aimed {OBJECTIVE}.")

# ================================================================= methods
d.add_heading("Methods", level=1)
para(d, f"Design and reporting. This is a {DESIGN}, reported according to the REporting of studies Conducted using Observational Routinely-collected health Data (RECORD) "
        f"statement {cite('benchimol2015')}.")
para(d, f"Data sources. Death certificates came from the Mortality Information System (SIM) and live birth records from the Live Birth Information System (SINASC), in the "
        f"public files of the Ministry of Health {cite('datasus')}, read in November 2026: deaths of 2013 to 2024 and births of 2000 to 2023. The classification made by families came from "
        f"the sample of the 2010 Population Census {cite('ibge_microdata2010')} "
        f"({n0(CEN['records'])} records representing {n0(CEN['persons'])} people). Municipal boundaries were those of the 2022 mesh {cite('ibge_mesh2022')}; regions, state capitals and metropolitan regions "
        f"{cite('ibge_regions2017', 'ibge_metro')} were taken from the Brazilian Institute of "
        "Geography and Statistics (IBGE). All files are public and carry no names.")
para(d, "The three classifications. The categories are the five of the official classification: branca (White), preta (Black), parda (Brown), amarela (Yellow) and indígena "
        "(Indigenous); Yellow is not shown separately because of small numbers. "
        f"(1) Mother's declaration: the race field of the birth record became the mother's self-declared race with the form introduced in 2011 {cite('manual_dn2011')}; it "
        f"was filled on {pct(form[2010]['mother_field'])} of births in 2010 and {pct(form[2012]['mother_field'])} in "
        "2012 (Supplementary Table S1), so cohorts born from 2012 were taken to carry the mother's race. (2) Family's classification: the 2010 Census asks one resident to report the race of every member of the household and identifies each person's mother when she "
        f"lives in the household ({n0(CEN['pairs_records'])} pair records of children under 25); it concerns "
        "other children than those who died, a population reference applied by the mother's race, the child's age and the place. "
        "(3) Certificate: the race field of the death certificate (Figure 1).")
para(d, f"Linkage of infant deaths. Deaths before one year of age in 2013 to 2023 ({n0(I['certificates'])} certificates) were linked to birth records by a probabilistic linkage "
        f"{cite('fellegi1969')} on birth date, sex, municipality of residence of the mother, birth weight and mother's age, keeping one-to-one pairs. {n0(I['linked'])} "
        f"({pct(I['linked'] / I['certificates'])}) were linked and {n0(I['linked_with_race'])} had the mother's race on the birth record. The estimated share of false "
        "links was "
        f"{min(v['fdr_percent'] for v in I['link_quality'].values()):.2f}-{max(v['fdr_percent'] for v in I['link_quality'].values()):.2f}% a year, and on fields not used to "
        f"link the pairs agreed on delivery type in {min(v['validations']['delivery type agrees'] for v in I['link_quality'].values()):.0f}% or more (Supplementary Table S2). "
        f"The linked share was compared across certified race, size of municipality, region, year and age at death {cite('harron2017', 'doidge2019')}.")
para(d, "Study populations. (a) Infant deaths of 2013-2023, linked. (b) Children under 10 living with their mother in the 2010 Census sample. Deaths at 1-9 "
        "years are in Supplementary Text S1.")
para(d, "Variables of the death and of the birth. Age at death, sex, municipality of residence, year, underlying cause of death, the certifier (attending or substitute physician, "
        "medical examiner, death verification service, other), the place and the establishment of death, and the mother's schooling and age and the birth weight.")
para(d, "Variables of the municipality. Racial composition: the share of White mothers among the municipality's live births of 2012-2023. Socioeconomic context "
        f"{cite('ibge_pib', 'ibge_sidra2010')}, health services {cite('cnes')}, the municipality's own certification practice, quality of recording and place (state capital, "
        "metropolitan region, macro-region and state) are defined, with their sources and years, in Supplementary Table S3.")
para(d, "Measures. For each class of mother, the proportion of deaths certified in each race, and the proportion of children the family classified in each race.")
para(d, f"Analyses. (1) Smoothing: for each class of mother, the linked infant deaths certified in each race were modelled by municipality as binomial "
        f"counts with a Besag-York-Mollié effect in the BYM2 parametrisation on the queen contiguity of the 2022 mesh {cite('besag1991', 'riebler2016', 'simpson2017', 'rue2009')}; "
        f"the census children were modelled the same way. (2) Spatial structure: Moran's I of the empirical-Bayes standardised proportions and the local Moran "
        f"statistic, 999 permutations {cite('moran1950', 'assuncao1999', 'anselin1995')}. (3) Composition, state and context: binomial models of the municipal "
        "proportions with a spline of the logit share of White births, state effects and the municipal context (GDP per capita, illiteracy, low income, "
        "urbanisation, physicians, the shares of deaths certified by a verification service or a medical examiner, blank race), alone and together, with the "
        "deviance each block explains. (4) Borders: for pairs of neighbouring municipalities in different states, the difference of their empirical logits "
        f"regressed on the difference of their states' effects estimated from interior municipalities {cite('keele2015')}. (5) Individuals: logistic models of "
        f"each death (for example, a Brown mother's infant certified White) with a random intercept for the municipality and, crossed, one for the establishment "
        f"of death, entering composition, context and the death's own variables in sequence {cite('bates2015', 'merlo2006')}; and, for 2014-2018, a crossed "
        "model with the certifying physician. (6) Time: binomial mixed models of the yearly proportions in 133 intermediate regions with a random slope for "
        f"the year, and a municipality-year panel splitting each yearly variable into between and within parts {cite('mundlak1978')}, with the change between "
        f"the 2010 and 2022 Censuses as a second time point {cite('ibge_pib', 'ibge_sidra2010')}. Details are in Supplementary Text S2.")
para(d, "The family and the birth record against place. Two tests located the gradient with composition. (1) If the Brown category were not the same population "
        "everywhere, families in whiter municipalities would report the children of a Brown mother and a Brown father as White more often: in the 2010 Census sample "
        "(municipality held) the share of such children aged 0-9 reported White was related to the municipality's share of White births, with the child's age and sex "
        "and the mother's schooling held, errors clustered by municipality, and the family's gradient for all Brown mothers' children was split into the partner mix "
        "and the rate within couple type. (2) If the birth record bent toward the local majority, its share of White mothers would depart from the census along "
        "composition: by municipality, the share of White mothers on the birth records of 2012-2013 was regressed (binomial, on the logit scale) on the share White "
        "among the mothers of children aged 0-2 in the 2010 Census sample, and the birth records of 2021-2023 on the women aged 15-49 of the 2022 Census, nationally, "
        "within region and within state; a slope of 1 means the birth record follows the census up to a constant (fertility), a slope above 1 that it leans toward the "
        "local majority.")
para(d, "Statistical analysis. Proportions from the one-to-one linkage carry 95% confidence intervals (95%CI) from 400 bootstrap resamples of municipalities, because pairs "
        f"cluster by place; binomial intervals, {CBRANGE} times narrower, are in the supplement. For the candidate estimator, the variance of a difference of counts was "
        "taken as the sum of the two counts (Poisson), and its proportions exclude "
        "municipalities with 25,600 or more live births per year, where it lost precision (Results). Municipalities "
        "were grouped by thirds of GDP per capita and as state capitals, other members of metropolitan regions and the interior. Census "
        "standard errors are understated. Local Moran statistics are reported at p < 0.05 without "
        "correction for multiplicity. No hypothesis test was pre-registered, and the analyses by place and context are exploratory. Analyses used Python and R "
        f"(R-INLA {cite('lindgren2015')}, lme4, esda {cite('rey2010')}); the code accompanies the article.")
para(d, "Ethics. The study used only public, anonymised data and, under Resolution 510/2016 of the National Health Council, did not require review by a research ethics committee.")
