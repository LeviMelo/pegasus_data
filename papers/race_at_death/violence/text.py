# The front of paper 5, violence: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py violence`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
import json as _json

VI = _json.loads((HERE / "results" / "violence.json").read_text(encoding="utf-8"))
DESIGN = "cross-sectional study of birth, hospital and death records related without identifiers"
OBJECTIVE = ("to measure whether the race recorded for young people in Brazil departs from their race at birth according to how they died, and at "
             "which record, in life or at death, the departure arises")
Y = R["youth"]
YC = R["context"]["youth"]
KINDS = ["natural", "transport", "suicide", "other external", "other assault", "assault by firearm", "legal intervention"]
KL = {"natural": "natural causes", "transport": "transport accidents", "suicide": "suicide", "other external": "other external causes",
      "other assault": "assault by other means", "assault by firearm": "assault by firearm", "legal intervention": "legal intervention"}


def yc(kind, a="Branca", b="Branca", src=None):
    return cell((src or Y["by_kind"])[kind], a, b)


def hv(group, j, k, order="hospital", key="person"):
    """Earlier hospital record against the certificate (one per person): among people recorded j, the share certified k (order 'hospital'), or among
    deaths certified k, the share an earlier admission recorded j (order 'certified')."""
    c = f"hospital {j}|certified {k}" if order == "hospital" else f"certified {k}|hospital {j}"
    return VI[key][group]["cells"][c]


def margin(kind):
    """White at birth and on the certificate among the deaths found among their birth candidates (the same deaths)."""
    m = Y["by_kind"][kind]
    mix = {a: (v["est"] if isinstance(v, dict) else v) for a, v in m["declared_mix"].items()}
    cert = sum(mix[a] * m["rows"][a]["Branca"]["est"] for a in mix if a in m["rows"] and "Branca" in m["rows"][a])
    return mix["Branca"], cert


nat, fire, leg = yc("natural"), yc("assault by firearm"), yc("legal intervention")
BC, TR = VI["birth_cert"], VI["three_records"]
PM = {g: VI["person"][g]["margins"] for g in VI["person"]}
TM = {g: VI["terminal"][g]["margins"] for g in VI["terminal"]}
EXT = ("transport", "suicide", "other external", "assault by firearm", "other assault")


def dd(a, b, key="net_shift", src=None):
    """The difference of a group's change from natural deaths' change, with its standard error (independent bootstrap errors)."""
    src = src or BC
    x, y = src[a][key], src[b][key]
    return {"est": x["est"] - y["est"], "se": (x["se"] ** 2 + y["se"] ** 2) ** 0.5}


def ddc(x):
    return f"{100 * x['est']:+.1f} percentage points (95%CI {100 * (x['est'] - 1.96 * x['se']):+.1f}; {100 * (x['est'] + 1.96 * x['se']):+.1f})"


P_ASS, P_EXT = dd("all assault", "natural"), dd("all external, not assault", "natural")
H_ASS = dd("all assault", "natural", "hospital_white->certified_white", TR)
B_ASS = dd("all assault", "natural", "birth_white->hospital_white", TR)
PLS = {g: sum(VI["placebo_shifts"][k][g] for k in VI["placebo_shifts"]) / len(VI["placebo_shifts"]) / max(VI["person"][g]["n_est"], 1)
       for g in ("natural", "assault by firearm")}
# the claims of the text, held by the results
assert all(BC[k]["net_shift"]["est"] < BC["natural"]["net_shift"]["est"] - 0.05 for k in ("transport", "suicide", "assault by firearm", "other assault")), \
    "external causes no longer lose more White from birth to the certificate than natural deaths"
