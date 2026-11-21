# Response to the independent audit (out/audit_report.md), build of 2026-11-21

The audit found 7 errors, 23 points to fix and 8 minor ones; it recomputed about 40 numbers against `results.json`
and found none wrong. What was done with each group:

## Errors (all fixed, in the generator)

| # | finding | what changed |
|---|---|---|
| 1 | "fell in every cohort" false for 1940-44 | the sentence is generated from `cohort_falls`: 26 of 27 comparisons, the exception named; all cohorts in Supplementary Table S5 |
| 2 | Table S4 note did not match the rule | one rule in code (`cell_ci`): not estimable when the estimate leaves 0-1 or its standard error exceeds 0.15; the note states it |
| 3 | "municipalities of any size" contradicted by the largest class | removed; Methods, Results, Discussion and the supplement say the estimator failed at 25,600 or more births a year; a sensitivity analysis without those municipalities is reported (`rate_ratio_without_large`) and a build check holds it inside the main intervals |
| 4 | 60,145 against 60,146 | the one death in a municipality without births in the cohort year is stated in the text and in Table 2's note |
| 5 | Figure 3 and Table 3 n mis-stated | titles say the n is deaths of any recorded colour; Table 3 gained the share found |
| 6 | "from 2026" | computed (2012 + 15 = 2027) |
| 7 | impossible period for ages 15-24 | the period and birth years come from the data (`old_cohort_death_years`): deaths 2015-2024 of people born 2000-2009; age is completed years on the certificate |

## Points to fix: done

- The claim "depends on age" is withdrawn: children are measured against the mother's race, ages 15-24 against the
  newborn's recorded colour; the abstract, objective and conclusion no longer compare them.
- The mother's race is named as the reference for children everywhere, and the competing reading (the child's race
  differs from the mother's) is in the Discussion.
- Rate ratios by certified race carry intervals (Poisson) in the abstract, Results, Figure 2 and Table S3.
- The validation linkage is described; the validation is discussed and its reach stated (infants only).
- Limitations carry a direction where one is known, and three were added (the share found assumed equal by race;
  validation in infants only; provisional deaths of 2023-2024).
- The unreported sensitivity analysis on movers was removed from Methods; movers stay a limitation.
- Supplementary items are numbered in order of first citation (S1 to S6).
- Every claim stated in words is checked against the results at build time (seven assertions).
- The stale fields of `results.json` were removed.
- Notes no longer carry letters without anchors; table columns hold one estimate each; Table 4 has one value a cell.

## Not done, and why

- **A wider literature comparison in the Discussion** (audit 22). Only references confirmed at Crossref are used, and
  none was re-read in full. Adding more is the authors' reading task.
- **Uncited facts of the data systems** (audit 23): the 2011 birth form, the role of medical examiners, the hospital
  system. They need official documents as references; the text now states what the files show (field fill by year)
  instead of asserting the regulation.
- **Extraction dates per source, the territorial division's year, a flow diagram** (audit 26). The files were read in
  2026; exact dates and a flow figure are to be added with the journal's requirements.
- **Intervals for the three readings of race** (audit 27): not computed; the text says so and keeps them supplementary.
- **Reference details** (audit 38): three references have no page or article number at Crossref; to be completed by hand.
- **Proportions with limits outside 0-1** (audit 14): kept as estimated in Supplementary Table S2, with a note; the
  estimator is a difference of counts.
- Style points 31-37 partly applied (title names the design; one term for the estimator); a human language pass remains.
