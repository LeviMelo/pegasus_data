# Review 6: "Race on the death certificate and place" (final verification)

Read: manuscript.txt and supplement.txt (as text), text sources, ledger, display plan, review_5 and response_5, results JSON (results, spatial, panel, panel_long, physician, mechanism, laplace), panel_long.py, municipal_estimates.parquet (DuckDB, 1.5 GB limit), and the five main figures.

## 1. Verdict

**Major revision (a short one).** The descriptive core is sound and the arithmetic is almost entirely faithful to the result files: 20 of 21 figures I recomputed matched, and the exception is one that depends on the unit (section 3). Review 5 was answered substantively: the third reading is no longer called "a third classification", the copy-from-birth-record rival was tested, a residence/occurrence analysis and a crossed physician model were added, the claims were reworded, and Table 1 sets readings against predictions. What remains is in three groups. (a) Two reported analyses are interpreted more strongly than their own intervals allow: the census long panel and the residence-against-occurrence contrast. (b) Results that exist in the files and cut against the text are not reported: the lead placebo, the 2000-2010 panel, the within-municipality effect of verification-service share, and the Laplace refit. (c) Several review-5 items are marked "done" or "stated" in response_5 but are not in the manuscript. The paper still answers a weaker question than its title and abstract ask ("what explains it"), and the Abstract's "followed the local majority" is stronger than any of the tests.

## 2. Review-5 items: fixed in the manuscript?

| Item | Verdict | Evidence |
|---|---|---|
| 1 Copy from DN | Partly. Tested (agreement 0.67 at hand against 0.61 elsewhere; gradient 0.73 against 0.56) and "third classification" removed. | The test is a proxy. "At hand" means died in the birth establishment on day 0-1, but those are also the deaths where staff saw the newborn, so an observer reading is not excluded. The paper never says this. RACACORN is dropped (212 records), so the reference is not given an error bar. "Copying excluded as main mechanism" is fair; "was not a copy" in the Abstract is fine. |
| 2 Residence, occurrence, establishment | Done, over-read. | "0.32 ... and 0.42 ... at equal values of the other" is turned into "weigh toward" a local norm. Residence composition is measured in small municipalities and occurrence composition in large referral centres, so the occurrence coefficient is less attenuated by sampling noise. The two coefficients are also not tested against each other (difference 0.10, SEs 0.019 and 0.021). Composition-by-certifier slopes and the adult placebo were not done (the placebo reason, no reference race for adults, is valid; it is not in the paper). |
| 3 Long panel | Done, mis-read. | See section 3, claim 5. The lead placebo and the 2000-2010 period (within estimate -0.23, SE 2.2) were run and are in `panel_long.json`, but appear nowhere in the manuscript or supplement. "Trait of the place" is removed, as the response says. |
| 4 Predictions, symmetric cells, border | Done except the family adjustment. | Table 1 and the cells analysis are there. The border sentence now reads "a step and a continuous gradient together" (good). Response_5 says the missing father/partner limitation "is stated". It is not: "father" and "partner" do not occur in the manuscript. Discussion cites only "both parents and schooling [14]". The even-odds point (58%, CI 56-60) excludes 50%, so the paper's own "local majority" rule is rejected at the pivot. The paper does not say what the rule predicts, and does not discuss the miss. |
| 5 Cut, FDR, Laplace, one interval set | Partly. | FDR is reported (356/565). Laplace refits exist (`data/spatial/laplace.json`: composition 0.868 against 0.870 under nAGQ=0) but the text still says the nAGQ=0 estimates "can understate" and never says the refit agrees. Intervals are still mixed: the investigation block prints binomial intervals such as "0.64 (95%CI 0.64; 0.64)" while Methods promise cluster bootstrap; "Intervals are not given" for the place and GDP proportions. Length is about 7,600 words by the response's count (9,900 extracted). Restricted spatial regression not done. |
| 5.1-5.11 wording | Done. | "was associated with 71%", "To our knowledge", context "collinear", deaths "without the macro-region", and the Black regional sentence are all present. Residue: the Conclusion and Discussion still assert that the Black category "rose ... unevenly between intermediate regions", a result that moved to paper 3 and is not shown here. |
| 4.3 Mundlak | Partly. | The reliability correction is described. The within coefficients for the share of natural deaths certified by a verification service are omitted, although significant (section 4, point 3). |
| 7 Overlap | Done in part. | The Black category (Moran 0.42, KK 22/37% deviance, multilevel 39%) remains, but the Abstract is Brown-to-White. |

## 3. Numbers recomputed (printed against recomputed)

Matched exactly unless stated.