assert abs(P_ASS["est"] - P_EXT["est"]) < 0.03, "assaults now differ from the other external causes"
assert abs(B_ASS["est"]) < 2 * B_ASS["se"] + 0.01, "birth to hospital now differs between assault and natural deaths"
assert H_ASS["est"] + 1.96 * H_ASS["se"] < 0, "hospital to certificate no longer differs between assault and natural deaths"
assert TR["natural"]["hospital_white->certified_white"]["est"] > 0 > TR["all assault"]["hospital_white->certified_white"]["est"]
assert all(TM[g]["certified_white"]["est"] > TM[g]["hospital_white"]["est"] for g in ("natural", "transport", "assault by firearm")), \
    "the certificate is no longer lighter than the record of the dying admission"
assert PLS["assault by firearm"] > 0.05 > 0 > PLS["natural"], "the placebo residuals changed sign or size"
iml_a, iml_x = YC["by_certifier"]["assault"]["medical examiner"], YC["by_certifier"]["external, not assault"]["medical examiner"]

d = new_doc()
TITLE = ("Where the race of young people who die violently changes: the same deaths at birth, in hospital and on the death certificate, Brazil, "
         "2015-2024")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}, Brazil. Deaths at 15-24 years in 2015-2024 of people born in 2000-2009, in municipalities with fewer than "
        "1,600 births a year, were related to the live births and to the earlier hospital admissions with the same birth date, sex and municipality of "
        "residence, with records of the other sex as a control for chance agreement. The share recorded White at birth (by staff), at an earlier admission and on "
        "the certificate was compared by cause of death, for the same deaths; the primary contrast was the change from birth to the certificate in external "
        "causes against natural causes.")
para(d, f"Results: Among {n0(sum(VI['deaths_total'][k] for k in ('natural', 'transport', 'suicide', 'other external', 'undetermined intent', 'assault by firearm', 'other assault', 'legal intervention')))} "
        f"deaths, about half were found among their birth candidates. From birth to the certificate the share White changed by "
        f"{100 * BC['natural']['net_shift']['est']:+.0f} percentage points for natural deaths and by "
        f"{100 * max(BC[k]['net_shift']['est'] for k in EXT):+.0f} to {100 * min(BC[k]['net_shift']['est'] for k in EXT):+.0f} for the external causes; the "
        f"difference was {ddc(P_ASS)} for assaults and {ddc(P_EXT)} for the other external causes. For the same deaths with an earlier admission, the share "
        f"White fell from birth to the hospital record by about {100 * -TR['natural']['birth_white->hospital_white']['est']:.0f} points whatever the cause, and "
        f"from the hospital record to the certificate it changed by {100 * TR['natural']['hospital_white->certified_white']['est']:+.0f} points for natural "
        f"deaths and {100 * TR['all assault']['hospital_white->certified_white']['est']:+.0f} for assaults ({ddc(H_ASS)}).")
para(d, "Conclusion: In the smaller Brazilian municipalities, young people who died of external causes, assaults no more than the others, were certified White "
        "less often than they were recorded at birth. The difference from natural deaths arose after the last hospital record, on the certificate, while the "
        "change from birth to hospital was the same for every cause. The large cities, where most homicides occur, require identified linkage.")
para(d, "Keywords: Homicide; Violence; Racial Groups; Death Certificates; Young Adult; Brazil.")

d.add_heading("Introduction", level=1)
para(d, f"Black and Brown young people die by homicide far more often than White ones in Brazil {cite('soaresfilho2011', 'cerqueira2014')}. These rates take "
        "the victim's race from the death certificate, which for violent deaths is often completed by the medical examiner of a medico-legal institute, who "
        f"has not seen the person alive and records race from the body or from whoever informs it {cite('cfm1779')}. Race is also a status marker that observers read from circumstances: people incarcerated or poor are "
        f"seen as darker {cite('saperstein2010', 'penner2008')}, and on United States certificates the race recorded depended on the cause of death "
        f"{cite('noymer2011')}. If certifiers record young people killed by firearms as Brown more often than they would the same people dying of other causes, "
        "part of the racial gap in homicide is made at death. If instead the young people who are killed were already recorded as Brown before they died, the "
        "certificate reports a classification made in life.")
