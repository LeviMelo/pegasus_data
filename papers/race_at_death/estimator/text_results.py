# The Results of the estimator paper. Executed by build.py after text.py.
# ruff: noqa: F821
d.add_heading("Results", level=1)
GI = [*SMALL, "<25,600", ">=25,600", "all"]
big_n = LI[">=25,600"]["variants"]["all"]["municipalities"]
sh_l = LI["all"]["variants"]["linked"]["units"] / LI["all"]["variants"]["all"]["units"]
fn = {g: (LI[g]["variants"]["linked"]["found"]["est"], LI[g]["variants"]["unlinked"]["found"]["est"]) for g in GI}
assert fn["<25,600"][0] > fn["<25,600"][1] + 0.05, "the unlinked infants are no longer found less often"
assert l25["outside_model"] <= 2 and l25["z_sd_model"] < 1, "the infants' intervals are no longer adequate or conservative"
assert sx_i["z_sd"] < 1.2 and sx_p["z_sd"] > 2, "the sexes no longer agree for infants or disagree for admissions"
assert pair_l["outside_model"] >= 8 and pair_l["z_sd_model"] > 3, "the admissions' intervals no longer fall short"
ulv = LI["<25,600"]["unlinked_vs_linked"]
para(d, f"Infant deaths. On exactly the units the linkage paired, below 25,600 births a year the estimator reproduced the linked table with a mean absolute "
        f"difference over the twenty cells of {pp(lv(LI, '<400')['mean_abs_diff'])} in municipalities under 400 births a year, "
        f"{pp(lv(LI, '6,400-25,599')['mean_abs_diff'])} at 6,400-25,599 and {pp(l25['mean_abs_diff'])} over all of them, the largest {pp(l25['max_abs_diff'], 2)} "
        f"(Table 1, Figure 2A); the candidates without the control differed by {pp(l25['nocontrol_mean_abs_diff'])} on average. For calibration, {l25['outside_model']} of {l25['cells']} cells lay outside the 95% model interval, {l25['outside_exact']} outside the "
        f"exact model interval and {l25['outside_chance']} outside the chance interval, with a standard deviation of the z-scores of {pp(l25['z_sd_model'], 2)}, "
        f"{pp(l25['z_sd_exact'], 2)} and {pp(l25['z_sd_chance'], 2)}: for infants the intervals were adequate or conservative, because the sampling error is large "
        f"and the key's own errors small (the linked units share the key in "
        f"{pct(E['like_infants']['unit_shares']['findable'] / E['like_infants']['unit_shares']['linked'], 0)} of cases). "
        f"Run on all units, the unlinked ones included, the difference from the linked "
        f"table was {pp(a25['mean_abs_diff'])}; the estimator found {pct(fn['<25,600'][0], 0)} of the linked and {pct(fn['<25,600'][1], 0)} of the unlinked infants, and the "
        f"two tables differed by {pp(ulv['mean_abs_diff'])} on average over the cells with 50 or more units ({ulv['cells']} cells; z-score sd {pp(ulv['z_sd'], 2)}). In the "
        f"{big_n} municipalities of 25,600 births or more the chance candidates overwhelmed the people: the largest difference was "
        f"{pp(big_i['max_abs_diff'], 2)}. Infants declared Black on the birth record were certified Black in "
        f"{pp(LI['<400']['full']['p'][1][1])} (95%CI {pp(LI['<400']['full']['p'][1][1] - 1.96 * LI['<400']['full']['p_se_model'][1][1])}; "
        f"{pp(LI['<400']['full']['p'][1][1] + 1.96 * LI['<400']['full']['p_se_model'][1][1])}) by the estimator and "
        f"{pp(LI['<400']['full']['truth'][1][1])} in the linked pairs, in the smallest municipalities.")
rows = []
for s in GI:
    b = LI[s]["variants"]
    lk, tr = b["linked"], LI[s]["full"]["truth"]
    f_ = LI[s]["full"]["p"]
    al = lk["against_linked"]
    rows.append([s, n0(lk["municipalities"]), n0(b["all"]["units"]), pct(lk["units"] / b["all"]["units"], 0), f"{pct(fn[s][0], 0)} / {pct(fn[s][1], 0)}",
                 f"{pp(f_[0][0], 2)} / {pp(tr[0][0], 2)}", f"{pp(f_[1][1], 2)} / {pp(tr[1][1], 2)}", f"{pp(f_[2][2], 2)} / {pp(tr[2][2], 2)}",
                 pp(al["mean_abs_diff"]), pp(b["all"]["against_linked"]["mean_abs_diff"]), pp(al["nocontrol_mean_abs_diff"]), pp(al["max_abs_diff"]),
                 f"{al['outside_model']} / {al['outside_exact']} / {al['outside_chance']}"])
