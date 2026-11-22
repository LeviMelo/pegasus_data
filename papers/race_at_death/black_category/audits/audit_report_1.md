# Audit report 1 - paper 3, `black_category/`

## 0. Verdict

The descriptive numbers are reproducible: all 40 I recomputed match the JSON. The headline readings are not yet supported as worded. The 0.36 and 0.18 are gross shares, not net counts, so "undercount" is overstated. The facility-practice model attaches practice to the hospital where the infant died, not the one where the mother delivered. The ladder compares different populations and years. Some intervals and a regional ranking are wrong or unsupported. Fix section 1 before submission.

## 1. Errors (must fix)

**E1. Facility practice is joined on the wrong hospital.**
- `analysis/black.py` merges `fb` (practice of the delivery facility) onto the deaths by `death_estab`. The parquet has a separate `delivery_facility` column that is never used there.
- Among 13,992 Black-mother infants with a delivery facility, only 75.0% died in the establishment where the mother delivered (my count). Deaths with no establishment (3.7%) or in a facility without 30 Black SUS deliveries (mostly private hospitals) drop out.
- The model measures the practice of the dying hospital, a mixture of the same institution (75%) and others (25%). The Abstract and Discussion ("a hospital's practice with its mothers predicted the certificates") read it as the delivering hospital. Re-estimate with `delivery_facility`, or state what was measured.
- The mothers of the deaths also contribute to `fb`, a small circularity.

**E2. "Undercount" rests on gross shares; the net count is not reported.**
- From `black.json`: Black-declared recorded Black 0.363 x 939,740 = about 341k. Brown-declared recorded Black 0.038 x 8,172,530 = about 311k. White-declared recorded Black 0.0105 x 4,222,685 = about 44k.
- The hospital recorded about 696k Black mothers against 940k declared: a net ratio near 0.74, not 0.36. Misclassification of the large Brown group into Black offsets about half of the loss.
- The Conclusion and Implications ("undercount it ... most for children") need the net ratio for hospital and certificate. The certificate's Black share for Brown mothers' infants is not shown in the main text.
- Conditioning on a noisy declaration in the small category (Brown mothers outnumber Black 8.7 to 1) gives "Black recorded Brown" more often than the reverse even with symmetric noise.
- The SINASC declaration is treated as truth. The reading report notes the mother "chooses" only by instruction, and the hospital staff fill the form.

**E3. Denominators differ along the ladder.**
- Hospital rows exclude blanks: 21.8% of Black-declared admissions are blank (n = 1,201,503). So 0.36 is among admissions with a race. With blanks in the denominator it is 0.28.
- The infant certificate row keeps its 8.5% "other or none" in the denominator.
- Table 1 and Figure 1 compare 0.36 with 0.18 as if alike. The Abstract says "of 939,740 admissions" without the blank share. "Most Black mothers as Brown" is 0.53 only among the non-blank (0.41 of all).
- Blanks by race for the other groups are not shown.

**E4. The hospital intervals are binomial and ignore clustering by hospital.**
- Abstract, Results and Table 1 give "0.36 (95%CI 0.36; 0.36)", Brown "0.53; 0.53", White "0.10; 0.10".
- Hospitals range from 0.01 to 0.64 (p10 to p90). The infant row uses a municipal bootstrap (se 0.0074, 2.9 times its binomial se). The hospital row needs a bootstrap or cluster-robust interval by facility.

**E5. "Fastest in the South" (Abstract, Results, Figure 4B) is unsupported.**
- `spatial.json`: the South interaction is +0.80, se 0.50, p = 0.11. All region-by-year interactions have p > 0.36. The North slope (0.19) has se 0.46.
- Only the national slope (0.42, se 0.11) is established. Remove the ranking or give interval and a joint test.
- Figure 4B regional lines are conditional (random effects at zero). The national 2023 point, 0.21, lies above every region except the South, so the lines are not regional proportions. The caption must say so.

**E6. "While the hospitals' practice stayed the same" contradicts the data.**
- Hospital Black share 0.341 (2013) to 0.361 (2023): +0.020, se about 0.002 each, so significant. It peaked at 0.382 in 2020.
- The build assert `abs(HY['2023'] - HY['2013']) < 0.06` is a threshold, not a test of stability.
- Express both changes on one scale (hospital about +0.09 log-odds over ten years; certificate +0.42 per decade). Say the hospital series is not a fixed cohort: records of Black mothers with a hospital record double (721 in 2013, 1,434 in 2023).

**E7. The family benchmark and the age gradient are not comparable.**
- The census figures (0.39, 0.47, 0.52) concern surviving, co-resident children in 2010, with mother and child reported by the same informant. The certificates concern infants who died in 2013-2023. The Discussion itself cites rising Black identification after 2010 [8], which makes a 2010 benchmark too low.
- "The more so the younger the child" (Conclusion) should rest on certificates alone.
- Certificate 1-4 and 5-9 rows come from the candidate estimator in municipalities with fewer than 25,600 births a year; the infant row is national. Age is confounded with geography; restate infants in the same municipalities.
- Adjacent intervals overlap: infant 0.169-0.198, 1-4 years 0.196-0.275, 5-9 years 0.226-0.359. The build asserts point-estimate order only; "rose with the age of the deceased" has no test.
- The adult women (28% false pairs removed in expectation, hospital deaths, small municipalities) are another population.