1. White/Brown/Black mothers certified as mother: 0.763/0.641/0.184 with bootstrap CIs (0.75;0.78), (0.62;0.66), (0.17;0.20). Matches.
2. Brown to White 0.252 (0.23;0.27) and Black to Brown 0.548 (0.53;0.57). Match.
3. Variance of the municipal field: 1.382/0.284 = 4.87, printed "4.9". Recomputed from `municipal_estimates.parquet`: 1.3824 and 0.2838. Match.
4. Births-weighted 5th-95th percentiles: certificate 0.091-0.758, family 0.104-0.364 (printed 0.09-0.76 and 0.10-0.36). Match.
5. Deviance explained from `moran` deviances: composition 71.1%, state 75.3%, composition+state 80.6%, context 42.0%; dispersion 8.36. Match.
6. Residual Moran 0.712, 0.288, 0.154; municipal-field variance 1.38, 0.41, 0.09. Match.
7. Border slope 0.455, SE 0.099, CI (0.26;0.65); mean squared difference 0.555 against 0.488 (printed 0.56 and 0.49); 1,069 pairs. Match.
8. Multilevel, nAGQ=0: variance 1.318, MOR 2.99; proportion explained 0.870 (composition), 0.546, 0.428, 0.889, individual only 0.741, without region -0.009, full 0.913 (MOR 1.38). All match. MOR from 1.32 recomputed as 2.99.
9. LISA 546/920; FDR 356/565; none for the Black category. Match.
10. Panel: between 0.446 (0.42;0.47), within 0.057 (0.02;0.10); regions 0.514 and 0.053; reliability 0.59 (41% noise) and 0.94; 0.053/0.943/0.514 = 11%. Match.
11. Census long difference: 0.294 (SE 0.174), CI (-0.05;0.63) against 1.006. Match.
12. Long panel: within -0.649 (SE 0.263), between -0.540, within SD 0.068 against 0.976. Match.
13. Copy test: 0.668 (se 0.007) against 0.612 (0.006); gradient 0.728 against 0.562. Match.
14. Physician, establishment and municipality variance 0.786/0.455/0.080 (Brown to White), 0.285/0.421/0.209 (Black). Match.
15. Cells: WP -0.844, PW 0.644, KP on Brown share 0.554, even odds 0.579 (0.557;0.602). Match.
16. Linkage 309,203/383,975 = 80.5%; 296,512/309,203 = 95.9% have the mother's race (4.1% do not; the manuscript does not say this, and these deaths leave the estimand).
17. Region difference of certificate minus family, births-weighted: South 0.367, Northeast -0.050. Match.
18. **Does not reproduce:** "the two crossing where about 35% of births were White". The text takes the first national tenth in which the certificate exceeds the family. On municipal fields, births-weighted by classes of White share, the certificate is already above the family at 22-31% White (0.30 against 0.24) and the crossing is near 20%. A single tenth-class edge gives no interval, so "35%" is an artefact of binning. Give it with a bootstrap and the unit, or drop it.
19. **Internally unexplained:** "fell by 0.19 in log-odds per decade, nationally from 0.26 to 0.25". The crude national proportion (0.263 to 0.252) implies about -0.06 in log-odds, not -0.19. The -0.19 is the conditional (within-municipality, mixed) slope. Say so, or the sentence looks contradictory. The Discussion's "became less common over the decade" is not true of the crude national figure.
20. The F statistics and the 7,429 establishment levels were not re-derived; they come from the same pipelines and I found no reason to doubt them.

## 4. Claims against the numbers

