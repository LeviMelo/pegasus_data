# The front of paper 3, the Black category: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py black_category`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
import json as _json

BK = _json.loads((HERE / "results" / "black.json").read_text(encoding="utf-8"))
DESIGN = "cross-sectional study of linked birth, hospital and death records and of census microdata"
OBJECTIVE = ("to measure how often the Black category is used for children of Black mothers on Brazilian death certificates, set it against how families, "
             "hospitals and certificates classify Black people at other moments, and find by whom, where and when it is used")
I, CEN, CH = R["infants"], R["census"], R["children"]
IL = I["linkage"]["rows"]["Preta"]
CB = I["cluster_bootstrap"]
LD, HO, IN, FM, FL = BK["ladder"], BK["hospital"], BK["individual"], BK["facility_model"], BK["facility_level"]
PK, MO, ML = SP["panel"]["KK"], SP["moran"]["KK"], SP["multilevel"]["black_black"]
FX = ML["full_fit"]["fixed"]
EST = ML["establishment"]
slopes = {"North": PK["by_macro"]["yc"]["Estimate"]} | {rn: PK["by_macro"]["yc"]["Estimate"] + PK["by_macro"][f"yc:macro{rn}"]["Estimate"]
                                                       for rn in ("Northeast", "Southeast", "South", "Centre-West")}
lo_r, hi_r = min(slopes, key=slopes.get), max(slopes, key=slopes.get)


def orx(term):
    e_, s_ = FX[term]["est"], FX[term]["se"]
    return f"{math.exp(e_):.2f} (95%CI {math.exp(e_ - 1.96 * s_):.2f}; {math.exp(e_ + 1.96 * s_):.2f})"


def cbci(key):
    """A proportion of the linkage with its interval from the bootstrap over municipalities."""
    return ci(CB[key])


by_h = IN["black_mother_by_hospital"]
NT0 = BK["net"]
DL = BK["delivery_link"]
# the claims of the text, held by the results
assert CB["Preta>Preta"]["est"] < 0.5 * LD["family_child_0"], "the certificate's Black share is no longer under half the family's"
assert CB["Preta>Parda"]["est"] > 0.5, "Black mothers' infants are no longer mostly certified Brown"
assert HO["matrix"]["black"]["black"]["est"] < 0.6, "hospitals now record most Black mothers as Black"
assert LD["certificate_adult_women"]["est"] > 2 * CB["Preta>Preta"]["est"], "adult women no longer far above infants"
assert PK["fixed"]["yc"]["Estimate"] - 1.96 * PK["fixed"]["yc"]["Std. Error"] > 0, "no longer rising"

d = new_doc()
TITLE = ("Black children recorded as Brown: the Black category on the death certificates of children of Black mothers, against the family, the hospital and the "
         "certificates of adults, Brazil, 2013-2023")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)

d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}, Brazil. Infant deaths of 2013-2023 were linked to their birth records (the mother's declaration of her own race) "
        "and the birth records to the mothers' delivery admissions (the hospital's record of the mother); the family's classification of children came from the 2010 "
        "Census. The certificate's category was related to the hospital's record of the same mother within hospitals, to each delivery hospital's practice by "
        "logistic regression with clustered errors, and to the certifier, the child and the place by multilevel logistic regression, in space and over time.")
