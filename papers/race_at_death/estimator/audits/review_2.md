# Referee report 2: paper 6 (the candidates-less-control estimator)

Reviewer standard: Statistics in Medicine / IJE / JRSS-A methods paper. Read: manuscript, supplement, audit and response, reading notes, `text*.py`, `estimator.json`, `simulation.json`, `analysis/{estimator,simulate,pair,infant_findable}.py`, `modelled_race.py` (`candidate_counts`, `_candidates`, `pair_candidate_counts`, `pair_truth`, `candidate_difference`, `candidate_estimates`), the three figures, ADR-0229 and ADR-0233. Nothing was run or edited. Points the response already answered are not repeated unless the answer is inadequate (marked "answer inadequate").

## 0. Overall judgement

**Major revision.** The idea is sound and useful: counting a death's same-key candidates and subtracting the other sex's records of the same day is a defensible way to estimate a cross-classification without linkage, and the algebra of E[T] and of the delta-method variances is correct for the stated independence model. The first audit's honesty fixes are visible. The paper still falls short of a methods-journal standard in five ways.

1. The validation does not test the estimator in the regime it is used in (ages 1-14, 28-39% not found), and neither validation compares like with like. The truth covers the linked subset; the estimator runs on all units.
2. The claim that A1 cannot be tested is wrong. The paper's own admissions data reject it, and the paper does not say so.
3. The simulation is benign by construction: Poisson births with no day-level overdispersion, A2 true, a fabricated and arbitrary mover mechanism, and one cell (Indigenous) silently left out of the headline bias statement. Coverage and bias statements are selectively summarised.
4. There is no head-to-head against any competing method. The obvious ones are the unique-key link, uniform 1/c attribution, the EM/ML contingency-table methods the paper cites but does not use, and ecological regression (Goodman / King / Wakefield) on the key cells. The estimator is, in effect, an ecological-regression moment estimator with a negative-control regressor, and the literature on that is absent.
5. Real-data calibration of the intervals fails (chance interval: 5 of 20 and 7 of 20 cells out against findable pairs; model interval: 9 of 80, P=0.018 under 5%), and the mismatch of unit sets (point 1) is the obvious cause. The response's "the known answers are too noisy" is untested and probably wrong.

All of this is fixable with data and code already in hand (section 5). Reject is not warranted.

## 1. Errors in derivation, code or numbers

Ranked by consequence.

**1.1 The headline "bias at most 0.004 / 0.009" omits the Indigenous cell, where the bias is 9 to 20 times larger.**
- Location: `text.py:20` (`P_CELLS`, five cells that exclude `p_indigenous_indigenous`), used in `hold_small`, `hold_bias`, the abstract and Results.
- Evidence (`simulation.json`, ideal, 6,400-25,599): `p_indigenous_indigenous` bias +0.0817, MCSE 0.0219, z=3.7. Twins: +0.062, z=3.7. Sparse, 1,600-6,399: +0.074, z=3.4. QUANT computes it; the text never mentions it.
- Across the 44 size x quantity cells of ideal, 4 have |z|>1.96 (9%); in sparse, 7 (16%).
- Fix: report the maximum over all QUANT cells, or state why Indigenous is excluded. Do not call the estimator "nearly unbiased" at 6,400-25,599 for rare rows.

**1.2 The "small-sample bias of a ratio of sums" is a heavy-tail artefact, not a bias.**
- Evidence (sparse, 6,400-25,599, Black as Black): mean bias +0.134, **median bias -0.0215** (opposite sign), sd 0.819. Indigenous: mean +0.533, median -0.124, sd 8.36.
- 27 of 200 replicates have a non-positive row sum (the `_invalid` counter), and the code includes them (`ok = np.isfinite(est)` removes only NaN/inf). A ratio whose denominator can cross zero has no finite mean.
- Fix: say "no finite moments where the row sum can be non-positive". Report medians and the failure rate. State how failed replicates are handled (ADEMP requires it).

