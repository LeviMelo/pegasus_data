# The supplement of paper 4. Executed by build.py after text.py, whose names it uses.
# ruff: noqa: F821
s = new_doc()
para(s, "Supplementary material - " + TITLE, bold=True)
s.add_heading("Supplementary Text S1 - The cohort series", level=2)
para(s, "The share of each five-year birth cohort reported White at the Censuses of 2000, 2010 and 2022 was read from a cohort-component population account of "
        "every municipality, built for this research programme from the censuses, the mortality and live birth registers and the official estimates of IBGE; "
        "in a census year the account takes the census population by single year of age and race as given, so the shares at the three dates are census "
        "shares. A cohort's White share can fall between censuses through reclassification, but also through higher mortality or emigration of White people, "
        "differences in coverage between censuses and the change of the 2022 questionnaire; the series describes the cohorts and does not separate these.")
s.add_heading("Supplementary Text S2 - Design-based standard errors", level=2)
para(s, "For a weighted proportion r = sum(w y) / sum(w), the linearised variable z = w (y - r) / sum(w) was summed within households and its variance "
        "estimated as the between-household variance within states, sum over states of n_h / (n_h - 1) sum (z_hi - mean_h)^2, which treats households as "
        "sampled with replacement within states. With the weighting areas of 2010 as strata the standard error of Brown mothers' children aged 0-9 reported "
        f"White was {FA['design_check_2010']['weighting_area_strata']['se']:.5f}, against {FA['design_check_2010']['state_strata']['se']:.5f} with states. The "
        "logistic models use the weights scaled to a mean of 1 and standard errors clustered by household.")
rows = []
for key, lab in (("brown|is_white", "Brown mother, child White"), ("black|is_black", "Black mother, child Black")):
    for term, val in MD[key].items():
        if isinstance(val, dict):
            rows.append([lab, term.replace("C(", "").replace(")[T.", ": ").replace("[T.", ": ").replace("]", ""), f"{val['or']:.2f}", f"{val['lo']:.2f}; {val['hi']:.2f}"])
table(s, "Supplementary Table S1 - Odds ratios of the race reported for children aged 0-9, logistic models of the Censuses of 2010 and 2022 together, Brazil",
      ["Outcome", "Term", "Odds ratio", "95%CI"], rows,
      ["References: census 2010; partner of the mother's race; mother with no or incomplete primary schooling; child aged 0-4; mother aged 25-34; boy; "
       "Centre-West. Weighted; standard errors clustered by household."])
rows = []
for y in ("2010", "2022"):
    for key, lab in (("brown|is_white", "Brown mother, child White"), ("black|is_black", "Black mother, child Black"), ("black|is_brown", "Black mother, child Brown")):
        for dim in ("instruction", "region"):
            for k, val in BY[y].items():
                if k.startswith(f"{key}|{dim}|"):
                    rows.append([y, lab, f"{dim}: {k.split('|')[3]}", dci(val)])
table(s, "Supplementary Table S2 - Children aged 0-9 by the mother's race, the race reported for the child, the mother's instruction and the region, Brazilian "
         "Censuses of 2010 and 2022", ["Census", "Cell", "Group", "Proportion (95%CI)"], rows,
      ["Design-based 95% confidence intervals."])
s.save(OUT / "supplement.docx")
