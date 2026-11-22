# The front of the estimator paper (paper 6): shared names, the claims asserted, title, abstract, introduction and methods. Executed
# by build.py (`build.py estimator`) before text_results.py, text_discussion.py and text_supplement.py, which share its namespace.
# ruff: noqa: F821
REFS |= json.loads((HERE / "references" / "crossref_estimator.json").read_text(encoding="utf-8"))
E = json.loads((HERE / "results" / "estimator.json").read_text(encoding="utf-8"))
SIM = json.loads((HERE / "results" / "simulation.json").read_text(encoding="utf-8"))
DESIGN = "methodological study with validation against linked records and a simulation study"
OBJECTIVE = ("to state, validate and give the variance of an estimator of the cross-classification of a variable recorded in two registers that share no "
             "identifier, only the birth date, sex and municipality of residence")
I = R["infants"]
INF = {b["size"]: b for b in E["infants"]}
PAIR = E["pair"]
PS = {b["size"]: b for b in PAIR["by_size"]}
SR = SIM["results"]
SMALL = ["<400", "400-1,599", "1,600-6,399", "6,400-25,599"]
LQ = PAIR["link_quality"]
lq_inf = I["link_quality"]
P_CELLS = ["p_white_white", "p_black_black", "p_black_brown", "p_brown_brown", "p_brown_white"]
HOLD = ("ideal", "twins", "sparse")                                   # the scenarios in which A1-A3 hold
FULL = ("ideal", "twins")                                             # ... with the real number of deaths


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


# ---------------------------------------------------------------- the simulation's summaries, and the claims they hold
found_ideal, found_twins = SR["ideal"]["all"]["found"]["est"], SR["twins"]["all"]["found"]["est"]
assert found_twins > found_ideal, "twins no longer raise the share found"
cm_lo, cm_hi = cover_range(HOLD, "cover_super_model")                 # model interval, the system's classification
cc_lo, cc_hi = cover_range(HOLD, "cover_found_chance")                # chance interval, the table of the deaths found
ck_lo, ck_hi = cover_range(HOLD, "cover_super")                       # cluster interval
cp_lo, cp_hi = cover_range(HOLD, "cover_super_poisson")               # the earlier counts' interval
hold_bias = max(worst(sc, "bias") for sc in FULL)
hold_small = max(worst(sc, "bias", sizes=SMALL[:3]) for sc in FULL)
hold_z = max(worst_z(sc) for sc in FULL)
# with a twelfth of the deaths the rows are small and the ratio of two noisy sums carries its small-sample bias
sparse_small, sparse_bias = worst("sparse", "bias", sizes=SMALL[:3]), worst("sparse", "bias")
cov_sel = {sc: cover_range([sc], "cover_model") for sc in ("movers", "unequal", "selective", "a2")}
t_ratio = (1 - SIM["scenarios"]["unequal"]["move"][0]) / (1 - SIM["scenarios"]["unequal"]["move"][2])
assert hold_small < 0.005 and hold_bias < 0.015, "with the assumptions holding the estimator is no longer nearly unbiased"
assert hold_small < sparse_small < 0.03 and sparse_bias > hold_bias, "the sparse scenario no longer shows a bounded small-sample bias"
assert cm_lo > 0.9 and cc_lo > 0.88, "the model or chance intervals no longer cover"

# ---------------------------------------------------------------- the validations' claims
inf_small = [INF[s]["against_linkage"] for s in SMALL]
v25 = INF["<25,600"]
assert max(x["mean_abs_diff"] for x in inf_small) < 0.025, "infants: the estimator no longer reproduces the linkage below 25,600 births"
assert INF[">=25,600"]["against_linkage"]["max_abs_diff"] > 0.3, "infants: the largest municipalities no longer fail"
assert v25["against_linkage"]["nocontrol_mean_abs_diff"] > 5 * v25["against_linkage"]["mean_abs_diff"], "infants: the control no longer matters"
assert abs(v25["against_findable"]["mean_abs_diff"] - v25["against_linkage"]["mean_abs_diff"]) < 0.002, "infants: the findable pairs now differ"
pair_all = PS["all"]["mun"]
assert pair_all["against_findable"]["max_abs_diff"] < 0.005, "admissions: the estimator no longer reproduces the findable pairs"
assert all(PS[s]["mun"]["against_findable"]["mean_abs_diff"] < 0.005 for s in PS), "admissions: a size class departs from the findable pairs"
assert PS[">=6,400"]["mun"]["against_findable"]["nocontrol_mean_abs_diff"] > 5 * PS[">=6,400"]["mun"]["against_findable"]["mean_abs_diff"]
unf, fnd = PAIR["unfindable"]["rows"], PS["all"]["findable"]["rows"]
gap = fnd["Branca"]["Branca"]["est"] - unf["Branca"]["Branca"]["est"]
assert gap > 0.05, "the unfindable no longer differ from the findable"
assert all(PS[s]["mun"]["against_linked"]["se_ratio_median"] > 1.5 for s in PS), "admissions: the cluster error no longer exceeds the counts' error"
assert max(abs(PS[s]["mun"]["against_findable"]["mean_abs_diff"] - PS[s]["uf"]["against_findable"]["mean_abs_diff"]) for s in PS) < 0.002, "the control's scaling matters"