table(d, f"Table 1 - The estimator against the one-to-one linkage of infant deaths to their births, run on the linked units, by the municipality's mean births a "
         f"year, Brazil, {I['years'][0]}-{I['years'][1]}",
      ["Births a year", "Municipalities", "Units", "Linked", "Found: linked / unlinked", "White certified White", "Black certified Black", "Brown certified Brown",
       "Mean |difference|, linked units", "Mean |difference|, all units", "Mean |difference|, no control", "Largest |difference|, linked units",
       "Cells of 20 outside 95%CI: model / exact / chance"], rows,
      ["Cells (three columns of proportions): estimator on the linked units / the linked pairs' table. Differences over the twenty cells of the table (race on the birth "
       "record: White, Black, Brown, Indigenous; on the certificate: the same and other or none); rows with fewer than 30 linked pairs left out. Municipalities: "
       "with deaths in the class; each is in one class. Size classes by the municipality's mean births 2012-2023. The limit of 25,600 was chosen on these data."])
figure(d, "estimator_validation", "Figure 2 - The estimator against the known answer on exactly the linked units, by municipality size, and the calibration of its interval",
       ["A: infant deaths, Brazil 2013-2023, against the one-to-one linkage to the birth record. B: admissions to the Unified Health System that ended in death, "
        "2016-2022, against the death certificates linked by the day of death and the hospital. Bars: 95% intervals from the exact model standard error; cells with a "
        "standard error of 0.15 or more not drawn. C: the same differences divided by that standard error (dashed: +/-1.96); admission cells beyond +/-6 are drawn at the edge."])

# ---- who shares the key
a1i, a1p = A1["infants"]["by_declared"], A1["pair"]["by_declared"]
ba = A1["pair"]["by_age"]
rrd = A1["rate_ratio_distortion"]
assert a1p["Branca"] - a1p["Indigena"] > 0.05, "findability by class no longer differs in the admissions"
assert miss["unfindable"]["missing"] > miss["findable"]["missing"], "the unfindable no longer miss the hospital's race more often"
tw = A1["pair"]["by_declared_recorded"]
para(d, f"Who shares the key. A1 is testable where linked data exist, and it fails. Among admissions linked to a certificate, the share whose certificate shares birth "
        f"date, sex and residence was {pct(a1p['Branca'])} for certified White, {pct(a1p['Preta'])} Black, {pct(a1p['Parda'])} Brown and {pct(a1p['Indigena'])} "
        f"Indigenous; within the White row {pct(tw['Branca|white']['t'])} where the hospital recorded White, {pct(tw['Branca|brown']['t'])} Brown and "
        f"{pct(tw['Branca|missing']['t'])} no race. Findability depends on the class, and given the class on the other register's class, so t_j is not constant and A1 "
        f"does not hold: a rate ratio of Indigenous to Brown children estimated through the key is scaled by {pp(rrd['Indigena/Brown'], 2)} before any moving. Among "
        f"linked infants the shares were {pct(a1i['Branca'])}, {pct(a1i['Preta'])}, {pct(a1i['Parda'])} and {pct(a1i['Indigena'])}. The differences between the units "
        f"that share the key and those that do not are in part differences in recording: of the linked units certified White, the hospital's race was missing in "
        f"{pct(miss['findable']['missing'])} of the findable and {pct(miss['unfindable']['missing'])} of the unfindable, and the share recorded White among those with a "
        f"recorded race was {pct(wk['findable'])} against {pct(wk['unfindable'])}, a gap of {pp(known_gap * 100, 1)} percentage points "
        f"({pp(raw_gap * 100, 1)} before conditioning on a recorded race). Of linked units, {pct(PAIR['colour_known']['admission'], 0)} had a hospital race in one of the five "
        f"classes and {pct(PAIR['colour_known']['certificate'], 0)} a race on the certificate. The unfindable are thus partly the units with sloppier records, not "
        "necessarily other people.")

