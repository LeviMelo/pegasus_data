# The Results of the estimator paper. Executed by build.py after text.py.
# ruff: noqa: F821
d.add_heading("Results", level=1)
v_all = INF["all"]
inf_out = sum(INF[s]["against_linkage"]["outside_model"] for s in SMALL)
para(d, f"Infant deaths. Below 25,600 births a year the estimator reproduced the linked table cell by cell (Table 1, Figure 2A): the mean absolute difference over "
        f"the twenty cells was {pp(INF['<400']['against_linkage']['mean_abs_diff'])} in municipalities under 400 births a year, "
        f"{pp(INF['6,400-25,599']['against_linkage']['mean_abs_diff'])} at 6,400-25,599 and {pp(v25['against_linkage']['mean_abs_diff'])} over all of them, the "
        f"largest {pp(max(x['max_abs_diff'] for x in inf_small), 2)}; {inf_out} of the {sum(INF[s]['against_linkage']['cells'] for s in SMALL)} cells of the four "
        f"classes differed by more than 1.96 model standard errors. The candidates without the control differed by {pp(v25['against_linkage']['nocontrol_mean_abs_diff'])} "
        f"on average, and by up to {pp(INF['1,600-6,399']['against_linkage']['nocontrol_max_abs_diff'], 2)} in a cell at 1,600-6,399 births a year. Of the linked "
        f"pairs, {pct(v25['findable_share'] / v25['linked_share'])} shared the estimator's key; against them alone the difference was "
        f"{pp(v25['against_findable']['mean_abs_diff'])}. Infants declared Black on the birth record were certified Black in "
        f"{cim(cell(INF['<400'], 'Preta', 'Preta'))} by the estimator and {pp(link_cell(R['validation'][0]['linkage'], 'Preta', 'Preta'))} in the linked pairs, "
        f"in the smallest municipalities. In the {INF['>=25,600']['municipalities']} municipalities of 25,600 births or more the chance candidates overwhelmed the "
        f"people: the largest difference was {pp(INF['>=25,600']['against_linkage']['max_abs_diff'], 2)}. The share found was {pct(v_all['found']['est'])} overall, "
        f"against {pct(v_all['linked_share'])} linked.")
rows = []
for s in [*SMALL, "<25,600", ">=25,600", "all"]:
    b = INF[s]
    lk = b["full"]["truth"]
    a, f_ = b["against_linkage"], b["against_findable"]
    rows.append([s, n0(b["municipalities"]), pct(b["found"]["est"]), pct(b["linked_share"]),
                 f"{pp(cell(b, 'Branca', 'Branca')['est'], 2)} / {pp(lk[0][0], 2)}", f"{pp(cell(b, 'Preta', 'Preta')['est'], 2)} / {pp(lk[1][1], 2)}",
                 f"{pp(cell(b, 'Parda', 'Parda')['est'], 2)} / {pp(lk[2][2], 2)}", pp(a["mean_abs_diff"]), pp(f_["mean_abs_diff"]), pp(a["nocontrol_mean_abs_diff"]),
                 pp(a["max_abs_diff"]), f"{a['outside_model']} of {a['cells']}"])
table(d, f"Table 1 - The estimator against the one-to-one linkage of infant deaths to their births, by the municipality's births a year, Brazil, "
         f"{I['years'][0]}-{I['years'][1]}",
      ["Births a year", "Municipalities", "Found", "Linked", "White certified White", "Black certified Black", "Brown certified Brown", "Mean |difference|",
       "Mean |difference|, findable", "Mean |difference|, no control", "Largest |difference|", "Cells outside 95%CI"], rows,
      ["Cells: the estimator / the linked pairs. Differences over the twenty cells of the table (race on the birth record: White, Black, Brown, Indigenous; on the "
       "certificate: the same and other or none) against all linked pairs, against the linked pairs sharing the estimator's key (findable) and, for the "
       "candidates without the control, against all linked pairs; rows with fewer than 30 linked pairs left out. 95%CI: the model standard error. Size classes "
       "by the municipality's births in the year of birth; a municipality may fall in two classes. The limit of 25,600 was chosen on these data."])
figure(d, "estimator_validation", "Figure 2 - Each cell of the race-by-race table estimated without linkage against the known answer, by municipality size",
       ["A: infant deaths, Brazil 2013-2023, against the one-to-one linkage to the birth record. B and C: admissions to the Unified Health System that ended in "
        "death, 2016-2022, against the death certificates linked by the day of death and the hospital (B: all linked; C: those sharing birth date, sex and "
        "residence). Bars: 95% intervals from the model standard error; estimates with a standard error of 0.15 or more not drawn."])

