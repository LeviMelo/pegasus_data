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
para(s, "Units that share a key and a class (g of them) share their candidates and their control, so their counts enter the variances as g squared. Let c be the "
        "records of a key cell of the unit's sex and o those of the other sex, s the scale. (i) Counts: Var T taken as the candidates plus the control summed, and "
        "a proportion's standard error sqrt(Var T(j, k)) / T(j, +), as if the row sum were known. (ii) Model: with the register's records Poisson, Var T(j, k) = "
        "sum of g^2 (c + s^2 o) over the cells; with independent cells the proportion p = T(j, k) / T(j, +) has Var p = [(1 - p)^2 V(j, k) + p^2 (V(j, +) - "
        "V(j, k))] / T(j, +)^2, which with no chance agreement is the binomial p(1 - p) / n; the declared mix is the same with rows in place of cells, and a ratio of "
        "rates by declared class a over b has Var log r = V(a, +) / T(a, +)^2 + V(b, +) / T(b, +)^2, the person-years being complete counts of births. (iii) "
        "Chance: for the table of these units only the chance candidates (expected s o) and the control vary, V = sum of g^2 o (s + s^2), with the same delta "
        "method. (iv) Clusters: with z_m the linearised contribution of municipality m (for p: [T_m(j, k) - p T_m(j, +)] / T(j, +)), Var = M / (M - 1) sum z_m^2 "
        "over the M municipalities of the group, years pooled. The rate ratios of the companion papers at 1-9 years were counted before the g and s terms were "
        "added; there V was taken with g = s = 1 (deaths at 1-9 years rarely share a key, and s is close to 1.05).")
para(s, "(ii) answers the question asked of a classification as a property of the system that produced the deaths; (iii) the question of how far the estimate is "
        "from the table that a perfect linkage of the same units would give; (iv) the first question without the Poisson model, treating the municipalities as a "
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
        "a scenario. Monte Carlo error of the bias: the standard deviation of estimate less truth over the replicates, over the square root of their number. "
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
                         pct(x["cover_found_chance"], 0)])
table(s, "Supplementary Table S1 - Simulation: bias, standard errors and coverage by scenario and municipality size",
      ["Scenario", "Births a year", "Estimand", "Truth", "Bias, all deaths (MC error)", "Bias, deaths found (MC error)", "Empirical SE", "Model SE", "Cluster SE",
       "Coverage of all deaths, model", "Coverage of the system's value, model", "Coverage of the system's value, cluster", "Coverage of the found, chance"], rows,
      [f"{SIM['replicates']} replicates a scenario. Truth: mean over replicates of the table of all deaths of the class. MC error: Monte Carlo standard error of "
       "the bias. Coverage: share of 95% intervals containing the target named. Above 25,600 births a year estimates are unstable (row sums at or below zero)."])
rows = []
for s_ in PS:
    for sc in ("mun", "uf"):
        b = PS[s_][sc]
        rows.append([s_, "municipality" if sc == "mun" else "state", pct(b["found"]["est"]), pp(b["against_findable"]["mean_abs_diff"], 4),
                     pp(b["against_findable"]["max_abs_diff"], 4), pp(b["against_linked"]["mean_abs_diff"]), pp(b["against_linked"]["max_abs_diff"]),
                     f2(b["against_linked"]["model_ratio_median"]), f2(b["against_linked"]["se_ratio_median"]), f2(b["against_linked"]["chance_ratio_median"])])
table(s, "Supplementary Table S2 - Admissions that ended in death: the control scaled within the municipality or the state, and the four standard errors",
      ["Certificates a year", "Control scaled within", "Found", "Mean |diff|, findable", "Largest |diff|, findable", "Mean |diff|, linked",
       "Largest |diff|, linked", "Model / counts SE", "Cluster / counts SE", "Chance / counts SE"], rows,
      ["Standard error ratios: medians over the twenty cells."])
s.save(OUT / "supplement.docx")
