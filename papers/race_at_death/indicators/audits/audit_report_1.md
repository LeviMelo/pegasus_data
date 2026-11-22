# Audit report 1 - paper 2, `indicators/`

Read: `indicators/out/manuscript.txt`, `supplement.txt`, the Table 1 and S1/S2 bodies (from the .docx), `indicators/text*.py`, `results.json`, `spatial.json`, paper 1 text, `reading_report.md`, Figures 1, 2 and S1 (PNG). Nothing was run except read-only Python on the JSON.

## 0. Verdict

Arithmetic is sound: all 40 printed numbers I recomputed match the JSON (section 4), and the paper's headline direction (mother's-race ratio below 1, certified-over-births ratio above 1) is real and large. The wording is ahead of the evidence in five places. (1) The "census-based denominator compresses the ratio toward none at 1-4 years" finding rests on an unvalidated modelled population with no interval, and is contradicted by the family's classification at the same age. (2) "The reversal was general" is mostly posterior means pulled toward a national mean below 1; credible reversal is in 115 of 510 regions. (3) The headline 1-4 mother's-race ratio uses municipalities where the estimator is shown to fail, unlike paper 1. (4) Table 1's infant mother's-race column uses the weaker estimator while the text uses the linkage; one printed sentence pairs rates and a ratio that do not belong together. (5) Black to Brown is in the objective but its infant result (the largest reversal) is absent from the text. Fix section 1 before submission.

## 1. Errors (must fix)