ch_large = PS[">=6,400"]["chance_per_unit"]
pl = PS[">=6,400"]["mun"]["against_findable"]
para(d, f"Admissions that ended in death. Chance candidates were fewer than in births: {pp(PS['<100']['chance_per_unit'], 2)} a unit where a municipality "
        f"recorded fewer than 100 deaths a year and {pp(ch_large, 2)} at 6,400 or more (Table 2). Against the linked certificates that shared the key, the estimator "
        f"differed by {pp(pair_all['against_findable']['mean_abs_diff'], 4)} on average and {pp(pair_all['against_findable']['max_abs_diff'])} at most over the twenty "
        f"cells (Figure 2C), whether the control was scaled within the municipality or the state. Where chance candidates were few the control changed little; "
        f"at 6,400 certificates a year or more the candidates without it differed by {pp(pl['nocontrol_mean_abs_diff'])} on average, with it by "
        f"{pp(pl['mean_abs_diff'])}. Against all linked certificates the differences were larger ({pp(pair_all['against_linked']['mean_abs_diff'])} on average, "
        f"{pp(pair_all['against_linked']['max_abs_diff'])} at most; Figure 2B): the {pct(PS['all']['findable_share'])} of units whose linked certificate shared "
        f"their key differed from the rest. Among the linked admissions whose certificate gave another birth date or residence, those certified White had been "
        f"recorded White by the hospital in {pct(unf['Branca']['Branca']['est'])}, against {pct(fnd['Branca']['Branca']['est'])} among those that shared it. The "
        f"share found was {pct(pair_all['found']['est'])} against {pct(PS['all']['findable_share'])} findable; the share found counts only the units whose "
        f"certificate gives one of the four races of the rows. The chance intervals, narrow where chance candidates are few, excluded the findable pairs' "
        f"value in {pair_all['against_findable']['outside_chance']} of the twenty cells; the model intervals in {pair_all['against_findable']['outside_model']}.")
rows = []
for s in PS:
    b = PS[s]
    af = b["mun"]["against_findable"]
    rows.append([s, n0(b["municipality_years"]), pp(b["chance_per_unit"], 2), pct(b["linked_share"]), pct(b["findable_share"]), pct(b["mun"]["found"]["est"]),
                 f"{pp(cell(b['mun'], 'Branca', 'Branca')['est'], 2)} / {pp(b['findable']['rows']['Branca']['Branca']['est'], 2)} / {pp(b['linked']['rows']['Branca']['Branca']['est'], 2)}",
                 f"{pp(cell(b['mun'], 'Preta', 'Preta')['est'], 2)} / {pp(b['findable']['rows']['Preta']['Preta']['est'], 2)} / {pp(b['linked']['rows']['Preta']['Preta']['est'], 2)}",
                 pp(af["mean_abs_diff"], 4), pp(af["nocontrol_mean_abs_diff"], 4), pp(b["mun"]["against_linked"]["mean_abs_diff"]),
                 f"{af['outside_model']} / {af['outside_chance']}"])
table(d, f"Table 2 - The estimator against the linkage of admissions that ended in death to their death certificates, by the municipality's certificates a "
         f"year, Brazil, {PAIR['years'][0]}-{PAIR['years'][-1]}",
      ["Certificates a year", "Municipality-years", "Chance candidates a unit", "Linked", "Findable", "Found", "Certified White, White in hospital",
       "Certified Black, Black in hospital", "Mean |difference|, findable", "Mean |difference|, findable, no control", "Mean |difference|, linked",
       "Cells outside 95%CI, model / chance"], rows,
      ["Proportions of the race on the certificate recorded so by the hospital. Cells: the estimator / the findable pairs / all linked pairs. Linked: units with a "
       "linked certificate; findable: those whose certificate shares birth date, sex and residence. Control scaled within the municipality and birth year. "
       "Cells outside: of twenty, against the findable pairs."])

