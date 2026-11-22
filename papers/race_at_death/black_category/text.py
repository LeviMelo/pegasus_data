# The front of paper 3, the Black category: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py black_category`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
import json as _json

BK = _json.loads((HERE / "results" / "black.json").read_text(encoding="utf-8"))
MC = _json.loads((HERE / "results" / "mechanism.json").read_text(encoding="utf-8"))
MB = MC["black"]
R3 = MC["review3"]
_MVT = MC["movers"]


def _odds(p):
    return p / (1 - p)


OR_SAME = _odds(_MVT["hospital_black_again|same hospital"]["est"]) / _odds(_MVT["hospital_black_after_not|same hospital"]["est"])
OR_OTHER = _odds(_MVT["hospital_black_again|another hospital"]["est"]) / _odds(_MVT["hospital_black_after_not|another hospital"]["est"])
DESIGN = "cross-sectional study of linked birth, hospital and death records and of census microdata"
OBJECTIVE = ("to measure how often the infants of mothers who declared themselves Black are recorded as Black on Brazilian death certificates, set it "
             "against the hospital's record of the same mothers, and test whether the category follows the person, the hospital that records her or the "
             "certifier")
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


def ci3(x):
    """An odds ratio with its interval, from a dict with or_per_sd, lo and hi."""
    return f"{x['or_per_sd']:.2f} (95%CI {x['lo']:.2f}; {x['hi']:.2f})"


def cbci(key):
    """A proportion of the linkage with its interval from the bootstrap over municipalities."""
    return ci(CB[key])


by_h = IN["black_mother_by_hospital"]
HD = _json.loads((HERE / "results" / "hospital_declaration.json").read_text(encoding="utf-8"))
AGAIN = _MVT["declared_again|black"]
AG_S, AG_O = _MVT["declared_again|black|same establishment"], _MVT["declared_again|black|another establishment"]
AGW_S, AGW_O = _MVT["declared_again|white|same establishment"], _MVT["declared_again|white|another establishment"]
AGB_S, AGB_O = _MVT["declared_again|brown|same establishment"], _MVT["declared_again|brown|another establishment"]
AG_GAP = AG_S["est"] - AG_O["est"]
assert AG_S["est"] < 0.7, "the declaration now repeats in the same establishment: rewrite 'most of its instability is the mother's'"
assert LD["certificate_infant"]["est"] < 0.5 * LD["family_child_0"] and HO["black_bootstrap"]["black"]["est"] < AGAIN["est"], "the four levels changed order"
_hf = HD["by_practice_fifth"]
assert _hf[0]["dn_black"] < 0.6 * _hf[0]["expected_black"] and _hf[-1]["dn_black"] > 0.9 * _hf[-1]["expected_black"], "the birth record's shortfall by practice changed"
assert abs(HD["oe_black"]["state"]["slope"]) < 2 * HD["oe_black"]["state"]["se"] + 0.01, "within states the shortfall now follows the hospital's practice"
_ps = HD["practice_by_state"]
PS_LO, PS_HI = min(_ps, key=lambda k: _ps[k]["est"]), max(_ps, key=lambda k: _ps[k]["est"])
NT0 = BK["net"]
DL = BK["delivery_link"]
# the claims of the text, held by the results
assert CB["Preta>Preta"]["est"] < 0.5 * LD["family_child_0"], "the certificate's Black share is no longer under half the family's"
assert CB["Preta>Parda"]["est"] > 0.5, "Black mothers' infants are no longer mostly certified Brown"
assert HO["matrix"]["black"]["black"]["est"] < 0.6, "hospitals now record most Black mothers as Black"
assert PK["fixed"]["yc"]["Estimate"] - 1.96 * PK["fixed"]["yc"]["Std. Error"] > 0, "no longer rising"

d = new_doc()
TITLE = ("Infants of Black mothers recorded as Brown: the Black category from the birth record to the delivery admission and the death certificate, Brazil, "
         "2012-2023")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)

d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
CLAIM = ["the four levels", "most of its instability is the mother's"]
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}, Brazil. Infant deaths of 2013-2023 were linked to their birth records and the births to the "
        "mothers' delivery admissions; mothers with two births were related by birth date and municipality. Each record of "
        "a Black mother or her child was set against its own comparator, and the certificate against the hospital's record within hospitals.")
para(d, f"Results: At four levels, the share recorded Black was {ci(AGAIN)} for a mother declaring herself Black again at her next birth, "
        f"{f2(LD['family_child_0'])} for such mothers' infants as households reported them, {ci(HO['black_bootstrap']['black'])} for the mother in the hospital's admission "
        f"and {ci(LD['certificate_infant'])} for her infant on the certificate. The mother's declaration repeated in {ci(AG_S)} of cases in the "
        f"same establishment and {ci(AG_O)} in another. Within the same delivery hospital, an infant whose mother the hospital had recorded Black had "
        f"{f2(MB['clogit_delivery_hospital_adjusted']['or'])} times the odds of being certified Black, also after dying elsewhere "
        f"({f2(MB['clogit_death_estab_elsewhere']['or'])}).")
