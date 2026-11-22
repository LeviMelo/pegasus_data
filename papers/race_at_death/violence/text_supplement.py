# The supplement of paper 5. Executed by build.py after text.py, whose names it uses.
# ruff: noqa: F821
s = new_doc()
para(s, "Supplementary material - " + TITLE, bold=True)
s.add_heading("Supplementary Text S1 - Relating records without identifiers", level=2)
para(s, "For a death i, let C_i be the set of records in the other register (live births, or hospital admissions) with the birth date, sex and municipality of "
        "residence of i. If the person stayed in the municipality, one element of C_i is the person (for admissions, possibly several, one per admission); the "
        "others agree by chance. The records of the other sex with the same birth date and municipality cannot contain the person and share the day's size; "
        "scaled by the ratio of the two sexes' records in the municipality (and, for admissions, the birth year, since young women are admitted for childbirth), "
        "their count estimates the chance candidates. The cross-classification of the records' race by the certified race, candidates minus scaled control, "
        "estimates that of the people found, who are those who did not move: the shares found were alike for every cause of death (Table 1 of the main text). "
        "The estimator reproduced one-to-one linkage of infant deaths in municipalities below 25,600 births a year; in simulation it was nearly unbiased for "
        "the people found where each row holds enough deaths, with a small-sample bias in sparse rows, and moving that depends on the class recorded biased "
        "it against all deaths (companion methods paper). Here the restriction to municipalities with fewer than 1,600 births a year keeps chance candidates "
        "few. For the hospital records, each death contributes whether any admission with its key was recorded in each race, so that a person with several admissions counts once.")
rows = []
for k in ("natural", "assault", "external"):
    for r in REG[k]:
        rows.append([k, f"region: {r}", n0(REG[k][r].get("deaths", 0)), cc(cell(REG[k][r], "Branca", "Branca")), cc(cell(REG[k][r], "Parda", "Parda"))])
    for pp in PER[k]:
        rows.append([k, f"period: {pp}", n0(PER[k][pp].get("deaths", 0)), cc(cell(PER[k][pp], "Branca", "Branca")), cc(cell(PER[k][pp], "Parda", "Parda"))])
table(s, "Supplementary Table S1 - Young people certified in their race at birth, by cause, region and period, Brazil, 2015-2024",
      ["Cause", "Group", "Deaths", "White at birth: certified White", "Brown at birth: certified Brown"], rows,
      ["Candidate estimator, municipalities with fewer than 1,600 births a year; 95% confidence intervals from the difference of counts."])
rows = []
for g in ("natural", "transport", "suicide", "assault by firearm", "other assault", "legal intervention", "all assault"):
    for j in ("white", "brown", "black"):
        rows.append([g, j] + [cc(VI["person"][g]["cells"][f"hospital {j}|certified {k}"]) if VI["person"][g]["cells"][f"hospital {j}|certified {k}"]["est"] is not None else "-"
                              for k in ("white", "brown", "black")])
table(s, "Supplementary Table S2 - Certified race of young people according to the race recorded at an earlier hospital admission, by cause of death, Brazil, "
         "2015-2024", ["Cause", "Hospital's race", "Certified White", "Certified Brown", "Certified Black"], rows,
      ["Admissions of 2010-2024 ending at least 30 days before the death and not in death, one record per person; candidate estimator with the other sex as control; 95% confidence "
       "intervals from a bootstrap over municipalities."])
SPL = [("All deaths found", "all"), ("Died in the municipality of residence", "died_at_home_municipality"), ("Died elsewhere", "died_elsewhere"),
       ("Standardised to the composition of the place of occurrence", "standardised_to_occurrence"), ("Died in hospital", "died_in_hospital"),
       ("Died out of hospital", "died_out_of_hospital")]
rows = []
for lab, k in SPL:
    blk = VP[k]
    rows.append([lab] + [_pt(blk[g]["shift"]) for g in ("natural", "transport", "all assault", "suicide")]
                + [dpl(blk["all assault"]["minus_natural"]).replace(" percentage points", ""), dpl(blk["all assault"]["minus_transport"]).replace(" percentage points", "")])
table(s, "Supplementary Table S3 - Change of the share White from birth to the death certificate by cause, by place of death and place of certification, "
         "Brazil, 2015-2024", ["Deaths", "Natural", "Transport", "Assaults", "Suicide", "Assaults minus natural (95%CI)", "Assaults minus transport (95%CI)"], rows,
      ["Percentage points. Deaths at 15-24 years found among their birth candidates, municipalities of residence with fewer than 1,600 births a year; place of "
       "occurrence and place of death from the death certificate (CODMUNOCOR, LOCOCOR: hospital or other health establishment against elsewhere). Standardised: "
       "each cause's change averaged over thirds of the share of White births in the municipality of occurrence with the weights of all deaths. Intervals: 500 "
       "bootstrap replicates over municipalities of residence."])
s.save(OUT / "supplement.docx")
