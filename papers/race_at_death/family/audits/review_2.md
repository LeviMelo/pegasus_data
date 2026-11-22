# Review 2 - Paper 4 (family), final verification

Read: manuscript.txt, supplement.txt, family.json, results.json (cohorts), family.py, the five PNGs, review_1/response_1, display_plan. Independent recomputation from `pairs2_2010/2022.parquet` (DuckDB, 1.5 GB cap; scratch code outside the repository). Nothing in the repository was edited; build.py was not run.

## 1 Verdict

**Major revision (narrow).** Arithmetic and review-1 repairs are sound; every printed number I checked recomputes. Four statements that carry the abstract and conclusion are not supported by data the authors already hold, or are contradicted by it:

1. "mostly the father" (Abstract, Discussion, Conclusion). A White mother with a Brown partner: child White 0.646-0.650 (informant file). A Brown mother with a White father: 0.56 (2010), 0.61 (2022). Black mother, White partner: child White about 0.43, Black 0.14-0.17; White mother, Black partner: child White 0.47, Black 0.13. The father's race counts about as much as the mother's, not more. What is shown is father more than stepfather. The words "mostly the father" read as father over mother.
2. "leans toward the race of whoever answers". The 7-pp partner effect (Brown mother, White partner, 2022, 0-9) sits almost wholly in households where the partner also answered for the mother. Crossing `informant` with `mother_informant` (my query): child White when mother answered for child and herself 0.574 (n 139,267); partner answered for child, mother answered for herself 0.589 (n 12,692); partner answered for both 0.664 (n 32,947; 18% of these households). So the effect is one respondent classifying both mother and child, not a general lean toward the informant's race. Within relation 04 and age strata the gap holds (0.636 vs 0.707 at 0-4; 0.556 vs 0.617 at 5-9), so it is not composition. The paper has the mother's informant (it prints 72% / 21%) but never crosses it.
3. The drift story. The Results and Discussion present Black mothers' schooling change (none/primary incomplete 51% to 22%, higher 4% to 12%) as evidence that "who the women declaring each category were" changed, "consistent with the darkening of adults' identification". `family.json drift` shows Brown mothers' profile moved identically (0.514 to 0.225 and 0.043 to 0.127); my own tabulation gives White mothers 33% to 12% low schooling. This is educational expansion for all mothers, not category composition. Standardising on schooling therefore removes a general trend. The standardised numbers (0.198, 0.465, 0.152) have no interval, yet the abstract says a rise "became a fall" (0.2095 to 0.2152 to 0.198).
4. "reads the child's descent and appearance more than it applies a household rule". Neither descent nor appearance is observed. The data are consistent with this reading but also with assortative mating (lighter Brown mothers partner White men), which the stepfather contrast does not remove.

## 2 Review-1 items

| Item | Fixed? | Evidence in the manuscript |
|---|---|---|
| E1 interaction | Yes | "the odds rose with White partners (... 0.15 ...) and with Black partners (0.18, 0.02), not with no partner (0.03, 0.01)". |
| E2 coverage | Yes | "kept 82% of the children aged 0-9 ... pairs with a Brown mother (84% White, 82% Black)". Recomputed 0.819 / 0.841 / 0.818. |
| E3 validation | Mostly | "order number pointed at the couple's woman for 99.8%"; "The rule cannot be checked in 2022." The Black-mother gap (0.476 vs 0.483) is rounded to "0.48 and 0.48", which hides it; the assert tolerance was relaxed to 0.01. Print three decimals. |
| E4 selection | Partly | Figure 5C now shows share in the pairs. The V0604 (2010) vs P0300 (2022, "mother or stepmother") mismatch is still not footnoted, and the cross-census 75% vs 80% coverage comparison stands without it. |
| E5 "same children" | Yes | "overlap for about three of five birth years ... (+0.07) is about half the gradient ... (+0.12) ... age and cohort cannot be separated." |
| E6 informant average | Partly | Replaced by within-couple contrasts, but the new reading ("leans toward") is not robust, see 1.2. Dropping "household holds the classification" is correct. |
| E7 cohort 2000 | Yes | "left out of the 2000 Census"; recomputed 25 of 26 intervals fall (exception: 1940, +0.0013). |
| E8 ref [9] | Yes | Removed; S1 names the population account. It is "built for this research programme": not citable or reproducible by readers; say so or supply the census counts. |
| E9 citations | Yes | [4] only for "reclassification ... described"; direction carried by [5]. [5] concerns adults and skin colour; the Discussion use is too strong (1.3). |
| E10 mother's informant | Yes | "the mother answered for herself in 72% of the pairs and the partner for her in 21%" (json 0.211 partner). |
| E11 drift | Not adequately | See 1.3; no interval, no placebo, standardisation confounded by general schooling trend. |
| E12 base | Yes | "65% of the children aged 0-14 of the pairs". |
| Father vs stepfather, siblings | Yes | Figure 3A-C. But see section 5 on confounding of the contrast and the missing full-sibling restriction. |

