# The Discussion of the estimator paper. Executed by build.py after text_results.py, whose names it uses.
# ruff: noqa: F821
d.add_heading("Discussion", level=1)
para(d, f"Main findings. The cross-classification of a variable recorded in two registers was estimated without linking any individual, from the birth date, sex "
        f"and municipality alone, by subtracting the other sex's records of the same day as a negative control. On the units a linkage paired it agreed with the linked "
        f"table within {pp(l25['mean_abs_diff'])} on average over the cells for infant deaths in municipalities under 25,600 births a year, where the candidates without "
        f"the control missed by {pp(l25['nocontrol_mean_abs_diff'])}, and within {pp(pair_l['max_abs_diff'])} in every cell for admissions that ended in death. A "
        f"shifted key date found nothing. Against its target, the people the key finds, the intervals were adequate for infants ({l25['outside_model']} of "
        f"{l25['cells']} cells outside the model interval) and for admissions ({pair_t['outside_model']} of {pair_t['cells']}); the admissions' linked table "
        f"departed from that target by about {pp(pair_l['mean_abs_diff'] - pair_t['mean_abs_diff'])}, the selection of who shares the key. {SIM_FINDING}")
para(d, f"What is estimated. The estimator describes the people whose key the two registers share, and A1 does not hold for them: findability fell from "
        f"{pct(t_cls['Branca'], 0)} for certified White to {pct(t_cls['Indigena'], 0)} for Indigenous admissions and depended on the class the hospital recorded. Its bias is "
        "therefore the selection of who shares the key, in part a property of the estimator's weighting (it weights each person by the probability of being found) "
        "and in part of the key. Where linked data exist it is measurable, as here; a linkage that uses other fields (the day of death, the hospital) reaches people "
        f"the estimator cannot, and comparing linked and unlinked records is the way to see who they are {cite('harron2017')}. Run on all units the infants' table "
        f"departed from the linked one by {pp(a25['mean_abs_diff'])} against {pp(l25['mean_abs_diff'])} on the linked units; in the admissions the units whose "
        f"certificate shared the key differed from the rest by {pp(raw_gap * 100, 1)} percentage points in White recorded White, but {pp(known_gap * 100, 1)} once the "
        f"hospital's missing race is set aside: about {pp((raw_gap - known_gap) * 100, 1)} points are extra missing race among the unfindable. The unfindable are "
        "therefore partly units with missing race, which suggests records kept less carefully; whether the rest are movers or recording errors was not tested "
        "(their age, cause and municipality were not profiled). After "
        "infancy, whether the people not found are children whose families moved, or whose birth date or municipality was recorded differently, cannot be told from these "
        "data; in the simulation the departure was small when moving was unrelated to the class recorded, because certification differed only through the gradient of "
        "classification between places that was put into it, and several times larger when moving followed the class recorded. The simulation shows the mechanism, not "
        "its size in the data.")
para(d, "Comparison with linkage methods and ecological inference. Regression on linked data can be corrected when the probability that each pair is a true link is "
        f"known or modelled {cite('lahiri2005')}, and with partially identifying variables unbiased coefficients required removing all wrong pairs {cite('hof2012')}. The "
        "estimator removes them in expectation instead of one by one: the false agreements are counted where they can be counted, among records that cannot be the "
        f"person, and the count is subtracted, where linkage estimates its false-match rate from a model of the match weights {cite('belin1995')}. Like multiple "
        f"imputation over all candidate records {cite('goldstein2012')} it uses every candidate, but it needs no model of which candidate is the person; unlike a "
        "latent-link likelihood over each death's candidate set it gives a unit with one candidate the weight of a unit with thirty-six, which is why it fails where "
        "the key is shared by many births. It is closest in spirit to ecological regression "
        f"{cite('goodman1953', 'wakefield2004')}, whose Goodman form, on the same cells, had {pp(cmpi['comparators']['goodman']['mean_abs_diff'] / cmpi['against_linked']['mean_abs_diff'], 1)} "
        "times the estimator's mean difference for infants below 25,600 births a year. Its price relative to linkage is that it gives tables, not linked records: no "
        "individual covariate of one register can be related to the other's beyond the classes counted, though any class of either register can be added to the counting "
        "(the certifier, the mother's schooling). The closest published method fits a contingency table by maximum likelihood from incorrectly linked data "
        f"{cite('chipperfield2011')}: it starts from record pairs already formed by a linkage, estimates from a clerically reviewed sample the probability that "
        "a link is correct in each cell, and replaces each linked pair's class with its expectation given that probability, iterating by EM; it assumes links "
        "are incorrect at random, independent of the outcome given the other file's class, and treats unlinked records as non-response "
        f"{cite('chipperfield2015', 'chambers2020')}. Where the key is shared by several births "
        "no pair is formed and no match probability is modelled, so it cannot be run on the same units; the estimator replaces the match model by the other "
        "sex's records of the same day as the measure of chance agreement.")
