# The supplement of the estimator paper. Executed by build.py after text_discussion.py, whose names it uses.
# ruff: noqa: F821
s = new_doc()
para(s, "Supplementary material - " + TITLE, bold=True)
s.add_heading("Supplementary Text S1 - The estimator's expectation and its four variances", level=2)
para(s, "Write F(j, k) for the units of G found among their candidates (the person kept the key) and B(j, k) = sum over units certified k of the chance candidates of "
        "class j. Then the candidates summed are F(j, k) + B(j, k) + W(j, k), W the related records sharing the key (same-sex twins), and the control summed is "
        "K(j, k) = B'(j, k) + W'(j, k), B' the other sex's chance records scaled by s and W' the other-sex twins. Under A2, E[B'] = E[B]; under A3, W and W' fall in "
        "the person's own cell. So E[T(j, k)] = E[F(j, k)] + E[W - W'], and under A1 E[F(j, k)] = t_j N(j, k). The row proportion is a ratio of such sums: "
        "consistent as the units of a row grow, biased in small rows, and unstable when a row sum is near zero (a class rare among the units and common among "
        "the chance candidates). Intervals are Wald intervals and are not bounded to 0-1. In the text and tables no rule withholds an estimate; the figures do not "
        "draw estimates whose standard error is 0.15 or more, and rows of the known answers with fewer than 30 pairs are left out of the comparisons.")
para(s, "Units that share a key cell share their candidates and their control whatever their class; the package's variance columns group by key, class, age, cause and "
        "year, the analysis here by key and class (the key cell's deaths of a class, g, enter as g squared). Let c be the records of a key cell of the unit's sex and o "
        "those of the other sex, s the scale. (i) Counts: Var T taken as the candidates plus the control summed, and a proportion's standard error sqrt(Var T(j, k)) / T(j, +), "
        "as if the row sum were known. (ii) Model: with the register's records Poisson, Var T(j, k) = sum of g^2 (c + s^2 o) over the cells; with independent cells the "
        "proportion p = T(j, k) / T(j, +) has Var p = [(1 - p)^2 V(j, k) + p^2 (V(j, +) - V(j, k))] / T(j, +)^2; the declared mix is the same with rows in place of cells, and "
        "a ratio of rates by declared class a over b has Var log r = V(a, +) / T(a, +)^2 + V(b, +) / T(b, +)^2, the person-years being complete counts of births. "
        "(iii) Exact model: in a key cell write x for the boys' deaths by class less the girls' over beta (beta the ratio of boys to girls in the municipality and birth "
        "year) and y for the girls' less beta times the boys'; the cell's T(j, k) is c_boys(j) x_k + c_girls(j) y_k, so for the linear form a'T(j, .) with a = e_k - p_jk "
        "the variance is a' M_j a with M_j the sum over cells of x x' c_boys(j) + y y' c_girls(j), which carries the covariances between classes of deaths sharing a "
        "cell and between the sexes; divided by T(j, +)^2 it is Var p_jk. With one death a cell it equals (ii). (iv) Chance: for the table of these units only the chance "
        "candidates (expected s o) and the control vary, V = sum of g^2 o (s + s^2), with the same delta method. (v) Clusters: with z_m the linearised contribution of "
        "municipality m (for p: [T_m(j, k) - p T_m(j, +)] / T(j, +)), Var = M / (M - 1) sum z_m^2 over the M municipalities of the group, years pooled. The rate ratios of the "
        "companion papers at 1-9 years were counted before the g and s terms were added; there V was taken with g = s = 1.")
para(s, "(ii) and (iii) answer the question asked of a classification as a property of the system that produced the deaths; (iv) the question of how far the estimate is "
        "from the table that a perfect linkage of the same units would give; (v) the first question without the Poisson model, treating the municipalities as a "
        "sample from a population of municipalities, so that variation of the classification between them enters the error.")