# ---------------------------------------------------------------- the simulation
W4 = {sc: SR[sc]["<400"]["p_white_white"] for sc in SIM["scenarios"]}
NAT = {sc: SR[sc]["all"] for sc in SIM["scenarios"]}
nat_u = NAT["unequal"]["ratio_white"]
a2 = SR["a2"]
assert abs(W4["movers"]["bias"]) > 5 * abs(W4["movers"]["bias_found"]), "movers: the bias is no longer selection at <400"
assert cp_hi - cp_lo > cm_hi - cm_lo, "the counts' error no longer covers worse than the model's"
assert abs(NAT["movers"]["ratio_white"]["bias"]) < 0.01 < nat_u["bias"], "rate ratios: unequal moving no longer the one that biases them"
assert worst("selective", "bias") > 2 * worst("movers", "bias") and worst("selective", "bias_found") < 0.015, "selective moving no longer biases the proportions"
para(d, f"Simulation. With the assumptions holding and the real number of deaths (ideal, twins), the largest bias of the five main cells was {pp(hold_small)} "
        f"below 6,400 births a year and {pp(hold_bias)} at 6,400-25,599, where rows are small and the ratio of sums is biased (up to {hold_z:.1f} Monte Carlo "
        f"errors; Table 3, Figure 3, Supplementary Table S1). With a twelfth of the deaths (sparse) the same small-sample bias grew to {pp(sparse_small)} below 6,400 "
        f"births and {pp(sparse_bias)} above, largest for the rare Black row: the estimator is nearly unbiased only where each row holds enough deaths. Twins raised the share found from {pct(found_ideal)} to {pct(found_twins)} and left the proportions as they were. In these "
        f"scenarios the model intervals covered the system's classification in {pct(cm_lo, 0)}-{pct(cm_hi, 0)} of replicates, the cluster intervals in "
        f"{pct(ck_lo, 0)}-{pct(ck_hi, 0)} and the earlier counts' intervals in {pct(cp_lo, 0)}-{pct(cp_hi, 0)}, too wide for common cells and too narrow for rare "
        f"ones; the chance intervals covered the table of the deaths found in {pct(cc_lo, 0)}-{pct(cc_hi, 0)}, also with deaths as sparse as in one real cohort. "
        f"Movers certified where they died, {pct(1 - NAT['movers']['found']['est'] / NAT['ideal']['found']['est'], 0)} of deaths lost from the candidates, biased "
        f"the proportions against all deaths: White recorded White by {sg(W4['movers']['bias'])} under 400 births a year, while against the deaths found the bias "
        f"was {sg(W4['movers']['bias_found'], 4)}; coverage of all deaths fell to {pct(cov_sel['movers'][0], 0)}. Moving unequal by race moved the national White "
        f"to Brown rate ratio from {pp(nat_u['truth'], 2)} to {pp(nat_u['est'], 2)} (the ratio of the shares found, {pp(t_ratio, 2)}), while equal moving left it at "
        f"{pp(NAT['movers']['ratio_white']['est'], 2)}. Moving that depended on the class recorded biased the proportions by up to {pp(worst('selective', 'bias'))} "
        f"against all deaths (coverage down to {pct(cov_sel['selective'][0], 0)}) and by at most {pp(worst('selective', 'bias_found'))} against those found. With A2 "
        f"broken (boys 52.5% of White and 50.5% of Black births) the proportions were biased by up to {pp(worst('a2', 'bias'))} and the White to Brown ratio by "
        f"{sg(a2['all']['ratio_white']['bias'])}. In municipalities of 25,600 births or more a row sum was at or below zero in "
        f"{SR['ideal']['>=25,600']['_invalid']} of {SIM['replicates']} replicates without any departure.")
SIM_FINDING = (f"In simulation, with the assumptions holding and the real number of deaths, it was nearly unbiased (at most {pp(hold_small)} below 6,400 births "
               f"a year; {pp(sparse_small)} with a twelfth of the deaths) and its model intervals "
               f"covered {pct(cm_lo, 0)}-{pct(cm_hi, 0)}; families moving biased it against all deaths, by up to {pp(worst('selective', 'bias'))} when moving "
               "depended on the class recorded.")
rows = []
for sc in SIM["scenarios"]:
    for size in ("<400", "6,400-25,599"):
        b = SR[sc][size]
        rows.append([sc, size, pct(SR[sc][size]["found"]["est"]), f"{sg(b['p_white_white']['bias'])} ({sg(b['p_white_white']['bias_found'])})",
                     f"{sg(b['p_black_black']['bias'])} ({sg(b['p_black_black']['bias_found'])})", f"{sg(b['p_brown_brown']['bias'])} ({sg(b['p_brown_brown']['bias_found'])})",
                     sg(b['ratio_white']['bias']), pct(b["p_black_black"]["cover_model"], 0), pct(b["p_black_black"]["cover_super_model"], 0),
                     pct(b["p_black_black"]["cover_found_chance"], 0)])
table(d, f"Table 3 - Simulation: bias of the estimator against all deaths (against the deaths found) and coverage, in the smallest and the largest valid "
         f"municipalities, {SIM['replicates']} replicates a scenario",
      ["Scenario", "Births a year", "Found", "White as White", "Black as Black", "Brown as Brown", "White/Brown rate ratio", "Coverage of all deaths, model",
       "Coverage of the system's value, model", "Coverage of the found, chance"], rows,
      ["Bias: mean of estimate less truth. Coverage (Black as Black): of the table of all deaths in the replicate and of the system's classification (the mean "
       "of that table over replicates) by the model interval; of the table of the deaths found in the replicate by the chance interval. All sizes, estimands and "
       "Monte Carlo errors: Supplementary Table S1."])
figure(d, "estimator_simulation", "Figure 3 - Simulation: bias against all deaths and coverage of the model interval, by scenario and municipality size",
       ["Bars: 95% Monte Carlo intervals of the bias. Coverage: of the system's classification for the proportions, of the true ratio for the rate ratio."])
