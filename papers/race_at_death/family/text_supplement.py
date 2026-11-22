# The supplement of paper 4. Executed by build.py after text.py, whose names it uses.
# ruff: noqa: F821
s = new_doc()
para(s, "Supplementary material - " + TITLE, bold=True)
s.add_heading("Supplementary Text S1 - The cohort series", level=2)
para(s, "The share of each five-year birth cohort reported White at the Censuses of 2000, 2010 and 2022 was read from a cohort-component population account of "
        "every municipality, built for this research programme from the censuses, the mortality and live birth registers and the official estimates of IBGE; "
        "in a census year the account takes the census population by single year of age and race as given, so the shares at the three dates are census "
        "shares. A cohort's White share can fall between censuses through reclassification, but also through higher mortality or emigration of White people, "
        "differences in coverage between censuses and the change of the 2022 questionnaire; the series describes the cohorts and does not separate these. The Census of 2000 was taken on 1 August 2000, so the cohort born in 2000 held only eight months of births then and is not compared with its later counts.")
s.add_heading("Supplementary Text S2 - Design-based standard errors", level=2)
para(s, "For a weighted proportion r = sum(w y) / sum(w), the linearised variable z = w (y - r) / sum(w) was summed within households and its variance "
        "estimated as the between-household variance within states, sum over states of n_h / (n_h - 1) sum (z_hi - mean_h)^2, which treats households as "
        "sampled with replacement within states. With the weighting areas of 2010 as strata the standard error of Brown mothers' children aged 0-9 reported "
        f"White was {FA['design_check_2010']['weighting_area_strata']['se']:.5f}, against {FA['design_check_2010']['state_strata']['se']:.5f} with states. The "
        "logistic models use the weights scaled to a mean of 1 and standard errors clustered by household.")
rows = []
for m, ml in (("white", "White"), ("brown", "Brown"), ("black", "Black"), ("indigenous", "Indigenous")):
    for y in (2010, 2022):
        rows.append([ml, str(y), n0(MX[str(y)][f"{m}|0-4"]["white"]["records"])] + [dci(v(y, m, c), 3) for c in ("white", "brown", "black")])
table(s, "Supplementary Table S1 - Race reported for children aged 0-4 according to the race of their mother, Brazilian Censuses of 2010 and 2022",
      ["Mother's race", "Census", "Children (sample records)", "Reported White (95%CI)", "Reported Brown (95%CI)", "Reported Black (95%CI)"], rows,
      ["Children of the household's couple living with their mother. Weighted proportions; 95% confidence intervals (95%CI) by Taylor linearisation, strata "
       "the states, primary units the households; they reflect sampling only. Rows do not sum to 1: the remainder is Yellow, Indigenous or not reported."])
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
