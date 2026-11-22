# The front of the estimator paper (paper 6): shared names, the claims asserted, title, abstract, introduction and methods. Executed
# by build.py (`build.py estimator`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# Revised after the second referee report (audits/review_2.md, audits/response_2.md).
# ruff: noqa: F821
REFS |= json.loads((HERE / "references" / "crossref_estimator.json").read_text(encoding="utf-8"))
E = json.loads((HERE / "results" / "estimator.json").read_text(encoding="utf-8"))
SIM = json.loads((HERE / "results" / "simulation.json").read_text(encoding="utf-8"))
_pooled = HERE / "results" / "simulation_pooled.json"                  # the scenarios that pool twelve cohorts are run apart (they take twelve times as long)
if _pooled.exists():
    _p = json.loads(_pooled.read_text(encoding="utf-8"))
    SIM["results"] |= _p["results"]
    SIM["scenarios"] |= _p["scenarios"]
    SIM["replicates_pooled"] = _p["replicates"]
DESIGN = "methodological study with validation against linked records and a simulation study"
OBJECTIVE = ("to state, validate and give the variance of an estimator of the cross-classification of a variable recorded in two registers that share no "
             "identifier, only the birth date, sex and municipality of residence")
I = R["infants"]
LI, LP = E["like_infants"]["groups"], E["like_pair"]["groups"]
PAIR = E["pair"]
SR = SIM["results"]
SMALL = ["<400", "400-1,599", "1,600-6,399", "6,400-25,599"]
LQ = PAIR["link_quality"]
lq_inf = I["link_quality"]
P_CELLS = ["p_white_white", "p_black_black", "p_black_brown", "p_brown_brown", "p_brown_white"]    # the five commonest cells
ALL_P = [*P_CELLS, "p_indigenous_indigenous"]                                                   # ... and the rare one (review 2, 1.1): every proportion simulated
HOLD = ("ideal", "twins", "sparse")                                   # the scenarios in which A1-A3 hold
FULL = ("ideal", "twins")                                             # ... with the real number of deaths
REPS = SIM["replicates"]
NEW = ("overdisp", "keyerr", "keyerr_k", "pooled12", "munfx", "application")
HAVE_NEW = all(k in SR for k in NEW)       # the scenarios added after review 2 (run apart: see audits/response_2.md)


def worst(sc, key, cells=P_CELLS, sizes=SMALL):
    return max(abs(SR[sc][s][q][key]) for s in sizes for q in cells)


def worst_z(sc, key="bias", mc="mcse_bias", cells=P_CELLS, sizes=SMALL):
    """The largest bias in units of its Monte Carlo error."""
    return max(abs(SR[sc][s][q][key]) / SR[sc][s][q][mc] for s in sizes for q in cells)


def cover_range(scs, key, cells=P_CELLS, sizes=SMALL):
    v = [SR[sc][s][q][key] for sc in scs for s in sizes for q in cells]
    return min(v), max(v)


def cell(block, a, b, key="cells"):
    return block[key][f"{a}|{b}"]


def pp(x, d=3):
    return f"{x:.{d}f}"


def sg(x, d=3):
    """A signed difference; a zero at this precision is written without a sign."""
    out = f"{x:+.{d}f}"
    return out[1:] if float(out) == 0 else out


def cim(c, se="se_model", d=3):
    """est (95%CI) with the named standard error."""
    return f"{c['est']:.{d}f} (95%CI {c['est'] - 1.96 * c[se]:.{d}f}; {c['est'] + 1.96 * c[se]:.{d}f})"


def link_cell(m, a, b):
    return m["rows"][a][b]["est"]


def lv(block, g, v="linked", t="against_linked"):
    """A like-for-like result: size class ``g``, variant ``v`` (the units the estimator ran on), the table ``t`` against which it is compared."""
    return block[g]["variants"][v][t]


