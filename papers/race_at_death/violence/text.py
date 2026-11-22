# The front of paper 5, violence: shared names, the claims asserted, title, abstract, introduction and methods. Executed by build.py
# (`build.py violence`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
import json as _json

VI = _json.loads((HERE / "results" / "violence.json").read_text(encoding="utf-8"))
DESIGN = "cross-sectional study of birth, hospital and death records related without identifiers"
OBJECTIVE = ("to measure whether the race recorded for young people in Brazil departs from their race at birth according to how and where they "
             "died, and at which record, in life or at death, the departure arises")
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


def _pt(v):
    """Percentage points, signed, without a negative zero."""
    s_ = f"{100 * v:+.1f}"
    return "0.0" if s_ in ("+0.0", "-0.0") else s_


def ddc(x):
    return f"{_pt(x['est'])} percentage points (95%CI {_pt(x['est'] - 1.96 * x['se'])}; {_pt(x['est'] + 1.96 * x['se'])})"


VP = _json.loads((HERE / "results" / "violence_place.json").read_text(encoding="utf-8"))
EF = _json.loads((HERE / "results" / "estimator.json").read_text(encoding="utf-8"))["a1_findability"]["pair"]["by_declared"]


def dpl(x):
    """A bootstrap difference with its percentile interval, in percentage points."""
    return f"{_pt(x['est'])} percentage points (95%CI {_pt(x['lo'])}; {_pt(x['hi'])})"


AT_ = VP["all"]["all assault"]["minus_transport"]
NT_ = VP["all"]["natural"]["minus_transport"]
ST_ = VP["standardised_to_occurrence"]["all assault"]["minus_natural"]
assert AT_["lo"] < 0 < AT_["hi"], "assaults now differ from transport deaths from birth to certificate"
assert ST_["hi"] < 0 and VP["died_at_home_municipality"]["all assault"]["minus_natural"]["hi"] < 0, "the contrast no longer survives the place of occurrence"
assert VP["died_in_hospital"]["all assault"]["minus_natural"]["hi"] < 0, "within hospital deaths the contrast is gone"


P_ASS, P_EXT = dd("all assault", "natural"), dd("all external, not assault", "natural")
H_ASS = dd("all assault", "natural", "hospital_white->certified_white", TR)
T_ASS = dd("all assault", "natural", "net_shift", TM)
A_ASS = dd("all assault", "natural", "birth_white->certified_white", TR)
B_ASS = dd("all assault", "natural", "birth_white->hospital_white", TR)
PLS = {g: sum(VI["placebo_shifts"][k][g] for k in VI["placebo_shifts"]) / len(VI["placebo_shifts"]) / max(VI["person"][g]["n_est"], 1)
       for g in ("natural", "assault by firearm")}
# the claims of the text, held by the results
assert all(BC[k]["net_shift"]["est"] < BC["natural"]["net_shift"]["est"] - 0.05 for k in ("transport", "suicide", "assault by firearm", "other assault")), \
    "external causes no longer lose more White from birth to the certificate than natural deaths"
assert abs(P_ASS["est"] - P_EXT["est"]) < 0.03, "assaults now differ from the other external causes"
assert abs(B_ASS["est"]) < 2 * B_ASS["se"] + 0.01, "birth to hospital now differs between assault and natural deaths"
assert H_ASS["est"] + 1.96 * H_ASS["se"] < 0, "hospital to certificate no longer differs between assault and natural deaths"
assert T_ASS["est"] < 0 and abs(A_ASS["est"] - P_ASS["est"]) < 0.02, "the dying admission or the admitted subset now disagree"
assert TR["natural"]["hospital_white->certified_white"]["est"] > 0 > TR["all assault"]["hospital_white->certified_white"]["est"]
assert all(TM[g]["certified_white"]["est"] > TM[g]["hospital_white"]["est"] for g in ("natural", "transport", "assault by firearm")), \
    "the certificate is no longer lighter than the record of the dying admission"
assert PLS["assault by firearm"] > 0.05 > 0 > PLS["natural"], "the placebo residuals changed sign or size"
iml_a, iml_x = YC["by_certifier"]["assault"]["medical examiner"], YC["by_certifier"]["external, not assault"]["medical examiner"]

d = new_doc()
TITLE = ("Recorded less White at death: the race of young people who die of external causes against their birth and hospital records, related "
         "without identifiers, Brazil, 2015-2024")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
CLAIM = ["deaths from external causes", "arose at death", "the external cause itself"]
para(d, f"Methods: {DESIGN[0].upper() + DESIGN[1:]}, Brazil. Deaths at 15-24 years in 2015-2024 of people born in 2000-2009, in municipalities with fewer than "
        "1,600 births a year, were related to the live births and to earlier hospital admissions, with records of the other sex as a control for chance agreement. "
        "The share recorded White at birth, at an earlier admission and on the certificate was compared by cause of death, for the same deaths.")