# ---- placebo and sex
zsd = {g: [x["z_sd"] for x in pl[g]] for g in pl}
para(d, f"Tests of the control on the real units. With the key date shifted by one or two weeks (the same weekday) the estimator found "
        f"{pct(max(abs(x['T_over_deaths']) for x in pl['<25,600']), 1)} or less of the infant units and "
        f"{pct(max(abs(x['T_over_deaths']) for x in pl_p['all']), 1)} or less of the admissions (against {pct(fn['<25,600'][0], 0)} and "
        f"{pct(pa_all['all']['found']['est'], 0)} unshifted); the z-scores of its cells had a mean absolute value of at most "
        f"{max(abs(x['z_mean']) for x in pl['<25,600']):.2f} and a standard deviation of {min(zsd['<25,600']):.2f}-{max(zsd['<25,600']):.2f} for infants "
        f"and {min(x['z_sd'] for x in pl_p['all']):.2f}-{max(x['z_sd'] for x in pl_p['all']):.2f} for admissions (Supplementary Table S3). Boys and girls "
        f"estimated apart gave tables that differed by {pp(sx_i['mean_abs_diff'])} on average for infants ({sx_i['cells']} cells, z-score sd {pp(sx_i['z_sd'], 2)}) "
        f"and {pp(sx_p['mean_abs_diff'])} for admissions ({sx_p['cells']} cells, {pp(sx_p['z_sd'], 2)}, {pct(sx_p['share_outside'], 0)} outside 1.96): "
        f"for infants the sexes agreed within their errors, as A2 predicts, but for a register of deaths of all ages they did not, as the sexes' different composition by "
        f"age and race implies (Discussion). "
        f"Scaling the "
        f"control within the state or the nation instead of the municipality changed the mean difference from the linked table by at most "
        f"{max(abs(lv(LI, g, v)['mean_abs_diff'] - lv(LI, g, 'all')['mean_abs_diff']) for g in SM_I for v in ('scale_uf', 'scale_br')):.4f} "
        f"for infants.")

# ---- admissions
rows = []
for s in LP:
    b = LP[s]["variants"]
    al, af = b["linked"]["against_linked"], b["findable"]["against_findable"]
    tr, f_ = LP[s]["full"]["truth"], LP[s]["full"]["p"]
    rows.append([s, n0(b["linked"]["municipalities"]), pp(b["all"]["chance_per_unit"], 2), n0(b["all"]["units"]), pct(b["linked"]["units"] / b["all"]["units"], 0),
                 f"{pct(b['linked']['found']['est'], 0)} / {pct(b['unlinked']['found']['est'], 0)}", f"{pp(f_[0][0], 2)} / {pp(tr[0][0], 2)}", f"{pp(f_[1][1], 2)} / {pp(tr[1][1], 2)}",
                 pp(al["mean_abs_diff"], 4), pp(al["nocontrol_mean_abs_diff"], 4), pp(b["all"]["against_linked"]["mean_abs_diff"]), pp(al["max_abs_diff"], 4),
                 f"{al['outside_model']} / {al['outside_exact']} / {al['outside_chance']}"])
ch_large = LP[">=6,400"]["variants"]["all"]["chance_per_unit"]
para(d, f"Admissions that ended in death. Chance candidates were fewer than in births: {pp(LP['<100']['variants']['all']['chance_per_unit'], 2)} a unit where a "
        f"municipality recorded fewer than 100 certificates a year and {pp(ch_large, 2)} at 6,400 or more (Table 2). On the linked units the estimator "
        f"differed from their table by {pp(pair_l['mean_abs_diff'], 4)} on average and {pp(pair_l['max_abs_diff'])} at most over the twenty cells (Figure 2B). Where chance "
        f"candidates were few the control changed little; at 6,400 certificates a year or more the candidates without it differed by "
        f"{pp(LP['>=6,400']['variants']['linked']['against_linked']['nocontrol_mean_abs_diff'])} on average, with it by "
        f"{pp(LP['>=6,400']['variants']['linked']['against_linked']['mean_abs_diff'])}. Run on all units the difference from the linked table was "
        f"{pp(pa_all['all']['against_linked']['mean_abs_diff'])} on average. Unlike the infants, the intervals fell far short of the real error, the units being many and the key's errors not sampling errors: of twenty cells "
        f"{pair_l['outside_model']} lay outside the model interval, {pair_l['outside_exact']} outside the exact one and {pair_l['outside_chance']} outside the chance "
        f"interval, with z-score standard deviations of {pp(pair_l['z_sd_model'], 2)}, {pp(pair_l['z_sd_exact'], 2)} and {pp(pair_l['z_sd_chance'], 2)}.")