para(d, "Conclusion: Against the right comparator for each record, the four levels fall from the mother's own repeated declaration to the certificate, which records the infant of a Black mother as Black less than half "
        "as often as families report such children; the declaration "
        + ("itself repeated only somewhat more in the same establishment, so most of its instability is the mother's." if AG_GAP > 0.05 else "itself repeats alike in the same or another establishment, so its instability is the mother's.")
        + " The certificate follows the hospital's record of the mother.")
para(d, "Keywords: Race Factors; Racial Groups; Death Certificates; Hospital Records; Medical Record Linkage; Infant Mortality; Brazil.")

# ================================================================= introduction
d.add_heading("Introduction", level=1)
para(d, "Brazil classifies its population in five categories of colour or race, and the boundary between two of them, preto (Black) and pardo (Brown), is where "
        f"classification is least stable. Interviewers and respondents agree least at the darker end of the colour continuum {cite('telles2002')}; the same person "
        f"moves between categories across surveys, in both directions {cite('muniz2022')}; people choose other terms than the census's according to education, "
        f"colour and the local population {cite('bailey2006')}; and skin colour carries inequalities that the census categories do not capture "
        f"{cite('monk2016', 'perreira2014')}. Black and Brown people also differ in the discrimination they report, and Brown people differ among themselves by "
        f"status {cite('daflon2017')}. Statistics and policy nonetheless often group Black and Brown as negros. Since 2010, Brazilians, especially those of darker skin, have "
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
        "which they were mothers and to the admission that ended in death (exploratory; Supplementary Text S1, Supplementary Table S1). After infancy, deaths at 1-9 years were related to the "
        "births of the same birth date, sex and municipality, with births of the other sex as a control for chance agreement (Supplementary Text S2). Figure 1 shows the records and what each comparison holds fixed.")
figure(d, "flow_black", "Figure 1 - Records of the same families and the comparisons that separate the person, the hospital's chart and the hospital, Brazil, "
                          "2012-2023", ["SINASC: Live Birth Information System. SIH: Hospital Information System. SIM: Mortality Information System. "
                                        "Counts are of records with a race."])
para(d, "Measures. For infants of mothers who declared themselves Black, the proportion certified Black, and the categories used instead; for their mothers, "
        "the proportion the delivery admission recorded Black. Gross shares were complemented by net counts: the number each record called Black against the "
        "number of mothers who declared themselves Black, which counts Brown mothers recorded Black against Black mothers recorded otherwise. The mother's "
        "declaration is the reference; it is entered on the birth record by staff on her answer, and its dependence on who filled it (physician, nursing, other "
        "staff) was examined within hospitals. The primary analyses were the infant certificate against the mother's declaration and against the hospital's "
        "record of the same mother; the others are exploratory.")
para(d, f"Analysis. Proportions from the linkage carry 95% confidence intervals (95%CI) from a bootstrap over municipalities, those of the hospital and the "
        "net ratios from bootstraps over hospitals and municipalities. Person against place: the hospital's record of the mother was related to the certificate "
        "within delivery hospitals (Mantel-Haenszel, with the Breslow-Day test of heterogeneity, and conditional logistic regression with the mother's schooling "
        "and age, low birth weight, the year and the infant's age at death); and, to separate copying from the delivery chart, within the establishments of death "
        "of infants who died where they were delivered and of those who died elsewhere. The hospital's practice was its share of Black mothers recorded Black over "
        "2012-2023 without the infant's own mother, shrunk by a beta prior fitted to the hospitals, entered as a logit in logistic models of the certificate with "
        "errors clustered by hospital, alone, with composition (a spline with three degrees of freedom), region and year, and beside the hospital's record of the "
        f"mother. The certifier: crossed random intercepts for the certifying physician, the establishment of death and the municipality {cite('bates2015')} "
        "(Laplace approximation; physicians identified by state and registration, filed in 2014-2018). Time: the yearly proportion standardised to the region, "
        "schooling and age of the Black mothers of 2013, and the hospital's record and the certificate of the same infants in one logistic model with a "
        "record-by-year interaction and errors clustered by infant. The same mothers across births: births with the same mother's birth date and municipality of "
        "residence in two years and a higher parity, in municipalities with fewer than 1,600 births a year, with the mother's birth date moved by one day as a "
        "control for chance pairs. Analyses used Python 3.11 and R 4.4; the code accompanies the article. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council no review was required.")