# ---------------------------------------------------------------- the simulation's summaries, and the claims they hold
found_ideal, found_twins = SR["ideal"]["all"]["found"]["est"], SR["twins"]["all"]["found"]["est"]
assert found_twins > found_ideal, "twins no longer raise the share found"
cm_lo, cm_hi = cover_range(HOLD, "cover_super_model")                 # model interval, the system's classification
cc_lo, cc_hi = cover_range(HOLD, "cover_found_chance")                # chance interval, the table of the deaths found
ck_lo, ck_hi = cover_range(HOLD, "cover_super")                       # cluster interval
cp_lo, cp_hi = cover_range(HOLD, "cover_super_poisson")               # the earlier counts' interval
cov_mcse = 1.96 * (0.95 * 0.05 / REPS) ** 0.5                          # a coverage's 95% Monte Carlo band at 95%
hold_bias = max(worst(sc, "bias") for sc in FULL)                      # five commonest cells, below 25,600
hold_small = max(worst(sc, "bias", sizes=SMALL[:3]) for sc in FULL)
hold_z = max(worst_z(sc) for sc in FULL)
hold_all_small = max(worst(sc, "bias", cells=ALL_P, sizes=SMALL[:3]) for sc in FULL)     # including the Indigenous row
hold_all_big = max(worst(sc, "bias", cells=ALL_P, sizes=SMALL[3:]) for sc in FULL)
indig = {sc: SR[sc]["6,400-25,599"]["p_indigenous_indigenous"] for sc in HOLD}
indig_z = {sc: indig[sc]["bias"] / indig[sc]["mcse_bias"] for sc in HOLD}
q_all = [q for q in SR["ideal"]["all"] if not q.startswith("_") and q != "found"]
n_cells = {sc: sum(abs(SR[sc][s][q]["bias"]) > 1.96 * SR[sc][s][q]["mcse_bias"] for s in SMALL for q in q_all) for sc in HOLD}
n_tot = len(SMALL) * len(q_all)
# with a twelfth of the deaths the rows are small: the ratio of two noisy sums has no finite mean where its denominator can cross zero
sp_row = SR["sparse"]["6,400-25,599"]["p_black_black"]
sp_fail = SR["sparse"]["6,400-25,599"]["_invalid"] / REPS
sparse_small, sparse_bias = worst("sparse", "bias", sizes=SMALL[:3]), worst("sparse", "bias")
sparse_med = max(abs(SR["sparse"][s][q]["median_bias_found"]) for s in SMALL for q in P_CELLS)
cov_sel = {sc: cover_range([sc], "cover_model") for sc in ("movers", "unequal", "selective", "a2")}
t_ratio = (1 - SIM["scenarios"]["unequal"]["move"][0]) / (1 - SIM["scenarios"]["unequal"]["move"][2])
SE_RATIO = {s: SR["ideal"][s]["p_black_black"]["se_model"] / SR["ideal"][s]["p_black_black"]["sd"] for s in [*SMALL, "all"]}     # mean model SE over the empirical SD
assert hold_small < 0.005 and hold_bias < 0.015, "with the assumptions holding the five commonest cells are no longer nearly unbiased"
assert hold_all_small < 0.01 < hold_all_big and 3 < max(indig_z.values()), "the Indigenous row no longer departs at 6,400-25,599"
assert hold_small < sparse_small < 0.03 and sparse_bias > hold_bias, "the sparse scenario no longer shows a bounded small-sample bias"
assert abs(sp_row["median_bias_found"]) < abs(sp_row["bias_found"]) / 3 and sp_fail > 0.05, "the sparse bias is no longer a heavy-tail artefact"
assert cm_lo > 0.9 and cc_lo > 0.88, "the model or chance intervals no longer cover"
assert SE_RATIO["all"] > 1.3 and 0.9 < SE_RATIO["<400"] < 1.1, "the model SE no longer overstates the pooled classes"
assert n_cells["ideal"] >= 3 and n_cells["sparse"] >= 4, "the share of cells with a bias beyond Monte Carlo error has changed"