para(d, f"Results: Of infants of mothers who declared themselves Black, {cbci('Preta>Preta')} were certified Black, {cbci('Preta>Parda')} Brown and "
        f"{cbci('Preta>Branca')} White; counted net, certificates recorded {f2(NT0['certificate_ratio'])} as many Black infants as there were infants of Black mothers. "
        f"Hospitals recorded Black mothers as Black at delivery in {ci(HO['black_bootstrap']['black'])} of admissions with a race (net ratio "
        f"{f2(NT0['hospital_ratio'])}). Within the same hospital, an infant whose mother the hospital had recorded as Black had {f2(IN['within_hospital_or']['est'])} "
        f"(95%CI {f2(IN['within_hospital_or']['lo'])}; {f2(IN['within_hospital_or']['hi'])}) times the odds of being certified Black, and the delivery hospital's "
        f"practice predicted the certificate at equal composition, region and year. The category was used more for children of 1-4 "
        f"({f2(LD['certificate_1_4']['est'])}) and 5-9 years ({f2(LD['certificate_5_9']['est'])}) than for infants in the same municipalities "
        f"({f2(LD['certificate_infant_below_25600']['est'])}), less by verification services and medical examiners, and it rose from "
        f"{f2(cell(I['by_year']['2013'], 'Preta', 'Preta')['est'])} in 2013 to {f2(cell(I['by_year']['2023'], 'Preta', 'Preta')['est'])} in 2023, faster than in the "
        "hospital.")
para(d, "Conclusion: Black families are recorded as Brown more often than as Black in Brazil's health records, and the infant certificate undercounts Black infants "
        "by about two thirds even net. The certificate follows the hospital's record of the same mother, and the category's use varies with the institution, the "
        "certifier and the place, so statistics of the Black population built from these records undercount it unevenly across the country.")
para(d, "Keywords: Race Factors; Racial Groups; Death Certificates; Hospital Records; Medical Record Linkage; Infant Mortality; Brazil.")

# ================================================================= introduction
d.add_heading("Introduction", level=1)
para(d, "Brazil classifies its population in five categories of colour or race, and the boundary between two of them, preto (Black) and pardo (Brown), is where "
        f"classification is least stable. Interviewers and respondents agree least at the darker end of the colour continuum {cite('telles2002')}; the same person "
        f"moves between categories across surveys, in both directions {cite('muniz2022')}; people choose other terms than the census's according to education, "
        f"colour and the local population {cite('bailey2006')}; and skin colour carries inequalities that the census categories do not capture "
        f"{cite('monk2016', 'perreira2014')}. Black and Brown people also differ in the discrimination they report, and Brown people differ among themselves by "
        f"status {cite('daflon2017')}. Statistics and policy nonetheless often group Black and Brown as negros, and the verification commissions of "
        f"affirmative action now decide by observation who belongs to the category {cite('silva2024')}. Since 2010, Brazilians, especially those of darker skin, have "
        f"increasingly identified as Black {cite('freemannc2024')}.")
para(d, "Health records add classifications made by others. The Ministry of Health instructs that the race on the death certificate be asked of the informant "
        f"{cite('manual_do2022')}, but in practice the certifier or hospital staff often enter it {cite('travassos2004')}; the hospital records the race of its patients "
        "on the admission; and since 2011 the live birth record carries the mother's declaration of her own race. How the Black category moves between these records "
        f"matters for statistics: a change in how race was recorded on birth records in 2012 changed infant mortality by race without any change in deaths "
        f"{cite('caldas2022')}, and infant mortality by race estimated from the records was underestimated, most for Brown children {cite('cardoso2005')}. We know "
        "of no study that followed the Black category through the records of the same families: the mother's declaration, the hospital's record of the mother, the "
        "certificate of her child.")
para(d, f"This study aimed {OBJECTIVE}.")

# ================================================================= methods
d.add_heading("Methods", level=1)
para(d, f"Design. This is a {DESIGN}, reported according to the RECORD statement {cite('benchimol2015')}. Deaths came from the Mortality Information System (SIM), "
        f"live births from the Live Birth Information System (SINASC) and delivery admissions from the Hospital Information System (SIH), public files of the Ministry of "
        f"Health {cite('datasus')}; the family's classification from the sample of the 2010 Census {cite('ibge_microdata2010')}. All files carry no names; records were "
        "related through the variables they share.")