Not done and still not in the paper as limitations beyond one clause: svyglm, conditional logit, imputation flags, the excluded 18%, single-year 2010 ages, 2000 child pseudo-cohort. Yellow and Indigenous mothers are named as a limitation only.

## 3 Numbers: printed vs recomputed

Parquet (P) or family.json (J). 2010 values are couple rule.

| # | Quantity | Printed | Recomputed | Source |
|---|---|---|---|---|
| 1 | Brown mothers, child White 0-4, 2010 / 2022 | 0.24 / 0.24 | 0.235 / 0.239 | J/P |
| 2 | Black mothers, child Black 0-4 | 0.44 / 0.43 | 0.437 / 0.433 | J/P |
| 3 | Black mothers, child White 0-4, 2022 | 0.178 | 0.1779 | P |
| 4 | 2022 pairs 0-9 White / Brown / Black mothers | 817,206 / 1,181,851 / 241,818 | identical; sum 2,240,875 = Figure 1 | P |
| 5 | White father, Brown mother, child White | 0.56 / 0.61 | 0.559 / 0.614 | P |
| 6 | Brown father, same | 0.11 / 0.12 | 0.109 / 0.116 | P |
| 7 | White stepfather, mother's child | 0.36 / 0.39 | 0.355 / 0.390 | P |
| 8 | White stepfather, his stepchild | 0.30 / 0.31 | 0.295 / 0.315 | P |
| 9 | Brown stepfather | 0.15-0.16 | 0.147-0.160 | P |
| 10 | "two to three times" (father gap / stepfather gap) | 2-3 | 0.45/0.21 = 2.1, 0.45/0.135 = 3.3 (2010); 2.1, 3.2 (2022) | J |
| 11 | No partner, Brown, child White | 0.22 | 2022 0.216; 2010 0.205 (census not stated) | P |
| 12 | Black mothers, Black father: child Black | 0.79 | 2022 0.790; 2010 0.796 | P |
| 13 | Black mothers, Brown father / White father | 0.18 / 0.14 | 0.182 / 0.143 (2022) | P |
| 14 | Sibling discordance Brown/White 2010, 2022 | 42% / 41% | 0.420 / 0.412 | J, P |
| 15 | Brown/Brown, Black/Black, White/White | 15% / 18% / 3.8% | 0.155,0.148 / 0.175,0.184 / 0.045,0.038 | J |
| 16 | Black/White and White/Brown | 38% / 37% | 2022 0.384 / 0.372 (2010 0.370 / 0.391); years not stated | J |
| 17 | Father share, Brown 0-9 | 81% / 75% | 0.805 / 0.748 | J |
| 18 | White partner share, Brown mothers | 20% / 17% | 0.202 / 0.168 | review 1, P |
| 19 | Black mothers, Black partner | 39% / 35% | 0.391 / 0.350 | review 1, P |
| 20 | Informant: partner White, Brown mother | 0.65 vs 0.57 | 0.646 vs 0.574 | J |
| 21 | Black mother, White partner | 0.49 vs 0.40 | 0.490 vs 0.404 | J |
| 22 | Black/Black, Black/Brown | 0.80 vs 0.76; 0.17 vs 0.20 | 0.797 vs 0.762; 0.167 vs 0.203 | J |
| 23 | Drift, Brown 0-9 | 0.21; 0.22; 0.20 | 0.2095; 0.2152; 0.1982 | J |
| 24 | Black mothers' instruction | 51% to 22%; 4% to 12% | 0.507 to 0.220; 0.038 to 0.121 | J |
| 25 | Black 0-4 / 20-24 by census | 0.44/0.62; 0.43/0.58 | 0.437/0.618; 0.433/0.577 | P |
| 26 | Pseudo-cohort and cross-section | +0.07; +0.12 | 0.504-0.437 = 0.067; 0.560-0.437 = 0.123 | P/review 1 |
| 27 | Cohorts falling | 25 of 26 | 25 of 26 | results.json |
| 28 | Odds ratios 9.36, 1.38, 1.43 | as printed | identical to json | J |