# ---------------------------------------------------------------- the validations' claims
SM_I = [*SMALL, "<25,600"]
v25 = LI["<25,600"]["variants"]
cmpi, cmpp = v25["all"], LP["all"]["variants"]["all"]
l25, a25, f25 = lv(LI, "<25,600"), lv(LI, "<25,600", "all"), lv(LI, "<25,600", "findable", "against_findable")
big_i = lv(LI, ">=25,600")
assert max(lv(LI, s)["mean_abs_diff"] for s in SMALL) < 0.03, "infants: the estimator on the linked units no longer reproduces the linkage below 25,600 births"
assert big_i["max_abs_diff"] > 0.3, "infants: the largest municipalities no longer fail"
assert l25["nocontrol_mean_abs_diff"] > 3 * l25["mean_abs_diff"], "infants: the control no longer matters"
assert a25["mean_abs_diff"] > l25["mean_abs_diff"], "infants: all units no longer differ more from the linked table than the linked units"
pa_all = LP["all"]["variants"]
pair_l, pair_f = pa_all["linked"]["against_linked"], pa_all["findable"]["against_findable"]
pair_t = pa_all["linked"]["against_findable"]       # the estimate on the linked units against the people among them the key finds: the estimator's target
assert pair_t["outside_model"] <= 4 and pair_t["z_sd_model"] < 2, "against its target the admissions' interval no longer holds"
assert pair_l["mean_abs_diff"] > 3 * pair_t["mean_abs_diff"], "the linked table no longer departs from the findable one"
SZ_INF = {s: LI[s]["variants"]["linked"]["against_linked"] for s in ("<400", "400-1,599", "1,600-6,399", "6,400-25,599") if "linked" in LI[s]["variants"]}
assert pair_l["max_abs_diff"] < 0.02 and pair_f["max_abs_diff"] < 0.02, "admissions: the estimator on the linked units no longer reproduces their table"
assert all(LP[s]["variants"]["linked"]["against_linked"]["mean_abs_diff"] < 0.02 for s in LP), "admissions: a size class departs from the linked units"
assert LP[">=6,400"]["variants"]["linked"]["against_linked"]["nocontrol_mean_abs_diff"] > 3 * LP[">=6,400"]["variants"]["linked"]["against_linked"]["mean_abs_diff"]
MR = PAIR["missing_race"]
miss = {s: MR[f"Branca|{s}"] for s in ("findable", "unfindable")}
wk = {s: miss[s]["white_given_known"] for s in miss}
raw_gap = (E["pair"]["by_size"][-1]["findable"]["rows"]["Branca"]["Branca"]["est"] - PAIR["unfindable"]["rows"]["Branca"]["Branca"]["est"])
known_gap = wk["findable"] - wk["unfindable"]
miss_gap = miss["unfindable"]["missing"] - miss["findable"]["missing"]
assert 0.05 < known_gap < raw_gap and miss_gap > 0.03, "the gap conditional on a recorded race no longer shrinks"
A1 = E["a1_findability"]
t_cls = A1["pair"]["by_declared"]
assert t_cls["Branca"] > t_cls["Preta"] > t_cls["Parda"] > t_cls["Indigena"], "findability no longer falls from White to Indigenous"
shifts = [f"shift{s:+d}" for s in (-14, -7, 7, 14)]
pl = {g: [LI[g]["variants"][v]["placebo"] for v in shifts] for g in ("<25,600", "all")}
pl_p = {g: [LP[g]["variants"][v]["placebo"] for v in shifts] for g in ("all",)}
assert all(abs(x["T_over_deaths"]) < 0.02 for x in pl["<25,600"] + pl_p["all"]), "the shifted-date placebo no longer finds nothing"
sx_i, sx_p = LI["<25,600"]["sex_split"], LP["all"]["sex_split"]

d = new_doc()
TITLE = ("Cross-classifying two registers without linking them: candidates less a negative control from birth date, sex and municipality, "
         "tested on Brazilian birth, death and hospital records")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
CLAIM = ["without linking anyone", "the people whose key", "its bias is the selection"]
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, "Methods: For each record of one register (a death), the records of the other (births) sharing its birth date, sex and municipality are counted "
        "by class; the other sex's records of the same day estimate the chance agreements and are subtracted. The estimator was run "
        f"on the units a one-to-one linkage paired, for {n0(I['certificates'])} Brazilian infant deaths ({I['years'][0]}-{I['years'][1]}) and "
        f"{n0(PAIR['units'])} hospital admissions that ended in death ({PAIR['years'][0]}-{PAIR['years'][-1]}), with a shifted-date placebo and a simulation of its bias and coverage.")
AGE_ = E.get("like_pair_by_age", {})
AGE_MAD = [v["groups"]["all"]["linked"]["against_findable"]["mean_abs_diff"] for v in AGE_.values()]
AGE_OUT = [v["groups"]["all"]["linked"]["against_findable"]["outside_model"] for v in AGE_.values()]
assert AGE_ and max(AGE_MAD) < 0.005 and max(AGE_OUT) <= 2, "by age at death the admissions' estimate no longer matches its target"
para(d, f"Results: On the linked infants of municipalities under 25,600 births a year ({pct(E['infants_births_share']['below_25600'], 0)} of births), the "
        f"estimate differed from the linkage by {pp(l25['mean_abs_diff'])} on average over 20 cells (without the control, {pp(l25['nocontrol_mean_abs_diff'])}). On admissions, against its target (the people the key finds), it differed by "
        f"{pp(pair_t['mean_abs_diff'])} with {pair_t['outside_model']} of {pair_t['cells']} cells outside the interval, and in every age band by "
        f"{min(AGE_MAD):.3f}-{max(AGE_MAD):.3f}. The shifted-date placebo found almost no one. In simulation the estimator was nearly unbiased for the people found where its "
        "assumptions held. Where it could be measured (admissions linked to certificates), "
        f"findability fell from {pct(t_cls['Branca'], 0)} for White to {pct(t_cls['Indigena'], 0)} for Indigenous.")