s.add_heading("Supplementary Text S2 - The simulation", level=2)
para(s, "Births. Each municipality's 2018 births by the race on the birth record (White, Black, Brown, Indigenous, and Asian or blank) were spread over the 365 days "
        "with weights for the weekday (Monday to Sunday 1.06, 1.08, 1.07, 1.06, 1.04, 0.88, 0.81, departures from one multiplied by 1.5 for White and 0.8 for "
        "Indigenous births) and a seasonal cosine of amplitude 0.05, and drawn as Poisson counts by day, sex (51.2% boys; in scenario a2 52.5% of White and 50.5% "
        "of Black and Indigenous births) and race. Twins (scenarios with twins): pairs drawn at 1% of births by day and race, two thirds of the same sex. Deaths: "
        "each birth died with a probability proportional to 0.66, 1.1, 1.0, 4.1 and 1.0 for the five classes, twins at twice it, scaled to the deaths of 2013-2024 "
        "at 1-9 years (scenario sparse: a twelfth of them). Movers: a death moved with the scenario's probability to a municipality of the same state chosen in "
        "proportion to its births (a draw of its own municipality being no move), and was resident there at death. Certified race: drawn from the infant "
        "linkage's proportions for the decile of the White share of births of the municipality of residence at death (rows with fewer than 50 linked pairs: the "
        "national proportions), a child declared Asian or blank as a Brown one; in the selective scenario the race is drawn where the child was born and the mover "
        "keeps it.")
para(s, "The estimator was computed as for the real data: candidates and the other sex's births of the death's day in its municipality of residence, scaled by the "
        f"municipality's ratio of boys to girls, deaths sharing a key and a class counted together. Every replicate drew a new world; {SIM['replicates']} replicates "
        f"a scenario ({SIM.get('replicates_pooled', SIM['replicates'])} for the two pooled ones). Monte Carlo error of the bias: the standard deviation of estimate less truth over the replicates, over the square root of their number. "
        "Targets: the table of all deaths of the size class (the estimand), of those found among their candidates (for the bias of the estimator itself), and the "
        "mean of the first over replicates (the system's classification, for the coverage of the model and cluster errors).")

rows = []
for sc in SIM["scenarios"]:
    for size in [*SMALL, ">=25,600", "all"]:
        b = SR[sc][size]
        for q, name in (("p_white_white", "White as White"), ("p_black_black", "Black as Black"), ("p_brown_brown", "Brown as Brown"),
                        ("ratio_white", "White/Brown rate ratio"), ("ratio_black", "Black/Brown rate ratio")):
            x = b[q]
            rows.append([sc, size, name, pp(x["truth"]), f"{sg(x['bias'])} ({pp(x['mcse_bias'])})", f"{sg(x['bias_found'])} ({pp(x['mcse_bias_found'])})",
                         pp(x["sd"]), pp(x["se_model"]), pp(x["se"]), pct(x["cover_model"], 0), pct(x["cover_super_model"], 0), pct(x["cover_super"], 0),
                         pct(x["cover_found_chance"], 0), sg(x["median_bias_found"]) if "median_bias_found" in x else "", pct(b["_invalid"] / REPS, 0)])
table(s, "Supplementary Table S1 - Simulation: bias, standard errors and coverage by scenario and municipality size",
      ["Scenario", "Births a year", "Estimand", "Truth", "Bias, all deaths (MC error)", "Bias, deaths found (MC error)", "Empirical SE", "Model SE", "Cluster SE",
       "Coverage of all deaths, model", "Coverage of the system's value, model", "Coverage of the system's value, cluster", "Coverage of the found, chance",
       "Median bias, deaths found", "Failed replicates"], rows,
      [f"{SIM['replicates']} replicates a scenario ({SIM.get('replicates_pooled', SIM['replicates'])} for pooled12 and application). Truth: mean over replicates of the table of all deaths of the class. MC error: Monte Carlo standard error of "
       "the bias. Coverage: share of 95% intervals containing the target named. Above 25,600 births a year estimates are unstable (row sums at or below zero). Monte Carlo error of a coverage near 95%: "
       f"{pp(cov_mcse / 1.96 * 100, 1)} points. Failed: a row sum at or below zero in the replicate (any row)."])
rows = []
for g in LP:
    for v in ("all", "scale_uf", "scale_br"):
        x = LP[g]["variants"][v]
        rows.append([g, {"all": "municipality", "scale_uf": "state", "scale_br": "nation"}[v], pct(x["found"]["est"]), pp(x["against_linked"]["mean_abs_diff"], 4),
                     pp(x["against_linked"]["max_abs_diff"], 4), f"{x['against_linked']['outside_model']} / {x['against_linked']['outside_exact']} / {x['against_linked']['outside_chance']}"])
