# Audit report 3: race at death (manuscript.txt, supplement.txt, figures 1-9, results.json, spatial.json)

Scope: numbers recomputed from the JSON with est ± 1.96·se (ratios on the log scale); verbal claims checked against JSON and generator code (`text*.py`, `analysis/spatial.py`, `analysis/models.R`); figures 1-9 viewed (S1-S10 not viewed individually; only their captions and citation order were checked); references checked against `reading_report.md`. Not done: Table S-series cell-by-cell recomputation.

## 1. Errors (must fix)

E1. **Regional slope mislabelled.** Results "Time and place": "from 0.19 per decade in the Southeast to 0.99 in the South". `models.R` l.101 builds `macro` with North as first level, so `by_macro['yc']` (0.192) is the **North** slope. The Southeast slope is 0.192+0.023 = 0.215 and the lowest is the North. `text_results.py` l.188-200 should say "North" (or the slope of the lowest region should be computed).

E2. **"The certifiers did not differ within one kind of cause"** (Results, ages 15-24). Table 5/JSON: external-not-assault, physician 0.43 (0.34; 0.51) vs medical examiner 0.60 (0.57; 0.63), difference 0.17, z about 3.6, and in the direction opposite to the mechanism. The build asserts only the natural-cause contrast (l.299). For natural causes (0.69 vs 0.58, ME n=2,163, se 0.07) and assault (0.40 (0.24; 0.56) vs 0.37) the intervals are 0.15-0.30 wide: "did not differ" is non-significance read as equivalence. The Discussion repeats it ("physicians and medical examiners did not differ within natural deaths"). Fix: state the three contrasts, report that external-not-assault differs, and say the data cannot exclude 10-point differences.

E3. **"Composition explained most; the state explained part of what remained" and "continuous surface".** Results/Table 3: state alone explains 75%, composition alone 71%; composition given state adds 6 points (81% vs 75%), state given composition 10 points. For Black mothers state (37%) exceeds composition (22%). The border slope 0.46 (0.32; 0.59) excludes 0, i.e. a step at borders. Yet the Discussion says composition "explained most", the certificate "moved ... as a continuous surface ... across state borders as well as within states", and the README thesis says "continuously across ... state borders". These are contradicted by the paper's own results; the state (26 df) vs composition (3 df) comparison is also not df-matched. Reword: composition and state each explain about three quarters, jointly 81%; the data fit neither a pure surface nor pure state practice.