table(d, f"Table 2 - The estimator against the linkage of admissions that ended in death to their death certificates, run on the linked units, by the municipality's mean "
         f"certificates a year, Brazil, {PAIR['years'][0]}-{PAIR['years'][-1]}",
      ["Certificates a year", "Municipalities", "Chance candidates a unit", "Units", "Linked", "Found: linked / unlinked", "Certified White, White in hospital",
       "Certified Black, Black in hospital", "Mean |difference|, linked units", "Mean |difference|, no control", "Mean |difference|, all units",
       "Largest |difference|", "Cells of 20 outside 95%CI: model / exact / chance"], rows,
      ["Proportions of the race on the certificate recorded so by the hospital; cells: the estimator on the linked units / the linked units' table. Control scaled within "
       "the municipality and birth year. Units: admissions with a valid birth date, sex and residence."])

# ---- comparators
rows = []
for name, B, gs in (("infants", LI, [*SMALL, "<25,600", ">=25,600"]), ("admissions", LP, list(LP))):
    for g in gs:
        v = B[g]["variants"]["all"]
        cmp_ = v["comparators"]
        rows.append([name, g, pp(v["against_linked"]["mean_abs_diff"]), pp(v["against_linked"]["nocontrol_mean_abs_diff"]), pp(cmp_["unique"]["mean_abs_diff"]),
                     pp(cmp_["uniform"]["mean_abs_diff"]), pp(cmp_["goodman"]["mean_abs_diff"]), pct(cmp_["unique"]["units_used"] / v["units"], 0)])
cmpi, cmpp = LI["<25,600"]["variants"]["all"], LP["all"]["variants"]["all"]
para(d, f"Comparison with simpler estimators. On all infant units below 25,600 births a year the mean absolute difference from the linked table was "
        f"{pp(cmpi['against_linked']['mean_abs_diff'])} for the estimator, {pp(cmpi['comparators']['unique']['mean_abs_diff'])} for the unique-key link, "
        f"{pp(cmpi['comparators']['uniform']['mean_abs_diff'])} for uniform attribution, {pp(cmpi['comparators']['goodman']['mean_abs_diff'])} for the Goodman regression and "
        f"{pp(cmpi['against_linked']['nocontrol_mean_abs_diff'])} for the candidates without the control (Table 3); for admissions "
        f"{pp(cmpp['against_linked']['mean_abs_diff'])}, {pp(cmpp['comparators']['unique']['mean_abs_diff'])}, {pp(cmpp['comparators']['uniform']['mean_abs_diff'])}, "
        f"{pp(cmpp['comparators']['goodman']['mean_abs_diff'])} and {pp(cmpp['against_linked']['nocontrol_mean_abs_diff'])}. The unique-key link uses "
        f"{pct(cmpi['comparators']['unique']['units_used'] / cmpi['units'], 0)} of the infant units below 25,600 births a year, and the estimator's advantage is "
        "the larger the more chance candidates a unit has (Table 3).")
table(d, "Table 3 - Mean absolute difference from the linked table over the twenty cells: the estimator and four simpler ones, all units, by size class",
      ["Data", "Size class", "Estimator", "Candidates without control", "Unique-key link", "Uniform attribution (1/c)", "Goodman regression", "Units with one candidate"], rows,
      ["All units of the class (linked and unlinked) against the table of the linked pairs, so that the columns are comparable with each other; the difference between "
       "the estimator's column and Table 1's 'linked units' column is the unlinked units."])