para(d, "Conclusion: A cross-classification between registers can be estimated without linking anyone, for the people whose key the two registers share, "
        "with an interval that held against that target; its bias is the selection of who shares the key.")
para(d, "Keywords: Medical Record Linkage; Vital Statistics; Data Accuracy; Bias; Negative Controls; Ecological Inference; Simulation; Brazil.")

d.add_heading("Introduction", level=1)
para(d, "Many questions in epidemiology need the cross-classification of a variable recorded twice for the same people in two registers: the race declared at "
        "birth against the race certified at death, the diagnosis of an admission against the underlying cause on the certificate. Linking the records gives it, and "
        f"computers have linked vital records since {cite('newcombe1959')}, formalised as probabilistic linkage {cite('fellegi1969')}. Where the registers carry no "
        f"identifier, linkage rests on partially identifying variables, its errors bias what is estimated from the linked pairs {cite('doidge2019', 'harron2017')}, "
        f"the rate of false matches must itself be estimated {cite('belin1995')}, and methods correct regression on linked data for known or modelled probabilities of a "
        f"false link {cite('lahiri2005', 'hof2012')}, correct cross-tabulations of linked files by a bootstrap of the linkage {cite('chipperfield2015')}, carry every "
        f"candidate record into the analysis by multiple imputation {cite('goldstein2012')}, or model the linkage and the analysis jointly {cite('tancredi2011')}. "
        "These linkage-error methods work from individual pairs. A cohort of 114 million Brazilians has been linked to national health databases with 93-97% true "
        f"matches {cite('pita2018')}, outside the public files, which carry no identifier.")
para(d, "Another tradition estimates a cross-classification from aggregates. Ecological regression infers individual behaviour from the counts of areas "
        f"{cite('goodman1953')}; the aggregate data alone do not identify the two unobserved fractions of a table, and the assumptions that identify them have to "
        f"be stated and examined {cite('wakefield2004')}; the R x C case has frequentist and Bayesian solutions {cite('rosen2001')}. The estimator studied here is "
        "close to that tradition: a cross-moment of the counts of two registers over key cells (birth date, sex, municipality), with a negative-control regressor, "
        "the other sex's births, that removes the chance agreements the cells themselves create. It differs in that a person is in the key cell, which makes "
        "each cell's expectation linear in the table sought, and it is compared below with a Goodman regression on the same cells.")
para(d, "After the first year of life a Brazilian death certificate shares with the person's birth record only the birth date, the sex and the municipality of "
        "residence: the mother's fields and the birth weight, which allow infant deaths to be linked one to one, are not filled. Where many children are born a day, "
        "the key is shared by several births and no individual link exists. Yet the question needs only the table, not who is whom. If the false agreements could be "
        "counted, they could be subtracted from the table of all agreements. The idea is borrowed from negative controls, comparisons known to carry a bias and not "
        f"the effect {cite('lipsitch2010')}, which empirical calibration also uses to correct intervals {cite('schuemie2014', 'schuemie2018')}: here, records that "
        "agree with a death as often by chance as its candidates do and can never be the person. The births of the other sex on the same day in the same municipality "
        "are such records.")
para(d, f"This study aimed {OBJECTIVE}: its assumptions and estimands, a variance that includes the denominator of each proportion and the covariances of deaths "
        "sharing a key, tests against linked records with known answers on exactly the units the linkage paired, a placebo, comparisons with simpler "
        "estimators, and a simulation study of its bias and coverage.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the RECORD statement {cite('benchimol2015')} and, for the simulation, the ADEMP structure "
        f"{cite('morris2019')}. Live births came from the Live Birth Information System (SINASC), deaths from the Mortality Information System (SIM) and admissions "
        f"that ended in death from the Hospital Information System of the Unified Health System (SIH), all public files of the Ministry of Health {cite('datasus')}. "
        "The race on a birth record is the mother's declaration of her own race since the 2011 form; on a certificate it is recorded by the certifier or hospital staff. "
        "Terms. The key is the birth date, sex and municipality of residence. A unit is a death (or an admission that ended in death). A unit is linked when the stored "
        "one-to-one linkage paired it with a record of the other register; findable when, besides, that record shares its key; found is the estimator's share "
        "T(+, +) over the units, the people the key finds in one of the four classes of the rows. A unit's row is the class on the other register's record (the mother's "
        "race for births), its column the class recorded for the unit.")
