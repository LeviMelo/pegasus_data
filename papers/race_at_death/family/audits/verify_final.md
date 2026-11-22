# Verification of the revision - paper 4 (family)

Read: manuscript.txt, response_2, review_2, family.json (review1, review2), results.json (cohorts), display_plan, figures 2-4. No file edited, no build.

## 1. "Done" items

| Item | Status | Evidence |
|---|---|---|
| 1 "mostly the father" | Done | "the mother's and the father's races counted about alike ... Brown mother and White father 0.56/0.61, White mother and Brown father 0.61/0.65; Black/White 0.44, White/Black 0.46." Recomputed from `parents`: 0.559/0.614, 0.611/0.646, 0.442, 0.456. Symmetric matrix is Figure 3C. "About alike" hides a 4-5 pp gap in the Brown/White pair; acceptable. |
| 2 informant crossed | Done | 0.57 / 0.59 / 0.66, Black mother 0.40/0.44/0.50, White mothers 0.65/0.65 and 0.47/0.48 match `informant_cross` (0.574, 0.589, 0.664; 0.404, 0.440, 0.504; 0.646/0.653; 0.468/0.476). Figure 4 shows it. |
| 3 drift | Partly | Schooling argument withdrawn (33->12, 51->22, 51->22 recomputed). Bootstrap changes match the json (+0.6, -0.5, -1.7, +2.6; standardised -1.1, -3.5, -1.1, +2.0). Fails on interpretation (2.1). |
| 4 full siblings | Done | 40%/39%, 14%/13%, 3%/3%, independent 56%/53% match `full_siblings` (0.401/0.390; 0.137/0.133; 0.034/0.027; 0.559/0.525). Observed is below independent in all 24 cells, so "in every couple type" is true. |
| 5 cohorts, wording | Done | 2005 cohort 0.472 -> 0.392 and 1995 cohort 0.534 -> 0.422 recomputed. "Two largest falls" is true among the 26 plotted intervals (-11.2, -8.1; next -6.8). Assortative mating named. "A stepfather still mattered" and "every couple type" are gone. |
| Figures, minor | Done | Figure 2D has bootstrap intervals; three decimals for the rule check; 2022 n in the abstract; census years given. |

Not done, and disclosed: household fixed effects, adjusted father/stepfather model, imputation flags, Yellow/Indigenous, excluded 18%.

## 2. Problems in the new or changed text

1. **The drift paragraph contradicts its own numbers.** Results: "the White mothers' standardised fall shows that this is the expansion of schooling, not a change in who declared each category." The White-mother check does not behave as a placebo: crude -0.5 becomes -3.5 at 2010 schooling, three times the Brown standardised change (-1.1). That shows the standardisation moves a great deal for every group; it supports "within equal schooling, darker reports", not "not a change in who declared". The second clause is unsupported; delete it. The Discussion ("a darkening within equal schooling of the kind surveys found in adults [5]") should state that the White-mother check moves as much, so the standardised change cannot be read as category drift.
2. **Abstract and Conclusion overreach on the informant.** "one respondent answering for mother and child pulls both toward his or her reading." The data show only the partner answering for both (+9 pp Brown/White, +10 pp Black/White, nil for White mothers). The mother answering for both is the reference. The mother's own race is fixed, so nothing "pulls both". Write "when the partner answered for both, the child was reported closer to his race", as the Discussion already does correctly.
3. **Cohort paragraph.** "between the ages at which households report the child and those at which young people report for themselves": the 2005 cohort is 12-17 and the 1995 cohort 10-14 at the later census, ages still mostly household-reported. Say "after childhood" or drop. The 1995 fall spans the 2000 and 2010 questionnaires; add a clause.
4. Two different standardisations are both labelled "2022 at 2010 mothers": 0.23 (partner mix, Brown 0-9) in the text and 0.198 (schooling and region, Figure 2D). Label which.
5. Intervals "0.56 (0.56; 0.56)", "(0.11; 0.11)" still at two decimals; give three decimals or percentage points.
6. "two to three times larger" recomputes as 2.1-3.3; acceptable.
7. The display plan is stale. Row 3 says "The child follows the father" and "C siblings" (siblings are now D; the claim is "both parents alike"); row 4 says "The answer leans toward whoever answers" (now only the partner answering for both).

## 3. Abstract numbers against main items

0.24/0.24 and 0.44/0.43 (Fig 2B,C); 0.56/0.61, 0.61/0.65, stepfather 0.30-0.39 (Fig 3A,C); 40/39 against 56/53 (Fig 3D, independence marks); 0.66/0.59/0.57 (Fig 4); "under three points" (Fig 2D crude). All present as points; no printed values on the plot, acceptable. 2022 n is in Figure 1 and the Methods. PASS on this point.

## Verdict

**Not yet PASS.** Required fixes: (a) delete "not a change in who declared each category" and say the White-mother check shows the standardisation is large for every group; (b) reword the abstract and conclusion on the informant to "when the partner answered for both" (no "his or her", no "pulls both"); (c) correct "ages at which young people report for themselves" for cohorts at 10-17; (d) update display_plan rows 3-4 (and label the two standardisations). Optional: three-decimal intervals.