# ---- the simulation
W4 = {sc: SR[sc]["<400"]["p_white_white"] for sc in SIM["scenarios"]}
NAT = {sc: SR[sc]["all"] for sc in SIM["scenarios"]}
nat_u = NAT["unequal"]["ratio_white"]
a2 = SR["a2"]
assert abs(W4["movers"]["bias"]) > 5 * abs(W4["movers"]["bias_found"]), "movers: the bias is no longer selection at <400"
assert cp_hi - cp_lo > cm_hi - cm_lo, "the counts' error no longer covers worse than the model's"
assert worst("selective", "bias") > 2 * worst("movers", "bias") and worst("selective", "bias_found") < 0.015, "selective moving no longer biases the proportions"
para(d, f"Simulation. With the assumptions holding and the real number of deaths (ideal, twins), the largest bias of the five commonest cells was {pp(hold_small)} "
        f"below 6,400 births a year and {pp(hold_bias)} at 6,400-25,599 (up to {hold_z:.1f} Monte Carlo errors). The Indigenous row, rare among the units and "
        f"common among the chance candidates, was biased by up to {pp(hold_all_big)} at 6,400-25,599 ({max(indig_z.values()):.1f} Monte Carlo errors; Table 4, Figure 3, "
        f"Supplementary Table S1); over the {n_tot} size-by-quantity cells below 25,600 births, {n_cells['ideal']} (ideal) and {n_cells['twins']} (twins) had a bias beyond "
        f"1.96 Monte Carlo errors. With a twelfth of the deaths (sparse) the five commonest cells reached {pp(sparse_small)} below 6,400 births and {pp(sparse_bias)} above; "
        f"this is a heavy-tail effect and not a small-sample bias of a ratio of sums: at 6,400-25,599, {pct(sp_fail, 0)} of replicates had a non-positive row sum, so that "
        f"the ratio has no finite moments, the median bias of Black recorded Black was {sg(sp_row['median_bias_found'])} against a mean of {sg(sp_row['bias_found'])} "
        f"(sd {pp(sp_row['sd'])}), and failed replicates are counted in the means. Twins raised the share found from {pct(found_ideal)} to {pct(found_twins)} and left "
        f"the proportions as they were. In these scenarios the model intervals covered the system's classification in {pct(cm_lo, 0)}-{pct(cm_hi, 0)} of replicates "
        f"(the Monte Carlo band of a coverage of 95% is +/-{pp(cov_mcse * 100, 1)} points), the cluster intervals in {pct(ck_lo, 0)}-{pct(ck_hi, 0)} and the earlier "
        f"counts' intervals in {pct(cp_lo, 0)}-{pct(cp_hi, 0)}, too wide for common cells and too narrow for rare ones; the chance intervals covered the table of the "
        f"deaths found in {pct(cc_lo, 0)}-{pct(cc_hi, 0)}. In the pooled classes the model standard error overstated the empirical one (mean model SE over empirical SD "
        f"{pp(SE_RATIO['all'], 2)} for Black recorded Black in all municipalities, {pp(SE_RATIO['<400'], 2)} under 400 births a year), and coverage there was "
        f"{pct(SR['ideal']['all']['p_black_black']['cover_super_model'], 1)}: conservative, not nominal. Movers certified where they died, "
        f"{pct(1 - NAT['movers']['found']['est'] / NAT['ideal']['found']['est'], 0)} of deaths lost from the candidates, biased the proportions against all deaths: "
        f"White recorded White by {sg(W4['movers']['bias'])} under 400 births a year, while against the deaths found the bias was {sg(W4['movers']['bias_found'], 4)}; "
        f"coverage of all deaths fell to {pct(cov_sel['movers'][0], 0)}. Moving unequal by race moved the national White to Brown rate ratio from "
        f"{pp(nat_u['truth'], 2)} to {pp(nat_u['est'], 2)} (the nominal ratio of the shares found, {pp(t_ratio, 2)}), while equal moving left it at "
        f"{pp(NAT['movers']['ratio_white']['est'], 2)}. Moving that depended on the class recorded biased the proportions by up to {pp(worst('selective', 'bias'))} "
        f"against all deaths (coverage down to {pct(cov_sel['selective'][0], 0)}) and by at most {pp(worst('selective', 'bias_found'))} against those found. With A2 "
        f"broken (boys 52.5% of White and 50.5% of Black births) the proportions were biased by up to {pp(worst('a2', 'bias'))} and the White to Brown ratio by "
        f"{sg(a2['all']['ratio_white']['bias'])}. In municipalities of 25,600 births or more a row sum was at or below zero in "
        f"{SR['ideal']['>=25,600']['_invalid']} of {REPS} replicates without any departure.")
