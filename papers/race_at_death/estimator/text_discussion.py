# The Discussion of the estimator paper. Executed by build.py after text_results.py, whose names it uses.
# ruff: noqa: F821
d.add_heading("Discussion", level=1)
para(d, f"Main findings. The cross-classification of a variable recorded in two registers was estimated without linking any individual, from the birth date, sex "
        f"and municipality alone, by subtracting the other sex's records of the same day as a negative control. Against linked records it reproduced the table: "
        f"within {pp(v25['against_linkage']['mean_abs_diff'])} on average over the cells for infant deaths in municipalities under 25,600 births a year, where the "
        f"candidates without the control missed by {pp(v25['against_linkage']['nocontrol_mean_abs_diff'])}, and within "
        f"{pp(pair_all['against_findable']['max_abs_diff'])} of the linked certificates that shared the key for admissions that ended in death. {SIM_FINDING}")
para(d, "What is estimated. The estimator describes the people whose key the two registers share. Its own error is that of the chance agreements; its bias is the "
        "difference between those people and the rest. In the admissions, the linked certificates that did not share the key were classified differently from those "
        f"that did, by {pp(gap * 100, 0)} percentage points for White, so the estimate departed from the full linked table by "
        f"{pp(pair_all['against_linked']['mean_abs_diff'])} on average while matching the findable pairs almost exactly. A linkage that uses other fields (the day "
        "of death, the hospital) reaches people the estimator cannot, and comparing linked and unlinked records is the way to see who they are "
        f"{cite('harron2017')}. Without such a linkage the size of this bias is not identified. After infancy, the people not found are mostly children whose "
        "families moved, or whose birth date or municipality was recorded differently; in the simulation their departure was small when moving was unrelated to "
        "the class recorded, because their certification differed only through the gradient of classification between places that was put into it, and it was "
        "several times larger when moving followed the class recorded. The simulation shows the mechanism, not its size in the data. It is not a property of the "
        "estimator but of the key, and is shared by any linkage on the same key.")
para(d, "Comparison with linkage methods. Regression on linked data can be corrected when the probability that each pair is a true link is known or modelled "
        f"{cite('lahiri2005')}, and with partially identifying variables unbiased coefficients required removing all wrong pairs {cite('hof2012')}. The estimator removes "
        "them in expectation instead of one by one: the false agreements are counted where they can be counted, among records that cannot be the person, and the "
        f"count is subtracted, where linkage estimates its false-match rate from a model of the match weights {cite('belin1995')}. Like multiple imputation over all "
        f"candidate records {cite('goldstein2012')} it uses every candidate, but it needs no model of which candidate is the person. Its price is that it gives tables, "
        "not linked records: no individual covariate of one register can be related to the other's beyond the classes counted, though any class of either register "
        "can be added to the counting (the certifier, the mother's schooling).")
para(d, "Variance. The earlier practice took each cell's counts as Poisson and ignored the row's sum in the denominator of a proportion; its intervals were too wide "
        "for common cells and too narrow for rare ones. With the denominator, the shared keys and the control's scale, the model interval covered nominally in the "
        "simulation. The chance interval answers another question, the distance from a perfect linkage of the same units, and covered nominally in the simulation, "
        "where that linkage is known. In the real validations it was narrower than the error of the known answers themselves (about 1% of false links, units "
        "linked or not, the key compared on the linked fields), so the cells it excluded test the known answer as much as the estimator. The cluster error treats "
        "the municipalities as a sample of places; because the classification varies between them, it was several times the "
        "model error for the admissions. For a national table, in which every municipality is present, the model error is the one to report.")
RB = PAIR["register_by_sex"]
assert RB["15-29|M"]["white"] < RB["15-29|F"]["white"] - 0.05 and RB["15-29|M"]["deaths"] > 3 * RB["15-29|F"]["deaths"], "young men's certificates no longer differ"
para(d, f"Assumptions. A2 requires that the two sexes born on a day share the composition by class and the sex ratio of the municipality and year. For births this is "
        f"nearly exact; in the simulation a two-point difference in the share of boys between White and Black births biased the White to Brown ratio by "
        f"{sg(a2['all']['ratio_white']['bias'])}. For a register of deaths of all ages it is not exact: in 2019, {pct(RB['15-29|M']['white'])} of the certificates "
        f"of men aged 15-29 gave White against {pct(RB['15-29|F']['white'])} of women's, and men's were {RB['15-29|M']['deaths'] / RB['15-29|F']['deaths']:.1f} "
        f"times as many, against {RB['60+|M']['deaths'] / RB['60+|F']['deaths']:.2f} at 60 or more. In the admissions the chance candidates were few, and scaling "
        "within the municipality or the state changed nothing; with many chance candidates in such a register, the control should be scaled within finer strata "
        "(age as well as place). A1 fails when moving, or the recording of the birth date and municipality, depends on the class recorded given the class "
        "declared. Unequal shares found by declared class leave the proportions unbiased and scale the rate ratios by the ratio of the shares; the data cannot "
        "identify them without linked records.")
FA = [v["found"] for k, v in R["children_by_age"].items() if 1 <= int(k) <= 12]
para(d, f"Limitations. First, neither validation tests the setting in which the estimator is needed: at 1-12 years {pct(1 - max(FA), 0)}-{pct(1 - min(FA), 0)} "
        f"of deaths are not found, by moving or by recording in proportions unknown, against {pct(1 - v_all['found']['est'], 0)} of infant deaths; there the "
        "simulation stands in. Second, above 25,600 births a year (seven municipalities) the chance candidates swamp the person and the estimates fail; the limit was chosen on "
        "the infant validation itself, and results without those municipalities should be given beside national ones. Classes rare among the units and "
        "common among the chance candidates (Indigenous deaths where Indigenous births are few) have unstable rows. Third, the simulation's world was built from the "
        "real births and the linked infants' classification, but its municipalities are fixed, the movers' destinations, the differential moving and the twins' "
        "mortality were set, not measured, and the heterogeneity of classification between municipalities is only the decile gradient, so it cannot tell whether "
        "the cluster error is right. Fourth, the known answers are themselves linkages with about 1% of false links. The paper makes no statement about race; that "
        "is left to the papers that use the estimator.")
para(d, "Use. Wherever two public registers share a date of birth, a sex and a place but no identifier, as Brazilian death certificates after infancy do with birth "
        "records, the table between them can be estimated, with its variance, for the people who kept the key. The functions are released with the data package, and "
        "the companion papers on race at death after infancy rest on them.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Candidates less the other sex's records of the same day reproduced linked tables between births and deaths and "
        "between admissions and certificates, without linking anyone. The estimate is of the people whose key the registers share, with the error of the chance "
        "agreements and the denominator; its bias is the selection of those people, which a key without identifiers cannot avoid and the public files cannot measure.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
