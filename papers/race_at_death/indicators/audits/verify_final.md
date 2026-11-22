# Verification of response_3 - paper 2, indicators

## Verified (manuscript.txt against results/indicators2.json)
- Item 1, one source for the rates: the Abstract, Table 1 and Results agree. Rates 10.84 and 13.48 per 1,000; White to Brown 0.80 (0.8046); usual 1.31 (14.10/10.80 = 1.305); child's 0.79 (10.36/13.12); Black to Brown 1.15, 0.49 (5.25/10.80), 0.80 (10.51/13.12). Each ratio equals its rate pair.
- Item 2, Shapley: +0.73 (SE 0.048, CI 0.63; 0.82), White to Brown -0.26, no race +0.05, other flows -0.02 (Black to Brown -0.078, Brown to Black +0.019, Indigenous -0.004, other +0.040 sum to -0.024), scaling -0.01 (-0.009), net +0.48 (0.2665 - (-0.2174) = 0.484; parts sum to 0.483). Black to Brown step 1.37 to 0.57 matches the waterfall; -0.98 matches the Shapley value (-0.975). "Almost entirely" is gone; "larger than the whole net change" is true (0.73 > 0.48). Fig 2B shows Shapley values with intervals.
- Item 3: the Abstract, Discussion and Conclusion state that the child's-denominator ratio is below 1 with an interval including 1 (0.58; 1.07) and give the regional range. Regional values 0.74, 0.52, 1.00, 1.35, 0.88 match certified_over_child.
- Item 4: the objective no longer promises 510 regions. The standardisation sentence is correct: standardised 0.87 (mother's) and 1.66 (usual) against crude 0.80 and 1.31, so the usual ratio moves away from 1 and the mother's toward it.
- Yearly range (mother's 0.76-0.85, usual 1.24-1.39), neonatal 0.81/1.21 and post-neonatal 0.77/1.56 match. Figures: Fig 1 is the 2 x 2 design, Fig 3 colour bars have end arrows, Fig 3D legend is off the data.

## Failing - fixes required
1. **"The reversal held ... for every cause group" fails for congenital anomalies.** The mother's White to Brown ratio is 0.98 there (by_cause), so there is no inequality to reverse; only the usual ratio (1.75) exceeds 1. Reword the Results: the usual ratio exceeded 1 in every cause group, the mother's-race ratio was 0.57-0.78 in five and 0.98 for congenital anomalies. The Abstract and Discussion ("usual ratio stayed above 1 ... every cause") are correct as they stand.
2. **Regional claim stronger than its evidence.** Abstract and Conclusion: "households and certifiers do not classify children alike everywhere"; Discussion: "the certificate and the household do not classify the same children alike everywhere". The support is five macro-region point ratios (0.52 to 1.35) with no interval; response_3 lists the regional intervals as not done, and a build assert is not evidence. Either add delete-one-state intervals for the five ratios or write "point estimates differed (0.52 to 1.35); no intervals were computed" and soften the Conclusion.

## New problems (minor)
- The Abstract's regional range and the 3.15 and 1.83 of the Results are in no main figure or table (Fig 3 maps certified and mother's ratios by immediate region, not the child's denominator by macro-region). Add a small regional panel or table, or drop the range from the Abstract.
- The Abstract's 0.73, -0.26 and 0.48 are in Fig 2B only as unlabelled points; print the values on the panel.
- The Methods say intervals are on the log scale, but the printed interval for the mother's White to Brown ratio (0.77; 0.84) equals 0.8046 +/- 1.96 x 0.0157 on the natural scale. State the scale or recompute.

## Verdict
FAIL: fix 1 (congenital wording) and fix 2 (regional claim or intervals). The central numbers are internally consistent and match the file.