d = new_doc()
TITLE = ("Cross-classifying two registers without linking them: an estimator from birth date, sex and municipality with the other sex as a negative "
         "control, validated on Brazilian birth, death and hospital records")
para(d, TITLE, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
para(d, "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]", italic=True)
d.add_heading("Abstract", level=1)
para(d, f"Objective: {OBJECTIVE[0].upper() + OBJECTIVE[1:]}.")
para(d, "Methods: For each record of one register (a death), the records of the other (births) that share its birth date, sex and municipality are counted by "
        "their class; one of them is the person when the key was kept, the rest agree by chance. The other sex's records of the same day and municipality, scaled "
        "by the sex ratio, estimate the chance agreements and are subtracted. The difference, summed over a group, is proportional to the cross-classification. "
        f"It was validated against the one-to-one linkage of {n0(I['certificates'])} Brazilian infant deaths of {I['years'][0]}-{I['years'][1]} to their births, "
        f"and against the linkage of {n0(PAIR['units'])} hospital admissions that ended in death ({PAIR['years'][0]}-{PAIR['years'][-1]}) to their death "
        f"certificates by the day of death and the hospital; a simulation built from the real births ({SIM['replicates']} replicates of each of "
        f"{len(SIM['scenarios'])} scenarios) measured bias and coverage under families that move, twins, unequal moving by race and a broken control.")
para(d, f"Results: In municipalities under 25,600 births a year ({pct(E['infants_births_share']['below_25600'], 0)} of births) the estimated proportions "
        f"differed from the infant linkage by {pp(v25['against_linkage']['mean_abs_diff'])} on average over the 20 cells of the table, against "
        f"{pp(v25['against_linkage']['nocontrol_mean_abs_diff'])} without the control, and failed above. For admissions the difference from the linked "
        f"certificates sharing the key was at most {pp(pair_all['against_findable']['max_abs_diff'])}; the "
        f"{pct(1 - PS['all']['findable_share'] / PS['all']['linked_share'], 0)} of linked admissions whose certificate did not share it were classified "
        f"differently (certified White and recorded White in hospital {pp(unf['Branca']['Branca']['est'], 2)} against {pp(fnd['Branca']['Branca']['est'], 2)}). "
        f"In simulation, with the assumptions holding and the real number of deaths, the bias was at most {pp(hold_small)} below 6,400 births a year and "
        f"{pp(hold_bias)} above; with a twelfth of the deaths it reached {pp(sparse_small)} and {pp(sparse_bias)}, the small-sample bias of a ratio of sums; the "
        f"model intervals covered in {pct(cm_lo, 0)}-{pct(cm_hi, 0)} of replicates; families moving, above all when moving depended on the class "
        f"recorded, biased the estimate against all deaths (coverage down to {pct(cov_sel['selective'][0], 0)}).")
para(d, "Conclusions: A cross-classification between registers can be estimated without linking individuals, for the people whose key the two registers share, "
        "with the error of the chance agreements and the proportion's denominator. Its bias is the difference between those people and the rest, which the "
        f"public files cannot measure: where it could be measured, in the admissions, it was {pp(gap * 100, 0)} percentage points in one cell.")
para(d, "Keywords: Medical Record Linkage; Vital Statistics; Data Accuracy; Bias; Negative Controls; Simulation; Race Factors; Brazil.")

d.add_heading("Introduction", level=1)
para(d, "Many questions in epidemiology need the cross-classification of a variable recorded twice for the same people in two registers: the race declared at "
        "birth against the race certified at death, the diagnosis of an admission against the underlying cause on the certificate. Linking the records gives it "
        f"{cite('fellegi1969')}. Where the registers carry no identifier, linkage rests on partially identifying variables, its errors bias what is estimated from the "
        f"linked pairs {cite('doidge2019', 'harron2017')}, the rate of false matches must itself be estimated {cite('belin1995')}, and methods correct regression on "
        f"linked data for known or modelled probabilities of a false link {cite('lahiri2005', 'hof2012')}, correct cross-tabulations of linked files by a "
        f"bootstrap of the linkage {cite('chipperfield2015')}, carry every candidate record into the analysis by "
        f"multiple imputation {cite('goldstein2012')}, or model the linkage and the analysis jointly {cite('tancredi2011')}. All work from individual pairs. "
        f"A cohort of 114 million Brazilians has been linked to national health databases with 93-97% true matches {cite('pita2018')}, outside the public files, "
        "which carry no identifier.")
para(d, "After the first year of life a Brazilian death certificate shares with the person's birth record only the birth date, the sex and the municipality of "
        "residence: the mother's fields and the birth weight, which allow infant deaths to be linked one to one, are not filled. Where many children are born a day, "
        "the key is shared by several births and no individual link exists. Yet the question needs only the table, not who is whom. If the false agreements could be "
        "counted, they could be subtracted from the table of all agreements. The idea is borrowed from negative controls, comparisons known to carry a bias and not "
        f"the effect {cite('lipsitch2010')}: here, records that agree with a death as often by chance as its candidates do and can never be the person. The births of "
        "the other sex on the same day in the same municipality are such records. The estimator built on them gave, for race at death after infancy, the table of "
        "race on the birth record by race on the certificate where no other source did.")
para(d, f"This study aimed {OBJECTIVE}: its assumptions and estimands, a variance that includes the denominator of each proportion, two validations against "
        "linked records with known answers, and a simulation study of its bias and coverage.")

d.add_heading("Methods", level=1)
para(d, f"Design and data. This is a {DESIGN}, reported according to the RECORD statement {cite('benchimol2015')} and, for the simulation, the ADEMP structure "
        f"{cite('morris2019')}. Live births came from the Live Birth Information System (SINASC), deaths from the Mortality Information System (SIM) and admissions "
        f"that ended in death from the Hospital Information System of the Unified Health System (SIH), all public files of the Ministry of Health {cite('datasus')}. "
        "The race on a birth record is the mother's declaration of her own race since the 2011 form; on a certificate it is recorded by the certifier or hospital staff.")
para(d, "The estimator. Let a group G hold units i (deaths) with key x_i (birth date, sex, municipality of residence) and class k_i in the first register (the race on "
        "the certificate), and let the second register hold records r with key x_r and class j_r (the race on the birth record). The candidates of i in class j are "
        "C_i(j), the records with x_r = x_i and j_r = j. Its control K_i(j) is the number of records of class j with the birth date and municipality of i and the "
        "other sex, times s_i, the ratio of the register's records of i's sex to those of the other sex in that municipality and birth year. The estimator is "
        "T(j, k) = sum over the units of G certified k of C_i(j) - K_i(j) (Figure 1). Three assumptions are used. (A1) The person's own record is among the "
        "candidates with a probability t_j that may depend on the class j but not, given j, on the class k: the person kept the key (did not move, and the birth date "
        "and municipality were recorded alike). (A2) Given the day and the municipality, the records of the two sexes have the same composition by class and stand "
        "in the ratio s: the chance candidates' expectation is the control's. (A3) A record related to the person and sharing the key is of the person's class: a "
        "twin of the same sex adds to the candidates, one of the other sex to the control, both in the person's own cell. Under A2 and A3 the expectation of "
        "T(j, k) is t_j N(j, k) plus a twins' term in the person's own cell, with N(j, k) the units of G by (j, k). Three quantities follow. The row T(j, k) / "
        "T(j, +) estimates P(k | j), how a class declared in the second register is recorded in the first, under A1-A3; as a ratio of sums it is consistent, "
        "with a small-sample bias in rows with few units. The row sums over T(+, +) estimate the declared mix, and a rate by declared class (row sum over "
        "person-years by that class) gives ratios between classes, both only if t_j is the same for all j; T(+, +) over the units of G is the share found, t, "
        "which counts only units found in one of the classes of the rows. No individual is linked, and the case of one candidate (the unique link) is included. A "
        "unit whose birth date or municipality differs between the registers is not among its candidates; it adds chance only, which its control removes.")
figure(d, "estimator_design", "Figure 1 - The estimator for one death: its candidates, its control and their difference",
       ["The same key (birth date, municipality of residence) with the other sex gives records that agree by chance as often and are never the person."])
para(d, "Variance. Four standard errors were compared (Supplementary Text S1), each by the delta method with a proportion's row sum, or a ratio's reference row, as "
        "denominator, and each counting together the units that share a key, which share their candidates. (i) Counts, the earlier practice: candidates plus "
        "control, over the row's sum as if the sum were known. (ii) Model: with the register's records Poisson, a cell is the people found plus the chance "
        "candidates less the control, the control's variance carrying its scale squared. (iii) Chance: the error in the table of these units only, in which the "
        "people found are fixed and only the chance agreements and the control vary. (iv) Clusters: Taylor linearisation with municipalities (pooled over years) "
        "as sampled units, which allows for dependence within a municipality and makes the variation of the classification between municipalities part of the error.")
para(d, f"Validation 1: infant deaths and their births. Infant deaths of {I['years'][0]}-{I['years'][1]} ({n0(I['certificates'])}) were linked to their birth records "
        f"by probabilistic linkage {cite('fellegi1969')} on birth date, sex, residence, birth weight and the mother's age; {pct(I['linked'] / I['certificates'])} were "
        f"linked, with an estimated {min(v['fdr_percent'] for v in lq_inf.values()):.2f}-{max(v['fdr_percent'] for v in lq_inf.values()):.2f}% of false links a year. "
        "The estimator was run on the same deaths with birth date, sex and municipality alone, and the twenty cells of the table (four races on the birth record by "
        "four races and none on the certificate) were compared with the linked pairs', and with the linked pairs whose birth record shares the estimator's key (the "
        "findable pairs), by the municipality's births a year. As a baseline, the candidates were also tabulated without the control.")
para(d, f"Validation 2: admissions that ended in death and their certificates. The {n0(PAIR['units'])} admissions of {PAIR['years'][0]}-{PAIR['years'][-1]} that "
        "ended in death in the year of the admission's end were the units, the death certificates of the same year the register, the race recorded by the hospital "
        "and the race on the certificate the two classes. The known answer was a probabilistic linkage of the two on birth date, sex, the day of death and the "
        f"hospital or its municipality, {min(v['fdr_percent'] for v in LQ.values()):.2f}-{max(v['fdr_percent'] for v in LQ.values()):.2f}% of false links a year, "
        f"{pct(PS['all']['linked_share'])} of the units linked, {min(v['died_in_hospital'] for v in LQ.values()):.1f}% or more of the linked certificates "
        "giving a hospital as the place of death. The estimator used birth date, sex and residence, and the year. Deaths change their sex ratio with age, so the "
        "control was scaled within birth year and municipality, and, as a check, within birth year and state. This pair differs from the first in the register "
        "(deaths of all ages instead of births), in who assigns the classes (hospital staff and certifiers), and in the density of chance agreements, which is lower; "
        "its known answer also tells which linked pairs share the estimator's key.")
para(d, "Simulation (ADEMP). Aims: bias and coverage of the estimator, and of its four errors, under departures from A1-A3. Data-generating mechanism: the 2018 "
        "birth cohort of every municipality by declared race, spread over days with a weekday and seasonal pattern (stronger on weekdays for White births); deaths "
        f"by declared race at the rates estimated at 1-9 years, {n0(SIM['deaths_target'])} in all as in 2013-2024, drawn from one cohort; the certified race drawn "
        "from the infant linkage's table for the decile of White births of the municipality where the death is certified (Supplementary Text S2). Scenarios: "
        "ideal (no departure); twins (2% of births twins, dying at twice the rate); movers (28% of children dying resident in another municipality of the state, "
        "certified there; the share found at 1-9 years implies about as many); unequal (movers 22% of White and 30-34% of other children); selective (movers "
        "22%, and 12 points more among the children certified in a class other than the declared one); sparse (as ideal, with a twelfth of the deaths, so that "
        "deaths sharing a day are as rare as in one real cohort); a2 (as ideal, with boys 52.5% of White and 50.5% of Black and Indigenous births, breaking A2). "
        "Estimands: P(k | j) for all deaths of a group of municipalities by size (the target) and for those found among their candidates; the declared mix; the "
        "White to Brown, Black to Brown and Indigenous to Brown rate ratios. Methods: the estimator and its four errors from the same package function as for "
        "the real data. Performance: bias with its Monte Carlo error (the standard deviation of estimate less truth over the replicates), empirical standard error, "
        "mean standard error, coverage of the 95% interval.")
para(d, "Unequal shares found. Where t differs between classes the declared mix and rate ratios are biased by the ratio of their t: a ratio between classes a and b "
        "estimates the true ratio times t_a / t_b. The data cannot identify the t_j without linked records; the size of the bias is shown by the simulation, as a "
        f"bias analysis {cite('lash2014')}. The limit of 25,600 births a year was chosen on the infant validation itself. Ethics: public, anonymised data; under "
        "Resolution 510/2016 of the National Health Council no review was required. Analysis code: the package pegasus_data (functions candidate_counts, "
        "pair_candidate_counts, candidate_estimates) and the scripts of the paper's repository.")