SN_ = VP["standardised_to_natural_place"]
assert all(BC[k]["net_shift"]["est"] < 0 for k in (*EXT, "natural")), "a share White no longer falls: rewrite 'fell by'"
para(d, f"Results: About half of {n0(sum(VI['deaths_total'][k] for k in ('natural', 'transport', 'suicide', 'other external', 'undetermined intent', 'assault by firearm', 'other assault', 'legal intervention')))} "
        f"deaths were found among their birth candidates. From birth to the certificate the share White fell by {abs(100 * BC['natural']['net_shift']['est']):.1f} "
        f"points for natural deaths and by {abs(100 * max(BC[k]['net_shift']['est'] for k in EXT)):.1f} to {abs(100 * min(BC[k]['net_shift']['est'] for k in EXT)):.1f} for "
        f"external causes; assaults changed as transport deaths did ({dpl(AT_)}). For the same deaths, the change from birth to an earlier hospital record "
        f"did not differ by cause ({ddc(B_ASS)}); the difference arose on the certificate. It held at equal racial composition of the municipality where the death occurred "
        f"({dpl(ST_)}), and with assaults given the natural deaths' distribution of place of death "
        f"{pct(SN_['all assault']['share_remaining'], 0)} of it remained ({dpl(SN_['all assault']['minus_natural'])}).")
para(d, "Conclusion: Young people in deaths from external causes, assaults no different from transport deaths, were certified White less often than their earlier records had them. "
        "The difference arose at death, partly with dying away from a health establishment and a family and partly with the external cause itself.")
para(d, "Keywords: External Causes; Death Certificates; Racial Groups; Forensic Medicine; Data Accuracy; Young Adult; Brazil.")
d.add_heading("Introduction", level=1)
para(d, f"Rates of death by race in Brazil, homicide among them, take the race from the death certificate {cite('soaresfilho2011', 'cerqueira2014')}. "
        "For deaths from external causes, the certificate is completed by the medical examiner of a medico-legal institute, who has not seen the person alive "
        f"and records race from the body or from whoever informs it {cite('cfm1779')}; for natural deaths it is usually the attending physician, with the "
        "family at hand. Race is also read from circumstances: people incarcerated or poor are seen as darker "
        f"{cite('saperstein2010', 'penner2008')}, and on United States certificates the race recorded depended on the cause of death {cite('noymer2011')}. If "
        "certifiers record young people who die of external causes as less White than the same people were recorded in life, part of the racial gap in those "
        "deaths is made at death; if those who die so were already recorded so before, the certificate reports a classification made in life. A third "
        "possibility is that it is not the cause but the circumstances of certification, away from a hospital and a family, that change the record.")
para(d, "The readings predict different things about a record made before death and about the place of death. Public Brazilian files carry no identifier, but deaths, births and "
        "hospital admissions share the birth date, sex and municipality of residence, which in smaller municipalities relate a death to its own birth and "
        "admissions with a measurable rate of chance agreement. We found no study that compared the race of the same young people at birth, in hospital "
        f"and at death by cause. This study aimed {OBJECTIVE}.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the RECORD statement {cite('benchimol2015')}. Deaths came from the Mortality Information "
        f"System (SIM), births from the Live Birth Information System (SINASC) and admissions from the Hospital Information System (SIH) of the Unified Health "
        f"System {cite('datasus')}.")
para(d, "Population. Deaths at 15-24 years in 2015-2024 of people born in 2000-2009, residents of municipalities with fewer than 1,600 live births a year on "
        "average in 2000-2009, where a birth date, sex and municipality are shared by few other people. Causes (underlying cause, ICD-10): "
        "transport accidents (V01-V99); suicide (X60-X84); assault by firearm (X93-X95); assault by other means (X85-Y09 otherwise); legal intervention "
        "(Y35-Y36); events of undetermined intent (Y10-Y34); other external causes, including injury codes (S, T) filed as underlying causes; natural "
        "causes are all other codes (A00-R99, U, Z, and deaths with no cause filed). Municipalities "
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
        "death, the estimate of each race at birth and of each race in hospital, which assumes that the chance agreements of the two registers are "
        "independent, as they come from different records. Intervals come from bootstrap "
        "replicates over municipalities (500 or 1,000); those of the strata in Figure 3 are of a difference of counts and omit the variance of the denominator. "
        "Analyses used Python 3.11; the code accompanies the article. Ethics: public, anonymised data; under Resolution 510/2016 of the National Health Council "
        "no review was required.")