para(d, f"Records of the same families. (1) Infant deaths of 2013-2023 were linked one-to-one to their birth records by probabilistic linkage {cite('fellegi1969')} "
        f"on birth date, sex, residence, birth weight and mother's age ({pct(I['linked'] / I['certificates'])} linked; estimated false links "
        f"{min(v['fdr_percent'] for v in I['link_quality'].values()):.2f}-{max(v['fdr_percent'] for v in I['link_quality'].values()):.2f}% a year); the birth record gives "
        "the mother's declaration of her own race. (2) Each birth record of 2012-2023 was linked to the mother's delivery admission in a hospital of the Unified Health "
        "System by the mother's birth date, the hospital and the day of birth within the admission, which gives the race the hospital recorded for the mother herself "
        f"({min(v['linked_share'] for v in DL.values()):.2f}-{max(v['linked_share'] for v in DL.values()):.2f} of births linked a year, about the public system's share "
        f"of deliveries; estimated false links {min(v['fdr_percent'] for v in DL.values()):.2f}-{max(v['fdr_percent'] for v in DL.values()):.2f}%; an obstetric "
        f"diagnosis on {min(v['obstetric'] for v in DL.values()):.1f}-{max(v['obstetric'] for v in DL.values()):.1f}% and the same municipality of residence on "
        f"{min(v['residence'] for v in DL.values()):.1f}-{max(v['residence'] for v in DL.values()):.1f}% of linked admissions); hospitals that recorded over a tenth of "
        f"their patients as Yellow (Asian) were left out as writing a default ({HO['facilities_left_out']} hospitals), from all analyses. (3) The "
        "family's classification is the race a household reported for a child under 10 against the race it reported for the child's mother, in the 2010 Census sample; "
        "it concerns other children than those who died. (4) For adult women, deaths at 15-49 years in hospital in 2015-2022 were related to the birth records on "
        "which they were mothers and to the admission that ended in death (exploratory; Supplementary Text S1). After infancy, deaths at 1-9 years were related to the "
        "births of the same birth date, sex and municipality, with births of the other sex as a control for chance agreement (Supplementary Text S2).")
para(d, "Measures. For people who declared themselves Black, or whose mothers did: the proportion recorded Black by each record, and the categories used instead. For "
        "linked infant deaths of Black mothers, the certificate's category by the race the hospital recorded for the same mother at the delivery. For each hospital with "
        "30 or more Black mothers, the share of them it recorded as Black over 2012-2023, its practice, set against the certificates of Black mothers' infants delivered "
        "in it. Gross shares were complemented by net counts: the number each record called Black against the number who declared themselves Black. The primary "
        "analyses were the infant certificate against the mother's declaration and against the hospital's record of the same mother; the others are exploratory.")
para(d, f"Analysis. Proportions from the linkage carry 95% confidence intervals (95%CI) from a bootstrap over municipalities, those of the hospital from a bootstrap "
        "over hospitals. The hospital's record of the mother was related to the certificate within delivery hospitals by a Mantel-Haenszel odds ratio. The use of the Black category on "
        f"infant certificates was modelled by logistic regression with a random intercept for the municipality {cite('bates2015')}, with the municipality's racial "
        "composition (a natural spline with three degrees of freedom on the logit of the White share), standardised socioeconomic context and health services, the "
        "certifier, the place and age at death, the cause, the mother's schooling and age, the birth weight, the region and the year per decade (fitted with nAGQ = 0), "
        f"and with a crossed random intercept for the establishment of death; spatial structure by Moran's I {cite('moran1950', 'assuncao1999')} and Besag-York-Mollié "
        f"models with penalised-complexity priors {cite('riebler2016', 'rue2009')}; change over 2013-2023 by binomial mixed models with random intercepts and slopes "
        "for 133 intermediate regions, the hospital's change by a quasi-binomial model of yearly counts. The delivery hospital's practice, as the logit of its share "
        "(with 0.01 added to both counts' shares), entered a logistic model of the certificate, with errors clustered by municipality, alone and with composition (a "
        "spline with three degrees of freedom), region and year; the hospital is dated by the birth, the certificate by the death. Analyses used Python 3.11 and R 4.4; the code accompanies the "
        "article. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council no review was required.")