**E1. The census-denominator result is unexplained, has no interval, and conflicts with the family benchmark.**
- Location: Abstract Results/Conclusion ("compressed toward none at 1-4 years"); Results para 1; Discussion para 1 ("because the census, like the certificate ... classifies part of Brown mothers' children as White"); Methods (3) "as rates after infancy are usually computed".
- Evidence:
  - `C14.conventional_2016_2024.ratio_certificate_population` = 0.944 against 0.805 for infants (`infant_rates.ratio_certificate_population` = 0.800). Both come from the same account (S2), so the Discussion's census-classification mechanism would predict the same at both ages. It does not.
  - At 1-4 years the same census's own household classification, applied by mother's race (the family's classification), gives 0.79 (`C14.ratio_household`), not 0.94. So the compression is a property of the modelled population account (2022 shares carried back, S2), not of how the census classifies children.
  - S2 itself lists coverage change, the 2022 questionnaire change and differential mortality or emigration as unseparated explanations.
  - No interval is given for the 0.80, 0.94 or 0.88 values. The 0.94 stands against 0.66 (0.54; 0.81) with no uncertainty on the account; the reader cannot tell 0.94 from 0.79.
  - "as rates after infancy are usually computed" has no citation.
- Fix: say that the compression is not shown to come from the census classification. Give an interval or a range (for example the 0.79-0.94 span between the 2010 household shares and the account). Explain why infants and 1-4 differ in the same account. Cite a source for the practice, or delete the phrase. In the Abstract replace "over census-based denominators it is kept in infancy and compressed toward none" with the values and "depends on the modelled population".

**E2. "The reversal was general across the country" overreads shrunken posterior means.**
- Location: Results para 3, Abstract (400 of 510), Discussion ("in most of the country's regions"), Conclusion.
- Evidence:
  - `misstated`: 400 of 510 regions have opposite posterior means (78%; 82% of births). Credible reversal (both intervals excluding 1) is 115 of 510 (23%). The mother's ratio is credibly below 1 in 159 (31%), against 446 (87%) for the certified ratio.
  - The regional mother's-race effects are shrunk: `ratio.mother` national fixed effect -0.107 (ratio 0.90, below 1), sd_total 0.16. A region with few White deaths therefore gets a ratio near 0.90 whatever its data. Counting "opposite direction" by posterior mean is partly a consequence of the prior.
  - "Credibly" is never defined (95% credible interval? excluding 1?).
- Fix: lead with 115 (and the 159 and 446 asymmetry); state that the mother's-race ratio is not credibly different from 1 in 351 regions; define credible; reword "general" to "in 400 regions by posterior mean, credibly in 115". Say what the national fixed effect of each model is.

**E3. The headline 1-4 mother's-race ratio includes municipalities where the estimator is shown to be wrong; paper 1 excludes them.**
- Location: Methods ("reproduced the linkage's proportions in infants in municipalities with fewer than 25,600 births a year [14]"); Abstract and Table 1 (0.66 (0.54; 0.81)); Results last paragraph.
- Evidence:
  - `validation`, White mothers certified White, candidate against linkage: 25,600 or more births, 0.849 against 0.708 (+14 points); 6,400-25,599, 0.689 against 0.715. These strata hold 114,200 of 381,514 infant deaths (30%).
  - Paper 1 (Methods, Statistical analysis) restricts the 1-9 year proportions to municipalities under 25,600 because the estimator loses precision there. Paper 2 uses all sizes for the same deaths (60,146 at 1-4). The excluded-large result is 0.73 (0.67; 0.80), and the main text calls the choices "robust" with no reason for the main analysis to keep the failing stratum.
  - The statement "it reproduced the linkage's proportions" has no number in paper 2, and the 6,400-25,599 stratum is 2.6 points off.
  - Lipsitch et al. [14] (negative controls) is cited for the validation claim. The reading report supports only the use of the opposite-sex candidates as a control. It does not support "reproduced the linkage".
- Fix: either exclude the 25,600+ stratum from the headline (as paper 1) and report the all-size ratio as sensitivity, or justify keeping it with the stratum error shown. Give the validation numbers in one sentence. Move [14] to the sentence on the control.

**E4. Infant "mother's race" is estimated two ways; the printed sentence pairs mismatched numbers.**
- Location: Results para 1 and Table 1.
- Evidence: "10.7 per 1,000 ... 13.5 ... The White to Brown ratio was 0.81" - 10.69/13.45 = 0.794, the candidate ratio (0.79), not the linked 0.81. Table 1 uses the candidate estimator for the infant row (White 0.79; Black 1.26 (1.15; 1.37); Indigenous 1.84) although the linkage exists. The linked values are Black 1.15 (1.09; 1.20), Indigenous 1.60 (1.46; 1.75). The candidate Black ratio lies outside the linked interval. Figure 1D plots 0.79 while the Abstract gives 0.81.
- Fix: for infants, put the linked rates and ratios (rates scaled by linked share) in Table 1, Figure 1 and the rate sentence; keep the candidate estimator for 1-9 years and state the infant comparison as validation.

**E5. Black to Brown is in the objective but not reported for infants, nor regionally.**
- Location: Objective/Aims ("White to Brown and Black to Brown ratios"); Results.
- Evidence: the only Black to Brown results in the text are at 1-4 years. Infant values are in the table only: linked 1.15 (1.09; 1.20) against certified 0.49 (0.48; 0.50), the largest reversal in the paper (a factor 2.4; White to Brown is 1.6). The Abstract and the 510-region models carry White to Brown only. Indigenous ratios (certified 2.48, 6.00) are unmentioned.
- Fix: report the infant Black to Brown pair in the Abstract and Results, or drop "Black to Brown" from the objective, title-level claims and conclusion.

## 2. Points to fix

1. **Rate definitions and coverage are not stated.** Methods never gives the age band and period of each rate, or the denominator years.
   - Infant deaths are 2013-2023 and births "2012-2023" (Design), but the infant rate denominator (births 29.84M in `infant_rates.births`) must be 2013-2023 births; say so, and say whether the rate is period (deaths in year over births in year) or cohort.
   - Deaths at 1-9 years of 2013-2024 are restricted to children born 2012-2023 (paper 1: 77,693 = 60,146 + 17,547). A 5-9 rate therefore covers cohorts born 2012-2019 only, weighted to ages 5-6 (age 5 reached from 2017). The 1-4 rate of 2013-2015 covers only age 1-3. Table 1 labels both "2013-2024".
   - The census comparison uses 2016-2024 (when 1-4 cohorts are all born 2012 or later); the reason is not given.
   - The births denominator excludes blank-race births and "Yellow"; Table 1 omits Yellow with no note. SINASC's field was mother-declared in only 92.7% of 2012 births (paper 1).
2. **BYM2 specification is not stated.** The paper gives no graph (queen contiguity of immediate regions?), no priors (paper 1 says penalised-complexity; paper 2 is silent), no offset, no mixing parameter, no definition of "credible" and no software. "Effects for the region and for the region's White to Brown contrast" is not a model. Posterior values: mother phi 0.72, sd 0.16; certificate phi 0.84, sd 0.50 (`ratio`). Add one sentence plus a supplementary line.
3. **Regional and national figures are not reconciled.** Births-weighted class means of the certified ratio are 1.52-2.92 in every class (`by_composition`), all above the national pooled 1.31; the mother's-race class means are 0.83-0.93, all above the national linked 0.81. The model's national terms are exp(0.757) = 2.13 and exp(-0.107) = 0.90. The cause is aggregation (composition between regions) plus shrinkage. A reader meeting "1.31" and "3.15 times" needs the one-sentence reason.
4. **"U-shaped" rests on four class means with no interval** (3.15, 1.92, 1.83, 2.19) and hand-set class limits (10%, 30%, 60%). The rise from 1.83 to 2.19 is small; Figure 2D shows a mild rise. Say "highest where under 10% were White, with a smaller rise above 60%", or give a fit.
5. **"Pulled toward its mean by the model (0.93 in that class)"** is asserted, not shown. Compare with the raw ratios in those 138 regions, or soften.
6. **Mechanism is incomplete.** The Discussion counts only Brown-to-White movement. The flow table also has White mothers' infants certified Brown (0.17) and Black mothers' infants certified Brown (0.55), which add to the Brown numerator. The net effect (Brown rate 13.5 to 10.7) should be shown by a counterfactual with the flow matrix, not argued.
7. **Mother's race is treated as the reference without saying so in the conclusions.** "Reversed", "misstated" (Figure 2C label, `misstated`) and "excess mortality present when classified by the mother" read the mother's declaration as truth; the Limitations says only "a declaration, not a truth". The word "misstated" in the Figure and Supplementary Table S1 is stronger than the "differs".
8. **Unlinked deaths (19.5%).** Linkage equality is shown by certified race (81.1/81.1/80.2; Indigenous 61.9%, not mentioned) but the exposure is the mother's race, unobserved for unlinked deaths. The scaling assumption (linked deaths scaled to all) is not stated as an assumption. "Equal linkage" (Discussion) is a 0.9-point difference tested by nothing.
9. **Primary outcome and multiplicity.** No primary analysis is named. Many CIs and counts (159, 446, 115, 469) are read as findings. Declare the infant White to Brown linked against certified-over-births contrast primary; label 1-9 years, regional and census-based results secondary.
10. **No uncertainty on the census-based or family's ratios**, and the "larger of Poisson and jackknife" se for national ratios ignores linkage and population-account error. State this in the limitations, not only for the family's classification.
11. **Different "not estimable" rules**: S2 uses se above 0.35 of the estimate, Figure S1 0.6, paper 1 0.15. Use one rule or explain.
12. **Intro claim uncited:** "Brazil monitors racial inequality in child health through mortality rates by race", and "the Ministry's infant indicator" is defined as certified deaths over births by the mother's race with no Ministry source.
13. **Sensitivity "robust".** The estimator sensitivity (0.57-0.77 for the t differential; 0.63-0.70 leave-one-state-out; 0.73 without large) lies within the 0.54-0.81 interval, which is itself wide. "Robust" is fine for direction; do not use it for the magnitude.
14. **Figure 2** colour bars stop at 4 (A, B) and 3 (C) while Supplementary Table S1 has ratios of 10.75 and 12.62; say the scale is censored. Check that Figure 2D (y-axis top about 11) shows the 12.62 region.

## 3. Minor

- Abstract Methods says "Infant deaths of 2013-2023 ... linked"; Results/Table say 2013-2023 for infants and 2013-2024 elsewhere; make the title's "2013-2024" explicit about infants.
- Table 1 footnote: "Census-based population: White to Brown only" - say 5-9 years has none (the column shows "-").
- "A quarter ... more than half" (Discussion) agrees with 0.25 and 0.55 (paper 1, 0.25 (0.23; 0.27) and 0.55 (0.53; 0.57)); give the numbers.
- Figure 1 panels B and C titles "per 100,000" should read "per 100,000 person-years"; the x-axis of panel D uses ticks 0.5, 0.67, 1, 1.5 with no label of the log scale in the caption.
- Supplementary Table S1 column "Certified over mother's" uses the word "understates" for the last 10 regions; it means certified ratio below mother's.
- Introduction: the mother's declaration "since 2011 [3]" against paper 1 (55.0% filled in 2011, 92.7% in 2012); say the births used start in 2012.
- Fellegi-Sunter [13] was not read in the reading report (publisher blocked); acceptable for a method citation but flagged as unverified.

## 3b. References

Source for check: `references/reading_report.md`.
- [1] manual do 2022, [3] DN manual 2011: used as in paper 1; the reading report does not list them, so they are unverified here beyond paper 1's use. [2] Travassos: supported (SINASC mother-reported, certificate by physician or staff). Do not use its date for mandatory reporting.
- [4] Cardoso, [5] Caldas: supported for "differences in opposite directions"; neither uses linked records, so "between sources" is right and the Discussion may not add "linked".
- [6] Hahn: supported (inconsistency changes small-group rates).
- [7] Arias 2016: supported for American Indian misclassification (about 40%); "understate American Indian mortality" is a reading of the abstract, which says misclassification, not direction; read the full text or write "misclassify".
- [8] Rebouças: supported (19,515,843 births 2012-2018; crude rates 950.98 and 1,201 under 1 year, 38.24 and 55.19 at 1-4 years; ratios 0.79 and 0.69 verified from Table 2). The text compares crude ratios with the paper's crude ratios: correct. The cohort covers born 2012-2018 with different follow-up; "gives" should say "agrees with" (0.79 within 0.78-0.84; 0.69 within 0.54-0.81).
- [9] RECORD: cited for reporting, but no RECORD checklist or code-availability statement is in the text.
- [10]-[12] public data pages: ok.
- [13] Fellegi and Sunter: not read (see 3).
- [14] Lipsitch: misplaced for "reproduced the linkage" (E3); fits only the control.
- [15]-[18] Besag/York/Mollié, Riebler, Rue, Lindgren: method references; not read in the reading report; plausible for BYM2 and INLA.

## 4. Numbers recomputed (est +/- 1.96 se on the log scale for ratios)

| # | Quantity | Printed | Recomputed from JSON | Status |
|---|---|---|---|---|
| 1 | Linked share | 80.5% | 309,203 / 383,975 = 80.53% | ok |
| 2 | Linked, certified White/Brown/Black | 81.1, 81.1, 80.2% | 81.14, 81.09, 80.21 | ok |
| 3 | False links per year | 0.57-0.75% | min 0.57 (2017), max 0.75 (2021) | ok |
| 4 | Infant rate, White mothers | 10.7 | 10.688 | ok |
| 5 | Infant rate, Brown mothers | 13.5 | 13.454 | ok |
| 6 | W/B linked | 0.81 (0.78; 0.84) | 0.8106 (0.780; 0.843) | ok |
| 7 | W/B candidate | 0.79 (0.73; 0.86) | 0.7944 (0.730; 0.865) | ok |
| 8 | W/B printed rates 10.7/13.5 | (sentence gives 0.81) | 0.794 | mismatch (E4) |
| 9 | W/B certified over births | 1.31 (1.30; 1.32) | 1.3096 (1.301; 1.319) | ok |
| 10 | Census-based, infants | 0.80 | 0.8005 | ok |
| 11 | Family's, infants | 0.88 | 0.8759 | ok |
| 12 | 1-4 y mother | 0.66 (0.54; 0.81) | 0.6632 (0.543; 0.810) | ok |
| 13 | 1-4 y certified | 1.43 (1.40; 1.45) | 1.4271 (1.403; 1.452) | ok |
| 14 | 1-4 y census-based | 0.94 | 0.9442 | ok, no interval |
| 15 | 1-4 y family's | 0.79 | 0.7888 | ok |
| 16 | 1-4 y mother, 2016-2024 | 0.66 (0.54; 0.81) | 0.6633 (0.543; 0.810) | ok |
| 17 | 5-9 mother | 0.67 (0.48; 0.93) | 0.6657 (0.479; 0.926) | ok |
| 18 | 5-9 certified | 1.21 (1.18; 1.25) | 1.2134 (1.176; 1.252) | ok |
| 19 | 5-9 family's | 0.78 | 0.7833 | ok |
| 20 | Black/Brown 1-4, mother | 1.11 (0.83; 1.48) | 1.109 (0.833; 1.476) | ok |
| 21 | Black/Brown 1-4, certified | 0.81 (0.78; 0.85) | 0.8138 (0.780; 0.849) | ok |
| 22 | Rebouças crude under 1 / 1-4 | 0.79, 0.69 | 950.98/1201 = 0.792; 38.24/55.19 = 0.693 | ok |
| 23 | Blank given mother's race | 1.22 | 1.2242 | ok |
| 24 | Table 1: 59.9/42.0 | 1.43 | 1.427 | ok |
| 25 | Table 1: 22.2/18.3 | 1.21 | 1.213 | ok |
| 26 | Table 1: 15.7/23.6 | 0.67 | 0.666 | ok |
| 27 | Reversed regions | 400 of 510 | 400/510 = 78.4% | ok ("most" ok) |
| 28 | Births in reversed regions | 82% | 0.8230 | ok |
| 29 | Credible: mother<1, cert>1, both, diff | 159, 446, 115, 469 | same | ok; 115 = 23% |
| 30 | Ratio of ratios <10% White | 3.15 | 3.1458 (= 2.922 / 0.9289) | ok |
| 31 | 10-29% | 1.92 | 1.9186 (= 1.6846 / 0.8780) | ok |
| 32 | 30-59% | 1.83 | 1.8276 (= 1.5233 / 0.8335) | ok |
| 33 | 60% or more | 2.19 | 2.1854 (= 1.9163 / 0.8769) | ok |
| 34 | Mother ratio in <10% class | 0.93 | 0.9289 | ok |
| 35 | 1-4 y without large | 0.73 (0.67; 0.80) | 0.7343 (0.671; 0.803) | ok |
| 36 | Leave one state out | 0.63 to 0.70 | 0.6349 to 0.7007 | ok |
| 37 | t differential | 0.57 to 0.77 | 0.5710 to 0.7704 | ok |
| 38 | Infant certificates | 383,975 | 383,975 | ok |
| 39 | t for infants (S1) | 89.8% | 0.8980 | ok |
| 40 | Quarter / more than half | 0.25 / 0.55 | Parda>Branca 0.2518; Preta>Parda 0.5485 | ok |
| 41 | Table S1 first row | 0.81, 10.28, 12.62 | exp(-0.2048) = 0.815; exp(2.3303) = 10.28; 2.5351 -> 12.62 | ok |
| 42 | Paper 1 agreement | 80.5%, 81.1/81.1/80.2, 0.57-0.75, 383,975, 25,600, 0.25 / 0.55, 77,693 = 60,146 + 17,547 | same in paper 1 | ok; the handling of the 25,600 threshold differs (E3) |