para(d, "Variance. The earlier practice took each cell's counts as Poisson and ignored the row's sum in the denominator of a proportion; its intervals were too wide "
        f"for common cells and too narrow for rare ones. With the denominator, the shared keys and the control's scale, the model interval was conservative or close to "
        f"nominal in the simulation up to 6,400 births a year ({pct(cm_lo, 0)}-{pct(cm_hi, 0)} against a Monte Carlo band of +/-{pp(cov_mcse * 100, 1)} points) and "
        f"conservative in the pooled classes, where the mean model standard error was {pp(SE_RATIO['all'], 2)} times the empirical one. These coverages hold "
        "where the assumptions hold; where they break, coverage of the people of the whole table fell, to "
        f"{min(SR['selective'][s][q]['cover_super_model'] for s in SMALL for q in P_CELLS):.2f} at worst when moving depended on the class recorded and "
        f"{min(SR['keyerr_k'][s][q]['cover_super_model'] for s in SMALL for q in P_CELLS):.2f} when key errors depended on it. On the real units, against its "
        f"target, the z-scores of the cells had a standard deviation of {pp(l25['z_sd_model'], 2)} (infants) and {pp(pair_t['z_sd_model'], 2)} (admissions); against "
        f"the whole linked admissions table it was {pp(pair_l['z_sd_model'], 2)}, because the units are so many that the selection of who shares the key, small as "
        "it is, dwarfs the sampling error. By size class among infants, the model interval missed "
        + ", ".join(f"{SZ_INF[s]['outside_model']} of 20 cells at {s}" for s in SZ_INF)
        + "; the limit of 25,600 births a year was chosen on the same data. The shifted-date placebo shows how an "
        f"empirical null could calibrate the intervals {cite('schuemie2014', 'schuemie2018')}: its z-scores had a standard deviation of "
        f"{min(zsd['<25,600']):.2f}-{max(zsd['<25,600']):.2f}, close to 1, so the interval is right for chance. The chance interval answers "
        "another question, the distance from a perfect linkage of the same units. The cluster error treats the municipalities as a sample of places and includes the "
        "variation of the classification between them; it exceeded the model error for the admissions, possibly because the classification varies between municipalities, "
        "which a simulation without a municipality effect cannot test. Which error to report for a national table is therefore left open until the intervals are "
        "calibrated on real data.")
RB = PAIR["register_by_sex"]
assert RB["15-29|M"]["white"] < RB["15-29|F"]["white"] - 0.05 and RB["15-29|M"]["deaths"] > 3 * RB["15-29|F"]["deaths"], "young men's certificates no longer differ"
para(d, f"Assumptions. A2 requires that the two sexes born on a day share the composition by class and the sex ratio of the municipality and year. For births the sex ratio "
        f"is nearly constant, and the sexes' day-to-day excess variation is almost wholly shared (in SINASC 2018 each sex's daily births' variance beyond Poisson was {pp(E['births_dispersion']['all']['phi'], 4)} "
        f"of the mean squared, and the part shared by the two sexes {pp(E['births_dispersion']['all']['psi'], 4)}); in the simulation a two-point difference in the share of boys between White and Black births biased the White to Brown ratio by "
        f"{sg(a2['all']['ratio_white']['bias'])}. For a register of deaths of all ages it is not exact: in 2019, {pct(RB['15-29|M']['white'])} of the certificates "
        f"of men aged 15-29 gave White against {pct(RB['15-29|F']['white'])} of women's, and men's were {RB['15-29|M']['deaths'] / RB['15-29|F']['deaths']:.1f} "
        f"times as many, against {RB['60+|M']['deaths'] / RB['60+|F']['deaths']:.2f} at 60 or more. In the admissions the chance candidates were few, and scaling "
        "within the municipality or the state changed nothing; with many chance candidates in such a register, the control should be scaled within finer strata "
        "(age as well as place). A1 fails when moving, or the recording of the birth date and municipality, depends on the class recorded given the class "
        "declared. Unequal shares found by declared class leave the proportions unbiased and scale the rate ratios by the ratio of the shares; the data cannot "
        "identify them without linked records, but linked data do give them (Results).")