for g in SM_I:
    for v in ("all", "scale_uf", "scale_br"):
        x = LI[g]["variants"][v]
        rows.append(["infants " + g, {"all": "municipality", "scale_uf": "state", "scale_br": "nation"}[v], pct(x["found"]["est"]), pp(x["against_linked"]["mean_abs_diff"], 4),
                     pp(x["against_linked"]["max_abs_diff"], 4), f"{x['against_linked']['outside_model']} / {x['against_linked']['outside_exact']} / {x['against_linked']['outside_chance']}"])
table(s, "Supplementary Table S2 - The control scaled within the municipality, the state or the nation, all units against the linked table",
      ["Size class (admissions: certificates a year)", "Control scaled within", "Found", "Mean |diff|", "Largest |diff|", "Cells outside 95%CI: model / exact / chance"], rows,
      ["Differences over the twenty cells against the table of the linked pairs."])
rows = []
for name, B in (("infants", LI), ("admissions", LP)):
    for g in B:
        for v in shifts:
            x = B[g]["variants"][v]["placebo"]
            rows.append([name, g, v.replace("shift", "shift "), pct(x["T_over_deaths"], 2), pp(x["z_mean"], 2), pp(x["z_sd"], 2), pct(x["share_outside"], 0)])
table(s, "Supplementary Table S3 - Placebo: the key birth date shifted by 7 or 14 days (the same weekday)",
      ["Data", "Size class", "Shift (days)", "Share found (should be 0)", "Mean z of the 20 cells", "SD of z", "Cells with |z| > 1.96"], rows,
      ["z = T(j, k) / its exact model standard error; under the null the mean is 0, the SD 1 and 5% of cells fall outside."])
rows = [[k, pp(v["phi"], 4), pp(v["psi"], 4), n0(v["municipalities"])] for k, v in E["births_dispersion"].items() if isinstance(v, dict)]
table(s, "Supplementary Table S4 - Dispersion of the daily births of SINASC 2018 beyond Poisson, by the municipality's size class",
      ["Births a year", "phi: excess variance / mean squared, per sex", "psi: covariance of the sexes / product of means", "Municipalities"], rows,
      ["Moments within municipality and weekday over the 52 weeks of 2018, each sum over municipalities of (variance - mean) over (mean squared - variance / 52). Classification "
       f"heterogeneity: sd of the municipality effect on the logit of certification as the declared class {pp(E['classification_heterogeneity']['tau'], 2)}."])
rows = []
for side, key in (("admissions", "pair"), ("infants", "infants")):
    for k_, v in A1[key]["by_declared_recorded"].items():
        rows.append([side, k_.replace("|", " certified, recorded "), pct(v["t"]), n0(v["n"])])
table(s, "Supplementary Table S5 - Findability (A1): the share of linked units whose partner shares the key, by the class on the other register and the unit's own class",
      ["Data", "Class on the other register | class recorded", "Share findable", "Linked units"], rows,
      ["Admissions: recorded is the hospital's race (missing and other apart). Infants: recorded is the certificate's race (other: not one of the four or none)."])
for _f in LATE_TABLES:
    _f()
rows = [[b, n0(v["units"]), pp(v["groups"]["all"]["linked"]["chance_per_unit"], 3), pp(v["groups"]["all"]["linked"]["against_findable"]["mean_abs_diff"], 4),
         str(v["groups"]["all"]["linked"]["against_findable"]["outside_model"]), pp(v["groups"]["all"]["linked"]["against_findable"]["z_sd_model"], 2),
         pp(v["groups"]["all"]["linked"]["against_linked"]["mean_abs_diff"], 4)] for b, v in E["like_pair_by_age"].items()]
table(s, "Supplementary Table S9 - The estimator on admissions that ended in death, by age at death: the linked units against the people the key finds (the "
         "target) and against the whole linked table, Brazil, 2016-2022", ["Age at death (years)", "Units", "Chance candidates per unit", "Mean absolute difference, "
         "target", "Cells outside the model interval (of 20)", "z-score SD", "Mean absolute difference, whole linked table"], rows,
      ["Age at death: year of death less year of birth. All municipality sizes pooled. Target: the linked people whose certificate shares the key with their "
       "admission."])
s.save(OUT / "supplement.docx")