1. **"Follows the local majority ... in every cell" (Abstract and Discussion).** Three cells were tested (PW, WP, KP) and a fourth (KK) is complementary to KP. The slopes are per logit and well below 1 (0.64, -0.84, 0.55), and the even-odds point is 58%, not 50%. These support "moves in the direction of the local majority, partially". "Followed" (Abstract, Results) reads as conformity. The pre-stated prediction (50%) is rejected by its own CI and the miss is not mentioned. Also, the two cells that supply the "symmetry" are both read off the same cross-sectional composition, so they are not independent confirmations.
2. **"Residence 0.32 against occurrence 0.42 weighs toward a local norm"** (Discussion; Table 1 "weakened"). The attenuation asymmetry above has not been excluded. Residence and occurrence composition are highly correlated, and the coefficient difference has no test. The rival (a regionally heterogeneous Brown category) is therefore "weakened" on a contrast that could be produced by measurement error alone. The ledger still says "open" for this row while Table 1 says "weakened": make them agree.
3. **"Nothing within places" (Table 1, wealth or services) and "GDP and physicians did not move the certificate within it".** Within a municipality, the verification-service share of natural deaths moved the certificate: +0.61 (0.23; 1.00); within immediate regions +0.85 (0.33; 1.37), while the medical-examiner share was -0.30 (-0.60; -0.01). These are the only within-place service effects with intervals clear of zero, they are in `panel.json`, and Figure 5C hides them by showing four of six covariates. They fit the certifier/state-practice readings, which the paper otherwise supports. Report them.
4. **"The certificate followed the census population as it changed" (within -0.65, close to between -0.54).** The outcome is logit(certified White) minus logit(births White). A fully following certificate predicts 0 and a fixed one predicts -1 (if births track the census). The interval -0.65 +/- 0.52 = (-1.17; -0.13) contains -1. So "followed" is not supported: the data exclude full following and cannot exclude a fixed trait. Add the lead model's result (within -0.33, SE 0.58; lead -0.54, SE 1.10: uninformative), and note that the within variation is 0.07 SD. Figure 5D plots the two designs on one axis, but their null points differ (0 for the left, -1 or 0 for the right); label the "fixed" and "following" lines. Section "Time and place" itself concludes "the data do not settle which", so the sentence "on this measure ... followed" contradicts its own conclusion.
5. **"Physician variance 0.79 is the largest level"; "the largest level" (Table 1, Discussion).** 22,103 physicians for 82,173 deaths (mean 3.7 per physician; 4,358 with five or more). Binary-outcome variance components at that sparsity are weakly identified. Physician is also nested in establishments and in the certifying service (IML/SVO are staffed by a few physicians), and the physician role (informant or certifier) is unknown. Add a sensitivity restricted to physicians with at least 5 deaths, and report a bootstrap or profile interval. Without one, the ranking physician > establishment > municipality is not secure.
6. **Table 1 "interviewed deaths certified alike"/"the family reading weakened".** Agreement is 0.68 with a home visit or family interview against 0.64 not investigated (non-overlapping CIs). That is a modest, real rise, and investigated deaths are selected. "Alike" overstates; "changed little" (the Results wording) is accurate.
7. **Ecological inference.** The "5 times the family's variance" compares 2013-2023 deaths with 2010 census children aged 0-9, smoothed under BYM2 at different information levels. The paper discloses the differences (family less shrunk). The comparison also assumes Brown mothers on the birth record and in the census household are the same population, and the census household benchmark ignores the father (paper 4's main finding). The Abstract should not use the ratio as the headline; it is a description, with no interval.
8. **"Not a copy of the birth record" and "excluded" (Table 1)** are right for a literal copy. A partial reading of the birth record (certifier sees the DN colour only sometimes) is not excluded. Wording "as the main mechanism" is correct; keep it in the Abstract.
9. **"Wealth and services ... little in addition"** is fine with the collinearity caveat (present). "More than with wealth, services or the circumstances of the death" (Conclusion) is a statement about association with one composition measure that comes from the same records as the outcome; the census substitution covers only the deviance models (disclosed).
10. **Linkage selection** is "bounded" in the ledger by flat linked shares across certified race (81.1/81.1/80.2). That does not bound selection on composition within place, and the linked share is 76% in the North and 62% for Indigenous. No weights or bounds are given.

## 5. Missing analyses, ranked

Feasible with data held:

1. **Within-municipality, two-sided measurement-error check of residence against occurrence** (feasible: SIM CODMUNRES/CODMUNOCOR, SINASC births). Restrict to referral deaths in large occurrence municipalities and equalise composition noise (use census composition or 3-year pooled births for both). Add a test of the difference. This decides whether the one result that "weakens" the Brown-category rival survives.
2. **Composition by certifier-type and age slopes** (IML, SVO, attending; neonatal against post-neonatal; home against hospital). A local norm and a state practice predict different heterogeneity; the response dropped these because of the physician model, which does not substitute.
3. **Linkage-failure model by place** (inverse-probability weights or Manski bounds on the map; SIM and SINASC both held). Currently only a descriptive linked share.
4. **Family benchmark adjusted for partner race and mother's schooling** (census 2010 microdata held; paper 4 already has the household partner data). This is the largest remaining rival (an informant-level mechanism: the father or other informant). At minimum state the limitation.
5. **Placebo: certified race of deaths at 1-4 years and 5-9 years against the same gradient** (estimator already built) as an age-of-informant dose-response, and **neonatal early-death RACACORN** if any 2012-2013 records allow it (212 records; not usable).
6. **A formal test of a monotone local-majority rule** against a partial-adjustment alternative: estimate the slope and the pivot with bootstrap and state the prediction in advance (50%).
7. **Multinomial hierarchical fit** (certified White/Brown/Black given mother's race by composition by state) so symmetry is tested in one model; the paper still reports three cells separately.
8. **SIH hospital record of the child** (`sih_deaths_to_sim`): a third observer of the same child. Held, not used.
9. Bias analysis for DN place-dependence (assume a misclassification rate and show the gradient's change), cheap and requested twice.

## 6. Figures (guide sections 2, 5, 6, 7; display plan)

- **Fig 1 (flow):** legible and not overlapping. It lacks the unlinked count (74,772), the 12,691 linked deaths without mother's race, the 1-9-year deaths (77,693) and the estimator, although Methods say Figure 1 shows how the records relate. The "by residence and occurrence" arrow is unexplained. Fix by adding the missing counts.
- **Fig 2 (matrices):** fine at 175 mm, but no intervals even though the text gives them; panel E shows a negative proportion (-0.01); rows do not sum to 1 (the "other" class is not shown, and the footnote does not say so).
- **Fig 3 (maps):** no-data class present in D only; A-C have none because the model fills every municipality, but the municipalities with fewer than 5 deaths (about half) are shown at the same visual weight with no uncertainty mask. Borders are thin and legible. The display plan promised that "5 times" is between A and B: there is no printed number in the figure. Panel D legend sits in the sea, acceptable. Posterior intervals or a low-information mask would be better than the viridis fill alone.
- **Fig 4 (explain):** five panels in a tall composite. Panel A: legend sits in empty space, good; dashed family line has no band. Panel C: legend lies on the grey points. B and D have no intervals, although they are the paper's headline numbers (71/75/81, 87%). E: Black-mother points (black squares) have bars, Brown-mother points (blue) show tiny or no bars; tick labels would be under 6 pt at 175 mm. D mixes three outcomes (including the White-mother series, which no text mentions) in one panel.
- **Fig 5 (time):** A readable with intervals. B grey no-data class named in the label but none visible. C omits two of six covariates (the verification-service share is the significant one). D mixes two outcomes on one axis (see claim 4) and shows no reference lines for "fixed" and "following".
- **Abstract numbers in a main item:** 0.76/0.64/0.18 (Fig 2), 0.09-0.76 (Fig 3A), 5 times (not printed), Moran 0.77 (Fig 4B "none" is the residual Moran, 0.71, not the 0.77 of the rate; not shown), 71/75/81/42 (4B), 87%/60% (4D), 0.46 (4C). The 5 times and Moran 0.77 are in no main item.

## 7. Minor

- Title says 2013-2024; infants end in 2023, deaths at 1-9 years in 2024. Say 2013-2023 or "2013-2024" with the caveat in the title's scope.
- "Table 1" in text but "Table 4" in response_5 and in the ledger's wording; check cross-references.
- Table 1 status "supported" for a local norm sits beside "not settled" for the within-place design; the Abstract carries only the second.
- The Methods promise a cluster bootstrap throughout but the investigation block, the establishment variance and the panel use model SEs.
- Limitation (7) mentions census standard errors treating the sample as simple, yet the 0.29 (-0.05;0.63) census interval is used to argue "disagree"; the real interval is wider.
- The Black category: reduce to one sentence in the Results and delete "rose ... unevenly" in the Conclusion; the evidence is in paper 3.
- Report in the Abstract that the analyses of place are exploratory: it is there. Keep it, and add "written after the data were explored" in Methods (review 5 asked).
- Linked-share 2013 was 76.8% and 82.3% in 2023: a time trend in linkage that coincides with the time analysis; mention.

## 8. Top five required changes

1. Correct the long-panel interpretation (claim 4): report the lead and 2000-2010 results, give the fixed (-1) and following (0) benchmarks, and drop "followed the census population".
2. Report the within-place verification-service and medical-examiner effects, show all six covariates in Fig 5C, and remove "nothing within places" from Table 1.
3. Test residence against occurrence with equalised measurement error and a difference test before it is used to weaken the regional-Brown rival; otherwise state it as inconclusive.
4. Replace "followed the local majority in every cell" with the tested statement (three cells, slopes 0.64/-0.84/0.55, pivot at 58% not 50%), and state the prediction made before the data were seen.
5. Add intervals to Figs 2, 4B, 4D and 3 (or a mask), add the missing flow counts, report the Laplace refit and the physician sensitivity, put the father/partner limitation in the text, and fix the 35% crossing and the 0.26-to-0.25 against -0.19 sentences.

**Verdict: major revision (short)**