para(d, "The estimator. Let a group G hold units i with key x_i and class k_i in the first register, and let the second register hold records r with key x_r and "
        "class j_r. The candidates of i in class j are C_i(j), the records with x_r = x_i and j_r = j. Its control K_i(j) is the number of records of class j with the "
        "birth date and municipality of i and the other sex, times s_i, the ratio of the register's records of i's sex to those of the other sex in that municipality "
        "and birth year. The estimator is T(j, k) = sum over the units of G certified k of C_i(j) - K_i(j) (Figure 1). Three assumptions are used. (A1) The person's own "
        "record is among the candidates with a probability t_j that may depend on the class j but not, given j, on the class k: the person kept the key (did not move, "
        "and the birth date and municipality were recorded alike). (A2) Given the day and the municipality, the records of the two sexes have the same composition by "
        "class and stand in the ratio s, and the day's excess variation is shared by the two sexes: the chance candidates' expectation, also for the days on which a "
        "death occurred, is the control's. (A3) A record related to the person and sharing the key is of the person's class: a twin of the same sex adds to the "
        "candidates, one of the other sex to the control, both in the person's own cell. Under A2 and A3 the expectation of T(j, k) is t_j N(j, k) plus a twins' "
        "term in the person's own cell, with N(j, k) the units of G by (j, k). The row T(j, k) / T(j, +) estimates P(k | j) under A1-A3; as a ratio of sums it is "
        "consistent, with no finite moments where the row sum can be non-positive. The row sums over T(+, +) estimate the declared mix, and a rate by declared class (row "
        "sum over person-years by that class) gives ratios between classes, both only if t_j is the same for all j. No individual is linked, and the case of one "
        "candidate (the unique link) is included. A unit whose birth date or municipality differs between the registers is not among its candidates; it adds chance "
        "only, which its control removes.")
figure(d, "estimator_design", "Figure 1 - The estimator for one death: its candidates, its control and their difference",
       ["The same key (birth date, municipality of residence) with the other sex gives records that agree by chance as often and are never the person."])
para(d, "Variance. Five standard errors were compared (Supplementary Text S1), each by the delta method with a proportion's row sum as denominator. (i) Counts, the "
        "earlier practice: candidates plus control over the row's sum as if it were known. (ii) Model: with the register's records Poisson, a cell is the people found "
        "plus the chance candidates less the control, the control's variance carrying its scale squared, units that share a key and a class counted together. (iii) "
        "Exact model: as (ii) with the covariances of the cells of a row, since deaths that share a key cell share their records whatever their class, and of the two "
        "sexes, since a day's girls are the candidates of girls' deaths and the control of boys'. (iv) Chance: the error in the table of these units only, in which the "
        "people found are fixed. (v) Clusters: Taylor linearisation with municipalities as sampled units, which allows for dependence within a municipality and puts "
        "the variation of the classification between municipalities in the error.")
para(d, f"Validation 1: infant deaths and their births. Infant deaths of {I['years'][0]}-{I['years'][1]} ({n0(I['certificates'])}) were linked to their birth records "
        f"by probabilistic linkage {cite('fellegi1969')} on birth date, sex, residence, birth weight and the mother's age; {pct(I['linked'] / I['certificates'])} were "
        f"linked, with an estimated {min(v['fdr_percent'] for v in lq_inf.values()):.2f}-{max(v['fdr_percent'] for v in lq_inf.values()):.2f}% of false links a year. "
        "The estimator was run on the units themselves, counted by birth date, sex and residence alone: on the linked units (the table to be reproduced is theirs), on "
        "all units, on the unlinked units, and on the findable ones, by the municipality's mean births a year. The twenty cells (four races on the birth record by four "
        "races and none on the certificate) were compared with the linked pairs'. As a baseline, the candidates were also tabulated without the control.")
