# Response to audit report 3

What was done in the generators for each point of `audit_report_3.md`; "not done" says why.

## 1. Errors

| point | action |
|---|---|
| E1 slope label | The regional slopes are computed per region from the model's contrasts (North is the reference level) and the lowest and highest are named from the numbers. |
| E2 certifiers | The 15-24 paragraph gives all three contrasts: the difference between causes holds within medical examiners; within causes the intervals cannot exclude 10-point differences, and for external causes other than assault medical examiners certified White more often than physicians. The Discussion says the same. |
| E3 composition vs state | Rewritten everywhere (Results, Discussion, Conclusion, Abstract, README): composition and state each account for about three quarters of the deviance, together four fifths, with a step at state borders; "continuous surface across borders" removed. |
| E4 reversed regions | Abstract and Conclusion give both counts: 400 of 510 by posterior means, 114 credibly. |
| E5 composition from the same records | New sensitivity: composition replaced by the 2010 Census share of White residents (correlation 0.94) explains 69% of the deviance (71% from births) and 80% with the state; asserted in the build, reported in Results and the limitations. The comparison of a precise regressor with noisier proxies remains a limitation of the ecological design (stated as "associated with"). |
| E6 establishment | Reworded: residual clustering is better captured by the establishment; deaths outside registered establishments share one level per municipality; the levels cannot be separated where a municipality has one hospital; not a partition of variance. |
| E7 case mix | The individual-only model (74% for Brown mothers' infants certified White) is reported in the Results and limitations; "classification of place" became "associated with place". |

## 2. Points

| point | action |
|---|---|
| P1 border test | Errors clustered by pair of states (0.46, 95%CI 0.26-0.65); the disagreement outcome reported (0.35); the Black outcome reported as not testable (unstable state effects); the slope described as a lower bound because of attenuation; the "half a gradient" interpretation removed. |
| P2 deviance and F | Abstract labels deviance and multilevel variance separately; the F tests' independence assumption and the binomial noise floor (dispersion 8.4) are stated; Moran's p written p ≤ 0.001. |
| P3 nAGQ = 0 | Stated in Methods and Results with its consequence; the failed Laplace refit is recorded in `models.R` and the study record. A sensitivity by another estimator was not done. |
| P4 phi, variance ratio, LISA | phi given as the model's mixing parameter; the shrinkage argument for the variance ratio stated; the LISA threshold and the absence of multiplicity control in Methods and Results. The age difference between the family (0-9) and certificate (infant) maps remains, stated in the captions. |
| P5 ecological wording | "What the data support" became "consistent with"; place within the state reported at equal composition (30-59%: capital, metropolitan, interior) instead of "follows their composition". |
| P6 mortality mechanism | The household-moves-births sentence removed; the U-shape named in the Discussion; the account's method is Supplementary Text S3, no longer cited to the IBGE projections. |
| P7 time | "Largest where already most used" removed; agreement slope given with its interval including 0; regression to the mean named; the census link labelled as untestable. |
| P8 Discussion | The adult-women comparison qualified ("in a different population and setting"); "explained little" became "less than composition and little in addition". |
| P9 binomial intervals | Removed from the place and GDP proportions, with the reason. |
| P10 resolution | Restricted to Brown mothers' children. |

## 3. Minor

M1: Figure 1 cited in Methods; Supplementary Tables S3, S4, S6, S7, S9 and S13 now cited. Supplementary items are still not numbered in order of first citation (not done: a renumbering of the supplement, left for the journal's format). M2: Figure 3D title says empirical-Bayes; scales to 0.9. M3: Figure 4C legend shortened. M4: Figure 7 tick labels separated. M5: Figure 8 scale 1/4 to 4. M6: not changed. M7: Methods describe the GDP thirds, the place classes, the t sensitivity, the Rebouças comparison and the LISA threshold. M8: the 383,975 / 383,971 / 381,511 / 381,514 differences explained in the note of Supplementary Table S11 (date parsing). M9: Table 5 note says intervals can extend beyond 0 or 1. M10: Abstract labels the census-based ratio (2016-2024). M11: R-INLA (Lindgren and Rue 2015) and PySAL (Rey and Anselin 2010) cited, checked at Crossref.

## 4. Previous points

P4(d) linkage weights and (e) per-step flows after infancy: still not done. P15/P5 mother's-race quality: limitation only; no sensitivity is possible without a second record of the mother's race. Reference concerns: Schwartzman now "partly because of whom they married"; Miranda and the 2022 census cited only for the untested question; Keele and Titiunik cited for the logic of a boundary comparison, as before.