**E8. Selection into the hospital rows is not characterised.**
- Only 10,568 of 22,305 Black mothers' infants (47%) have a SUS delivery admission. Those with and without are not compared (region, schooling, certified Black).
- The 490 excluded hospitals are removed from the matrix and the facility file but not from the individual file: 339 of the 10,568 (3.2%) come from them, 55 recorded Asian. Methods states the exclusion generally.
- The rule detects only a Yellow default. A Brown default (for example a system default) is undetected and is the main rival to "classification", for the 0.53. It is not discussed.
- Linked share of deaths rose from 0.77 (2013) to 0.82 (2023); the trend of the certificate is not examined against it.

## 2. Points to fix

1. **Individual association is crude.** 0.28 vs 0.12 is not adjusted for mother, place or hospital. A within-hospital contrast would separate person from place. The pattern is non-monotone: mothers recorded White by the hospital have infants certified Black at 0.17, above Brown-recorded (0.12); not discussed.
2. **Facility correlation 0.47** (328 hospitals, 10 or more deaths) is ecological, unweighted (weighted 0.52 in JSON) and noisy in both axes. Say which is quoted.
3. **State against composition (37% vs 22% of deviance).** The state term uses about 20 more degrees of freedom (residual df 581 vs 601). Compare at equal df or by out-of-sample deviance. The units are 605 municipalities with enough deaths; ecological.
4. **Multiplicity.** About 25 odds ratios, regional and age contrasts and several cross-tabs, with no named primary analysis. Declare the infant share and the hospital-certificate link primary; label the rest exploratory. The Discussion says verification services and examiners used it less "for the same kind of death", stated as fact.
5. **Shared appearance.** The Discussion says the rival does not explain three facts. The first (every record below declared) is what E2 predicts. The second is confounded with geography (E7). The third is confounded by cause and place of death. The rival is weaker-handled than stated.
6. **Year attribution.** Figure 4C plots the hospital by birth year and the certificate by death year. The practice measure pools 2012-2023, including births after the death. State both in Methods.
7. **Methods incomplete.**
   - Delivery linkage (item 2) has no match rate or false-link estimate, unlike item 1.
   - The multilevel specification (spline on white share, `z_*` terms), BYM2 priors and the year scaling are not stated.
   - The facility model uses a +0.01 smoothing of the rate and a 3-df spline; not mentioned.
   - The 20% of unlinked deaths are not characterised.
8. **Supplementary Table numbering.** The main text cites S4, then S2, S1, S3. Order by citation.
9. **Abstract.** "per logit unit" is not defined (logit of the practice share, smoothed). "Multilevel logistic regression ... against each hospital's practice" is wrong for the hospital model: it is a GLM with cluster-robust errors.
10. **Table 1 note.** "Census ... standard errors below 0.005" is not design-based; say so.
11. **Interpretation inside Results** ("without reaching it", "carried over") belongs in the Discussion.

## 3. Minor

- Figure 4C: the legend sits on the y-axis tick (0.3), and the panel has no y label. Figure 4A's title touches panel B's y label.
- Figure 1: the hospital error bar is invisible. The caption should say the 1.00 reference bar is by construction.
- Figure 2B caption: give the minimum of 10 deaths per hospital and what the area is (the panel title does).
- Figure 3 caption: say "per decade" is the year coefficient (OR about 1.5).
- Results: "939,740 were of mothers who declared themselves Black" reads as births; they are admissions with a race.
- "No study was found that followed ..." is a search claim; give the search or soften it.
- Strengths says "three records nationally"; the hospital record is SUS only (as Limitations says).
- Moran "residual clustering remained (0.13)" has no p-value in the text.

## 3b. References