para(d, "The two readings predict different things about a record made before death. Public Brazilian files carry no identifier, but deaths, births and "
        "hospital admissions share the birth date, sex and municipality of residence, which in smaller municipalities relate a death to its own birth and "
        "admissions with a measurable rate of chance agreement. We found no study that compared the race of the same young people at birth, in hospital "
        f"and at death by cause. This study aimed {OBJECTIVE}.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the RECORD statement {cite('benchimol2015')}. Deaths came from the Mortality Information "
        f"System (SIM), births from the Live Birth Information System (SINASC) and admissions from the Hospital Information System (SIH) of the Unified Health "
        f"System {cite('datasus')}.")
para(d, "Population. Deaths at 15-24 years in 2015-2024 of people born in 2000-2009, residents of municipalities with fewer than 1,600 live births a year on "
        "average in 2000-2009, where a birth date, sex and municipality are shared by few other people. Causes (underlying cause, ICD-10): natural (A00-R99); "
        "transport accidents (V01-V99); suicide (X60-X84); assault by firearm (X93-X95); assault by other means (X85-Y09 otherwise); legal intervention "
        "(Y35-Y36); events of undetermined intent (Y10-Y34); other external causes, including injury codes (S, T) filed as underlying causes. Municipalities "
        "are those with fewer than 1,600 births a year in 2000-2009 for every comparison except the strata of Figure 3, which come from a tabulation that "
        "classes them by their births of 2012-2023.")
para(d, "Race at birth and certified race. For each death, the live births of 2000-2009 with the same birth date, sex and municipality of residence are its "
        "candidates; the deceased is among them unless the family moved. The births of the other sex on the same day and in the same municipality cannot "
        "contain the deceased and estimate the chance candidates; their count, scaled by the ratio of births of the two sexes, was subtracted from the candidates "
        "by race at birth and certified race, which estimates the cross-classification of the deaths found (Supplementary Text S1; validated against "
        "one-to-one linkage in infants, where it holds below 25,600 births a year). Before 2011 the birth record carried the newborn's colour as recorded by "
        "staff, not the mother's declaration. Proportions are of deaths recorded in a race at birth.")
para(d, "Race at an earlier admission. The same design related each death to the SIH admissions of 2010-2024 of people born in 2000-2009 with its birth date, "
        "sex and municipality that ended at least 30 days before the death and not in death, with the admissions of the other sex, scaled by the ratio of the two "
        "sexes' admissions in the municipality and birth year, as the control. The hospital's race (White, Black, Brown) was cross-classified with the certified "
        "race; intervals came from a bootstrap over municipalities (Figure 1).")
figure(d, "flow_violence", "Figure 1 - Deaths at 15-24 years related to the live births and the hospital admissions of the same birth date, sex and "
                           "municipality, with the other sex as control, Brazil, births of 2000-2009, admissions of 2010-2024, deaths of 2015-2024",
       ["SINASC: Live Birth Information System. SIM: Mortality Information System. SIH: Hospital Information System. Municipalities with fewer than "
        "1,600 live births a year."])
para(d, "Analysis. Cross-classifications were compared between causes, within strata of the certifier (attending physician, medical examiner, death "
        "verification service), the place of death, the mother's schooling at birth and the municipality's composition, and standardised to the composition of "
        "natural deaths. The primary contrast, stated before the hospital records were analysed, is the change of the share White from birth to the "
        "certificate in external causes against natural causes. Birth, hospital and certificate were compared for the same deaths by multiplying, death by "
        "death, the estimate of each race at birth and of each race in hospital (the chance parts of the two are independent). Intervals come from bootstrap "
        "replicates over municipalities (500 or 1,000); those of the strata in Figure 3 are of a difference of counts and omit the variance of the denominator. "
        "Analyses used Python 3.11; the code accompanies the article. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council "
        "no review was required.")
