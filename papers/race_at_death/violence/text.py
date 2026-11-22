# The front of paper 5, violence: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py violence`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
import json as _json

VI = _json.loads((HERE / "results" / "violence.json").read_text(encoding="utf-8"))
DESIGN = "cross-sectional study of birth, hospital and death records related without identifiers"
OBJECTIVE = ("to measure whether the race on the death certificate of young people in Brazil depends on how they died, and whether a departure from their race "
             "at birth was already present in an earlier hospital record or arises at death")
Y = R["youth"]
YC = R["context"]["youth"]
KINDS = ["natural", "transport", "suicide", "other external", "other assault", "assault by firearm", "legal intervention"]
KL = {"natural": "natural causes", "transport": "transport accidents", "suicide": "suicide", "other external": "other external causes",
      "other assault": "assault by other means", "assault by firearm": "assault by firearm", "legal intervention": "legal intervention"}


def yc(kind, a="Branca", b="Branca", src=None):
    return cell((src or Y["by_kind"])[kind], a, b)


def hv(group, j, k, order="hospital"):
    """Earlier hospital record against the certificate: among admissions recorded j, the share certified k (order 'hospital'), or among deaths certified k,
    the share an earlier admission recorded j (order 'certified')."""
    key = f"hospital {j}|certified {k}" if order == "hospital" else f"certified {k}|hospital {j}"
    return VI[group]["cells"][key]


nat, fire, leg = yc("natural"), yc("assault by firearm"), yc("legal intervention")
# the claims of the text, held by the results
assert fire["est"] + 2 * fire["se"] < nat["est"] - 2 * nat["se"], "firearm deaths no longer certified White less often than natural deaths"
assert YC["standardised"]["assault"]["Branca"]["Branca"]["est"] < YC["standardised"]["natural"]["Branca"]["Branca"]["est"] - 0.1, "composition now explains the gap"
iml_a, iml_x = YC["by_certifier"]["assault"]["medical examiner"], YC["by_certifier"]["external, not assault"]["medical examiner"]
assert cell(iml_a, "Branca", "Branca")["est"] + 0.1 < cell(iml_x, "Branca", "Branca")["est"], "within medical examiners the gap is gone"

d = new_doc()
TITLE = "Who becomes Brown when killed: the race of young people at birth, in hospital and on the death certificate by cause of death, Brazil, 2015-2024"
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}, Brazil. Deaths at 15-24 years in 2015-2024 of people born in 2000-2009 were related to the live births "
        "and to the earlier hospital admissions with the same birth date, sex and municipality of residence, with records of the other sex as a control for chance "
        "agreement, in municipalities with fewer than 1,600 births a year. The race recorded at birth (by staff, before the 2011 form) and at an earlier admission "
        "was cross-classified with the certified race, by cause of death.")
hw_n, hw_f = hv("natural", "white", "white"), hv("assault by firearm", "white", "white")
assert 0.4 < hv("assault by firearm", "white", "brown")["est"] < 0.6 and 0.12 < hv("natural", "white", "brown")["est"] < 0.21, "half and a sixth no longer hold"
para(d, f"Results: Of young people recorded White at birth, {cc(nat)} were certified White after a natural death, {cc(fire)} after an assault by firearm and "
        f"{cc(leg)} after a legal intervention; the gap held at equal municipal composition, in every region and within deaths certified by medical examiners. "
        f"Of those an earlier hospital admission had recorded White, {cc(hw_n)} were certified White after a natural death and {cc(hw_f)} after a firearm "
        f"assault. The deceased was found among the candidates in {pct(min(Y['by_kind'][k]['found'] for k in KINDS), 0)}-{pct(max(Y['by_kind'][k]['found'] for k in KINDS), 0)} "
        "of deaths, alike for every cause.")