para(d, f"Validation 2: admissions that ended in death and their certificates. The {n0(PAIR['units'])} admissions of {PAIR['years'][0]}-{PAIR['years'][-1]} that "
        "ended in death in the year of the admission's end were the units, the death certificates of the same year the register, the race recorded by the hospital "
        "and the race on the certificate the two classes. The known answer was a probabilistic linkage of the two on birth date, sex, the day of death and the "
        f"hospital or its municipality, {min(v['fdr_percent'] for v in LQ.values()):.2f}-{max(v['fdr_percent'] for v in LQ.values()):.2f}% of false links a year, "
        f"{pct(PAIR['linked'] / PAIR['units'])} of the units linked. The estimator used birth date, sex and residence, and the year, and the control was scaled within "
        "birth year and municipality. This pair differs from the first in the register (deaths of all ages instead of births), in who assigns the classes (hospital "
        "staff and certifiers), and in the density of chance agreements, which is lower; its known answer also tells which linked pairs share the key. Size classes were "
        "the municipality's mean certificates a year.")
para(d, "Tests of the assumptions on the real units. Placebo: the key birth date of every unit was shifted by 7 or 14 days, forward or back (the same weekday), "
        "so that no unit has its person among its candidates; every T(j, k) should be zero within its error, and the z-scores give an empirical null "
        f"{cite('schuemie2014', 'schuemie2018')}. Sex: the table was estimated for boys and for girls apart (control from the other sex) and compared cell by cell. "
        "Scale: the control was scaled within the municipality, the state or the nation. Findability (A1): among linked units, the share findable by the class on "
        "the other register, by that class and the unit's, and by age. Comparators, on all units and the same cells: the unique-key link (units with one candidate "
        "only), uniform attribution (each of c candidates takes 1/c), and Goodman's regression by least squares of the deaths of each class on the births of each class "
        f"over the key cells without intercept {cite('goodman1953')}, its coefficients normalised by row.")
para(d, "Simulation (ADEMP). Aims: bias and coverage of the estimator, and of its errors, under departures from A1-A3. Data-generating mechanism: the 2018 "
        "birth cohort of every municipality by declared race, spread over days with a weekday and seasonal pattern (stronger on weekdays for White births); deaths "
        f"by declared race at the rates estimated at 1-9 years, {n0(SIM['deaths_target'])} in all as in 2013-2024, drawn from one cohort; the certified race drawn "
        "from the infant linkage's table for the decile of White births of the municipality where the death is certified (Supplementary Text S2). Scenarios: "
        "ideal (no departure; all deaths of the twelve cohorts in one cohort, so that deaths sharing a day are twelve times as frequent as in the data); twins "
        "(2% of births twins, dying at twice the rate); movers (28% of children dying resident in another municipality of the state, certified there); unequal (movers "
        "22% of White and 30-34% of other children); selective (movers 22%, and 12 points more among the children certified in a class other than the declared one); "
        "sparse (as ideal, with a twelfth of the deaths); a2 (boys 52.5% of White and 50.5% of Black and Indigenous births, breaking A2)"
        + ("; and, added after the second review, overdisp (a day's births overdispersed, partly shared by the sexes, at the dispersion measured in SINASC 2018), keyerr "
           "and keyerr_k (a wrong birth date on the death record at the rate by class that the admissions' findability implies, in the second also more often when the "
           "class recorded differs from the declared), pooled12 (twelve independent sparse cohorts pooled, the real density of deaths per key and the real number of "
           "deaths), munfx (a municipality effect on the odds of being certified the declared class, of the size measured in the linked infants) and application "
           "(movers, twins, pooled cohorts, overdispersion, municipality effects and wrong dates together)" if HAVE_NEW else "")
        + ". Estimands: P(k | j) for all deaths of a group of municipalities by size (the target) and for those found among "
        "their candidates; the declared mix; the White, Black and Indigenous to Brown rate ratios, truth by deaths by municipality of birth over births of the same "
        "municipalities. Methods: the estimator and its errors from the package function and the exact model error. Performance: bias with its Monte Carlo error, "
        "median bias, empirical standard error, mean and median standard error, variance ratio, coverage of the 95% interval with its Monte Carlo error, and the share "
        "of replicates with a non-positive row sum (failed), with the moments among the valid ones.")
para(d, "Unequal shares found. Where t differs between classes the declared mix and rate ratios are biased by the ratio of their t: a ratio between classes a and b "
        "estimates the true ratio times t_a / t_b. The t_j were measured where linked data allow (Results) and enter the simulation; the size of the bias is shown by "
        f"it, as a bias analysis {cite('lash2014')}. The limit of 25,600 births a year was chosen on the infant validation itself. Ethics: public, anonymised data; under "
        "Resolution 510/2016 of the National Health Council no review was required. Analysis code: the package pegasus_data (functions candidate_counts, "
        "pair_candidate_counts, candidate_estimates) and the scripts of the paper's repository.")
