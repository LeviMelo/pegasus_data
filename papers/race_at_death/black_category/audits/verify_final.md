# Verification of response_3 - paper 3, black_category

## Verified (manuscript.txt against results/mechanism.json key review3 and movers)
- Item 1, practice: per SD (1.72 logit) 1.63 (1.44; 1.85) alone, 1.37 (1.22; 1.54) at equal composition, region and year, 1.18 (1.04; 1.33) beside the mother's record; 48% through her record (0.481); the text says the last is the part that does not pass through her record. "Added little" is gone. Fig 3B plots the printed values (checked on the log axis). Table 1 no longer carries the old prediction.
- Item 2, movers: persistence 0.918 against 0.128 in the same hospital and 0.584 against 0.355 in another: odds ratios 77 and 2.45, printed "about 76" and "2.5" (acceptable; "about 77" is exact). Slope 1.013 (SE 0.031; origin clustering 0.030), corrected 1.159, 5,678 mothers. The registry-memory reading is in the Results, Discussion and Table 1.
- Item 3: no prenatal visit 2.53 (1.41; 4.54), 255 deaths; home 3.37 (1.81; 6.28), 338 deaths; elsewhere, 838 deaths in 114 establishments (file's Mantel-Haenszel 1.77 (1.28; 2.43); the text's 1.75 (1.25; 2.44) is the adjusted model, labelled as in Fig 3B). The "equally compatible with the mother's own varying self-classification" wording is present.
- Item 4: White cell region-standardised 0.25, 0.14, 0.13 (0.252, 0.135, 0.135); South shares 0.42 and 0.03; MH over regions 2.11 (1.90; 2.35); same infants 0.37 against 0.19 (0.371; 0.186). Trend without 2023: -0.286 (SE 0.111) gives (-0.50; -0.07), n 9,014. 92,004 to 119,012 stated. Four of five regions rose between 2013 and 2023 (North fell).
- Claims: "taking the mother's declaration as the reference" present; Table 1 status rule defined; Fig 5A raw regional proportions with intervals; Fig 5B marks the 2023 change; Fig 1 has counts.

## Failing - fixes required
1. **Contradiction on the person.** End of the movers paragraph in the Results: "the hospital's level travels with the hospital, not with the mother". The same paragraph reports an odds ratio of about 2.5 across hospitals, and the Discussion and Table 1 state that a person component remained ("compatible; not separable"). Replace with "the hospital's level travels with the hospital, although a person component remains across hospitals (odds ratio about 2.5)".
2. **"By the full difference in practice" (Discussion) and "moved by 1.01 of the difference" (Abstract).** The estimate is 1.01 (SE 0.03) and 1.16 corrected for chance pairs; neither is below 1 and the second exceeds it. State the interval (about 0.95; 1.07) and write "about the full difference".

## New problems (minor)
- Two samples carry different counts without reconciliation: 10,568 infants (admission linked) in the first Results paragraph and 10,438 (both records informative) from the second section on. Define 10,438 where it first appears.
- "... which lowered that year's share" sits beside "0.34 of 2013 and 0.36 of 2023". Fig 5B shows a fall from about 0.375 in 2022 to 0.361 in 2023: name 2022 explicitly.
- Abstract numbers -0.29 (Fig 5B prints no value) and 48% (not in Fig 3B) are in no main item as numbers, contrary to display_plan.md ("Every abstract number is in a main item"). Print them in the figure or table notes.
- Not done and acknowledged: the infant's own SIH record, mother-plus-hospital decomposition, CNES moderators, linkage weights, tau of the 2.0 OR. The first is the strongest rival to "compatible with staff reading the same person alike"; the limitations name it only as "not used".

## Verdict
FAIL on two wording fixes (1 and 2); no new analysis is needed. Every number recomputed matches the files.