All consistent. Presentation faults: rows 11-13 and 16 give no census; row 16 mixes 2010 and 2022 under one phrase.

## 4 Claims against evidence

- "every couple type examined" (Discussion). Contrasts in family.json that do not lean: White mother / Brown partner 0.650 vs 0.646 (n 68,182 / 103,260); White mother / Black partner child White 0.476 vs 0.468; Brown/Brown 0.113 vs 0.122 and Brown mother / Black partner 0.099 vs 0.117 (about 1 to 2 pp). The statement is true of the four contrasts plotted in Figure 4, which omit the null ones. Also see 1.2.
- "a stepfather still mattered". The White-stepfather gap (0.15 to 0.24 above Brown stepfather) is the sum of household influence and selection (mothers who partner White men are lighter, same class). It is not a causal "mattered".
- "in mixed couples the household did not apply one category to all its children". Supported, and I tested the half-sibling objection: restricted to households where all children are relation 04 (full siblings), Brown mother / White partner discordance is 40.4% (2010) and 39.0% (2022) versus 42.0 / 41.2% for all; Brown/Brown 14.3% / 13.3%. Households with a stepchild: 51% / 52%. So the paper understates its own point and should publish the full-sibling figure. But there is no independence benchmark: with p(White) 0.56, independent draws give 2p(1-p) = 0.49, observed 0.40, so households do share information. Say so; the rule "one category per household" is rejected, a partial household effect is not.
- "Women reporting themselves Black in 2022 were far more schooled ... consistent with the darkening" - refuted (1.3). Delete.
- "the small national changes depend on who the women declaring each category were" - supported only for Brown (0.2152 to 0.198, no CI); for Black mothers' Black the standardised value (0.4646) moves 0.6 pp of the 1.7 pp change.
- Cohort paragraph: "25 of 26" is fine, but the paper ignores the series' most relevant result for its question. The cohort born 2005-09 is 0.472 White at 0-4 (2010) and 0.392 at 12-17 (2022): -8.1 pp, the largest fall of any cohort (cohort 2000: -4.4; 1985: -4.3; 1960: -3.2). The 1995 cohort's White share fell 11 pp between 2000 (ages 0-4) and 2010. Children reported by households are lighter than adults of the cohorts just above them (0.472 vs 0.422 for 1995, 2010), then darken or are reclassified when they report for themselves. This is whole-population, free of co-residence selection, and speaks to age and cohort better than the pairs. The text says only that age and cohort "cannot be separated".
- "Implications ... live birth record will differ" - speculative; state as hypothesis.
- Priority statement "We found no study" is now hedged; acceptable.
- Variance: strata inert (SE 0.00050 both ways) means the SE is a household-clustered one; the paper says "design-based". Acceptable with the Supplement S2 caveat; "sampling alone" caveat present.

## 5 Rival explanations and missing analyses (ranked)

Rivals not tested in the paper: (a) respondent-style concordance (same person answering for mother and child) - testable, I did it; (b) mother's own tone/assortative mating (partly addressed by stepfather contrast, not stated); (c) 2022 stepfather share rise explains nothing (addressed); (d) general educational expansion vs category composition (not addressed); (e) 2022 relation coding change (not addressed); (f) imputation donors.

Ranked, all feasible with data held:
1. Informant x mother's informant x partner (cells in 1.2): who answered for both, who for the child only, mother self-reported. Table or Figure 4 extension. Pairs file has both fields.
2. Full-sibling discordance with an independence benchmark and an intraclass correlation; conditional logit within household (birth order, sex, age gap) - household fixed effects separate household rule from child traits. Pairs file has household id, age group, sex.
3. Use the cohort series as a children-specific test: same birth cohort at two censuses (2005 cohort -8.1 pp, 1995 cohort -11 pp), alongside the pairs' age gradient.
4. A properly specified change decomposition 2010 to 2022 with intervals: Kitagawa/Oaxaca over partner race x relation x mother's age x schooling x region, with White mothers as placebo, and the schooling of each category relative to all mothers (rank), not absolute.
5. Father/stepfather model with partner x relation interaction adjusted for age, schooling, region (the contrast is currently unadjusted; stepfather households have older children and head-of-household differs: relation 05 woman head, 06 man head, so informant and respondent role differ by structure).
6. Symmetric parent matrix (White mother x Brown/Black partner versus the reverse): currently models only Brown and Black mothers; needed to support or retire "mostly the father".
7. Imputation flags (M0606, MP0210 if kept in the 2022 file), re-estimate without imputed child or mother race.
8. Yellow and Indigenous mothers (counts 5,758 vs 30,354; 64,073 vs 24,430): show, since they are the clearest drift signal.
9. Excluded 18% (grandparent households), survey GLM check, 2010 single-year ages. Less valuable.