if HAVE_NEW:
    od, ke, kk, pl12, mf, ap = (SR[k] for k in ("overdisp", "keyerr", "keyerr_k", "pooled12", "munfx", "application"))
    para(d, f"The scenarios added after review. A day's births overdispersed as in SINASC 2018 raised the share found to {pct(od['all']['found']['est'])} "
            f"(against {pct(found_ideal)}), because a sex-specific excess of births on a day with a death is not removed by the other sex's control, and biased the "
            f"proportions by up to {pp(worst('overdisp', 'bias'))}. Wrong birth dates at the rates by class of the admissions left the share found at "
            f"{pct(ke['all']['found']['est'])} and biased the White to Brown rate ratio by {sg(ke['all']['ratio_white']['bias'])}, and by "
            f"{sg(kk['all']['ratio_white']['bias'])} when also more frequent when the class recorded differs from the declared. Twelve pooled sparse cohorts, the real "
            f"regime, gave a largest bias of {pp(worst('pooled12', 'bias'))} and model coverage of {pct(cover_range(['pooled12'], 'cover_super_model')[0], 0)}-"
            f"{pct(cover_range(['pooled12'], 'cover_super_model')[1], 0)}; a municipality effect on the classification (tau {SIM['parameters']['tau']:.2f} on the logit) "
            f"brought the cluster intervals' coverage to {pct(cover_range(['munfx'], 'cover_super')[0], 0)}-{pct(cover_range(['munfx'], 'cover_super')[1], 0)} "
            f"against the model intervals' {pct(cover_range(['munfx'], 'cover_super_model')[0], 0)}-{pct(cover_range(['munfx'], 'cover_super_model')[1], 0)}; with every "
            f"departure together (application) the proportions were biased by up to {pp(worst('application', 'bias'))} against all deaths.")
SIM_FINDING = (f"In simulation, with the assumptions holding and the real number of deaths, bias was at most {pp(hold_small)} below 6,400 births a year for the five "
               f"commonest cells and up to {pp(hold_all_big)} for the Indigenous row at 6,400-25,599; the model intervals covered {pct(cm_lo, 0)}-{pct(cm_hi, 0)}, within "
               f"Monte Carlo error of 95% up to 6,400 births a year and conservative above; families moving biased it against all deaths, by up to "
               f"{pp(worst('selective', 'bias'))} when moving depended on the class recorded.")
rows = []
for sc in SIM["scenarios"]:
    for size in ("<400", "6,400-25,599"):
        b = SR[sc][size]
        rows.append([sc, size, pct(b["found"]["est"]), f"{sg(b['p_white_white']['bias'])} ({sg(b['p_white_white']['bias_found'])})",
                     f"{sg(b['p_black_black']['bias'])} ({sg(b['p_black_black']['bias_found'])})", f"{sg(b['p_brown_brown']['bias'])} ({sg(b['p_brown_brown']['bias_found'])})",
                     f"{sg(b['p_indigenous_indigenous']['bias'])}", sg(b['ratio_white']['bias']),
                     f"{pct(b['p_black_black']['cover_super_model'], 0)} ({pct(b['p_black_black']['cover_super_model_mcse'], 1) if 'cover_super_model_mcse' in b['p_black_black'] else pct((b['p_black_black']['cover_super_model'] * (1 - b['p_black_black']['cover_super_model']) / REPS) ** 0.5, 1)})",
                     pct(b["p_black_black"]["cover_found_chance"], 0), pct(SR[sc][size]["_invalid"] / REPS, 0)])
table(d, f"Table 4 - Simulation: bias of the estimator against all deaths (against the deaths found), coverage with its Monte Carlo error, and failed replicates, in the "
         f"smallest and the largest valid municipalities, {REPS} replicates a scenario",
      ["Scenario", "Births a year", "Found", "White as White", "Black as Black", "Brown as Brown", "Indigenous as Indigenous", "White/Brown rate ratio",
       "Coverage of the system's value, model (MC error)", "Coverage of the found, chance", "Failed replicates"], rows,
      ["Bias: mean of estimate less truth; the rate ratio's truth is the deaths by municipality of birth over the births of the same municipalities. Coverage "
       "(Black as Black): of the system's classification (the mean of the table over replicates) by the model interval; of the table of the deaths found in the replicate "
       "by the chance interval. Failed: a row sum at or below zero. Monte Carlo errors of every bias, medians and variance ratios: Supplementary Table S1."])
figure(d, "estimator_simulation", "Figure 3 - Simulation: bias against all deaths, bias in Monte Carlo errors and coverage of the model interval, by scenario and municipality size",
       ["Bars: 95% Monte Carlo intervals of the bias; the middle row divides the bias by its Monte Carlo error (dashed: +/-1.96). Coverage: of the system's "
        "classification for the proportions, of the true ratio for the rate ratio; the grey band is 95% +/-1.96 Monte Carlo errors."])
