# Response to audit 1 - paper 3, `black_category/`

Every error in section 1 is fixed in the analysis (`analysis/black.py`, `analysis/counts.py delivery`) or the text, and the claims are now held by asserts in `text_results.py`.

| Item | What was done |
|---|---|
| E1 practice on the wrong hospital | `counts.py delivery` now carries `delivery_facility` for each linked infant. The model joins practice to the delivery hospital (`facility_model_delivery`: 12,988 deaths, 1,040 hospitals; OR 1.36 alone, 1.20 (1.14; 1.26) adjusted). 75% of Black mothers' infants died where they were delivered (stated). The old death-hospital model stays in the JSON; it is not cited. |
| E2 gross, not net | Net counts added (`net`). Hospital 697,191 recorded Black against 939,740 declared (0.74). Certificate 7,560 against 22,305 (0.34); Brown mothers' infants certified Black 1.6%. The undercount claim now rests on the net certificate ratio. The Discussion explains the small-into-large asymmetry. The declaration-as-reference limitation is stated. |
| E3 denominators | Blank share (21.8%) and the share with blanks counted (0.28) are in Results and the Table 1 note. The note says the populations and years differ between rows. |
| E4 hospital intervals | Bootstrap over hospitals: Black 0.36 (0.33; 0.39), Brown 0.53 (0.49; 0.56), White 0.10 (0.09; 0.11). Used in the Abstract, Results, Table 1 and Figure 1. |
| E5 "fastest in the South" | Removed. Results give the slope range and say no region differed clearly. The Figure 4B caption says the lines are conditional fits, not proportions. |
| E6 "stayed the same" | Replaced by the hospital trend on the certificate's scale: +0.11 (0.05; 0.17) log-odds per decade, quasi-binomial on yearly counts, against +0.42. An assert holds hospital < certificate. |
| E7 ladder not comparable | Infants re-estimated in the estimator's municipalities (under 25,600 births): 0.18 (0.17; 0.18), below 1-4 (0.24) and 5-9 (0.29). Asserted, and a new bar in Figure 1. The family is now context only, not the basis of "the younger the child". |
| E8 selection | Black mothers' infants with and without a delivery record are certified Black alike (0.19 vs 0.18; asserted). The Yellow-default exclusion now applies to all analyses. An undetected Brown default is a stated limitation. |
| 2.1 crude individual association | Within-delivery-hospital Mantel-Haenszel OR 2.04 (1.80; 2.32), 443 hospitals. The White-recorded non-monotonicity is reported in Results; it is not interpreted. |
| 2.2 facility correlation | Both given: 0.47 unweighted, 0.52 weighted by deaths. |
| 2.3 state vs composition | Parameters stated (26 vs 3). Equal-df comparison not done; the claim is not used in the Discussion. |
| 2.4 multiplicity | Two primary analyses are named in Methods: the infant against the declaration, and against the hospital's record. The rest is labelled exploratory. "For the same kind of death" is removed. |
| 2.5 shared appearance | The Discussion now opens the explanations with shared perception. It fits the within-hospital association, which a hospital-wide practice cannot produce. Practice remains partly confounded with it. |
| 2.6 year attribution | Stated in Methods and in the Figure 4C caption. |
| 2.7 methods | Added: delivery-link quality (linked share 0.53-0.61, false links 0.65-0.92%, obstetric 96.6-98.8%, residence 95.7-97.5%), the spline and standardised terms, the PC priors, the +0.01 smoothing and the facility spline. Unlinked deaths are not characterised further: paper 1 does that. |
| 2.8 numbering | Supplementary tables renumbered and reordered by citation: S1 women, S2 by hospital record, S3 hospital matrix, S4 multilevel. |
| 2.9 abstract | The model description is corrected (within hospitals; logistic with clustered errors; multilevel). "Per logit unit" is defined in Results and kept out of the Abstract. |
| 2.10 census SE | The note says the standard errors treat the sample as simple. |
| 2.11 interpretation in Results | "Without reaching it" and "carried over" are removed. |
| Minor | Figure 4: the panel A title is shortened, panel C has a y label and its legend is moved. Figure 1: the hospital bar has a visible bootstrap interval, and the caption says the reference bar is 1 by construction. Figure 2B caption: the 10-death minimum is given. Moran's I is named for the residual. "No study was found" becomes "We know of no study". |
| References | [9]: the 2022 manual is verified in full text (`reading_report.md` B, item b). Cardoso: reworded to what the reading supports, rates underestimated, most for Brown children. Monk and Daflon: softened to what their abstracts say. Freeman: the coincidence is stated without a causal test. |