para(d, "Conclusion: In the smaller Brazilian municipalities, young people killed by assault are certified darker than they were recorded at birth and in "
        "hospital during life; the departure arises at death, and part of the racial gap in homicide rates is made by the certificate. The large cities, where "
        "most homicides occur, require identified linkage.")
para(d, "Keywords: Homicide; Violence; Racial Groups; Death Certificates; Young Adult; Brazil.")

d.add_heading("Introduction", level=1)
para(d, f"Black and Brown young people die by homicide far more often than White ones in Brazil {cite('soaresfilho2011', 'cerqueira2014')}. These rates take "
        "the victim's race from the death certificate, completed for violent deaths by the medical examiner of a medico-legal institute, who in most cases has "
        f"never seen the person alive {cite('cfm1779')}. Race is also a status marker that observers read from circumstances: people incarcerated or poor are "
        f"seen as darker {cite('saperstein2010', 'penner2008')}, and on United States certificates the race recorded depended on the cause of death "
        f"{cite('noymer2011')}. If certifiers record young people killed by firearms as Brown more often than they would the same people dying of other causes, "
        "part of the racial gap in homicide is made at death. If instead the young people who are killed were already recorded as Brown before they died, the "
        "certificate reports a classification made in life.")
para(d, "The two readings predict different things about a record made before death. Public Brazilian files carry no identifier, but deaths, births and "
        "hospital admissions share the birth date, sex and municipality of residence, which in smaller municipalities relate a death to its own birth and "
        "admissions with a measurable rate of chance agreement. We know of no study that compared the race of the same young people at birth, in hospital "
        f"and at death by cause. This study aimed {OBJECTIVE}.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the RECORD statement {cite('benchimol2015')}. Deaths came from the Mortality Information "
        f"System (SIM), births from the Live Birth Information System (SINASC) and admissions from the Hospital Information System (SIH) of the Unified Health "
        f"System {cite('datasus')}.")
para(d, "Population. Deaths at 15-24 years in 2015-2024 of people born in 2000-2009, residents of municipalities with fewer than 1,600 live births a year on "
        "average in 2000-2009, where a birth date, sex and municipality are shared by few other people. Causes (underlying cause, ICD-10): natural (A00-R99); "
        "transport accidents (V01-V99); suicide (X60-X84); assault by firearm (X93-X95); assault by other means (X85-Y09 otherwise); legal intervention "
        "(Y35-Y36); other external causes.")
para(d, "Race at birth and certified race. For each death, the live births of 2000-2009 with the same birth date, sex and municipality of residence are its "
        "candidates; the deceased is among them unless the family moved. The births of the other sex on the same day and in the same municipality cannot "
        "contain the deceased and estimate the chance candidates; their count, scaled by the ratio of births of the two sexes, was subtracted from the candidates "
        "by race at birth and certified race, which estimates the cross-classification of the deaths found (Supplementary Text S1; validated against "
        "one-to-one linkage in infants, where it holds below 25,600 births a year). Before 2011 the birth record carried the newborn's colour as recorded by "
        "staff, not the mother's declaration. Proportions are of deaths recorded in a race at birth.")
para(d, "Race at an earlier admission. The same design related each death to the SIH admissions of 2010-2024 of people born in 2000-2009 with its birth date, "
        "sex and municipality that ended at least 30 days before the death and not in death, with the admissions of the other sex, scaled by the ratio of the two "
        "sexes' admissions in the municipality and birth year, as the control. The hospital's race (White, Black, Brown) was cross-classified with the certified "
        "race; intervals came from a bootstrap over municipalities.")
para(d, "Analysis. Cross-classifications were compared between causes, within strata of the certifier (attending physician, medical examiner, death "
        "verification service), the place of death, the mother's schooling at birth and the municipality's composition, and standardised to the composition of "
        "natural deaths. Standard errors of the candidate estimates are those of a difference of counts (Poisson); they omit the variance of the denominator. "
        "Analyses used Python 3.11; the code accompanies the article. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council "
        "no review was required.")