Data extent: good on pairs, relation, informant, partner; underused: mother's informant, household id for within-household inference, the cohort series, White mothers' cells, imputation flags. Municipality/urban is absent in 2022 public file (declared).

## 6 Figures (175 mm, figure guide s2, 5, 6, 7)

Dimensions at 300 dpi: matrix 174 mm, partner 176 mm, informant 151 mm, age 154 mm, flow 175 mm. Text 7-9 pt on axes; legends about 6.5 pt (Figure 3A legend, Figure 2D legend, Figure 5C legend): borderline, raise to 7. No overlap or legend-over-data found; Figure 4 legend sits close to the 0.86 point but clear. Colour pairing consistent (grey 2010, orange 2022).

- Fig 1: text-only flowchart; adequate for design. It repeats Methods.
- Fig 2: A-C proportions printed nowhere on the plot; no values, intervals invisible (stated). Panel D mixes ages (0-9) under a y-label "children aged 0-4"; relabel D separately. Standardised points have no interval (guide: "estimates with no interval").
- Fig 3: A, B clear; legend mixes shape (relation) and colour (year) in one box, acceptable. C has no intervals and no n, omits White and Black mothers with no partner while Brown no partner is shown, and lacks the independence benchmark and the full-sibling series. Dot rows ordered by meaning, good.
- Fig 4: only four of the plotted cells show a lean; mother/partner/other/non-resident colours differ from Figure 3's palette meaning (orange was 2022 elsewhere, here "partner"): conflicts with "a group has the same colour in every figure". No n. Add the third axis (mother self-reported vs not), or the figure overstates.
- Fig 5: A, B intervals not visible (fine). C solid/dashed plus colour is readable. D: no uncertainty, no counts, y axis starts at 0.38; the 2000-census cohort 1995 point at ages 0-4 is not distinguished from adults; label the age at each census. Direct labels would replace the legend.
- Plan check: every abstract number sits in a main item, but values are read off points; Figures 2 and 4 need a printed value or a small table. Table 1 as text rows is long; format as a two-column forest.

## 7 Minor

- Results father paragraph: say 2022 (or both) for 0.79, 0.18, 0.14, 0.22; "0.08 and 0.10" has years, others do not.
- Garbled sentence: "were reported Black about half as much more often as the 2010 cross-section's gradient implies"; write "the rise was about half the cross-sectional gradient".
- "more than half of households" refers to children, not households.
- Two-decimal intervals "(0.11; 0.11)" repeated; give three decimals or percentage points, or drop intervals that are narrower than rounding.
- Discussion para 3 strawman: "lighter of the two" or "partner's race" as a strict rule is rejected by any data; state the probabilistic household-rule alternative and why siblings (positive correlation) cannot reject it.
- Methods: say that 2022 Black/Brown/White mother classification uses P0300 "mother or stepmother"; call it a limitation, not only that rule "cannot be checked".
- Abstract Methods gives 2010 n only; give 2022 (2,240,875).
- Population account [S1]: "built for this research programme" is not verifiable.
- Reference [5]: confirm that the 2025 PNAS paper reports a darkening of identification in the 2010s (response_1 calls it freemannc2024).

## Top five required changes

1. Replace "mostly the father" by "the father more than a stepfather, about as much as the mother", supported by the symmetric White-mother/Brown-partner cell, and add that symmetric parent matrix.
2. Cross child's informant with mother's informant; restate or drop "leans toward whoever answers" (effect +1.5 pp when the mother reported herself, +9 pp when the partner reported both).
3. Withdraw the Black-mothers' schooling as category-drift evidence (Brown and White mothers moved the same); add intervals and a placebo to the standardisation, or soften "rise became a fall".
4. Report full-sibling discordance (40.4% / 39.0%) with an independence benchmark and household-level model; add intervals to Figure 3C.
5. Use the cohort series (2005 cohort -8.1 pp, 1995 cohort -11 pp) in the age discussion, and replace "descent and appearance" with "consistent with", naming assortative mating as a rival.

**Verdict: major revision (narrow); descriptive core accepted, interpretation to be reduced to what the informant, parent-matrix and drift checks support.**