FA = [v["found"] for k, v in R["children_by_age"].items() if 1 <= int(k) <= 12]
para(d, f"Limitations. First, neither validation tests the setting in which the estimator is needed, so it is validated for infant and hospital deaths and not yet for ages 1-14: at 1-12 years {pct(1 - max(FA), 0)}-{pct(1 - min(FA), 0)} "
        f"of deaths are not found, by moving or by recording in proportions unknown, against {pct(1 - LI['all']['variants']['all']['found']['est'], 0)} of infant deaths; there the "
        "simulation stands in. Second, above 25,600 births a year (seven municipalities) the chance candidates swamp the person and the estimates fail; the limit was chosen on "
        "the infant validation itself, and results without those municipalities should be given beside national ones. Classes rare among the units and "
        "common among the chance candidates (Indigenous deaths where Indigenous births are few) have unstable rows. Third, the simulation's world was built from the "
        "real births and the linked infants' classification, but its municipalities are fixed, the movers' destinations, the differential moving and the twins' "
        "mortality were set, not measured, and the heterogeneity of classification between municipalities is only the decile gradient, so it cannot tell whether "
        "the cluster error is right. Fourth, the known answers are themselves linkages with about 1% of false links. The paper makes no statement about race; that "
        "is left to the papers that use the estimator. Fifth, the working limit is not a municipality's size but the expected chance candidates per unit, which the limit of 25,600 births a year only approximates; combining key cells by inverse variance, instead of discarding the largest municipalities, was not attempted. Sixth, the rare Indigenous row is unreliable above 1,600 births a year.")
_BVC = _json.loads((HERE / "results" / "birth_vs_census.json").read_text(encoding="utf-8")) if "_json" in globals() else __import__("json").loads((HERE / "results" / "birth_vs_census.json").read_text(encoding="utf-8"))
_HD = __import__("json").loads((HERE / "results" / "hospital_declaration.json").read_text(encoding="utf-8"))
_SL = _BVC["mothers_2010"]["W"]["slope_region"]["slope"]
_H0 = _HD["by_practice_fifth"][0]
assert _SL > 1 and _H0["dn_black"] < 0.6 * _H0["expected_black"], "the two findings about the reference changed: rewrite the paragraph on the reference"
para(d, f"The reference. Two findings of the companion papers weaken the birth record as the reference: it leans toward the local majority, recording mothers whiter than the census in whiter places and less White in less White ones (logit slope {_SL:.2f} within regions, 1 if it followed the census), and where hospitals rarely record Black on the admission it counts about half the Black mothers the census holds ({100 * _H0['dn_black']:.1f}% against {100 * _H0['expected_black']:.1f}%). "
        "For the estimator, these concern what the table means, not how well it is estimated: it reproduces the birth record's classification, "
        "whatever its departures from self-declaration.")
para(d, "Use. Where two public registers share a date of birth, a sex and a place but no identifier, as Brazilian death certificates after infancy do with birth "
        "records, the table between them can be estimated, with its variance, for the people who kept the key, provided the expected chance candidates per unit are few "
        "(here, municipalities under 25,600 births a year). It is validated for infants and hospital deaths and not yet for ages 1-14. The functions are released with "
        "the data package.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Candidates less the other sex's records of the same day reproduced linked tables between births and deaths and "
        "between admissions and certificates on the units that were linked, without linking anyone, and found nothing when the key date was shifted. The estimate is of "
        "the people whose key the registers share, with the error of the chance agreements and the denominator, an interval that held for both infants and "
        "admissions against that target; its bias is "
        "the selection of those people, measurable only where a linkage with other fields exists.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
