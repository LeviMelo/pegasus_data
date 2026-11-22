# Referee report 3: paper 6 (candidates less a negative control)

## Verdict
Major revision, on a narrower front than round 2. Most of review 2 is fixed and the paper is honest about failures. But the results file undercuts the main negative finding: against the correct target (findable units, those that share the key) the admissions interval is NOT "too narrow" and the estimator agrees to 0.001, not 0.006. This is computed in estimator.json (like_pair.groups.all.variants.all.against_findable) and never reported.

| admissions, all units | target | mean abs diff | cells outside model/exact/chance | z sd model |
|---|---|---|---|---|
| | linked | 0.0058 | 13/13/16 | 8.6 |
| | findable | 0.0010 | 3/3/6 | 1.17 |
| findable units | findable | 0.0006 | 0/0/1 | 0.66 |

By size class vs findable: z sd 0.36, 0.57, 0.35, 0.78, 1.19; cells outside model 0,0,0,1,2. The 0.0057 gap is the A1 selection (linked less findable table), not variance error. Abstract, Results, Discussion and Conclusions ("too narrow for admissions", "error of the key itself") must change.

## Review-2 items
- 1.1 Indigenous omitted: fixed (0.082, z 3.7; recomputed 0.0817, 3.73; 4 of 44 cells).
- 1.2 heavy tail: fixed (14% non-positive row sums; median -0.021 vs mean +0.134; recomputed 0.135).
- 1.3 "nominal": mostly fixed (word dropped; SE ratio 1.36 quoted, but variance ratio is 1.93).
- 1.4 covariances: fixed as an added exact model error; the package still uses the old one.
- 1.5 rate-ratio truth: fixed (births-municipality truth).
- 1.6 colour_known / missing race: fixed (17.6% vs 24.2% missing; 76.2% vs 66.2%; gap 10.0 vs 12.6; recomputed).
- 1.7 unit mismatch: partly. Infants fixed; the admissions failure is blamed on key errors, but it is the wrong target (above).
- 1.8: fixed. A1 (2): fixed (0.913/0.896/0.882/0.807; 0.915 distortion). 3.1/3.2: disclosed, not solved (no census check).
- 3.3 simulation: largely delivered; 1,000 replicates and common random numbers not done; pooled12 and application have 100 replicates, not 200.
- 3.4 coverage: partly (see claims). 4 literature: partly (Chipperfield 2011 not compared; no EM comparator). 5.1, 5.2, 5.4: done. 5.5: not done. 7: Figure 2 redone; RECORD flow diagram missing; Figure 3 lacks pooled12 and application.
- Old-run sentences: none found. But abstract "200 replicates of each of 13 scenarios", the Table 4 caption "200 replicates a scenario" and the general "+/-3.0 points" MC band are wrong for pooled12/application (100 replicates; band about +/-4.3).

## Numbers recomputed (all match unless noted)
Linked share 0.8056; admissions linked 0.9592, findable 0.8620; ideal found 0.9591, twins 0.9703, overdisp 0.9670, keyerr 0.852; five-cell max bias ideal 0.0093 (z 2.95) at 6,400-25,599, 0.0039 below 6,400 (twins); Indigenous 0.0817 (z 3.73), twins 0.0620; sparse five-cell 0.0201 (z 3.2) and 0.1337; 28/200 invalid at >=25,600; Black as Black all sizes SE ratio 1.363, variance ratio 1.93, <400 0.994; unequal RR bias +0.062 (0.66->0.723); a2 RR +0.065 national but +0.045 at 6,400-25,599 (reconcile with Table 4); keyerr RR +0.019, keyerr_k +0.025; findability 0.913/0.896/0.882/0.807 and infants 0.955/0.953/0.947/0.935; Goodman multiple 8.7 uses 0.0045 (Table 3 rounded values give 9.75); infants unlinked vs linked 0.0187, z sd 2.00, 20% outside; admissions sex split 0.0066, z sd 4.23, 60% outside. Infant Table 1 per size class (model/chance outside, all-units variant): 3/4, 4/6, 0/0, 0/0 of 20; the abstract quotes only the pooled <25,600 row. Garbled sentence: "dispersion 0.007 ... 0.007 of it the sexes' covariance" (phi 0.0075 shared, psi 0.0069 sex-specific).

## Claims stronger than evidence
- Coverage "92%-100%" is Black as Black without selective. Five-cell minima (model, system value): selective 0.00, keyerr_k 0.60, application 0.80, movers 0.83, unequal 0.785; pooled12 Indigenous 0.89. Application coverage is never reported.
- Table 3: in admissions the estimator is worse than no control in 4 of 5 size classes (0.005 v 0.004; 0.004 v 0.003; 0.005 v 0.004; 0.013 v 0.012) and no better than unique/uniform/Goodman at <1,600; in infants <400 the unique-key link wins (0.004 v 0.005). Not stated; and against the linked target all sit at the A1 floor so cannot discriminate.
- "Adequate for infants": pooled only; 400-1,599 has 2 model and 4 chance cells outside (P about 0.016); 25,600 chosen on the same data.
- "Unfindable are sloppy records, not movers": not tested; need age/sex/cause profile of unfindable.
- Goodman comparator without intercepts or municipality effects is a weak rival; "weight of 1 vs 36 candidates" asserted not tested; sex-specific excess births breaking A2 (share found 1.66 at invented parameters) is not in the manuscript.

## Missing analyses, ranked
1. Report admissions against the findable target (computed; cheap). 2. Comparators against findable by size class (cheap). 3. pooled12/application at 200 replicates and in Figure 3 (about 3 h). 4. Age/sex/cause/size profile of linked vs findable vs unfindable (cheap). 5. Coverage over all cells and scenarios (cheap). 6. Empirical-null calibration of intervals from placebo z sd (cheap). 7. Census check for ages 1-14 (needs microdata). 8. A2 dose response by age band in admissions (feasible). 9. Split-half/bootstrap model v cluster SE (feasible). 10. EM comparator, inverse-variance combination (heavy; future work).

## Figures
- Fig 1: clear; use generic sex wording.
- Fig 2: panel A dominated by wide large-cell bars, headline 0.004 unreadable; panel B and C use the wrong (linked) target; z clipped at +/-6 for many admissions points; legends overlap data; caption says "exact model SE" while text says "model interval".
- Fig 3: 11 scenarios, one palette (dense); pooled12 and application missing though the text counts 13; coverage axis from 0.5 hides clipped minima.
- Display plan: not every abstract number is in a main item (placebo result, sex split, 14% failed only in text or supplement). RECORD flow diagram absent.

## Minor
Abstract Methods is one 150-word sentence and Results has about 20 numbers; title 28 words; Table 1 municipality counts differ across rows (5,493/5,522/5,500); "certified White, White in hospital" ambiguous; state how failed replicates enter Table 4; check the 114-million cohort figure; confirm SINASC 2013 births were deduplicated (package defect); consider moving keyerr_k, munfx, a2 to the supplement.

VERDICT: Major revision.
Top five changes: (1) report admissions vs the findable target and drop "too narrow"; (2) correct replicate counts (100 for pooled12/application) or rerun, and add them to Figure 3; (3) report coverage over all cells and scenarios with minima; (4) state that the estimator is no better than comparators where chance is low, recompute Table 3 vs findable; (5) report infant adequacy by size class, mark 25,600 as in-sample, and profile the unfindable against the mover explanation.