E4. **"Reversed in 400 of 510 immediate regions" (Abstract) and "reversed ... in most regions of the country" (Conclusion)** rest on posterior means. Credible reversal (mother's ratio <1 and certified >1, both intervals excluding 1) is 114 regions (22%); this figure appears only in Results. Abstract and Conclusion must carry it.

E5. **Compositional measure shares its classification practice with the outcome.** Composition = share of White mothers on the birth record, a staff-completed field; the outcome is the certified race of Brown mothers' infants. If registry/hospital staff classify by local norms, composition and outcome both carry that practice, so "composition explains 71%" can partly be one classification system correlated with itself. Limitation (4) mentions only the cohort mismatch. No sensitivity with an independent composition (the census 2010 municipal race shares are in `municipal_context.parquet`) is reported. Add it or state the limitation; the abstract's "classification of place ... more than wealth or services" is also a comparison between a precisely measured regressor and noisy proxies (GDP per capita, illiteracy), which favours composition.

E6. **Establishment random effect over-read** (Results; Discussion "the classification belongs ... to the institution"). `models.R` l.164 recodes deaths without a registered establishment to `none_<municipality>`, so for home/street deaths the establishment effect equals the municipality effect; for municipalities with one hospital the two levels are not separable. The sentence "What composition and context left was mostly not between municipalities but between establishments" compares 0.29 (establishment level, estimated after region/year/individual terms) with 0.03 (municipality level, residual after the establishment term absorbs it), not a partition of the 0.115 left by the full model. A hospital's catchment composition is also unmeasured. Say only that residual clustering is better captured by establishments, not that it "lay between" them.

E7. **Individual-level terms explain almost as much municipal variance as composition and this is not reported** (JSON `individual_only`: PCV 0.74 for Brown/White vs composition 0.87; 0.78 for White/White). Certifier, place of death, age at death, schooling, birth weight and region vary systematically by municipality, so part of the "place" effect is case mix. Results mention only the 91% for the full model. Report `individual_only` in the text and Table S12 and temper "classification of place".

## 2. Points to fix

P1. **Border test logic and inference.** (a) State effects are estimated from interior municipalities (those touching no other state); small states have few, and unstable effects (Black outcome: sd of state effects 3.93, slope 0.03, 357 pairs; not reported, yet the Discussion says the Black category "depended on the state more than on composition"). (b) Regression dilution of the estimated state effects biases the slope towards 0; the "half a step" reading is a lower bound, not a mixture of "local" and "administrative". (c) The CI uses HC1 SEs on pairs that share municipalities and run along common borders; no cluster-robust SE by border segment. (d) The disagreement outcome gives 0.35, also unreported. (e) "Neither a purely local ... nor a purely administrative one fits" is fine for the point estimate but "half is a gradient shared with the neighbouring state" is interpretation, not result.

P2. **Deviance explained and F tests.** The null deviance (28,457 on 3,458 df, dispersion 8.4) includes binomial noise; the explainable ceiling is about 88%, so 81% for composition+state is near ceiling and "context added 1%" is compressed. Abstract writes "composition explained 71% of it" where "it" is the between-municipality variance, but 71% is deviance; the multilevel 87% is variance (PCV). Label them differently in the Abstract. F = 325 and 66.8 assume independent residuals while residual Moran's I is still 0.15-0.29; p-values are anti-conservative. Printed "p = 0.001" for Moran (999 permutations) is the floor; write p ≤ 0.001.

P3. **nAGQ = 0.** Methods give nAGQ=0 but not its consequence: PIRLS-only estimates bias variance components and fixed effects (here municipal variance 1.3), so PCV, MOR and odds ratios (Fig 5B, "full_laplace" in JSON is also nAGQ=0, the key is misleading) are approximate. The code comment reports that a Laplace refit did not converge in 13 minutes; this and a sensitivity (one outcome with INLA or nAGQ=1 on a subset) should be stated. The multilevel columns also use linear context terms against a 3-df spline for composition.

P4. **BYM2 phi.** "The BYM2 model attributed 99% of it to the structured component": phi is a mixing parameter estimated here by empirical-Bayes/Gaussian approximation, with sd 0.01; it is not a variance share of observed data and says nothing about causal "spatial" origin. Phrase as model estimate. The 4.9× variance ratio compares smoothed fields from counts of very different size (median 8 deaths vs 151 census children per municipality); shrinkage differs and the family series is ages 0-9, the certificate age 0. LISA: significance threshold (p<0.05, no multiplicity control) appears only in the Fig 3D title, not Methods; 1,466 "clusters" among 3,459 units are expected partly by chance and by spatial dependence.

P5. **Ecological/causal wording.** Abstract/Conclusion: "it is a classification of place: it follows the racial composition ... more than wealth or services"; Discussion: "What the data support is the third reading, a classification made by whoever fills the certificate". Municipal-level associations cannot say who classifies (limitation 5 says so) nor exclude the informant or the mother's category heterogeneity by place. Place effects within state (Fig 4D) are described as "follows their composition" without a test: at equal composition 30-59% the metropolitan non-capital is 0.47 vs capital 0.38 and interior 0.39 (`comp_place`).

P6. **Mortality section.** Discussion: "the household's classification of infants moves births between White and Brown in roughly the proportions in which the certificate moves deaths" is a mechanism inferred from one ratio (0.80 vs 0.79) and the population account is not documented (ref 41 is IBGE's projection, which has no race breakdown; see 6). "Misstated most where White births were fewest" in the Abstract and Conclusion hides that the relation is U-shaped (3.15, 1.92, 1.83, 2.19 by class) and based on 4 classes; the mechanism "a small share ... inflates a small White rate" is not tested. "Compressed toward 1 ... reversed" depends on the choice of denominator (acknowledged).

P7. **Time section.** "In the probability scale it was largest in the intermediate regions where the category was already most used": Fig 6B shows the opposite at the top end (regions with 0.3-0.4 in 2013 change between -0.04 and +0.08; the largest changes are at 0.2-0.38). A logit slope necessarily gives larger probability changes near 0.5; not evidence. Correlation of random intercept and slope (-0.31) is partly regression to the mean; the agreement slope 0.06 (se 0.03) has p = 0.051 and is described as "changed". Discussion still ties the Black rise to the census trend with no label as speculation (audit 2 P9 not fixed).

P8. **Discussion.** "three times the proportion for the infants of Black mothers: the scarcity of the category is sharpest for small children" compares adult women dying in hospital in small municipalities (exploratory) with infants; selection and period differ. "Wealth ... explained little that composition did not": GDP within <30% composition goes 0.15 to 0.23 (non-overlapping even with 10× wider intervals); say "less than composition".

P9. **Intervals.** Place, GDP-tertile and composition proportions (Results "Composition, state and context") are binomial, e.g. "0.30 (95%CI 0.30; 0.30)", although Methods states binomial intervals are 3-10 times too narrow. Use the bootstrap there or omit intervals.

P10. **Resolution claim.** "municipal resolution is therefore supported for the children of Brown and White mothers": `resolution` has no entry for White mothers' certified-White; the White-mother outcome shown (WP) has median 3 deaths and interval width 0.29.

## 3. Minor

M1. Figure 1 is not cited in the text (only its caption); Methods do not mention it. Supplementary Tables S3, S4, S6, S7, S9, S13 are never cited in the main text; supplementary items are cited out of order (Fig S10 before S9; Table S12, S14, S5, S15, S16, S8 in non-numerical order; Fig S6 before S2).
M2. Fig 3D title "Local clusters of the raw rate" vs caption "empirical-Bayes proportion" and Methods (EB). Fig 3A/B use viridis (colour-blind safe) but the 0-0.8 scale clips the Rio Grande do Sul values.
M3. Fig 4: legend line in C ("jump as large as the states' difference") runs into the y-label of D; D has no legend for the Black/Brown/White colours' relation to the text (the White-mother values 0.69-0.81 are not in the text); B puts Moran's I and deviance explained on one 0-1 axis without a second axis label. Legend of A is crossed by the dashed line.
M4. Fig 7A-C: x tick labels "mother" and "certificate" overprint ("mothercertificate"); the "race by" label sits below. D uses y-order under 1 y/1-4 y/5-9 y but markers are not aligned to labels.
M5. Fig 8A/B: scale truncated at 3, panel B is almost entirely saturated brown in the North and Northeast (information lost); panel D legend line overlaps the lowest points.
M6. Fig 6B/C: colour for macro-regions (B) not repeated in C; D colour bar starts at 0.4 although values go below (RN 2013 appears darkest).
M7. Methods do not describe: GDP tertiles; capital/metropolitan/interior classification used in Fig 4D; the sensitivity analysis on t (±10 points); Rebouças crude ratios (computed from Table 2 of that paper); the construction of the "census-based population account" ([41] cited for it); how infant ratios by family classification were interval-less. Moran's I significance threshold for LISA absent.
M8. Methods "383,975 certificates" vs Results "383,971 infant certificates" vs 381,514 candidate deaths (JSON `flow`: lake 383,971; with sex and municipality 381,511; candidate_deaths 381,514). Four deaths unexplained (carried from audit 2, P4b).
M9. Table 2 note "standard errors below 0.005" but the family cells for Black/Indigenous mothers are not checked in the note; Table 5 shows "0.91 (0.81; 1.01)" with an upper bound above 1 (note should say intervals can exceed 1).
M10. Keywords/abstract mix "reversed" and "reversed or compresses"; Abstract "(0.94 over the census-based population)" is unlabelled (1-4 years, 2016-2024).
M11. R-INLA, esda/PySAL and statsmodels are named but only lme4 is cited; add Lindgren and Rue (R-INLA) and Rey and Anselin (PySAL).

## 4. Previous points (audit 2) not fixed or only partly fixed

- E3 certifier: removed from Abstract and Conclusion; the Results/Discussion statement "certifiers did not differ" is false for one cell (new E2 above).
- P3 intervals: main proportions bootstrapped; place/GDP/composition proportions still binomial (P9 above).
- P4(d) linkage weights and threshold, and (e) per-step flow at 1-9 and 15-24: stated by the response as "not done"; still absent.
- P9 Black trend and census trend: still linked in the Discussion without a speculation label.
- P6 composition measure: limitation added only for cohort mismatch; the shared-classification problem is not addressed (E5).
- P15/P5 mother's-race quality: limitation (3) added; no sensitivity.
- M-points: Fig 7 labels still overlap (M11 of audit 2 persisted in a new form); Fig 3D/Fig 8 clipped scale.
- Audit 2 "383,975 vs 381,514": still unexplained.
Fixed and verified in the built text: E1 (title, Fig 1 two-level), E2 (age gap computed: 8 of 10 ages; figure moved), E4, E5, E7, E8, E9 (statement removed), E10, P1 (conventional denominator), P2 (mixture to supplement), P8 (Rebouças crude rates), P12 ("partner"), P17-P21.

## 5. Numbers recomputed (location; printed; recomputed; status)

1. Abstract/Results, White mothers certified White (bootstrap); 0.76 (0.75; 0.78); 0.763 (0.749; 0.777); ok
2. Brown/Brown; 0.64 (0.62; 0.66); 0.641 (0.621; 0.661); ok
3. Black/Black; 0.18 (0.17; 0.20); 0.184 (0.169; 0.198); ok
4. Brown>White; 0.25 (0.23; 0.27); 0.252 (0.231; 0.273); ok
5. Black>Brown; 0.55 (0.53; 0.57); 0.548 (0.527; 0.570); ok
6. Abstract, 296,512 linked; JSON linked_with_race 296,512; ok
7. Abstract, range 0.09 to 0.76; p5 0.091, p95 0.760; ok
8. Abstract, variance ratio 5; 1.382/0.284 = 4.87; ok (4.9 in Results)
9. Moran's I 0.77; 0.7703; ok
10. Deviance explained composition 71%, context 42%; 0.711, 0.420; ok
11. Multilevel 87% and 60%; 0.870, 0.596; ok
12. Border slope 0.46 (0.32; 0.59); 0.455±1.96·0.0688 = 0.321; 0.590; ok
13. Infant ratio 0.79 (0.75; 0.84); 0.794 (0.751; 0.840); ok
14. Certified 1.31 (1.30; 1.32); 1.310 (1.301; 1.319); ok
15. 1-4 y ratios 0.66 (0.54; 0.81), 1.43 (1.40; 1.45); 0.663 (0.543; 0.810), 1.427 (1.403; 1.452); ok
16. 0.94 census-based; 0.944; ok
17. 15-24 natural 0.68 (0.64; 0.71), firearm 0.35 (0.31; 0.39); 0.675 (0.637; 0.714), 0.350 (0.311; 0.388); ok
18. 400 of 510 reversed; JSON 400; ok (credible 114; see E4)
19. Results, linked share 80.5%; 309,203/383,975 = 80.5%; ok. By certified race 81.1/81.1/80.2, Indigenous 61.9; ok. 64.9%, 76.2%, 89.0%; ok
20. Validation 0.78/0.76, 0.64/0.64, 0.18/0.18; 0.779/0.763, 0.639/0.641, 0.176/0.184; ok. SE 0.12; 0.122; ok
21. 71.7%, 51.7%, 89.8%; 0.717, 0.517, 0.898; ok
22. Median 8 deaths; 29.3% ≥20; Black median 0, 50.3% none; width 0.22; ok
23. Variances 1.38 and 0.28; 1.382, 0.284; ok. phi 99%; 0.991; ok
24. Clusters 546 and 920; ok. Moran disagree 0.45, Black 0.42; 0.450, 0.420; ok
25. Crossing at about 35%: not recomputable from JSON bins here; South +0.37, NE -0.05; 0.367, -0.050; ok
26. Residual Moran's I 0.71, 0.29, 0.15; 0.712, 0.288, 0.154; ok. Field variance 1.38, 0.41, 0.09; ok
27. F = 325 (3 df), 66.8 (26); 324.96, 66.82; ok
28. Black: composition 22%, state 37%, residual I 0.13; 0.220, 0.374, 0.126; ok
29. Place 0.25 (0.25; 0.26), 0.30 (0.30; 0.30), 0.22 (0.22; 0.23); 0.253 (0.249; 0.257), 0.300, 0.223 (0.220; 0.226); ok
30. GDP at equal composition 0.15/0.23, 0.64/0.66; 0.146/0.235, 0.636/0.658; ok
31. Multilevel n 178,656; var 1.32; MOR 2.99; 91% and 1.38; ok. Black 39/19/22/58; ok
32. Establishment 0.29/0.03, 0.31/0.10; AIC drops 3,411 and 266; 0.292/0.027, 0.309/0.095; 3,411, 266; ok
33. Time: 0.42 (0.20; 0.64); 0.420 (0.204; 0.637); ok. 0.15 to 0.21; 0.155, 0.212; ok. Brown +0.35, White -0.19; ok. SD 0.47, p 0.0004; ok. **0.19 "Southeast"**: North, 0.99 South: 0.988; mislabel (E1)
34. Agreement slope 0.06 (se 0.03); 0.062 (0.032); ok; correlation -0.31; ok. SC 0.82, RS 0.77, GO 0.50, ES 0.54; 0.824, 0.775, 0.495, 0.541; ok
35. Rates 10.7, 13.5; 10.69, 13.45; ok. Census-based infants 0.80; 0.8005; ok
36. 1-4 y: 0.94 vs 0.66; 0.944, 0.663; ok. 5-9 y 0.67 (0.48; 0.93), 1.21 (1.18; 1.25); 0.666 (0.479; 0.926), 1.213 (1.176; 1.252); ok
37. Household 0.79, 0.78; 0.789, 0.783; ok. Black v Brown 1.11 (0.83; 1.48), 0.81 (0.78; 0.85); ok. Indigenous 4.61 (3.58; 5.92), 6.00 (5.77; 6.25); ok
38. Without large 0.73 (0.67; 0.80); 0.734 (0.671; 0.803); ok. Leave-one-state 0.63 to 0.70; 0.635, 0.701; ok. t sensitivity 0.77, 0.58; 0.770, 0.577; ok (picks 2 of 4 scenarios; the others 0.57, 0.76)
39. Rebouças 0.79, 0.69; 0.792, 0.693; ok. Blank-as-mother 1.31 to 1.22; 1.224; ok
40. Regions 157, 446, 114, 82%; ok. 3.15, 1.83, 2.19; ok. Correlation 0.65, R² 0.06; ok. 22 of 25 in N/NE; 25 uf codes counted: 3 outside (MG×2, SP); ok
41. Table 5/ages: natural 0.68, suicide 0.62 (0.55; 0.69), transport 0.58 (0.54; 0.61), other external 0.55 (0.48; 0.62), assault other 0.47 (0.39; 0.55), firearm 0.35, legal 0.32 (0.15; 0.49); ok. Brown 0.29→0.61; Brown/Brown 0.65, 0.83; ok
42. By region natural/assault 0.31/0.19, 0.44/0.15, 0.70/0.49, 0.86/0.65, 0.59/0.29; ok. Ages exceeding 1.96 se: 15-21, 23 (z 3.5-5.0, 2.31; ages 22 and 24 z 1.25, 0.35); ok
43. Composition classes: 0.39 (0.33; 0.45), 0.17 (0.13; 0.20), 0.91 (0.81; 1.01), 0.79 (0.65; 0.93); ok. Standardised 0.65, 0.55, 0.45; 0.655, 0.551, 0.445; ok
44. Medical examiner shares 9.1%, 83.1%, 90.5%; ok (2,163/23,780 etc). Natural 0.69 (0.65; 0.74) vs 0.58 (0.44; 0.73); ok. Assault ME 0.37 (0.34; 0.41); other external 0.60 (0.57; 0.63); ok. Facility 0.45 (0.36; 0.54), street 0.35 (0.30; 0.40); ok
45. Discussion: 0.55/0.18 = 3.06 ("three times"), 0.18 vs 0.39 ("less than half": 0.46); ok. Standardised 0.65 vs 0.45; ok
46. Table 3 rows (deviance explained 71/75/42/81/74/82; Moran 0.71 etc.; multilevel 87/55/89...): composition_context 0.740 and state 0.753 ok; every cell reproduced
47. Methods: 383,975 vs Results 383,971 (M8); 80,326? not rechecked
Mismatches: only the Southeast/North label (E1); everything else matches to rounding.

## 6. References

All cited keys exist in `references/*.json` or `manual.json` (the build raises otherwise). Concerns about support: [41] (IBGE population projections, revision 2024) is cited for "the census-based population account by race"; the projections publish no race breakdown, and the account's construction (audit 2 P10) is only in Supplementary Text S3; cite the method or the inputs actually used. [49] Keele and Titiunik concern regression-discontinuity designs at boundaries; the border test here is a pair-difference regression, so the citation supports the idea, not the estimator. [14] Schwartzman: "mostly because of whom they married" is stronger than the reading report's summary (marriage partly explains it). [52] Miranda covers censuses up to 2010 and cannot support a 2013-2023 trend; [53] supports 2022 only at the national level. [10] Telles 2002 supported (abstract only, "local racial composition" appears in the abstract summary); the agreement of "79%" is as recorded. [13] supported by full text. [24] Rebouças "19.5 million" is 19,515,843 in the report; the reference title says 19 million, fine.