- [9] The text cites the 2022 DO manual. `reading_report.md` verified only the 2011 DO and DN manuals. Read the 2022 edition or cite 2011.
- [12] Cardoso 2005: "differences in opposite directions" is not in the report's reading (rates underestimated, most for Brown; no linked records). Reword.
- [4] Monk and [6] Daflon are cited for "the Black and Brown categories are not interchangeable". Monk's abstract concerns skin colour beyond categories; Daflon's concerns discrimination. Neither says it directly. Soften.
- [8] Freeman 2025: LAPOP survey identification. The Discussion links it to rising mothers' declarations without a test.
- [2], [3], [5], [7], [8], [11]: abstract only (Muniz's Crossref abstract was missing; OpenAlex used). Claims should stay at abstract level; [11] "changed infant mortality by race" fits.
- [10] Travassos: read in full and supports the sentence. Its warning on numerator and denominator sources applies to the 2010 census comparison.
- Task D lists `telles1998` and `travassos2011` but not [1] `telles2002` in the same table (its entry is elsewhere in the report); consistent but untidy.

## 4. Numbers recomputed

Sources: `black.json`, `results.json`, `spatial.json`. Proportions est +/- 1.96 se; ORs exp(est +/- 1.96 se).

| # | Location | Printed | Recomputed | Status |
|---|---|---|---|---|
| 1 | Abstract, cert Black | 0.18 (0.17; 0.20) | 0.184 (0.169; 0.198) | ok |
| 2 | Abstract, cert Brown | 0.55 (0.53; 0.57) | 0.548 (0.527; 0.570) | ok |
| 3 | Abstract, cert White | 0.18 (0.16; 0.21) | 0.182 (0.156; 0.207) | ok |
| 4 | Family under 1 | 0.39 | 0.393 | ok |
| 5 | Hospital Black | 0.36 | 0.3626 | ok; CI see E4 |
| 6 | Median hospital | 0.24 | 0.2439 | ok |
| 7 | Hosp-Black mother, cert Black | 0.28 (0.27; 0.29) | 0.279 (0.265; 0.293) | ok |
| 8 | Hosp-Brown mother, cert Black | 0.12 (0.12; 0.13) | 0.124 (0.115; 0.132) | ok |
| 9 | Hosp-Black mother, cert Brown | 0.47 (0.45; 0.48) | 0.467 (0.451; 0.482) | ok |
| 10 | Hosp-White mother, cert Black | 0.17 (0.15; 0.20) | 0.172 (0.148; 0.196) | ok |
| 11 | Hosp-White mother, cert White | 0.39 (0.36; 0.42) | 0.394 (0.363; 0.425) | ok |
| 12 | Brown mother, hosp Black, cert Black | 0.06 (0.05; 0.07) | 0.063 (0.055; 0.071) | ok |
| 13 | Brown mother, hosp Brown, cert Black | 0.02 (0.01; 0.02) | 0.015 (0.014; 0.016) | ok |
| 14 | OR practice, full | 1.23 | 1.234 (1.168; 1.303) | ok |
| 15 | OR practice, alone | 1.36 | 1.363 (1.269; 1.463) | ok |
| 16 | Verification service OR | 0.59 (0.47; 0.75) | 0.591 (0.467; 0.748) | ok |
| 17 | Medical examiner OR | 0.65 (0.53; 0.81) | 0.652 (0.526; 0.809) | ok |
| 18 | Mother under 20 OR | 0.82 (0.74; 0.92) | 0.825 (0.742; 0.918) | ok |
| 19 | Mother 0-3 years OR | 1.25 (1.03; 1.51) | 1.251 (1.035; 1.512) | ok |
| 20 | Mother 12+ years OR | 1.14 (1.02; 1.28) | 1.144 (1.022; 1.281) | ok |
| 21 | Cert 1-4 years | 0.24 (0.20; 0.27) | 0.235 (0.196; 0.275) | ok |
| 22 | Cert 5-9 years | 0.29 (0.23; 0.36) | 0.292 (0.226; 0.359) | ok |
| 23 | Adult women, hospital | 0.37 (0.31; 0.44) | 0.373 (0.307; 0.438) | ok |
| 24 | Adult women, cert | 0.55 (0.48; 0.63) | 0.554 (0.479; 0.628) | ok |
| 25 | Family 1-4 / 5-9 | 0.47 / 0.52 | 0.465 / 0.522 | ok |
| 26 | Hospital Brown / White | 0.53 / 0.10 | 0.529 / 0.100 | ok |
| 27 | Blank admissions | 21.8% | 21.79% | ok |
| 28 | Cert Black 2013 / 2023 | 0.15 / 0.21 | 0.1545 / 0.2124 | ok |
| 29 | Slope per decade | 0.42 (0.20; 0.64) | 0.420 (0.204; 0.637) | ok |
| 30 | North / South slope | 0.19 / 0.99 | 0.192 / 0.192+0.796 = 0.988 | ok; not significant (E5) |
| 31 | Hospital 2013 / 2023 | 0.34 / 0.36 | 0.341 / 0.361 | ok; difference real (E6) |
| 32 | Black births 2013 / 2023 | 5.6% / 7.9% | 5.58% / 7.88% | ok |
| 33 | Variance explained: composition, SES, services, all | 39, 19, 22, 58% | 39.4, 18.8, 22.1, 58.1% | ok |
| 34 | Deviance: state, composition, census composition | 37, 22, 24% | 37.4, 22.0, 24.0% | ok |
| 35 | Moran, residual | 0.42, 0.13 | 0.420, 0.126 | ok |
| 36 | False links | 0.57-0.75% | 0.57-0.75 | ok |
| 37 | Linked share | 80.5% | 309,203/383,975 = 80.5% | ok |
| 38 | Facility correlation | 0.47 | 0.4726 (weighted 0.520) | ok |
| 39 | "More than twice as likely" | - | 0.279/0.124 = 2.26 | ok |
| 40 | Establishment / municipal variance | 0.31 / 0.10 | 0.3086 / 0.0952 | ok |

Not recomputable from the JSON: the 2022 admissions figures in Supplementary Text S1 (0.74, 0.80, 0.37; 1,208,430).