**1.3 "The model interval covered nominally" is false for pooled and large classes.**
- Evidence (ideal, Black as Black): empirical sd vs mean model SE is 0.0268 vs 0.0366 for `all` (x1.37). It is 0.0074 vs 0.0114 for `mix_black` (x1.54). Twins >=25,600 White as White is 1.246 vs 3.777.
- Coverage is 99.5-100% there: over-coverage, not nominal.
- Cause (suspected): the mean of SEs over replicates is dominated by replicates with a near-zero denominator. Check with sqrt(mean variance) and the median SE.
- Cause (certain): the variance omits the two covariances in 1.4.
- Fix: report variance ratio (mean model variance / empirical variance) and median SE per class, and drop "nominally".

**1.4 The documented "units that share a key share their candidates" is not what the SQL implements.**
- `candidate_counts` builds `d` with `GROUP BY dn, sex, mun, k, age, cause, dy`, so g is the number of deaths sharing key, class, age, cause and year. Simulation and `pair_candidate_counts` group by key and class only.
- Deaths with the same key but a different certified class (or cause) share the same candidates, yet enter V as independent. So Cov(T(j,k), T(j,k')) is omitted.
- The two sexes also share records: a day's girls are the chance candidates of girls' deaths and the (scaled) control of boys' deaths. The cross term in the coefficient on the girls' count, (g_F - s g_M)^2 vs g_F^2 + s^2 g_M^2, is ignored. The response calls it "second order" without evidence.
- The terms vanish where deaths per key cell are about 0 (small municipalities) and matter exactly in the large classes the paper discards. They are likely part of 1.3.
- Fix: aggregate g over all deaths of the key cell (and sex pair), then test by simulation.

**1.5 Rate-ratio "truth" for size classes is mismatched, so S1 shows spurious bias.**
- `truth_of` uses deaths by municipality of residence at death (r) over person-years (`expo`) by municipality of birth. A mover is a death in class r but an exposure in class m.
- Evidence: movers, <400, Black/Brown truth 1.202 (ideal 1.103), "bias" -0.101, coverage 62-67%. Selective: -0.190.
- The estimator is right; the target is wrong. Table 3 hides this; S1 does not explain it.
- Fix: define size-class ratio truth with matched numerators and denominators, or drop size-class ratios under movers.

**1.6 `colour_known` is vacuous, and the 'other' cell hides missing race.**
- `estimator.py` computes `avg((col IN (...))::INT)`; `NULL IN (...)` is NULL and `avg` skips it, so the value is 1.0 whenever the non-null values are listed, regardless of how many are missing.
- The 'other' column (non-four-class or missing hospital race) is 18.6% / 27.3% / 29.1% of the White / Black / Brown rows of the findable pairs (`estimator.json` `pair.by_size[all].findable`). Table 2 reports only the diagonal and never tells the reader that about 20-30% of hospital race is missing.
- Fix: report the missing share explicitly. Re-express the headline "50.2% vs 62.8%" conditional on a recorded race: 0.628/(1-0.186)=0.771 vs 0.502/(1-0.256)=0.675, a 9.6-point gap, of which 7.0 points are extra missingness in the unfindable.
- Consequence: the "13 points" is mainly a data-quality selection (sloppy records are both unfindable and race-missing), not "movers or other people". The Discussion's mechanism is not supported.

**1.7 The chance-interval failure is not explained by "the known answer's 1% false links"; the unit mismatch is (response to audit 5: answer inadequate).**
- The estimator runs on all units. The truth is the table of the linked 80.5% (infants) or 95.9% (admissions). The chance SE conditions on the units being fixed, so it is the wrong yardstick for est - table(linked).
- The linked subset's table differs from the all-units table by a thinning term, roughly p(1-p)(1/n_l - 1/n), the same order as the model SE. That alone predicts chance-interval failure and that the model interval cope better.
- Evidence: `outside_chance` against findable, infants <400: 7/20 (P(X>=7|20,0.05)=3x10^-5); 400-1,599: 6/20. Admissions all: 5/20 (P=0.003). Table 1 omits the infant chance counts.
- A 1% false-link rate changes a cell by at most 0.01 x |p_wrong - p_true| (about 0.007), well below many of the failures.
- Fix: run the estimator on exactly the linked units (and separately on the unlinked), which is trivial because deaths are the units (see 5.1). Then the chance interval is testable and the false-link claim becomes checkable.

**1.8 Minor numbers and wording.**
- "a ratio ... (the ratio of the shares found, 1.11)": nominal (1-0.22)/(1-0.30)=1.114. The realised effect is 0.722/0.660=1.094 (own-municipality draws are non-moves). Say "nominal".
- The infant "found 89.8% vs 80.5% linked" is a 9.3-point (13.4 vs findable-of-all) gap. It is reported without explanation, though it bears on whether the estimator or the linkage is the more complete.
- Cell-level z-scores in Table 1 would show the 9/80 vs 4 expected.

## 2. Assumptions

| assumption | testable? | tested in the paper? | my assessment |
|---|---|---|---|
| A1: t_j independent of k given j | **Yes, on any linked subset: findability by (j,k) cell** | No. The paper says "the data cannot identify t_j", Discussion. | **Rejected by the paper's own admissions data (below).** |
| A2: both sexes same class composition and ratio s per day | Yes: sex ratio by class in SINASC; placebo (shifted date); swap sex roles; stratify admissions by age | Simulated only (a2: 52.5% vs 50.5%, arbitrary). Admissions "state vs municipality scaling" is a weak check. | Plausible for births; **not established, and the register of deaths violates it** (15-29 y: 28.1% vs 39.3% White by sex), yet the validation cannot show the tolerance because chance is 0.01-0.09 per unit in four of five classes. |
| A3: related records of the person's class | Partly | Simulated with twins from a fixed rate | Fine for births (mother's declaration); twins born across midnight just drop out. Siblings born the same day are rare. |
| Implicit: Poisson births (no day-level overdispersion, sexes independent given day) | Yes: index of dispersion, sex correlation of daily counts in real SINASC | No | **The variance rests on it; the simulation has no overdispersion.** If sexes are positively correlated within day, SEs are conservative; if cells are overdispersed, they are anti-conservative. Undetermined. |
| Implicit: birth-day size bias | Partly | ADR-0229 only (shifted-date control gave "found" 1.4-6.2, other sex 0.61-0.74) | Handled by sharing the day. The evidence that justifies the central design choice is in an ADR and should be in the paper. |
| Implicit: scale s | Yes | Admissions only (mun vs UF). Not for births. | s is estimated per municipality-year from the same records (noise; slight bias in tiny cells, because the control's own records sit in s's denominator). Births have a near-constant sex ratio, so a state or national s should be tried: a one-line sensitivity. |
| Implicit: movers, SIM residence field | Partly | Simulated with invented rates | SIM residence is sometimes filled with the municipality of occurrence for hospital deaths of children (class-dependent in remote areas). Compare residence vs occurrence municipality by class. |
| Implicit: SINASC coverage / late registration by class | Yes (by class, from IBGE estimates) | No | Enters t_j. |
| Implicit: "race at birth" is the mother's own declaration | Known | Stated | Name the estimand "mother's race on the birth record by child's race on the certificate" everywhere; the title and abstract say "race at birth". |

**A1 is rejected on the paper's own data.** From `estimator.json` (admissions, all sizes), with p = findable share among linked, by certificate class:
- t(White) 0.913, t(Black) 0.896, t(Brown) 0.882, t(Indigenous) 0.807.
- By cell within the White row: t(hospital White) = 1,049,917/(1,049,917+80,377)=0.929, t(hospital other/missing) 0.884, t(hospital Brown) 0.888.

So findability depends on k given j, and on j. The paper calls these quantities not identifiable; they are, wherever a linkage with extra fields exists. They also give an independent, real-data lower bound on rate-ratio distortion from key errors alone: Indigenous/Brown scaled by 0.807/0.882 = 0.915, a 8.5% bias before any moving.

**Sex-ratio heterogeneity.** The a2 scenario's two points are arbitrary. State the real male share by race in SINASC (unknown to the reader) and report the bias that scenario implies.

## 3. Validation and simulation adequacy

**3.1 Validation does not match the application (audit 14, answer inadequate).**
- Target: ages 1-14, found about 72%, movers dominant.
- Infants: found 90%, movers rare; the truth shares the key by construction (the linkage rewards agreement on birth date, sex and residence, hence "95% findable").
- Admissions: key errors, not moves; chance candidates few.
- Neither tests the subtraction where it matters. The "limitation" paragraph is correct but the abstract and conclusion still say "validated". A census-based external check is available (5.3).

**3.2 The estimator's population differs from the truth's** (1.7). The response's "findable" column only restricts the truth, not the estimator's units.

**3.3 Simulation makes the estimator look good by construction.**
- (a) Births are independent Poisson per day x sex x class with a deterministic weekday/season weight; the same weights for every municipality; no day-level shocks, no hospital clustering. A2 holds exactly except in `a2`.
- (b) The class certified at death is drawn from the infant-linkage matrix by decile of White share of the destination, independent of everything else. Between-municipality heterogeneity beyond the decile is zero, so the cluster SE cannot differ from the model SE (0.0148/0.0148 in ideal <400). The paper concedes this; the abstract/Discussion still discuss "the cluster error was several times the model error" as an empirical fact.
- (c) Movers are 28% and 22/30/34% with an invented mechanism; "selective" adds 12 points to discordant children. Single points, no sensitivity surface. The Lash 2014 citation calls for a bias model with parameter ranges.
- (d) "ideal" puts 12 cohorts' deaths (77,693) into one 2018 cohort. Per death, chance density is right, but deaths sharing a key are 12x too frequent. `sparse` has the real density but 1/12 of the deaths. The real regime is 12 independent `sparse` cohorts pooled, which is simply not simulated. The text says "the real number of deaths" for ideal, which is true only of the count.
- (e) Key errors (typos, wrong municipality code, date/month swaps), distinct from moves, are not simulated. They are half of "not found" in the admissions.
- (f) The mortality ratios (0.66, 1.1, 4.1) used to drive the DGM are the estimator's own output on real data. Mildly circular for the rate-ratio truth.
- (g) 200 replicates, one seed. MCSE of the bias is 0.003 at the sizes where the claims are made; coverage MCSE is 1.5 points at 95%, so 92% is 1.9 MCSE below nominal and cannot be called nominal. Coverage MCSE is never shown. Three coverage definitions (all deaths, system value, found) x four SEs are reported and then summarised as "92-100%".
- (h) "Coverage of all deaths, model" is 100% in ideal <400 by design (the SE includes death-sampling variance, the realised table does not): over-coverage, not validity.
- (i) Heavy-tailed results (1.2) are summarised by means.

**3.4 Coverage claims depend on which SE and which target.** The cluster interval's 89% minimum and the counts' 86% minimum are quoted, but the model interval's 91.5% minimum is described as "92%". With 60 cells, a 1.5-point MCSE and cells expected to be correlated, a few values near 91-92% are expected under nominal coverage. The honest summary is "consistent with nominal, within MCSE, up to 6,400 births a year".

## 4. Comparison with established methods and literature gaps

The Discussion compares only in words. A demanding referee will ask for numbers against the following, all implementable on the existing counts.

1. **Unique-key deterministic link** (units with one same-key candidate): the practitioner's default. Its bias is exactly the chance/found mixture. Required; the response (audit 7) said "not tabulated". It is the minimum baseline.
2. **Uniform attribution (each of c candidates has weight 1/c)**, equivalent to Fellegi-Sunter with a single agreeing field and no discriminating power. The estimator's advantage over it is the paper's whole claim.
3. **Probabilistic linkage with error adjustment**: Fellegi & Sunter 1969; Winkler 1988 (EM); Jaro 1989; Belin & Rubin 1995 (cited); Lahiri & Larsen 2005 and Chambers 2009 (regression/contingency analysis of linked data); **Chipperfield, Bycroft & Chambers 2011, Survey Methodology 37:13-24 (ML for contingency tables with incorrectly linked data) is the closest published method and was dropped because Crossref matched another work; retrieve it**; Chipperfield & Chambers 2015 (cited, not used).
4. **Candidate-set EM/MI** (Goldstein, Harron & Wade 2012, cited): a latent-link likelihood over each death's candidate set. It would use the unique-candidate days efficiently, whereas the moment estimator gives them the same weight as 36-candidate days. The efficiency loss in large municipalities (failure above 25,600) is exactly this. Also Tancredi & Liseo 2011 (cited), Steorts, Hall & Fienberg 2016, Sadinle 2017, Gutman, Afendulis & Zaslavsky 2013.
5. **Ecological inference.** The estimator is a cross-moment of death-class counts with sex-differenced birth-class counts over key cells, i.e. a Goodman (1953) regression with a negative-control regressor. A Poisson/multinomial regression of death counts by class on same-sex birth counts by class (with municipality-by-sex-by-class intercepts for inflow) estimates t_j N(j,k) under weaker conditions, since it needs no equal-composition A2, and carries GLM theory and sandwich SEs by municipality. Cite and compare: Goodman 1953; Duncan & Davis 1953 (bounds; tight here because key cells are tiny); King 1997; Wakefield 2004 (JRSS A, aggregation bias and ecological bias); Rosen, Jiang, King & Tanner 2001 (R x C); Greiner & Quinn 2009 (R x C with survey information). This literature is absent. The claim "All work from individual pairs" (Introduction) is false for it.
6. **Dual-system / capture-recapture**: t is a capture probability; Chandrasekar & Deming 1949; Ding & Fienberg 1994 (dual-system estimation with matching error), Brittain & Boehning 2009. The paper's t estimate has a natural interpretation and validation (census) there.
7. **Statistical matching** (D'Orazio, Di Zio & Scanu 2006): joining files on common variables under conditional independence; the contrast (here the person is *in* the key cell, so no CIA) should be stated.
8. **Negative-control calibration**: Lipsitch et al. 2010 (cited, for the idea only), Schuemie et al. 2014 (Stat Med, empirical p-value calibration with negative controls) and Schuemie et al. 2018 (PNAS, empirical CI calibration), Tchetgen Tchetgen 2014 (control outcome calibration), Shi, Miao & Tchetgen Tchetgen 2020. The paper uses negative controls only to subtract; it does not use them to calibrate the SEs, which the real-data failures (1.7) call for.
9. **Estimating random agreement by construction** in linkage: Newcombe 1959; Herzog, Scheuren & Winkler 2007. The "other sex" control is a u-probability estimated by an engineered non-match; the novelty claim should be placed against this.
10. **Variance**: Binder 1983 (linearisation; in notes, uncited), cluster bootstrap, jackknife for ratio bias (Quenouille), Fieller or logit intervals for proportions, small-area / empirical-Bayes shrinkage of municipal classification (Fay & Herriot 1979; Clayton & Kaldor 1987) for the between-municipality heterogeneity.
11. **Race on certificates**: Arias et al. 2010 (NCHS, validity of race and Hispanic origin on death certificates) and the Brazilian linkage-cohort results for external benchmarks (the 100 Million Brazilian Cohort, already cited for scale).
12. **ADEMP**: Morris 2019 (cited) requires failure handling, MCSE for every performance measure, and a justification of the number of repetitions. None given.

## 5. Analyses the data allow but the paper lacks, ranked

1. **Run the estimator on exactly the linked units, and on the unlinked ones** (both validations). Removes the unit mismatch (1.7), makes the chance interval testable, shows whether the linked and the unlinked 19.5% (infants) differ, and gives found share among the unlinked. Cheapest and most decisive.
2. **Placebo and falsification on the real data.** (a) Shift the key date by +/-7, +/-14 days (same weekday) and recompute T: every cell should be 0 within its SE; the z distribution gives an empirical null and calibrates the SEs (Schuemie). (b) Compute T for boys and for girls separately; the two tables should agree (a direct A2 test). (c) Same-sex-other-municipality control. (d) Sex ratio, daily dispersion and sex correlation of SINASC counts by class.
3. **Validate in the application regime.** The estimator gives t by *recorded* class k (T(+,k)/D_k) and by age, region, cause. Compare with census (2010/2022) microdata: share of children aged a living in the municipality of birth, by race. That replaces the invented 28%. Also compare SIM residence vs occurrence municipality by class.
4. **Report A1 diagnostics from the linked data.** Findability by (j,k), by j, by age and by size (the admissions numbers in section 2). Add a quantitative bias analysis over a grid of (t_j, selective moving), with the headline tipping points, not two points.
5. **Calibrate model vs cluster SE on real data.** Split-half by municipality and by year, municipality bootstrap, compare predicted and realised variance. For the 1-9 Indigenous ratio the cluster SE is 0.727 vs 0.264 (x2.8); the Discussion recommends the model SE with no evidence.
6. **Head-to-head comparators** (section 4, items 1, 2, 4, 5), in simulation (bias, RMSE, coverage) and in the infant validation (difference from linkage).
7. **Stratify the admissions validation** by sex-composition gap (age 15-29) and by chance per unit: a dose-response test of A2, since chance is highest where A2 is weakest.
8. **Efficiency**: inverse-variance combination across size classes and key cells so that the 7 large municipalities (15% of births) are not discarded; pooled "all" is already 0.007 vs 0.005, so the failure is variance, not bias. State the design criterion as expected chance candidates per unit, not municipality size.
9. **Simulation upgrades**: day-level overdispersion with sex correlation; key errors; 12 pooled sparse cohorts; random municipality effects in classification (so cluster SE is testable); 1,000+ replicates (3 s each); common random numbers; MCSE for coverage; medians.
10. **Sensitivity of s** (state/national, shrinkage) for births, and of the Wald vs logit/bootstrap intervals for rare rows.

## 6. Claims stronger than evidence

| quote | why | rewording |
|---|---|---|
| "the estimator reproduced the linked table cell by cell" (Results, Infant deaths) | 9 of 80 cells outside the model interval (P=0.018 at 5%); 7 of 20 outside the chance interval in the smallest class; truth is the linked 80%, estimator all units | "agreed within 0.026 in every cell below 25,600 births a year (mean 0.005); 11% of cells fell outside the 95% model interval" |
| "the model interval covered nominally in the simulation" (Discussion, Variance) | 99.5-100% and SE overstated 37-54% in pooled and large classes; MCSE 1.5 points | "was conservative or close to nominal up to 6,400 births a year and conservative above" |
| "nearly unbiased (at most 0.004 below 6,400 births; 0.009 above)" (abstract, Results) | Indigenous cell +0.082 (z 3.7); five-cell selection | "bias at most 0.004 below 6,400 births for the five commonest cells; up to 0.08 for the Indigenous row at 6,400-25,599" |
| "the small-sample bias of a ratio of sums" | median bias has the opposite sign; heavy tails | "the mean is dominated by replicates with a near-zero denominator (median bias -0.02)" |
| "Its bias is the difference between those people and the rest, which the public files cannot measure" and "not a property of the estimator but of the key" | the paper's admissions data do measure part of it; findability depends on k given j, so it is also a property of A1 and of the estimator's weighting; a linkage using other fields would not share it | "its bias is the selection of who shares the key; in admissions linked to certificates it is measurable and was ..." |
| "the 13 percentage points" selection effect | 7 of the 12.6 points are extra missing hospital race among the unfindable | give the gap conditional on a recorded race (9.6 points) and the missing share |
| "A cross-classification ... can be estimated ... for the people whose key the two registers share" (Conclusions) and "Wherever two public registers share ..." (Use) | the working limit is expected chance candidates per unit, not stated as such; seven largest municipalities fail; application regime untested | add the design criterion; "validated for infants and hospital deaths, not yet for ages 1-14" |
| "The estimator built on them gave, for race at death after infancy, the table ... where no other source did" (Introduction) | unverifiable here; no result for that regime; companion papers only | delete or cite the companion paper |
| "All work from individual pairs." (Introduction) | ecological-inference and dual-system methods do not | "The linkage-error methods cited work from individual pairs" |
| "the cluster error ... was several times the model error for the admissions ... because the classification varies between them" | untested; the simulation cannot test it (no heterogeneity); the response says so | "possibly because..." and test it (5.5) |
| "For a national table ... the model error is the one to report" | recommends the smaller SE where it is 2.8x smaller (Indigenous ratio) with no real-data calibration | withhold until calibrated (5.2, 5.5) |
| "models ... 92%-100% of replicates" | min 91.5% rounded up; MCSE 1.5 | "91-100%, within Monte Carlo error of 95% up to 6,400 births" |

## 7. Presentation

- Title is 29 words; the abstract Results paragraph has 14 numbers and no estimand statement. State the estimand (a 4x5 table, with t).
- The Methods "estimator" paragraph is one 400-word block mixing definitions, assumptions, expectations and consequences. Move variance derivations to a boxed set; keep one numbered equation list.
- Table 3 has 10 columns and each cell holds two numbers; the reader cannot see MCSE or the |z|. Put a z or "bias / MCSE" column and a coverage MCSE footnote.
- Table 1 "0.78 / 0.78" cells are unlabelled in the header (estimator / linked, only in the footnote). Add chance-interval counts to Table 1 (omitted, 1.7).
- Table 1 municipality counts sum to 5,969 vs 5,529: footnoted, but confusing. State the unit.
- Figure 2 is a scatter against the diagonal over 0-1: dominated by the large cells (the diagonals) and shows nothing about calibration. Use z-scores (estimate-truth)/SE by cell and size, or a Bland-Altman plot with the two intervals.
- Figure 3: bias axes differ per panel, and sparse Black at 6,400+ (0.134) compresses the others; use a free-scale per panel with a common z panel. Add the MCSE band of coverage at 95%.
- A RECORD flow diagram (383,975 -> 309,203 linked -> 94.5% findable; 3,766,913 -> 3,613,329 -> 3,247,014) is missing.
- Terms: "found", "findable", "linked" and "key" are used interchangeably in the abstract; define once. "Certified White, recorded White in hospital" is ambiguous; say which register is the row.
- The paper says it "makes no statement about race", yet the title, abstract and discussion use race as the example estimand: acceptable, but name the estimand in the Methods.
- References: reading_notes shows full texts unread for nearly all; the Chipperfield 2011 omission is a substantive gap, not a bibliographic one (section 4).

## 8. Numbers recomputed

All from `results/estimator.json` and `results/simulation.json` unless stated. "OK" = matches the manuscript.

| # | quantity | recomputed | manuscript |
|---|---|---|---|
| 1 | infant linked share 309,203 / 383,975 | 0.8053 | 80.5% OK |
| 2 | admissions linked 3,613,329 / 3,766,913 | 0.9592 | 95.9% OK |
| 3 | admissions findable 3,247,014 / 3,766,913 | 0.8620 | 86.2% OK |
| 4 | findable among linked | 0.8986 (10.1% not) | "10%" OK |
| 5 | admissions found 0.8323 vs 4-class findable (3,142,382/3,766,913) | 0.8342 | gap 0.19 points; supports the paper's note on the four races |
| 6 | White recorded White: findable vs unfindable | 0.628 vs 0.502 = 12.6 points | "13" OK |
| 7 | same, conditional on recorded race | 0.771 vs 0.675 = 9.6 points | not reported |
| 8 | missing hospital race, White row | 18.6% vs 25.6% (+7.0) | not reported |
| 9 | t among linked by certificate class (W/B/Br/I) | 0.913 / 0.896 / 0.882 / 0.807 | not reported |
| 10 | t(White row): hospital White / other / Brown | 0.929 / 0.884 / 0.888 | A1 violated, not reported |
| 11 | Table 2 municipality-years 22,621+12,275+3,110+748+140 | 38,894 | 38,894 OK |
| 12 | infants findable share of linked, <25,600 (0.7590/0.8035); all (0.7644/0.8053) | 94.5%; 94.9% | 94.5% OK for <25,600 |
| 13 | infants found 0.8982 vs linked 0.8053 vs findable of all 0.7644 | +9.3; +13.4 points | "89.8% vs 80.5%" OK |
| 14 | infants <25,600 births share | 0.853 | "85%" OK |
| 15 | cells outside model 95% CI: 3+4+2+0 | 9 of 80 = 11.3%; P(X>=9) under 5% = 0.018 | "9 of 80" OK |
| 16 | infant chance interval against findable, <400 / 400-1,599 / all | 7 / 6 / 1 of 20 (P(>=7)=3x10^-5) | not in Table 1 |
| 17 | admissions chance outside against findable, all | 5 of 20 (P=0.003) | "5" OK; "model 2" OK |
| 18 | infant Black as Black <400: 0.1354 +/- 1.96 x 0.00612 | 0.123; 0.147 | OK |
| 19 | no-control mean difference infants <25,600 / <400 | 0.0687 / 0.0148; max 0.438 at 1,600-6,399 | 0.069, 0.44 OK |
| 20 | simulation: ideal `all` found / twins / movers | 0.9591 / 0.9703 / 0.7113 | 95.9%, 97.0% OK; movers lost 25.8% = "26%" OK |
| 21 | twins found gain: 3.9% twin deaths x (2/3 - s/3 = 0.31) | +1.2 points | observed +1.1: consistent |
| 22 | unequal: 0.660 + 0.062 = 0.722; ratio of shares | 1.094 (nominal 1.114) | text "1.11": nominal, not realised |
| 23 | ideal invalid replicates >=25,600 | 28 of 200 (twins 35, sparse 131) | "28 of 200" OK |
| 24 | ideal `p_indigenous_indigenous` 6,400-25,599 | +0.0817, MCSE 0.0219, z 3.7 | omitted |
| 25 | sparse 6,400-25,599 Black as Black: mean / median / sd | +0.134 / -0.022 / 0.819 | "0.134" is the mean |
| 26 | ideal `all` Black as Black: empirical sd / model SE | 0.0268 / 0.0366 (x1.37); mix 0.0074 / 0.0114 (x1.54) | "covered nominally" |
| 27 | coverage MCSE at 95%, n=200 | 1.54 points; 91.5% = 2.3 MCSE below | "92%-100%" |
| 28 | sparse deaths 77,693/12 | 6,474 (sim mean 6,466) | OK |
| 29 | 1-9 Indigenous ratio SE: cluster / model | 0.727 / 0.264 (x2.8) | not reported in text |
| 30 | `hold_small`, `hold_big` over five proportions | 0.0039, 0.0093 | "0.004, 0.009" OK, with 1.1 |
| 31 | `hold_z` | 3.0 (five cells); 3.7 over all quantities | "3.0" OK for the subset |
| 32 | movers <400 Black/Brown truth vs ideal | 1.202 vs 1.103 | target mismatch (1.5) |

Transcription is accurate throughout; the problems are selection of what is summarised, target definitions and calibration.
